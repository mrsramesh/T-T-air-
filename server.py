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
from turkish_tracker.client import TurkishCargoClient, TurkishShipmentNotFoundError, TurkishTrackingError
from etihad_tracker.client import EtihadCargoClient, EtihadShipmentNotFoundError, EtihadTrackingError
from saudia_tracker.client import SaudiaCargoClient, SaudiaShipmentNotFoundError, SaudiaTrackingError
from bulk_tracker import (
    BulkCargoTracker,
    AWBExtractor,
    ExcelReportExporter,
    CSVReportExporter,
    BulkTrackingSummary,
    UnifiedTrackingRecord,
    MasterLedgerManager,
    master_ledger,
)
from bulk_tracker.google_sheets import (
    GoogleSheetsTracker,
    GoogleSheetAccessError,
    GoogleSheetError,
)
from bulk_tracker.autopilot import AutoPilotManager
from bulk_tracker.safe_runner import SafeChunkedTracker
from bulk_tracker.proxy_pool import proxy_pool, install_requests_proxy_hook
from bulk_tracker.circuit_breaker import circuit_breaker
from bulk_tracker.notifier import notifier

sheets_tracker = GoogleSheetsTracker()
autopilot = AutoPilotManager(sheets_tracker, master_ledger)
safe_runner = SafeChunkedTracker(master_ledger)

app = FastAPI(
    title="Multi-Carrier Air Cargo Tracking API",
    description="Industry-level API service for tracking Air India Cargo (098), Lufthansa Cargo (020), Emirates SkyCargo (176), Kuwait Airways (229), British Airways Cargo (125), Virgin Atlantic Cargo (932), Qatar Airways Cargo (157), EgyptAir Cargo (077), Neos Air Cargo (703), and IndiGo CarGo (312). Features bulk extraction, Excel export, and concurrent multi-carrier tracking.",
    version="11.0.0",
)

@app.on_event("startup")
def on_app_startup():
    """
    Solves Risk #6: Automatically restores Auto-Pilot daemon state and Proxy Mode across server/Docker restarts.
    """
    saved_proxy = master_ledger.get_setting("proxy_mode")
    if isinstance(saved_proxy, dict) and saved_proxy.get("mode"):
        proxy_pool.set_mode(saved_proxy["mode"], saved_proxy.get("custom_proxies"))
        print(f"[Startup] Restored persisted Proxy Mode: {saved_proxy['mode']}")

    install_requests_proxy_hook()

    resumed = autopilot.resume_from_storage()
    if resumed:
        print("[Startup] Auto-Pilot background daemon successfully resumed from persistent storage.")
    else:
        print("[Startup] Auto-Pilot is idle (toggle was OFF).")

    # Check and report proxy status
    status = proxy_pool.get_status()
    print(f"[Startup] Proxy Engine initialized: Mode={status['mode']}, TorAvailable={status['tor_available']}, HealthyProxies={status['healthy_proxies_count']}")

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
turkish_client = TurkishCargoClient()
etihad_client = EtihadCargoClient()
saudia_client = SaudiaCargoClient()
bulk_tracker = BulkCargoTracker(max_global_workers=2)


class BatchTrackRequest(BaseModel):
    awbs: List[str]
    carrier: Optional[str] = "auto"


class BulkTrackPayload(BaseModel):
    awbs: Optional[List[str]] = None
    text: Optional[str] = None
    workers: Optional[int] = 1


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
    if cleaned.startswith("235"):
        return "turkish"
    if cleaned.startswith("607"):
        return "etihad"
    if cleaned.startswith("065"):
        return "saudia"
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
            "Turkish Cargo (TK) (235)",
            "Etihad Cargo (EY) (607)",
            "Saudia Cargo (SV) (065)",
        ],
    }


