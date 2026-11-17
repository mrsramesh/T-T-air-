#!/usr/bin/env python3
"""
Multi-Carrier Cargo Tracking CLI (Air India, Lufthansa Cargo, Emirates SkyCargo & Kuwait Airways).
Provides rich, interactive command-line tracking across major airlines.
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
from emirates_tracker.client import EmiratesTrackerClient
from emirates_tracker.browser import EmiratesBrowserTracker
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError
from kuwait_tracker.browser import KuwaitBrowserTracker

console = Console()


def detect_carrier(awb_input: str) -> str:
    """Detect carrier by AWB prefix."""
    cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
    if cleaned.startswith("229"):
        return "kuwait"
    if cleaned.startswith("176"):
        return "emirates"
    if cleaned.startswith("020"):
        return "lufthansa"
    if cleaned.startswith("098"):
        return "airindia"
    if len(cleaned) == 8:
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


# ==================== EMIRATES SKYCARGO RENDERING ====================

def render_emirates_overview(overview):
    """Render Emirates SkyCargo summary overview card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold red", justify="right")
    grid.add_column()
    grid.add_column(style="bold red", justify="right")
    grid.add_column()

    grid.add_row(
        "AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
        "Route:", f"[bold magenta]{overview.origin.code} ({overview.origin.name or ''}) ➔ {overview.destination.code} ({overview.destination.name or ''})[/bold magenta]"
    )
    grid.add_row(
        "Pieces:", f"{overview.pieces} pcs",
        "Gross Weight:", f"{overview.gross_weight:,.1f} {overview.weight_unit}"
    )
    grid.add_row(
        "Volume:", f"{overview.volume:.3f} {overview.volume_unit}",
        "Chargeable Wt:", f"{overview.chargeable_weight:,.1f} {overview.weight_unit}" if overview.chargeable_weight else "N/A"
    )
    grid.add_row(
        "Commodity / Product:", f"[bold white]{overview.commodity or overview.product_name or 'General Cargo'}[/bold white]",
        "Special Handling:", f"{', '.join(overview.special_handling_codes) if overview.special_handling_codes else 'None'}"
    )
    grid.add_row(
        "Booking Ref (BRN):", f"{overview.booking_reference_number} (JRN: {overview.job_reference_number or 'N/A'})",
        "Order Status:", f"[bold green]{overview.order_status}[/bold green]"
    )

    console.print(Panel(
        grid,
        title=f"[bold red]✈ Emirates SkyCargo[/bold red] - [bold white]{overview.formatted_awb}[/bold white]",
        border_style="red",
        box=box.ROUNDED
    ))

    ms_banner = (
        f"[bold cyan]Latest Milestone:[/bold cyan] [bold white]{overview.latest_milestone_code}[/bold white] - "
        f"{overview.latest_milestone_description} "
        f"@ [bold yellow]{overview.latest_milestone_station or '---'}[/bold yellow] "
        f"({overview.latest_milestone_time or 'N/A'})"
    )
    console.print(Panel(ms_banner, border_style="gold1", box=box.SQUARE))


def render_emirates_itinerary(legs):
    """Render Emirates flight routing & schedule."""
    table = Table(title="[bold red]🛫 Emirates SkyCargo - Flight Routing & Itinerary[/bold red]", box=box.ROUNDED)
    table.add_column("Flight", style="bold red")
    table.add_column("Origin ➔ Destination", style="magenta")
    table.add_column("Departure (Local)", style="white")
    table.add_column("Arrival (Local)", style="white")
    table.add_column("Aircraft / Reg", style="cyan")
    table.add_column("Movement Status", style="green", justify="center")

    if not legs:
        console.print("[dim yellow]No flight itinerary legs available.[/dim yellow]")
        return

    for leg in legs:
        route = f"{leg.origin.code} ➔ {leg.destination.code}"
        dep = f"Sched: {leg.scheduled_departure or 'N/A'}"
        if leg.actual_departure and leg.actual_departure != leg.scheduled_departure:
            dep += f"\n[dim green]Act: {leg.actual_departure}[/dim green]"

        arr = f"Sched: {leg.scheduled_arrival or 'N/A'}"
        if leg.actual_arrival and leg.actual_arrival != leg.scheduled_arrival:
            arr += f"\n[dim green]Act: {leg.actual_arrival}[/dim green]"

        ac = []
        if leg.aircraft_type:
            ac.append(leg.aircraft_type)
        if leg.registration_number:
            ac.append(f"Reg: {leg.registration_number}")
        ac_str = " | ".join(ac) if ac else "Boeing 777"

        status = f"[bold green]{leg.movement_status}[/bold green]" if leg.movement_status else "---"
        table.add_row(leg.flight_display, route, dep, arr, ac_str, status)

    console.print(table)


