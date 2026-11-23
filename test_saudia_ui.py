import os
import sys
import time
from playwright.sync_api import sync_playwright

def test_saudia_ui():
    print("Starting Playwright UI Verification for Saudia Cargo (065-4710-2484)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 950})
        page = context.new_page()

        # 1. Navigate to localhost:8000
        print("Navigating to http://localhost:8000...")
        page.goto("http://localhost:8000", wait_until="networkidle", timeout=30000)

        # Check badges
        badges = page.locator(".carrier-badge, [class*='badge-']").all_text_contents()
        print("Visible header badges:", [b.strip() for b in badges if b.strip()])

        # 2. Check input and enter Saudia AWB
        input_el = page.locator("#awbInput")
        current_val = input_el.input_value()
        print("Current input value:", current_val)
        
        input_el.fill("065-4710-2484")

        # 3. Click Track Shipment
        print("Clicking 'Track Shipment' button...")
        track_btn = page.locator("#singleTrackerSection button.btn-search")
        track_btn.click()

        # 4. Wait for #resultCard to become visible
        print("Waiting for #resultCard to render...")
        page.wait_for_selector("#resultCard", state="visible", timeout=45000)

        # Wait for data to populate
        page.wait_for_timeout(2000)

        # 5. Extract UI values
        carrier_text = page.locator("#carrierTag").inner_text()
        awb_text = page.locator("#awbDisplay").inner_text()
        status_text = page.locator("#statusPill").inner_text()
        route_text = page.locator("#routeDisplay").inner_text()
        pieces_text = page.locator("#pcsWeightDisplay").inner_text()
        volume_text = page.locator("#volumeDisplay").inner_text()
        commodity_text = page.locator("#productDisplay").inner_text()

        print("\n--- UI Verification Results ---")
        print("Carrier Tag:", carrier_text)
        print("AWB Display:", awb_text)
        print("Status Pill:", status_text)
        print("Route:", route_text)
        print("Pieces & Weight:", pieces_text)
        print("Volume Details:", volume_text)
        print("Commodity / Status:", commodity_text)

        # Check action buttons
        action_buttons = page.locator("#latestBanner a, #latestBanner button").all_text_contents()
        print("Action Buttons in Banner:", [ab.strip() for ab in action_buttons if ab.strip()])

        # Check flights table
        flights_rows = page.locator("#flightsBody tr").all_text_contents()
        print("Flight rows count:", len(flights_rows))
        for idx, row in enumerate(flights_rows[:3]):
            print(f" Flight Row {idx+1}:", " | ".join(row.split()))

        # Switch to Milestones & History tab
        print("\nClicking 'Milestones & History' tab...")
        page.locator("button:has-text('Milestones & History')").click()
        page.wait_for_timeout(1000)

        milestone_rows = page.locator("#historyBody tr").all_text_contents()
        print("Milestones count:", len(milestone_rows))
        for idx, row in enumerate(milestone_rows[:5]):
            print(f" Milestone {idx+1}:", " | ".join(row.split()))

        # 6. Capture full screenshot
        os.makedirs("screenshots", exist_ok=True)
        screenshot_path = "screenshots/saudia_065_47102484_verified.png"
        page.screenshot(path=screenshot_path, full_page=True)
        print(f"\nSaved verified screenshot to {screenshot_path}")

        # Also copy to artifacts directory
        artifact_dir = "/Users/apple/.gemini/antigravity/brain/00993f6d-1fd9-43e2-928c-5a2dd53f5e09"
        if os.path.isdir(artifact_dir):
            import shutil
            shutil.copy(screenshot_path, os.path.join(artifact_dir, "saudia_065_47102484_verified.png"))
            print(f"Copied screenshot to artifact directory: {artifact_dir}")

        browser.close()
        print("UI Verification completed successfully!")

if __name__ == "__main__":
    test_saudia_ui()
