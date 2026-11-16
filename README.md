# Multi-Carrier Air Cargo Tracking System (Production-Ready)

An enterprise-grade, high-performance tracking solution supporting **Air India Cargo (`098`)** and **Lufthansa Cargo (`020`)**.

Built using dual architectures:
1. **High-Speed Direct REST & GraphQL APIs** (Instant, sub-second responses, zero bot-blocking).
2. **Headless Browser Automation (Playwright)** (Automates cookie consent "Deny", AWB entry, search submission, and visual screenshots).

---

## 🌟 Key Features

### ✈ 1. Lufthansa Cargo (`020`)
- **AWB Sanitization**: Automatically handles `020-04585280`, `020 04585280`, `02004585280`, or plain 8-digit serial `04585280` (auto-strips `020` for input fields while keeping standard format for reporting).
- **Cookie Consent**: Automatically detects and dismisses the "Cookie Settings" popup by clicking **"Deny"**.
- **Complete AWB Details**:
  - Latest Event (`RCF`, `DEP`, `ARR`, etc.) with flight descriptor (e.g. `AZ769 DEL - FCO`).
  - Origin & Destination airports (`DEL ➔ GRU`, `DEL ➔ MUC`).
  - Pieces, Gross Weight (kg), Volume (cbm), Product (`General Cargo - YNZ`), Special Cargo Codes (`SLY`, `SPX`, `HEA`, etc.).
  - Planned vs. Actual availability and acceptance times.
  - Flight segments (scheduled vs. actual departure and arrival times, aircraft type).
  - Chronological Status History (audit trail of all IATA cargo events).
  - Confirmed Booking details.

### ✈ 2. Air India Cargo (`098`)
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

#### Track Lufthansa Cargo AWB:
```bash
# Direct fast tracking (Overview + Flights + Status History)
python3 cli.py 020-04585280

# 8-digit input (020 prefix auto-handled)
python3 cli.py 04676405 --carrier lufthansa

# Run live Playwright browser automation with screenshot capture
python3 cli.py 020-04585280 --browser

# Specific views
python3 cli.py 020-04585280 --view overview
python3 cli.py 020-04585280 --view tracking
python3 cli.py 020-04585280 --view activity

# Raw JSON output
python3 cli.py 020-04585280 --json
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
  - Search any AWB (Air India or Lufthansa).
  - Click quick-sample buttons.
  - Toggle between Flight Movements and Event Status History.
- **REST API Endpoints**:
  - `GET /api/v1/track/{awb}` (Auto-detects carrier from prefix `020` or `098`)
  - `POST /api/v1/track/batch` (Batch track multiple AWBs)
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🧪 Running Tests

```bash
python3 -m unittest discover tests
```
