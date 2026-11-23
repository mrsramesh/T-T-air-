import time
from playwright.sync_api import sync_playwright

def verify_no_auto_track():
    print("Verifying page load and refresh behavior...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        api_calls = []
        def on_request(req):
            if "/api/v1/track" in req.url:
                api_calls.append(req.url)
                print(f"--> Intercepted tracking request: {req.url}")

        page.on("request", on_request)

        # 1. First Load
        print("\nLoading page http://localhost:8000...")
        page.goto("http://localhost:8000", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        loader_visible = page.locator("#loader").is_visible()
        btn_loading = page.locator(".btn-content-loading").is_visible()
        result_visible = page.locator("#resultCard").is_visible()

        print("On First Load:")
        print("  - Tracking API Calls Count:", len(api_calls))
        print("  - Loader Visible:", loader_visible)
        print("  - Button in Loading State:", btn_loading)
        print("  - Result Card Visible:", result_visible)

        assert len(api_calls) == 0, f"Expected 0 tracking calls on page load, but got {len(api_calls)}!"
        assert not loader_visible, "Loader should NOT be visible on initial load!"
        assert not btn_loading, "Button should NOT be in loading state on initial load!"

        # 2. Reload / Refresh
        print("\nReloading / Refreshing page...")
        page.reload(wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)

        loader_visible_reload = page.locator("#loader").is_visible()
        btn_loading_reload = page.locator(".btn-content-loading").is_visible()

        print("On Page Reload:")
        print("  - Total Tracking API Calls Count:", len(api_calls))
        print("  - Loader Visible:", loader_visible_reload)
        print("  - Button in Loading State:", btn_loading_reload)

        assert len(api_calls) == 0, f"Expected 0 tracking calls after reload, but got {len(api_calls)}!"
        assert not loader_visible_reload, "Loader should NOT be visible after reload!"
        assert not btn_loading_reload, "Button should NOT be in loading state after reload!"

        # 3. Explicit User Click Verification
        print("\nTesting user explicit click on Track Shipment...")
        page.locator("#trackBtn").click()
        page.wait_for_timeout(500)

        print("After User Click:")
        print("  - Tracking API Calls Count:", len(api_calls))
        print("  - Button in Loading State:", page.locator(".btn-content-loading").is_visible())
        assert len(api_calls) >= 1, "Tracking call should trigger when user clicks Track Shipment!"

        browser.close()
        print("\nVERIFICATION PASSED: No auto tracking on refresh or page load!")

if __name__ == "__main__":
    verify_no_auto_track()
