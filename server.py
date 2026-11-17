"""
Production Multi-Carrier REST API & Interactive Web Dashboard.
Supports Air India Cargo (098), Lufthansa Cargo (020), Emirates SkyCargo (176), and Kuwait Airways (229).
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import re
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import AirIndiaTrackerException, AWBNotFoundException
from lufthansa_tracker.client import LufthansaCargoClient
from emirates_tracker.client import EmiratesTrackerClient, EmiratesShipmentNotFoundError, EmiratesTrackingError
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError, KuwaitTrackingError
from parcels_tracker.client import ParcelsTrackerClient, ParcelsShipmentNotFoundError, ParcelsTrackingError

app = FastAPI(
    title="Multi-Carrier Air Cargo Tracking API",
    description="Industry-level API service for tracking Air India Cargo (098), Lufthansa Cargo (020), Emirates SkyCargo (176), Kuwait Airways (229), and British Airways Cargo (125).",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ai_client = AirIndiaCargoClient()
lh_client = LufthansaCargoClient()
ek_client = EmiratesTrackerClient()
kw_client = KuwaitCargoClient()
parcels_client = ParcelsTrackerClient()


class BatchTrackRequest(BaseModel):
    awbs: List[str]
    carrier: Optional[str] = "auto"


def detect_carrier(awb: str) -> str:
    cleaned = re.sub(r"[\s\-_]+", "", awb.strip())
    if cleaned.startswith("125"):
        return "britishairways"
    if cleaned.startswith("229"):
        return "kuwait"
    if cleaned.startswith("176"):
        return "emirates"
    if cleaned.startswith("020"):
        return "lufthansa"
    if cleaned.startswith("098"):
        return "airindia"
    if len(cleaned) == 8:
        return "kuwait"
    return "airindia"


@app.get("/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "multi-carrier-cargo-tracker",
        "carriers": [
            "Air India (098)",
            "Lufthansa Cargo (020)",
            "Emirates SkyCargo (176)",
            "Kuwait Airways (229)",
            "British Airways Cargo (125)",
        ],
    }


@app.get("/api/v1/track/{awb}", tags=["Tracking"])
def track_shipment(
    awb: str,
    carrier: Optional[str] = Query("auto", description="Carrier: 'auto', 'airindia', 'lufthansa', 'emirates', 'kuwait', or 'britishairways'"),
):
    """
    Track a shipment by AWB number.
    Auto-detects British Airways (125), Kuwait Airways (229), Emirates SkyCargo (176), Lufthansa Cargo (020), or Air India (098).
    """
    target_carrier = carrier if carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "parcels") else detect_carrier(awb)

    try:
        if target_carrier in ("britishairways", "parcels"):
            res = parcels_client.track(awb)
            return {"carrier": "British Airways Cargo", "carrier_code": "125", "data": res.dict()}
        elif target_carrier == "kuwait":
            res = kw_client.track(awb)
            return {"carrier": "Kuwait Airways", "carrier_code": "229", "data": res.dict()}
        elif target_carrier == "emirates":
            res = ek_client.track(awb)
            return {"carrier": "Emirates SkyCargo", "carrier_code": "176", "data": res.dict()}
        elif target_carrier == "lufthansa":
            res = lh_client.track(awb)
            return {"carrier": "Lufthansa Cargo", "carrier_code": "020", "data": res.dict()}
        else:
            res = ai_client.track(awb)
            return {"carrier": "Air India Cargo", "carrier_code": "098", "data": res.dict()}
    except (AWBNotFoundException, EmiratesShipmentNotFoundError, KuwaitShipmentNotFoundError, ParcelsShipmentNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (AirIndiaTrackerException, EmiratesTrackingError, KuwaitTrackingError, ParcelsTrackingError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal tracking error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple AWBs concurrently across multiple carriers."""
    results = {}
    for awb in payload.awbs:
        target = payload.carrier if payload.carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "parcels") else detect_carrier(awb)
        try:
            if target in ("britishairways", "parcels"):
                results[awb] = {"carrier": "British Airways Cargo", "status": "success", "data": parcels_client.track(awb).dict()}
            elif target == "kuwait":
                results[awb] = {"carrier": "Kuwait Airways", "status": "success", "data": kw_client.track(awb).dict()}
            elif target == "emirates":
                results[awb] = {"carrier": "Emirates SkyCargo", "status": "success", "data": ek_client.track(awb).dict()}
            elif target == "lufthansa":
                results[awb] = {"carrier": "Lufthansa Cargo", "status": "success", "data": lh_client.track(awb).dict()}
            else:
                results[awb] = {"carrier": "Air India Cargo", "status": "success", "data": ai_client.track(awb).dict()}
        except Exception as e:
            results[awb] = {"status": "error", "error": str(e)}
    return results


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Interactive Web Dashboard for Multi-Carrier Cargo Tracking."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global Air Cargo Shipment Tracker</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-lh: #05164d;
            --accent-lh: #ffb800;
            --primary-ai: #d71921;
            --primary-ek: #b91c1c;
            --primary-kw: #0f3d6e;
            --accent-kw: #0284c7;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #16a34a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text-main); padding: 2rem 1rem; }
        .container { max-width: 1080px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; }
        .logo-wrap { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .badge-ba { background: #00205b; color: #ffffff; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; border: 1px solid #eb2226; }
        .badge-kw { background: var(--primary-kw); color: #bae6fd; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; border: 1px solid #0284c7; }
        .badge-ek { background: var(--primary-ek); color: #fef08a; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; border: 1px solid #dc2626; }
        .badge-ai { background: var(--primary-ai); color: white; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; }
        .badge-lh { background: var(--primary-lh); color: var(--accent-lh); padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 0.8rem; }
        .title { font-size: 1.35rem; font-weight: 700; color: #1e293b; margin-left: 6px; }
        .search-card { background: var(--card-bg); border-radius: 12px; padding: 1.5rem; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 1.5rem; }
        .form-row { display: flex; gap: 12px; }
        .carrier-select { padding: 0.85rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 0.95rem; font-weight: 600; background: white; outline: none; }
        input[type="text"] { flex: 1; padding: 0.85rem 1rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 1rem; outline: none; }
        input[type="text"]:focus { border-color: #2563eb; }
        button.btn-search { background: #2563eb; color: white; border: none; padding: 0.85rem 1.75rem; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 1rem; transition: opacity 0.2s; }
        button.btn-search:hover { opacity: 0.9; }
        .quick-links { margin-top: 12px; font-size: 0.85rem; color: var(--text-muted); display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .quick-btn { background: #f1f5f9; border: 1px solid var(--border); padding: 4px 10px; border-radius: 6px; cursor: pointer; color: #334155; font-family: monospace; font-size: 0.82rem; }
        .quick-btn:hover { background: #e2e8f0; }
        .result-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); overflow: hidden; display: none; }
        .card-top { padding: 1.25rem 1.75rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .awb-num { font-size: 1.4rem; font-weight: 700; }
        .status-pill { padding: 5px 14px; border-radius: 9999px; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; }
        .banner { padding: 1rem 1.75rem; background: #eff6ff; border-bottom: 1px solid #dbeafe; font-size: 0.95rem; font-weight: 500; color: #1e40af; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; padding: 1.5rem 1.75rem; border-bottom: 1px solid var(--border); }
        .m-lbl { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }
        .m-val { font-size: 1.15rem; font-weight: 700; color: #1e293b; }
        .station-cards-wrap { padding: 1.25rem 1.75rem; background: #f8fafc; border-bottom: 1px solid var(--border); }
        .station-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 1rem; }
        .station-box { background: white; padding: 1rem; border-radius: 8px; border: 1px solid var(--border); }
        .station-title { font-weight: 700; font-size: 1rem; color: #0f3d6e; display: flex; align-items: center; gap: 6px; margin-bottom: 8px; }
        .station-detail { font-size: 0.85rem; margin-bottom: 4px; }
        .tab-bar { display: flex; border-bottom: 1px solid var(--border); background: #ffffff; padding: 0 1.75rem; }
        .tab-item { padding: 1rem 1.25rem; border: none; background: none; font-weight: 600; font-size: 0.95rem; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; }
        .tab-item.active { color: #2563eb; border-bottom-color: #2563eb; }
        .tab-panel { padding: 1.5rem 1.75rem; overflow-x: auto; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
        th { padding: 0.75rem 1rem; background: #f8fafc; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
        td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
        tr:hover { background: #f8fafc; }
        .badge-ev { background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-family: monospace; }
        .badge-latest { background: #dcfce7; color: #15803d; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 0.8rem; }
        .loader { display: none; text-align: center; padding: 2.5rem; font-weight: 600; color: var(--text-muted); font-size: 1.05rem; }
        .error-msg { display: none; background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; font-weight: 500; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-wrap">
                <span class="badge-ba">BRITISH AIRWAYS (125)</span>
                <span class="badge-kw">KUWAIT (229)</span>
                <span class="badge-ek">EMIRATES (176)</span>
                <span class="badge-lh">LUFTHANSA (020)</span>
                <span class="badge-ai">AIR INDIA (098)</span>
                <span class="title">Global Cargo Tracker</span>
            </div>
            <a href="/docs" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 600; font-size: 0.9rem;">Swagger API ↗</a>
        </div>

        <div class="search-card">
            <div class="form-row">
                <select id="carrierSelect" class="carrier-select">
                    <option value="auto">Auto-Detect Carrier</option>
                    <option value="britishairways">British Airways Cargo (125)</option>
                    <option value="kuwait">Kuwait Airways (229)</option>
                    <option value="emirates">Emirates SkyCargo (176)</option>
                    <option value="lufthansa">Lufthansa Cargo (020)</option>
                    <option value="airindia">Air India Cargo (098)</option>
                </select>
                <input type="text" id="awbInput" placeholder="Enter AWB (e.g. 125-24128344, 229-18148900, 176-63116340, 020-04585280, 098-30244056)" value="125-24128344" />
                <button class="btn-search" onclick="trackAWB()">Track Shipment</button>
            </div>
            <div class="quick-links">
                <span>Quick Samples:</span>
                <button class="quick-btn" onclick="setAwb('125-24128344', 'britishairways')">125-24128344 (British Airways)</button>
                <button class="quick-btn" onclick="setAwb('229-18148900', 'kuwait')">229-18148900 (Kuwait Valid)</button>
                <button class="quick-btn" onclick="setAwb('229-17349566', 'kuwait')">229-17349566 (Kuwait Not Found)</button>
                <button class="quick-btn" onclick="setAwb('176-63116340', 'emirates')">176-63116340 (Emirates)</button>
                <button class="quick-btn" onclick="setAwb('020-04585280', 'lufthansa')">020-04585280 (Lufthansa)</button>
                <button class="quick-btn" onclick="setAwb('098-30244056', 'airindia')">098-30244056 (Air India)</button>
            </div>
        </div>

        <div class="error-msg" id="errorBox"></div>
        <div class="loader" id="loader">Fetching tracking details from airline cargo portal...</div>

        <div class="result-card" id="resultCard">
            <div class="card-top" id="cardTop">
                <div>
                    <span id="carrierTag" style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: #64748b; display: block; margin-bottom: 2px;">AIRLINE</span>
                    <div class="awb-num" id="awbDisplay">000-00000000</div>
                </div>
                <div class="status-pill" id="statusPill" style="background: #16a34a; color: white;">STATUS</div>
            </div>

            <div class="banner" id="latestBanner">Latest Event: ...</div>

            <div class="metrics-grid">
                <div>
                    <div class="m-lbl">Origin ➔ Destination</div>
                    <div class="m-val" id="routeDisplay">--- ➔ ---</div>
                </div>
                <div>
                    <div class="m-lbl">Pieces & Weight</div>
                    <div class="m-val" id="pcsWeightDisplay">--- pcs / --- KG</div>
                </div>
                <div>
                    <div class="m-lbl">Volume / Details</div>
                    <div class="m-val" id="volumeDisplay">---</div>
                </div>
                <div>
                    <div class="m-lbl">Commodity / Current Status</div>
                    <div class="m-val" id="productDisplay">---</div>
                </div>
            </div>

            <div class="station-cards-wrap" id="stationCardsWrap" style="display: none;">
                <div style="font-size: 0.85rem; font-weight: 700; text-transform: uppercase; color: #64748b; margin-bottom: 8px;">Transit Station Checkpoints</div>
                <div class="station-grid" id="stationGrid"></div>
            </div>

            <div class="tab-bar">
                <button class="tab-item active" onclick="switchTab('flights')">Flights & Routing</button>
                <button class="tab-item" onclick="switchTab('history')">Milestones & History</button>
            </div>

            <div class="tab-panel" id="panelFlights">
                <table>
                    <thead>
                        <tr>
                            <th>Flight</th>
                            <th>Origin ➔ Destination</th>
                            <th>Date / Departure</th>
                            <th>Arrival / Details</th>
                            <th>Pieces / Weight</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="flightsBody"></tbody>
                </table>
            </div>

            <div class="tab-panel" id="panelHistory" style="display: none;">
                <table>
                    <thead>
                        <tr>
                            <th>Date & Time</th>
                            <th>Code</th>
                            <th>Description</th>
                            <th>Station</th>
                            <th>Flight / Pieces</th>
                            <th>State</th>
                        </tr>
                    </thead>
                    <tbody id="historyBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        function setAwb(awb, carrier) {
            document.getElementById('awbInput').value = awb;
            document.getElementById('carrierSelect').value = carrier;
            trackAWB();
        }

        async function trackAWB() {
            const awb = document.getElementById('awbInput').value.trim();
            const carrier = document.getElementById('carrierSelect').value;
            if (!awb) return;

            const errorBox = document.getElementById('errorBox');
            const loader = document.getElementById('loader');
            const resultCard = document.getElementById('resultCard');
            const stationWrap = document.getElementById('stationCardsWrap');

            errorBox.style.display = 'none';
            resultCard.style.display = 'none';
            stationWrap.style.display = 'none';
            loader.style.display = 'block';

            try {
                const res = await fetch(`/api/v1/track/${encodeURIComponent(awb)}?carrier=${carrier}`);
                const envelope = await res.json();

                if (!res.ok) {
                    throw new Error(envelope.detail || 'Shipment tracking failed');
                }

                const cName = envelope.carrier;
                const data = envelope.data;

                document.getElementById('carrierTag').innerText = cName;
                document.getElementById('awbDisplay').innerText = data.formatted_awb || data.formatted_tracking_number;

                const topBar = document.getElementById('cardTop');

                if (cName.includes('British Airways') || cName.includes('Parcels')) {
                    // British Airways Cargo / ParcelsApp
                    topBar.style.background = '#f0f4f8';
                    document.getElementById('statusPill').style.background = '#00205b';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.latest_status || 'IN TRANSIT';

                    const latLoc = data.overview.latest_location ? ` @ ${data.overview.latest_location}` : '';
                    const latDt = data.overview.latest_date ? ` (${data.overview.latest_date})` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>Latest Event:</strong> ${data.overview.latest_status}${latLoc}${latDt} &bull; <em>${data.overview.primary_carrier}</em>`;

                    const orig = data.overview.origin_location || data.overview.origin_country || 'DEL';
                    const dest = data.overview.destination_location || data.overview.destination_country || 'ATL';
                    document.getElementById('routeDisplay').innerText = `${orig} ➔ ${dest}`;

                    const pkgs = data.overview.pieces || data.overview.number_of_packages || '---';
                    const wt = data.overview.weight || '---';
                    document.getElementById('pcsWeightDisplay').innerText = `${pkgs} pkgs / ${wt}`;

                    const days = data.overview.days_in_transit ? `${data.overview.days_in_transit} days transit` : 'N/A';
                    document.getElementById('volumeDisplay').innerText = days;

                    const couriersList = (data.overview.couriers || []).join(', ') || data.overview.primary_carrier;
                    document.getElementById('productDisplay').innerText = couriersList;

                    // Flights & Routing tab
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    const flightStates = (data.states || []).filter(s => {
                        const stLow = (s.status || '').toLowerCase();
                        return stLow.includes('flight') || stLow.includes('departed') || stLow.includes('arrived') || stLow.includes('booked') || stLow.includes('received');
                    });
                    const displayStates = flightStates.length > 0 ? flightStates : (data.states || []);
                    displayStates.forEach(st => {
                        const isLatest = st.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span class="badge-ev">CONF</span>';
                        fBody.innerHTML += `
                            <tr>
                                <td><strong>${st.carrier_name || 'BA Cargo'}</strong></td>
                                <td>${st.location || '---'}</td>
                                <td>${st.date || 'N/A'}</td>
                                <td>${st.status}</td>
                                <td>${pkgs} pkgs / ${wt}</td>
                                <td>${isLatest}</td>
                            </tr>
                        `;
                    });

                    // History tab
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.states || []).forEach(st => {
                        const badge = st.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Completed</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${st.date || 'N/A'}</td>
                                <td><span class="badge-ev">${st.carrier_name || 'BA'}</span></td>
                                <td>${st.status}</td>
                                <td><strong>${st.location || '---'}</strong></td>
                                <td>${pkgs} pkgs</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Kuwait')) {
                    // Kuwait Airways
                    topBar.style.background = '#f0f9ff';
                    document.getElementById('statusPill').style.background = '#0f3d6e';
                    document.getElementById('statusPill').style.color = '#bae6fd';
                    document.getElementById('statusPill').innerText = data.overview.latest_event_code || 'DELIVERED';

                    document.getElementById('latestBanner').innerHTML = `<strong>Current Status:</strong> ${data.overview.current_status}`;
                    document.getElementById('routeDisplay').innerText = `${data.overview.origin} ➔ ${data.overview.destination}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.gross_weight} ${data.overview.weight_unit}`;
                    document.getElementById('volumeDisplay').innerText = `${data.overview.volume} ${data.overview.volume_unit}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.current_status}`;

                    // Station checkpoint boxes
                    if (data.station_boxes && data.station_boxes.length > 0) {
                        const sGrid = document.getElementById('stationGrid');
                        sGrid.innerHTML = '';
                        data.station_boxes.forEach(b => {
                            sGrid.innerHTML += `
                                <div class="station-box">
                                    <div class="station-title">🏛 Station: ${b.airport}</div>
                                    <div class="station-detail"><span class="badge-ev">${b.status_code_1 || '---'}</span> ${b.event_time_1 || 'N/A'}</div>
                                    <div class="station-detail"><span class="badge-ev">${b.status_code_2 || '---'}</span> ${b.event_time_2 || 'N/A'}</div>
                                    <div class="station-detail" style="color: #64748b; font-size: 0.8rem; margin-top: 4px;">${b.pieces || '---'} pcs / ${b.weight || '---'} KGS</div>
                                </div>
                            `;
                        });
                        stationWrap.style.display = 'block';
                    }

                    // Flights
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flights || []).forEach(fl => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong>${fl.flight_number}</strong></td>
                                <td>${fl.origin} ➔ ${fl.destination}</td>
                                <td>${fl.flight_date || 'N/A'}</td>
                                <td>${fl.volume ? fl.volume + ' CBM' : '---'}</td>
                                <td>${fl.pieces || '---'} pcs / ${fl.weight || '---'} KG</td>
                                <td><span class="badge-ev">${fl.status_message || fl.status_code}</span></td>
                            </tr>
                        `;
                    });

                    // Operational events
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.operational_events || []).forEach((ev, idx) => {
                        const dt = `${ev.event_date || ''} ${ev.event_time || ''}`.strip ? `${ev.event_date || ''} ${ev.event_time || ''}`.trim() : 'N/A';
                        const badge = idx === 0 ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Completed</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${dt}</td>
                                <td><span class="badge-ev">${ev.status_code}</span></td>
                                <td>${ev.status_name} <br><small style="color: #64748b;">${ev.full_details || ''}</small></td>
                                <td><strong>${ev.airport || '---'}</strong></td>
                                <td>${ev.flight_number ? ev.flight_number : (ev.pieces ? ev.pieces + ' pcs' : '---')}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Emirates')) {
                    // Emirates SkyCargo
                    topBar.style.background = '#fef2f2';
                    document.getElementById('statusPill').style.background = '#991b1b';
                    document.getElementById('statusPill').style.color = '#fef08a';
                    document.getElementById('statusPill').innerText = data.overview.latest_milestone_code || 'CONFIRMED';
                    
                    const latestDesc = `${data.overview.latest_milestone_code} - ${data.overview.latest_milestone_description} @ ${data.overview.latest_milestone_station || '---'} (${data.overview.latest_milestone_time || 'N/A'})`;
                    document.getElementById('latestBanner').innerHTML = `<strong>Latest Milestone:</strong> ${latestDesc} &bull; <em>${data.overview.order_status}</em>`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin.code} (${data.overview.origin.name || ''}) ➔ ${data.overview.destination.code} (${data.overview.destination.name || ''})`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.gross_weight} ${data.overview.weight_unit}`;
                    
                    const chgWt = data.overview.chargeable_weight ? ` / ${data.overview.chargeable_weight} ${data.overview.weight_unit}` : '';
                    document.getElementById('volumeDisplay').innerText = `${data.overview.volume} ${data.overview.volume_unit}${chgWt}`;
                    
                    const spCodes = (data.overview.special_handling_codes || []).join(', ');
                    document.getElementById('productDisplay').innerText = `${data.overview.commodity || data.overview.product_name || 'Pharma Plus'} ${spCodes ? '[' + spCodes + ']' : ''}`;

                    // Flights / Itinerary
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.itinerary || []).forEach(leg => {
                        const dep = leg.actual_departure ? `${leg.actual_departure} (Sched: ${leg.scheduled_departure || ''})` : (leg.scheduled_departure || 'N/A');
                        const arr = leg.actual_arrival ? `${leg.actual_arrival} (Sched: ${leg.scheduled_arrival || ''})` : (leg.scheduled_arrival || 'N/A');
                        const ac = [leg.aircraft_type, leg.registration_number ? `Reg: ${leg.registration_number}` : ''].filter(Boolean).join(' | ') || 'Aircraft';
                        fBody.innerHTML += `
                            <tr>
                                <td><strong>${leg.flight_display}</strong></td>
                                <td>${leg.origin.code} ➔ ${leg.destination.code}</td>
                                <td>${dep}</td>
                                <td>${arr}</td>
                                <td>${leg.pieces || '---'} pcs</td>
                                <td><span class="badge-ev">${leg.movement_status || 'CONF'}</span></td>
                            </tr>
                        `;
                    });

                    // Milestones
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.milestones || []).forEach(m => {
                        const pcsWt = [m.pieces ? `${m.pieces} pcs` : '', m.weight ? `${m.weight} ${m.weight_unit}` : ''].filter(Boolean).join(' / ') || '---';
                        const badge = m.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Archived</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${m.timestamp || 'N/A'}</td>
                                <td><span class="badge-ev">${m.code}</span></td>
                                <td>${m.description}</td>
                                <td><strong>${m.station || '---'}</strong></td>
                                <td>${pcsWt}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Lufthansa')) {
                    // Lufthansa Cargo
                    topBar.style.background = '#fffdf0';
                    document.getElementById('statusPill').style.background = '#05164d';
                    document.getElementById('statusPill').style.color = '#ffb800';
                    document.getElementById('statusPill').innerText = data.overview.latest_event;
                    document.getElementById('latestBanner').innerText = data.overview.latest_event_description;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin.code} ➔ ${data.overview.destination.code}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.gross_weight} ${data.overview.weight_unit}`;
                    document.getElementById('volumeDisplay').innerText = `${data.overview.volume} ${data.overview.volume_unit}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.product_name || 'General Cargo'}`;

                    // Flights
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flights || []).forEach(f => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong>${f.flight_number}</strong></td>
                                <td>${f.origin.code} ➔ ${f.destination.code}</td>
                                <td>${f.actual_departure || f.scheduled_departure || 'N/A'}</td>
                                <td>${f.actual_arrival || f.scheduled_arrival || 'N/A'}</td>
                                <td>${f.pieces || '---'} pcs</td>
                                <td><span class="badge-ev">CONF</span></td>
                            </tr>
                        `;
                    });

                    // History
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.status_history || []).forEach(h => {
                        const pcsWt = [h.pieces ? `${h.pieces} pcs` : '', h.weight ? `${h.weight} kg` : ''].filter(Boolean).join(' / ') || '---';
                        const stateBadge = h.is_actual ? '<span class="badge-latest">Actual</span>' : '<span style="color: #64748b;">Planned</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${h.event_time || 'N/A'}</td>
                                <td><span class="badge-ev">${h.event_code}</span></td>
                                <td>${h.event_name}</td>
                                <td>${h.station || '---'}</td>
                                <td>${pcsWt}</td>
                                <td>${stateBadge}</td>
                            </tr>
                        `;
                    });

                } else {
                    // Air India Cargo
                    topBar.style.background = '#fff5f5';
                    document.getElementById('statusPill').style.background = data.overview.overall_status === 'DELIVERED' ? '#16a34a' : '#d97706';
                    document.getElementById('statusPill').style.color = 'white';
                    document.getElementById('statusPill').innerText = data.overview.overall_status;
                    document.getElementById('latestBanner').innerText = `Air India Cargo: ${data.overview.overall_status} | Description: ${data.overview.shipment_description || 'N/A'}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin_airport_code} ➔ ${data.overview.destination_airport_code}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.stated_weight} ${data.overview.weight_unit}`;
                    document.getElementById('volumeDisplay').innerText = `${data.overview.stated_volume} ${data.overview.volume_unit}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.product_name || 'AGC'} (${data.overview.special_handling_code || '---'})`;

                    // Flights
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.tracking_view || []).forEach(s => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong>${s.carrier_code || 'AI'} ${s.flight_number || ''}</strong></td>
                                <td>${s.segment_origin || '---'} ➔ ${s.segment_destination || '---'}</td>
                                <td>${s.departure_date || ''} ${s.departure_time || ''}</td>
                                <td>${s.arrival_date || ''} ${s.arrival_time || ''}</td>
                                <td>${s.pieces || '---'} pcs</td>
                                <td><span class="badge-ev">CONF</span></td>
                            </tr>
                        `;
                    });

                    // History
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.activity_view || []).forEach(ev => {
                        const pcsWt = [ev.pieces !== null ? `${ev.pieces} pcs` : '', ev.weight !== null ? `${ev.weight} ${ev.weight_unit}` : ''].filter(Boolean).join(' / ') || '---';
                        hBody.innerHTML += `
                            <tr>
                                <td>${ev.event_time || ev.last_updated_time || '---'}</td>
                                <td><span class="badge-ev">${ev.event_code}</span></td>
                                <td>${ev.event_name}</td>
                                <td>${ev.airport_code || '---'}</td>
                                <td>${pcsWt}</td>
                                <td><span class="badge-latest">Recorded</span></td>
                            </tr>
                        `;
                    });
                }

                resultCard.style.display = 'block';
            } catch (err) {
                errorBox.innerText = err.message;
                errorBox.style.display = 'block';
            } finally {
                loader.style.display = 'none';
            }
        }

        function switchTab(tab) {
            const tabs = document.querySelectorAll('.tab-item');
            tabs.forEach(t => t.classList.remove('active'));

            if (tab === 'flights') {
                tabs[0].classList.add('active');
                document.getElementById('panelFlights').style.display = 'block';
                document.getElementById('panelHistory').style.display = 'none';
            } else {
                tabs[1].classList.add('active');
                document.getElementById('panelFlights').style.display = 'none';
                document.getElementById('panelHistory').style.display = 'block';
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            trackAWB();
        });
    </script>
</body>
</html>
    """


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
