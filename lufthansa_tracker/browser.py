"""
Lufthansa Cargo Browser Automation with Playwright.
Automates visual browser tracking: handles Cookie consent ('Deny'),
input normalization, search submission, and screenshot capture.
"""

import os
import re
import logging
from typing import Optional, Dict, Any
from playwright.sync_api import sync_playwright

from .constants import PORTAL_URL, AIRLINE_PREFIX

logger = logging.getLogger("lufthansa_tracker.browser")


class LufthansaBrowserTracker:
    """Automates tracking via the live Lufthansa Cargo website using Playwright."""

    @staticmethod
    def extract_serial(awb_input: str) -> str:
        """Strip 020 prefix and non-digits to get the 8-digit serial number."""
        cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
        if cleaned.startswith(AIRLINE_PREFIX) and len(cleaned) == 11:
            return cleaned[3:]
        elif len(cleaned) == 8:
            return cleaned
        return cleaned

    def track_in_browser(
        self,
        awb_input: str,
        headless: bool = True,
        screenshot_path: Optional[str] = None,
        timeout_ms: int = 30000,
    ) -> Dict[str, Any]:
        """
        Open the Lufthansa Cargo eTracking portal, handle cookie consent ('Deny'),
        fill in the AWB serial, click Search, and capture the result page.
        """
        serial = self.extract_serial(awb_input)
        logger.info(f"Initiating browser tracking for serial: {serial} (input: {awb_input})")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1440, "height": 900},
                locale="en-US",
            )
            page = context.new_page()

            try:
                page.goto(PORTAL_URL, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as e:
                logger.warning(f"Initial navigation slow/timed out: {e}")

            page.wait_for_timeout(2000)

            # 1. Handle Cookie Settings popup -> Click Deny
            deny_selectors = [
                "button:has-text('Deny')",
                "#consent-deny",
                "#onetrust-reject-all-handler",
                "button[data-testid='uc-deny-all-button']",
                ".uc-deny-all",
            ]
            for sel in deny_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click()
                        logger.info("Successfully clicked Cookie 'Deny' button.")
                        break
                except Exception:
                    pass

            page.wait_for_timeout(1000)

            # 2. Fill in the 8-digit tracking serial
            input_selectors = [
                "input[placeholder*='Airwaybill number' i]",
                "input[name*='awb' i]",
                "input[type='text']",
            ]
            input_el = None
            for sel in input_selectors:
                try:
                    el = page.locator(sel).first
                    if el.is_visible(timeout=2000):
                        input_el = el
                        break
                except Exception:
                    pass

            if input_el:
                input_el.fill(serial)
                logger.info(f"Entered serial '{serial}' into input field.")
                page.wait_for_timeout(500)

                # 3. Click the Search button
                search_selectors = [
                    "button:has-text('Search')",
                    "button[type='submit']",
                ]
                clicked = False
                for sel in search_selectors:
                    try:
                        s_btn = page.locator(sel).first
                        if s_btn.is_visible(timeout=2000):
                            s_btn.click()
                            clicked = True
                            break
                    except Exception:
                        pass

                if not clicked:
                    input_el.press("Enter")

                page.wait_for_timeout(6000)
            else:
                # Direct navigation fallback
                direct_url = f"{PORTAL_URL}/tracking/-/awb/{AIRLINE_PREFIX}/{serial}"
                logger.info(f"Directly navigating to: {direct_url}")
                page.goto(direct_url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(6000)

            result_url = page.url
            if screenshot_path:
                os.makedirs(os.path.dirname(os.path.abspath(screenshot_path)), exist_ok=True)
                page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Saved full page screenshot to {screenshot_path}")

            browser.close()

            return {
                "awb_serial": serial,
                "result_url": result_url,
                "screenshot_path": screenshot_path,
                "status": "success",
            }
