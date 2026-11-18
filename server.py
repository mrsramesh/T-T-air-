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
import io
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import AirIndiaTrackerException, AWBNotFoundException
from lufthansa_tracker.client import LufthansaCargoClient
from emirates_tracker.client import EmiratesTrackerClient, EmiratesShipmentNotFoundError, EmiratesTrackingError
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError, KuwaitTrackingError
from parcels_tracker.client import ParcelsTrackerClient, ParcelsShipmentNotFoundError, ParcelsTrackingError
from virgin_tracker.client import VirginCargoClient, VirginShipmentNotFoundError, VirginTrackingError
from qatar_tracker.client import QatarCargoClient, QatarShipmentNotFoundError, QatarTrackingError
from cargoflash_tracker.client import CargoFlashClient, CargoFlashShipmentNotFoundError, CargoFlashTrackingError
from neos_tracker.client import NeosCargoClient, NeosShipmentNotFoundError, NeosTrackingError
from indigo_tracker.client import IndigoCargoClient, IndigoShipmentNotFoundError, IndigoTrackingError
from bulk_tracker import (
    BulkCargoTracker,
    AWBExtractor,
    ExcelReportExporter,
    CSVReportExporter,
    BulkTrackingSummary,
    UnifiedTrackingRecord,
)

app = FastAPI(
    title="Multi-Carrier Air Cargo Tracking API",
    description="Industry-level API service for tracking Air India Cargo (098), Lufthansa Cargo (020), Emirates SkyCargo (176), Kuwait Airways (229), British Airways Cargo (125), Virgin Atlantic Cargo (932), Qatar Airways Cargo (157), EgyptAir Cargo (077), Neos Air Cargo (703), and IndiGo CarGo (312). Features bulk extraction, Excel export, and concurrent multi-carrier tracking.",
    version="11.0.0",
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
virgin_client = VirginCargoClient()
qatar_client = QatarCargoClient()
cargoflash_client = CargoFlashClient()
neos_client = NeosCargoClient()
indigo_client = IndigoCargoClient()
bulk_tracker = BulkCargoTracker(max_global_workers=8)


class BatchTrackRequest(BaseModel):
    awbs: List[str]
    carrier: Optional[str] = "auto"


class BulkTrackPayload(BaseModel):
    awbs: Optional[List[str]] = None
    text: Optional[str] = None
    workers: Optional[int] = 5


class ExportPayload(BaseModel):
    records: List[Dict[str, Any]]


def detect_carrier(awb: str) -> str:
    cleaned = re.sub(r"[\s\-_]+", "", awb.strip())
    if cleaned.startswith("312"):
        return "indigo"
    if cleaned.startswith("703"):
        return "neos"
    if cleaned.startswith("077"):
        return "cargoflash"
    if cleaned.startswith("157"):
        return "qatar"
    if cleaned.startswith("932"):
        return "virgin"
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
            "Virgin Atlantic Cargo (932)",
            "Qatar Airways Cargo (157)",
            "EgyptAir Cargo / Cargo Flash (077)",
            "Neos Air Cargo (NO) / WCS (703)",
            "IndiGo CarGo (6E) (312)",
        ],
    }


