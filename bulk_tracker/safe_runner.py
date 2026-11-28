"""
Safe, Detection-Proof, Chunked Human-Paced Tracking Runner.

Design principles (no sugarcoating):
1. Pre-Filter First (0 network hits): Separates unsupported prefixes (outside the 13
   supported carriers) into Table 3 (Unreachable / Unsupported) before any request runs.
2. Airline Shuffling & Small Chunks: Shuffles supported AWBs across carriers so no single
   airline portal is hammered consecutively, and groups them into small chunks (e.g. 6 AWBs).
3. Human-Like Random Timing: Sleeps a randomized 2-to-7 minute (120s-420s) cooldown
   between chunks + 3.5-7.0s per-domain & 1.0-2.5s global jitter inside each chunk.
4. Safe Failure Quarantine: Any AWB returning UNREACHABLE / ERROR / NOT_FOUND is moved
   to Table 3 with its exact reason so it does not loop-fail in Table 1.
5. Transparent Live Steps & Plan: Exposes exact step-by-step progress, chunk countdown,
   proxy mode, and execution plan to the Web UI.
"""

import datetime
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import random
import threading
import time
from typing import Any, Dict, List, Optional

from bulk_tracker.engine import BulkCargoTracker
from bulk_tracker.proxy_pool import proxy_pool
from bulk_tracker.circuit_breaker import circuit_breaker

logger = logging.getLogger("bulk_tracker.safe_runner")
_LOG_DIR = Path(__file__).resolve().parent.parent / "data"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    _fh = RotatingFileHandler(_LOG_DIR / "safe_tracker.log", maxBytes=2 * 1024 * 1024, backupCount=3)
    _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(_fh)
    logger.setLevel(logging.INFO)


