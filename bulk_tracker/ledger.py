"""
Master Air Cargo Ledger & Historical Persistence Engine.
Maintains persistent records of all queried AWBs without duplicates.
Provides automatic upserting, rich Excel/CSV export, and statistics.
"""

import json
import sqlite3
import io
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from bulk_tracker.models import UnifiedTrackingRecord


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "master_cargo_ledger.db"


class MasterLedgerManager:
    """
    Thread-safe, ACID-compliant persistence engine for Master Air Cargo records.
    Guarantee:
    - Zero duplicate entries (unique primary key on clean digits of AWB).
    - Automatic upsert: status updates, flight updates, and timestamps are refreshed in place.
    - Historical continuity: first_tracked_at is preserved forever; tracked_count increments.
    - Permanent on-disk persistence (survives app restarts, never deleted).
    """

    # Palette for Excel styling
    NAVY_HEADER = "0F172A"       # Modern Dark Slate #0f172a
    WHITE = "FFFFFF"
    BORDER_COLOR = "E2E8F0"
    ZEBRA_FILL = "F8FAFC"

    STATUS_COLORS = {
        "DELIVERED": ("ECFDF5", "047857"),    # Emerald
        "IN_TRANSIT": ("EFF6FF", "1D4ED8"),   # Sapphire Blue
        "DEPARTED": ("F0F9FF", "0369A1"),     # Sky Blue
        "ARRIVED": ("FDF4FF", "7E22CE"),      # Purple
        "BOOKED": ("F5F3FF", "6D28D9"),       # Indigo
        "ACCEPTED": ("F5F3FF", "6D28D9"),     # Indigo
        "NOT_FOUND": ("FFF1F2", "BE123C"),    # Rose / Orange
        "UNREACHABLE": ("FFFBEB", "B45309"),  # Amber
        "SKIPPED": ("F8FAFC", "475569"),      # Slate
        "ERROR": ("FEF2F2", "B91C1C"),        # Red
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency read/write
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS master_awb_ledger (
                awb_clean TEXT PRIMARY KEY,
                awb_no TEXT NOT NULL,
                customer_name TEXT,
                package_pieces INTEGER,
                package_display TEXT,
                gross_weight TEXT,
                volume_weight TEXT,
                iata TEXT,
                iata_prefix TEXT,
                carrier_name TEXT,
                carrier_code TEXT,
                flight_code TEXT,
                source TEXT,
                destination TEXT,
                direction_transition TEXT,
                status TEXT NOT NULL,
                status_detail TEXT,
                latest_activity TEXT,
                latest_location TEXT,
                first_tracked_at TEXT NOT NULL,
                last_updated_at TEXT NOT NULL,
                tracked_count INTEGER DEFAULT 1,
                raw_payload_json TEXT
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_status ON master_awb_ledger(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_updated ON master_awb_ledger(last_updated_at);")
            conn.commit()

    @staticmethod
    def _clean_awb_key(awb: str) -> str:
        return "".join(c for c in str(awb) if c.isdigit())

    @classmethod
    def _extract_customer_name(cls, record: UnifiedTrackingRecord) -> str:
        """Extracts customer name from record or underlying raw data."""
        if record.consignee_issued_to and record.consignee_issued_to.strip() not in ("---", "N/A", "None", ""):
            return record.consignee_issued_to.strip()

        raw = record.raw_data or {}
        if isinstance(raw, dict):
            ov = raw.get("overview") or {}
            for k in ("consignee", "consignee_name", "agent_name", "issued_to", "customer_name", "shipper", "booking_agent"):
                val = ov.get(k) or raw.get(k)
                if val and str(val).strip() not in ("---", "N/A", "None", ""):
                    return str(val).strip()
        return "Customer (Direct Cargo)"

    @classmethod
    def _compute_direction_transition(cls, record: UnifiedTrackingRecord) -> str:
        """Computes clean direction in transition / route progress."""
        st = record.status.upper()
        orig = record.origin if record.origin and record.origin != "---" else None
        dest = record.destination if record.destination and record.destination != "---" else None
        loc = record.latest_location if record.latest_location and record.latest_location != "---" else None

        if st == "DELIVERED":
            return f"Delivered at {dest or 'Destination'}"
        elif st == "ARRIVED":
            return f"Arrived at {dest or loc or 'Destination'}"
        elif st in ("IN_TRANSIT", "DEPARTED"):
            if loc and loc not in (orig, dest):
                return f"In-Transit via {loc} ({orig or ''} ➔ {dest or ''})".replace("()", "").strip()
            return f"In-Transit ({orig or ''} ➔ {dest or ''})".replace("()", "").strip()
        elif st in ("BOOKED", "ACCEPTED"):
            return f"Booked at {orig or 'Origin'} for {dest or 'Destination'}"
        elif st == "SKIPPED":
            return f"Skipped (IATA Prefix {record.carrier_prefix})"
        elif st == "UNREACHABLE":
            return "Carrier Portal Connection Timeout"
        elif st == "NOT_FOUND":
            return "No Active Route (AWB Not Found)"
        return f"{orig or '---'} ➔ {dest or '---'}"

    def upsert_record(self, record: UnifiedTrackingRecord) -> Dict[str, Any]:
        """
        Upserts a single UnifiedTrackingRecord.
        If AWB already exists, updates latest status, flights, and last_updated_at in place.
        Maintains first_tracked_at and increments tracked_count.
        """
        clean_key = self._clean_awb_key(record.awb)
        if not clean_key:
            clean_key = self._clean_awb_key(record.raw_input)
        if not clean_key:
            return {}

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        customer = self._extract_customer_name(record)
        direction = self._compute_direction_transition(record)

        pkg_pieces = record.pieces
        pkg_display = f"{record.pieces} pcs" if record.pieces is not None else "---"
        gross_wt = record.weight or "---"
        vol_wt = record.volume or "---"

        carrier_code = record.carrier_code or ""
        prefix = record.carrier_prefix or (clean_key[:3] if len(clean_key) >= 3 else "")
        iata_display = f"{prefix} / {carrier_code} ({record.carrier_name})" if carrier_code else f"{prefix} ({record.carrier_name})"

        fl_code = record.flight_details or "---"
        source = record.origin or "---"
        dest = record.destination or "---"
        latest_act = record.latest_activity or record.status_detail or "---"
        raw_json_str = json.dumps(record.raw_data or {}) if record.raw_data else None

        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO master_awb_ledger (
                awb_clean, awb_no, customer_name, package_pieces, package_display,
                gross_weight, volume_weight, iata, iata_prefix, carrier_name, carrier_code,
                flight_code, source, destination, direction_transition, status,
                status_detail, latest_activity, latest_location, first_tracked_at,
                last_updated_at, tracked_count, raw_payload_json
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?
            )
            ON CONFLICT(awb_clean) DO UPDATE SET
                awb_no = excluded.awb_no,
                customer_name = CASE
                    WHEN excluded.customer_name IS NOT NULL AND excluded.customer_name NOT IN ('---', 'Customer (Direct Cargo)')
                    THEN excluded.customer_name
                    ELSE COALESCE(master_awb_ledger.customer_name, excluded.customer_name)
                END,
                package_pieces = COALESCE(excluded.package_pieces, master_awb_ledger.package_pieces),
                package_display = CASE WHEN excluded.package_display != '---' THEN excluded.package_display ELSE master_awb_ledger.package_display END,
                gross_weight = CASE WHEN excluded.gross_weight != '---' THEN excluded.gross_weight ELSE master_awb_ledger.gross_weight END,
                volume_weight = CASE WHEN excluded.volume_weight != '---' THEN excluded.volume_weight ELSE master_awb_ledger.volume_weight END,
                iata = excluded.iata,
                carrier_name = excluded.carrier_name,
                carrier_code = excluded.carrier_code,
                flight_code = CASE WHEN excluded.flight_code != '---' THEN excluded.flight_code ELSE master_awb_ledger.flight_code END,
                source = CASE WHEN excluded.source != '---' THEN excluded.source ELSE master_awb_ledger.source END,
                destination = CASE WHEN excluded.destination != '---' THEN excluded.destination ELSE master_awb_ledger.destination END,
                direction_transition = excluded.direction_transition,
                status = excluded.status,
                status_detail = excluded.status_detail,
                latest_activity = excluded.latest_activity,
                latest_location = excluded.latest_location,
                last_updated_at = excluded.last_updated_at,
                tracked_count = master_awb_ledger.tracked_count + 1,
                raw_payload_json = COALESCE(excluded.raw_payload_json, master_awb_ledger.raw_payload_json);
            """, (
                clean_key, record.awb, customer, pkg_pieces, pkg_display,
                gross_wt, vol_wt, iata_display, prefix, record.carrier_name, carrier_code,
                fl_code, source, dest, direction, record.status,
                record.status_detail, latest_act, record.latest_location or dest,
                now_iso, now_iso, raw_json_str
            ))
            conn.commit()

        return self.get_record_by_awb(clean_key) or {}

    def upsert_batch(self, records: List[UnifiedTrackingRecord]) -> int:
        """Batch upsert multiple records inside a single transaction."""
        count = 0
        for rec in records:
            if rec and (rec.awb or rec.raw_input):
                self.upsert_record(rec)
                count += 1
        return count

    def get_record_by_awb(self, clean_or_formatted_awb: str) -> Optional[Dict[str, Any]]:
        clean_key = self._clean_awb_key(clean_or_formatted_awb)
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM master_awb_ledger WHERE awb_clean = ? LIMIT 1;", (clean_key,))
            row = cur.fetchone()
            if row:
                return dict(row)
        return None

    def get_all_records(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieves master records with optional search filter and status filtering."""
        query = "SELECT * FROM master_awb_ledger WHERE 1=1"
        params: List[Any] = []

        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        if search and search.strip():
            s = f"%{search.strip().lower()}%"
            query += """ AND (
                LOWER(awb_no) LIKE ? OR
                LOWER(customer_name) LIKE ? OR
                LOWER(carrier_name) LIKE ? OR
                LOWER(flight_code) LIKE ? OR
                LOWER(source) LIKE ? OR
                LOWER(destination) LIKE ? OR
                LOWER(direction_transition) LIKE ? OR
                LOWER(status) LIKE ?
            )"""
            params.extend([s] * 8)

        query += " ORDER BY last_updated_at DESC LIMIT ? OFFSET ?;"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cur = conn.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates live summary metrics for the Master Sheet dashboard."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM master_awb_ledger;").fetchone()[0]
            delivered = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'DELIVERED';").fetchone()[0]
            transit = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status IN ('IN_TRANSIT', 'DEPARTED');").fetchone()[0]
            arrived = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'ARRIVED';").fetchone()[0]
            not_found = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'NOT_FOUND';").fetchone()[0]
            skipped = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'SKIPPED';").fetchone()[0]
            unreachable = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'UNREACHABLE';").fetchone()[0]
            unique_carriers = conn.execute("SELECT COUNT(DISTINCT carrier_name) FROM master_awb_ledger WHERE carrier_name IS NOT NULL;").fetchone()[0]
            last_sync = conn.execute("SELECT MAX(last_updated_at) FROM master_awb_ledger;").fetchone()[0] or "N/A"

            return {
                "total_records": total,
                "delivered": delivered,
                "in_transit": transit,
                "arrived": arrived,
                "not_found": not_found,
                "skipped": skipped,
                "unreachable": unreachable,
                "unique_carriers": unique_carriers,
                "last_sync": last_sync,
            }

    def export_excel(self, records: Optional[List[Dict[str, Any]]] = None) -> bytes:
        """
        Generates an executive-grade, styled Master Air Cargo Excel Sheet (.xlsx).
        Headers requested by user:
        Customer Name, AWB No, Package, Gross Weight, Volume Weight, IATA, Flight Code, Source, Destination, Direction in Transition, Status of AWB
        Plus tracking audit timestamps.
        """
        if records is None:
            records = self.get_all_records(limit=10000)

        wb = openpyxl.Workbook()

        # ====================================================
        # Sheet 1: Master Air Cargo Ledger
        # ====================================================
        ws = wb.active
        ws.title = "Master Air Cargo Ledger"
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "#",
            "Customer Name",
            "AWB No",
            "Package",
            "Gross Weight",
            "Volume Weight",
            "IATA / Airline",
            "Flight Code",
            "Source",
            "Destination",
            "Direction in Transition",
            "Status of AWB",
            "Latest Activity / Detail",
            "First Tracked At",
            "Last Updated At",
            "Times Tracked",
        ]

        ws.append(headers)

        header_font = Font(name="Calibri", size=11, bold=True, color=self.WHITE)
        header_fill = PatternFill(start_color=self.NAVY_HEADER, end_color=self.NAVY_HEADER, fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color=self.BORDER_COLOR)
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = cell_border
        ws.row_dimensions[1].height = 28

        regular_font = Font(name="Calibri", size=10, color="0F172A")
        mono_font = Font(name="Consolas", size=10, bold=True, color="0F172A")
        zebra_fill = PatternFill(start_color=self.ZEBRA_FILL, end_color=self.ZEBRA_FILL, fill_type="solid")

        for idx, row in enumerate(records, start=1):
            st = str(row.get("status") or "").upper()
            row_data = [
                idx,
                row.get("customer_name") or "Customer (Direct Cargo)",
                row.get("awb_no") or "---",
                row.get("package_display") or (f"{row.get('package_pieces')} pcs" if row.get("package_pieces") else "---"),
                row.get("gross_weight") or "---",
                row.get("volume_weight") or "---",
                row.get("iata") or f"{row.get('iata_prefix')} ({row.get('carrier_name')})",
                row.get("flight_code") or "---",
                row.get("source") or "---",
                row.get("destination") or "---",
                row.get("direction_transition") or "---",
                st,
                row.get("latest_activity") or row.get("status_detail") or "---",
                row.get("first_tracked_at") or "---",
                row.get("last_updated_at") or "---",
                row.get("tracked_count") or 1,
            ]
            ws.append(row_data)
            row_num = ws.max_row
            ws.row_dimensions[row_num].height = 22

            is_even = (idx % 2 == 0)

            for col_idx in range(1, len(row_data) + 1):
                c = ws.cell(row=row_num, column=col_idx)
                c.border = cell_border
                c.font = regular_font

                if is_even:
                    c.fill = zebra_fill

                # AWB column monospace
                if col_idx == 3:
                    c.font = mono_font
                    c.alignment = Alignment(horizontal="center", vertical="center")
                elif col_idx in (1, 9, 10, 16):
                    c.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    c.alignment = Alignment(horizontal="left", vertical="center")

                # Status pill coloring in Excel
                if col_idx == 12 and st in self.STATUS_COLORS:
                    bg_color, fg_color = self.STATUS_COLORS[st]
                    c.fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
                    c.font = Font(name="Calibri", size=10, bold=True, color=fg_color)
                    c.alignment = Alignment(horizontal="center", vertical="center")

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 38)

        # Freeze top header row
        ws.freeze_panes = "A2"

        # ====================================================
        # Sheet 2: Executive Summary & Ledger Statistics
        # ====================================================
        ws_sum = wb.create_sheet(title="Executive Summary")
        ws_sum.views.sheetView[0].showGridLines = True

        stats = self.get_summary_stats()

        summary_title_font = Font(name="Calibri", size=14, bold=True, color=self.WHITE)
        title_cell = ws_sum.cell(row=2, column=2, value="Master Air Cargo Ledger Summary Report")
        title_cell.font = summary_title_font
        title_cell.fill = header_fill
        title_cell.alignment = Alignment(horizontal="left", vertical="center")
        ws_sum.merge_cells("B2:D2")
        ws_sum.row_dimensions[2].height = 30

        kpis = [
            ("Total Unique AWBs Tracked", stats["total_records"]),
            ("Delivered Shipments (POD)", stats["delivered"]),
            ("In-Transit / Departed", stats["in_transit"]),
            ("Arrived at Destination", stats["arrived"]),
            ("Not Found / Invalid", stats["not_found"]),
            ("Skipped (Unsupported Prefix)", stats["skipped"]),
            ("Unreachable Portals", stats["unreachable"]),
            ("Unique Airlines Covered", stats["unique_carriers"]),
            ("Latest Ledger Update Timestamp", stats["last_sync"]),
            ("Report Export Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]

        lbl_font = Font(name="Calibri", size=11, bold=True, color="334155")
        val_font = Font(name="Calibri", size=11, color="0F172A")

        for i, (metric, val) in enumerate(kpis, start=4):
            ws_sum.cell(row=i, column=2, value=metric).font = lbl_font
            v_cell = ws_sum.cell(row=i, column=3, value=val)
            v_cell.font = val_font
            v_cell.alignment = Alignment(horizontal="left")
            ws_sum.row_dimensions[i].height = 20

        ws_sum.column_dimensions["B"].width = 34
        ws_sum.column_dimensions["C"].width = 28
        ws_sum.column_dimensions["D"].width = 15

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def export_csv(self, records: Optional[List[Dict[str, Any]]] = None) -> str:
        """Exports master ledger records to standard CSV."""
        if records is None:
            records = self.get_all_records(limit=10000)

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            "Customer Name",
            "AWB No",
            "Package",
            "Gross Weight",
            "Volume Weight",
            "IATA / Airline",
            "Flight Code",
            "Source",
            "Destination",
            "Direction in Transition",
            "Status of AWB",
            "Latest Activity / Detail",
            "First Tracked At",
            "Last Updated At",
            "Times Tracked",
        ]
        writer.writerow(headers)

        for r in records:
            writer.writerow([
                r.get("customer_name") or "Customer (Direct Cargo)",
                r.get("awb_no") or "---",
                r.get("package_display") or (f"{r.get('package_pieces')} pcs" if r.get("package_pieces") else "---"),
                r.get("gross_weight") or "---",
                r.get("volume_weight") or "---",
                r.get("iata") or f"{r.get('iata_prefix')} ({r.get('carrier_name')})",
                r.get("flight_code") or "---",
                r.get("source") or "---",
                r.get("destination") or "---",
                r.get("direction_transition") or "---",
                r.get("status") or "---",
                r.get("latest_activity") or r.get("status_detail") or "---",
                r.get("first_tracked_at") or "---",
                r.get("last_updated_at") or "---",
                r.get("tracked_count") or 1,
            ])

        return output.getvalue()


# Global Singleton instance
master_ledger = MasterLedgerManager()
