"""
Production-grade tracking client for ParcelsApp & British Airways Cargo (IATA prefix 125).
Combines stealth browser automation with direct API interception for 100% data fidelity.
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Tuple, Any
from playwright.sync_api import sync_playwright

from parcels_tracker.constants import (
    PARCELSAPP_URL,
    PARCELSAPP_DIRECT_URL,
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    STEALTH_SCRIPT,
)
from parcels_tracker.models import (
    ParcelsAttribute,
    ParcelsCourier,
    ParcelsOverview,
    ParcelsStateEvent,
    ParcelsTrackingResult,
)

logger = logging.getLogger("parcels_tracker")


class ParcelsTrackingError(Exception):
    """Base exception for ParcelsApp tracking."""
    pass


class ParcelsShipmentNotFoundError(ParcelsTrackingError):
    """Raised when shipment tracking details cannot be found."""
    pass


class ParcelsTrackerClient:
    """
    Automates ParcelsApp tracking workflow with advanced bot-detection resistance.
    """

    def __init__(self, timeout_ms: int = 40000):
        self.timeout_ms = timeout_ms

    @staticmethod
    def normalize_tracking_number(tracking_input: str) -> Tuple[str, str, str, str]:
        """
        Normalize AWB/tracking string to (prefix, serial, formatted, full_digits).
        e.g. '125-24128344' -> ('125', '24128344', '125-24128344', '12524128344')
        """
        cleaned = re.sub(r"[^\d]", "", str(tracking_input or "").strip())
        if not cleaned:
            raise ValueError(f"Invalid tracking number: '{tracking_input}'. Expected numeric digits.")

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
        tracking_input: str,
        headless: bool = True,
        screenshot_path: Optional[str] = None,
    ) -> ParcelsTrackingResult:
        """
        Executes ParcelsApp tracking flow:
        1. Navigates to parcelsapp.com/en/tracking
        2. Enters tracking number in 'enter tracking number' field
        3. Clicks 'Track Package'
        4. Intercepts backend states JSON and returns structured tracking result
        """
        prefix, serial, formatted_awb, full_digits = self.normalize_tracking_number(tracking_input)
        logger.info(f"Initiating ParcelsApp tracking for {formatted_awb}")

        intercepted_data: Dict[str, Any] = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="en-US",
                timezone_id="Asia/Kolkata",
            )
            page = context.new_page()

            # Inject WebGL & webdriver stealth bypasses
            page.add_init_script(STEALTH_SCRIPT)

            # Intercept api/v2/parcels responses
            def on_response(res):
                if "api/v2/parcels" in res.url and res.status == 200:
                    try:
                        d = res.json()
                        if d.get("states"):
                            intercepted_data.update(d)
                            logger.info(f"Successfully intercepted tracking payload with {len(d.get('states', []))} states")
                    except Exception:
                        pass

            page.on("response", on_response)

            # Step 1: Open parcelsapp.com/en/tracking
            logger.info(f"Opening {PARCELSAPP_URL}...")
            try:
                page.goto(PARCELSAPP_URL, wait_until="domcontentloaded", timeout=self.timeout_ms)
            except Exception as e:
                logger.warning(f"Navigation slow: {e}")

            page.wait_for_timeout(1500)

            # Dismiss cookie consent if shown
            consent_selectors = [
                ".fc-cta-consent",
                "button:has-text('Consent')",
                "button:has-text('Accept')",
                "button:has-text('Agree')",
            ]
            for sel in consent_selectors:
                try:
                    c_btn = page.locator(sel).first
                    if c_btn.is_visible(timeout=2000):
                        c_btn.click()
                        logger.info("Accepted cookie consent banner.")
                        break
                except Exception:
                    pass

            page.wait_for_timeout(500)

            # Step 2: Fill tracking number into 'enter tracking number' field
            input_el = None
            for sel in [
                "input[placeholder*='tracking number' i]",
                "input[placeholder*='Enter' i]",
                "input[name='trackingId']",
                ".track-input",
                "input[type='text']",
            ]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        input_el = loc
                        break
                except Exception:
                    pass

            if input_el:
                input_el.click()
                input_el.fill(formatted_awb)
                logger.info(f"Entered tracking number '{formatted_awb}' into input.")
            else:
                logger.warning("Could not find input element, navigating to direct URL...")
                direct_url = PARCELSAPP_DIRECT_URL.format(tracking_number=formatted_awb)
                page.goto(direct_url, wait_until="domcontentloaded", timeout=self.timeout_ms)

            page.wait_for_timeout(500)

            # Step 3: Click 'TRACK PACKAGE'
            submit_selectors = [
                "button:has-text('TRACK PACKAGE')",
                "button:has-text('Track Package')",
                ".btn-track",
                "button[type='submit']",
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        submitted = True
                        logger.info("Clicked 'TRACK PACKAGE' button.")
                        break
                except Exception:
                    pass

            if not submitted and input_el:
                input_el.press("Enter")

            # Step 4: Wait for results payload or DOM elements
            start_time = time.time()
            while time.time() - start_time < 25:
                if intercepted_data:
                    break
                page.wait_for_timeout(1000)

            page.wait_for_timeout(2000)

            # Step 5: Save screenshot if requested
            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Saved full page screenshot to {screenshot_path}")

            browser.close()

        if not intercepted_data or not intercepted_data.get("states"):
            raise ParcelsShipmentNotFoundError(
                f"Could not retrieve tracking details for '{formatted_awb}' on ParcelsApp."
            )

        # Parse intercepted data
        raw_states = intercepted_data.get("states", [])
        raw_services = intercepted_data.get("services", [])
        raw_attributes = intercepted_data.get("attributes", [])

        couriers: List[ParcelsCourier] = []
        courier_names: List[str] = []
        for s in raw_services:
            c_name = s.get("name", "")
            c_slug = s.get("slug", "")
            if c_name:
                couriers.append(ParcelsCourier(name=c_name, slug=c_slug))
                courier_names.append(c_name)

        primary_carrier = courier_names[0] if courier_names else "British Airways Cargo"

        states: List[ParcelsStateEvent] = []
        for idx, st in enumerate(raw_states):
            c_idx = st.get("carrier", 0)
            c_name = courier_names[c_idx] if c_idx < len(courier_names) else primary_carrier
            states.append(
                ParcelsStateEvent(
                    date=st.get("date"),
                    status=st.get("status", ""),
                    location=st.get("location"),
                    carrier_name=c_name,
                    is_latest=(idx == 0),
                )
            )

        attributes: List[ParcelsAttribute] = []
        attr_dict = {}
        for attr in raw_attributes:
            k = attr.get("l") or ""
            n = attr.get("n") or k
            v = str(attr.get("val") or "")
            if k:
                attributes.append(ParcelsAttribute(key=k, name=n, value=v))
                attr_dict[k] = v

        latest_state = states[0] if states else None
        overview = ParcelsOverview(
            tracking_number=serial,
            formatted_tracking_number=formatted_awb,
            origin_country=intercepted_data.get("origin"),
            origin_location=intercepted_data.get("from"),
            destination_country=intercepted_data.get("destination"),
            destination_location=intercepted_data.get("to"),
            weight=intercepted_data.get("weight"),
            number_of_packages=attr_dict.get("packages"),
            pieces=attr_dict.get("pieces"),
            days_in_transit=attr_dict.get("days_transit"),
            primary_carrier=primary_carrier,
            couriers=courier_names,
            latest_status=latest_state.status if latest_state else "In Transit",
            latest_location=latest_state.location if latest_state else None,
            latest_date=latest_state.date if latest_state else None,
        )

        return ParcelsTrackingResult(
            tracking_number=serial,
            formatted_tracking_number=formatted_awb,
            airline=f"{primary_carrier} ({prefix})",
            overview=overview,
            states=states,
            couriers=couriers,
            attributes=attributes,
        )
