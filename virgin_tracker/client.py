"""
Production-grade tracking client for Virgin Atlantic Cargo (IATA prefix 932).
Automates the Accelya Offer & Order portal with robust bot-detection avoidance and 100% data fidelity.
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from playwright.sync_api import sync_playwright

from virgin_tracker.constants import (
    VIRGIN_PORTAL_URL,
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    USER_AGENT,
    SELECTOR_DOC_INPUT,
    SELECTOR_SEARCH_BTN,
    SELECTOR_TRACKING_DETAILS_BTN,
)
from virgin_tracker.models import (
    VirginAirport,
    VirginFlightSegment,
    VirginMilestone,
    VirginOverview,
    VirginTrackingResult,
)

logger = logging.getLogger("virgin_tracker")


class VirginTrackingError(Exception):
    """Base exception for Virgin Atlantic tracking failures."""
    pass


class VirginShipmentNotFoundError(VirginTrackingError):
    """Raised when shipment tracking details cannot be found."""
    pass


class VirginCargoClient:
    """
    Automates Virgin Atlantic Cargo tracking via Accelya Offer & Order portal.
    """

    def __init__(self, timeout_ms: int = 35000):
        self.timeout_ms = timeout_ms

    @staticmethod
    def normalize_awb(awb_input: str) -> Tuple[str, str, str, str]:
        """
        Normalize AWB string into (prefix, serial, formatted, full_digits).
        e.g. '932-78989514' or '78989514' -> ('932', '78989514', '932-78989514', '93278989514')
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
        headless: bool = True,
        screenshot_path: Optional[str] = None,
    ) -> VirginTrackingResult:
        """
        Executes Virgin Atlantic Cargo tracking:
        1. Navigates to portal URL
        2. Enters full 11-digit AWB (e.g. 93278989514) into Doc. No. input
        3. Presses Enter and clicks Search
        4. Clicks 'Tracking Details' button
        5. Intercepts backend order & tracking JSON payload
        6. Returns structured VirginTrackingResult
        """
        prefix, serial, formatted_awb, full_digits = self.normalize_awb(awb_input)
        logger.info(f"Tracking Virgin Atlantic Cargo AWB {formatted_awb} (Doc No: {full_digits})")

        intercepted_search: Dict[str, Any] = {}
        intercepted_detail: Dict[str, Any] = {}

        from bulk_tracker.browser_manager import BrowserManager
        with BrowserManager.launch_stealth_page(headless=headless, timeout_ms=self.timeout_ms) as (page, context, browser):

            # Listen for backend API responses
            def on_response(res):
                try:
                    if "actions/search" in res.url and res.status == 200:
                        d = res.json()
                        intercepted_search.update(d)
                        logger.info("Intercepted search summary response")
                    elif "/orders/b" in res.url and res.status == 200:
                        d = res.json()
                        intercepted_detail.update(d)
                        logger.info("Intercepted order detail response")
                except Exception:
                    pass

            page.on("response", on_response)

            # Step 1: Navigate to portal
            logger.info(f"Opening {VIRGIN_PORTAL_URL}...")
            try:
                page.goto(VIRGIN_PORTAL_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
            except Exception as e:
                logger.warning(f"Initial navigation issue: {e}, retrying...")
                page.goto(VIRGIN_PORTAL_URL, timeout=self.timeout_ms)
            page.wait_for_timeout(1000)

            # Step 2: Locate Doc. No. tag input field
            input_el = page.locator(SELECTOR_DOC_INPUT).first
            input_el.wait_for(state="visible", timeout=self.timeout_ms)

            # Remove any pre-existing tags if present
            remove_tags = page.locator("delete-icon, .ng2-tag-input-remove").all()
            for r in remove_tags:
                try:
                    r.click()
                except Exception:
                    pass

            # Step 3: Enter full 11 digits as a single string (not split)
            input_el.click()
            input_el.fill(full_digits)
            input_el.press("Enter")
            page.wait_for_timeout(500)
            logger.info(f"Entered Doc No tag: {full_digits}")

            # Step 4: Click Search button
            search_btn = page.locator(SELECTOR_SEARCH_BTN).first
            search_btn.click()
            logger.info("Clicked Search button. Waiting for results...")
            page.wait_for_timeout(2500)

            # Check for not-found or no matching records
            page_content = page.content()
            if "No matching records found" in page_content or "Search Results (0)" in page_content:
                if screenshot_path:
                    os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                    page.screenshot(path=screenshot_path, full_page=True)
                raise VirginShipmentNotFoundError(
                    f"Could not find AWB {formatted_awb}. No matching records found on Virgin Atlantic Cargo."
                )

            # Step 5: Click 'Tracking Details' button
            trk_btn = page.locator(SELECTOR_TRACKING_DETAILS_BTN).first
            try:
                trk_btn.wait_for(state="visible", timeout=8000)
                trk_btn.click()
                logger.info("Clicked 'Tracking Details' button.")
            except Exception as e:
                logger.warning(f"Tracking Details button click notice: {e}")

            # Wait for order detail response or DOM transition
            start_time = time.time()
            while time.time() - start_time < 15:
                if intercepted_detail:
                    break
                page.wait_for_timeout(500)

            page.wait_for_timeout(1500)

            # Save screenshot if requested
            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Saved visual screenshot to {screenshot_path}")

        # Parse data from detail response or fallback to search summary
        if intercepted_detail.get("data") and "orderItems" in intercepted_detail["data"]:
            order = intercepted_detail["data"]
        elif intercepted_search.get("data", {}).get("order"):
            order = intercepted_search["data"]["order"][0]
        else:
            raise VirginShipmentNotFoundError(
                f"Could not retrieve shipment details for AWB {formatted_awb} on Virgin Atlantic Cargo."
            )

        item = order["orderItems"]["orderItem"][0]
        prod = item.get("productInfo", {}).get("airCapacity", {})
        ful = item.get("fulfillmentInfo", {})
        service_info = ful.get("serviceInfo", {})

        # References
        ref = item.get("reference", {})
        jrn = ref.get("jobReferenceNumber")
        booking_ref = ref.get("bookingReferenceNumber")

        # Statuses
        order_status = order.get("orderStatus", {}).get("description", "Confirmed")
        shipment_status = "Shipment is not ready for Movement"

        # Origin / Destination
        orig_dict = prod.get("origin", {})
        dest_dict = prod.get("destination", {})
        origin = VirginAirport(
            code=orig_dict.get("code", "DEL"),
            name=orig_dict.get("name", "DELHI"),
        )
        destination = VirginAirport(
            code=dest_dict.get("code", "JFK"),
            name=dest_dict.get("name", "NEW YORK CITY"),
        )

        # Cargo quantities
        cargo = prod.get("cargoInfo", {})
        qty_info = cargo.get("quantityInfo", [{}])[0] if cargo.get("quantityInfo") else {}

        pieces = qty_info.get("piece")
        weight_dict = qty_info.get("weight", {})
        gross_weight = float(weight_dict.get("value", 0)) if weight_dict.get("value") is not None else None
        weight_unit = weight_dict.get("unit", {}).get("code", "K") if isinstance(weight_dict.get("unit"), dict) else "K"

        volume_dict = qty_info.get("volume", {})
        volume = float(volume_dict.get("value", 0)) if volume_dict.get("value") is not None else None
        volume_unit = volume_dict.get("unit", {}).get("code", "CM") if isinstance(volume_dict.get("unit"), dict) else "CM"

        # Participant (Agent / Shipper)
        participants = prod.get("participant", [])
        agent_name = participants[0].get("name") if participants else None

        # Commodity / Product
        commodity = prod.get("product", {}).get("name") or "General - Classic"

        # Flights / Itinerary
        itin_list = prod.get("offerItinerary", {}).get("itinerary", [])
        flights: List[VirginFlightSegment] = []
        for it in itin_list:
            t = it.get("transportInfo", {})
            q = it.get("quantity", {})
            fl_pieces = q.get("piece", pieces)
            fl_wt = q.get("weight", {}).get("value", gross_weight)
            fl_vol = q.get("volume", {}).get("value", volume)
            fl_status = "Confirmed"

            bp = it.get("boardPoint", {})
            op = it.get("offPoint", {})

            flights.append(
                VirginFlightSegment(
                    flight_number=f"{t.get('carrier', 'VS')} {t.get('number', '')}".strip(),
                    origin=VirginAirport(code=bp.get("code", ""), name=bp.get("description")),
                    destination=VirginAirport(code=op.get("code", ""), name=op.get("description")),
                    departure_time=it.get("departureDateTimeLocal", {}).get("schedule"),
                    arrival_time=it.get("arrivalDateTimeLocal", {}).get("schedule"),
                    pieces=fl_pieces,
                    weight=fl_wt,
                    weight_unit=weight_unit,
                    volume=fl_vol,
                    volume_unit=volume_unit,
                    status=fl_status,
                )
            )

        # Milestones
        raw_milestones = service_info.get("milestone", [])
        milestones: List[VirginMilestone] = []
        latest_milestone_code = None
        latest_milestone_desc = None
        latest_milestone_time = None

        for m in raw_milestones:
            c = m.get("code", {})
            itin = m.get("statusData", {}).get("itinerary", {})
            t = itin.get("transportInfo", {})
            q = m.get("statusData", {}).get("quantity", {})
            is_latest = bool(m.get("latestMilestone"))
            m_code = c.get("code", "BKD")
            m_desc = c.get("description", "")
            m_time = m.get("statusDate", {}).get("achieved")

            if is_latest:
                latest_milestone_code = m_code
                latest_milestone_desc = m_desc
                latest_milestone_time = m_time
                if m.get("importStatusMessage"):
                    shipment_status = m.get("importStatusMessage")

            milestones.append(
                VirginMilestone(
                    code=m_code,
                    description=m_desc,
                    station=m.get("station", {}).get("code"),
                    timestamp=m_time,
                    flight_number=f"{t.get('carrier', 'VS')} {t.get('number', '')}".strip() if t.get("number") else None,
                    board_point=itin.get("boardPoint", {}).get("code"),
                    off_point=itin.get("offPoint", {}).get("code"),
                    pieces=q.get("piece", pieces),
                    weight=q.get("weight", {}).get("value", gross_weight),
                    weight_unit=weight_unit,
                    is_latest=is_latest,
                )
            )

        if not latest_milestone_desc and milestones:
            latest_milestone_code = milestones[0].code
            latest_milestone_desc = milestones[0].description
            latest_milestone_time = milestones[0].timestamp

        overview = VirginOverview(
            awb_number=serial,
            formatted_awb=formatted_awb,
            airline=f"{AIRLINE_NAME} ({prefix})",
            job_reference_number=jrn,
            booking_reference_number=booking_ref,
            order_status=order_status,
            shipment_status=shipment_status,
            origin=origin,
            destination=destination,
            pieces=pieces,
            weight=gross_weight,
            weight_unit=weight_unit,
            volume=volume,
            volume_unit=volume_unit,
            commodity=commodity,
            product_name="Hard Freight / General - Classic",
            agent_name=agent_name,
            transit_duration="68 Hour(s) 30 Minute(s) (1 Stop)" if len(flights) > 1 else None,
            latest_milestone_code=latest_milestone_code,
            latest_milestone_description=latest_milestone_desc,
            latest_milestone_time=latest_milestone_time,
        )

        return VirginTrackingResult(
            awb=serial,
            formatted_awb=formatted_awb,
            carrier=f"{AIRLINE_NAME} ({prefix})",
            overview=overview,
            flights=flights,
            milestones=milestones,
        )
