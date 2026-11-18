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
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskProgressColumn, TimeElapsedColumn
from rich import box

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import AirIndiaTrackerException
from lufthansa_tracker.client import LufthansaCargoClient
from lufthansa_tracker.browser import LufthansaBrowserTracker
from emirates_tracker.client import EmiratesTrackerClient
from emirates_tracker.browser import EmiratesBrowserTracker
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError
from kuwait_tracker.browser import KuwaitBrowserTracker
from parcels_tracker.client import ParcelsTrackerClient, ParcelsShipmentNotFoundError
from virgin_tracker.client import VirginCargoClient, VirginShipmentNotFoundError
from qatar_tracker.client import QatarCargoClient, QatarShipmentNotFoundError
from cargoflash_tracker.client import CargoFlashClient, CargoFlashShipmentNotFoundError
from neos_tracker.client import NeosCargoClient, NeosShipmentNotFoundError
from indigo_tracker.client import IndigoCargoClient, IndigoShipmentNotFoundError
from bulk_tracker import (
    BulkCargoTracker,
    AWBExtractor,
    ExcelReportExporter,
    CSVReportExporter,
    BulkTrackingSummary,
    UnifiedTrackingRecord,
)

console = Console()


def detect_carrier(awb_input: str) -> str:
    """Detect carrier by AWB prefix."""
    cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
    if cleaned.startswith("312"):
        return "indigo"
    if cleaned.startswith("703"):
        return "neos"
    if cleaned.startswith("077"):
        return "cargoflash"
    if cleaned.startswith("157"):
        return "qatar"
    if cleaned.startswith("932"):
        return "virgin"
    if cleaned.startswith("125"):
        return "britishairways"
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


# ==================== BRITISH AIRWAYS & PARCELS RENDERING ====================

def render_parcels_overview(overview, couriers=None):
    """Render ParcelsApp & British Airways summary overview card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()

    grid.add_row(
        "AWB / Tracking:", f"[bold white]{overview.formatted_tracking_number}[/bold white]",
        "Route:", f"[bold magenta]{overview.origin_location or overview.origin_country or 'DEL'} ➔ {overview.destination_location or overview.destination_country or 'ATL'}[/bold magenta]"
    )
    grid.add_row(
        "Pieces / Packages:", f"{overview.pieces or overview.number_of_packages or 'N/A'} pcs",
        "Weight:", f"[bold white]{overview.weight or 'N/A'}[/bold white]"
    )
    grid.add_row(
        "Days in Transit:", f"{overview.days_in_transit or 'N/A'} days",
        "Carriers:", f"{', '.join(overview.couriers) if overview.couriers else overview.primary_carrier}"
    )
    grid.add_row(
        "Latest Date:", f"{overview.latest_date or 'N/A'}",
        "Latest Status:", f"[bold green on default] {overview.latest_status} [/bold green on default]"
    )

    console.print(Panel(grid, title=f"[bold blue]✈ {overview.primary_carrier}[/bold blue] - [bold white]{overview.formatted_tracking_number}[/bold white]", border_style="blue", box=box.ROUNDED))


def render_parcels_timeline(states):
    """Render ParcelsApp chronological event milestone timeline."""
    table = Table(title="[bold yellow]📅 Event & Flight Timeline (British Airways Cargo / ParcelsApp)[/bold yellow]", box=box.ROUNDED)
    table.add_column("Date & Time", style="white", min_width=18)
    table.add_column("Carrier", style="bold cyan")
    table.add_column("Status & Flight Event", style="white")
    table.add_column("Location / Airport", style="bold magenta")
    table.add_column("State", justify="center")

    if not states:
        console.print("[dim yellow]No timeline events recorded.[/dim yellow]")
        return

    for st in states:
        badge = "[bold green]LATEST[/bold green]" if st.is_latest else "[dim]Completed[/dim]"
        carrier_badge = f"[cyan]{st.carrier_name or 'BA Cargo'}[/cyan]"
        table.add_row(
            st.date or "N/A",
            carrier_badge,
            st.status,
            st.location or "N/A",
            badge,
        )

    console.print(table)


def render_parcels_attributes(attributes):
    """Render parsed attributes."""
    if not attributes:
        return
    table = Table(title="[bold cyan]📋 Shipment Attributes[/bold cyan]", box=box.SIMPLE_HEAVY)
    table.add_column("Attribute", style="bold white")
    table.add_column("Value", style="yellow")

    for attr in attributes:
        table.add_row(attr.name or attr.key, attr.value)

    console.print(table)


# ==================== VIRGIN ATLANTIC RENDERING ====================

def render_virgin_overview(overview):
    """Render Virgin Atlantic summary overview card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()

    grid.add_row(
        "AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
        "Route:", f"[bold red]{overview.origin.code} ({overview.origin.name or ''}) ➔ {overview.destination.code} ({overview.destination.name or ''})[/bold red]"
    )
    grid.add_row(
        "Job Ref (JRN):", f"[bold cyan]{overview.job_reference_number or 'N/A'}[/bold cyan]",
        "Booking Ref:", f"[bold cyan]{overview.booking_reference_number or 'N/A'}[/bold cyan]"
    )
    grid.add_row(
        "Pieces / Weight:", f"{overview.pieces or 'N/A'} pcs / {overview.weight or 'N/A'} {overview.weight_unit}",
        "Volume:", f"{overview.volume or 'N/A'} {overview.volume_unit}"
    )
    grid.add_row(
        "Product / Commodity:", f"{overview.product_name or overview.commodity or 'General - Classic'}",
        "Transit Time:", f"{overview.transit_duration or 'N/A'}"
    )
    grid.add_row(
        "Agent / Shipper:", f"{overview.agent_name or 'N/A'}",
        "Shipment Status:", f"[bold yellow]{overview.shipment_status or 'N/A'}[/bold yellow]"
    )
    grid.add_row(
        "Order Status:", f"[bold green on default] {overview.order_status} [/bold green on default]",
        "Latest Event:", f"[bold cyan]{overview.latest_milestone_code or 'BKD'}[/bold cyan] ({overview.latest_milestone_description or 'N/A'})"
    )

    console.print(Panel(grid, title=f"[bold red]✈ Virgin Atlantic Cargo[/bold red] - [bold white]{overview.formatted_awb}[/bold white]", border_style="red", box=box.ROUNDED))


