# Multi-Carrier Air Cargo Tracking System (Production-Ready)

An enterprise-grade, high-performance tracking solution supporting:
- **Emirates SkyCargo (`176`)** (Direct REST APIs & `track-trace.com` headless automation)
- **Lufthansa Cargo (`020`)** (Direct REST APIs & cookie consent automation)
- **Air India Cargo (`098`)** (iCargo Neo GraphQL integration)

Built using dual architectures:
1. **High-Speed Direct REST & GraphQL APIs** (Instant, sub-second responses, guest OAuth caching, zero bot-blocking).
2. **Headless Browser Automation (Playwright)** (Automates `track-trace.com/aircargo` traversal, handles frame warnings, navigates to airline portals, clicks "Tracking Details", and captures full screenshots).

---

## 🌟 Key Features

### ✈ 1. Emirates SkyCargo (`176`) via track-trace.com & Direct REST
- **track-trace.com Automation**:
  - Navigates to `https://www.track-trace.com/aircargo`.
  - Enters AWB number in `Enter number...` input field (e.g. `176-63116340`).
  - Supports **Track direct** first, with seamless fallback to **Track with options**.
  - Handles the frame warning by clicking **"Click here to show Emirates(EK) results without frame"**.
  - Enters Emirates SkyCargo portal, locates shipment order card, and clicks **"Tracking Details"**.
  - Captures full visual screenshots (`emirates_results.png`, `emirates_details.png`).
- **High-Speed Direct Microservices REST API**:
  - Thread-safe guest OAuth token negotiation (`api/uaa/guest/oauth/token`) with in-memory caching.
  - Multi-booking order discovery (`api/order/services/cargo/v1/orders/actions/search`).
  - Order details, routing, and complete milestone event timeline (`api/order/services/cargo/v1/orders/b{BRN}`).
- **Parsed Data Fields**:
  - Origin & Destination (`DEL ➔ MLA`).
  - Product & Commodity: `Emirates Pharma Plus` (`AXD`, `E0101`).
  - Special Handling Codes (`PIL`, `CRT`, `EMD`, `ECC`, `EAP`).
  - Pieces (`11 pcs`), Gross Weight (`1467.0 K`), Chargeable Weight (`2112.0 K`), Volume (`12.672 CM`).
  - Booking Reference Number (`65761815`) and Job Reference Number (`65012126`).
  - Full Flight Routing Itinerary (`EK 0513` DEL ➔ DXB, `EK 0109` DXB ➔ MLA) with scheduled vs. actual departure/arrival times and aircraft registration.
  - Milestones Timeline (`DLV`, `NFD`, `RCF`, `ARR`, `DEP`, `MAN`, `RCS`, `BKD`).

### ✈ 2. Lufthansa Cargo (`020`)
- **AWB Sanitization**: Automatically handles `020-04585280`, `020 04585280`, `02004585280`, or plain 8-digit serial `04585280` (auto-strips `020` for input fields while keeping standard format for reporting).
- **Cookie Consent**: Automatically detects and dismisses the "Cookie Settings" popup by clicking **"Deny"**.
- **Complete AWB Details**:
  - Latest Event (`RCF`, `DEP`, `ARR`, `MAN`, etc.) with flight descriptor.
  - Origin & Destination airports (`DEL ➔ GRU`, `DEL ➔ MUC`).
  - Pieces, Gross Weight (kg), Volume (cbm), Product (`General Cargo - YNZ`), Special Cargo Codes (`SLY`, `SPX`, `HEA`, etc.).
  - Planned vs. Actual availability and acceptance times.
  - Flight segments (scheduled vs. actual departure and arrival times, aircraft type).
  - Chronological Status History (audit trail of all IATA cargo events).

### ✈ 3. Air India Cargo (`098`)
- IBS Software **iCargo Neo** GraphQL integration with automated anonymous session management (`loginAsAnonymousUser`).
- Milestone tracking (`ACCEPTED`, `DEPARTED`, `ARRIVED`, `DELIVERED`).
- Tracking View (Flight routing & split pieces) and Activity View (complete event history with ULD container numbers).

---

## 🚀 Quick Start

### 1. Installation
```bash
pip install -r requirements.txt
playwright install chromium
```

---

### 2. Command-Line Interface (CLI)

#### Track Emirates SkyCargo AWB:
```bash
# Ultra-fast direct tracking (Overview + Itinerary Flights + Milestones)
python3 cli.py 176-63116340

# Execute full live Playwright automation via track-trace.com & save screenshots
python3 cli.py 176-63116340 --browser

# Specific views
python3 cli.py 176-63116340 --view overview
python3 cli.py 176-63116340 --view tracking
python3 cli.py 176-63116340 --view activity

# Raw JSON output
python3 cli.py 176-63116340 --json
```

#### Track Lufthansa Cargo AWB:
```bash
# Direct fast tracking
python3 cli.py 020-04585280

# 8-digit input (020 prefix auto-handled)
python3 cli.py 04676405 --carrier lufthansa

# Run live Playwright browser automation with screenshot capture
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
  - Search any AWB (Emirates SkyCargo, Lufthansa Cargo, or Air India).
  - Click quick-sample buttons (`176-63116340`, `020-04585280`, `04676405`, `098-30244056`).
  - Toggle between Flight Movements and Event Status History.
- **REST API Endpoints**:
  - `GET /api/v1/track/{awb}` (Auto-detects carrier from prefix `176`, `020`, or `098`)
  - `POST /api/v1/track/batch` (Batch track multiple AWBs across carriers)
  - `GET /health` (System health and carrier coverage)
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🧪 Running Tests

```bash
python3 -m unittest discover tests
```
