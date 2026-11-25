"""
Production-grade Google Sheets Auto-Sync & Lifecycle Tracking Engine.
Features:
- Extracts spreadsheet ID from any Google Docs URL.
- Auto-inspects sheet structure: tabs, columns, header rows, and cell coordinates (e.g. H19-H24).
- Extracts AWB numbers from designated column (default Column H) along with Customer, Destination, Packages, and Weights.
- Lifecycle tracking:
  - Continuously tracks active 'On-The-Way' shipments (In-Transit, Departed, Arrived, Booked).
  - Skips redundant queries for shipments already marked 'DELIVERED' in Master Ledger.
  - Automatically updates SQLite Master Cargo Ledger with zero duplicate entries.
- Graceful error messaging for restricted Google Sheets (401/403).
"""

import io
import re
import time
import logging
import urllib.request
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any, Callable
from pathlib import Path

import openpyxl

from bulk_tracker.models import UnifiedTrackingRecord
from bulk_tracker.engine import BulkCargoTracker
from bulk_tracker.ledger import MasterLedgerManager, DEFAULT_DB_PATH
from bulk_tracker.extractor import KNOWN_GLOBAL_IATA_PREFIXES, CARRIER_PREFIXES
from bulk_tracker.proxy_pool import proxy_pool
from bulk_tracker.stealth import StealthEngine

logger = logging.getLogger("bulk_tracker.google_sheets")


class GoogleSheetError(Exception):
    """Base exception for Google Sheets integration."""
    pass


class GoogleSheetAccessError(GoogleSheetError):
    """Raised when Google Sheet permissions are restricted (401/403)."""
    pass


class GoogleSheetNotFoundError(GoogleSheetError):
    """Raised when Google Sheet or Tab is not found."""
    pass


