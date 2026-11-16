"""
FastAPI Production REST API & Web Dashboard for Air India Cargo Tracking.
Includes OpenAPI/Swagger docs, JSON endpoints, batch tracking, and interactive web UI.
"""

import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from typing import List
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.models import TrackingResult
from airindia_tracker.exceptions import AirIndiaTrackerException, AWBNotFoundException

app = FastAPI(
    title="Air India Cargo Tracking API",
    description="Industry-level API service for tracking Air India Cargo (iCargo Neo) shipments.",
    version="1.0.0",
)

# Enable CORS for cross-origin integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = AirIndiaCargoClient()


class BatchTrackRequest(BaseModel):
    awbs: List[str]


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "air-india-cargo-tracker"}


@app.get("/api/v1/track/{awb}", response_model=TrackingResult, tags=["Tracking"])
def track_shipment(awb: str):
    """
    Track a single Air India Cargo shipment by AWB number.
    Accepts formats: '098-30244056', '09830244056', '30244056'.
    Returns overview, tracking_view (flight legs), and activity_view (audit events).
    """
    try:
        return client.track(awb)
    except AWBNotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AirIndiaTrackerException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple Air India Cargo AWBs concurrently."""
    return client.track_batch(payload.awbs)


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Interactive Web Dashboard with Tracking View and Activity View."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Air India Cargo Shipment Tracker</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #d71921;
            --primary-hover: #b8141b;
            --bg: #f8fafc;
            --card-bg: #ffffff;
            --text-main: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #16a34a;
            --warning: #f59e0b;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
        body { background: var(--bg); color: var(--text-main); padding: 2rem 1rem; }
        .container { max-width: 1000px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 2rem; }
        .logo { display: flex; align-items: center; gap: 12px; }
        .logo-badge { background: var(--primary); color: white; padding: 6px 12px; border-radius: 6px; font-weight: 700; font-size: 1.1rem; letter-spacing: 1px; }
        .logo-title { font-size: 1.3rem; font-weight: 700; color: #1e293b; }
        .search-card { background: var(--card-bg); border-radius: 12px; padding: 1.75rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid var(--border); margin-bottom: 1.5rem; }
        .search-form { display: flex; gap: 12px; }
        .input-group { flex: 1; }
        input[type="text"] { width: 100%; padding: 0.85rem 1rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 1rem; outline: none; transition: border-color 0.2s; }
        input[type="text"]:focus { border-color: var(--primary); }
        button.btn-primary { background: var(--primary); color: white; border: none; padding: 0.85rem 1.75rem; border-radius: 8px; font-weight: 600; cursor: pointer; transition: background 0.2s; font-size: 1rem; }
        button.btn-primary:hover { background: var(--primary-hover); }
        .result-card { background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); overflow: hidden; display: none; }
        .shipment-header { background: #fff5f5; border-bottom: 1px solid #fee2e2; padding: 1.25rem 1.75rem; display: flex; justify-content: space-between; align-items: center; }
        .awb-badge { font-size: 1.3rem; font-weight: 700; color: var(--primary); }
        .status-badge { background: var(--success); color: white; padding: 4px 12px; border-radius: 9999px; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; padding: 1.5rem 1.75rem; border-bottom: 1px solid var(--border); }
        .stat-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-bottom: 4px; font-weight: 600; }
        .stat-value { font-size: 1.1rem; font-weight: 700; color: #1e293b; }
        .milestones-bar { display: flex; padding: 1.5rem 1.75rem; border-bottom: 1px solid var(--border); background: #fafafa; gap: 1rem; }
        .m-step { flex: 1; text-align: center; position: relative; }
        .m-circle { width: 34px; height: 34px; border-radius: 50%; margin: 0 auto 8px; display: flex; align-items: center; justify-content: center; font-size: 0.9rem; font-weight: 700; }
        .m-done .m-circle { background: #dcfce7; color: var(--success); border: 2px solid var(--success); }
        .m-pending .m-circle { background: #f1f5f9; color: var(--text-muted); border: 2px solid var(--border); }
        .m-name { font-size: 0.8rem; font-weight: 600; color: #334155; }
        .tab-nav { display: flex; border-bottom: 1px solid var(--border); background: #ffffff; padding: 0 1.75rem; }
        .tab-btn { padding: 1rem 1.5rem; border: none; background: none; font-weight: 600; font-size: 0.95rem; color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; }
        .tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }
        .tab-content { padding: 1.75rem; }
        table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
        th { padding: 0.75rem 1rem; background: #f8fafc; color: var(--text-muted); font-weight: 600; border-bottom: 1px solid var(--border); }
        td { padding: 0.75rem 1rem; border-bottom: 1px solid var(--border); }
        tr:hover { background: #f8fafc; }
        .badge-event { background: #eff6ff; color: #2563eb; padding: 2px 8px; border-radius: 4px; font-weight: 600; font-family: monospace; }
        .loader { display: none; text-align: center; padding: 2rem; font-weight: 600; color: var(--text-muted); }
        .error-msg { display: none; background: #fef2f2; border: 1px solid #fecaca; color: #991b1b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo">
                <span class="logo-badge">AIR INDIA</span>
                <span class="logo-title">Cargo Shipment Tracking Portal</span>
            </div>
            <a href="/docs" target="_blank" style="color: var(--primary); text-decoration: none; font-weight: 600; font-size: 0.9rem;">API Documentation (Swagger) ↗</a>
        </div>

        <div class="search-card">
            <div class="search-form">
                <div class="input-group">
                    <input type="text" id="awbInput" placeholder="Enter AWB Number (e.g. 098-30244056)" value="098-30244056" />
                </div>
                <button class="btn-primary" onclick="trackAWB()">Track Shipment</button>
            </div>
        </div>

        <div class="error-msg" id="errorBox"></div>
        <div class="loader" id="loader">Fetching tracking details from Air India iCargo Portal...</div>

        <div class="result-card" id="resultCard">
            <div class="shipment-header">
                <div class="awb-badge" id="awbDisplay">098-00000000</div>
                <div class="status-badge" id="statusBadge">STATUS</div>
            </div>

            <div class="summary-grid">
                <div>
                    <div class="stat-label">Routing</div>
                    <div class="stat-value" id="routeDisplay">DEL ➔ YYZ</div>
                </div>
                <div>
                    <div class="stat-label">Pieces / Weight</div>
                    <div class="stat-value" id="pcsWeightDisplay">43 pcs / 271 KG</div>
                </div>
                <div>
                    <div class="stat-label">Volume</div>
                    <div class="stat-value" id="volDisplay">2.31 CBM</div>
                </div>
                <div>
                    <div class="stat-label">Description / Code</div>
                    <div class="stat-value" id="descDisplay">CONSOLIDATION (CSL)</div>
                </div>
            </div>

            <div class="milestones-bar" id="milestonesBar"></div>

            <div class="tab-nav">
                <button class="tab-btn active" onclick="switchTab('tracking')">Tracking View (Flight Segments)</button>
                <button class="tab-btn" onclick="switchTab('activity')">Activity View (Event Timeline)</button>
            </div>

            <div class="tab-content" id="tabTracking">
                <table>
                    <thead>
                        <tr>
                            <th>Flight</th>
                            <th>Origin ➔ Destination</th>
                            <th>Departure Time</th>
                            <th>Arrival Time</th>
                            <th>Pieces</th>
                        </tr>
                    </thead>
                    <tbody id="trackingTableBody"></tbody>
                </table>
            </div>

            <div class="tab-content" id="tabActivity" style="display: none;">
                <table>
                    <thead>
                        <tr>
                            <th>Date & Time</th>
                            <th>Code</th>
                            <th>Event Description</th>
                            <th>Station</th>
                            <th>Pieces / Weight</th>
                            <th>Flight / ULD</th>
                        </tr>
                    </thead>
                    <tbody id="activityTableBody"></tbody>
                </table>
            </div>
        </div>
    </div>

    <script>
        async function trackAWB() {
            const awb = document.getElementById('awbInput').value.trim();
            if (!awb) return;

            const errorBox = document.getElementById('errorBox');
            const loader = document.getElementById('loader');
            const resultCard = document.getElementById('resultCard');

            errorBox.style.display = 'none';
            resultCard.style.display = 'none';
            loader.style.display = 'block';

            try {
                const res = await fetch(`/api/v1/track/${encodeURIComponent(awb)}`);
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.detail || 'Failed to fetch shipment details');
                }

                // Render Overview
                document.getElementById('awbDisplay').innerText = data.formatted_awb;
                document.getElementById('statusBadge').innerText = data.overview.overall_status;
                document.getElementById('routeDisplay').innerText = `${data.overview.origin_airport_code} ➔ ${data.overview.destination_airport_code}`;
                document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.stated_weight} ${data.overview.weight_unit}`;
                document.getElementById('volDisplay').innerText = `${data.overview.stated_volume} ${data.overview.volume_unit}`;
                document.getElementById('descDisplay').innerText = `${data.overview.shipment_description || 'General'} (${data.overview.special_handling_code || '---'})`;

                // Render Milestones
                const mBar = document.getElementById('milestonesBar');
                mBar.innerHTML = '';
                data.overview.milestones.forEach(m => {
                    const isDone = m.is_completed;
                    const el = document.createElement('div');
                    el.className = `m-step ${isDone ? 'm-done' : 'm-pending'}`;
                    el.innerHTML = `
                        <div class="m-circle">${isDone ? '✓' : '•'}</div>
                        <div class="m-name">${m.milestone}</div>
                    `;
                    mBar.appendChild(el);
                });

                // Render Tracking View (Flights)
                const tBody = document.getElementById('trackingTableBody');
                tBody.innerHTML = '';
                if (!data.tracking_view || data.tracking_view.length === 0) {
                    tBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #64748b;">No flight segments recorded.</td></tr>';
                } else {
                    data.tracking_view.forEach(s => {
                        tBody.innerHTML += `
                            <tr>
                                <td><strong>${s.carrier_code || 'AI'} ${s.flight_number || ''}</strong></td>
                                <td>${s.segment_origin || '---'} ➔ ${s.segment_destination || '---'}</td>
                                <td>${s.departure_date || ''} ${s.departure_time || ''}</td>
                                <td>${s.arrival_date || ''} ${s.arrival_time || ''}</td>
                                <td>${s.pieces || '---'} pcs</td>
                            </tr>
                        `;
                    });
                }

                // Render Activity View (Events)
                const aBody = document.getElementById('activityTableBody');
                aBody.innerHTML = '';
                if (!data.activity_view || data.activity_view.length === 0) {
                    aBody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: #64748b;">No activity logs recorded.</td></tr>';
                } else {
                    data.activity_view.forEach(ev => {
                        const flightUld = [
                            ev.flight_number ? `${ev.flight_carrier_code || 'AI'} ${ev.flight_number}` : '',
                            ev.uld_number ? `ULD: ${ev.uld_number}` : ''
                        ].filter(Boolean).join(' | ') || '---';

                        const pcsWt = [
                            ev.pieces !== null && ev.pieces !== undefined ? `${ev.pieces} pcs` : '',
                            ev.weight !== null && ev.weight !== undefined ? `${ev.weight} ${ev.weight_unit}` : ''
                        ].filter(Boolean).join(' / ') || '---';

                        aBody.innerHTML += `
                            <tr>
                                <td>${ev.event_time || ev.last_updated_time || '---'}</td>
                                <td><span class="badge-event">${ev.event_code}</span></td>
                                <td>${ev.event_name}</td>
                                <td>${ev.airport_code || '---'}</td>
                                <td>${pcsWt}</td>
                                <td>${flightUld}</td>
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
            const tabs = document.querySelectorAll('.tab-btn');
            tabs.forEach(t => t.classList.remove('active'));

            if (tab === 'tracking') {
                tabs[0].classList.add('active');
                document.getElementById('tabTracking').style.display = 'block';
                document.getElementById('tabActivity').style.display = 'none';
            } else {
                tabs[1].classList.add('active');
                document.getElementById('tabTracking').style.display = 'none';
                document.getElementById('tabActivity').style.display = 'block';
            }
        }

        // Auto track on load
        window.addEventListener('DOMContentLoaded', () => {
            trackAWB();
        });
    </script>
</body>
</html>
    """
    return html_content


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