@app.get("/api/v1/track/{awb}", tags=["Tracking"])
def track_shipment(
    awb: str,
    carrier: Optional[str] = Query("auto", description="Carrier: 'auto', 'airindia', 'lufthansa', 'emirates', 'kuwait', 'britishairways', 'virgin', 'qatar', 'cargoflash', 'neos', or 'indigo'"),
    force: bool = Query(False, description="Bypass 6-hour DB cooldown cache"),
):
    """
    Track a shipment by AWB number.
    Auto-detects IndiGo CarGo (312), Neos Air Cargo (703), EgyptAir Cargo (077), Qatar Airways (157), Virgin Atlantic (932), British Airways (125), Kuwait Airways (229), Emirates SkyCargo (176), Lufthansa Cargo (020), or Air India (098).
    """
    target_carrier = carrier if carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels", "turkish", "tk", "turkishcargo", "etihad", "ey", "etihadcargo", "saudia", "sv", "saudiacargo") else detect_carrier(awb)

    if not force:
        cached = master_ledger.get_fresh_cached_record(awb, cooldown_hours=6.0)
        if cached and cached["record"].get("raw_payload_json"):
            import json as _json
            try:
                rec = cached["record"]
                raw_payload = _json.loads(rec["raw_payload_json"])
                return {
                    "carrier": rec.get("carrier_name") or "Cached Carrier",
                    "carrier_code": rec.get("iata_prefix") or "",
                    "cached": True,
                    "cache_age_minutes": cached["age_minutes"],
                    "remaining_minutes": cached["remaining_minutes"],
                    "cache_message": cached["message"],
                    "data": raw_payload,
                }
            except Exception:
                pass

    # Automatically record & update in Master Ledger
    try:
        s_rec = bulk_tracker.track_single(awb)
        if s_rec:
            master_ledger.upsert_record(s_rec)
    except Exception:
        pass

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
        elif target_carrier in ("turkish", "tk", "turkishcargo"):
            res = turkish_client.track(awb)
            return {"carrier": "Turkish Cargo (TK)", "carrier_code": "235", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("etihad", "ey", "etihadcargo"):
            res = etihad_client.track(awb)
            return {"carrier": "Etihad Cargo (EY)", "carrier_code": "607", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        elif target_carrier in ("saudia", "sv", "saudiacargo"):
            res = saudia_client.track(awb)
            return {"carrier": "Saudia Cargo (SV)", "carrier_code": "065", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
        else:
            res = ai_client.track(awb)
            return {"carrier": "Air India Cargo", "carrier_code": "098", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
    except (AWBNotFoundException, EmiratesShipmentNotFoundError, KuwaitShipmentNotFoundError, ParcelsShipmentNotFoundError, VirginShipmentNotFoundError, QatarShipmentNotFoundError, CargoFlashShipmentNotFoundError, NeosShipmentNotFoundError, IndigoShipmentNotFoundError, TurkishShipmentNotFoundError, EtihadShipmentNotFoundError, SaudiaShipmentNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (AirIndiaTrackerException, EmiratesTrackingError, KuwaitTrackingError, ParcelsTrackingError, VirginTrackingError, QatarTrackingError, CargoFlashTrackingError, NeosTrackingError, IndigoTrackingError, TurkishTrackingError, EtihadTrackingError, SaudiaTrackingError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal tracking error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple AWBs concurrently across multiple carriers."""
    results = {}
    for awb in payload.awbs:
        target = payload.carrier if payload.carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels", "turkish", "tk", "turkishcargo", "etihad", "ey", "etihadcargo", "saudia", "sv", "saudiacargo") else detect_carrier(awb)
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
            elif target in ("turkish", "tk", "turkishcargo"):
                results[awb] = {"carrier": "Turkish Cargo (TK)", "status": "success", "data": turkish_client.track(awb).model_dump() if hasattr(turkish_client.track(awb), "model_dump") else turkish_client.track(awb).dict()}
            elif target in ("etihad", "ey", "etihadcargo"):
                results[awb] = {"carrier": "Etihad Cargo (EY)", "status": "success", "data": etihad_client.track(awb).model_dump() if hasattr(etihad_client.track(awb), "model_dump") else etihad_client.track(awb).dict()}
            elif target in ("saudia", "sv", "saudiacargo"):
                results[awb] = {"carrier": "Saudia Cargo (SV)", "status": "success", "data": saudia_client.track(awb).model_dump() if hasattr(saudia_client.track(awb), "model_dump") else saudia_client.track(awb).dict()}
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

    engine = BulkCargoTracker(max_global_workers=payload.workers or 1)
    summary = engine.track_batch(unique_awbs)
    # Automatically persist/update master ledger without duplicates
    master_ledger.upsert_batch(summary.records)
    return summary.model_dump()


@app.post("/api/v1/track/upload", tags=["Bulk Tracking"])
async def track_uploaded_file(file: UploadFile = File(...), workers: int = Query(1)):
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
    # Automatically persist/update master ledger without duplicates
    master_ledger.upsert_batch(summary.records)
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


# =========================================================================
# Master Cargo Ledger & Permanent Storage Endpoints
# =========================================================================

@app.get("/api/v1/ledger", tags=["Master Ledger"])
def get_master_ledger(
    search: Optional[str] = Query(None, description="Search by AWB, Customer, Airline, Station, Flight, etc."),
    status: Optional[str] = Query("ALL", description="Filter by status: ALL, DELIVERED, IN_TRANSIT, ARRIVED, etc."),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """
    Retrieve master persistent air cargo ledger records.
    Every AWB tracked is permanently saved without duplicates and updated in place.
    """
    records = master_ledger.get_all_records(search=search, status=status, limit=limit, offset=offset)
    stats = master_ledger.get_summary_stats()
    return {
        "stats": stats,
        "total_matched": len(records),
        "records": records,
    }


@app.get("/api/v1/ledger/stats", tags=["Master Ledger"])
def get_ledger_stats():
    """Retrieve aggregate statistics for the Master Cargo Ledger."""
    return master_ledger.get_summary_stats()


@app.get("/api/v1/ledger/export/excel", tags=["Master Ledger"])
def export_ledger_excel(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
):
    """
    Download the complete Master Air Cargo Ledger as a beautifully formatted Excel (.xlsx) sheet.
    Columns: Customer Name, AWB No, Package, Gross Weight, Volume Weight, IATA, Flight Code, Source, Destination, Direction in Transition, Status of AWB.
    """
    from datetime import datetime
    records = master_ledger.get_all_records(search=search, status=status, limit=10000)
    excel_bytes = master_ledger.export_excel(records)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=AirCargo_Master_Ledger_{datetime.now().strftime('%Y%m%d')}.xlsx"},
    )


@app.get("/api/v1/ledger/export/csv", tags=["Master Ledger"])
def export_ledger_csv(
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
):
    """
    Download the complete Master Air Cargo Ledger as a CSV file.
    """
    from datetime import datetime
    records = master_ledger.get_all_records(search=search, status=status, limit=10000)
    csv_str = master_ledger.export_csv(records)
    return Response(
        content=csv_str,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=AirCargo_Master_Ledger_{datetime.now().strftime('%Y%m%d')}.csv"},
    )


# =========================================================================
# Google Sheets Auto-Sync & Lifecycle Tracking Endpoints
# =========================================================================

class GoogleSheetInspectRequest(BaseModel):
    url: str
    sheet_name: Optional[str] = None
    target_col: Optional[str] = "H"
    start_row: Optional[int] = None
    scan_all_tabs: Optional[bool] = False


class GoogleSheetSyncRequest(BaseModel):
    url: str
    sheet_name: Optional[str] = None
    target_col: Optional[str] = "H"
    start_row: Optional[int] = None
    scan_all_tabs: Optional[bool] = False
    workers: Optional[int] = 1
    recheck_delivered: Optional[bool] = False


class AutoPilotConfigRequest(BaseModel):
    url: Optional[str] = None
    sheet_name: Optional[str] = None
    target_col: Optional[str] = "H"
    start_row: Optional[int] = 110
    scan_all_tabs: Optional[bool] = False
    interval_minutes: Optional[int] = 60
    workers: Optional[int] = 1


@app.post("/api/v1/sheets/inspect", tags=["Google Sheets"])
def inspect_google_sheet(payload: GoogleSheetInspectRequest):
    """
    Inspect a Google Sheet by URL:
    - Lists all available sheet tabs.
    - Auto-detects columns (Column H = AWB, Column C = Customer, Column F = Dest, etc.).
    - Supports start_row (e.g. H110 downwards) and multi-tab scanning.
    - Returns preview of found AWBs with row and cell coordinates.
    """
    try:
        return sheets_tracker.inspect_sheet(
            payload.url,
            sheet_name=payload.sheet_name,
            target_col=payload.target_col or "H",
            start_row=payload.start_row,
            scan_all_tabs=bool(payload.scan_all_tabs),
        )
    except GoogleSheetAccessError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/sheets/sync", tags=["Google Sheets"])
def sync_and_track_google_sheet(payload: GoogleSheetSyncRequest):
    """
    Auto-read AWBs from Google Sheet (Column H) and execute lifecycle tracking:
    - Skips already DELIVERED shipments (saves resources).
    - Tracks active 'On-The-Way' shipments across multi-airline engines concurrently.
    - Supports start_row (e.g. H110 downwards) and multi-tab scanning.
    - Upserts Master Cargo Ledger without duplicate rows.
    - Categorizes into Active On-The-Way vs Delivered Archive.
    """
    try:
        return sheets_tracker.sync_and_track_lifecycle(
            payload.url,
            sheet_name=payload.sheet_name,
            target_col=payload.target_col or "H",
            start_row=payload.start_row,
            scan_all_tabs=bool(payload.scan_all_tabs),
            workers=payload.workers or 1,
            recheck_delivered=bool(payload.recheck_delivered),
        )
    except GoogleSheetAccessError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/sheets/autopilot/start", tags=["Google Sheets Auto-Pilot"])
def start_autopilot(payload: Optional[AutoPilotConfigRequest] = None):
    """
    Activate continuous background lifecycle tracking for Google Sheets.
    Tracks active/undelivered AWBs (starting from start_row downwards),
    freezes delivered AWBs, and updates database at regular intervals.
    """
    config_dict = payload.model_dump(exclude_unset=True) if payload else {}
    return autopilot.start(config_dict)


@app.post("/api/v1/sheets/autopilot/stop", tags=["Google Sheets Auto-Pilot"])
def stop_autopilot():
    """
    Gracefully pause/stop the Auto-Pilot continuous lifecycle tracking daemon.
    """
    return autopilot.stop()


@app.get("/api/v1/sheets/autopilot/status", tags=["Google Sheets Auto-Pilot"])
def get_autopilot_status():
    """
    Get live status, countdown to next cycle, total cycles run, and metrics.
    """
    return autopilot.get_status()


@app.post("/api/v1/sheets/autopilot/run-now", tags=["Google Sheets Auto-Pilot"])
def run_autopilot_now():
    """
    Trigger a manual sync cycle immediately via the Auto-Pilot engine.
    """
    if safe_runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="Process Lock Active: Safe Chunked Tracker is currently running. Stop it before running Auto-Pilot.",
        )
    return autopilot.run_now()


@app.get("/api/v1/sheets/lifecycle", tags=["Google Sheets"])
def get_lifecycle_shipments(
    view: str = Query("all", description="View filter: 'active' (On The Way), 'delivered' (Archive), or 'all'"),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
):
    """
    Retrieve shipments categorized by lifecycle:
    - 'active' / 'on_the_way': Shipments currently moving, in-transit, departed, or booked.
    - 'delivered': Successfully delivered shipments (completed archive).
    - 'all': Complete ledger.
    """
    records = master_ledger.get_all_records(
        search=search,
        status=status,
        lifecycle=view,
        limit=limit,
        offset=offset,
    )
    stats = master_ledger.get_summary_stats()
    return {
        "view": view,
        "stats": stats,
        "total_matched": len(records),
        "records": records,
    }


# =========================================================================
# Multi-Sheet Sources & Unified Tracking Queue + KPIs
# =========================================================================

class SheetSourceUpsertRequest(BaseModel):
    url: str
    label: Optional[str] = None
    sheet_name: Optional[str] = None
    target_col: Optional[str] = "H"
    start_row: Optional[int] = 110
    scan_all_tabs: Optional[bool] = True
    is_enabled: Optional[bool] = True
    source_id: Optional[int] = None


class SheetSourceToggleRequest(BaseModel):
    is_enabled: bool


class MultiSheetSyncRequest(BaseModel):
    workers: Optional[int] = 1


@app.get("/api/v1/sheets/sources", tags=["Multi-Sheet Manager"])
def list_sheet_sources():
    """Returns all configured Google Sheet sources with their Enable/Disable status and sync metrics."""
    return {
        "status": "success",
        "sources": master_ledger.list_sheet_sources(),
    }


@app.post("/api/v1/sheets/sources", tags=["Multi-Sheet Manager"])
def upsert_sheet_source(payload: SheetSourceUpsertRequest):
    """Adds or updates a Google Sheet source configuration."""
    try:
        src = master_ledger.upsert_sheet_source(
            url=payload.url,
            label=payload.label,
            sheet_name=payload.sheet_name,
            target_col=payload.target_col or "H",
            start_row=payload.start_row or 110,
            scan_all_tabs=True if payload.scan_all_tabs is None else bool(payload.scan_all_tabs),
            is_enabled=True if payload.is_enabled is None else bool(payload.is_enabled),
            source_id=payload.source_id,
        )
        return {"status": "success", "source": src}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/v1/sheets/sources/{source_id}/toggle", tags=["Multi-Sheet Manager"])
def toggle_sheet_source(source_id: int, payload: SheetSourceToggleRequest):
    """Enables or disables reading for a specific Google Sheet."""
    updated = master_ledger.toggle_sheet_source(source_id, payload.is_enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Sheet source {source_id} not found")
    return {"status": "success", "source": updated}


@app.delete("/api/v1/sheets/sources/{source_id}", tags=["Multi-Sheet Manager"])
def delete_sheet_source(source_id: int):
    """Removes a Google Sheet source from the multi-sheet list."""
    deleted = master_ledger.delete_sheet_source(source_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Sheet source {source_id} not found")
    return {"status": "success", "deleted_id": source_id}


@app.post("/api/v1/sheets/sources/scan-only", tags=["Multi-Sheet Manager"])
def scan_enabled_sheets_only():
    """
    Scans all ENABLED Google Sheets for new rows & new tabs (0 airline API calls),
    registers new AWBs into the Active Tracking Queue, and returns updated KPIs + 2 tables.
    """
    try:
        scan_res = sheets_tracker.scan_enabled_sheets()
        queue_data = master_ledger.get_tracking_queue_and_kpis()
        return {
            "status": "success",
            "scan_summary": scan_res,
            **queue_data,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/v1/sheets/sources/sync-track", tags=["Multi-Sheet Manager"])
def sync_and_track_enabled_sheets(payload: Optional[MultiSheetSyncRequest] = None):
    """
    Scans all ENABLED Google Sheets + collects undelivered AWBs from Central Ledger,
    tracks them live across airlines, and updates Active Tracking List vs Delivered Report.
    """
    try:
        workers = (payload.workers if payload and payload.workers else 1)
        return sheets_tracker.sync_all_enabled_sheets(workers=workers, track_live=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/v1/sheets/queue", tags=["Multi-Sheet Manager"])
def get_tracking_queue_and_kpis(
    search: Optional[str] = Query(None),
    sheet_filter: Optional[str] = Query("ALL"),
    limit: int = Query(2000, ge=1, le=10000),
):
    """
    Returns the two lifecycle tables (Active Tracking List & Delivered Report) plus live KPIs
    from local SQLite (0 external API calls).
    """
    data = master_ledger.get_tracking_queue_and_kpis(
        search=search,
        sheet_filter=sheet_filter,
        limit=limit,
    )
    return {"status": "success", **data}


# =========================================================================
# Safe Chunked Human-Paced Tracking & Table 3 (Unreachable / Unsupported)
# =========================================================================

class SafeTrackStartRequest(BaseModel):
    chunk_size: Optional[int] = 6
    min_delay_min: Optional[float] = 2.0
    max_delay_min: Optional[float] = 7.0


class UnreachableRetryRequest(BaseModel):
    awb_clean: Optional[str] = None


@app.get("/api/v1/sheets/safe-track/plan", tags=["Safe Chunked Tracker"])
def get_safe_track_plan(
    chunk_size: int = Query(6, ge=1, le=20),
    min_delay_min: float = Query(2.0, ge=0.5, le=30.0),
    max_delay_min: float = Query(7.0, ge=0.5, le=60.0),
):
    """Pre-filters unsupported prefixes and returns a transparent execution plan (0 network calls)."""
    plan = safe_runner.build_plan(
        chunk_size=chunk_size,
        min_delay_min=min_delay_min,
        max_delay_min=max_delay_min,
    )
    queue_data = master_ledger.get_tracking_queue_and_kpis()
    return {"status": "success", "plan": plan, **queue_data}


@app.post("/api/v1/sheets/safe-track/start", tags=["Safe Chunked Tracker"])
def start_safe_track(payload: Optional[SafeTrackStartRequest] = None):
    """Starts background chunked human-paced tracking with random 2-7 min delays."""
    p = payload or SafeTrackStartRequest()
    return safe_runner.start(
        chunk_size=p.chunk_size or 6,
        min_delay_min=p.min_delay_min or 2.0,
        max_delay_min=p.max_delay_min or 7.0,
    )


@app.post("/api/v1/sheets/safe-track/stop", tags=["Safe Chunked Tracker"])
def stop_safe_track():
    """Gracefully stops background chunked tracking after the current AWB."""
    return safe_runner.stop()


@app.get("/api/v1/sheets/safe-track/status", tags=["Safe Chunked Tracker"])
def get_safe_track_status():
    """Returns live step-by-step progress, chunk countdown, plan, and step logs."""
    return safe_runner.get_status()


@app.get("/api/v1/sheets/safe-track/health", tags=["Safe Chunked Tracker"])
def get_safe_track_health():
    """Returns live Proxy, Tor daemon, Circuit Breaker, and Queue health diagnostics."""
    return safe_runner.run_health_check()


@app.post("/api/v1/sheets/prefilter", tags=["Safe Chunked Tracker"])
def prefilter_queue():
    """Pre-filters Active Queue against 13 supported airlines (0 network calls)."""
    pf = master_ledger.prefilter_supported_queue()
    queue_data = master_ledger.get_tracking_queue_and_kpis()
    return {"status": "success", "prefilter": pf, **queue_data}


@app.post("/api/v1/sheets/unreachable/retry", tags=["Safe Chunked Tracker"])
def retry_unreachable(payload: Optional[UnreachableRetryRequest] = None):
    """Moves an unreachable AWB (or all supported-prefix unreachable AWBs) back to Table 1."""
    awb = payload.awb_clean if payload else None
    count = master_ledger.retry_unreachable_awb(awb)
    queue_data = master_ledger.get_tracking_queue_and_kpis()
    return {"status": "success", "requeued_count": count, **queue_data}


class ProxyModeRequest(BaseModel):
    mode: str
    custom_proxies: Optional[List[str]] = None


@app.get("/api/v1/proxy/status", tags=["Proxy Engine"])
def get_proxy_status():
    """Returns proxy pool health metrics, active mode, and Tor connectivity."""
    return proxy_pool.get_status()


@app.post("/api/v1/proxy/mode", tags=["Proxy Engine"])
def set_proxy_mode(payload: ProxyModeRequest):
    """Sets active proxy routing mode ('off', 'tor', 'free_pool', 'custom') and persists it."""
    if safe_runner.is_running:
        raise HTTPException(
            status_code=409,
            detail="Process Lock Active: Cannot change Proxy Mode while Safe Chunked Tracker is running. Stop the active run first.",
        )
    proxy_pool.set_mode(payload.mode, payload.custom_proxies)
    master_ledger.save_setting("proxy_mode", {"mode": payload.mode, "custom_proxies": payload.custom_proxies})
    return {
        "status": "success",
        "message": f"Proxy mode updated to '{payload.mode}'",
        "data": proxy_pool.get_status()
    }


@app.get("/api/v1/state", tags=["State Management"])
def get_app_state():
    """Returns persisted UI & application state from SQLite."""
    return {
        "status": "success",
        "state": master_ledger.get_ui_state()
    }


@app.post("/api/v1/state", tags=["State Management"])
def save_app_state(payload: Dict[str, Any]):
    """Merges and persists UI & application state into SQLite."""
    updated = master_ledger.save_ui_state(payload)
    return {
        "status": "success",
        "state": updated
    }


@app.get("/api/v1/health/carriers", tags=["Carrier Health & Circuit Breakers"])
def get_carrier_health():
    """Returns circuit breaker status, failure counters, and fallback states for all carriers."""
    return {
        "status": "success",
        "carriers": circuit_breaker.get_all_status()
    }


class AlertTestRequest(BaseModel):
    title: Optional[str] = "Tracking System Test Alert"
    message: Optional[str] = "This is a verified test notification from the Multi-Carrier Tracking Engine."


@app.post("/api/v1/alerts/test", tags=["Alerts & Notifications"])
def test_alert(payload: AlertTestRequest):
    """Dispatches a test notification via Telegram or configured webhook."""
    notifier.send_alert_async(payload.title, payload.message, level="info")
    return {
        "status": "success",
        "message": "Test alert dispatched to background worker.",
        "telegram_configured": bool(notifier.telegram_bot_token and notifier.telegram_chat_id),
        "webhook_configured": bool(notifier.webhook_url)
    }


@app.get("/api/v1/system/problems", tags=["System Diagnostics"])
def get_system_problems():
    """
    Returns real-time runtime diagnostics and known system/architectural problems
    with severity, root cause, affected modules, and current mitigation status.
    """
    proxy_st = proxy_pool.get_status()
    cb_st = circuit_breaker.get_all_status()
    queue_data = master_ledger.get_tracking_queue_and_kpis()
    kpis = queue_data.get("kpis", {})
    ap_st = autopilot.get_status()

    problems = []

    # 1. Live Proxy / IP Rotation Status
    mode = proxy_st.get("mode", "off")
    if mode == "off":
        problems.append({
            "id": "RUNTIME-PROXY-OFF",
            "title": "Direct IP Mode Active (No Proxy Rotation)",
            "severity": "P0",
            "category": "runtime",
            "status": "ACTIVE_RISK",
            "affected": "bulk_tracker/proxy_pool.py, all 13 airline scrapers",
            "description": "Outbound tracking requests are currently using your single static machine IP. Continuous high-frequency scraping can trigger PerimeterX (Turkish), reCAPTCHA v3 (Saudia), or Akamai/Cloudflare (Emirates) IP blocks.",
            "mitigation": "Enable Tor SOCKS5 or Custom Residential Proxies in Settings, or use Safe Chunked Tracker with 2-7 min human-paced delays.",
        })
    elif mode == "tor" and not proxy_st.get("tor_available"):
        problems.append({
            "id": "RUNTIME-TOR-DOWN",
            "title": "Tor Mode Selected But Tor Daemon Unreachable",
            "severity": "P0",
            "category": "runtime",
            "status": "FAILING",
            "affected": "bulk_tracker/proxy_pool.py (ports 9050/9150)",
            "description": "Proxy mode is set to 'tor', but no local Tor SOCKS5 daemon is listening on 127.0.0.1:9050 or 9150. Requests are falling back to Direct IP.",
            "mitigation": "Start the local Tor service (`brew services start tor`) or switch proxy mode in Settings.",
        })
    elif mode == "free_pool" and proxy_st.get("healthy_proxies_count", 0) == 0:
        problems.append({
            "id": "RUNTIME-FREEPOOL-EMPTY",
            "title": "Free Proxy Pool Has 0 Healthy Proxies",
            "severity": "P1",
            "category": "runtime",
            "status": "DEGRADED",
            "affected": "bulk_tracker/proxy_pool.py",
            "description": "Free public proxy pool currently has 0 healthy nodes. Airline portals will time out or reject connections.",
            "mitigation": "Switch to Custom Residential Proxies, Tor, or Direct IP with Safe Chunked Tracking.",
        })

    # 2. Live Carrier Circuit Breakers
    degraded_carriers = [
        (code, info) for code, info in cb_st.items()
        if isinstance(info, dict) and info.get("state") in ("DEGRADED", "TRIPPED", "OPEN")
    ]
    for code, info in degraded_carriers:
        problems.append({
            "id": f"RUNTIME-CB-{code}",
            "title": f"Carrier Portal Degraded / Tripped: {code}",
            "severity": "P1",
            "category": "runtime",
            "status": info.get("state", "DEGRADED"),
            "affected": f"{code} scraper & bulk_tracker/circuit_breaker.py",
            "description": f"Consecutive failures: {info.get('consecutive_failures', 0)}. Last error: {info.get('last_error') or 'Unknown portal error'}. Fallback aggregator routing active: {info.get('fallback_active', False)}.",
            "mitigation": "Circuit breaker automatically reroutes to fallback aggregators and probes recovery after timeout.",
        })

    # 3. Live Unreachable / Unsupported AWBs
    unreachable_cnt = kpis.get("total_unreachable", 0)
    if unreachable_cnt > 0:
        problems.append({
            "id": "RUNTIME-UNREACHABLE-AWBS",
            "title": f"{unreachable_cnt} Unreachable / Unsupported AWBs in Quarantine",
            "severity": "P2",
            "category": "runtime",
            "status": "ATTENTION",
            "affected": "data/master_cargo_ledger.db (Table 3)",
            "description": f"There are currently {unreachable_cnt} AWB records marked UNREACHABLE, ERROR, NOT_FOUND, or SKIPPED (unsupported airline prefix).",
            "mitigation": "Inspect Table 3 in Auto Track or Masterdata -> Unreachable, verify airline prefix support, and click Retry for transient errors.",
        })

    # 4. AutoPilot Last Error
    if ap_st.get("last_error"):
        problems.append({
            "id": "RUNTIME-AUTOPILOT-ERR",
            "title": "Auto-Pilot Reported a Cycle Error",
            "severity": "P1",
            "category": "runtime",
            "status": "ERROR",
            "affected": "bulk_tracker/autopilot.py",
            "description": str(ap_st.get("last_error")),
            "mitigation": "Check Google Sheet URL accessibility and System Logs in Profile.",
        })

    # 5. Core Architectural & Scraper Risks (from system audit)
    arch_problems = [
        {
            "id": "ARCH-01",
            "title": "Anti-Bot Detection & IP Blacklisting Risk",
            "severity": "P0",
            "category": "architecture",
            "status": "MITIGATED_PARTIAL" if mode != "off" else "OPEN",
            "affected": "turkish_tracker, saudia_tracker, emirates_tracker, bulk_tracker/stealth.py",
            "description": "Airline portals (PerimeterX, Google reCAPTCHA v3, Akamai/Cloudflare) block repeated queries from static residential/VPS IPs within hours if concurrency or frequency is too high.",
            "mitigation": "Stealth headers & Playwright anti-detection scripts added; Safe Chunked Tracker enforces 2-7 min randomized cooldowns; Proxy Pool supports Tor & Custom Residential Proxies.",
        },
        {
            "id": "ARCH-02",
            "title": "Headless Chromium Memory Spikes & OOM Risk",
            "severity": "P0",
            "category": "architecture",
            "status": "MITIGATED",
            "affected": "bulk_tracker/stealth.py, bulk_tracker/engine.py, Playwright trackers",
            "description": "Each Chromium instance consumes 150-350MB RAM. Uncapped parallel browser workers can exhaust host RAM and trigger OS OOM Killer or leave zombie browser processes.",
            "mitigation": "BROWSER_CONCURRENCY_SEMAPHORE caps concurrent Chromium browsers to max 2, with low-memory flags and guaranteed cleanup.",
        },
        {
            "id": "ARCH-03",
            "title": "Unofficial Google Sheets XLSX Export Rate Limits (HTTP 429)",
            "severity": "P1",
            "category": "architecture",
            "status": "MITIGATED_PARTIAL",
            "affected": "bulk_tracker/google_sheets.py",
            "description": "Polling public `/export?format=xlsx` links without official Google Sheets API v4 Service Account credentials can trigger HTTP 429 rate limits and does not support two-way cell write-back.",
            "mitigation": "Exponential backoff and local caching implemented in google_sheets.py; official Sheets API v4 Service Account recommended for write-back.",
        },
        {
            "id": "ARCH-04",
            "title": "SQLite Concurrent Write Lock Contention",
            "severity": "P1",
            "category": "architecture",
            "status": "MITIGATED",
            "affected": "bulk_tracker/ledger.py, data/master_cargo_ledger.db",
            "description": "Background Auto-Pilot / Safe Runner writes occurring simultaneously with UI reads or exports can cause 'database is locked' errors under default SQLite journal mode.",
            "mitigation": "SQLite WAL mode (`PRAGMA journal_mode=WAL`), 15s `busy_timeout`, and `@sqlite_retry` decorator are active.",
        },
        {
            "id": "ARCH-05",
            "title": "Recycled AWB Numbers Trap (6-12 Month Reuse)",
            "severity": "P2",
            "category": "architecture",
            "status": "MITIGATED",
            "affected": "bulk_tracker/ledger.py (is_record_stale_or_recycled)",
            "description": "Airlines recycle 8-digit AWB serials every 6-12 months. Skipping any AWB marked DELIVERED forever would ignore new shipments reusing an old AWB.",
            "mitigation": "Records older than 60 days are automatically flagged as stale/recycled so new sheet appearances are re-tracked.",
        },
        {
            "id": "ARCH-06",
            "title": "Carrier Website DOM & API Breaking Changes",
            "severity": "P1",
            "category": "architecture",
            "status": "MITIGATED_PARTIAL",
            "affected": "All 13 *_tracker/client.py adapters",
            "description": "Airline portals frequently update HTML selectors, JSON payloads, or anti-bot gates without notice, causing silent scraping failures.",
            "mitigation": "CarrierCircuitBreaker monitors consecutive failures (trips at 5) and routes to fallback aggregators with Telegram/Webhook alerting.",
        },
    ]

    problems.extend(arch_problems)

    summary = {
        "total": len(problems),
        "p0_critical": sum(1 for p in problems if p["severity"] == "P0"),
        "p1_high": sum(1 for p in problems if p["severity"] == "P1"),
        "p2_medium": sum(1 for p in problems if p["severity"] == "P2"),
        "runtime_count": sum(1 for p in problems if p["category"] == "runtime"),
        "architecture_count": sum(1 for p in problems if p["category"] == "architecture"),
    }

    return {
        "status": "success",
        "summary": summary,
        "problems": problems,
        "live_diagnostics": {
            "proxy": proxy_st,
            "circuit_breakers": cb_st,
            "unreachable_count": unreachable_cnt,
            "autopilot_running": ap_st.get("is_running", False),
            "safe_runner_running": safe_runner.is_running,
        },
    }


@app.get("/api/v1/system/logs", tags=["System Diagnostics"])
def get_system_logs(lines: int = Query(120, ge=10, le=500)):
    """Returns recent lines from data/safe_tracker.log for the System Logs viewer."""
    log_file = PROJECT_ROOT / "data" / "safe_tracker.log"
    if not log_file.exists():
        return {"status": "success", "log_file": str(log_file), "lines": []}
    try:
        with open(log_file, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.read().splitlines()
        return {
            "status": "success",
            "log_file": str(log_file),
            "total_lines": len(all_lines),
            "lines": all_lines[-lines:],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read log file: {e}")


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def web_dashboard():
    """Enterprise Web Dashboard for Multi-Carrier Cargo Tracking (Single & Bulk Engine with Live Terminal Logs)."""
    template_path = PROJECT_ROOT / "templates" / "index.html"
    if not template_path.exists():
        raise HTTPException(status_code=500, detail="Dashboard template not found at templates/index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