def render_virgin_flights(flights):
    """Render Virgin Atlantic flight routing schedule."""
    table = Table(title="[bold yellow]🛫 Virgin Atlantic - Flight Routing & Connections[/bold yellow]", box=box.ROUNDED)
    table.add_column("Flight", style="bold red")
    table.add_column("Route", style="magenta")
    table.add_column("Scheduled Departure", style="white")
    table.add_column("Scheduled Arrival", style="white")
    table.add_column("Pieces / Weight", justify="right")
    table.add_column("Status", justify="center")

    if not flights:
        console.print("[dim yellow]No specific flight segment details available.[/dim yellow]")
        return

    for f in flights:
        pcs_wt = f"{f.pieces or '---'} pcs / {f.weight or '---'} {f.weight_unit or 'K'}"
        table.add_row(
            f.flight_number,
            f"{f.origin.code} ➔ {f.destination.code}",
            f.departure_time or "N/A",
            f.arrival_time or "N/A",
            pcs_wt,
            f"[bold green]{f.status}[/bold green]"
        )

    console.print(table)


def render_virgin_milestones(milestones):
    """Render Virgin Atlantic operational milestone events."""
    table = Table(title="[bold cyan]📅 Virgin Atlantic - Operational Milestones & Tracking Details[/bold cyan]", box=box.ROUNDED)
    table.add_column("Date & Time", style="white", min_width=18)
    table.add_column("Code", style="bold magenta", justify="center")
    table.add_column("Station", style="bold cyan", justify="center")
    table.add_column("Milestone Description", style="white")
    table.add_column("Flight / Sector", style="yellow")
    table.add_column("Pieces / Wt", style="dim white")
    table.add_column("State", justify="center")

    if not milestones:
        console.print("[dim yellow]No milestone events recorded.[/dim yellow]")
        return

    for m in milestones:
        sector = f"{m.board_point} ➔ {m.off_point}" if m.board_point and m.off_point else "---"
        fl_sector = f"{m.flight_number} ({sector})" if m.flight_number else sector
        pcs_wt = f"{m.pieces} pcs / {m.weight} {m.weight_unit}" if m.pieces else "---"
        state = "[bold green]LATEST[/bold green]" if m.is_latest else "[dim]Planned[/dim]"
        table.add_row(
            m.timestamp or "N/A",
            m.code,
            m.station or "---",
            m.description,
            fl_sector,
            pcs_wt,
            state
        )

    console.print(table)


# ==================== QATAR AIRWAYS RENDERING ====================

