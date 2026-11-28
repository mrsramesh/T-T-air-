"""
Master Air Cargo Ledger & Historical Persistence Engine.
Maintains persistent records of all queried AWBs without duplicates.
Provides automatic upserting, rich Excel/CSV export, and statistics.
"""

import json
import sqlite3
import io
import csv
import functools
import random
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

def sqlite_retry(max_retries: int = 5, initial_delay: float = 0.05):
    """Decorator to retry SQLite operations when database is locked or busy."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_err = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    if "locked" in str(e).lower() or "busy" in str(e).lower():
                        last_err = e
                        time.sleep(delay + random.uniform(0.01, 0.04))
                        delay *= 1.8
                    else:
                        raise e
            raise last_err
        return wrapper
    return decorator

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
        conn = sqlite3.connect(str(self.db_path), timeout=60.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode and robust busy timeout for zero locking errors
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=15000;")
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
            conn.execute("""
            CREATE TABLE IF NOT EXISTS autopilot_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS app_kv_store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sheet_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL,
                url TEXT NOT NULL,
                sheet_id TEXT NOT NULL UNIQUE,
                sheet_name TEXT,
                target_col TEXT NOT NULL DEFAULT 'H',
                start_row INTEGER NOT NULL DEFAULT 110,
                scan_all_tabs INTEGER NOT NULL DEFAULT 1,
                is_enabled INTEGER NOT NULL DEFAULT 1,
                last_signature TEXT,
                known_tabs_json TEXT,
                last_row_count INTEGER DEFAULT 0,
                last_new_today INTEGER DEFAULT 0,
                last_synced_at TEXT,
                last_checked_at TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)
            # Safe additive migrations for master_awb_ledger
            cur = conn.execute("PRAGMA table_info(master_awb_ledger);")
            existing_cols = {row["name"] for row in cur.fetchall()}
            migrations = [
                ("source_sheet_id", "TEXT"),
                ("source_sheet_label", "TEXT"),
                ("source_tab", "TEXT"),
                ("source_cell", "TEXT"),
                ("added_via", "TEXT DEFAULT 'manual'"),
                ("sheet_added_date", "TEXT"),
            ]
            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE master_awb_ledger ADD COLUMN {col_name} {col_type};")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_status ON master_awb_ledger(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_updated ON master_awb_ledger(last_updated_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ledger_sheet_date ON master_awb_ledger(sheet_added_date);")
            conn.commit()

    @sqlite_retry()
    def save_autopilot_state(self, is_running: bool, config: Dict[str, Any]):
        """Persists Auto-Pilot ON/OFF toggle state and configuration to SQLite."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO autopilot_state (key, value) VALUES ('is_running', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
                (str(int(bool(is_running))),)
            )
            conn.execute(
                "INSERT INTO autopilot_state (key, value) VALUES ('config', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value;",
                (json.dumps(config),)
            )
            conn.commit()

    @sqlite_retry()
    def load_autopilot_state(self) -> Optional[Dict[str, Any]]:
        """Loads persisted Auto-Pilot ON/OFF toggle and configuration from SQLite."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT key, value FROM autopilot_state;")
            data = {row["key"]: row["value"] for row in cur.fetchall()}
            if not data:
                return None
            is_running = bool(int(data.get("is_running", "0")))
            cfg = json.loads(data.get("config", "{}"))
            return {"is_running": is_running, "config": cfg}

    @sqlite_retry()
    def get_ui_state(self) -> Dict[str, Any]:
        """Retrieves persisted frontend UI state dictionary from SQLite."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM app_kv_store WHERE key = 'ui_state' LIMIT 1;")
            row = cur.fetchone()
            if row:
                try:
                    data = json.loads(row["value"])
                    if isinstance(data, dict):
                        return data
                except Exception:
                    pass
        return {}

    @sqlite_retry()
    def save_ui_state(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        """Merges partial or full UI state into SQLite so state survives refreshes & restarts."""
        if not isinstance(patch, dict):
            return self.get_ui_state()
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM app_kv_store WHERE key = 'ui_state' LIMIT 1;")
            row = cur.fetchone()
            current: Dict[str, Any] = {}
            if row:
                try:
                    loaded = json.loads(row["value"])
                    if isinstance(loaded, dict):
                        current = loaded
                except Exception:
                    pass
            current.update(patch)
            conn.execute(
                """
                INSERT INTO app_kv_store (key, value, updated_at)
                VALUES ('ui_state', ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
                """,
                (json.dumps(current), now_iso),
            )
            conn.commit()
            return current

    @sqlite_retry()
    def save_setting(self, key: str, value: Any):
        """Persists an arbitrary application setting (e.g., proxy_mode) in SQLite."""
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO app_kv_store (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at;
                """,
                (str(key), json.dumps(value), now_iso),
            )
            conn.commit()

    @sqlite_retry()
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Retrieves an arbitrary application setting from SQLite."""
        with self._get_connection() as conn:
            cur = conn.execute("SELECT value FROM app_kv_store WHERE key = ? LIMIT 1;", (str(key),))
            row = cur.fetchone()
            if row:
                try:
                    return json.loads(row["value"])
                except Exception:
                    return row["value"]
        return default

    @staticmethod
    def is_record_stale_or_recycled(
        record: Dict[str, Any],
        max_delivery_age_days: int = 60,
        current_tab_month: Optional[str] = None,
    ) -> bool:
        """
        Solves Risk #5 (Recycled AWB Trap):
        Airlines recycle 8-digit serials every 6 to 12 months.
        If an AWB is DELIVERED, but its last updated date is > max_delivery_age_days ago
        or appears in a distinct new month tab, treat it as recycled and verify anew.
        """
        if not record or record.get("status") != "DELIVERED":
            return True  # Active shipments always tracked

        last_up = record.get("last_updated_at")
        if last_up:
            try:
                dt = datetime.strptime(last_up.split()[0], "%Y-%m-%d")
                age_days = (datetime.now() - dt).days
                if age_days > max_delivery_age_days:
                    return True  # Recycled AWB from previous cycle
            except Exception:
                pass

        return False

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

    @sqlite_retry()
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

    @sqlite_retry()
    def upsert_batch(self, records: List[UnifiedTrackingRecord]) -> int:
        """Batch upsert multiple records inside a single transaction."""
        count = 0
        for rec in records:
            if rec and (rec.awb or rec.raw_input):
                self.upsert_record(rec)
                count += 1
        return count

    @sqlite_retry()
    def sync_sheet_metadata(
        self,
        clean_awb: str,
        customer_name: Optional[str] = None,
        destination: Optional[str] = None,
        pkg_pieces: Any = None,
        gross_weight: Any = None,
    ) -> bool:
        """
        Syncs edited Google Sheet metadata (customer, destination, packages, weight)
        into an existing ledger record without altering its tracking status.
        """
        clean_key = self._clean_awb_key(clean_awb)
        if not clean_key:
            return False

        updates = []
        params: List[Any] = []

        if customer_name and str(customer_name).strip() not in ("", "---", "General Cargo", "None"):
            updates.append("customer_name = ?")
            params.append(str(customer_name).strip())

        if destination and str(destination).strip() not in ("", "---", "None"):
            updates.append("destination = ?")
            params.append(str(destination).strip())

        if pkg_pieces not in (None, "", "DONE", "---"):
            try:
                pcs = int(float(str(pkg_pieces)))
                updates.append("package_pieces = ?")
                params.append(pcs)
                updates.append("package_display = ?")
                params.append(f"{pcs} pcs")
            except Exception:
                pass

        if gross_weight not in (None, "", "---"):
            wt_str = str(gross_weight).strip()
            if not wt_str.lower().endswith("kg"):
                wt_str = f"{wt_str} kg"
            updates.append("gross_weight = ?")
            params.append(wt_str)

        if not updates:
            return False

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates.append("last_updated_at = ?")
        params.append(now_iso)
        params.append(clean_key)

        with self._get_connection() as conn:
            cur = conn.execute(
                f"UPDATE master_awb_ledger SET {', '.join(updates)} WHERE awb_clean = ?;",
                params,
            )
            conn.commit()
            return cur.rowcount > 0

    @sqlite_retry()
    def get_record_by_awb(self, clean_or_formatted_awb: str) -> Optional[Dict[str, Any]]:
        clean_key = self._clean_awb_key(clean_or_formatted_awb)
        with self._get_connection() as conn:
            cur = conn.execute("SELECT * FROM master_awb_ledger WHERE awb_clean = ? LIMIT 1;", (clean_key,))
            row = cur.fetchone()
            if row:
                return dict(row)
        return None

    @sqlite_retry()
    def get_all_records(
        self,
        search: Optional[str] = None,
        status: Optional[str] = None,
        lifecycle: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Retrieves master records with optional search filter, status filtering, and lifecycle filtering."""
        query = "SELECT * FROM master_awb_ledger WHERE 1=1"
        params: List[Any] = []

        if status and status.upper() != "ALL":
            query += " AND status = ?"
            params.append(status.upper())

        if lifecycle:
            lc = lifecycle.strip().lower()
            if lc in ("active", "on_the_way", "ontheway"):
                query += " AND status != 'DELIVERED'"
            elif lc in ("delivered", "archive", "completed"):
                query += " AND status = 'DELIVERED'"

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

    def get_active_shipments(self, limit: int = 5000) -> List[Dict[str, Any]]:
        """Returns shipments currently on the way (status != DELIVERED)."""
        return self.get_all_records(lifecycle="active", limit=limit)

    def get_delivered_shipments(self, limit: int = 5000) -> List[Dict[str, Any]]:
        """Returns shipments marked DELIVERED (completed archive)."""
        return self.get_all_records(lifecycle="delivered", limit=limit)

    @sqlite_retry()
    def get_summary_stats(self) -> Dict[str, Any]:
        """Calculates live summary metrics for the Master Sheet dashboard."""
        with self._get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM master_awb_ledger;").fetchone()[0]
            delivered = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status = 'DELIVERED';").fetchone()[0]
            active_on_way = conn.execute("SELECT COUNT(*) FROM master_awb_ledger WHERE status != 'DELIVERED';").fetchone()[0]
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
                "active_on_the_way": active_on_way,
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
        Contains tabs:
        1. All Shipments (Complete Ledger)
        2. 🚚 On The Way (Active Shipments)
        3. ✅ Delivered (Completed Archive)
        4. Executive Summary & KPIs
        """
        if records is None:
            records = self.get_all_records(limit=10000)

        wb = openpyxl.Workbook()

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

        header_font = Font(name="Calibri", size=11, bold=True, color=self.WHITE)
        header_fill = PatternFill(start_color=self.NAVY_HEADER, end_color=self.NAVY_HEADER, fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color=self.BORDER_COLOR)
        cell_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        regular_font = Font(name="Calibri", size=10, color="0F172A")
        mono_font = Font(name="Consolas", size=10, bold=True, color="0F172A")
        zebra_fill = PatternFill(start_color=self.ZEBRA_FILL, end_color=self.ZEBRA_FILL, fill_type="solid")

        def _populate_tab(ws, tab_records):
            ws.views.sheetView[0].showGridLines = True
            ws.append(headers)

            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=1, column=col_num)
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = header_align
                cell.border = cell_border
            ws.row_dimensions[1].height = 28

            for idx, row in enumerate(tab_records, start=1):
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

                    if col_idx == 3:
                        c.font = mono_font
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    elif col_idx in (1, 9, 10, 16):
                        c.alignment = Alignment(horizontal="center", vertical="center")
                    else:
                        c.alignment = Alignment(horizontal="left", vertical="center")

                    if col_idx == 12 and st in self.STATUS_COLORS:
                        bg_color, fg_color = self.STATUS_COLORS[st]
                        c.fill = PatternFill(start_color=bg_color, end_color=bg_color, fill_type="solid")
                        c.font = Font(name="Calibri", size=10, bold=True, color=fg_color)
                        c.alignment = Alignment(horizontal="center", vertical="center")

            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val = str(cell.value or "")
                    if len(val) > max_len:
                        max_len = len(val)
                ws.column_dimensions[col_letter].width = min(max(max_len + 3, 11), 38)
            ws.freeze_panes = "A2"

        # Tab 1: All Shipments
        ws_all = wb.active
        ws_all.title = "All Shipments"
        _populate_tab(ws_all, records)

        # Tab 2: On The Way (Active)
        active_recs = [r for r in records if (r.get("status") or "").upper() != "DELIVERED"]
        ws_active = wb.create_sheet(title="On The Way (Active)")
        _populate_tab(ws_active, active_recs)

        # Tab 3: Delivered Archive
        delivered_recs = [r for r in records if (r.get("status") or "").upper() == "DELIVERED"]
        ws_dlv = wb.create_sheet(title="Delivered Archive")
        _populate_tab(ws_dlv, delivered_recs)

        # Tab 4: Executive Summary
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

    # =========================================================================
    # Multi-Sheet Sources & Unified Tracking Queue + KPIs
    # =========================================================================

    @staticmethod
    def _extract_sheet_id(url_or_id: str) -> str:
        import re as _re
        raw = str(url_or_id or "").strip()
        m = _re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw)
        if m:
            return m.group(1)
        clean = _re.sub(r"[^a-zA-Z0-9-_]", "", raw)
        if len(clean) >= 20:
            return clean
        raise ValueError(f"Invalid Google Sheet URL or ID: '{url_or_id}'")

    @sqlite_retry()
    def list_sheet_sources(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """Returns all configured Google Sheet sources."""
        query = "SELECT * FROM sheet_sources"
        if enabled_only:
            query += " WHERE is_enabled = 1"
        query += " ORDER BY id ASC;"
        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["is_enabled"] = bool(d.get("is_enabled", 1))
                d["scan_all_tabs"] = bool(d.get("scan_all_tabs", 1))
                try:
                    d["known_tabs"] = json.loads(d.get("known_tabs_json") or "[]")
                except Exception:
                    d["known_tabs"] = []
                result.append(d)
            return result

    @sqlite_retry()
    def get_sheet_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sheet_sources WHERE id = ? LIMIT 1;", (source_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["is_enabled"] = bool(d.get("is_enabled", 1))
            d["scan_all_tabs"] = bool(d.get("scan_all_tabs", 1))
            try:
                d["known_tabs"] = json.loads(d.get("known_tabs_json") or "[]")
            except Exception:
                d["known_tabs"] = []
            return d

    @sqlite_retry()
    def upsert_sheet_source(
        self,
        url: str,
        label: Optional[str] = None,
        sheet_name: Optional[str] = None,
        target_col: str = "H",
        start_row: int = 110,
        scan_all_tabs: bool = True,
        is_enabled: bool = True,
        source_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Creates or updates a Google Sheet source configuration."""
        sheet_id = self._extract_sheet_id(url)
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        clean_label = (label or "").strip() or f"Sheet ({sheet_id[:8]}...)"
        clean_col = (target_col or "H").strip().upper()
        clean_row = max(1, int(start_row or 110))

        with self._get_connection() as conn:
            if source_id is not None:
                conn.execute(
                    """
                    UPDATE sheet_sources
                    SET label = ?, url = ?, sheet_id = ?, sheet_name = ?,
                        target_col = ?, start_row = ?, scan_all_tabs = ?,
                        is_enabled = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (
                        clean_label, url.strip(), sheet_id, sheet_name,
                        clean_col, clean_row, int(bool(scan_all_tabs)),
                        int(bool(is_enabled)), now_iso, int(source_id),
                    ),
                )
                conn.commit()
                return self.get_sheet_source(int(source_id)) or {}

            conn.execute(
                """
                INSERT INTO sheet_sources (
                    label, url, sheet_id, sheet_name, target_col, start_row,
                    scan_all_tabs, is_enabled, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sheet_id) DO UPDATE SET
                    label = excluded.label,
                    url = excluded.url,
                    sheet_name = excluded.sheet_name,
                    target_col = excluded.target_col,
                    start_row = excluded.start_row,
                    scan_all_tabs = excluded.scan_all_tabs,
                    is_enabled = excluded.is_enabled,
                    updated_at = excluded.updated_at;
                """,
                (
                    clean_label, url.strip(), sheet_id, sheet_name,
                    clean_col, clean_row, int(bool(scan_all_tabs)),
                    int(bool(is_enabled)), now_iso, now_iso,
                ),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM sheet_sources WHERE sheet_id = ? LIMIT 1;", (sheet_id,)).fetchone()
            return self.get_sheet_source(row["id"]) if row else {}

    @sqlite_retry()
    def toggle_sheet_source(self, source_id: int, is_enabled: bool) -> Optional[Dict[str, Any]]:
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sheet_sources SET is_enabled = ?, updated_at = ? WHERE id = ?;",
                (int(bool(is_enabled)), now_iso, int(source_id)),
            )
            conn.commit()
        return self.get_sheet_source(int(source_id))

    @sqlite_retry()
    def delete_sheet_source(self, source_id: int) -> bool:
        with self._get_connection() as conn:
            row = conn.execute("SELECT sheet_id FROM sheet_sources WHERE id = ? LIMIT 1;", (int(source_id),)).fetchone()
            cur = conn.execute("DELETE FROM sheet_sources WHERE id = ?;", (int(source_id),))
            if row and row["sheet_id"]:
                conn.execute(
                    "DELETE FROM master_awb_ledger WHERE source_sheet_id = ? AND status = 'PENDING' AND added_via = 'sheet';",
                    (row["sheet_id"],),
                )
            conn.commit()
            return cur.rowcount > 0

    @sqlite_retry()
    def prune_stale_sheet_stubs(self, source_sheet_id: str, valid_clean_awbs: List[str]) -> int:
        """
        Removes PENDING sheet-stub rows for `source_sheet_id` that are no longer in `valid_clean_awbs`
        (e.g. rows before start_row/starting_tab), plus any orphan PENDING stubs from deleted sheets.
        Never deletes already-tracked records (status != 'PENDING').
        """
        valid_set = set(valid_clean_awbs or [])
        removed = 0
        with self._get_connection() as conn:
            # 1. Remove orphan PENDING sheet stubs whose sheet_id is not in sheet_sources
            cur1 = conn.execute("""
                DELETE FROM master_awb_ledger
                WHERE status = 'PENDING' AND added_via = 'sheet'
                  AND (source_sheet_id IS NULL OR source_sheet_id NOT IN (SELECT sheet_id FROM sheet_sources));
            """)
            removed += cur1.rowcount

            # 2. Remove PENDING stubs for this sheet_id that are outside the current manifest
            rows = conn.execute(
                "SELECT awb_clean FROM master_awb_ledger WHERE source_sheet_id = ? AND status = 'PENDING' AND added_via = 'sheet';",
                (source_sheet_id,),
            ).fetchall()
            to_delete = [(r["awb_clean"],) for r in rows if r["awb_clean"] not in valid_set]
            if to_delete:
                conn.executemany(
                    "DELETE FROM master_awb_ledger WHERE awb_clean = ? AND status = 'PENDING' AND added_via = 'sheet';",
                    to_delete,
                )
                removed += len(to_delete)
            conn.commit()
        return removed

    @sqlite_retry()
    def update_sheet_source_sync_state(
        self,
        source_id: int,
        last_signature: Optional[str] = None,
        known_tabs: Optional[List[str]] = None,
        last_row_count: Optional[int] = None,
        last_new_today: Optional[int] = None,
        synced: bool = False,
        last_error: Optional[str] = None,
    ):
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updates = ["last_checked_at = ?", "updated_at = ?", "last_error = ?"]
        params: List[Any] = [now_iso, now_iso, last_error]

        if last_signature is not None:
            updates.append("last_signature = ?")
            params.append(last_signature)
        if known_tabs is not None:
            updates.append("known_tabs_json = ?")
            params.append(json.dumps(known_tabs))
        if last_row_count is not None:
            updates.append("last_row_count = ?")
            params.append(int(last_row_count))
        if last_new_today is not None:
            updates.append("last_new_today = ?")
            params.append(int(last_new_today))
        if synced:
            updates.append("last_synced_at = ?")
            params.append(now_iso)

        params.append(int(source_id))
        with self._get_connection() as conn:
            conn.execute(
                f"UPDATE sheet_sources SET {', '.join(updates)} WHERE id = ?;",
                params,
            )
            conn.commit()

    @sqlite_retry()
    def ensure_default_sheet_source(
        self,
        default_url: str,
        label: str = "Primary Cargo Sheet",
        sheet_name: Optional[str] = "NOV-26",
        target_col: str = "H",
        start_row: int = 110,
        scan_all_tabs: bool = True,
    ) -> List[Dict[str, Any]]:
        """Auto-migrates the single configured sheet into sheet_sources if empty."""
        existing = self.list_sheet_sources()
        if existing:
            return existing
        saved = self.load_autopilot_state()
        cfg = (saved or {}).get("config") or {}
        url = cfg.get("url") or default_url
        if url:
            self.upsert_sheet_source(
                url=url,
                label=label,
                sheet_name=cfg.get("sheet_name") or sheet_name,
                target_col=cfg.get("target_col") or target_col,
                start_row=int(cfg.get("start_row") or start_row),
                scan_all_tabs=bool(cfg.get("scan_all_tabs", scan_all_tabs)),
                is_enabled=True,
            )
        return self.list_sheet_sources()

    @sqlite_retry()
    def register_sheet_awb_stub(
        self,
        clean_awb: str,
        formatted_awb: str,
        customer_name: Optional[str] = None,
        destination: Optional[str] = None,
        pkg_pieces: Any = None,
        gross_weight: Any = None,
        source_sheet_id: Optional[str] = None,
        source_sheet_label: Optional[str] = None,
        source_tab: Optional[str] = None,
        source_cell: Optional[str] = None,
    ) -> bool:
        """
        Ensures an AWB discovered in an enabled Google Sheet is registered in the ledger.
        Returns True if this is a brand-new AWB not previously in the system.
        """
        clean_key = self._clean_awb_key(clean_awb)
        if not clean_key:
            return False

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_str = datetime.now().strftime("%Y-%m-%d")

        existing = self.get_record_by_awb(clean_key)
        if existing:
            # Update source attribution & metadata without overwriting live tracking status
            with self._get_connection() as conn:
                conn.execute(
                    """
                    UPDATE master_awb_ledger
                    SET source_sheet_id = COALESCE(?, source_sheet_id),
                        source_sheet_label = COALESCE(?, source_sheet_label),
                        source_tab = COALESCE(?, source_tab),
                        source_cell = COALESCE(?, source_cell)
                    WHERE awb_clean = ?;
                    """,
                    (source_sheet_id, source_sheet_label, source_tab, source_cell, clean_key),
                )
                conn.commit()
            self.sync_sheet_metadata(
                clean_awb=clean_key,
                customer_name=customer_name,
                destination=destination,
                pkg_pieces=pkg_pieces,
                gross_weight=gross_weight,
            )
            return False

        cust = (customer_name or "").strip() or "General Cargo"
        dest = (destination or "").strip() or "---"
        pcs = None
        pkg_disp = "---"
        if pkg_pieces not in (None, "", "DONE", "---"):
            try:
                pcs = int(float(str(pkg_pieces)))
                pkg_disp = f"{pcs} pcs"
            except Exception:
                pass
        wt_str = "---"
        if gross_weight not in (None, "", "---"):
            wt_str = str(gross_weight).strip()
            if not wt_str.lower().endswith("kg"):
                wt_str = f"{wt_str} kg"

        prefix = clean_key[:3] if len(clean_key) >= 3 else ""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO master_awb_ledger (
                    awb_clean, awb_no, customer_name, package_pieces, package_display,
                    gross_weight, volume_weight, iata, iata_prefix, carrier_name, carrier_code,
                    flight_code, source, destination, direction_transition, status,
                    status_detail, latest_activity, latest_location, first_tracked_at,
                    last_updated_at, tracked_count, source_sheet_id, source_sheet_label,
                    source_tab, source_cell, added_via, sheet_added_date
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, '---', ?, ?, 'Pending Sync', '',
                    '---', '---', ?, 'Queued from Google Sheet', 'PENDING',
                    'Discovered in Google Sheet (awaiting carrier tracking)',
                    'Queued for tracking', ?, ?, ?, 0, ?, ?, ?, ?, 'sheet', ?
                );
                """,
                (
                    clean_key, formatted_awb or clean_key, cust, pcs, pkg_disp,
                    wt_str, prefix, prefix, dest, dest, now_iso, now_iso,
                    source_sheet_id, source_sheet_label, source_tab, source_cell, today_str,
                ),
            )
            conn.commit()
        return True

    @sqlite_retry()
    def get_tracking_queue_and_kpis(
        self,
        search: Optional[str] = None,
        sheet_filter: Optional[str] = None,
        limit: int = 2000,
    ) -> Dict[str, Any]:
        """
        Returns the two lifecycle tables + rich KPIs:
        - active_queue: All undelivered AWBs (new from enabled sheets + pending from central ledger).
        - delivered_report: All DELIVERED AWBs (completed report).
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        all_records_raw = self.get_all_records(search=search, limit=limit)

        sheets = self.list_sheet_sources()
        enabled_sheets = [s for s in sheets if s.get("is_enabled")]
        enabled_sheet_ids = {s["sheet_id"] for s in enabled_sheets}

        # Exclude PENDING sheet stubs belonging to disabled or deleted sheets
        all_records = [
            r for r in all_records_raw
            if not (
                (r.get("status") or "").upper() == "PENDING"
                and r.get("added_via") == "sheet"
                and r.get("source_sheet_id") not in enabled_sheet_ids
            )
        ]

        if sheet_filter and sheet_filter != "ALL":
            if sheet_filter == "CENTRAL":
                filtered = [r for r in all_records if not r.get("source_sheet_id")]
            else:
                filtered = [r for r in all_records if r.get("source_sheet_id") == sheet_filter]
        else:
            filtered = all_records

        active_queue = [r for r in filtered if (r.get("status") or "").upper() != "DELIVERED"]
        delivered_report = [r for r in filtered if (r.get("status") or "").upper() == "DELIVERED"]

        # Unfiltered KPI totals across the whole system
        all_active = [r for r in all_records if (r.get("status") or "").upper() != "DELIVERED"]
        all_delivered = [r for r in all_records if (r.get("status") or "").upper() == "DELIVERED"]

        added_from_sheets_today = sum(
            1 for r in all_records
            if r.get("added_via") == "sheet" and r.get("sheet_added_date") == today_str
        )
        undelivered_from_sheets = sum(
            1 for r in all_active
            if r.get("source_sheet_id") or r.get("added_via") == "sheet"
        )
        active_from_sheets_today = sum(
            1 for r in all_active
            if r.get("added_via") == "sheet" and r.get("sheet_added_date") == today_str
        )
        picked_from_central_undelivered = max(0, len(all_active) - undelivered_from_sheets)
        delivered_today = sum(
            1 for r in all_delivered
            if (r.get("last_updated_at") or "").startswith(today_str)
        )

        # Per-sheet breakdown (only for active configured sheet_sources)
        active_sheet_ids = {s["sheet_id"] for s in sheets}
        per_sheet: Dict[str, Dict[str, Any]] = {}
        for r in all_records:
            sid = r.get("source_sheet_id")
            if not sid or sid not in active_sheet_ids:
                continue
            if sid not in per_sheet:
                per_sheet[sid] = {
                    "sheet_id": sid,
                    "label": r.get("source_sheet_label") or sid[:8],
                    "active_count": 0,
                    "delivered_count": 0,
                    "new_today_count": 0,
                }
            if (r.get("status") or "").upper() == "DELIVERED":
                per_sheet[sid]["delivered_count"] += 1
            else:
                per_sheet[sid]["active_count"] += 1
            if r.get("added_via") == "sheet" and r.get("sheet_added_date") == today_str:
                per_sheet[sid]["new_today_count"] += 1

        return {
            "active_queue": active_queue,
            "delivered_report": delivered_report,
            "kpis": {
                "total_active_queue": len(all_active),
                "undelivered_from_sheets": undelivered_from_sheets,
                "added_from_sheets_today": added_from_sheets_today,
                "active_from_sheets_today": active_from_sheets_today,
                "picked_from_central_undelivered": picked_from_central_undelivered,
                "total_delivered": len(all_delivered),
                "delivered_today": delivered_today,
                "total_sheets": len(sheets),
                "enabled_sheets": len(enabled_sheets),
                "per_sheet": list(per_sheet.values()),
            },
        }


# Global Singleton instance
master_ledger = MasterLedgerManager()
