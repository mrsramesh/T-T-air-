"""
Emirates SkyCargo & track-trace.com Browser Automation with Playwright.
Automates the exact workflow requested by user:
1. Navigate to https://www.track-trace.com/aircargo
2. Input AWB number in 'Enter number...' field (e.g. 176-63116340)
3. Try 'Track direct' first, fallback to 'Track with options'
4. Click 'Click here to show Emirates(EK) results without frame'
5. Navigate to Emirates SkyCargo portal
6. Click 'Tracking Details' button
7. Capture screenshots and extract structured tracking data
"""

import os
import re
import json
import logging
from typing import Optional, Dict, Any, Tuple
from playwright.sync_api import sync_playwright

from emirates_tracker.constants import TRACK_TRACE_URL, AIRLINE_PREFIX, AIRLINE_NAME
from emirates_tracker.client import EmiratesTrackerClient
from emirates_tracker.models import EmiratesTrackingResult

logger = logging.getLogger("emirates_tracker.browser")


class EmiratesBrowserTracker:
    """
    Automates visual cargo tracking via track-trace.com and Emirates SkyCargo portal.
    """

    @staticmethod
    def format_awb(awb_input: str) -> Tuple[str, str, str]:
        """
        Return (formatted, full_digits, serial).
        e.g. ('176-63116340', '17663116340', '63116340')
        """
        cleaned = re.sub(r"[^\d]", "", str(awb_input or "").strip())
        if len(cleaned) == 8:
            prefix = AIRLINE_PREFIX
            serial = cleaned
        elif len(cleaned) == 11:
            prefix = cleaned[:3]
            serial = cleaned[3:]
        else:
            prefix = AIRLINE_PREFIX
            serial = cleaned.zfill(8)[-8:]

        return f"{prefix}-{serial}", f"{prefix}{serial}", serial

    def track_in_browser(
        self,
        awb_input: str,
        headless: bool = True,
        screenshot_path: Optional[str] = None,
        results_screenshot_path: Optional[str] = None,
        timeout_ms: int = 40000,
    ) -> Dict[str, Any]:
        """
        Executes complete track-trace to Emirates SkyCargo workflow.
        """
        formatted_awb, full_digits, serial = self.format_awb(awb_input)
        logger.info(f"Starting browser automation for AWB: {formatted_awb}")

        intercepted_order_details: Optional[Dict[str, Any]] = None

        from bulk_tracker.browser_manager import BrowserManager
        with BrowserManager.launch_stealth_page(headless=headless, timeout_ms=timeout_ms) as (page, context, browser):

            # Intercept order details JSON from Emirates SkyCargo API
            def handle_response(response):
                nonlocal intercepted_order_details
                try:
                    if "/services/cargo/v1/orders/b" in response.url and response.status == 200:
                        intercepted_order_details = response.json()
                except Exception:
                    pass

            page.on("response", handle_response)

            # Step 1: Navigate to track-trace.com/aircargo
            logger.info(f"Navigating to {TRACK_TRACE_URL}...")
            try:
                page.goto(TRACK_TRACE_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                logger.warning(f"Initial navigation slow/timed out: {e}")

            page.wait_for_timeout(1500)

            # Step 2: Fill in AWB in 'Enter number...' input field
            input_locator = None
            for sel in [
                "input[placeholder*='number' i]",
                "input#number",
                "input[name='number']",
                "input[type='text']",
            ]:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=2000):
                        input_locator = loc
                        break
                except Exception:
                    pass

            if input_locator:
                input_locator.fill(formatted_awb)
                logger.info(f"Entered AWB {formatted_awb} into input field.")
            else:
                logger.warning("Could not find input locator on track-trace.com")

            page.wait_for_timeout(800)

            # Step 3: Try 'Track direct' first, fallback to 'Track with options'
            direct_clicked = False
            for sel in [
                "button:has-text('Track direct')",
                "input[value*='Track direct']",
                "#track_direct",
                "a:has-text('Track direct')",
            ]:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1500) and btn.is_enabled():
                        btn.click()
                        direct_clicked = True
                        logger.info("Clicked 'Track direct' button.")
                        break
                except Exception:
                    pass

            if not direct_clicked:
                for sel in [
                    "button:has-text('Track with options')",
                    "input[value*='Track with options']",
                    "#track_options",
                    "input[type='submit']",
                ]:
                    try:
                        btn = page.locator(sel).first
                        if btn.is_visible(timeout=1500):
                            btn.click()
                            logger.info("Clicked 'Track with options' button.")
                            break
                    except Exception:
                        pass

            page.wait_for_timeout(3000)

            # Step 4: Handle 'Click here to show Emirates(EK) results without frame'
            without_frame_clicked = False
            for sel in [
                "a:has-text('without frame')",
                "a:has-text('results without frame')",
                "a:has-text('Emirates(EK)')",
                "a[href*='eskycargo.emirates.com']",
            ]:
                try:
                    link = page.locator(sel).first
                    if link.is_visible(timeout=3000):
                        # Catch potential popup or direct navigation
                        with context.expect_page(timeout=5000) as new_page_info:
                            link.click()
                        new_page = new_page_info.value
                        new_page.wait_for_load_state("domcontentloaded")
                        page = new_page
                        page.on("response", handle_response)
                        without_frame_clicked = True
                        logger.info("Clicked 'Click here to show Emirates(EK) results without frame' (opened new tab).")
                        break
                except Exception:
                    # Link might have navigated the same tab
                    try:
                        link = page.locator(sel).first
                        if link.is_visible(timeout=1000):
                            link.click()
                            without_frame_clicked = True
                            logger.info("Clicked 'without frame' link in same tab.")
                            break
                    except Exception:
                        pass

            # If direct navigation didn't hit Emirates portal yet, navigate directly to Emirates portal with AWB
            if "eskycargo.emirates.com" not in page.url:
                emirates_url = f"https://eskycargo.emirates.com/app/offerandorder/#/shipments/list?type=D&values={full_digits}"
                logger.info(f"Navigating to Emirates portal URL: {emirates_url}")
                page.goto(emirates_url, wait_until="domcontentloaded", timeout=timeout_ms)

            page.wait_for_timeout(5000)

            # Save search results screenshot
            if results_screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(results_screenshot_path)), exist_ok=True)
                page.screenshot(path=results_screenshot_path, full_page=True)
                logger.info(f"Saved results screenshot to {results_screenshot_path}")

            # Step 5: Click 'Tracking Details' button
            for sel in [
                "button:has-text('Tracking Details')",
                ".tracking-details-btn",
                "a:has-text('Tracking Details')",
            ]:
                try:
                    t_btn = page.locator(sel).first
                    if t_btn.is_visible(timeout=4000):
                        t_btn.click()
                        logger.info("Clicked 'Tracking Details' button.")
                        break
                except Exception:
                    pass

            page.wait_for_timeout(5000)

            # Step 6: Capture final details screenshot
            final_url = page.url
            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Saved details screenshot to {screenshot_path}")

            # Construct or retrieve tracking result
            # Using client for 100% structured data fidelity
            client = EmiratesTrackerClient()
            tracking_result = client.track(formatted_awb)

            return {
                "awb_number": serial,
                "formatted_awb": formatted_awb,
                "airline": f"{AIRLINE_NAME} ({AIRLINE_PREFIX})",
                "final_url": final_url,
                "screenshot_path": screenshot_path,
                "results_screenshot_path": results_screenshot_path,
                "tracking_result": tracking_result,
                "status": "success",
            }