class GoogleSheetsTracker:
    """
    Automated Google Sheets ingestion and shipment lifecycle engine.
    """

    def __init__(self, db_path: Optional[Path] = None, timeout_sec: int = 25):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.ledger = MasterLedgerManager(self.db_path)
        self.timeout_sec = timeout_sec
        self._cache: Dict[str, Tuple[float, bytes]] = {}
        self.cache_ttl_sec: int = 120  # 2 minute cache to prevent Google rate limits

    @staticmethod
    def parse_sheet_id(url_or_id: str) -> str:
        """
        Extracts spreadsheet ID from URL or returns clean ID.
        e.g. 'https://docs.google.com/spreadsheets/d/1OsdRGPcS2fLa8pI6C8rTh8eOYQMRRzhTVM2pOaN4h9U/edit?usp=sharing'
        -> '1OsdRGPcS2fLa8pI6C8rTh8eOYQMRRzhTVM2pOaN4h9U'
        """
        raw = str(url_or_id or "").strip()
        m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw)
        if m:
            return m.group(1)
        # If passed without URL prefix
        clean = re.sub(r"[^a-zA-Z0-9-_]", "", raw)
        if len(clean) >= 20:
            return clean
        raise ValueError(f"Invalid Google Sheet URL or ID: '{url_or_id}'. Expected standard Google Docs spreadsheet link.")

    def fetch_workbook(self, sheet_id: str, bypass_cache: bool = False) -> openpyxl.Workbook:
        """
        Downloads Google Sheet via XLSX export and loads into openpyxl Workbook.
        Features anti-429 exponential backoff, rotating User-Agent, in-memory caching,
        and proxy support.
        """
        now = time.time()
        if not bypass_cache and sheet_id in self._cache:
            ts, cached_bytes = self._cache[sheet_id]
            if now - ts < self.cache_ttl_sec:
                logger.debug(f"[GoogleSheets] Returning cached workbook for {sheet_id} ({int(now - ts)}s old)")
                return openpyxl.load_workbook(io.BytesIO(cached_bytes), data_only=True)

        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx"
        headers = StealthEngine.get_stealth_headers(referer="https://docs.google.com/")

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                proxy_str = proxy_pool.get_proxy()
                opener = urllib.request.build_opener()
                if proxy_str:
                    proxy_handler = urllib.request.ProxyHandler({"http": proxy_str, "https": proxy_str})
                    opener = urllib.request.build_opener(proxy_handler)

                req = urllib.request.Request(export_url, headers=headers)
                with opener.open(req, timeout=self.timeout_sec) as response:
                    content = response.read()
                    if not content or len(content) < 500:
                        raise GoogleSheetError("Downloaded spreadsheet payload is empty or corrupted.")

                    # Cache successful download
                    self._cache[sheet_id] = (time.time(), content)
                    if proxy_str:
                        proxy_pool.report_success(proxy_str)
                    return openpyxl.load_workbook(io.BytesIO(content), data_only=True)

            except urllib.error.HTTPError as he:
                last_error = he
                if he.code in (401, 403):
                    raise GoogleSheetAccessError(
                        f"Google Sheet access is restricted (HTTP {he.code} Unauthorized). "
                        "Please open the sheet in Google Drive -> click 'Share' at the top right -> "
                        "under 'General access', change from 'Restricted' to 'Anyone with the link can view' (or Editor), then retry."
                    )
                elif he.code == 404:
                    raise GoogleSheetNotFoundError(f"Google Sheet not found (HTTP 404). Please verify the spreadsheet ID: '{sheet_id}'.")
                elif he.code == 429:
                    wait_time = (2 ** attempt) + 1.0
                    logger.warning(f"[GoogleSheets] HTTP 429 Rate Limit from Google. Backing off {wait_time}s (attempt {attempt + 1}/{max_attempts})...")
                    time.sleep(wait_time)
                else:
                    logger.warning(f"[GoogleSheets] HTTP Error {he.code}: {he.reason}")
                    time.sleep(1.0)
            except Exception as e:
                last_error = e
                logger.warning(f"[GoogleSheets] Network error on attempt {attempt + 1}: {e}")
                time.sleep(1.5)

        # If cache exists (even expired), use it as fallback before crashing
        if sheet_id in self._cache:
            logger.info(f"[GoogleSheets] Network failed; falling back to last good cached workbook for {sheet_id}")
            _, cached_bytes = self._cache[sheet_id]
            return openpyxl.load_workbook(io.BytesIO(cached_bytes), data_only=True)

        raise GoogleSheetError(f"Failed to fetch Google Sheet after retries: {last_error}")

    @staticmethod
    def _col_letter_to_index(col_str: str) -> int:
        """Convert 'A'->1, 'H'->8, etc."""
        col = col_str.strip().upper()
        if col.isdigit():
            return int(col)
        exp = 0
        idx = 0
        for char in reversed(col):
            idx += (ord(char) - ord("A") + 1) * (26 ** exp)
            exp += 1
        return idx

    @staticmethod
    def _col_index_to_letter(idx: int) -> str:
        return openpyxl.utils.get_column_letter(idx)

    def _auto_detect_columns(self, sheet: Any) -> Tuple[int, Dict[str, int]]:
        """
        Detects header row and column mapping:
        awb, customer, destination, iata, pkg, gr_wt, ch_wt, date
        """
        col_map: Dict[str, int] = {}
        best_header_row = 1
        max_matches = 0

        # Scan rows 1 through 25 to find header row
        for r in range(1, min(sheet.max_row + 1, 26)):
            row_matches = 0
            temp_map: Dict[str, int] = {}
            for c in range(1, min(sheet.max_column + 1, 30)):
                val = str(sheet.cell(row=r, column=c).value or "").strip().upper()
                if not val:
                    continue

                if ("AWB" in val and "DRAFT" not in val) or val == "AWB NO" or val == "AIR WAYBILL":
                    temp_map["awb"] = c
                    row_matches += 1
                elif "CUSTOMER" in val or "CLIENT" in val or "SHIPPER" in val:
                    temp_map["customer"] = c
                    row_matches += 1
                elif "DEST" in val or "AIRPORT" in val:
                    temp_map["dest"] = c
                    row_matches += 1
                elif "IATA" in val or "AGENT" in val:
                    temp_map["iata"] = c
                    row_matches += 1
                elif "PKG" in val or "PIECE" in val or "PCS" in val:
                    temp_map["pkg"] = c
                    row_matches += 1
                elif ("GR" in val and "WT" in val) or "GROSS" in val:
                    temp_map["gr_wt"] = c
                    row_matches += 1
                elif ("CH" in val and "WT" in val) or "CHARGEABLE" in val:
                    temp_map["ch_wt"] = c
                    row_matches += 1
                elif "DATE" in val:
                    temp_map["date"] = c
                    row_matches += 1

            if row_matches > max_matches:
                max_matches = row_matches
                best_header_row = r
                col_map = temp_map

        # Defaults if not explicitly detected
        if "awb" not in col_map:
            col_map["awb"] = 8  # Col H
        if "customer" not in col_map:
            col_map["customer"] = 3  # Col C
        if "dest" not in col_map:
            col_map["dest"] = 6  # Col F
        if "iata" not in col_map:
            col_map["iata"] = 7  # Col G
        if "pkg" not in col_map:
            col_map["pkg"] = 10  # Col J
        if "gr_wt" not in col_map:
            col_map["gr_wt"] = 11  # Col K
        if "ch_wt" not in col_map:
            col_map["ch_wt"] = 12  # Col L

        return best_header_row, col_map

    def inspect_sheet(
        self,
        url_or_id: str,
        sheet_name: Optional[str] = None,
        target_col: str = "H",
        start_row: Optional[int] = None,
        scan_all_tabs: bool = False,
    ) -> Dict[str, Any]:
        """
        Inspects Google Sheet structure: tabs, detected columns, and previews AWBs.
        Supports start_row (e.g. 110 for H110 downwards) and scan_all_tabs.
        """
        sheet_id = self.parse_sheet_id(url_or_id)
        wb = self.fetch_workbook(sheet_id)

        all_tabs = wb.sheetnames
        selected_sheet_name = sheet_name if (sheet_name and sheet_name in all_tabs) else all_tabs[-1]
        sheet = wb[selected_sheet_name]

        header_row, col_map = self._auto_detect_columns(sheet)

        # Allow user-specified target column override for AWB
        awb_col_idx = self._col_letter_to_index(target_col) if target_col else col_map["awb"]

        readable_cols = {
            "awb": f"Column {self._col_index_to_letter(awb_col_idx)} (AWB NO)",
            "customer": f"Column {self._col_index_to_letter(col_map['customer'])} (CUSTOMER)",
            "dest": f"Column {self._col_index_to_letter(col_map['dest'])} (DESTINATION)",
            "iata": f"Column {self._col_index_to_letter(col_map['iata'])} (IATA)",
            "pkg": f"Column {self._col_index_to_letter(col_map['pkg'])} (PKG/PIECES)",
            "gr_wt": f"Column {self._col_index_to_letter(col_map['gr_wt'])} (GROSS WT)",
            "ch_wt": f"Column {self._col_index_to_letter(col_map['ch_wt'])} (CH WT)",
        }

        # Effective starting row (default to header_row + 1, or user's start_row e.g. 110)
        effective_start = int(start_row) if (start_row and int(start_row) > 0) else (header_row + 1)

        # Scan for AWBs
        records = []
        carrier_counts: Dict[str, int] = {}

        tabs_to_scan = all_tabs if (scan_all_tabs or sheet_name in ("ALL", "all", "*")) else [selected_sheet_name]

        for tab in tabs_to_scan:
            curr_sheet = wb[tab]
            curr_h_row, curr_cmap = self._auto_detect_columns(curr_sheet)
            c_awb_idx = self._col_letter_to_index(target_col) if target_col else curr_cmap["awb"]
            c_start = int(start_row) if (start_row and int(start_row) > 0) else (curr_h_row + 1)

            for r in range(c_start, curr_sheet.max_row + 1):
                val = str(curr_sheet.cell(row=r, column=c_awb_idx).value or "").strip()
                digits = re.sub(r"[^\d]", "", val)
                clean_digits = ""
                formatted_awb = ""

                if len(digits) == 11:
                    clean_digits = digits
                    formatted_awb = f"{digits[:3]}-{digits[3:]}"
                elif len(digits) == 12 and digits.startswith(("020", "235", "176", "098", "157", "703", "229", "125", "932", "077", "312", "065", "205")):
                    # Normalize 12-digit AWBs with trailing check digit (e.g. 020-037700970 -> 020-03770097)
                    clean_digits = digits[:11]
                    formatted_awb = f"{digits[:3]}-{digits[3:11]}"
                elif len(digits) == 8 and digits.isdigit():
                    clean_digits = digits
                    formatted_awb = digits

                if clean_digits:
                    prefix = clean_digits[:3] if len(clean_digits) == 11 else "098"
                    c_val = CARRIER_PREFIXES.get(prefix, KNOWN_GLOBAL_IATA_PREFIXES.get(prefix, f"Airline ({prefix})"))
                    c_name = f"{c_val[0]} ({c_val[1]})" if isinstance(c_val, tuple) else str(c_val)
                    carrier_counts[c_name] = carrier_counts.get(c_name, 0) + 1

                    cust = str(curr_sheet.cell(row=r, column=curr_cmap["customer"]).value or "").strip()
                    dest = str(curr_sheet.cell(row=r, column=curr_cmap["dest"]).value or "").strip()
                    iata = str(curr_sheet.cell(row=r, column=curr_cmap["iata"]).value or "").strip()
                    pkg = curr_sheet.cell(row=r, column=curr_cmap["pkg"]).value
                    gr_wt = curr_sheet.cell(row=r, column=curr_cmap["gr_wt"]).value

                    records.append({
                        "tab": tab,
                        "row": r,
                        "cell": f"{self._col_index_to_letter(c_awb_idx)}{r}",
                        "raw_awb": val,
                        "awb": formatted_awb,
                        "clean_awb": clean_digits,
                        "carrier": c_name,
                        "prefix": prefix,
                        "customer": cust or "General Freight",
                        "destination": dest or "---",
                        "iata": iata or "---",
                        "packages": pkg,
                        "gross_weight": gr_wt,
                    })

        return {
            "status": "success",
            "sheet_id": sheet_id,
            "all_tabs": all_tabs,
            "selected_tab": "ALL_TABS" if (scan_all_tabs or sheet_name in ("ALL", "all", "*")) else selected_sheet_name,
            "start_row": effective_start,
            "header_row": header_row,
            "awb_column": self._col_index_to_letter(awb_col_idx),
            "column_mapping": readable_cols,
            "total_sheet_rows": sheet.max_row,
            "valid_awbs_found": len(records),
            "carrier_distribution": carrier_counts,
            "preview_records": records[:30],
        }

    def extract_awb_manifest(
        self,
        url_or_id: str,
        sheet_name: Optional[str] = None,
        target_col: str = "H",
        start_row: Optional[int] = None,
        scan_all_tabs: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Extracts all AWB items with associated metadata from sheet.
        Supports start_row (e.g. 110 for H110 downwards) and scan_all_tabs.
        """
        info = self.inspect_sheet(
            url_or_id,
            sheet_name=sheet_name,
            target_col=target_col,
            start_row=start_row,
            scan_all_tabs=scan_all_tabs,
        )
        wb = self.fetch_workbook(info["sheet_id"])

        tabs_to_scan = wb.sheetnames if (scan_all_tabs or sheet_name in ("ALL", "all", "*")) else [info["selected_tab"]]
        items = []

        for tab in tabs_to_scan:
            sheet = wb[tab]
            header_row, col_map = self._auto_detect_columns(sheet)
            awb_col_idx = self._col_letter_to_index(target_col) if target_col else col_map["awb"]
            c_start = int(start_row) if (start_row and int(start_row) > 0) else (header_row + 1)

            for r in range(c_start, sheet.max_row + 1):
                val = str(sheet.cell(row=r, column=awb_col_idx).value or "").strip()
                digits = re.sub(r"[^\d]", "", val)
                clean_digits = ""
                formatted_awb = ""

                if len(digits) == 11:
                    clean_digits = digits
                    formatted_awb = f"{digits[:3]}-{digits[3:]}"
                elif len(digits) == 12 and digits.startswith(("020", "235", "176", "098", "157", "703", "229", "125", "932", "077", "312", "065", "205")):
                    clean_digits = digits[:11]
                    formatted_awb = f"{digits[:3]}-{digits[3:11]}"
                elif len(digits) == 8 and digits.isdigit():
                    clean_digits = digits
                    formatted_awb = digits

                if clean_digits:
                    cust = str(sheet.cell(row=r, column=col_map["customer"]).value or "").strip()
                    dest = str(sheet.cell(row=r, column=col_map["dest"]).value or "").strip()
                    iata = str(sheet.cell(row=r, column=col_map["iata"]).value or "").strip()
                    pkg = sheet.cell(row=r, column=col_map["pkg"]).value
                    gr_wt = sheet.cell(row=r, column=col_map["gr_wt"]).value
                    ch_wt = sheet.cell(row=r, column=col_map["ch_wt"]).value

                    items.append({
                        "tab": tab,
                        "row": r,
                        "cell": f"{self._col_index_to_letter(awb_col_idx)}{r}",
                        "raw_awb": val,
                        "formatted_awb": formatted_awb,
                        "clean_awb": clean_digits,
                        "customer_name": cust or "General Cargo",
                        "destination": dest or "---",
                        "iata_agent": iata or "---",
                        "pkg_pieces": pkg,
                        "gross_weight": gr_wt,
                        "chargeable_weight": ch_wt,
                    })

        return items

    def sync_and_track_lifecycle(
        self,
        url_or_id: str,
        sheet_name: Optional[str] = None,
        target_col: str = "H",
        start_row: Optional[int] = None,
        scan_all_tabs: bool = False,
        workers: int = 5,
        recheck_delivered: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes complete lifecycle tracking from Google Sheet:
        1. Reads AWBs and metadata from the sheet (supports start_row e.g. 110, and multi-tab).
        2. Checks Master Cargo Ledger: If already DELIVERED, skips re-querying airline!
        3. For active 'On-The-Way' shipments, queries live airline trackers concurrently.
        4. Upserts Master Cargo Ledger without duplicate rows.
        5. Returns structured report categorized into 'Active / On The Way' vs 'Delivered Archive'.
        """
        t0 = time.time()
        sheet_id = self.parse_sheet_id(url_or_id)
        manifest = self.extract_awb_manifest(
            sheet_id,
            sheet_name=sheet_name,
            target_col=target_col,
            start_row=start_row,
            scan_all_tabs=scan_all_tabs,
        )
        total_items = len(manifest)

        logger.info(f"Loaded {total_items} AWBs from Google Sheet tab '{sheet_name or 'Default'}' (Col {target_col}, start_row={start_row})")

        tracker = BulkCargoTracker(max_global_workers=workers)

        # Categorize into already delivered vs needs tracking
        needs_tracking: List[Dict[str, Any]] = []
        already_delivered_records: List[Dict[str, Any]] = []

        for item in manifest:
            existing = self.ledger.get_record_by_awb(item["clean_awb"])
            is_recycled = self.ledger.is_record_stale_or_recycled(
                existing, max_delivery_age_days=60, current_tab_month=sheet_name
            )
            if existing and existing.get("status") == "DELIVERED" and not recheck_delivered and not is_recycled:
                already_delivered_records.append(existing)
            else:
                if is_recycled and existing and existing.get("status") == "DELIVERED":
                    logger.info(f"[Lifecycle] AWB {item['formatted_awb']} was delivered >60 days ago. Treating as recycled serial and re-tracking!")
                needs_tracking.append(item)

        logger.info(f"LifeCycle: {len(already_delivered_records)} already DELIVERED (skipped). {len(needs_tracking)} Active / New to track.")

        # Dispatch tracking for active items
        tracked_records: List[Dict[str, Any]] = []
        if needs_tracking:
            awb_list = [item["formatted_awb"] for item in needs_tracking]
            bulk_summary = tracker.track_batch(awb_list)

            # Map sheet metadata (customer, destination, weights) into each tracked record
            for rec in bulk_summary.records:
                clean_k = self.ledger._clean_awb_key(rec.awb)
                matching_item = next((i for i in needs_tracking if i["clean_awb"] == clean_k), None)

                # Enrich with Google Sheet customer & destination if missing
                if matching_item:
                    if not rec.consignee_issued_to or rec.consignee_issued_to in ("---", "None", ""):
                        rec.consignee_issued_to = matching_item["customer_name"]
                    if (not rec.destination or rec.destination == "---") and matching_item["destination"] != "---":
                        rec.destination = matching_item["destination"]
                    if not rec.pieces and matching_item["pkg_pieces"] not in (None, "", "DONE"):
                        try:
                            rec.pieces = int(float(str(matching_item["pkg_pieces"])))
                        except Exception:
                            pass
                    if (not rec.weight or rec.weight == "---") and matching_item["gross_weight"] not in (None, ""):
                        rec.weight = f"{matching_item['gross_weight']} kg"

                # Upsert into Master Cargo Ledger
                upserted = self.ledger.upsert_record(rec)
                tracked_records.append(upserted)

        elapsed = round(time.time() - t0, 2)

        # Bucket results into Lifecycle
        all_records = self.ledger.get_all_records(limit=5000)
        manifest_keys = {item["clean_awb"] for item in manifest}
        sheet_records = [r for r in all_records if r["awb_clean"] in manifest_keys]

        active_on_the_way = [r for r in sheet_records if r.get("status") != "DELIVERED"]
        delivered_archive = [r for r in sheet_records if r.get("status") == "DELIVERED"]

        return {
            "status": "success",
            "execution_time_sec": elapsed,
            "total_sheet_awbs": total_items,
            "already_delivered_skipped": len(already_delivered_records),
            "newly_tracked_count": len(tracked_records),
            "active_on_the_way_count": len(active_on_the_way),
            "delivered_count": len(delivered_archive),
            "active_shipments": active_on_the_way,
            "delivered_shipments": delivered_archive,
            "all_records": sheet_records,
        }
