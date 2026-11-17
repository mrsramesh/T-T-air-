"""
Production-grade tracking client for EgyptAir Cargo (Cargo Flash Portal - IATA prefix 077).
Fetches high-speed, 100% structured data from the official WCF service with zero detection or bot issues.
"""

import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any

from cargoflash_tracker.constants import (
    AIRLINE_PREFIX,
    AIRLINE_NAME,
    CARGOFLASH_PORTAL_BASE,
    CARGOFLASH_API_URL,
    USER_AGENT,
    ACTION_DESCRIPTIONS,
    ACTION_SENTENCES,
)
from cargoflash_tracker.models import (
    CargoFlashFlightDetail,
    CargoFlashMilestonePlanItem,
    CargoFlashOverview,
    CargoFlashTrackingResult,
)

logger = logging.getLogger("cargoflash_tracker")


class CargoFlashTrackingError(Exception):
    """Base exception for Cargo Flash tracking failures."""
    pass


class CargoFlashShipmentNotFoundError(CargoFlashTrackingError):
    """Raised when shipment tracking details cannot be found."""
    pass


class CargoFlashClient:
    """
    High-speed, production client for EgyptAir Cargo on Cargo Flash.
    """

    def __init__(self, timeout_sec: int = 15):
        self.timeout_sec = timeout_sec

    @staticmethod
    def normalize_awb(awb_input: str) -> Tuple[str, str, str, str]:
        """
        Normalize AWB string into (prefix, serial, formatted, full_digits).
        e.g. '077-59060002' or '59060002' -> ('077', '59060002', '077-59060002', '07759060002')
        """
        cleaned = re.sub(r"[^\d]", "", str(awb_input or "").strip())
        if not cleaned:
            raise ValueError(f"Invalid AWB input: '{awb_input}'. Expected numeric digits.")

        if len(cleaned) == 11 and cleaned.startswith(AIRLINE_PREFIX):
            prefix = cleaned[:3]
            serial = cleaned[3:]
        elif len(cleaned) == 8:
            prefix = AIRLINE_PREFIX
            serial = cleaned
        elif len(cleaned) > 8 and cleaned.startswith(AIRLINE_PREFIX):
            prefix = AIRLINE_PREFIX
            serial = cleaned[3:11]
        else:
            prefix = cleaned[:3] if len(cleaned) >= 3 else AIRLINE_PREFIX
            serial = cleaned[3:] if len(cleaned) > 3 else cleaned

        formatted = f"{prefix}-{serial}" if len(serial) == 8 else cleaned
        full_digits = f"{prefix}{serial}"
        return prefix, serial, formatted, full_digits

    def track(
        self,
        awb_input: str,
        screenshot_path: Optional[str] = None,
    ) -> CargoFlashTrackingResult:
        """
        Tracks shipment for EgyptAir Cargo / Cargo Flash:
        1. Queries official WCF endpoint
        2. Validates records in Table0
        3. Parses Overview, Milestone Plan, and Flight Details
        4. Optionally saves rendered screenshot if screenshot_path is provided
        """
        prefix, serial, formatted_awb, _ = self.normalize_awb(awb_input)
        logger.info(f"Tracking EgyptAir Cargo AWB {formatted_awb}")

        params = {
            "AWBNo": serial,
            "BasedOn": "0",
            "AccountSNo": "0",
            "flag": "0",
            "CarrierCode": prefix,
            "AWBTrackingCaptchaCode": "",
            "SourceOrigin": "same-origin",
        }
        url = f"{CARGOFLASH_API_URL}?{urllib.parse.urlencode(params)}"
        portal_ref = f"{CARGOFLASH_PORTAL_BASE}/{formatted_awb}"

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": portal_ref,
                "Accept": "application/json, text/javascript, */*; q=0.01",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            raise CargoFlashTrackingError(f"Network error querying Cargo Flash portal: {e}") from e

        try:
            parsed = json.loads(content)
            data = json.loads(parsed) if isinstance(parsed, str) else parsed
        except Exception as e:
            raise CargoFlashTrackingError(f"Failed to parse Cargo Flash JSON response: {e}") from e

        table0 = data.get("Table0", [])
        if not table0:
            raise CargoFlashShipmentNotFoundError(
                f"Could not find shipment for AWB {formatted_awb} on EgyptAir Cargo / Cargo Flash. "
                "Please check the AWB number correctness and try again."
            )

        row0 = table0[0]
        table1 = data.get("Table1", [])
        row1 = table1[0] if table1 else {}
        table3 = data.get("Table3", [])

        # Parse Overview
        pieces = 0
        if row0.get("Pieces") or row0.get("TotalPieces"):
            try:
                pieces = int(row0.get("Pieces") or row0.get("TotalPieces"))
            except ValueError:
                pieces = 0

        gross_wt = 0.0
        if row0.get("GrossWeight") or row0.get("TotalGrossWeight"):
            try:
                gross_wt = float(str(row0.get("GrossWeight") or row0.get("TotalGrossWeight")).replace(",", ""))
            except ValueError:
                gross_wt = 0.0

        chargeable_wt = None
        if row0.get("ChargeableWeight"):
            try:
                chargeable_wt = float(str(row0.get("ChargeableWeight")).replace(",", ""))
            except ValueError:
                chargeable_wt = None

        vol = None
        if row0.get("Volume"):
            try:
                vol = float(str(row0.get("Volume")).replace(",", ""))
            except ValueError:
                vol = None

        cbm = None
        if row0.get("cbm") or row0.get("Volume1"):
            try:
                cbm = float(str(row0.get("cbm") or row0.get("Volume1")).replace(",", ""))
            except ValueError:
                cbm = None

        lat_action = row1.get("Action", row0.get("AWBStatus", "RCF"))
        lat_station = row1.get("Station", row0.get("Destination", ""))
        lat_time = row1.get("createdon")
        sentence = ACTION_SENTENCES.get(lat_action, "has been updated at")
        
        if lat_time and lat_station:
            latest_msg = f"LATEST EVENT: {lat_action} Your shipment {sentence} {lat_station} on {lat_time}"
        elif lat_station:
            latest_msg = f"LATEST EVENT: {lat_action} Your shipment {sentence} {lat_station}"
        else:
            latest_msg = f"LATEST EVENT: {lat_action}"

        overview = CargoFlashOverview(
            awb_number=serial,
            formatted_awb=formatted_awb,
            carrier=f"{AIRLINE_NAME} ({prefix})",
            origin=row0.get("Origin", ""),
            destination=row0.get("Destination", ""),
            pieces=pieces,
            gross_weight=gross_wt,
            weight_unit="KG",
            chargeable_weight=chargeable_wt,
            volume=vol,
            cbm=cbm,
            volume_unit="CBM",
            product_name=row0.get("ProductName") or "GENERAL CARGO",
            commodity=row0.get("Commodity"),
            agent_name=row0.get("AgentName"),
            booking_station=row0.get("BookingStationCode"),
            latest_event_action=lat_action,
            latest_event_station=lat_station,
            latest_event_time=lat_time,
            latest_event_message=latest_msg,
        )

        # Parse Flight Details
        flight_details: List[CargoFlashFlightDetail] = []
        for r in table3:
            ev = str(r.get("Action", "")).strip()
            desc = ACTION_DESCRIPTIONS.get(ev, ev)
            stn = str(r.get("Station", "")).strip()
            fl_no = str(r.get("FlightNo", "")).strip()
            orig = str(r.get("Origin", "")).strip()
            dest = str(r.get("Destination", "")).strip()
            fl_disp = f"{fl_no} ( {orig} -> {dest} )" if (orig and dest and fl_no) else fl_no
            fl_date = str(r.get("FlightDate", "")).strip()

            tot_pcs = None
            if r.get("Pieces"):
                try:
                    tot_pcs = int(r.get("Pieces"))
                except ValueError:
                    tot_pcs = None

            plan_pcs = None
            if r.get("ActualPieces"):
                try:
                    plan_pcs = int(r.get("ActualPieces"))
                except ValueError:
                    plan_pcs = None

            row_wt = None
            if r.get("Weight"):
                try:
                    row_wt = float(str(r.get("Weight")).replace(",", ""))
                except ValueError:
                    row_wt = None

            row_cbm = None
            if r.get("cbm"):
                try:
                    row_cbm = float(str(r.get("cbm")).replace(",", ""))
                except ValueError:
                    row_cbm = None

            flight_details.append(
                CargoFlashFlightDetail(
                    event=ev,
                    description=desc,
                    station=stn,
                    flight_no=fl_no,
                    route=f"{orig} -> {dest}" if (orig and dest) else "",
                    flight_display=fl_disp,
                    flight_date=fl_date,
                    total_pieces=tot_pcs,
                    planned_pieces=plan_pcs,
                    gross_weight=row_wt,
                    cbm=row_cbm,
                    created_on=str(r.get("createdon", "")).strip(),
                )
            )

        # Parse Milestone Plan
        milestone_plan: List[CargoFlashMilestonePlanItem] = []
        for r in table3:
            act = str(r.get("Action", "")).strip()
            stn = str(r.get("Station", "")).strip()
            dt = str(r.get("createdon", "")).strip()
            pcs = None
            if r.get("Pieces"):
                try:
                    pcs = int(r.get("Pieces"))
                except ValueError:
                    pcs = None

            milestone_plan.append(
                CargoFlashMilestonePlanItem(
                    action=act,
                    station=stn,
                    date_time=dt,
                    pieces=pcs,
                )
            )

        # Optional Screenshot Generation
        if screenshot_path:
            self._save_rendered_screenshot(overview, milestone_plan, flight_details, screenshot_path)

        return CargoFlashTrackingResult(
            awb=serial,
            formatted_awb=formatted_awb,
            carrier=f"{AIRLINE_NAME} ({prefix})",
            overview=overview,
            milestone_plan=milestone_plan,
            flight_details=flight_details,
        )

    def _save_rendered_screenshot(
        self,
        overview: CargoFlashOverview,
        milestones: List[CargoFlashMilestonePlanItem],
        flights: List[CargoFlashFlightDetail],
        screenshot_path: str,
    ):
        """Renders visual HTML and saves full-page screenshot using Playwright."""
        try:
            from playwright.sync_api import sync_playwright

            html_content = self._generate_html_report(overview, milestones, flights)
            os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page.set_content(html_content, wait_until="load")
                page.screenshot(path=screenshot_path, full_page=True)
                browser.close()
                logger.info(f"Saved visual screenshot to {screenshot_path}")
        except Exception as e:
            logger.warning(f"Could not render visual screenshot: {e}")

    def _generate_html_report(
        self,
        overview: CargoFlashOverview,
        milestones: List[CargoFlashMilestonePlanItem],
        flights: List[CargoFlashFlightDetail],
    ) -> str:
        """Generates HTML matching the exact visual layout of Cargo Flash."""
        milestone_html = ""
        for idx, m in enumerate(milestones):
            arrow = '<div style="font-size: 24px; color: #475569; align-self: center;">➔</div>' if idx > 0 else ''
            milestone_html += f"""
            {arrow}
            <div style="display: flex; flex-direction: column; align-items: center; min-width: 90px; text-align: center;">
                <div style="font-weight: 700; font-size: 13px; color: #1e293b; margin-bottom: 4px;">{m.station}</div>
                <div style="width: 44px; height: 44px; border-radius: 8px; background: #f1f5f9; border: 1.5px solid #cbd5e1; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 14px; color: #0284c7; margin-bottom: 4px;">
                    {m.action}
                </div>
                <div style="font-size: 11px; color: #64748b; font-weight: 600;">{m.date_time or 'N/A'}</div>
                <div style="font-size: 11px; color: #0f172a; font-weight: 700;">{m.pieces} pcs</div>
            </div>
            """

        flight_rows = ""
        for f in flights:
            flight_rows += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px; font-weight: 700; color: #0369a1;">{f.event}</td>
                <td style="padding: 10px;">{f.description}</td>
                <td style="padding: 10px; font-weight: 600;">{f.station}</td>
                <td style="padding: 10px; font-weight: 700; color: #dc2626;">{f.flight_display}</td>
                <td style="padding: 10px;">{f.flight_date or 'N/A'}</td>
                <td style="padding: 10px; text-align: right;">{f.total_pieces or '---'}</td>
                <td style="padding: 10px; text-align: right;">{f.planned_pieces or '---'}</td>
                <td style="padding: 10px; text-align: right; font-weight: 600;">{f.gross_weight:,.2f}</td>
            </tr>
            """

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AWBTracking: {overview.formatted_awb}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8fafc; color: #0f172a; margin: 0; padding: 24px; }}
        .card {{ background: #ffffff; border-radius: 8px; border: 1px solid #cbd5e1; box-shadow: 0 2px 4px rgba(0,0,0,0.04); margin-bottom: 20px; overflow: hidden; }}
        .header {{ background: #002d62; color: white; padding: 12px 18px; font-weight: 700; font-size: 16px; display: flex; justify-content: space-between; }}
        .banner {{ background: #eff6ff; border-left: 4px solid #0284c7; padding: 12px 18px; font-weight: 700; font-size: 14px; color: #0c4a6e; }}
        .grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; padding: 16px 18px; background: #f8fafc; border-bottom: 1px solid #e2e8f0; text-align: center; }}
        .grid-lbl {{ font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 600; margin-bottom: 4px; }}
        .grid-val {{ font-size: 15px; font-weight: 700; color: #0f172a; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #f1f5f9; padding: 10px; text-align: left; font-weight: 700; color: #475569; border-bottom: 2px solid #cbd5e1; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="header">
            <span>✈ EgyptAir Cargo (Cargo Flash) - AWB No: {overview.formatted_awb}</span>
            <span>Origin: {overview.origin} ➔ Destination: {overview.destination}</span>
        </div>
        <div class="banner">
            {overview.latest_event_message}
        </div>
        <div class="grid">
            <div><div class="grid-lbl">Origin</div><div class="grid-val">{overview.origin}</div></div>
            <div><div class="grid-lbl">Destination</div><div class="grid-val">{overview.destination}</div></div>
            <div><div class="grid-lbl">Total Pieces</div><div class="grid-val">{overview.pieces}</div></div>
            <div><div class="grid-lbl">Gross Weight</div><div class="grid-val">{overview.gross_weight:,.3f} KG</div></div>
            <div><div class="grid-lbl">Product</div><div class="grid-val">{overview.product_name}</div></div>
        </div>
        
        <div style="padding: 16px 18px; border-bottom: 1px solid #e2e8f0;">
            <div style="font-weight: 700; font-size: 13px; text-transform: uppercase; color: #475569; margin-bottom: 12px;">Milestone Plan</div>
            <div style="display: flex; gap: 10px; overflow-x: auto; padding-bottom: 8px;">
                {milestone_html}
            </div>
        </div>

        <div style="padding: 16px 18px;">
            <div style="font-weight: 700; font-size: 13px; text-transform: uppercase; color: #475569; margin-bottom: 12px;">Flight Details</div>
            <table>
                <thead>
                    <tr>
                        <th>Event</th>
                        <th>Description</th>
                        <th>Station</th>
                        <th>Flight No</th>
                        <th>Flight Date</th>
                        <th style="text-align: right;">Total Pieces</th>
                        <th style="text-align: right;">Planned Pieces</th>
                        <th style="text-align: right;">Gross Weight</th>
                    </tr>
                </thead>
                <tbody>
                    {flight_rows}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""
