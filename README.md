# Air India Cargo Tracking Solution (Industry-Grade)

An enterprise-ready, high-performance Air India Cargo shipment tracking engine and microservice. Built by reverse-engineering the IBS Software iCargo Neo GraphQL API used by the Air India Cargo Portal (`aicargoportal.airindia.com`), eliminating brittle DOM web scraping, slow headless browsers, and UI selector breakage.

---

## 🚀 Key Highlights & Capabilities

1. **Direct iCargo Neo GraphQL API Integration**:
   - Zero headless browser overhead (100x faster, ~1-2 seconds per request).
   - Automated anonymous session authentication (`loginAsAnonymousUser` mutation) with token lifecycle and auto-refresh on expiration.
2. **Dual-View Support (Exact Match with Portal Screenshots)**:
   - **Overview & Milestones**: Overall status (e.g. `DELIVERED`, `IN_TRANSIT`), route (`DEL ➔ YYZ`), pieces, gross weight, volume, special handling codes (`CSL`), commodity description (`CONSOLIDATION`).
   - **Tracking View**: Flight segments, flight numbers (`AI 0187`), departure/arrival schedules, and piece breakdown per leg.
   - **Activity View**: Complete chronological audit trail with standard IATA event codes (`RCS`, `BKD`, `MAN`, `DEP`, `ARR`, `RCF` with ULD container numbers like `AKE25039R9`, `NFD`, `DLV`), timestamps, and station codes.
3. **Flexible AWB Number Normalization**:
   - Supports: `098-30244056`, `098 30244056`, `09830244056`, or plain 8-digit serial `30244056` (automatically prefixes Air India airline code `098`).
4. **Multiple Interfaces**:
   - **CLI Tool** (`cli.py`): Beautiful colored tables, progress indicators, and JSON export.
   - **Python SDK** (`airindia_tracker`): Easy to import and embed into your own scripts or workflows.
   - **FastAPI Production Microservice** (`server.py`): REST API with auto-generated Swagger documentation and an interactive web UI.

---

## 📁 Project Architecture

```
tracking/
├── airindia_tracker/          # Core Python SDK
│   ├── __init__.py
│   ├── client.py              # AirIndiaCargoClient (GraphQL session, token refresh, queries)
│   ├── models.py              # Pydantic schemas (Overview, FlightSegment, ActivityEvent, TrackingResult)
│   ├── constants.py           # IATA cargo event mappings and endpoints
│   └── exceptions.py          # Custom exceptions
├── cli.py                     # Rich terminal CLI
├── server.py                  # FastAPI REST Server + Web Dashboard
├── requirements.txt           # Dependencies
├── tests/
│   └── test_tracker.py        # Automated test suite
└── README.md
```

---

## 🛠 Installation

```bash
pip install -r requirements.txt
```

---

## 💻 Usage

### 1. Command-Line Interface (CLI)

#### Full Track (Overview + Tracking View + Activity View):
```bash
python3 cli.py 098-30244056
```

#### View Specific Sections:
```bash
# Only Overview
python3 cli.py 098-30244056 --view overview

# Only Tracking View (Flight Segments)
python3 cli.py 098-30244056 --view tracking

# Only Activity View (Event Audit Trail)
python3 cli.py 098-30244056 --view activity
```

#### Export to JSON:
```bash
python3 cli.py 098-30244056 --json
```

---

### 2. Python SDK

```python
from airindia_tracker import AirIndiaCargoClient

client = AirIndiaCargoClient()

# Track single shipment
result = client.track("098-30244056")

print("AWB:", result.formatted_awb)
print("Status:", result.overview.overall_status)
print("Route:", result.overview.origin_airport_code, "->", result.overview.destination_airport_code)
print("Pieces:", result.overview.pieces, "Weight:", result.overview.stated_weight, result.overview.weight_unit)

# Tracking View (Flight Legs)
for leg in result.tracking_view:
    print(f"Flight: {leg.carrier_code} {leg.flight_number} | {leg.segment_origin} -> {leg.segment_destination} | Pieces: {leg.pieces}")

# Activity View (Events)
for event in result.activity_view:
    print(f"[{event.event_time}] {event.event_code} - {event.event_name} @ {event.airport_code}")
```

---

### 3. REST API & Web Dashboard

Start the FastAPI server:
```bash
python3 server.py
# Or: uvicorn server:app --host 0.0.0.0 --port 8000
```

- **Interactive Web UI**: Open `http://localhost:8000/` in your browser.
- **Swagger API Docs**: Open `http://localhost:8000/docs`.
- **API Endpoint**:
  ```bash
  curl http://localhost:8000/api/v1/track/098-30244056
  ```

#### Batch API Endpoint:
```bash
curl -X POST http://localhost:8000/api/v1/track/batch \
  -H "Content-Type: application/json" \
  -d '{"awbs": ["098-30244056"]}'
```

---

## 🧪 Running Tests

```bash
python3 -m unittest discover tests
```
