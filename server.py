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

sheets_tracker = GoogleSheetsTracker()
autopilot = AutoPilotManager(sheets_tracker, master_ledger)

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
turkish_client = TurkishCargoClient()
etihad_client = EtihadCargoClient()
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
    if cleaned.startswith("235"):
        return "turkish"
    if cleaned.startswith("607"):
        return "etihad"
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
    target_carrier = carrier if carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels", "turkish", "tk", "turkishcargo", "etihad", "ey", "etihadcargo") else detect_carrier(awb)

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
        else:
            res = ai_client.track(awb)
            return {"carrier": "Air India Cargo", "carrier_code": "098", "data": res.model_dump() if hasattr(res, "model_dump") else res.dict()}
    except (AWBNotFoundException, EmiratesShipmentNotFoundError, KuwaitShipmentNotFoundError, ParcelsShipmentNotFoundError, VirginShipmentNotFoundError, QatarShipmentNotFoundError, CargoFlashShipmentNotFoundError, NeosShipmentNotFoundError, IndigoShipmentNotFoundError, TurkishShipmentNotFoundError, EtihadShipmentNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except (AirIndiaTrackerException, EmiratesTrackingError, KuwaitTrackingError, ParcelsTrackingError, VirginTrackingError, QatarTrackingError, CargoFlashTrackingError, NeosTrackingError, IndigoTrackingError, TurkishTrackingError, EtihadTrackingError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal tracking error: {e}")


@app.post("/api/v1/track/batch", tags=["Tracking"])
def track_batch(payload: BatchTrackRequest):
    """Track multiple AWBs concurrently across multiple carriers."""
    results = {}
    for awb in payload.awbs:
        target = payload.carrier if payload.carrier in ("airindia", "lufthansa", "emirates", "kuwait", "britishairways", "virgin", "virginatlantic", "qatar", "qrcargo", "cargoflash", "egyptair", "neos", "wcs", "neosair", "indigo", "6e", "indigocargo", "parcels", "turkish", "tk", "turkishcargo", "etihad", "ey", "etihadcargo") else detect_carrier(awb)
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
    # Automatically persist/update master ledger without duplicates
    master_ledger.upsert_batch(summary.records)
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
    workers: Optional[int] = 5
    recheck_delivered: Optional[bool] = False


class AutoPilotConfigRequest(BaseModel):
    url: Optional[str] = None
    sheet_name: Optional[str] = None
    target_col: Optional[str] = "H"
    start_row: Optional[int] = 110
    scan_all_tabs: Optional[bool] = False
    interval_minutes: Optional[int] = 30
    workers: Optional[int] = 5


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
            workers=payload.workers or 5,
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
