"""
Production Multi-Carrier REST API & Interactive Web Dashboard.
Supports Air India Cargo (098) and Lufthansa Cargo (020).
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

app = FastAPI(
    title="Multi-Carrier Air Cargo Tracking API",
    description="Industry-level API service for tracking Air India Cargo (098) and Lufthansa Cargo (020).",
    version="2.0.0",
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


class BatchTrackRequest(BaseModel):
    awbs: List[str]
    carrier: Optional[str] = "auto"


def detect_carrier(awb: str) -> str:
    cleaned = re.sub(r"[\s\-_]+", "", awb.strip())
    if cleaned.startswith("020"):
        return "lufthansa"
    if cleaned.startswith("098"):
        return "airindia"
    if len(cleaned) == 8:
        return "lufthansa"  # If 8 digits passed without prefix, can default or specify
    return "airindia"


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy", "service": "multi-carrier-cargo-tracker", "carriers": ["Air India (098)", "Lufthansa Cargo (020)"]}


@app.get("/api/v1/track/{awb}", tags=["Tracking"])
def track_shipment(awb: str, carrier: Optional[str] = Query("auto", description="Carrier: 'auto', 'airindia', or 'lufthansa'")):
    """
    Track a shipment by AWB number.
    Auto-detects Air India (098-XXXXXXXX) or Lufthansa Cargo (020-XXXXXXXX).
    """
    target_carrier = carrier if carrier in ("airindia", "lufthansa") else detect_carrier(awb)

    try:
        if target_carrier == "lufthansa":
            res = lh_client.track(awb)
            return {"carrier": "Lufthansa Cargo", "carrier_code": "020", "data": res.dict()}
        else:
            res = ai_client.track(awb)
            return {"carrier": "Air India Cargo", "carrier_code": "098", "data": res.dict()}
    except (AWBNotFoundException, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AirIndiaTrackerException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal tracking error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple AWBs concurrently."""
    results = {}
    for awb in payload.awbs:
        target = payload.carrier if payload.carrier in ("airindia", "lufthansa") else detect_carrier(awb)
        try:
            if target == "lufthansa":
                results[awb] = {"carrier": "Lufthansa Cargo", "status": "success", "data": lh_client.track(awb).dict()}
            else:
                results[awb] = {"carrier": "Air India Cargo", "status": "success", "data": ai_client.track(awb).dict()}
        except Exception as e:
            results[awb] = {"status": "error", "error": str(e)}
    return results


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Interactive Web Dashboard for Air India & Lufthansa Cargo."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global Cargo Shipment Tracker</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary-lh: #05164d;
            --accent-lh: #ffb800;
            --primary-ai: #d71921;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #16a34a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text-main); padding: 2rem 1rem; }
        .container { max-width: 1050px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; }
        .logo-wrap { display: flex; align-items: center; gap: 12px; }
        .badge-ai { background: var(--primary-ai); color: white; padding: 5px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; }
        .badge-lh { background: var(--primary-lh); color: var(--accent-lh); padding: 5px 10px; border-radius: 6px; font-weight: 700; font-size: 0.85rem; }
        .title { font-size: 1.3rem; font-weight: 700; color: #1e293b; }
        .search-card { background: var(--card-bg); border-radius: 12px; padding: 1.5rem; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 1.5rem; }
        .form-row { display: flex; gap: 12px; }
        .carrier-select { padding: 0.85rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 0.95rem; font-weight: 600; background: white; outline: none; }
        input[type="text"] { flex: 1; padding: 0.85rem 1rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 1rem; outline: none; }
        input[type="text"]:focus { border-color: #2563eb; }
        button.btn-search { background: #2563eb; color: white; border: none; padding: 0.85rem 1.75rem; border-radius: 8px; font-weight: 600; cursor: pointer; font-size: 1rem; transition: opacity 0.2s; }
        button.btn-search:hover { opacity: 0.9; }
        .quick-links { margin-top: 10px; font-size: 0.85rem; color: var(--text-muted); display: flex; gap: 10px; align-items: center; }
        .quick-btn { background: #f1f5f9; border: 1px solid var(--border); padding: 3px 8px; border-radius: 4px; cursor: pointer; color: #334155; font-family: monospace; }
        .quick-btn:hover { background: #e2e8f0; }
        .result-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); overflow: hidden; display: none; }
        .card-top { padding: 1.25rem 1.75rem; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); }
        .awb-num { font-size: 1.35rem; font-weight: 700; }
        .status-pill { padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
        .banner { padding: 1rem 1.75rem; background: #eff6ff; border-bottom: 1px solid #dbeafe; font-size: 0.95rem; font-weight: 500; color: #1e40af; }
        .metrics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; padding: 1.5rem 1.75rem; border-bottom: 1px solid var(--border); }
        .m-lbl { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; font-weight: 600; margin-bottom: 4px; }
        .m-val { font-size: 1.15rem; font-weight: 700; color: #1e293b; }
        .tab-bar { display: flex; border-bottom: 1px solid var(--border); background: #ffffff; padding: 0 1.75rem; }
        .tab-item { padding: 1rem 1.25rem; border: none; background: none; font-weight: 600; font-size: 0.95rem; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; }
        .tab-item.active { color: #2563eb; border-bottom-color: #2563eb; }
        .tab-panel { padding: 1.5rem 1.75rem; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
        th { padding: 0.75rem 1rem; background: #f8fafc; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
        td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
        tr:hover { background: #f8fafc; }
        .badge-ev { background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-family: monospace; }
        .loader { display: none; text-align: center; padding: 2rem; font-weight: 600; color: var(--text-muted); }
        .error-msg { display: none; background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-wrap">
                <span class="badge-ai">AIR INDIA (098)</span>
                <span class="badge-lh">LUFTHANSA (020)</span>
                <span class="title">Cargo Shipment Tracker</span>
            </div>
            <a href="/docs" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 600; font-size: 0.9rem;">Swagger API ↗</a>
        </div>

        <div class="search-card">
            <div class="form-row">
                <select id="carrierSelect" class="carrier-select">
                    <option value="auto">Auto-Detect Carrier</option>
                    <option value="lufthansa">Lufthansa Cargo (020)</option>
                    <option value="airindia">Air India Cargo (098)</option>
                </select>
                <input type="text" id="awbInput" placeholder="Enter AWB Number (e.g. 020-04585280, 04676405, 098-30244056)" value="020-04585280" />
                <button class="btn-search" onclick="trackAWB()">Track Shipment</button>
            </div>
            <div class="quick-links">
                <span>Sample AWBs:</span>
                <button class="quick-btn" onclick="setAwb('020-04585280', 'lufthansa')">020-04585280 (Lufthansa)</button>
                <button class="quick-btn" onclick="setAwb('04676405', 'lufthansa')">04676405 (Lufthansa 8-digit)</button>
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
                    <div class="m-lbl">Volume</div>
                    <div class="m-val" id="volumeDisplay">--- CBM</div>
                </div>
                <div>
                    <div class="m-lbl">Product / Details</div>
                    <div class="m-val" id="productDisplay">---</div>
                </div>
            </div>

            <div class="tab-bar">
                <button class="tab-item active" onclick="switchTab('flights')">Flights & Routing</button>
                <button class="tab-item" onclick="switchTab('history')">Status History (Events)</button>
            </div>

            <div class="tab-panel" id="panelFlights">
                <table>
                    <thead>
                        <tr>
                            <th>Flight</th>
                            <th>Origin ➔ Destination</th>
                            <th>Departure Time</th>
                            <th>Arrival Time</th>
                            <th>Pieces / Type</th>
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
                            <th>Pieces / Weight</th>
                            <th>Flight</th>
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

            errorBox.style.display = 'none';
            resultCard.style.display = 'none';
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
                document.getElementById('awbDisplay').innerText = data.formatted_awb;

                // Airline-specific styling
                const topBar = document.getElementById('cardTop');
                if (cName.includes('Lufthansa')) {
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
                                <td>${f.aircraft_type || 'Aircraft'}</td>
                            </tr>
                        `;
                    });

                    // History
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.status_history || []).forEach(h => {
                        const pcsWt = [h.pieces ? `${h.pieces} pcs` : '', h.weight ? `${h.weight} kg` : ''].filter(Boolean).join(' / ') || '---';
                        const stateBadge = h.is_actual ? '<span style="color: #16a34a; font-weight: 600;">Actual</span>' : '<span style="color: #64748b;">Planned</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${h.event_time || 'N/A'}</td>
                                <td><span class="badge-ev">${h.event_code}</span></td>
                                <td>${h.event_name}</td>
                                <td>${h.station || '---'}</td>
                                <td>${pcsWt}</td>
                                <td>${h.flight_number || '---'}</td>
                                <td>${stateBadge}</td>
                            </tr>
                        `;
                    });

                } else {
                    // Air India
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
                            </tr>
                        `;
                    });

                    // History
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.activity_view || []).forEach(ev => {
                        const pcsWt = [ev.pieces !== null ? `${ev.pieces} pcs` : '', ev.weight !== null ? `${ev.weight} ${ev.weight_unit}` : ''].filter(Boolean).join(' / ') || '---';
                        const flUld = [ev.flight_number ? `${ev.flight_carrier_code || 'AI'} ${ev.flight_number}` : '', ev.uld_number ? `ULD: ${ev.uld_number}` : ''].filter(Boolean).join(' | ') || '---';
                        hBody.innerHTML += `
                            <tr>
                                <td>${ev.event_time || ev.last_updated_time || '---'}</td>
                                <td><span class="badge-ev">${ev.event_code}</span></td>
                                <td>${ev.event_name}</td>
                                <td>${ev.airport_code || '---'}</td>
                                <td>${pcsWt}</td>
                                <td>${flUld}</td>
                                <td><span style="color: #16a34a; font-weight: 600;">Recorded</span></td>
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