@app.get("/api/v1/track/{awb}", tags=["Tracking"])
def track_shipment(
    awb: str,
    carrier: Optional[str] = Query("auto", description="Carrier: 'auto', 'airindia', 'lufthansa', 'emirates', 'kuwait', 'britishairways', 'virgin', 'qatar', 'cargoflash', 'neos', or 'indigo'"),
):
    """
    Track a shipment by AWB number.
    Auto-detects IndiGo CarGo (312), Neos Air Cargo (703), EgyptAir Cargo (077), Qatar Airways (157), Virgin Atlantic (932), British Airways (125), Kuwait Airways (229), Emirates SkyCargo (176), Lufthansa Cargo (020), or Air India (098).
    """
    target_carrier = carrier if carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels") else detect_carrier(awb)

    try:
        if target_carrier in ("indigo", "6e", "indigocargo"):
            res = indigo_client.track(awb)
            return {"carrier": "IndiGo CarGo (6E)", "carrier_code": "312", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("neos", "neosair", "wcs"):
            res = neos_client.track(awb)
            return {"carrier": "Neos Air Cargo (NO) / WCS", "carrier_code": "703", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("cargoflash", "egyptair"):
            res = cargoflash_client.track(awb)
            return {"carrier": "EgyptAir Cargo (Cargo Flash)", "carrier_code": "077", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("qatar", "qrcargo"):
            res = qatar_client.track(awb)
            return {"carrier": "Qatar Airways Cargo", "carrier_code": "157", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("virgin", "virginatlantic"):
            res = virgin_client.track(awb)
            return {"carrier": "Virgin Atlantic Cargo", "carrier_code": "932", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("britishairways", "parcels"):
            res = parcels_client.track(awb)
            return {"carrier": "British Airways Cargo", "carrier_code": "125", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier == "kuwait":
            res = kw_client.track(awb)
            return {"carrier": "Kuwait Airways", "carrier_code": "229", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier == "emirates":
            res = ek_client.track(awb)
            return {"carrier": "Emirates SkyCargo", "carrier_code": "176", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier == "lufthansa":
            res = lh_client.track(awb)
            return {"carrier": "Lufthansa Cargo", "carrier_code": "020", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        else:
            res = ai_client.track(awb)
            return {"carrier": "Air India Cargo", "carrier_code": "098", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
    except (AWBNotFoundException, EmiratesShipmentNotFoundError, KuwaitShipmentNotFoundError, ParcelsShipmentNotFoundError, VirginShipmentNotFoundError, QatarShipmentNotFoundError, CargoFlashShipmentNotFoundError, NeosShipmentNotFoundError, IndigoShipmentNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (AirIndiaTrackerException, EmiratesTrackingError, KuwaitTrackingError, ParcelsTrackingError, VirginTrackingError, QatarTrackingError, CargoFlashTrackingError, NeosTrackingError, IndigoTrackingError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal tracking error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple AWBs concurrently across multiple carriers."""
    results = {}
    for awb in payload.awbs:
        target = payload.carrier if payload.carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels") else detect_carrier(awb)
        try:
            if target in ("indigo", "6e", "indigocargo"):
                results[awb] = {"carrier": "IndiGo CarGo (6E)", "status": "success", "data": indigo_client.track(awb).model_dump() if hasattr(indigo_client.track(awb), "model_dump") else indigo_client.track(awb).dict()}
            elif target in ("neos", "neosair", "wcs"):
                results[awb] = {"carrier": "Neos Air Cargo (NO) / WCS", "status": "success", "data": neos_client.track(awb).model_dump() if hasattr(neos_client.track(awb), "model_dump") else neos_client.track(awb).dict()}
            elif target in ("cargoflash", "egyptair"):
                results[awb] = {"carrier": "EgyptAir Cargo (Cargo Flash)", "status": "success", "data": cargoflash_client.track(awb).model_dump() if hasattr(cargoflash_client.track(awb), "model_dump") else cargoflash_client.track(awb).dict()}
            elif target in ("qatar", "qrcargo"):
                results[awb] = {"carrier": "Qatar Airways Cargo", "status": "success", "data": qatar_client.track(awb).model_dump() if hasattr(qatar_client.track(awb), "model_dump") else qatar_client.track(awb).dict()}
            elif target in ("virgin", "virginatlantic"):
                results[awb] = {"carrier": "Virgin Atlantic Cargo", "status": "success", "data": virgin_client.track(awb).model_dump() if hasattr(virgin_client.track(awb), "model_dump") else virgin_client.track(awb).dict()}
            elif target in ("britishairways", "parcels"):
                results[awb] = {"carrier": "British Airways Cargo", "status": "success", "data": parcels_client.track(awb).model_dump() if hasattr(parcels_client.track(awb), "model_dump") else parcels_client.track(awb).dict()}
            elif target == "kuwait":
                results[awb] = {"carrier": "Kuwait Airways", "status": "success", "data": kw_client.track(awb).model_dump() if hasattr(kw_client.track(awb), "model_dump") else kw_client.track(awb).dict()}
            elif target == "emirates":
                results[awb] = {"carrier": "Emirates SkyCargo", "status": "success", "data": ek_client.track(awb).model_dump() if hasattr(ek_client.track(awb), "model_dump") else ek_client.track(awb).dict()}
            elif target == "lufthansa":
                results[awb] = {"carrier": "Lufthansa Cargo", "status": "success", "data": lh_client.track(awb).model_dump() if hasattr(lh_client.track(awb), "model_dump") else lh_client.track(awb).dict()}
            else:
                results[awb] = {"carrier": "Air India Cargo", "status": "success", "data": ai_client.track(awb).model_dump() if hasattr(ai_client.track(awb), "model_dump") else ai_client.track(awb).dict()}
        except Exception as e:
            results[awb] = {"status": "error", "error": str(e)}
    return results


@app.post("/api/v1/track/bulk", tags=["Bulk Tracking"])
def track_bulk_shipments(payload: BulkTrackPayload):
    """
    Track multiple AWBs concurrently across all 10 major airline portals.
    Accepts an AWB list or raw text block (comma, newline, or space separated).
    """
    awbs: List[str] = []
    if payload.awbs:
        for a in payload.awbs:
            awbs.extend(AWBExtractor.extract_from_text(a))
    if payload.text:
        awbs.extend(AWBExtractor.extract_from_text(payload.text))

    seen = set()
    unique_awbs = [a for a in awbs if not (a in seen or seen.add(a))]

    if not unique_awbs:
        raise HTTPException(status_code=400, detail="No valid AWB numbers found in request.")

    engine = BulkCargoTracker(max_global_workers=payload.workers or 5)
    summary = engine.track_batch(unique_awbs)
    return summary.model_dump()


@app.post("/api/v1/track/upload", tags=["Bulk Tracking"])
async def track_uploaded_file(file: UploadFile = File(...), workers: int = Query(5)):
    """
    Upload an Excel spreadsheet (.xlsx, .xls), CSV file, or Text file.
    Extracts all AWBs automatically and tracks them in parallel.
    """
    file_bytes = await file.read()
    awbs = AWBExtractor.extract_from_any(file_bytes, filename=file.filename or "")

    seen = set()
    unique_awbs = [a for a in awbs if not (a in seen or seen.add(a))]

    if not unique_awbs:
        raise HTTPException(status_code=400, detail=f"No valid AWB numbers found in uploaded file '{file.filename}'.")

    engine = BulkCargoTracker(max_global_workers=workers)
    summary = engine.track_batch(unique_awbs)
    return summary.model_dump()


@app.post("/api/v1/export/excel", tags=["Bulk Export"])
def export_excel_report(payload: ExportPayload):
    """
    Generate and stream an executive-grade formatted Excel spreadsheet (.xlsx).
    """
    records = [UnifiedTrackingRecord(**r) for r in payload.records]
    excel_bytes = ExcelReportExporter.export_to_bytes(records)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=AirCargo_Shipments_Tracking.xlsx"},
    )


@app.post("/api/v1/export/csv", tags=["Bulk Export"])
def export_csv_report(payload: ExportPayload):
    """
    Generate and stream a clean UTF-8 CSV file.
    """
    records = [UnifiedTrackingRecord(**r) for r in payload.records]
    csv_bytes = CSVReportExporter.export_to_bytes(records)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=AirCargo_Shipments_Tracking.csv"},
    )


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Enterprise Web Dashboard for Multi-Carrier Cargo Tracking (Single & Bulk Engine)."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Global Air Cargo Tracking & Bulk Engine</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
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
        .container { max-width: 1140px; margin: 0 auto; }
        .header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 12px; }
        .logo-wrap { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .badge-6e { background: #002d62; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #1e40af; }
        .badge-no { background: #991b1b; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #7f1d1d; }
        .badge-ms { background: #002d62; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #1e40af; }
        .badge-qr { background: #5c0632; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #8a0c4d; }
        .badge-vs { background: #e10a0a; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #7c0404; }
        .badge-ba { background: #00205b; color: #ffffff; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #eb2226; }
        .badge-kw { background: var(--primary-kw); color: #bae6fd; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #0284c7; }
        .badge-ek { background: var(--primary-ek); color: #fef08a; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; border: 1px solid #dc2626; }
        .badge-lh { background: var(--primary-lh); color: var(--accent-lh); padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; }
        .badge-ai { background: var(--primary-ai); color: white; padding: 4px 9px; border-radius: 6px; font-weight: 700; font-size: 0.78rem; }
        .title { font-size: 1.35rem; font-weight: 800; color: #1e293b; margin-left: 6px; }

        /* Mode Switcher */
        .mode-switch-wrap { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem; flex-wrap: wrap; gap: 12px; }
        .mode-switch { display: flex; gap: 6px; background: #e2e8f0; padding: 4px; border-radius: 10px; width: fit-content; }
        .mode-btn { border: none; background: transparent; padding: 9px 20px; border-radius: 8px; font-weight: 700; font-size: 0.92rem; color: #475569; cursor: pointer; transition: all 0.2s; }
        .mode-btn.active { background: #ffffff; color: #0f172a; box-shadow: 0 2px 4px rgba(0,0,0,0.08); }
        .mode-btn:hover:not(.active) { color: #1e293b; background: rgba(255,255,255,0.4); }

        /* Single Tracker Styles */
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

        /* Bulk & Multi-AWB Engine Styles */
        .bulk-card { background: var(--card-bg); border-radius: 12px; padding: 1.5rem; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); margin-bottom: 1.5rem; }
        .subtabs { display: flex; gap: 8px; margin-bottom: 14px; border-bottom: 1px solid var(--border); padding-bottom: 10px; }
        .subtab-btn { border: 1px solid var(--border); background: #f8fafc; padding: 8px 18px; border-radius: 6px; font-weight: 600; font-size: 0.88rem; cursor: pointer; color: #475569; transition: all 0.2s; }
        .subtab-btn.active { background: #2563eb; color: #ffffff; border-color: #2563eb; }
        .bulk-textarea { width: 100%; min-height: 125px; padding: 0.85rem 1rem; border: 1.5px solid var(--border); border-radius: 8px; font-family: ui-monospace, Menlo, Monaco, Consolas, monospace; font-size: 0.92rem; line-height: 1.5; outline: none; resize: vertical; }
        .bulk-textarea:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37,99,235,0.1); }
        .drop-zone { border: 2px dashed #cbd5e1; border-radius: 8px; padding: 2.2rem 1.5rem; text-align: center; background: #f8fafc; cursor: pointer; transition: all 0.2s; }
        .drop-zone:hover, .drop-zone.dragover { border-color: #2563eb; background: #eff6ff; }
        .drop-zone-icon { font-size: 2.2rem; margin-bottom: 6px; }
        .drop-zone-text { font-size: 0.95rem; font-weight: 600; color: #334155; }
        .drop-zone-hint { font-size: 0.8rem; color: #64748b; margin-top: 4px; }
        .file-chosen-badge { display: inline-flex; align-items: center; gap: 6px; background: #dbeafe; color: #1e40af; padding: 6px 14px; border-radius: 6px; font-weight: 600; font-size: 0.88rem; margin-top: 10px; }

        /* Bulk Control Bar */
        .bulk-ctrls { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-top: 14px; flex-wrap: wrap; }
        .bulk-quick { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
        .bulk-run-wrap { display: flex; gap: 10px; align-items: center; }
        .worker-select { padding: 0.65rem 0.85rem; border: 1.5px solid var(--border); border-radius: 8px; font-size: 0.88rem; font-weight: 600; background: white; outline: none; }
        button.btn-bulk-track { background: #2563eb; color: white; border: none; padding: 0.75rem 1.8rem; border-radius: 8px; font-weight: 700; cursor: pointer; font-size: 0.95rem; transition: opacity 0.2s; display: flex; align-items: center; gap: 8px; }
        button.btn-bulk-track:hover { opacity: 0.92; }
        button.btn-bulk-track:disabled { opacity: 0.6; cursor: not-allowed; }

        /* Progress Bar */
        .progress-box { margin-bottom: 1.5rem; display: none; background: white; padding: 1.25rem 1.5rem; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 2px 4px rgba(0,0,0,0.03); }
        .progress-head { display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: 600; color: #334155; margin-bottom: 8px; }
        .progress-bar-wrap { width: 100%; height: 10px; background: #f1f5f9; border-radius: 9999px; overflow: hidden; }
        .progress-bar-fill { height: 100%; width: 0%; background: linear-gradient(90deg, #2563eb, #38bdf8); transition: width 0.3s; }

        /* KPI Cards */
        .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(125px, 1fr)); gap: 12px; margin-bottom: 1.5rem; }
        .kpi-card { background: white; border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.03); }
        .kpi-card .m-val { font-size: 1.55rem; font-weight: 800; color: #0f172a; }
        .kpi-card .m-lbl { font-size: 0.72rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 4px; letter-spacing: 0.4px; }
        .kpi-card.kpi-success .m-val { color: #16a34a; }
        .kpi-card.kpi-failed .m-val { color: #dc2626; }
        .kpi-card.kpi-transit .m-val { color: #2563eb; }

        /* Bulk Table Card */
        .bulk-results-card { background: white; border-radius: 12px; border: 1px solid var(--border); box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); overflow: hidden; display: none; margin-bottom: 2rem; }
        .bulk-toolbar { padding: 1rem 1.5rem; background: #f8fafc; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }
        .filter-group { display: flex; gap: 10px; align-items: center; flex: 1; min-width: 280px; }
        .filter-input { flex: 1; padding: 0.6rem 0.85rem; border: 1.5px solid var(--border); border-radius: 6px; font-size: 0.88rem; outline: none; }
        .filter-input:focus { border-color: #2563eb; }
        .filter-select { padding: 0.6rem 0.85rem; border: 1.5px solid var(--border); border-radius: 6px; font-size: 0.88rem; background: white; outline: none; }
        .export-actions { display: flex; gap: 8px; align-items: center; }
        .btn-export-excel { background: #16a34a; color: white; border: none; padding: 0.6rem 1.1rem; border-radius: 6px; font-weight: 700; font-size: 0.88rem; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: opacity 0.2s; }
        .btn-export-excel:hover { opacity: 0.9; }
        .btn-export-csv { background: #0284c7; color: white; border: none; padding: 0.6rem 1.1rem; border-radius: 6px; font-weight: 700; font-size: 0.88rem; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; transition: opacity 0.2s; }
        .btn-export-csv:hover { opacity: 0.9; }
        .btn-inspect { background: #f1f5f9; border: 1px solid var(--border); color: #1e293b; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.15s; }
        .btn-inspect:hover { background: #e2e8f0; color: #0f172a; }

        /* Status Pills */
        .status-badge { display: inline-block; padding: 3px 10px; border-radius: 9999px; font-size: 0.74rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px; }
        .st-DELIVERED { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
        .st-IN_TRANSIT, .st-DEPARTED { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
        .st-ARRIVED { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
        .st-BOOKED, .st-ACCEPTED { background: #ede9fe; color: #6d28d9; border: 1px solid #ddd6fe; }
        .st-NOT_FOUND { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
        .st-ERROR { background: #fee2e2; color: #b91c1c; border: 1px solid #fecaca; }

        /* Airline Pills */
        .carrier-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 0.74rem; font-weight: 700; font-family: monospace; }
        .ct-indigo { background: #eff6ff; color: #002d62; border: 1px solid #bfdbfe; }
        .ct-neos { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
        .ct-cargoflash { background: #eff6ff; color: #002d62; border: 1px solid #bfdbfe; }
        .ct-qatar { background: #fdf2f8; color: #5c0632; border: 1px solid #fbcfe8; }
        .ct-virgin { background: #fef2f2; color: #e10a0a; border: 1px solid #fecaca; }
        .ct-britishairways { background: #eff6ff; color: #00205b; border: 1px solid #bfdbfe; }
        .ct-kuwait { background: #f0f9ff; color: #0f3d6e; border: 1px solid #bae6fd; }
        .ct-emirates { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }
        .ct-lufthansa { background: #eff6ff; color: #05164d; border: 1px solid #bfdbfe; }
        .ct-airindia { background: #fef2f2; color: #d71921; border: 1px solid #fecaca; }

        /* Modal Dialog */
        .modal-overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(15, 23, 42, 0.65); display: none; align-items: center; justify-content: center; z-index: 9999; padding: 1rem; backdrop-filter: blur(2px); }
        .modal-wrap { background: white; border-radius: 12px; width: 100%; max-width: 860px; max-height: 90vh; overflow-y: auto; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25); border: 1px solid var(--border); }
        .modal-head { padding: 1.25rem 1.75rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; background: #f8fafc; }
        .modal-head h3 { font-size: 1.25rem; font-weight: 700; color: #0f172a; }
        .modal-close-btn { background: none; border: none; font-size: 1.5rem; line-height: 1; cursor: pointer; color: #64748b; padding: 4px 8px; border-radius: 4px; }
        .modal-close-btn:hover { color: #0f172a; background: #e2e8f0; }
        .modal-body { padding: 1.5rem 1.75rem; }
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Branding Header -->
        <div class="header">
            <div class="logo-wrap">
                <span class="badge-6e">INDIGO (312)</span>
                <span class="badge-no">NEOS AIR (703)</span>
                <span class="badge-ms">EGYPTAIR (077)</span>
                <span class="badge-qr">QATAR (157)</span>
                <span class="badge-vs">VIRGIN (932)</span>
                <span class="badge-ba">BRITISH AIRWAYS (125)</span>
                <span class="badge-kw">KUWAIT (229)</span>
                <span class="badge-ek">EMIRATES (176)</span>
                <span class="badge-lh">LUFTHANSA (020)</span>
                <span class="badge-ai">AIR INDIA (098)</span>
                <span class="title">Global Cargo Tracker</span>
            </div>
            <a href="/docs" target="_blank" style="color: #2563eb; text-decoration: none; font-weight: 600; font-size: 0.9rem;">Swagger API ↗</a>
        </div>

        <!-- Mode Switcher (Single vs Bulk Engine) -->
        <div class="mode-switch-wrap">
            <div class="mode-switch">
                <button id="btnModeSingle" class="mode-btn active" onclick="switchDashboardMode('single')">🔍 Single AWB Tracker</button>
                <button id="btnModeBulk" class="mode-btn" onclick="switchDashboardMode('bulk')">⚡ Bulk & Multi-AWB Engine (Excel & CSV)</button>
            </div>
            <div style="font-size: 0.85rem; color: #64748b;">Enterprise 10-Carrier Concurrency & Anti-Bot Protection</div>
        </div>

        <div class="error-msg" id="errorBox"></div>

        <!-- ================= SECTION 1: SINGLE AWB TRACKER ================= -->
        <div id="singleTrackerSection">
            <div class="search-card">
                <div class="form-row">
                    <select id="carrierSelect" class="carrier-select">
                        <option value="auto">Auto-Detect Carrier</option>
                        <option value="indigo">IndiGo CarGo (312)</option>
                        <option value="neos">Neos Air Cargo (703)</option>
                        <option value="cargoflash">EgyptAir Cargo (077)</option>
                        <option value="qatar">Qatar Airways Cargo (157)</option>
                        <option value="virgin">Virgin Atlantic Cargo (932)</option>
                        <option value="britishairways">British Airways Cargo (125)</option>
                        <option value="kuwait">Kuwait Airways (229)</option>
                        <option value="emirates">Emirates SkyCargo (176)</option>
                        <option value="lufthansa">Lufthansa Cargo (020)</option>
                        <option value="airindia">Air India Cargo (098)</option>
                    </select>
                    <input type="text" id="awbInput" placeholder="Enter AWB (e.g. 312-9298-9396, 703-13715800, 077-59060002, 157-5366-1580, 932-78989514, 125-24128344, 229-18148900, 176-63116340, 020-04585280, 098-30244056)" value="312-9298-9396" />
                    <button class="btn-search" onclick="trackAWB()">Track Shipment</button>
                </div>
                <div class="quick-links">
                    <span>Quick Samples:</span>
                    <button class="quick-btn" onclick="setAwb('312-9298-9396', 'indigo')">312-9298-9396 (IndiGo BKK)</button>
                    <button class="quick-btn" onclick="setAwb('703-13715800', 'neos')">703-13715800 (Neos KWI)</button>
                    <button class="quick-btn" onclick="setAwb('703-13715332', 'neos')">703-13715332 (Neos JED)</button>
                    <button class="quick-btn" onclick="setAwb('077-59060002', 'cargoflash')">077-59060002 (EgyptAir LON)</button>
                    <button class="quick-btn" onclick="setAwb('077-59060945', 'cargoflash')">077-59060945 (EgyptAir ORD)</button>
                    <button class="quick-btn" onclick="setAwb('157-5366-1580', 'qatar')">157-5366-1580 (Qatar Airways)</button>
                    <button class="quick-btn" onclick="setAwb('932-78989514', 'virgin')">932-78989514 (Virgin Atlantic)</button>
                    <button class="quick-btn" onclick="setAwb('125-24128344', 'britishairways')">125-24128344 (British Airways)</button>
                    <button class="quick-btn" onclick="setAwb('229-18148900', 'kuwait')">229-18148900 (Kuwait Valid)</button>
                    <button class="quick-btn" onclick="setAwb('229-17349566', 'kuwait')">229-17349566 (Kuwait Not Found)</button>
                    <button class="quick-btn" onclick="setAwb('176-63116340', 'emirates')">176-63116340 (Emirates)</button>
                    <button class="quick-btn" onclick="setAwb('020-04585280', 'lufthansa')">020-04585280 (Lufthansa)</button>
                    <button class="quick-btn" onclick="setAwb('098-30244056', 'airindia')">098-30244056 (Air India)</button>
                </div>
            </div>

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

        <!-- ================= SECTION 2: BULK & MULTI-AWB ENGINE ================= -->
        <div id="bulkTrackerSection" style="display: none;">
            <div class="bulk-card">
                <div class="subtabs">
                    <button id="tabPasteBtn" class="subtab-btn active" onclick="switchBulkTab('paste')">📋 Paste AWBs (Multi-Line / CSV / Text)</button>
                    <button id="tabUploadBtn" class="subtab-btn" onclick="switchBulkTab('upload')">📁 Upload Spreadsheet (.xlsx / .csv / .txt)</button>
                </div>

                <!-- Panel A: Paste Area -->
                <div id="panelPasteArea">
                    <textarea id="bulkTextarea" class="bulk-textarea" placeholder="Paste multiple AWB numbers here (separated by newlines, commas, spaces, semicolons, tabs, or pipes).&#10;Example:&#10;312-9298-9396, 703-13715800, 077-59060002&#10;157-5366-1580, 125-24128344, 229-18148900"></textarea>
                </div>

                <!-- Panel B: Upload Area -->
                <div id="panelUploadArea" style="display: none;">
                    <div class="drop-zone" id="dropZone" onclick="document.getElementById('fileUploadInput').click()">
                        <div class="drop-zone-icon">📊</div>
                        <div class="drop-zone-text">Click or drag & drop your Excel or CSV file here</div>
                        <div class="drop-zone-hint">Supports .xlsx (all sheets scanned), .csv, and .txt files</div>
                        <input type="file" id="fileUploadInput" accept=".xlsx,.csv,.txt" style="display: none;" onchange="handleFileSelect(this)" />
                        <div id="fileBadge" class="file-chosen-badge" style="display: none;">
                            <span>📄 Selected:</span>
                            <span id="fileNameSpan"></span>
                        </div>
                    </div>
                </div>

                <!-- Bulk Controls -->
                <div class="bulk-ctrls">
                    <div class="bulk-quick">
                        <button class="quick-btn" onclick="fillBulkSample()">⚡ Fill 8-Airline Sample Batch</button>
                        <button class="quick-btn" onclick="clearBulkInput()">🗑 Clear</button>
                    </div>
                    <div class="bulk-run-wrap">
                        <label style="font-size: 0.85rem; font-weight: 600; color: #475569;">Concurrency:</label>
                        <select id="bulkWorkersSelect" class="worker-select">
                            <option value="3">3 Workers (Gentle)</option>
                            <option value="5" selected>5 Workers (Recommended)</option>
                            <option value="8">8 Workers (Fast)</option>
                            <option value="10">10 Workers (Max)</option>
                        </select>
                        <button id="btnRunBulk" class="btn-bulk-track" onclick="runBulkTracking()">
                            <span>🚀 Track All AWBs</span>
                        </button>
                    </div>
                </div>
            </div>

            <!-- Progress Box -->
            <div class="progress-box" id="bulkProgressBox">
                <div class="progress-head">
                    <span id="bulkProgressStatus">Running Multi-Carrier Batch Engine...</span>
                    <span id="bulkProgressText">Initializing...</span>
                </div>
                <div class="progress-bar-wrap">
                    <div class="progress-bar-fill" id="bulkProgressBar"></div>
                </div>
            </div>

            <!-- Bulk KPI Metrics Row -->
            <div class="kpi-row" id="bulkKpiRow" style="display: none;">
                <div class="kpi-card">
                    <div class="m-lbl">Total Shipments</div>
                    <div class="m-val" id="kpiTotal">0</div>
                </div>
                <div class="kpi-card kpi-success">
                    <div class="m-lbl">Succeeded</div>
                    <div class="m-val" id="kpiSuccess">0</div>
                </div>
                <div class="kpi-card kpi-failed">
                    <div class="m-lbl">Failed / Not Found</div>
                    <div class="m-val" id="kpiFailed">0</div>
                </div>
                <div class="kpi-card kpi-success">
                    <div class="m-lbl">Delivered</div>
                    <div class="m-val" id="kpiDelivered">0</div>
                </div>
                <div class="kpi-card kpi-transit">
                    <div class="m-lbl">In-Transit / Departed</div>
                    <div class="m-val" id="kpiTransit">0</div>
                </div>
                <div class="kpi-card">
                    <div class="m-lbl">Arrived</div>
                    <div class="m-val" id="kpiArrived">0</div>
                </div>
                <div class="kpi-card">
                    <div class="m-lbl">Booked / Accepted</div>
                    <div class="m-val" id="kpiBooked">0</div>
                </div>
                <div class="kpi-card">
                    <div class="m-lbl">Elapsed Time</div>
                    <div class="m-val" id="kpiDuration">0.0s</div>
                </div>
            </div>

            <!-- Bulk Table & Toolbar Card -->
            <div class="bulk-results-card" id="bulkResultsCard">
                <div class="bulk-toolbar">
                    <div class="filter-group">
                        <input type="text" id="bulkSearchInput" class="filter-input" placeholder="🔍 Search AWB, Airline, Station (e.g. BOM, BKK, KWI), Flight..." oninput="renderBulkTable()" />
                        <select id="bulkStatusFilter" class="filter-select" onchange="renderBulkTable()">
                            <option value="ALL">All Statuses</option>
                            <option value="DELIVERED">Delivered</option>
                            <option value="IN_TRANSIT">In Transit</option>
                            <option value="ARRIVED">Arrived</option>
                            <option value="DEPARTED">Departed</option>
                            <option value="BOOKED">Booked</option>
                            <option value="ACCEPTED">Accepted</option>
                            <option value="NOT_FOUND">Not Found</option>
                            <option value="ERROR">Error</option>
                        </select>
                    </div>
                    <div class="export-actions">
                        <button class="btn-export-excel" onclick="exportBulkExcel()">
                            <span>📊 Export Excel (.xlsx)</span>
                        </button>
                        <button class="btn-export-csv" onclick="exportBulkCsv()">
                            <span>📄 Export CSV</span>
                        </button>
                    </div>
                </div>

                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>AWB Number</th>
                                <th>Airline</th>
                                <th>Status</th>
                                <th>Origin ➔ Destination</th>
                                <th>Pieces / Weight</th>
                                <th>Flight(s)</th>
                                <th>Latest Activity</th>
                                <th>Timestamp</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="bulkTableBody"></tbody>
                    </table>
                </div>
            </div>
        </div>

    </div>

    <!-- ================= SHIPMENT INSPECTION MODAL ================= -->
    <div class="modal-overlay" id="shipmentModalOverlay" onclick="if(event.target === this) closeModal()">
        <div class="modal-wrap">
            <div class="modal-head">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <h3 id="modalAwbTitle">AWB</h3>
                    <span id="modalCarrierTag" class="carrier-tag">CARRIER</span>
                    <span id="modalStatusBadge" class="status-badge">STATUS</span>
                </div>
                <button class="modal-close-btn" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div class="metrics-grid" style="border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1.25rem;">
                    <div>
                        <div class="m-lbl">Route</div>
                        <div class="m-val" id="modalRoute">---</div>
                    </div>
                    <div>
                        <div class="m-lbl">Pieces & Weight</div>
                        <div class="m-val" id="modalPcsWeight">---</div>
                    </div>
                    <div>
                        <div class="m-lbl">Flight(s)</div>
                        <div class="m-val" id="modalFlight">---</div>
                    </div>
                    <div>
                        <div class="m-lbl">Event Timestamp</div>
                        <div class="m-val" id="modalEventTime" style="font-size: 0.95rem;">---</div>
                    </div>
                </div>

                <div class="banner" id="modalLatestActivity" style="border-radius: 8px; margin-bottom: 1.25rem;">Latest Activity</div>

                <div style="font-size: 0.95rem; font-weight: 700; margin-bottom: 8px; color: #1e293b;">Milestones Timeline</div>
                <div style="border: 1px solid var(--border); border-radius: 8px; overflow: hidden; margin-bottom: 1.25rem;">
                    <table>
                        <thead>
                            <tr>
                                <th>Date & Time</th>
                                <th>Code</th>
                                <th>Description</th>
                                <th>Station</th>
                            </tr>
                        </thead>
                        <tbody id="modalMilestonesBody"></tbody>
                    </table>
                </div>

                <details style="font-size: 0.85rem; color: #64748b; background: #f8fafc; padding: 0.75rem 1rem; border-radius: 8px; border: 1px solid var(--border);">
                    <summary style="cursor: pointer; font-weight: 600;">View Raw Payload JSON</summary>
                    <pre id="modalRawData" style="margin-top: 8px; font-family: monospace; font-size: 0.8rem; overflow-x: auto; white-space: pre-wrap; color: #0f172a;"></pre>
                </details>
            </div>
        </div>
    </div>

    <script>
        // Current Bulk State
        let currentBulkData = null;
        let currentBulkRecords = [];

        function switchDashboardMode(mode) {
            const btnSingle = document.getElementById('btnModeSingle');
            const btnBulk = document.getElementById('btnModeBulk');
            const secSingle = document.getElementById('singleTrackerSection');
            const secBulk = document.getElementById('bulkTrackerSection');

            if (mode === 'bulk') {
                btnSingle.classList.remove('active');
                btnBulk.classList.add('active');
                secSingle.style.display = 'none';
                secBulk.style.display = 'block';
            } else {
                btnBulk.classList.remove('active');
                btnSingle.classList.add('active');
                secBulk.style.display = 'none';
                secSingle.style.display = 'block';
            }
        }

        function switchBulkTab(tab) {
            const tabPaste = document.getElementById('tabPasteBtn');
            const tabUpload = document.getElementById('tabUploadBtn');
            const panelPaste = document.getElementById('panelPasteArea');
            const panelUpload = document.getElementById('panelUploadArea');

            if (tab === 'upload') {
                tabPaste.classList.remove('active');
                tabUpload.classList.add('active');
                panelPaste.style.display = 'none';
                panelUpload.style.display = 'block';
            } else {
                tabUpload.classList.remove('active');
                tabPaste.classList.add('active');
                panelUpload.style.display = 'none';
                panelPaste.style.display = 'block';
            }
        }

        function fillBulkSample() {
            const samples = [
                "312-9298-9396", // IndiGo
                "703-13715800", // Neos Air
                "077-59060002", // EgyptAir
                "157-5366-1580", // Qatar Airways
                "125-24128344", // British Airways
                "229-18148900", // Kuwait Airways
                "077-59060945", // EgyptAir ORD
                "703-13715332"  // Neos Air JED
            ];
            document.getElementById('bulkTextarea').value = samples.join('\n');
            switchBulkTab('paste');
        }

        function clearBulkInput() {
            document.getElementById('bulkTextarea').value = '';
            document.getElementById('fileUploadInput').value = '';
            document.getElementById('fileBadge').style.display = 'none';
        }

        function handleFileSelect(input) {
            if (input.files && input.files[0]) {
                const file = input.files[0];
                document.getElementById('fileBadge').style.display = 'inline-flex';
                document.getElementById('fileNameSpan').innerText = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
            }
        }

        async function runBulkTracking() {
            const isUploadTab = document.getElementById('tabUploadBtn').classList.contains('active');
            const workers = parseInt(document.getElementById('bulkWorkersSelect').value) || 5;
            const progressBox = document.getElementById('bulkProgressBox');
            const progressBar = document.getElementById('bulkProgressBar');
            const progressText = document.getElementById('bulkProgressText');
            const btnRun = document.getElementById('btnRunBulk');
            const resultsCard = document.getElementById('bulkResultsCard');
            const kpiRow = document.getElementById('bulkKpiRow');
            const errorBox = document.getElementById('errorBox');

            errorBox.style.display = 'none';
            btnRun.disabled = true;
            btnRun.innerHTML = '<span>Tracking In Progress...</span>';
            progressBox.style.display = 'block';
            progressBar.style.width = '35%';
            progressText.innerText = `Dispatching multi-airline tracking queries (Concurrency: ${workers} workers)...`;

            try {
                let response;
                if (isUploadTab) {
                    const fileInput = document.getElementById('fileUploadInput');
                    if (!fileInput.files || fileInput.files.length === 0) {
                        throw new Error("Please select an Excel (.xlsx), CSV (.csv), or Text file to upload.");
                    }
                    const formData = new FormData();
                    formData.append('file', fileInput.files[0]);
                    response = await fetch(`/api/v1/track/upload?workers=${workers}`, {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    const text = document.getElementById('bulkTextarea').value.trim();
                    if (!text) {
                        throw new Error("Please paste at least one AWB number into the box or click 'Fill Sample Batch'.");
                    }
                    response = await fetch(`/api/v1/track/bulk`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ text: text, workers: workers })
                    });
                }

                progressBar.style.width = '75%';
                progressText.innerText = 'Analyzing and standardizing carrier responses...';

                if (!response.ok) {
                    const errData = await response.json();
                    throw new Error(errData.detail || 'Bulk tracking request failed');
                }

                const data = await response.json();
                currentBulkData = data;
                currentBulkRecords = data.records || [];

                progressBar.style.width = '100%';
                progressText.innerText = `Complete! Tracked ${data.total_awbs} AWBs in ${data.duration_seconds}s (${data.success_count} succeeded, ${data.failure_count} failed).`;

                // Update KPI Metrics
                document.getElementById('kpiTotal').innerText = data.total_awbs;
                document.getElementById('kpiSuccess').innerText = data.success_count;
                document.getElementById('kpiFailed').innerText = data.failure_count;
                document.getElementById('kpiDelivered').innerText = (data.status_breakdown && data.status_breakdown.DELIVERED) || 0;
                document.getElementById('kpiTransit').innerText = ((data.status_breakdown && data.status_breakdown.IN_TRANSIT) || 0) + ((data.status_breakdown && data.status_breakdown.DEPARTED) || 0);
                document.getElementById('kpiArrived').innerText = (data.status_breakdown && data.status_breakdown.ARRIVED) || 0;
                document.getElementById('kpiBooked').innerText = ((data.status_breakdown && data.status_breakdown.BOOKED) || 0) + ((data.status_breakdown && data.status_breakdown.ACCEPTED) || 0);
                document.getElementById('kpiDuration').innerText = `${data.duration_seconds}s`;

                // Show KPI and Results
                kpiRow.style.display = 'grid';
                resultsCard.style.display = 'block';
                renderBulkTable();

                // Smooth scroll to results
                resultsCard.scrollIntoView({ behavior: 'smooth' });

            } catch (err) {
                errorBox.innerText = `Error: ${err.message}`;
                errorBox.style.display = 'block';
                progressBox.style.display = 'none';
            } finally {
                btnRun.disabled = false;
                btnRun.innerHTML = '<span>🚀 Track All AWBs</span>';
            }
        }

        function renderBulkTable() {
            const tbody = document.getElementById('bulkTableBody');
            const searchFilter = (document.getElementById('bulkSearchInput').value || '').toLowerCase().trim();
            const statusFilter = document.getElementById('bulkStatusFilter').value;

            tbody.innerHTML = '';

            const filtered = currentBulkRecords.filter(r => {
                if (statusFilter !== 'ALL' && r.status !== statusFilter) {
                    return false;
                }
                if (searchFilter) {
                    const combined = `${r.awb} ${r.carrier} ${r.origin} ${r.destination} ${r.flight_numbers} ${r.latest_activity} ${r.status}`.toLowerCase();
                    return combined.includes(searchFilter);
                }
                return true;
            });

            if (filtered.length === 0) {
                tbody.innerHTML = `<tr><td colspan="10" style="text-align: center; padding: 2rem; color: #64748b;">No shipments match your search filter.</td></tr>`;
                return;
            }

            filtered.forEach((r, idx) => {
                const tr = document.createElement('tr');
                const stClass = `st-${r.status}`;
                const ctClass = `ct-${r.carrier_code.toLowerCase()}`;
                const flightBadge = r.flight_numbers ? `<span class="badge-ev">${r.flight_numbers}</span>` : '<span style="color:#94a3b8">N/A</span>';
                const route = (r.origin || r.destination) ? `<strong>${r.origin || '---'}</strong> ➔ <strong>${r.destination || '---'}</strong>` : '<span style="color:#94a3b8">N/A</span>';
                const weightPcs = `${r.pieces ? r.pieces + ' pcs' : ''} ${r.weight_kg ? '/ ' + r.weight_kg + ' KG' : ''}`.trim() || '<span style="color:#94a3b8">N/A</span>';

                tr.innerHTML = `
                    <td style="color: #64748b; font-weight: 600;">${idx + 1}</td>
                    <td><strong style="font-family: monospace; font-size: 0.95rem;">${r.awb}</strong></td>
                    <td><span class="carrier-tag ${ctClass}">${r.carrier}</span></td>
                    <td><span class="status-badge ${stClass}">${r.status}</span></td>
                    <td>${route}</td>
                    <td>${weightPcs}</td>
                    <td>${flightBadge}</td>
                    <td style="max-width: 260px; font-size: 0.85rem;" title="${r.latest_activity}">${r.latest_activity || '---'}</td>
                    <td style="font-size: 0.8rem; color: #64748b; white-space: nowrap;">${r.latest_event_time || '---'}</td>
                    <td>
                        <button class="btn-inspect" onclick="inspectShipment('${r.awb}')">👁 Inspect</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        async function exportBulkExcel() {
            if (!currentBulkRecords || currentBulkRecords.length === 0) {
                alert("No tracked shipment data available to export.");
                return;
            }
            try {
                const res = await fetch('/api/v1/export/excel', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ records: currentBulkRecords })
                });
                if (!res.ok) throw new Error("Excel export failed");
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `AirCargo_Tracking_Report_${new Date().toISOString().slice(0,10)}.xlsx`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            } catch (e) {
                alert(`Export error: ${e.message}`);
            }
        }

        async function exportBulkCsv() {
            if (!currentBulkRecords || currentBulkRecords.length === 0) {
                alert("No tracked shipment data available to export.");
                return;
            }
            try {
                const res = await fetch('/api/v1/export/csv', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ records: currentBulkRecords })
                });
                if (!res.ok) throw new Error("CSV export failed");
                const blob = await res.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `AirCargo_Tracking_Report_${new Date().toISOString().slice(0,10)}.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
            } catch (e) {
                alert(`Export error: ${e.message}`);
            }
        }

        function inspectShipment(awb) {
            const record = currentBulkRecords.find(r => r.awb === awb);
            if (!record) return;

            document.getElementById('modalAwbTitle').innerText = record.awb;
            document.getElementById('modalCarrierTag').innerText = record.carrier;
            document.getElementById('modalCarrierTag').className = `carrier-tag ct-${record.carrier_code.toLowerCase()}`;
            document.getElementById('modalStatusBadge').innerText = record.status;
            document.getElementById('modalStatusBadge').className = `status-badge st-${record.status}`;

            document.getElementById('modalRoute').innerText = `${record.origin || 'N/A'} ➔ ${record.destination || 'N/A'}`;
            document.getElementById('modalPcsWeight').innerText = `${record.pieces || '---'} pcs / ${record.weight_kg || '---'} KG`;
            document.getElementById('modalFlight').innerText = record.flight_numbers || 'N/A';
            document.getElementById('modalLatestActivity').innerText = record.latest_activity || 'N/A';
            document.getElementById('modalEventTime').innerText = record.latest_event_time || 'N/A';
            document.getElementById('modalRawData').innerText = JSON.stringify(record.raw_payload || {}, null, 2);

            // Milestones
            const mBody = document.getElementById('modalMilestonesBody');
            mBody.innerHTML = '';
            const milestones = record.milestones || [];
            if (milestones.length === 0) {
                mBody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: #64748b; padding: 1rem;">No milestone events recorded.</td></tr>`;
            } else {
                milestones.forEach(m => {
                    mBody.innerHTML += `
                        <tr>
                            <td style="font-size: 0.85rem; font-weight: 600;">${m.date_time || '---'}</td>
                            <td><span class="badge-ev">${m.code || 'EV'}</span></td>
                            <td style="font-size: 0.88rem;">${m.description || '---'}</td>
                            <td><strong>${m.station || '---'}</strong></td>
                        </tr>
                    `;
                });
            }

            document.getElementById('shipmentModalOverlay').style.display = 'flex';
        }

        function closeModal() {
            document.getElementById('shipmentModalOverlay').style.display = 'none';
        }

        // Close modal on escape key
        window.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });

        // Single Tracker JS logic
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

                if (cName.includes('IndiGo') || cName.includes('312') || cName.includes('6E')) {
                    // IndiGo CarGo (SmartKargo)
                    topBar.style.background = '#eff6ff';
                    const isDelivered = (data.overview.current_status || '').toLowerCase().includes('delivered');
                    document.getElementById('statusPill').style.background = isDelivered ? '#15803d' : '#002d62';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.current_status || 'DELIVERED';

                    const fl = data.overview.flight_no ? ` &bull; Flight: <em>${data.overview.flight_no}</em>` : '';
                    const iss = data.overview.issued_to ? ` &bull; Issued To: <strong>${data.overview.issued_to}</strong>` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>IndiGo CarGo (6E):</strong> ${data.overview.latest_activity}${fl}${iss}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin} ➔ ${data.overview.destination}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces || '---'} pcs / ${data.overview.gross_weight || '---'}`;
                    document.getElementById('volumeDisplay').innerText = data.overview.flight_no || 'Scheduled Flight';
                    document.getElementById('productDisplay').innerText = data.overview.issued_to ? `DO Issued: ${data.overview.issued_to}` : 'Commercial Air Cargo';

                    // Transit Station Checkpoints (Card Grid)
                    const sGrid = document.getElementById('stationGrid');
                    sGrid.innerHTML = '';
                    (data.booking_info || []).forEach(b => {
                        sGrid.innerHTML += `
                            <div class="station-box">
                                <div class="station-title">📋 ${b.status}: <strong>${b.station} ➔ ${b.destination}</strong></div>
                                <div class="station-detail"><span class="badge-ev">${b.flight_no || 'Flight'}</span> <strong>${b.pieces || '---'} pcs (${b.weight || '---'})</strong></div>
                                <div class="station-detail" style="color: #64748b; font-size: 0.82rem; margin-top: 4px;">⏱ ${b.event_time || 'N/A'}</div>
                            </div>
                        `;
                    });
                    (data.delivery_orders || []).forEach(doItem => {
                        sGrid.innerHTML += `
                            <div class="station-box" style="border: 2px solid #15803d; background: #f0fdf4;">
                                <div class="station-title" style="color: #15803d;">📦 DO: <strong>${doItem.do_number}</strong> <span class="badge-latest">RELEASED</span></div>
                                <div class="station-detail">Consignee: <strong>${doItem.issued_to || 'N/A'}</strong></div>
                                <div class="station-detail" style="color: #64748b; font-size: 0.82rem; margin-top: 4px;">${doItem.pieces || '---'} pcs / ${doItem.weight || '---'}</div>
                            </div>
                        `;
                    });
                    stationWrap.style.display = 'block';

                    // Flights & Booking Info Tab
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.booking_info || []).forEach(b => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong style="color: #002d62;">${b.flight_no || '6E Flight'}</strong></td>
                                <td>${b.station} ➔ ${b.destination}</td>
                                <td>${b.event_time || 'N/A'}</td>
                                <td>Booking Status: ${b.status}</td>
                                <td>${b.pieces || '---'} pcs / ${b.weight || '---'}</td>
                                <td><span class="badge-ev">${b.status}</span></td>
                            </tr>
                        `;
                    });

                    // Shipment Milestones & Audit Trail Tab
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.status_history || []).forEach(h => {
                        const badge = h.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Historical</span>';
                        const sector = (h.origin && h.destination) ? `${h.origin} ➔ ${h.destination}` : '---';
                        const flDesc = h.flight_no ? `${h.flight_no} (${h.flight_date || ''})` : (h.uld_or_remarks || '---');
                        hBody.innerHTML += `
                            <tr>
                                <td>${h.event_time || 'N/A'}</td>
                                <td><span class="badge-ev">${h.milestone}</span></td>
                                <td>${h.milestone} at ${h.station} ${h.uld_or_remarks ? ' - ' + h.uld_or_remarks : ''}</td>
                                <td><strong>${h.station} (${sector})</strong></td>
                                <td>${flDesc}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Neos') || cName.includes('WCS') || cName.includes('703')) {
                    // Neos Air Cargo / World Cargo Solutions
                    topBar.style.background = '#fef2f2';
                    document.getElementById('statusPill').style.background = '#991b1b';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.latest_event_code || 'DELIVERED';

                    const comm = data.overview.commodity ? ` &bull; Commodity: <em>${data.overview.commodity}</em>` : '';
                    const src = data.overview.source ? ` &bull; Source: <em>${data.overview.source}</em>` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>Neos Air Cargo (WCS):</strong> ${data.overview.current_status}${comm}${src}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin} ➔ ${data.overview.destination}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces || '---'} pcs / ${data.overview.gross_weight || '---'}`;
                    document.getElementById('volumeDisplay').innerText = `Step: ${data.overview.progress_step || 'Delivered'}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.commodity || 'GENERAL CARGO'}`;

                    // Flights & Routing Tab
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flights || []).forEach(fl => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong style="color: #991b1b;">${fl.flight_display || fl.flight_no}</strong></td>
                                <td>${fl.origin} ➔ ${fl.destination}</td>
                                <td>${fl.departure_time || 'N/A'}</td>
                                <td>${fl.arrival_time || 'N/A'}</td>
                                <td>${fl.weight || data.overview.gross_weight || '---'}</td>
                                <td><span class="badge-ev">${fl.status}</span></td>
                            </tr>
                        `;
                    });

                    // Shipment History / Milestones Tab
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.milestones || []).forEach(m => {
                        const badge = m.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Historical</span>';
                        const sector = (m.origin && m.destination) ? `${m.origin} ➔ ${m.destination}` : m.destination;
                        hBody.innerHTML += `
                            <tr>
                                <td>${m.timestamp || 'N/A'}</td>
                                <td><span class="badge-ev">${m.status_code}</span></td>
                                <td>${m.description}</td>
                                <td><strong>${sector || '---'}</strong></td>
                                <td>${m.flight_no ? m.flight_no : (m.pieces ? m.pieces + ' pcs' : '---')}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('EgyptAir') || cName.includes('Cargo Flash')) {
                    // EgyptAir Cargo / Cargo Flash
                    topBar.style.background = '#f0fdf4';
                    document.getElementById('statusPill').style.background = '#064e3b';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.latest_event_action || 'CONFIRMED';

                    const comm = data.overview.commodity ? ` &bull; Commodity: <em>${data.overview.commodity}</em>` : '';
                    const agent = data.overview.agent_name ? ` &bull; Agent: <em>${data.overview.agent_name}</em>` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>EgyptAir Cargo:</strong> ${data.overview.latest_event_message}${comm}${agent}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin} ➔ ${data.overview.destination}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces} pcs / ${data.overview.gross_weight} ${data.overview.weight_unit}`;
                    const volCbm = (data.overview.cbm != null && data.overview.cbm > 0) ? `${data.overview.cbm} CBM` : (data.overview.chargeable_weight ? `Chg: ${data.overview.chargeable_weight} KG` : '---');
                    document.getElementById('volumeDisplay').innerText = volCbm;
                    document.getElementById('productDisplay').innerText = `${data.overview.product_name || 'GENERAL CARGO'}`;

                    // Milestone Plan Checkpoints (Card Grid)
                    if (data.milestone_plan && data.milestone_plan.length > 0) {
                        const sGrid = document.getElementById('stationGrid');
                        sGrid.innerHTML = '';
                        data.milestone_plan.forEach((mp, idx) => {
                            const isLatest = idx === data.milestone_plan.length - 1;
                            sGrid.innerHTML += `
                                <div class="station-box" style="${isLatest ? 'border: 2px solid #059669; background: #ecfdf5;' : ''}">
                                    <div class="station-title">🏛 Station: <strong>${mp.station}</strong> ${isLatest ? '<span class="badge-latest">CURRENT</span>' : ''}</div>
                                    <div class="station-detail"><span class="badge-ev">${mp.action}</span> <strong>${mp.pieces || '---'} pcs</strong></div>
                                    <div class="station-detail" style="color: #64748b; font-size: 0.82rem; margin-top: 4px;">📅 ${mp.date_time || 'N/A'}</div>
                                </div>
                            `;
                        });
                        stationWrap.style.display = 'block';
                    }

                    // Flights & Itinerary Tab
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flight_details || []).forEach(fl => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong style="color: #047857;">${fl.flight_display || fl.flight_no}</strong></td>
                                <td>${fl.route || fl.station}</td>
                                <td>${fl.flight_date || 'N/A'}</td>
                                <td>${fl.description} @ ${fl.station}</td>
                                <td>${fl.total_pieces || '---'} pcs / ${fl.gross_weight || '---'} KG</td>
                                <td><span class="badge-ev">${fl.event}</span></td>
                            </tr>
                        `;
                    });

                    // Shipment History / Milestones Tab
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.milestone_plan || []).forEach((mp, idx) => {
                        const isLatest = idx === data.milestone_plan.length - 1;
                        const badge = isLatest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Completed</span>';
                        hBody.innerHTML += `
                            <tr>
                                <td>${mp.date_time || 'N/A'}</td>
                                <td><span class="badge-ev">${mp.action}</span></td>
                                <td>Shipment Milestone ${mp.action}</td>
                                <td><strong>${mp.station}</strong></td>
                                <td>${mp.pieces ? mp.pieces + ' pcs' : '---'}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Qatar')) {
                    // Qatar Airways Cargo
                    topBar.style.background = '#fdf2f8';
                    document.getElementById('statusPill').style.background = '#5c0632';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.overall_status || 'DELIVERED';

                    const st1 = data.overview.latest_status_message ? ` &bull; <em>${data.overview.latest_status_message}</em>` : '';
                    const st2 = data.overview.latest_arrival_message ? ` &bull; <em>${data.overview.latest_arrival_message}</em>` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>Qatar Airways Cargo:</strong> ${data.overview.overall_status}${st1}${st2}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin || 'DEL'} ➔ ${data.overview.destination || 'LUN'}`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces || '---'} pcs / ${data.overview.weight || '---'} ${data.overview.weight_unit || 'Kg'}`;
                    document.getElementById('volumeDisplay').innerText = `${data.overview.volume || '---'} ${data.overview.volume_unit || 'm³'}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.overall_status} (${data.overview.latest_status_message || ''})`;

                    // Flights
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flights || []).forEach(fl => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong style="color: #5c0632;">${fl.flight_number}</strong></td>
                                <td>${fl.origin} ➔ ${fl.destination}</td>
                                <td>${fl.departure_date_time || 'N/A'}</td>
                                <td>${fl.arrival_date_time || 'N/A'}</td>
                                <td>${fl.pieces || '---'} pcs / ${fl.weight || '---'} ${fl.weight_unit || 'Kg'}</td>
                                <td><span class="badge-ev">${fl.flight_status || 'Departed'}</span></td>
                            </tr>
                        `;
                    });

                    // Milestones
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.milestones || []).forEach(m => {
                        const pcsWt = m.pieces ? `${m.pieces} pcs / ${m.weight} ${m.weight_unit || 'Kg'}` : '---';
                        const badge = m.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Historical</span>';
                        const dt = [m.event_date, m.event_time].filter(Boolean).join(' ') || 'N/A';
                        hBody.innerHTML += `
                            <tr>
                                <td>${dt}</td>
                                <td><span class="badge-ev">${m.status_code}</span></td>
                                <td>${m.details}</td>
                                <td><strong>${m.airport || '---'}</strong></td>
                                <td>${pcsWt}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('Virgin')) {
                    // Virgin Atlantic Cargo
                    topBar.style.background = '#fff1f2';
                    document.getElementById('statusPill').style.background = '#e10a0a';
                    document.getElementById('statusPill').style.color = '#ffffff';
                    document.getElementById('statusPill').innerText = data.overview.order_status || 'CONFIRMED';

                    const jrn = data.overview.job_reference_number ? `JRN: ${data.overview.job_reference_number}` : '';
                    const bref = data.overview.booking_reference_number ? `Booking: ${data.overview.booking_reference_number}` : '';
                    const shpStatus = data.overview.shipment_status ? ` &bull; <em>${data.overview.shipment_status}</em>` : '';
                    document.getElementById('latestBanner').innerHTML = `<strong>Virgin Atlantic Cargo:</strong> ${data.overview.order_status}${shpStatus} &bull; ${[jrn, bref].filter(Boolean).join(' | ')}`;

                    document.getElementById('routeDisplay').innerText = `${data.overview.origin.code} (${data.overview.origin.name || ''}) ➔ ${data.overview.destination.code} (${data.overview.destination.name || ''})`;
                    document.getElementById('pcsWeightDisplay').innerText = `${data.overview.pieces || '---'} pcs / ${data.overview.weight || '---'} ${data.overview.weight_unit || 'K'}`;
                    document.getElementById('volumeDisplay').innerText = `${data.overview.volume || '---'} ${data.overview.volume_unit || 'CM'}${data.overview.transit_duration ? ' (' + data.overview.transit_duration + ')' : ''}`;
                    document.getElementById('productDisplay').innerText = `${data.overview.product_name || data.overview.commodity || 'General - Classic'}${data.overview.agent_name ? ' | ' + data.overview.agent_name : ''}`;

                    // Flights
                    const fBody = document.getElementById('flightsBody');
                    fBody.innerHTML = '';
                    (data.flights || []).forEach(fl => {
                        fBody.innerHTML += `
                            <tr>
                                <td><strong style="color: #e10a0a;">${fl.flight_number}</strong></td>
                                <td>${fl.origin.code} ➔ ${fl.destination.code}</td>
                                <td>${fl.departure_time || 'N/A'}</td>
                                <td>${fl.arrival_time || 'N/A'}</td>
                                <td>${fl.pieces || '---'} pcs / ${fl.weight || '---'} ${fl.weight_unit || 'K'}</td>
                                <td><span class="badge-ev">${fl.status || 'CONF'}</span></td>
                            </tr>
                        `;
                    });

                    // Milestones
                    const hBody = document.getElementById('historyBody');
                    hBody.innerHTML = '';
                    (data.milestones || []).forEach(m => {
                        const pcsWt = m.pieces ? `${m.pieces} pcs / ${m.weight} ${m.weight_unit || 'K'}` : '---';
                        const badge = m.is_latest ? '<span class="badge-latest">LATEST</span>' : '<span style="color: #64748b;">Planned</span>';
                        const sector = [m.board_point, m.off_point].filter(Boolean).join(' ➔ ');
                        const flSec = m.flight_number ? `${m.flight_number} (${sector})` : sector;
                        hBody.innerHTML += `
                            <tr>
                                <td>${m.timestamp || 'N/A'}</td>
                                <td><span class="badge-ev">${m.code}</span></td>
                                <td>${m.description}</td>
                                <td><strong>${m.station || '---'}</strong></td>
                                <td>${flSec || pcsWt}</td>
                                <td>${badge}</td>
                            </tr>
                        `;
                    });

                } else if (cName.includes('British Airways') || cName.includes('Parcels')) {
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

        function switchTab(tab) {
            const tabs = document.querySelectorAll('#singleTrackerSection .tab-item');
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
