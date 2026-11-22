"""
Continuous Auto-Pilot Lifecycle Tracking Daemon for Google Sheets.
Periodically re-scans designated Google Sheet columns (Column H from H110 downwards),
tracks all active / in-transit / departed shipments until delivered,
freezes delivered shipments (never tracks them again), and keeps the Master Cargo Ledger updated.
"""

import asyncio
import datetime
import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("AutoPilotManager")


class AutoPilotManager:
    """
    Singleton Manager for automated background tracking of Google Sheets.
    Supports continuous lifecycle tracking with an ON/OFF toggle switch from the Web UI.
    """

    def __init__(self, sheets_tracker, ledger):
        self.sheets_tracker = sheets_tracker
        self.ledger = ledger
        self.is_running = False

        self.config: Dict[str, Any] = {
            "url": "https://docs.google.com/spreadsheets/d/1-4HOJ7A8eydJOR6Gyci_7HvZWhl-vAGumqjItwSIriw/edit?usp=sharing",
            "sheet_name": "NOV-26",
            "target_col": "H",
            "start_row": 110,
            "scan_all_tabs": False,
            "interval_minutes": 30,
            "workers": 5,
        }

        self.stats: Dict[str, Any] = {
            "total_cycles": 0,
            "last_run_time": None,
            "next_run_time": None,
            "total_scanned": 0,
            "active_tracked": 0,
            "delivered_skipped": 0,
            "newly_delivered": 0,
            "last_error": None,
        }

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and metrics of the Auto-Pilot daemon."""
        with self._lock:
            # Calculate remaining seconds until next sync
            remaining_sec = 0
            if self.is_running and self.stats.get("next_run_time"):
                try:
                    nxt = datetime.datetime.fromisoformat(self.stats["next_run_time"])
                    diff = (nxt - datetime.datetime.now()).total_seconds()
                    remaining_sec = max(0, int(diff))
                except Exception:
                    pass

            return {
                "status": "success",
                "is_running": self.is_running,
                "config": dict(self.config),
                "stats": dict(self.stats),
                "next_run_countdown_sec": remaining_sec,
            }

    def start(self, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Starts the Auto-Pilot background daemon."""
        with self._lock:
            if self.is_running:
                return {
                    "status": "already_running",
                    "message": "Auto-Pilot is already running.",
                    "status_data": self.get_status(),
                }

            if config_override:
                for k, v in config_override.items():
                    if v is not None and k in self.config:
                        self.config[k] = v

            self._stop_event.clear()
            self.is_running = True
            self.stats["last_error"] = None

            # Spawn dedicated background worker thread
            self._thread = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name="AutoPilot-Worker",
            )
            self._thread.start()
            logger.info(
                f"[AutoPilot] Daemon STARTED for Google Sheet '{self.config['url'][:40]}...' "
                f"(Tab: {self.config['sheet_name']}, Col: {self.config['target_col']}, "
                f"Start Row: {self.config['start_row']}, Interval: {self.config['interval_minutes']}m)"
            )

        return {
            "status": "started",
            "message": "Auto-Pilot background lifecycle tracker activated successfully.",
            "status_data": self.get_status(),
        }

    def stop(self) -> Dict[str, Any]:
        """Stops the Auto-Pilot background daemon gracefully."""
        with self._lock:
            if not self.is_running:
                return {
                    "status": "already_stopped",
                    "message": "Auto-Pilot is not running.",
                    "status_data": self.get_status(),
                }

            self.is_running = False
            self._stop_event.set()
            self.stats["next_run_time"] = None
            logger.info("[AutoPilot] Daemon STOP requested.")

        return {
            "status": "stopped",
            "message": "Auto-Pilot background lifecycle tracker paused.",
            "status_data": self.get_status(),
        }

    def run_now(self) -> Dict[str, Any]:
        """Executes a single tracking cycle immediately in-line."""
        return self._execute_cycle()

    def _worker_loop(self):
        """Background thread loop that executes tracking cycles at regular intervals."""
        # Initial run on start
        self._execute_cycle()

        while not self._stop_event.is_set():
            interval_sec = max(60, int(self.config.get("interval_minutes", 30)) * 60)
            next_time = datetime.datetime.now() + datetime.timedelta(seconds=interval_sec)

            with self._lock:
                self.stats["next_run_time"] = next_time.isoformat()

            logger.info(f"[AutoPilot] Next scheduled cycle at {self.stats['next_run_time']}")

            # Sleep in 1-second chunks to respond quickly to stop requests
            for _ in range(interval_sec):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

            if not self._stop_event.is_set():
                self._execute_cycle()

    def _execute_cycle(self) -> Dict[str, Any]:
        """Runs a complete sync cycle from Google Sheet."""
        t0 = time.time()
        logger.info("[AutoPilot] Executing scheduled lifecycle tracking cycle...")

        try:
            url = self.config["url"]
            tab = self.config["sheet_name"]
            col = self.config["target_col"]
            start_row = self.config["start_row"]
            scan_all = self.config["scan_all_tabs"]
            workers = self.config.get("workers", 5)

            result = self.sheets_tracker.sync_and_track_lifecycle(
                url,
                sheet_name=tab,
                target_col=col,
                start_row=start_row,
                scan_all_tabs=scan_all,
                workers=workers,
                recheck_delivered=False,
            )

            with self._lock:
                self.stats["total_cycles"] += 1
                self.stats["last_run_time"] = datetime.datetime.now().isoformat()
                self.stats["total_scanned"] = result.get("total_sheet_awbs", 0)
                self.stats["active_tracked"] = result.get("active_tracked_count", 0)
                self.stats["delivered_skipped"] = result.get("already_delivered_skipped", 0)
                self.stats["newly_delivered"] = result.get("delivered_count", 0)
                self.stats["last_error"] = None

            elapsed = round(time.time() - t0, 2)
            logger.info(
                f"[AutoPilot] Cycle #{self.stats['total_cycles']} completed in {elapsed}s: "
                f"{self.stats['total_scanned']} AWBs scanned | "
                f"{self.stats['active_tracked']} active tracked | "
                f"{self.stats['delivered_skipped']} delivered skipped"
            )
            return result

        except Exception as e:
            err_msg = f"AutoPilot cycle error: {str(e)}"
            logger.error(err_msg, exc_info=True)
            with self._lock:
                self.stats["last_error"] = err_msg
            return {"status": "error", "message": err_msg}
