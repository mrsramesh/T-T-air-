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

    def fetch_workbook(self, sheet_id: str, bypass_cache: bool = True) -> openpyxl.Workbook:
        """
        Downloads live Google Sheet via XLSX export and loads into openpyxl Workbook.
        Always fetches fresh data by default (with cache-busting query param and no-cache headers)
        so edits in Google Sheet appear immediately. In-memory cache is used ONLY as an
        offline/429 fallback if Google cannot be reached.
        """
        now = time.time()
        if not bypass_cache and sheet_id in self._cache:
            ts, cached_bytes = self._cache[sheet_id]
            if now - ts < self.cache_ttl_sec:
                logger.debug(f"[GoogleSheets] Returning cached workbook for {sheet_id} ({int(now - ts)}s old)")
                return openpyxl.load_workbook(io.BytesIO(cached_bytes), data_only=True)

        # Cache-buster query param + no-cache headers prevent Google CDN from serving stale XLSX
        export_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=xlsx&_cb={int(now)}"
        headers = StealthEngine.get_stealth_headers(referer="https://docs.google.com/")
        headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        headers["Pragma"] = "no-cache"

        max_attempts = 3
        last_error = None

        for attempt in range(max_attempts):
            try:
                import requests as req_lib
                resp = req_lib.get(export_url, headers=headers, timeout=self.timeout_sec)
                if resp.status_code in (401, 403):
                    raise GoogleSheetAccessError(
                        f"Google Sheet access is restricted (HTTP {resp.status_code} Unauthorized). "
                        "Please open the sheet in Google Drive -> click 'Share' at the top right -> "
                        "under 'General access', change from 'Restricted' to 'Anyone with the link can view' (or Editor), then retry."
                    )
                elif resp.status_code == 404:
                    raise GoogleSheetNotFoundError(f"Google Sheet not found (HTTP 404). Please verify the spreadsheet ID: '{sheet_id}'.")
                elif resp.status_code == 429:
                    wait_time = (2 ** attempt) + 1.0
                    logger.warning(f"[GoogleSheets] HTTP 429 Rate Limit from Google. Backing off {wait_time}s (attempt {attempt + 1}/{max_attempts})...")
                    time.sleep(wait_time)
                    continue
                elif resp.status_code >= 400:
                    raise GoogleSheetError(f"Failed to fetch Google Sheet: HTTP {resp.status_code} {resp.reason}")

                content = resp.content
                if not content or len(content) < 500:
                    raise GoogleSheetError("Downloaded spreadsheet payload is empty or corrupted.")

                self._cache[sheet_id] = (time.time(), content)
                return openpyxl.load_workbook(io.BytesIO(content), data_only=True)

            except (GoogleSheetAccessError, GoogleSheetNotFoundError):
                raise
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

    @staticmethod
    def _resolve_tabs_to_scan(
        wb: Any,
        sheet_name: Optional[str],
        scan_all_tabs: bool,
        selected_sheet_name: str,
    ) -> List[str]:
        """Returns ordered list of tabs to scan, respecting starting tab when scan_all_tabs=True."""
        all_tabs = list(wb.sheetnames)
        if not (scan_all_tabs or sheet_name in ("ALL", "all", "*")):
            return [selected_sheet_name]
        if sheet_name and sheet_name not in ("ALL", "all", "*"):
            target_norm = re.sub(r"[^a-z0-9]", "", sheet_name.strip().lower())
            for idx_t, t_name in enumerate(all_tabs):
                if t_name.strip().lower() == sheet_name.strip().lower() or re.sub(r"[^a-z0-9]", "", t_name.strip().lower()) == target_norm:
                    return all_tabs[idx_t:]
        return all_tabs

    @staticmethod
    def _find_matching_tab(all_tabs: List[str], sheet_name: Optional[str]) -> str:
        if sheet_name:
            target_norm = re.sub(r"[^a-z0-9]", "", sheet_name.strip().lower())
            for t in all_tabs:
                if t.strip().lower() == sheet_name.strip().lower() or re.sub(r"[^a-z0-9]", "", t.strip().lower()) == target_norm:
                    return t
        return all_tabs[-1]

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
        Supports start_row (e.g. 110 for H110 downwards), starting tab, and scan_all_tabs.
        """
        sheet_id = self.parse_sheet_id(url_or_id)
        wb = self.fetch_workbook(sheet_id)

        all_tabs = wb.sheetnames
        selected_sheet_name = self._find_matching_tab(all_tabs, sheet_name)
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

        tabs_to_scan = self._resolve_tabs_to_scan(wb, sheet_name, scan_all_tabs, selected_sheet_name)

        for tab_pos, tab in enumerate(tabs_to_scan):
            curr_sheet = wb[tab]
            curr_h_row, curr_cmap = self._auto_detect_columns(curr_sheet)
            c_awb_idx = self._col_letter_to_index(target_col) if target_col else curr_cmap["awb"]
            if start_row and int(start_row) > 0 and (tab_pos == 0 or not sheet_name or sheet_name in ("ALL", "all", "*")):
                c_start = int(start_row)
            else:
                c_start = curr_h_row + 1

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
            "preview_records": records[:1000],
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
        start_tab_idx = 0
        if scan_all_tabs and sheet_name and sheet_name not in ("ALL", "all", "*"):
            target_norm = re.sub(r"[^a-z0-9]", "", sheet_name.strip().lower())
            for idx_t, t_name in enumerate(wb.sheetnames):
                if t_name.strip().lower() == sheet_name.strip().lower() or re.sub(r"[^a-z0-9]", "", t_name.strip().lower()) == target_norm:
                    start_tab_idx = idx_t
                    break
            tabs_to_scan = wb.sheetnames[start_tab_idx:]

        items = []

        for tab_pos, tab in enumerate(tabs_to_scan):
            sheet = wb[tab]
            header_row, col_map = self._auto_detect_columns(sheet)
            awb_col_idx = self._col_letter_to_index(target_col) if target_col else col_map["awb"]
            # Apply start_row to the starting tab (or all tabs if no specific starting tab was given);
            # future tabs added AFTER the starting tab are scanned from header_row + 1 downwards.
            if start_row and int(start_row) > 0 and (tab_pos == 0 or not sheet_name or sheet_name in ("ALL", "all", "*")):
                c_start = int(start_row)
            else:
                c_start = header_row + 1

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
            # Always sync latest Google Sheet metadata (customer, dest, pieces, weight) into existing DB records
            self.ledger.sync_sheet_metadata(
                clean_awb=item["clean_awb"],
                customer_name=item.get("customer_name"),
                destination=item.get("destination"),
                pkg_pieces=item.get("pkg_pieces"),
                gross_weight=item.get("gross_weight"),
            )

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
            "active_tracked_count": len(tracked_records),
            "active_on_the_way_count": len(active_on_the_way),
            "delivered_count": len(delivered_archive),
            "active_shipments": active_on_the_way,
            "delivered_shipments": delivered_archive,
            "all_records": sheet_records,
        }

    def compute_manifest_signature(
        self,
        url_or_id: str,
        sheet_name: Optional[str] = None,
        target_col: str = "H",
        start_row: Optional[int] = None,
        scan_all_tabs: bool = False,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Fetches live Google Sheet and computes a deterministic SHA-256 signature of all rows.
        Used by AutoPilot's Smart Sheet Watcher to detect sheet edits with ZERO airline API calls.
        """
        import hashlib
        import json

        sheet_id = self.parse_sheet_id(url_or_id)
        manifest = self.extract_awb_manifest(
            sheet_id,
            sheet_name=sheet_name,
            target_col=target_col,
            start_row=start_row,
            scan_all_tabs=scan_all_tabs,
        )
        canonical = [
            (
                i.get("tab"),
                i.get("row"),
                i.get("clean_awb"),
                i.get("customer_name"),
                i.get("destination"),
                str(i.get("pkg_pieces")),
                str(i.get("gross_weight")),
            )
            for i in manifest
        ]
        sig = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()
        return sig, manifest

    def _compute_manifest_sig_only(self, manifest: List[Dict[str, Any]], tabs: List[str]) -> str:
        import hashlib
        import json
        canonical = {
            "tabs": sorted(tabs),
            "rows": [
                (
                    i.get("tab"),
                    i.get("row"),
                    i.get("clean_awb"),
                    i.get("customer_name"),
                    i.get("destination"),
                    str(i.get("pkg_pieces")),
                    str(i.get("gross_weight")),
                )
                for i in manifest
            ],
        }
        return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()

    def scan_enabled_sheets(self) -> Dict[str, Any]:
        """
        Reads all ENABLED Google Sheets from `sheet_sources`, detects new tabs & new rows
        after each sheet's start_row, and registers any new AWBs into `master_awb_ledger`
        with ZERO airline API calls.
        """
        enabled_sheets = self.ledger.list_sheet_sources(enabled_only=True)
        total_new_awbs = 0
        new_tabs_detected: List[Dict[str, Any]] = []
        changed_sheets: List[str] = []
        sheet_summaries: List[Dict[str, Any]] = []

        for src in enabled_sheets:
            sid = src["id"]
            label = src["label"]
            try:
                info = self.inspect_sheet(
                    src["url"],
                    sheet_name=src.get("sheet_name"),
                    target_col=src.get("target_col") or "H",
                    start_row=src.get("start_row") or 110,
                    scan_all_tabs=bool(src.get("scan_all_tabs", True)),
                )
                all_tabs = info.get("all_tabs") or info.get("tabs") or []
                prev_tabs = set(src.get("known_tabs") or [])
                added_tabs = [t for t in all_tabs if t not in prev_tabs] if prev_tabs else []

                manifest = self.extract_awb_manifest(
                    src["url"],
                    sheet_name=src.get("sheet_name"),
                    target_col=src.get("target_col") or "H",
                    start_row=src.get("start_row") or 110,
                    scan_all_tabs=bool(src.get("scan_all_tabs", True)),
                )

                new_in_sheet = 0
                for item in manifest:
                    is_new = self.ledger.register_sheet_awb_stub(
                        clean_awb=item["clean_awb"],
                        formatted_awb=item["formatted_awb"],
                        customer_name=item.get("customer_name"),
                        destination=item.get("destination"),
                        pkg_pieces=item.get("pkg_pieces"),
                        gross_weight=item.get("gross_weight"),
                        source_sheet_id=src["sheet_id"],
                        source_sheet_label=label,
                        source_tab=item.get("tab"),
                        source_cell=item.get("cell"),
                    )
                    if is_new:
                        new_in_sheet += 1

                total_new_awbs += new_in_sheet
                self.ledger.prune_stale_sheet_stubs(
                    source_sheet_id=src["sheet_id"],
                    valid_clean_awbs=[i["clean_awb"] for i in manifest],
                )
                new_sig = self._compute_manifest_sig_only(manifest, all_tabs)
                has_changed = bool(src.get("last_signature") and new_sig != src.get("last_signature"))
                if has_changed or added_tabs or new_in_sheet > 0:
                    changed_sheets.append(label)

                if added_tabs:
                    new_tabs_detected.append({"sheet": label, "tabs": added_tabs})

                self.ledger.update_sheet_source_sync_state(
                    source_id=sid,
                    last_signature=new_sig,
                    known_tabs=all_tabs,
                    last_row_count=len(manifest),
                    last_new_today=new_in_sheet,
                    synced=True,
                    last_error=None,
                )
                sheet_summaries.append({
                    "id": sid,
                    "label": label,
                    "sheet_id": src["sheet_id"],
                    "rows_found": len(manifest),
                    "new_awbs": new_in_sheet,
                    "tabs_count": len(all_tabs),
                    "added_tabs": added_tabs,
                    "changed": has_changed,
                    "error": None,
                })
            except Exception as e:
                err = str(e)
                logger.warning(f"[MultiSheet] Error scanning '{label}': {err}")
                self.ledger.update_sheet_source_sync_state(source_id=sid, last_error=err)
                sheet_summaries.append({
                    "id": sid,
                    "label": label,
                    "sheet_id": src["sheet_id"],
                    "rows_found": 0,
                    "new_awbs": 0,
                    "tabs_count": 0,
                    "added_tabs": [],
                    "changed": False,
                    "error": err,
                })

        return {
            "enabled_count": len(enabled_sheets),
            "total_new_awbs": total_new_awbs,
            "changed_sheets": changed_sheets,
            "new_tabs_detected": new_tabs_detected,
            "sheets": sheet_summaries,
        }

    def sync_all_enabled_sheets(
        self,
        workers: int = 1,
        track_live: bool = True,
    ) -> Dict[str, Any]:
        """
        1. Scans all enabled Google Sheets (registering new entries after start_row & new tabs).
        2. Collects the unified Final Active Tracking List (new from sheets + undelivered from central ledger).
        3. If track_live=True, tracks all undelivered AWBs via BulkCargoTracker and moves DELIVERED ones
           out of the Active Tracking List into the Delivered Report.
        """
        t0 = time.time()
        scan_res = self.scan_enabled_sheets()

        newly_tracked = 0
        newly_delivered = 0

        if track_live:
            active_records = self.ledger.get_active_shipments(limit=5000)
            # Exclude SKIPPED (unsupported carrier prefix) from repeated airline hits
            to_track = [
                r for r in active_records
                if (r.get("status") or "").upper() not in ("DELIVERED", "SKIPPED")
            ]
            if to_track:
                awb_list = [r.get("awb_no") or r.get("awb_clean") for r in to_track]
                tracker = BulkCargoTracker(max_global_workers=workers)
                bulk_summary = tracker.track_batch(awb_list)
                for rec in bulk_summary.records:
                    upserted = self.ledger.upsert_record(rec)
                    newly_tracked += 1
                    if upserted.get("status") == "DELIVERED":
                        newly_delivered += 1

        queue_data = self.ledger.get_tracking_queue_and_kpis()
        elapsed = round(time.time() - t0, 2)

        return {
            "status": "success",
            "execution_time_sec": elapsed,
            "scan_summary": scan_res,
            "newly_tracked_count": newly_tracked,
            "newly_delivered_count": newly_delivered,
            "total_sheet_awbs": sum(s.get("rows_found", 0) for s in scan_res.get("sheets", [])),
            "active_tracked_count": newly_tracked,
            "already_delivered_skipped": queue_data["kpis"]["total_delivered"],
            "delivered_count": newly_delivered,
            "kpis": queue_data["kpis"],
            "active_queue": queue_data["active_queue"],
            "delivered_report": queue_data["delivered_report"],
        }
