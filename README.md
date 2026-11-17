# Multi-Carrier Air Cargo Tracking System (Production-Ready)

An enterprise-grade, high-performance tracking solution supporting:
- **British Airways Cargo (`125`)** (`parcelsapp.com` stealth Playwright automation with anti-bot bypass)
- **Kuwait Airways (`229`)** (Direct REST APIs & live portal Playwright automation)
- **Emirates SkyCargo (`176`)** (Direct REST APIs & `track-trace.com` headless automation)
- **Lufthansa Cargo (`020`)** (Direct REST APIs & cookie consent automation)
- **Air India Cargo (`098`)** (iCargo Neo GraphQL integration)

Built using dual architectures:
1. **High-Speed Direct REST & GraphQL APIs** (Instant, sub-second responses, guest OAuth caching, zero bot-blocking).
2. **Headless Browser Automation (Playwright)** (Automates cookie banners, form submission, anti-bot stealth WebGL spoofing, error detection, and full page visual screenshots).

---

## 🌟 Key Features

### ✈ 1. British Airways Cargo (`125`) via ParcelsApp Automation
- **ParcelsApp Tracking Workflow**:
  - Live portal: `https://parcelsapp.com/en/tracking`.
  - Enters 11-digit AWB number (e.g. `125-24128344`) in the placeholder input field.
  - Clicks **"TRACK PACKAGE"** and captures results dynamically.
- **Advanced Bot-Detection & Anti-Fingerprinting Stealth**:
  - Automatically overrides `navigator.webdriver` to prevent detection.
  - Spoofs WebGL vendor and renderer strings (`Intel Inc.` / `Intel(R) Iris(TM) Plus Graphics 655`) to defeat SwiftShader fingerprinting.
  - Intercepts backend states JSON payload directly from the active session for 100% data fidelity.
- **Complete Extracted Details (e.g. `125-24128344`)**:
  - **Route**: `DEL, Indira Gandhi Intl, Delhi` ➔ `Hartsfield Jackson Atlanta Intl (ATL), United States`.
  - **Metrics**: 65 packages / pieces, 1,103.00 kg gross weight, 6 days in transit.
  - **Carriers**: British Airways Cargo + WFS Cargo (Worldwide Flight Services).
  - **Latest Status**: `Received on flight. Flight BA223 @ Nashville Intl (BNA), Nashville, United States`.
  - **18 Chronological Milestone & Flight Events** (LHR, BNA, ATL, DEL) including departures, arrivals, bookings, and discrepancy updates.

### ✈ 2. Kuwait Airways Cargo (`229`)
- **Portal & API Integration**:
  - Live portal: `https://www.kuwaitairways.com/en/cargo/tracking`.
  - High-speed direct REST API: `https://services.kuwaitairways.com/cargo/api/GetCargoInfo/229/{serial}/en`.
- **AWB Sanitization & Prefix Handling**:
  - Automatically handles `229-18148900`, `229 18148900`, `22918148900`, or raw 8-digit serial `18148900` (auto-extracts the last 8 digits serial for input into `#txtAwbNo` where `229` prefix is fixed).
- **Graceful Error Handling & Bot Resilience**:
  - Intercepts and parses `-1` response code cleanly as `KuwaitShipmentNotFoundError` (e.g. for `229-17349566`: `"Could not find AWB 229-17349566. Please check your request and try again."`).
- **Complete AWB Details**:
  - Route (`BOM ➔ LHR`).
  - Pieces (`2 pcs`), Weight (`1180.0 KGS`), Volume (`1.68 CBM`).
  - Current Status: `Delivered 1180.0 Kgs on 14-NOV-26 04:59`.
  - Transit Station Checkpoints (`BOM`, `KWI`, `LHR`) with check-in intake and departure/delivery timestamps.
  - Flight segments (`KU304` BOM ➔ KWI, `KU101` KWI ➔ LHR).
  - Chronological Operational Status Events (`DLV`, `NFD`, `RCF`, `ARR`, `DEP`, `MAN`, `PRE`, `RCS`).

### ✈ 2. Emirates SkyCargo (`176`) via track-trace.com & Direct REST
- **track-trace.com Automation**:
  - Navigates to `https://www.track-trace.com/aircargo`.
  - Enters AWB in `Enter number...` input field.
  - Supports **Track direct** first, with fallback to **Track with options**.
  - Clicks **"Click here to show Emirates(EK) results without frame"**.
  - Clicks **"Tracking Details"** and captures visual screenshots.
- **High-Speed Direct Microservices REST API**:
  - Thread-safe guest OAuth token negotiation (`api/uaa/guest/oauth/token`).
  - Multi-booking order discovery and milestone details.

### ✈ 3. Lufthansa Cargo (`020`)
- **AWB Sanitization**: Automatically handles `020-04585280` or `04585280`.
- **Cookie Consent**: Automatically detects and dismisses the "Cookie Settings" popup by clicking **"Deny"**.
- **Complete AWB Details**: Flight segments, milestones, acceptance times, and status audit trail.

### ✈ 4. Air India Cargo (`098`)
- IBS Software **iCargo Neo** GraphQL integration with anonymous session management.
- Tracking View and Activity View with ULD container numbers.

---

## 🚀 Quick Start

### 1. Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

---

### 2. Command-Line Interface (CLI)

#### Track British Airways Cargo AWB (via ParcelsApp):
```bash
# Auto-detect carrier by prefix 125
python3 cli.py 125-24128344

# Capture full page visual screenshot
python3 cli.py 125-24128344 --browser
```

#### Track Kuwait Airways AWB:
```bash
# Direct fast tracking (Overview + Station Checkpoints + Flights + Milestones)
python3 cli.py 229-18148900

# 8-digit input (229 prefix auto-handled)
python3 cli.py 18148900 --carrier kuwait

# Run live Playwright browser automation with screenshot capture
python3 cli.py 229-18148900 --browser

# Test non-existent AWB error handling
python3 cli.py 229-17349566
```

#### Track Emirates SkyCargo AWB:
```bash
python3 cli.py 176-63116340
python3 cli.py 176-63116340 --browser
```

#### Track Lufthansa Cargo AWB:
```bash
python3 cli.py 020-04585280
python3 cli.py 020-04585280 --browser
```

#### Track Air India Cargo AWB:
```bash
python3 cli.py 098-30244056
```

---

### 3. REST API & Web Dashboard

Start the server:
```bash
python3 server.py
```

- **Interactive Web Dashboard**: Open `http://localhost:8000/` in your browser.
  - Quick-sample buttons for British Airways (`125-24128344`), Kuwait Airways (`229-18148900`, `229-17349566`), Emirates (`176-63116340`), Lufthansa (`020-04585280`), and Air India (`098-30244056`).
  - Real-time status pills, route map overview, package weights, flight legs, and timeline milestone events.
- **REST API Endpoints**:
  - `GET /api/v1/track/{awb}` (Auto-detects carrier from prefix `125`, `229`, `176`, `020`, or `098`)
  - `POST /api/v1/track/batch` (Batch track multiple AWBs across carriers)
  - `GET /health` (System health and carrier coverage for all 5 airlines)
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🧪 Running Tests

```bash
python3 -m unittest discover tests
```