class SafeChunkedTracker:
    """Singleton manager for safe, human-paced chunked tracking of the Active Queue."""

    def __init__(self, ledger):
        self.ledger = ledger
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self.is_running: bool = False
        self.current_step: str = "IDLE"
        self.plan: Dict[str, Any] = {}
        self.progress: Dict[str, Any] = {
            "total_to_track": 0,
            "completed_awbs": 0,
            "delivered_moved": 0,
            "unreachable_moved": 0,
            "active_remaining": 0,
            "current_chunk": 0,
            "total_chunks": 0,
            "current_awb": None,
            "next_chunk_in_sec": 0,
            "started_at": None,
            "finished_at": None,
            "last_error": None,
        }
        self.step_logs: List[Dict[str, str]] = []

    def _add_log(self, step: str, message: str, level: str = "info"):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self.step_logs.append({"time": ts, "step": step, "message": message, "level": level})
            if len(self.step_logs) > 80:
                self.step_logs = self.step_logs[-80:]
        logger.info(f"[SafeRunner:{step}] {message}")

    def run_health_check(self) -> Dict[str, Any]:
        """
        Live pre-flight diagnostics for Proxy, Tor daemon, Circuit Breakers, and Queue.
        """
        if proxy_pool.mode == "tor":
            proxy_pool._detect_tor()
        pst = proxy_pool.get_status()
        cb_all = circuit_breaker.get_all_status()
        open_breakers = [k for k, v in cb_all.items() if isinstance(v, dict) and v.get("state") == "OPEN"]

        mode = pst.get("mode", "off")
        proxy_ok = True
        proxy_msg = "Direct IP (Polite Human Jitter — Best for Mac residential/office IP)"

        if mode == "tor":
            if pst.get("tor_available"):
                proxy_ok = True
                proxy_msg = f"Tor SOCKS5 Active ({pst.get('tor_url')})"
            else:
                proxy_ok = False
                proxy_msg = "Tor selected, but NO local Tor daemon running on port 9050/9150 (falling back to Direct IP!)"
        elif mode == "free_pool":
            cnt = pst.get("healthy_proxies_count", 0)
            if cnt > 0:
                proxy_ok = True
                proxy_msg = f"Free Proxy Pool Active ({cnt} healthy proxies)"
            else:
                proxy_ok = False
                proxy_msg = "Free Proxy Pool has 0 healthy proxies right now (unreliable for airlines — switch to Direct or Tor)"
        elif mode == "custom":
            cnt = pst.get("custom_proxies_count", 0)
            proxy_ok = cnt > 0
            proxy_msg = f"Custom Proxy List ({cnt} configured)" if cnt > 0 else "Custom Proxy selected but 0 proxies configured"

        q = self.ledger.get_tracking_queue_and_kpis()
        return {
            "status": "success",
            "proxy_ok": proxy_ok,
            "proxy_mode": mode,
            "proxy_message": proxy_msg,
            "tor_available": pst.get("tor_available", False),
            "healthy_proxies_count": pst.get("healthy_proxies_count", 0),
            "open_circuit_breakers": open_breakers,
            "carriers_healthy": len(open_breakers) == 0,
            "supported_queue_count": q["kpis"]["total_active_queue"],
            "unreachable_count": q["kpis"]["total_unreachable"],
            "log_file": str(_LOG_DIR / "safe_tracker.log"),
        }

    def build_plan(
        self,
        chunk_size: int = 6,
        min_delay_min: float = 2.0,
        max_delay_min: float = 7.0,
        cooldown_hours: float = 6.0,
    ) -> Dict[str, Any]:
        """Runs 0-API pre-filter + 6h cooldown resume filter and builds a transparent execution plan."""
        pf = self.ledger.prefilter_supported_queue()
        q = self.ledger.get_tracking_queue_and_kpis()
        all_active = q["active_queue"]

        # 6-hour per-AWB cooldown & automatic crash/stop resume filter
        active = []
        skipped_cooldown = 0
        for item in all_active:
            if self.ledger.get_fresh_cached_record(item["awb_clean"], cooldown_hours=cooldown_hours):
                skipped_cooldown += 1
            else:
                active.append(item)

        c_size = max(1, min(20, int(chunk_size or 6)))
        min_d = max(0.5, float(min_delay_min or 2.0))
        max_d = max(min_d, float(max_delay_min or 7.0))

        total_chunks = (len(active) + c_size - 1) // c_size if active else 0
        avg_delay_min = (min_d + max_d) / 2.0
        est_minutes = round(max(0, total_chunks - 1) * avg_delay_min + (len(active) * 0.12), 1)

        proxy_st = proxy_pool.get_status()
        return {
            "supported_to_track": len(active),
            "skipped_cooldown_6h": skipped_cooldown,
            "prefiltered_unsupported_moved": pf["moved_unsupported"],
            "total_unreachable_now": q["kpis"]["total_unreachable"],
            "chunk_size": c_size,
            "total_chunks": total_chunks,
            "chunk_delay_range_min": f"{min_d:.1f}–{max_d:.1f} min (random)",
            "min_delay_sec": int(min_d * 60),
            "max_delay_sec": int(max_d * 60),
            "per_request_jitter": "3.5–7.0s per airline + 1.0–2.5s global",
            "workers": "1 (Serial stealth mode)",
            "proxy_mode": proxy_st.get("mode", "off"),
            "cooldown_hours": cooldown_hours,
            "estimated_total_minutes": est_minutes,
        }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "status": "success",
                "is_running": self.is_running,
                "current_step": self.current_step,
                "plan": dict(self.plan),
                "progress": dict(self.progress),
                "step_logs": list(self.step_logs[-25:]),
            }

    def start(
        self,
        chunk_size: int = 6,
        min_delay_min: float = 2.0,
        max_delay_min: float = 7.0,
    ) -> Dict[str, Any]:
        with self._lock:
            if self.is_running:
                return {
                    "status": "already_running",
                    "message": "Safe Chunked Tracker is already running.",
                    "data": self.get_status_unlocked(),
                }
            self.step_logs = []
            self._stop_event.clear()
            self.is_running = True
            self.current_step = "STEP_1_PREFILTER"

        plan = self.build_plan(chunk_size=chunk_size, min_delay_min=min_delay_min, max_delay_min=max_delay_min)
        with self._lock:
            self.plan = plan
            self.progress = {
                "total_to_track": plan["supported_to_track"],
                "completed_awbs": 0,
                "delivered_moved": 0,
                "unreachable_moved": 0,
                "active_remaining": plan["supported_to_track"],
                "current_chunk": 0,
                "total_chunks": plan["total_chunks"],
                "current_awb": None,
                "next_chunk_in_sec": 0,
                "started_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": None,
                "last_error": None,
            }

        self._add_log(
            "Step 1: Pre-Filter & Resume",
            f"Filtered 13 supported airlines: {plan['supported_to_track']} ready to track | "
            f"{plan.get('skipped_cooldown_6h', 0)} skipped (6h DB cache/resume) | "
            f"{plan['prefiltered_unsupported_moved']} unsupported moved to Table 3.",
            "info",
        )

        if plan["supported_to_track"] == 0:
            with self._lock:
                self.is_running = False
                self.current_step = "COMPLETED"
                self.progress["finished_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._add_log("Complete", "No supported AWBs pending in Active Tracking List.", "success")
            return {"status": "completed", "data": self.get_status()}

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(plan["chunk_size"], plan["min_delay_sec"], plan["max_delay_sec"]),
            daemon=True,
            name="SafeChunkedTracker-Worker",
        )
        self._thread.start()
        return {"status": "started", "data": self.get_status()}

    def get_status_unlocked(self) -> Dict[str, Any]:
        return {
            "status": "success",
            "is_running": self.is_running,
            "current_step": self.current_step,
            "plan": dict(self.plan),
            "progress": dict(self.progress),
            "step_logs": list(self.step_logs[-25:]),
        }

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            if not self.is_running:
                return {"status": "already_stopped", "data": self.get_status_unlocked()}
            self._stop_event.set()
            self.current_step = "STOPPING"
        self._add_log("Stopping", "Stop requested — finishing current AWB safely and pausing.", "warning")
        return {"status": "stopping", "data": self.get_status()}

    def _run_loop(self, chunk_size: int, min_delay_sec: int, max_delay_sec: int):
        try:
            q = self.ledger.get_tracking_queue_and_kpis()
            items = [
                item for item in q["active_queue"]
                if not self.ledger.get_fresh_cached_record(item["awb_clean"], cooldown_hours=6.0)
            ]
            # Shuffle across carriers so same airline is not hit consecutively
            random.shuffle(items)

            chunks = [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]
            tracker = BulkCargoTracker(max_global_workers=1, max_domain_workers=1, safe_mode=True)

            health = self.run_health_check()
            self._add_log(
                "Pre-Flight Health",
                f"Proxy: {health['proxy_message']} | Carriers Healthy: {health['carriers_healthy']} | Log: safe_tracker.log",
                "info" if health["proxy_ok"] else "warning",
            )
            self._add_log(
                "Step 2: Plan Ready",
                f"Prepared {len(chunks)} shuffled chunks ({chunk_size} AWBs/chunk), "
                f"random cooldown {min_delay_sec//60}–{max_delay_sec//60} min, Proxy={self.plan.get('proxy_mode', 'off')}.",
                "info",
            )

            for idx, chunk in enumerate(chunks, start=1):
                if self._stop_event.is_set():
                    break

                with self._lock:
                    self.current_step = f"STEP_3_CHUNK_{idx}_OF_{len(chunks)}"
                    self.progress["current_chunk"] = idx
                    self.progress["next_chunk_in_sec"] = 0

                self._add_log(f"Chunk {idx}/{len(chunks)}", f"Starting chunk with {len(chunk)} AWBs (human-paced 1 worker)...", "info")

                for item in chunk:
                    if self._stop_event.is_set():
                        break
                    awb_str = item.get("awb_no") or item.get("awb_clean")
                    clean_k = item.get("awb_clean")
                    with self._lock:
                        self.progress["current_awb"] = awb_str

                    try:
                        summary = tracker.track_batch([awb_str])
                        if summary.records:
                            rec = summary.records[0]
                            upserted = self.ledger.upsert_record(rec)
                            st = (upserted.get("status") or "").upper()
                            with self._lock:
                                self.progress["completed_awbs"] += 1
                                self.progress["active_remaining"] = max(0, self.progress["active_remaining"] - 1)
                                if st == "DELIVERED":
                                    self.progress["delivered_moved"] += 1
                                elif st in ("SKIPPED", "UNREACHABLE", "ERROR", "NOT_FOUND"):
                                    self.progress["unreachable_moved"] += 1

                            if st in ("SKIPPED", "UNREACHABLE", "ERROR", "NOT_FOUND"):
                                reason = upserted.get("status_detail") or f"Carrier returned {st}"
                                self.ledger.mark_unreachable_reason(clean_k, reason)
                                self._add_log(f"AWB {awb_str}", f"Moved to Table 3 ({st}): {reason}", "warning")
                            elif st == "DELIVERED":
                                self._add_log(f"AWB {awb_str}", "DELIVERED -> Moved to Table 2 Report.", "success")
                            else:
                                self._add_log(f"AWB {awb_str}", f"Updated status: {st}", "info")
                    except Exception as awb_err:
                        reason = f"Tracking exception: {str(awb_err)[:120]}"
                        self.ledger.mark_unreachable_reason(clean_k, reason)
                        self._add_log(f"AWB {awb_str}", reason, "error")

                # Cooldown between chunks (random 2-7 min)
                if idx < len(chunks) and not self._stop_event.is_set():
                    wait_sec = random.randint(min_delay_sec, max_delay_sec)
                    with self._lock:
                        self.current_step = f"STEP_4_COOLDOWN_AFTER_CHUNK_{idx}"
                        self.progress["current_awb"] = None
                        self.progress["next_chunk_in_sec"] = wait_sec

                    self._add_log(
                        "Human Cooldown",
                        f"Chunk {idx}/{len(chunks)} done. Sleeping randomly for {wait_sec // 60}m {wait_sec % 60}s before next chunk (anti-detection)...",
                        "info",
                    )

                    for rem in range(wait_sec, 0, -1):
                        if self._stop_event.is_set():
                            break
                        with self._lock:
                            self.progress["next_chunk_in_sec"] = rem
                        time.sleep(1)

            with self._lock:
                self.current_step = "STOPPED" if self._stop_event.is_set() else "COMPLETED"
                self.progress["current_awb"] = None
                self.progress["next_chunk_in_sec"] = 0
                self.progress["finished_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._add_log(
                "Finished",
                f"Safe tracking {self.current_step.lower()}: {self.progress['completed_awbs']} processed, "
                f"{self.progress['delivered_moved']} delivered, {self.progress['unreachable_moved']} moved to Table 3.",
                "success",
            )
        except Exception as e:
            logger.error(f"[SafeRunner] Fatal error: {e}", exc_info=True)
            with self._lock:
                self.current_step = "ERROR"
                self.progress["last_error"] = str(e)
            self._add_log("Error", str(e), "error")
        finally:
            with self._lock:
                self.is_running = False