def render_emirates_milestones(milestones):
    """Render Emirates milestones event timeline."""
    table = Table(title="[bold green]📋 Emirates SkyCargo - Milestones & Tracking History[/bold green]", box=box.ROUNDED)
    table.add_column("Date & Time", style="cyan", no_wrap=True)
    table.add_column("Code", style="bold red")
    table.add_column("Description", style="white")
    table.add_column("Station", style="magenta", justify="center")
    table.add_column("Pieces / Weight", justify="right")
    table.add_column("State", justify="center")

    if not milestones:
        console.print("[dim yellow]No milestones history recorded.[/dim yellow]")
        return

    for m in milestones:
        pcs_wt = []
        if m.pieces is not None:
            pcs_wt.append(f"{m.pieces} pcs")
        if m.weight is not None:
            pcs_wt.append(f"{m.weight:.1f} {m.weight_unit}")
        pcs_wt_str = " / ".join(pcs_wt) if pcs_wt else "---"

        badge = "[bold green]LATEST[/bold green]" if m.is_latest else "[dim]Archived[/dim]"
        table.add_row(
            m.timestamp or "N/A",
            m.code,
            m.description,
            m.station or "---",
            pcs_wt_str,
            badge
        )

    console.print(table)


# ==================== KUWAIT AIRWAYS RENDERING ====================

