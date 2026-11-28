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
            "interval_minutes": 60,
            "workers": 1,
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
            "is_cycling": False,
        }

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._last_manifest_sig: Optional[str] = None
        self.sheet_watch_interval_sec: int = 300  # Check enabled Google Sheets for edits/new tabs every 5 mins (0 airline hits)

        # Auto-migrate existing single sheet into sheet_sources as Sheet #1 if empty
        try:
            self.ledger.ensure_default_sheet_source(
                default_url=self.config["url"],
                label="Primary Cargo Sheet",
                sheet_name=self.config.get("sheet_name") or "NOV-26",
                target_col=self.config.get("target_col") or "H",
                start_row=int(self.config.get("start_row") or 110),
                scan_all_tabs=True,
            )
        except Exception as e:
            logger.warning(f"[AutoPilot] Default sheet migration skipped: {e}")

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

            # Persist state to SQLite so it survives restarts
            try:
                self.ledger.save_autopilot_state(is_running=True, config=self.config)
            except Exception as se:
                logger.warning(f"[AutoPilot] Could not persist state to DB: {se}")

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
            try:
                self.ledger.save_autopilot_state(is_running=False, config=self.config)
            except Exception as se:
                logger.warning(f"[AutoPilot] Could not persist state to DB: {se}")
            logger.info("[AutoPilot] Daemon STOP requested.")

        return {
            "status": "stopped",
            "message": "Auto-Pilot background lifecycle tracker paused.",
            "status_data": self.get_status(),
        }

    def resume_from_storage(self) -> bool:
        """
        Solves Risk #6: Auto-resumes Auto-Pilot if it was running before server restart.
        """
        try:
            saved = self.ledger.load_autopilot_state()
            if saved and saved.get("is_running"):
                cfg = saved.get("config") or {}
                logger.info("[AutoPilot] Found persisted active state in database. Auto-resuming background daemon...")
                self.start(config_override=cfg)
                return True
        except Exception as e:
            logger.warning(f"[AutoPilot] Could not resume state from database: {e}")
        return False

    def run_now(self) -> Dict[str, Any]:
        """Executes a single tracking cycle immediately in-line."""
        return self._execute_cycle()

    def _worker_loop(self):
        """Background thread loop that executes tracking cycles at regular intervals."""
        # Initial run on start
        self._execute_cycle()

        while not self._stop_event.is_set():
            import random
            base_sec = max(60, int(self.config.get("interval_minutes", 60)) * 60)
            # Anti-clockwork jitter: adds 30-180s random offset so bots don't fire on exact clock ticks
            jitter_sec = random.randint(30, 180)
            interval_sec = base_sec + jitter_sec
            next_time = datetime.datetime.now() + datetime.timedelta(seconds=interval_sec)

            with self._lock:
                self.stats["next_run_time"] = next_time.isoformat()

            logger.info(f"[AutoPilot] Next scheduled cycle at {self.stats['next_run_time']}")

            # Sleep in 1-second chunks; check all enabled Google Sheets every 5 minutes (0 airline hits)
            for elapsed_sec in range(1, interval_sec + 1):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

                if elapsed_sec % self.sheet_watch_interval_sec == 0 and elapsed_sec < interval_sec - 10:
                    try:
                        scan_res = self.sheets_tracker.scan_enabled_sheets()
                        if scan_res.get("changed_sheets") or scan_res.get("total_new_awbs", 0) > 0 or scan_res.get("new_tabs_detected"):
                            logger.info(
                                f"[AutoPilot Smart Watcher] Detected changes in enabled sheets "
                                f"({scan_res.get('changed_sheets')}, new AWBs: {scan_res.get('total_new_awbs')}). "
                                f"Triggering immediate sync..."
                            )
                            break
                    except Exception as watch_err:
                        logger.debug(f"[AutoPilot Smart Watcher] Multi-sheet check skipped: {watch_err}")

            if not self._stop_event.is_set():
                self._execute_cycle()

    def _execute_cycle(self) -> Dict[str, Any]:
        """Runs a complete sync cycle from Google Sheet."""
        t0 = time.time()
        logger.info("[AutoPilot] Executing scheduled lifecycle tracking cycle...")
        with self._lock:
            self.stats["is_cycling"] = True

        try:
            workers = self.config.get("workers", 1)
            result = self.sheets_tracker.sync_all_enabled_sheets(
                workers=workers,
                track_live=True,
            )

            new_delivered = result.get("newly_delivered_count", 0)

            with self._lock:
                self.stats["total_cycles"] += 1
                self.stats["last_run_time"] = datetime.datetime.now().isoformat()
                self.stats["total_scanned"] = result.get("total_sheet_awbs", 0)
                self.stats["active_tracked"] = result.get("active_tracked_count", 0)
                self.stats["delivered_skipped"] = result.get("already_delivered_skipped", 0)
                self.stats["newly_delivered"] = new_delivered
                self.stats["last_error"] = None

            # Dispatched notification if new shipments delivered
            if new_delivered > 0:
                try:
                    from bulk_tracker.notifier import notifier
                    notifier.send_alert_async(
                        "AutoPilot: Shipments Delivered!",
                        f"Cycle #{self.stats['total_cycles']} delivered {new_delivered} shipments.\n"
                        f"Active remaining: {self.stats['active_tracked']}",
                        level="info",
                    )
                except Exception:
                    pass

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
            try:
                from bulk_tracker.notifier import notifier
                notifier.send_alert_async("AutoPilot Error", err_msg, level="error")
            except Exception:
                pass
            return {"status": "error", "message": err_msg}
        finally:
            with self._lock:
                self.stats["is_cycling"] = False
