#!/usr/bin/env python3
"""
Multi-Carrier Cargo Tracking CLI (Air India & Lufthansa Cargo).
Provides rich, interactive command-line tracking for Air India (098) and Lufthansa Cargo (020) AWBs.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
import re
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import AirIndiaTrackerException
from lufthansa_tracker.client import LufthansaCargoClient
from lufthansa_tracker.browser import LufthansaBrowserTracker

console = Console()


def detect_carrier(awb_input: str) -> str:
    """Detect carrier by AWB prefix."""
    cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
    if cleaned.startswith("020"):
        return "lufthansa"
    if cleaned.startswith("098"):
        return "airindia"
    if len(cleaned) == 8:
        # Default can be asked or defaults to Lufthansa if user is on 020
        return "auto"
    return "airindia"


# ==================== AIR INDIA RENDERING ====================

def render_airindia_overview(overview):
    """Render Air India summary overview card."""
    status_color = "green" if overview.overall_status == "DELIVERED" else "yellow"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()

    grid.add_row("AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
                 "Route:", f"[bold magenta]{overview.origin_airport_code} ➔ {overview.destination_airport_code}[/bold magenta]")
    grid.add_row("Pieces:", f"{overview.pieces} pcs",
                 "Weight:", f"{overview.stated_weight:,.2f} {overview.weight_unit}")
    grid.add_row("Volume:", f"{overview.stated_volume:.2f} {overview.volume_unit}",
                 "Flights:", f"{overview.number_of_flights} Flights")
    grid.add_row("Product:", f"{overview.product_name or 'N/A'}",
                 "Handling:", f"{overview.special_handling_code or 'N/A'}")
    grid.add_row("Description:", f"{overview.shipment_description or 'N/A'}",
                 "Overall Status:", f"[bold {status_color} on default] {overview.overall_status} [/bold {status_color} on default]")

    console.print(Panel(grid, title=f"[bold red]✈ Air India Cargo[/bold red] - [bold white]{overview.formatted_awb}[/bold white]", border_style="red", box=box.ROUNDED))

    m_table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold blue")
    m_table.add_column("Milestone", justify="center")
    m_table.add_column("Status", justify="center")
    m_table.add_column("State", justify="center")

    for m in overview.milestones:
        is_done = m.is_completed
        icon = "✅ Done" if is_done else ("⏳ In Progress" if "progress" in m.status.lower() else "⚪ Pending")
        color = "green" if is_done else ("yellow" if "progress" in m.status.lower() else "dim")
        m_table.add_row(m.milestone, f"[{color}]{m.status.title()}[/{color}]", icon)

    console.print(m_table)


def render_airindia_tracking(segments):
    """Render Air India flight segments."""
    table = Table(title="[bold yellow]🛫 Air India - Flight Segments & Schedule (Tracking View)[/bold yellow]", box=box.ROUNDED)
    table.add_column("Flight", style="bold cyan")
    table.add_column("Route", style="magenta")
    table.add_column("Departure", style="white")
    table.add_column("Arrival", style="white")
    table.add_column("Pieces", justify="right")

    if not segments:
        console.print("[dim yellow]No specific flight segment details available.[/dim yellow]")
        return

    for s in segments:
        flight = f"{s.carrier_code or 'AI'} {s.flight_number or ''}".strip()
        route = f"{s.segment_origin or '---'} ➔ {s.segment_destination or '---'}"
        dep = f"{s.departure_date or ''} {s.departure_time or ''}".strip() or "N/A"
        arr = f"{s.arrival_date or ''} {s.arrival_time or ''}".strip() or "N/A"
        pcs = f"{s.pieces} pcs" if s.pieces is not None else "---"
        table.add_row(flight, route, dep, arr, pcs)

    console.print(table)


def render_airindia_activity(events):
    """Render Air India activity view."""
    table = Table(title="[bold green]📋 Air India - Event History (Activity View)[/bold green]", box=box.ROUNDED)
    table.add_column("Date & Time", style="cyan", no_wrap=True)
    table.add_column("Event", style="bold yellow")
    table.add_column("Description", style="white")
    table.add_column("Station", style="magenta")
    table.add_column("Pcs / Wt", justify="right")
    table.add_column("Flight / ULD", style="blue")

    if not events:
        console.print("[dim yellow]No activity logs recorded.[/dim yellow]")
        return

    for ev in events:
        dt = ev.event_time or ev.last_updated_time or "N/A"
        code = ev.event_code
        desc = ev.event_name
        station = ev.airport_code or "---"

        pcs_wt = []
        if ev.pieces is not None:
            pcs_wt.append(f"{ev.pieces} pcs")
        if ev.weight is not None:
            pcs_wt.append(f"{ev.weight:.1f}{ev.weight_unit}")
        pcs_wt_str = " / ".join(pcs_wt) if pcs_wt else "---"

        flight_uld = []
        if ev.flight_number:
            flight_uld.append(f"{ev.flight_carrier_code or 'AI'} {ev.flight_number}")
        if ev.uld_number:
            flight_uld.append(f"ULD: {ev.uld_number}")
        flight_uld_str = " | ".join(flight_uld) if flight_uld else "---"

        table.add_row(dt, code, desc, station, pcs_wt_str, flight_uld_str)

    console.print(table)


# ==================== LUFTHANSA RENDERING ====================

def render_lufthansa_overview(overview):
    """Render Lufthansa Cargo overview card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold yellow", justify="right")
    grid.add_column()
    grid.add_column(style="bold yellow", justify="right")
    grid.add_column()

    grid.add_row("AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
                 "Route:", f"[bold cyan]{overview.origin.code} ({overview.origin.name or ''}) ➔ {overview.destination.code} ({overview.destination.name or ''})[/bold cyan]")
    grid.add_row("Pieces:", f"{overview.pieces} pcs",
                 "Gross Weight:", f"{overview.gross_weight:,.1f} {overview.weight_unit}")
    grid.add_row("Volume:", f"{overview.volume:.2f} {overview.volume_unit}",
                 "Product:", f"{overview.product_name or 'N/A'} ({overview.product_code or '---'})")
    grid.add_row("Special Codes:", f"{', '.join(overview.special_cargo_codes) if overview.special_cargo_codes else 'None'}",
                 "Latest Event:", f"[bold blue]{overview.latest_event}[/bold blue]")

    console.print(Panel(grid, title=f"[bold yellow]✈ Lufthansa Cargo[/bold yellow] - [bold white]{overview.formatted_awb}[/bold white]", border_style="yellow", box=box.ROUNDED))

    # Banner for latest status
    console.print(Panel(f"[bold green]Latest Event:[/bold green] {overview.latest_event_description}", border_style="blue", box=box.SQUARE))


