"""
Kuwait Airways Cargo Browser Automation with Playwright.
Automates visual browser tracking:
1. Navigates to https://www.kuwaitairways.com/en/cargo/tracking
2. Handles cookie consent ('Accept Cookies')
3. Inputs the 8-digit tracking serial into 'AWB# :' field (#txtAwbNo)
4. Submits the tracking form
5. Detects either the tracking results or the not-found error message
6. Captures high-resolution visual screenshots
"""

import os
import re
import logging
from typing import Optional, Dict, Any, Tuple
from playwright.sync_api import sync_playwright

from kuwait_tracker.constants import PORTAL_URL, AIRLINE_PREFIX, AIRLINE_NAME
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError

logger = logging.getLogger("kuwait_tracker.browser")


class KuwaitBrowserTracker:
    """
    Automates live browser tracking on Kuwait Airways cargo portal with anti-bot defenses.
    """

    @staticmethod
    def extract_serial(awb_input: str) -> Tuple[str, str]:
        """
        Extract the 8-digit serial and formatted AWB.
        e.g. ('18148900', '229-18148900')
        """
        cleaned = re.sub(r"[^\d]", "", str(awb_input or "").strip())
        if len(cleaned) == 11 and cleaned.startswith(AIRLINE_PREFIX):
            serial = cleaned[3:]
        elif len(cleaned) == 8:
            serial = cleaned
        elif len(cleaned) > 8:
            serial = cleaned[-8:]
        else:
            serial = cleaned.zfill(8)

        return serial, f"{AIRLINE_PREFIX}-{serial}"

    def track_in_browser(
        self,
        awb_input: str,
        headless: bool = True,
        screenshot_path: Optional[str] = None,
        timeout_ms: int = 35000,
    ) -> Dict[str, Any]:
        """
        Executes end-to-end browser tracking on Kuwait Airways portal.
        """
        serial, formatted_awb = self.extract_serial(awb_input)
        logger.info(f"Initiating browser tracking for serial: {serial} (AWB: {formatted_awb})")

        error_message: Optional[str] = None
        has_results = False

        from bulk_tracker.browser_manager import BrowserManager
        with BrowserManager.launch_stealth_page(headless=headless, timeout_ms=timeout_ms) as (page, context, browser):

            logger.info(f"Navigating to {PORTAL_URL}...")
            try:
                page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                logger.warning(f"Navigation slow: {e}")

            page.wait_for_timeout(1500)

            # 1. Accept Cookie Banner
            cookie_selectors = [
                "button:has-text('Accept Cookies')",
                "button:has-text('Accept')",
                "#accept-cookies",
                ".cookie-accept",
            ]
            for sel in cookie_selectors:
                try:
                    c_btn = page.locator(sel).first
                    if c_btn.is_visible(timeout=2000):
                        c_btn.click()
                        logger.info("Accepted cookies banner.")
                        break
                except Exception:
                    pass

            page.wait_for_timeout(800)

            # 2. Enter 8-digit tracking serial in #txtAwbNo
            input_el = None
            for sel in ["#txtAwbNo", "input[name='txtAwbNo']", "input[placeholder*='AWB' i]"]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        input_el = loc
                        break
                except Exception:
                    pass

            if not input_el:
                # Fallback to any visible text input in the tracking container
                inputs = page.locator("input[type='text']").all()
                if len(inputs) >= 2:
                    input_el = inputs[1]  # Second input is AWB# (first is Prefix 229)

            if input_el:
                input_el.click()
                input_el.fill(serial)
                logger.info(f"Entered serial '{serial}' into input field.")
            else:
                logger.error("Could not locate AWB input field on Kuwait Airways portal.")

            page.wait_for_timeout(500)

            # 3. Click Submit button
            submit_selectors = [
                "#btnSubmit",
                "button:has-text('Submit')",
                "input[value='Submit']",
                ".btnSubmit",
            ]
            submitted = False
            for sel in submit_selectors:
                try:
                    s_btn = page.locator(sel).first
                    if s_btn.is_visible(timeout=2000):
                        s_btn.click()
                        submitted = True
                        logger.info("Clicked Submit button.")
                        break
                except Exception:
                    pass

            if not submitted and input_el:
                input_el.press("Enter")

            # 4. Wait for response or error
            page.wait_for_timeout(4000)

            # Check for error message (e.g. "Could not find AWB 229-17349566...")
            for err_sel in [
                "span:has-text('Could not find AWB')",
                "div:has-text('Could not find AWB')",
                "p:has-text('Could not find AWB')",
                ".errorMessage",
                ".error",
            ]:
                try:
                    err_el = page.locator(err_sel).first
                    if err_el.is_visible(timeout=2000):
                        txt = err_el.inner_text().strip()
                        if "Could not find" in txt or "Please check" in txt:
                            error_message = txt
                            logger.warning(f"Portal returned error: {error_message}")
                            break
                except Exception:
                    pass

            # Check if results are rendered
            try:
                if page.locator("text='Shipment Info'").first.is_visible(timeout=2000):
                    has_results = True
            except Exception:
                pass

            # 5. Capture screenshot
            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Saved screenshot to {screenshot_path}")

            final_url = page.url

            # Retrieve structured data via direct client
            client = KuwaitCargoClient()
            tracking_result = None
            if not error_message:
                try:
                    tracking_result = client.track(formatted_awb)
                except KuwaitShipmentNotFoundError as e:
                    error_message = str(e)
            else:
                try:
                    # Double check via API
                    tracking_result = client.track(formatted_awb)
                    error_message = None
                except KuwaitShipmentNotFoundError as e:
                    error_message = str(e)

            return {
                "awb_serial": serial,
                "formatted_awb": formatted_awb,
                "airline": f"{AIRLINE_NAME} ({AIRLINE_PREFIX})",
                "final_url": final_url,
                "screenshot_path": screenshot_path,
                "error": error_message,
                "has_results": bool(tracking_result and not error_message),
                "tracking_result": tracking_result,
                "status": "success" if not error_message else "not_found",
            }