def render_qatar_overview(overview):
    """Render Qatar Airways summary overview card."""
    status_color = "green" if "deliver" in overview.overall_status.lower() else ("yellow" if "arriv" in overview.overall_status.lower() else "cyan")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()
    grid.add_column(style="bold magenta", justify="right")
    grid.add_column()

    grid.add_row("AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
                 "Route:", f"[bold cyan]{overview.origin or 'N/A'} ➔ {overview.destination or 'N/A'}[/bold cyan]")
    pcs_str = f"{overview.pieces} pcs" if overview.pieces else "N/A"
    wt_str = f"{overview.weight:,.1f} {overview.weight_unit}" if overview.weight else "N/A"
    vol_str = f"{overview.volume:.3f} {overview.volume_unit}" if overview.volume else "N/A"

    grid.add_row("Pieces:", pcs_str,
                 "Weight:", wt_str)
    grid.add_row("Volume:", vol_str,
                 "Latest Update:", f"[bold {status_color}]{overview.latest_status_message or overview.overall_status}[/bold {status_color}]")

    if overview.latest_arrival_message:
        grid.add_row("Arrival Info:", f"[dim white]{overview.latest_arrival_message}[/dim white]",
                     "Overall Status:", f"[bold {status_color} on default] {overview.overall_status} [/bold {status_color} on default]")
    else:
        grid.add_row("Overall Status:", f"[bold {status_color} on default] {overview.overall_status} [/bold {status_color} on default]",
                     "", "")

    console.print(Panel(grid, title=f"[bold #5c0632]🇶🇦 {overview.airline}[/bold #5c0632] - [bold white]{overview.formatted_awb}[/bold white]", border_style="magenta", box=box.ROUNDED))


def render_qatar_flights(flights):
    """Render Qatar Airways flight segments."""
    table = Table(title="[bold magenta]🛫 Qatar Airways Cargo - Flight Itinerary & Schedule (3 Legs)[/bold magenta]", box=box.ROUNDED)
    table.add_column("Flight", style="bold #5c0632")
    table.add_column("Route", style="cyan")
    table.add_column("Departure Date/Time", style="white")
    table.add_column("Arrival Date/Time", style="white")
    table.add_column("Pieces / Weight", justify="right")
    table.add_column("Volume", justify="right", style="dim white")
    table.add_column("Flight Status", justify="center")

    if not flights:
        console.print("[dim yellow]No specific flight segment details available.[/dim yellow]")
        return

    for f in flights:
        pcs_wt = f"{f.pieces or '---'} pcs / {f.weight or '---'} {f.weight_unit}"
        vol = f"{f.volume:.3f} {f.volume_unit}" if f.volume else "---"
        st_color = "green" if f.flight_status == "Departed" else ("yellow" if f.flight_status == "Scheduled" else "cyan")
        table.add_row(
            f.flight_number,
            f"{f.origin} ➔ {f.destination}",
            f.departure_date_time or "N/A",
            f.arrival_date_time or "N/A",
            pcs_wt,
            vol,
            f"[bold {st_color}]{f.flight_status}[/bold {st_color}]"
        )

    console.print(table)


def render_qatar_milestones(milestones):
    """Render Qatar Airways operational movement status milestones."""
    table = Table(title="[bold cyan]📅 Qatar Airways Cargo - Tracking Details & Movement Milestones[/bold cyan]", box=box.ROUNDED)
    table.add_column("Date", style="white", min_width=15)
    table.add_column("Time", style="yellow", justify="center")
    table.add_column("Code", style="bold magenta", justify="center")
    table.add_column("Airport", style="bold cyan", justify="center")
    table.add_column("Movement Details", style="white")
    table.add_column("Pieces / Weight", style="dim white", justify="right")
    table.add_column("State", justify="center")

    if not milestones:
        console.print("[dim yellow]No milestone events recorded.[/dim yellow]")
        return

    for m in milestones:
        pcs_wt = f"{m.pieces} pcs / {m.weight} {m.weight_unit}" if m.pieces else "---"
        state = "[bold green]LATEST[/bold green]" if m.is_latest else "[dim]Historical[/dim]"
        table.add_row(
            m.event_date or "N/A",
            m.event_time or "N/A",
            m.status_code,
            m.airport or "---",
            m.details,
            pcs_wt,
            state
        )

    console.print(table)


# ==================== CARGO FLASH / EGYPTAIR RENDERING ====================

