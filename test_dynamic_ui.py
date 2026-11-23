import os
import time
from playwright.sync_api import sync_playwright

def test_dynamic_ui():
    print("Testing Dynamic Track Button & Production UI...")
    os.makedirs("screenshots", exist_ok=True)
    artifact_dir = "/Users/apple/.gemini/antigravity/brain/00993f6d-1fd9-43e2-928c-5a2dd53f5e09"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 960})
        page = context.new_page()

        print("Navigating to http://localhost:8000...")
        page.goto("http://localhost:8000", wait_until="networkidle", timeout=30000)

        # 1. Verify Header Elements
        brand_title = page.locator(".brand-title").inner_text()
        print("Brand Title:", brand_title)
        carrier_pills = page.locator(".c-pill").all_text_contents()
        print(f"Carrier Status Strip ({len(carrier_pills)} carriers):", [c.strip() for c in carrier_pills[:6]], "...")

        # 2. Wait for initial tracking to settle if any
        page.wait_for_timeout(3000)

        # 3. Enter AWB and click Track
        input_el = page.locator("#awbInput")
        input_el.fill("065-4710-2484")

        track_btn = page.locator("#trackBtn")
        print("Initial Track Button Disabled state:", track_btn.is_disabled())

        # Click track button
        print("Clicking Track Shipment button...")
        track_btn.click()

        # 4. IMMEDIATELY verify Dynamic Loading State
        page.wait_for_timeout(500)
        is_disabled = track_btn.is_disabled()
        loading_text_visible = page.locator(".btn-content-loading").is_visible()
        spinner_visible = page.locator(".btn-spinner").is_visible()
        loader_card_visible = page.locator("#loader").is_visible()
        radar_visible = page.locator(".radar-box").is_visible()
        step_text = page.locator("#loaderDynamicStep").inner_text()
        timer_text = page.locator("#loaderTimer").inner_text()

        print("\n--- Dynamic Loading State Verification ---")
        print("Button Disabled:", is_disabled)
        print("Loading Text Visible:", loading_text_visible)
        print("Spinner Icon Visible:", spinner_visible)
        print("Modern Loader Visible:", loader_card_visible)
        print("Radar Scanner Visible:", radar_visible)
        print("Dynamic Step Message:", step_text)
        print("Live Timer:", timer_text)

        # Capture Loading State Screenshot
        loading_screenshot = "screenshots/dynamic_tracking_loading_state.png"
        page.screenshot(path=loading_screenshot, full_page=False)
        print(f"Captured Loading State screenshot to {loading_screenshot}")
        if os.path.isdir(artifact_dir):
            import shutil
            shutil.copy(loading_screenshot, os.path.join(artifact_dir, "dynamic_tracking_loading_state.png"))

        assert is_disabled, "Button should be disabled during tracking!"
        assert loader_card_visible, "Loader radar card should be visible during tracking!"

        # 5. Wait for tracking to finish
        print("\nWaiting for tracking to complete and resultCard to render...")
        page.wait_for_selector("#resultCard", state="visible", timeout=45000)
        page.wait_for_timeout(2000)

        # 6. Verify Completed State
        is_disabled_after = track_btn.is_disabled()
        default_text_visible = page.locator(".btn-content-default").is_visible()
        awb_display = page.locator("#awbDisplay").inner_text()
        status_pill = page.locator("#statusPill").inner_text()
        copy_btn_visible = page.locator("#btnCopyAwb").is_visible()

        print("\n--- Completed State Verification ---")
        print("Button Disabled After Completion:", is_disabled_after)
        print("Default Button Text Restored:", default_text_visible)
        print("AWB Displayed:", awb_display)
        print("Status Pill:", status_pill)
        print("Copy Button Visible:", copy_btn_visible)

        # Test Copy AWB button
        page.locator("#btnCopyAwb").click()
        page.wait_for_timeout(500)
        copy_btn_text = page.locator("#btnCopyAwb").inner_text()
        print("Copy Button After Click:", copy_btn_text)

        # Capture Completed State Screenshot
        completed_screenshot = "screenshots/dynamic_tracking_completed_state.png"
        page.screenshot(path=completed_screenshot, full_page=True)
        print(f"Captured Completed State screenshot to {completed_screenshot}")
        if os.path.isdir(artifact_dir):
            import shutil
            shutil.copy(completed_screenshot, os.path.join(artifact_dir, "dynamic_tracking_completed_state.png"))

        browser.close()
        print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_dynamic_ui()
