import asyncio
import os
import shutil
from playwright.async_api import async_playwright

async def capture_all():
    os.makedirs('screenshots', exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={'width': 1440, 'height': 960})
        page = await context.new_page()

        print("Navigating to http://127.0.0.1:8000...")
        await page.goto('http://127.0.0.1:8000')
        await page.wait_for_timeout(1500)

        # 1. Single Tracker View
        print("Capturing 1. Single Tracker (Initial)...")
        await page.screenshot(path='screenshots/enterprise_single_initial.png', full_page=False)

        # Fill & Track Saudia Sample AWB
        print("Triggering Saudia tracking in Single Tracker...")
        await page.click('button.quick-btn.qb-sv')
        # Wait for result card to appear
        await page.wait_for_selector('#resultCard', state='visible', timeout=30000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path='screenshots/enterprise_single_tracked.png', full_page=False)

        # Switch to Milestones Tab
        await page.click("button.tab-item:has-text('Milestones & History')")
        await page.wait_for_timeout(800)
        await page.screenshot(path='screenshots/enterprise_single_milestones.png', full_page=False)

        # 2. Bulk Tracker View
        print("Capturing 2. Bulk Tracker View...")
        await page.click('#btnModeBulk')
        await page.wait_for_timeout(1000)
        # Click Fill User 11 AWBs
        await page.click("button:has-text('Fill User')")
        await page.wait_for_timeout(500)
        await page.screenshot(path='screenshots/enterprise_bulk_input.png', full_page=False)

        # 3. Master Cargo Ledger View
        print("Capturing 3. Master Cargo Ledger View...")
        await page.click('#btnModeLedger')
        await page.wait_for_timeout(2000)
        await page.screenshot(path='screenshots/enterprise_master_ledger.png', full_page=False)

        # 4. Google Sheets Auto-Tracker View
        print("Capturing 4. Google Sheets Auto-Tracker View...")
        await page.click('#btnModeSheets')
        await page.wait_for_timeout(1500)
        await page.screenshot(path='screenshots/enterprise_sheets_dashboard.png', full_page=False)

        # Trigger Sheet Inspect to show Preview Table & Column Mappings
        print("Triggering Google Sheet Inspection...")
        await page.click('#btnGSheetInspect')
        await page.wait_for_selector('#gSheetInspectCard', state='visible', timeout=20000)
        await page.wait_for_timeout(1500)
        await page.screenshot(path='screenshots/enterprise_sheets_inspected.png', full_page=False)

        await browser.close()
        print("All screenshots captured successfully!")

asyncio.run(capture_all())