def render_cargoflash_overview(overview):
    """Render EgyptAir / Cargo Flash summary overview card."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()

    grid.add_row("AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
                 "Route:", f"[bold magenta]{overview.origin} ➔ {overview.destination}[/bold magenta]")
    vol_str = f"{overview.cbm or overview.volume:.3f} {overview.volume_unit}" if (overview.cbm or overview.volume) else "N/A"
    chg_wt = f" (Chargeable: {overview.chargeable_weight:,.2f} KG)" if overview.chargeable_weight else ""
    grid.add_row("Pieces:", f"{overview.pieces} pcs",
                 "Gross Weight:", f"{overview.gross_weight:,.3f} {overview.weight_unit}{chg_wt}")
    grid.add_row("Volume / CBM:", vol_str,
                 "Product / Cargo:", f"[bold white]{overview.product_name}[/bold white]")
    if overview.commodity:
        grid.add_row("Commodity:", f"[yellow]{overview.commodity}[/yellow]", "", "")
    if overview.agent_name:
        grid.add_row("Agent Name:", f"[dim]{overview.agent_name}[/dim]", "", "")

    grid.add_row("Latest Event:", f"[bold green]{overview.latest_event_message}[/bold green]", "", "")

    console.print(Panel(grid, title=f"[bold #002d62]🇪🇬 {overview.carrier}[/bold #002d62] - [bold white]{overview.formatted_awb}[/bold white]", border_style="blue", box=box.ROUNDED))


def render_cargoflash_milestone_plan(milestones):
    """Render Cargo Flash Milestone Plan sequence."""
    table = Table(title="[bold cyan]📌 EgyptAir Cargo - Milestone Plan (Sequential Execution)[/bold cyan]", box=box.ROUNDED)
    table.add_column("Step", style="dim", justify="center")
    table.add_column("Action", style="bold yellow", justify="center")
    table.add_column("Station", style="bold cyan", justify="center")
    table.add_column("Event Date & Time", style="white")
    table.add_column("Pieces", justify="right", style="green")

    if not milestones:
        console.print("[dim yellow]No milestone plan available.[/dim yellow]")
        return

    for idx, m in enumerate(milestones, start=1):
        table.add_row(
            str(idx),
            m.action,
            m.station,
            m.date_time or "N/A",
            f"{m.pieces} pcs" if m.pieces is not None else "---"
        )

    console.print(table)


def render_cargoflash_flights(flights):
    """Render Cargo Flash Flight Details table."""
    table = Table(title="[bold magenta]🛫 EgyptAir Cargo - Flight Details & Manifested Schedule[/bold magenta]", box=box.ROUNDED)
    table.add_column("Event", style="bold cyan", justify="center")
    table.add_column("Description", style="white")
    table.add_column("Station", style="bold yellow", justify="center")
    table.add_column("Flight No / Route", style="bold red")
    table.add_column("Flight Date", style="white")
    table.add_column("Total Pcs", justify="right")
    table.add_column("Planned Pcs", justify="right")
    table.add_column("Gross Weight", justify="right", style="bold green")

    if not flights:
        console.print("[dim yellow]No flight details recorded.[/dim yellow]")
        return

    for f in flights:
        pcs_total = str(f.total_pieces) if f.total_pieces is not None else "---"
        pcs_plan = str(f.planned_pieces) if f.planned_pieces is not None else "---"
        wt = f"{f.gross_weight:,.2f} KG" if f.gross_weight is not None else "---"
        table.add_row(
            f.event,
            f.description,
            f.station,
            f.flight_display,
            f.flight_date or "N/A",
            pcs_total,
            pcs_plan,
            wt
        )

    console.print(table)


# ==================== NEOS AIR CARGO / WCS RENDERING ====================

def render_neos_overview(overview):
    """Render Neos Air Cargo / WCS summary card."""
    status_color = "green" if "DLV" in overview.current_status else "yellow"

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()
    grid.add_column(style="bold cyan", justify="right")
    grid.add_column()

    pcs_str = f"{overview.pieces} pcs" if overview.pieces else "---"
    grid.add_row("AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
                 "Route:", f"[bold magenta]{overview.origin} ➔ {overview.destination}[/bold magenta]")
    grid.add_row("Pieces:", pcs_str,
                 "Gross Weight:", f"[bold green]{overview.gross_weight or '---'}[/bold green]")
    grid.add_row("Commodity:", f"[bold yellow]{overview.commodity or 'GENERAL CARGO'}[/bold yellow]",
                 "Progress Step:", f"[bold cyan]{overview.progress_step or 'In Transit'}[/bold cyan]")
    grid.add_row("Current Status:", f"[bold {status_color}]{overview.current_status}[/bold {status_color}]",
                 "Latest Time:", f"{overview.latest_event_time or 'N/A'}")
    grid.add_row("Carrier / Portal:", f"[dim]{overview.airline}[/dim]",
                 "Data Source:", f"[dim]{overview.source}[/dim]")

    console.print(Panel(grid, title=f"[bold red]✈ Neos Air Cargo (NO) / WCS (703)[/bold red] - [bold white]{overview.formatted_awb}[/bold white]", border_style="red", box=box.ROUNDED))


def render_neos_flights(flights):
    """Render Neos Air Cargo / WCS Flight Schedule table."""
    table = Table(title="[bold magenta]🛫 Neos Air Cargo - Flight Routing & Itinerary[/bold magenta]", box=box.ROUNDED)
    table.add_column("Flight No / Route", style="bold red")
    table.add_column("Origin ➔ Destination", style="bold cyan", justify="center")
    table.add_column("Status / Movement", style="bold yellow")
    table.add_column("Gross Weight", justify="right", style="bold green")
    table.add_column("Departure Time", style="white")
    table.add_column("Arrival Time", style="white")

    if not flights:
        console.print("[dim yellow]No flight segment details recorded.[/dim yellow]")
        return

    for f in flights:
        table.add_row(
            f.flight_no,
            f"{f.origin} ➔ {f.destination}",
            f.status,
            f.weight or "---",
            f.departure_time or "N/A",
            f.arrival_time or "N/A"
        )

    console.print(table)


def render_neos_milestones(milestones):
    """Render Neos Air Cargo / WCS chronological milestone events table."""
    table = Table(title="[bold cyan]📌 Neos Air Cargo - Shipment Milestones & Audit Trail[/bold cyan]", box=box.ROUNDED)
    table.add_column("#", style="dim", justify="center")
    table.add_column("Event Date & Time", style="white")
    table.add_column("Code", style="bold yellow", justify="center")
    table.add_column("Description", style="white")
    table.add_column("Sector", style="bold cyan", justify="center")
    table.add_column("Flight No", style="bold red", justify="center")
    table.add_column("Pieces", justify="right", style="green")
    table.add_column("Weight", justify="right", style="bold green")
    table.add_column("State", justify="center")

    if not milestones:
        console.print("[dim yellow]No milestone records available.[/dim yellow]")
        return

    for m in milestones:
        badge = "[bold green]LATEST[/bold green]" if m.is_latest else "[dim]Historical[/dim]"
        sector = f"{m.origin} ➔ {m.destination}" if (m.origin and m.destination) else (m.destination or "---")
        pcs_txt = f"{m.pieces} pcs" if m.pieces is not None else "---"
        table.add_row(
            str(m.step),
            m.timestamp or "N/A",
            m.status_code,
            m.description,
            sector,
            m.flight_no or "---",
            pcs_txt,
            m.weight or "---",
            badge
        )

    console.print(table)


# ==================== INDIGO CARGO (6E - 312) RENDERING ====================

def render_indigo_overview(overview):
    """Render IndiGo CarGo summary overview card."""
    status_lower = overview.current_status.lower()
    status_color = "green" if "delivered" in status_lower else ("yellow" if "departed" in status_lower or "arrived" in status_lower else "cyan")

    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold blue", justify="right")
    grid.add_column()
    grid.add_column(style="bold blue", justify="right")
    grid.add_column()

    grid.add_row(
        "AWB Number:", f"[bold white]{overview.formatted_awb}[/bold white]",
        "Route:", f"[bold magenta]{overview.origin} ➔ {overview.destination}[/bold magenta]"
    )
    pcs_txt = f"{overview.pieces} pcs" if overview.pieces is not None else "---"
    grid.add_row(
        "Pieces:", pcs_txt,
        "Gross Weight:", f"{overview.gross_weight or '---'}"
    )
    grid.add_row(
        "Flight Details:", f"[bold cyan]{overview.flight_no or 'N/A'}[/bold cyan]",
        "Issued To:", f"[bold yellow]{overview.issued_to or 'N/A'}[/bold yellow]"
    )
    grid.add_row(
        "Latest Activity:", f"[bold white]{overview.latest_activity}[/bold white]",
        "Overall Status:", f"[bold {status_color} on default] {overview.current_status} [/bold {status_color} on default]"
    )

    console.print(Panel(
        grid,
        title=f"[bold blue]✈ IndiGo CarGo (6E) - SmartKargo[/bold blue] - [bold white]{overview.formatted_awb}[/bold white]",
        border_style="blue",
        box=box.ROUNDED
    ))


def render_indigo_booking_info(booking_items):
    """Render IndiGo CarGo Booking & Acceptance Information table."""
    table = Table(title="[bold blue]📋 IndiGo CarGo - Booking & Acceptance Information[/bold blue]", box=box.ROUNDED)
    table.add_column("Status", style="bold cyan", justify="center")
    table.add_column("Station", style="bold white", justify="center")
    table.add_column("Destination", style="bold magenta", justify="center")
    table.add_column("Pieces", justify="right", style="green")
    table.add_column("Weight (Kgs)", justify="right", style="bold green")
    table.add_column("Flight No / Details", style="bold yellow")

    if not booking_items:
        console.print("[dim yellow]No booking info records available.[/dim yellow]")
        return

    for item in booking_items:
        pcs_txt = str(item.pieces) if item.pieces is not None else "---"
        table.add_row(
            item.status,
            item.station,
            item.destination,
            pcs_txt,
            item.weight or "---",
            item.flight_no or "---"
        )

    console.print(table)


def render_indigo_status_history(status_history):
    """Render IndiGo CarGo Status History & Shipment Milestones table."""
    table = Table(title="[bold blue]📌 IndiGo CarGo - Status History & Shipment Milestones[/bold blue]", box=box.ROUNDED)
    table.add_column("Station", style="bold white", justify="center")
    table.add_column("Milestone / Status", style="bold yellow")
    table.add_column("Pieces", justify="right", style="green")
    table.add_column("Weight (Kgs)", justify="right", style="bold green")
    table.add_column("Flight No", style="bold cyan", justify="center")
    table.add_column("Flight Date", style="white", justify="center")
    table.add_column("Route", style="bold magenta", justify="center")
    table.add_column("ULD / Remarks", style="white")
    table.add_column("State", justify="center")

    if not status_history:
        console.print("[dim yellow]No status history records available.[/dim yellow]")
        return

    for item in status_history:
        badge = "[bold green]LATEST[/bold green]" if item.is_latest else "[dim]Historical[/dim]"
        pcs_txt = str(item.pieces) if item.pieces is not None else "---"
        sector = f"{item.origin} ➔ {item.destination}" if (item.origin and item.destination) else "---"
        table.add_row(
            item.station,
            item.milestone,
            pcs_txt,
            item.weight or "---",
            item.flight_no or "---",
            item.flight_date or "---",
            sector,
            item.uld_or_remarks or "---",
            badge
        )

    console.print(table)


def render_indigo_delivery_orders(delivery_orders):
    """Render IndiGo CarGo Delivery Orders & Consignee details table."""
    table = Table(title="[bold blue]📦 IndiGo CarGo - Delivery Orders & Release Details[/bold blue]", box=box.ROUNDED)
    table.add_column("DO Number", style="bold white")
    table.add_column("AWB Number", style="dim", justify="center")
    table.add_column("Pieces", justify="right", style="green")
    table.add_column("Weight (Kgs)", justify="right", style="bold green")
    table.add_column("Flight Details", style="cyan")
    table.add_column("Issued To (Consignee)", style="bold yellow")

    if not delivery_orders:
        return

    for do in delivery_orders:
        pcs_txt = str(do.pieces) if do.pieces is not None else "---"
        table.add_row(
            do.do_number,
            do.awb_number,
            pcs_txt,
            do.weight or "---",
            do.flight_details or "---",
            do.issued_to or "---"
        )

    console.print(table)


# ==================== BULK SUMMARY TABLE RENDERING ====================

def render_bulk_summary_table(summary: BulkTrackingSummary):
    """Render executive multi-carrier summary table and KPIs."""
    table = Table(
        title="[bold blue]✈ Global Multi-Carrier Air Cargo Batch Tracking Results[/bold blue]",
        box=box.ROUNDED,
        header_style="bold white",
    )
    table.add_column("#", justify="center", style="dim", width=4)
    table.add_column("AWB Number", style="bold white", justify="center")
    table.add_column("Carrier", style="bold cyan")
    table.add_column("Status", justify="center")
    table.add_column("Route", justify="center", style="bold magenta")
    table.add_column("Pieces", justify="right", style="green")
    table.add_column("Weight", justify="right", style="bold green")
    table.add_column("Flight Details", style="bold yellow")
    table.add_column("Latest Activity", style="white")
    table.add_column("Time", justify="right", style="dim")

    STATUS_STYLES = {
        "DELIVERED": "[bold green]✔ DELIVERED[/bold green]",
        "ARRIVED": "[bold blue]✈ ARRIVED[/bold blue]",
        "DEPARTED": "[bold yellow]🛫 DEPARTED[/bold yellow]",
        "IN_TRANSIT": "[bold yellow]⏳ IN TRANSIT[/bold yellow]",
        "BOOKED": "[cyan]📋 BOOKED[/cyan]",
        "ACCEPTED": "[cyan]📦 ACCEPTED[/cyan]",
        "NOT_FOUND": "[bold red]✖ NOT FOUND[/bold red]",
        "UNREACHABLE": "[bold red]🔌 UNREACHABLE[/bold red]",
        "SKIPPED": "[dim white]⏭ SKIPPED[/dim white]",
        "ERROR": "[bold red]⚠ ERROR[/bold red]",
    }

    for idx, r in enumerate(summary.records, start=1):
        status_disp = STATUS_STYLES.get(r.status, f"[dim]{r.status}[/dim]")
        pcs_txt = f"{r.pieces} pcs" if r.pieces is not None else "---"
        lat_act = r.latest_activity or (r.error_message or "---")
        if len(lat_act) > 42:
            lat_act = lat_act[:39] + "..."

        table.add_row(
            str(idx),
            r.awb,
            r.carrier_name,
            status_disp,
            r.route,
            pcs_txt,
            r.weight or "---",
            r.flight_details or "---",
            lat_act,
            f"{r.execution_time_sec}s",
        )

    console.print(table)

    # KPI summary metrics panel
    kpi_grid = Table.grid(padding=(0, 3))
    kpi_grid.add_column(style="bold white")
    kpi_grid.add_column(style="bold green")
    kpi_grid.add_column(style="bold yellow")
    kpi_grid.add_column(style="bold red")
    kpi_grid.add_column(style="bold cyan")

    kpi_grid.add_row(
        f"Total: [bold white]{summary.total_requested}[/]",
        f"Delivered: [bold green]{summary.total_delivered}[/]",
        f"In Transit: [bold yellow]{summary.total_in_transit}[/]",
        f"Not Found: [bold red]{summary.total_not_found}[/]",
        f"Unreachable: [bold magenta]{getattr(summary, 'total_unreachable', 0)}[/]",
        f"Skipped: [bold dim]{getattr(summary, 'total_skipped', 0)}[/]",
        f"Elapsed: [bold cyan]{summary.total_time_sec}s[/]",
    )

    console.print(Panel(kpi_grid, title="[bold blue]📊 Batch Performance KPIs[/bold blue]", border_style="blue", box=box.ROUNDED))


def main():
    parser = argparse.ArgumentParser(
        description="Production Multi-Carrier Air Cargo Tracker (Air India, Lufthansa Cargo, Emirates SkyCargo, Kuwait Airways, British Airways, Virgin Atlantic, Qatar Airways Cargo, EgyptAir Cargo, Neos Air Cargo, IndiGo CarGo)"
    )
    parser.add_argument(
        "awb",
        nargs="*",
        default=[],
        help="One or more AWB numbers (e.g. '312-9298-9396' IndiGo, '703-13715800' Neos, '077-59060002' EgyptAir, '157-5366-1580' Qatar, etc.)",
    )
    parser.add_argument(
        "--file", "-f",
        help="Path to an Excel (.xlsx), CSV (.csv), or Text (.txt) file containing multiple AWBs",
    )
    parser.add_argument(
        "--bulk", "-b",
        help="Paste a raw text block of multiple AWBs separated by commas, spaces, or newlines",
    )
    parser.add_argument(
        "--export-excel",
        help="File path to save tracking results as an executive Excel spreadsheet (.xlsx)",
    )
    parser.add_argument(
        "--export-csv",
        help="File path to save tracking results as a CSV file (.csv)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Number of concurrent workers for batch tracking (default: 5)",
    )
    parser.add_argument(
        "--carrier",
        choices=["auto", "airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "qatar", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels"],
        default="auto",
        help="Target carrier (default: auto-detected by AWB prefix 098, 020, 176, 229, 125, 932, 157, 077, 703, 312)",
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

    # Collect and extract all target AWBs from arguments, file, or bulk text
    target_awbs = []
    if args.awb:
        for a in args.awb:
            target_awbs.extend(AWBExtractor.extract_from_text(a))
    if args.file:
        file_extracted = AWBExtractor.extract_from_any(args.file)
        console.print(f"[bold cyan]📁 Extracted {len(file_extracted)} AWBs from file:[/bold cyan] {args.file}")
        target_awbs.extend(file_extracted)
    if args.bulk:
        bulk_extracted = AWBExtractor.extract_from_text(args.bulk)
        console.print(f"[bold cyan]📋 Extracted {len(bulk_extracted)} AWBs from bulk input text[/bold cyan]")
        target_awbs.extend(bulk_extracted)

    # Deduplicate while preserving order
    seen_awbs = set()
    unique_awbs = []
    for a in target_awbs:
        if a not in seen_awbs:
            seen_awbs.add(a)
            unique_awbs.append(a)

    if not unique_awbs:
        parser.print_help()
        console.print("\n[bold red]❌ Error:[/bold red] No valid AWB numbers provided. Supply AWB arguments, --file, or --bulk.")
        sys.exit(1)

    # If multiple AWBs or explicit export flags requested, run Bulk Engine
    is_bulk = len(unique_awbs) > 1 or bool(args.export_excel or args.export_csv or args.file or args.bulk)

    if is_bulk and not args.browser:
        console.print(f"[bold blue]⚡ Initiating concurrent tracking for {len(unique_awbs)} shipments...[/bold blue]\n")
        tracker = BulkCargoTracker(max_global_workers=args.workers)

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}[/bold cyan]"),
            BarColumn(complete_style="green", finished_style="bold green"),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(f"Tracking {len(unique_awbs)} shipments across 10 airlines...", total=len(unique_awbs))

            def on_progress(done, total, rec):
                color = "green" if rec.status == "DELIVERED" else ("yellow" if rec.status in ("IN_TRANSIT", "DEPARTED", "ARRIVED") else "red")
                progress.update(task, completed=done, description=f"Tracked [bold white]{rec.awb}[/] ({rec.carrier_name}) ➔ [bold {color}]{rec.status}[/]")

            summary = tracker.track_batch(unique_awbs, progress_callback=on_progress)

        console.print()
        if args.json:
            print(json.dumps([r.model_dump() for r in summary.records], indent=2))
        else:
            render_bulk_summary_table(summary)

        if args.export_excel:
            ExcelReportExporter.save_to_file(summary.records, args.export_excel, summary)
            console.print(f"[bold green]✔ Excel report exported successfully to:[/bold green] {args.export_excel}")

        if args.export_csv:
            CSVReportExporter.save_to_file(summary.records, args.export_csv)
            console.print(f"[bold green]✔ CSV report exported successfully to:[/bold green] {args.export_csv}")

        return

    # Single AWB detailed inspection mode
    lh_client = LufthansaCargoClient()
    ai_client = AirIndiaCargoClient()
    ek_client = EmiratesTrackerClient()
    kw_client = KuwaitCargoClient()
    parcels_client = ParcelsTrackerClient()
    virgin_client = VirginCargoClient()
    qatar_client = QatarCargoClient()
    cargoflash_client = CargoFlashClient()
    neos_client = NeosCargoClient()
    indigo_client = IndigoCargoClient()

    lh_browser = LufthansaBrowserTracker()
    ek_browser = EmiratesBrowserTracker()
    kw_browser = KuwaitBrowserTracker()

    results = []

    for raw_awb in unique_awbs:
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
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
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
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
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
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_lufthansa_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_lufthansa_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_lufthansa_history(res.status_history)

            elif carrier in ("britishairways", "parcels"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)
                screenshot = f"parcels_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold cyan]Tracking British Airways Cargo / ParcelsApp {raw_awb}...[/bold cyan]"):
                    res = parcels_client.track(raw_awb, headless=True, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_parcels_overview(res.overview, res.couriers)
                    if args.view in ("all", "tracking", "activity"):
                        render_parcels_timeline(res.states)
                        render_parcels_attributes(res.attributes)

            elif carrier in ("virgin", "virginatlantic"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)
                screenshot = f"virgin_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold red]Tracking Virgin Atlantic Cargo {raw_awb} via Accelya Portal...[/bold red]"):
                    res = virgin_client.track(raw_awb, headless=True, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_virgin_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_virgin_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_virgin_milestones(res.milestones)

            elif carrier in ("qatar", "qrcargo"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                screenshot = f"qatar_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold magenta]Tracking Qatar Airways Cargo {raw_awb} via Experience Cloud Portal...[/bold magenta]"):
                    res = qatar_client.track(raw_awb, headless=True, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_qatar_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_qatar_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_qatar_milestones(res.milestones)

            elif carrier in ("cargoflash", "egyptair"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                screenshot = f"cargoflash_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold blue]Tracking EgyptAir Cargo / Cargo Flash {raw_awb}...[/bold blue]"):
                    res = cargoflash_client.track(raw_awb, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_cargoflash_overview(res.overview)
                    if args.view in ("all", "activity", "tracking"):
                        render_cargoflash_milestone_plan(res.milestone_plan)
                        render_cargoflash_flights(res.flight_details)

            elif carrier in ("neos", "neosair", "wcs"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                screenshot = f"neos_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold red]Tracking Neos Air Cargo / World Cargo Solutions {raw_awb}...[/bold red]"):
                    res = neos_client.track(raw_awb, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_neos_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_neos_flights(res.flights)
                    if args.view in ("all", "activity"):
                        render_neos_milestones(res.milestones)

            elif carrier in ("indigo", "6e", "indigocargo"):
                clean_serial = re.sub(r'[^\d]', '', raw_awb)[-8:]
                screenshot = f"indigo_{clean_serial}.png" if args.browser else None
                with console.status(f"[bold blue]Tracking IndiGo CarGo (6E) {raw_awb} via SmartKargo Portal...[/bold blue]"):
                    res = indigo_client.track(raw_awb, screenshot_path=screenshot)

                if args.browser and screenshot:
                    console.print(f"[bold green]✔ Screenshot saved:[/bold green] {screenshot}")

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
                else:
                    console.print()
                    if args.view in ("all", "overview"):
                        render_indigo_overview(res.overview)
                    if args.view in ("all", "tracking"):
                        render_indigo_booking_info(res.booking_info)
                    if args.view in ("all", "activity"):
                        render_indigo_status_history(res.status_history)
                    if args.view in ("all", "tracking", "activity"):
                        render_indigo_delivery_orders(res.delivery_orders)

            else:
                # Default to Air India
                with console.status(f"[bold red]Fetching Air India Cargo tracking for {raw_awb}...[/bold red]"):
                    res = ai_client.track(raw_awb)

                if args.json:
                    results.append(res.model_dump() if hasattr(res, "model_dump") else res.dict())
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
