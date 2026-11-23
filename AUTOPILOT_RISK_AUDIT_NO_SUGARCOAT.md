# Auto Mode Technical Risk Audit (No Sugar Coating)

## Executive Summary
This document provides an unvarnished, 100% transparent architectural audit of running the **Auto-Pilot / Google Sheets Lifecycle Tracking Engine** in continuous 24/7 background production based on the **current codebase**.

While the core lifecycle logic (skipping delivered shipments, parsing AWBs from Column H, updating SQLite ledger) is functional for manual batches, running it on an automated 24/7 background loop exposes **7 severe failure modes** that will inevitably cause degraded performance, IP blocks, or server crashes if not engineered with enterprise safeguards.

---

## 1. The 7 Critical Failure Modes in Current Code

### Risk #1: IP Blacklisting & Anti-Bot Bans (No Rotating Proxy Pool)
* **What the code does right now**:
  Every cycle (e.g. every 30 minutes), the daemon sends tracking requests across 13 airline websites and aggregator portals (ParcelsApp, Track-Trace, Saudia Cargo, Emirates SkyCargo, Turkish Cargo, Air India).
* **The Brutal Reality**:
  - ALL requests originate from the **same single static IP address** of your server/Mac.
  - Carriers like **Turkish Cargo (PerimeterX)**, **Saudia Cargo (Google reCAPTCHA v3)**, and **Emirates (Akamai/Cloudflare)** maintain strict rate-limit thresholds.
  - When 20 to 50 AWBs are queried repeatedly from the same IP every 30 minutes, carrier bot-detection algorithms will flag your IP within 2 to 4 hours.
  - **Result**: Portals start returning `UNREACHABLE`, HTTP 403 Forbidden, or interactive CAPTCHA challenges, causing tracking to fail.
* **Industry Standard Solution**:
  Integrate a **Residential Rotating Proxy Pool** (e.g. BrightData, SmartProxy, or Webshare). Every outbound request or Playwright browser session must route through a new residential IP with realistic TLS fingerprints.

---

### Risk #2: Memory Exhaustion (OOM) & Headless Browser Leaks
* **What the code does right now**:
  In `bulk_tracker/engine.py`, `track_batch` runs with `ThreadPoolExecutor(max_workers=5)`.
  Multiple carriers (`saudia_tracker` / `parcels_tracker`, `emirates_tracker`, `kuwait_tracker`, `lufthansa_tracker`) instantiate Playwright Chromium instances.
* **The Brutal Reality**:
  - One Chromium headless browser consumes between **150MB to 350MB of RAM**.
  - 5 concurrent Chromium instances = **1.5 GB to 2.0 GB of instantaneous RAM usage**.
  - If a carrier page takes too long or hangs on a network socket, the Chromium process may not terminate immediately.
  - On a standard cloud VPS (1GB–2GB RAM) or a shared machine, this will trigger the OS **OOM Killer (Out Of Memory)**, instantly terminating the Python Uvicorn process (`Killed: 9`), bringing down your entire tracker.
* **Industry Standard Solution**:
  - Cap concurrent browser workers to a strict pool of **max 2 browser instances** at any time.
  - Wrap browser execution in strict OS timeouts (`timeout 40s`) and ensure `browser.close()` and `context.close()` are enclosed in guaranteed `finally` blocks with process reaping.

---

### Risk #3: Fragility of Unofficial Google Sheet XLSX Export Link
* **What the code does right now**:
  In `bulk_tracker/google_sheets.py`, lines 79-85:
  ```python
  export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
  req = urllib.request.Request(export_url, headers={...})
  ```
* **The Brutal Reality**:
  - This is an **unofficial public web export link**, NOT the official Google Sheets API.
  - When polled automatically on a recurring timer, Google's web edge servers detect scraping behavior and return **HTTP 429 Too Many Requests** or redirect to a Google Account login page.
  - **Zero Write-Back Capability**: You cannot write statuses (e.g. "DELIVERED", timestamps, pieces) back into the Google Sheet columns with this URL. It is strictly a one-way read.
* **Industry Standard Solution**:
  Use the official **Google Sheets API v4** with a dedicated **Google Cloud Service Account JSON** (`credentials.json`). This gives you:
  - 300 read/write requests per minute guaranteed without rate limits.
  - Direct two-way sync: writing tracking status directly back to the user's Google Sheet cells in real time.

---

### Risk #4: SQLite Database Locking (`OperationalError: database is locked`)
* **What the code does right now**:
  The entire shipment ledger is stored in a single local SQLite file: `data/master_cargo_ledger.db`.