def render_kuwait_overview(overview, station_boxes):
    """Render Kuwait Airways summary overview card & station transit cards."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold blue", justify="right")
    grid.add_column()
    grid.add_column(style="bold blue", justify="right")
    grid.add_column()

    grid.add_row(
        "AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
        "Route:", f"[bold cyan]{overview.origin} ➔ {overview.destination}[/bold cyan]"
    )
    grid.add_row(
        "Pieces:", f"{overview.pieces} pcs",
        "Gross Weight:", f"{overview.gross_weight:,.1f} {overview.weight_unit}"
    )
    grid.add_row(
        "Volume:", f"{overview.volume:.2f} {overview.volume_unit}",
        "Current Status:", f"[bold green]{overview.current_status}[/bold green]"
    )

    console.print(Panel(
        grid,
        title=f"[bold blue]✈ Kuwait Airways Cargo[/bold blue] - [bold white]{overview.formatted_awb}[/bold white]",
        border_style="blue",
        box=box.ROUNDED
    ))

    # Station boxes cards
    if station_boxes:
        box_table = Table(title="[bold cyan]📍 Transit Station Checkpoints (Routing Boxes)[/bold cyan]", box=box.ROUNDED)
        box_table.add_column("Station", style="bold yellow", justify="center")
        box_table.add_column("Check-in / Intake (Event 1)", style="white")
        box_table.add_column("Departure / Delivery (Event 2)", style="white")
        box_table.add_column("Pieces & Weight", justify="right")

        for b in station_boxes:
            ev1 = f"[bold cyan]{b.status_code_1 or '---'}[/bold cyan]: {b.event_time_1 or 'N/A'}"
            ev2 = f"[bold green]{b.status_code_2 or '---'}[/bold green]: {b.event_time_2 or 'N/A'}"
            pcs_wt = f"{b.pieces or '---'} pcs / {b.weight or '---'} KGS"
            box_table.add_row(f"🏛 {b.airport}", ev1, ev2, pcs_wt)

        console.print(box_table)


def render_kuwait_flights(flights):
    """Render Kuwait Airways flight legs & routing table."""
    table = Table(title="[bold blue]🛫 Kuwait Airways - Flight Movements & Routing[/bold blue]", box=box.ROUNDED)
    table.add_column("Flight", style="bold cyan")
    table.add_column("Date", style="white")
    table.add_column("Origin ➔ Destination", style="magenta")
    table.add_column("Pieces", justify="right")
    table.add_column("Weight (KG)", justify="right")
    table.add_column("Volume (MC)", justify="right")
    table.add_column("Status", style="green")

    if not flights:
        console.print("[dim yellow]No flight segment details recorded.[/dim yellow]")
        return

    for fl in flights:
        route = f"{fl.origin} ➔ {fl.destination}"
        pcs = f"{fl.pieces} pcs" if fl.pieces is not None else "---"
        wt = f"{fl.weight:,.1f}" if fl.weight is not None else "---"
        vol = f"{fl.volume:.2f}" if fl.volume is not None else "---"
        status = f"{fl.status_message or fl.status_code or '---'}"
        table.add_row(fl.flight_number, fl.flight_date or "N/A", route, pcs, wt, vol, status)

    console.print(table)


def render_kuwait_events(events):
    """Render Kuwait Airways operational milestone events table."""
    table = Table(title="[bold green]📋 Kuwait Airways - Operational Status (Audit Events)[/bold green]", box=box.ROUNDED)
    table.add_column("Date & Time", style="cyan", no_wrap=True)
    table.add_column("Code", style="bold yellow", justify="center")
    table.add_column("Airport", style="magenta", justify="center")
    table.add_column("Status", style="white")
    table.add_column("Flight", style="blue")
    table.add_column("Details", style="dim white")

    if not events:
        console.print("[dim yellow]No operational events recorded.[/dim yellow]")
        return

    for ev in events:
        dt = f"{ev.event_date or ''} {ev.event_time or ''}".strip() or "N/A"
        fl = f"{ev.flight_number} ({ev.flight_date})" if ev.flight_number else "---"
        table.add_row(dt, ev.status_code, ev.airport or "---", ev.status_name, fl, ev.full_details or "---")

    console.print(table)


def main():
    parser = argparse.ArgumentParser(
        description="Production Multi-Carrier Air Cargo Tracker (Air India, Lufthansa Cargo, Emirates SkyCargo, Kuwait Airways)"
    )
    parser.add_argument(
        "awb",
        nargs="+",
        help="One or more AWB numbers (e.g. '098-30244056' Air India, '020-04585280' Lufthansa, '176-63116340' Emirates, '229-18148900' Kuwait Airways)",
    )
    parser.add_argument(
        "--carrier",
        choices=["auto", "airindia", "lufthansa", "emirates", "kuwait"],
        default="auto",
        help="Target carrier (default: auto-detected by AWB prefix 098, 020, 176, 229)",
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
        help="Execute live Playwright browser automation with screenshots",
    )

    args = parser.parse_args()

    lh_client = LufthansaCargoClient()
    ai_client = AirIndiaCargoClient()
    ek_client = EmiratesTrackerClient()
    kw_client = KuwaitCargoClient()

    lh_browser = LufthansaBrowserTracker()
    ek_browser = EmiratesBrowserTracker()
    kw_browser = KuwaitBrowserTracker()

    results = []

    for raw_awb in args.awb:
        carrier = args.carrier
        if carrier == "auto":
            carrier = detect_carrier(raw_awb)

        try:
            if carrier == "kuwait":
                if args.browser:
                    with console.status(f"[bold cyan]Running live Playwright browser automation for Kuwait Airways {raw_awb}...[/bold cyan]"):
                        clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                        screenshot = f"kuwait_{clean_serial}.png"
                        b_res = kw_browser.track_in_browser(
                            raw_awb,
                            headless=True,
                            screenshot_path=screenshot,
                        )
                        if b_res["error"]:
                            console.print(f"[bold red]❌ Kuwait Airways Portal Error:[/bold red] {b_res['error']}")
                            if b_res.get("screenshot_path"):
                                console.print(f"[bold yellow]📷 Error Screenshot saved:[/bold yellow] {screenshot}")
                            if args.json:
                                results.append({"awb": raw_awb, "error": b_res["error"]})
                            continue
                        else:
                            console.print(f"[bold green]✔ Browser workflow completed![/bold green] Portal URL: {b_res['final_url']}")
                            console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")
                            res = b_res["tracking_result"]
                else:
                    with console.status(f"[bold blue]Fetching Kuwait Airways tracking for {raw_awb}...[/bold blue]"):
                        res = kw_client.track(raw_awb)

                if args.json:
                    results.append(res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_kuwait_overview(res.overview, res.station_boxes)
                    if args.view in ("all", "tracking"):
                        render_kuwait_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_kuwait_events(res.operational_events)

            elif carrier == "emirates":
                if args.browser:
                    with console.status(f"[bold cyan]Running live Playwright browser automation for Emirates {raw_awb} via track-trace.com...[/bold cyan]"):
                        clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                        screenshot = f"emirates_details_{clean_serial}.png"
                        res_screenshot = f"emirates_results_{clean_serial}.png"
                        b_res = ek_browser.track_in_browser(
                            raw_awb,
                            headless=True,
                            screenshot_path=screenshot,
                            results_screenshot_path=res_screenshot,
                        )
                        console.print(f"[bold green]✔ Browser workflow completed![/bold green] Final URL: {b_res['final_url']}")
                        console.print(f"[bold green]✔ Results Screenshot:[/bold green] {res_screenshot}")
                        console.print(f"[bold green]✔ Details Screenshot:[/bold green] {screenshot}")
                        res = b_res["tracking_result"]
                else:
                    with console.status(f"[bold red]Fetching Emirates SkyCargo tracking for {raw_awb}...[/bold red]"):
                        res = ek_client.track(raw_awb)

                if args.json:
                    results.append(res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_emirates_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_emirates_itinerary(res.itinerary)
                    if args.view in ("all", "activity"):
                        render_emirates_milestones(res.milestones)

            elif carrier == "lufthansa":
                if args.browser:
                    with console.status(f"[bold cyan]Running live Playwright browser automation for Lufthansa {raw_awb}...[/bold cyan]"):
                        clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                        screenshot = f"lufthansa_{clean_serial}.png"
                        b_res = lh_browser.track_in_browser(raw_awb, headless=True, screenshot_path=screenshot)
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
