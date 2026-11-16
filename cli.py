#!/usr/bin/env python3
"""
Air India Cargo Tracking CLI.
Provides rich, interactive command-line tracking for Air India Cargo AWBs.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import argparse
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import AirIndiaTrackerException


console = Console()


def render_overview(overview):
    """Render shipment summary overview card."""
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

    # Milestones bar
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


def render_tracking_view(segments):
    """Render flight segments (Tracking View)."""
    table = Table(title="[bold yellow]🛫 Tracking View - Flight Segments & Schedule[/bold yellow]", box=box.ROUNDED)
    table.add_column("Flight", style="bold cyan")
    table.add_column("Route", style="magenta")
    table.add_column("Departure", style="white")
    table.add_column("Arrival", style="white")
    table.add_column("Pieces", justify="right")

    if not segments:
        console.print("[dim yellow]No specific flight segment details available for this shipment.[/dim yellow]")
        return

    for s in segments:
        flight = f"{s.carrier_code or 'AI'} {s.flight_number or ''}".strip()
        route = f"{s.segment_origin or '---'} ➔ {s.segment_destination or '---'}"
        dep = f"{s.departure_date or ''} {s.departure_time or ''}".strip() or "N/A"
        arr = f"{s.arrival_date or ''} {s.arrival_time or ''}".strip() or "N/A"
        pcs = f"{s.pieces} pcs" if s.pieces is not None else "---"
        table.add_row(flight, route, dep, arr, pcs)

    console.print(table)


def render_activity_view(events):
    """Render detailed audit trail (Activity View)."""
    table = Table(title="[bold green]📋 Activity View - Chronological Event History[/bold green]", box=box.ROUNDED)
    table.add_column("Date & Time", style="cyan", no_wrap=True)
    table.add_column("Event", style="bold yellow")
    table.add_column("Description", style="white")
    table.add_column("Station", style="magenta")
    table.add_column("Pcs / Wt", justify="right")
    table.add_column("Flight / ULD", style="blue")

    if not events:
        console.print("[dim yellow]No activity logs recorded yet.[/dim yellow]")
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


def main():
    parser = argparse.ArgumentParser(
        description="Industry-level Air India Cargo Tracking Tool"
    )
    parser.add_argument(
        "awb",
        nargs="+",
        help="One or more Air India AWB numbers (e.g. '098-30244056' or '30244056')",
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
        help="Output raw JSON format instead of human tables",
    )

    args = parser.parse_args()
    client = AirIndiaCargoClient()

    results = []

    for awb in args.awb:
        try:
            with console.status(f"[bold cyan]Fetching Air India Cargo tracking for {awb}...[/bold cyan]"):
                res = client.track(awb)

            if args.json:
                results.append(res.dict())
            else:
                console.print()
                if args.view in ("all", "overview"):
                    render_overview(res.overview)
                if args.view in ("all", "tracking"):
                    render_tracking_view(res.tracking_view)
                if args.view in ("all", "activity"):
                    render_activity_view(res.activity_view)

        except AirIndiaTrackerException as e:
            if args.json:
                results.append({"awb": awb, "error": str(e)})
            else:
                console.print(f"[bold red]❌ Error tracking AWB {awb}:[/bold red] {e}")
        except Exception as e:
            if args.json:
                results.append({"awb": awb, "error": f"Unexpected error: {e}"})
            else:
                console.print(f"[bold red]❌ Unexpected error tracking AWB {awb}:[/bold red] {e}")

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))


if __name__ == "__main__":
    main()