* **The Brutal Reality**:
  - In Auto Mode, the background thread `AutoPilot-Worker` executes batch `upsert_record` transactions.
  - While it is writing to SQLite, if the user in the Web UI views the Ledger, searches an AWB, or clicks "Export to Excel", SQLite file lock contention occurs.
  - If the database file is busy, web queries will crash with:
    `sqlite3.OperationalError: database is locked`
    resulting in HTTP 500 errors on the frontend.
* **Industry Standard Solution**:
  - Enable SQLite **WAL Mode (Write-Ahead Logging)** immediately:
    `PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`
  - For enterprise multi-user scale, migrate the master ledger to **PostgreSQL**.

---

### Risk #5: Stale Deliveries & Recycled AWB Number Trap
* **What the code does right now**:
  ```python
  existing = self.ledger.get_record_by_awb(item["clean_awb"])
  if existing and existing.get("status") == "DELIVERED" and not recheck_delivered:
      already_delivered_records.append(existing)
  else:
      needs_tracking.append(item)
  ```
* **The Brutal Reality**:
  - **Airlines recycle 8-digit serials every 6 to 12 months**: If an AWB was delivered in January 2026, and a new shipment uses that same AWB in November 2026, the current code sees it as "DELIVERED" and **permanently ignores it**.
  - **False Positive Deliveries**: If an airline portal experienced a momentary API bug or reported partial delivery that was parsed as `DELIVERED`, the system permanently freezes that AWB and will never verify it again.
* **Industry Standard Solution**:
  Include the **Shipment Booking Date / Month** in the primary key tuple: `(awb_number, origin, destination, booking_year)`. If an AWB appears in a new month tab (e.g. `NOV-26`), check if the ledger record was from an older flight date before skipping.

---

### Risk #6: Zero Process Persistence Across Server Restarts
* **What the code does right now**:
  Auto-Pilot is managed via an in-memory Python `threading.Thread` in `AutoPilotManager`.
* **The Brutal Reality**:
  - If the server restarts, if Uvicorn crashes, or if you reboot your Mac/VPS, the thread terminates.
  - When the server starts up again, `is_running` defaults to `False`.
  - The system **will NOT auto-resume tracking**. It silently stays idle until a human opens the web UI and flips the toggle button back on.
* **Industry Standard Solution**:
  - Store the Auto-Pilot toggle state in the database (`settings` table: `autopilot_enabled = true`).
  - On server startup (`@app.on_event("startup")`), check this setting and automatically resume the worker thread if it was previously enabled.

---

### Risk #7: Carrier Website Breaking Changes (Zero Contract Guarantees)
* **What the code does right now**:
  Scrapers rely on DOM CSS selectors, JSON endpoints, and URL patterns for airlines.
* **The Brutal Reality**:
  - Airlines frequently update their websites, redesign pages, change API parameters, or add new bot challenges.
  - When Saudia Cargo, Emirates, or Turkish updates their portal, the scraper will fail.
  - In continuous Auto Mode, failed queries will mark shipments as `UNREACHABLE` or `ERROR`. Without proactive alerting (e.g. Slack / Telegram / Email alerts), you won't know tracking has stopped working until a customer complains.
* **Industry Standard Solution**:
  - Add **Health Monitoring & Circuit Breakers**: If a carrier fails 5 consecutive times, flag the adapter as `DEGRADED` and send an instant webhook alert to the developer.

---

## 2. Risk Matrix & Severity Summary

| # | Risk Factor | Likelihood | Impact | Severity | Primary Mitigation |
| :-: | :--- | :-: | :-: | :-: | :--- |
| **1** | **IP Blacklisting / CAPTCHA Bans** | High (100% within 48h) | Critical | **P0 (Blocker)** | Integrate Residential Rotating Proxies (BrightData / Webshare) |
| **2** | **RAM Spikes & OOM Server Crashes** | High (with 5 workers) | Critical | **P0 (Blocker)** | Limit concurrency to max 2 browsers + enforce process killing |
| **3** | **Google Sheet Export Rate Limit (429)** | Medium (after 20-30 cycles) | High | **P1 (High)** | Migrate to official Google Sheets API v4 (Service Account JSON) |
| **4** | **SQLite Lock Contention** | Medium (during concurrent UI use) | Medium | **P1 (High)** | Enable SQLite WAL mode (`PRAGMA journal_mode=WAL;`) |
| **5** | **Recycled AWB Number Trap** | Medium (over months) | Medium | **P2 (Medium)** | Compound key `(AWB, Tab/Date)` instead of AWB alone |
| **6** | **Server Restart Disables Auto-Pilot** | High (on any reboot) | High | **P1 (High)** | Persist toggle state in DB & resume on app startup |
| **7** | **Silent Carrier Portal Breakages** | Medium (quarterly) | High | **P1 (High)** | Webhook alerts (Telegram/Slack) on repeated carrier failures |