def render_lufthansa_flights(flights):
    """Render Lufthansa flight movements."""
    table = Table(title="[bold yellow]🛫 Lufthansa Cargo - Flight Movement & Segments[/bold yellow]", box=box.ROUNDED)
    table.add_column("Flight", style="bold cyan")
    table.add_column("Origin ➔ Destination", style="magenta")
    table.add_column("Date", style="white")
    table.add_column("Departure (Sched / Actual)", style="white")
    table.add_column("Arrival (Sched / Actual)", style="white")
    table.add_column("Aircraft / Transport", style="blue")

    if not flights:
        console.print("[dim yellow]No flight information available.[/dim yellow]")
        return

    for fl in flights:
        route = f"{fl.origin.code} ➔ {fl.destination.code}"
        dep = f"{fl.actual_departure or fl.scheduled_departure or 'N/A'}"
        arr = f"{fl.actual_arrival or fl.scheduled_arrival or 'N/A'}"
        table.add_row(fl.flight_number, route, fl.flight_date or "N/A", dep, arr, fl.aircraft_type or "Aircraft")

    console.print(table)


def render_lufthansa_history(events):
    """Render Lufthansa status history."""
    table = Table(title="[bold green]📋 Lufthansa Cargo - Status History (Audit Events)[/bold green]", box=box.ROUNDED)
    table.add_column("Date & Time", style="cyan", no_wrap=True)
    table.add_column("Event", style="bold yellow")
    table.add_column("Description", style="white")
    table.add_column("Station", style="magenta")
    table.add_column("Pieces / Weight", justify="right")
    table.add_column("Flight", style="blue")
    table.add_column("State", justify="center")

    if not events:
        console.print("[dim yellow]No status history available.[/dim yellow]")
        return

    for ev in events:
        pcs_wt = []
        if ev.pieces is not None:
            pcs_wt.append(f"{ev.pieces} pcs")
        if ev.weight is not None:
            pcs_wt.append(f"{ev.weight:.1f} kg")
        pcs_wt_str = " / ".join(pcs_wt) if pcs_wt else "---"

        state_badge = "[green]Actual[/green]" if ev.is_actual else "[dim]Planned[/dim]"
        table.add_row(ev.event_time or "N/A", ev.event_code, ev.event_name, ev.station or "---", pcs_wt_str, ev.flight_number or "---", state_badge)

    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Production Multi-Carrier Air Cargo Tracker (Air India & Lufthansa Cargo)"
    )
    parser.add_argument(
        "awb",
        nargs="+",
        help="One or more AWB numbers (e.g. '098-30244056' for Air India, '020-04585280' or '04585280' for Lufthansa)",
    )
    parser.add_argument(
        "--carrier",
        choices=["auto", "airindia", "lufthansa"],
        default="auto",
        help="Target carrier (default: auto-detected by AWB prefix 098 or 020)",
    )
    parser.add_argument(
        "--view",
        choices=["all", "overview", "tracking", "activity"],
        default="all",
        help="View mode to display (default: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON format",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="For Lufthansa: execute live Playwright browser automation (clicks Deny, inputs AWB, takes screenshot)",
    )

    args = parser.parse_args()

    lh_client = LufthansaCargoClient()
    ai_client = AirIndiaCargoClient()
    browser_tracker = LufthansaBrowserTracker()

    results = []

    for raw_awb in args.awb:
        # Determine carrier
        carrier = args.carrier
        if carrier == "auto":
            carrier = detect_carrier(raw_awb)

        try:
            if carrier == "lufthansa":
                if args.browser:
                    with console.status(f"[bold cyan]Running live Playwright browser automation for Lufthansa {raw_awb}...[/bold cyan]"):
                        screenshot = f"lufthansa_{raw_awb.replace('-', '')}.png"
                        b_res = browser_tracker.track_in_browser(raw_awb, headless=True, screenshot_path=screenshot)
                        console.print(f"[bold green]✔ Browser automation completed![/bold green] Results URL: {b_res['result_url']}")
                        console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                with console.status(f"[bold yellow]Fetching Lufthansa Cargo tracking for {raw_awb}...[/bold yellow]"):
                    res = lh_client.track(raw_awb)

                if args.json:
                    results.append(res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_lufthansa_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_lufthansa_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_lufthansa_history(res.status_history)

            else:
                # Default to Air India
                with console.status(f"[bold red]Fetching Air India Cargo tracking for {raw_awb}...[/bold red]"):
                    res = ai_client.track(raw_awb)

                if args.json:
                    results.append(res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_airindia_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_airindia_tracking(res.tracking_view)
                    if args.view in ("all", "activity"):
                        render_airindia_activity(res.activity_view)

        except Exception as e:
            if args.json:
                results.append({"awb": raw_awb, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Error tracking AWB {raw_awb}:[/bold red] {e}")

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))


if __name__ == "__main__":
    main()
