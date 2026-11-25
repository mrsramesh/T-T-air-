"""
Carrier Circuit Breaker and Adaptive Fallback Router.
Protects against breaking changes on carrier websites:
- Monitors success/failure rates per carrier.
- Trips circuit if 5 consecutive queries fail.
- Automatically reroutes traffic to fallback aggregators (Track-Trace, ParcelsApp, etc.)
  when direct carrier website breaks or changes its DOM.
- Auto-recovers when carrier portal stabilizes.
"""

import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("circuit_breaker")


class CarrierCircuitBreaker:
    """
    Tracks carrier portal reliability and manages state transitions:
    HEALTHY (0-2 fails) -> DEGRADED (3-4 fails) -> TRIPPED (5+ fails).
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout_sec: int = 600):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_sec = recovery_timeout_sec
        self._stats: Dict[str, Dict[str, Any]] = {}

    def _get_entry(self, carrier_code: str) -> Dict[str, Any]:
        if carrier_code not in self._stats:
            self._stats[carrier_code] = {
                "consecutive_failures": 0,
                "total_successes": 0,
                "total_failures": 0,
                "state": "HEALTHY",  # HEALTHY, DEGRADED, TRIPPED
                "last_failure_time": 0.0,
                "last_error": None,
                "fallback_active": False,
            }
        return self._stats[carrier_code]

    def record_success(self, carrier_code: str):
        """Records a successful carrier query, resetting failure count."""
        entry = self._get_entry(carrier_code)
        entry["consecutive_failures"] = 0
        entry["total_successes"] += 1
        if entry["state"] != "HEALTHY":
            logger.info(f"[CircuitBreaker] Carrier {carrier_code} recovered to HEALTHY state.")
        entry["state"] = "HEALTHY"
        entry["fallback_active"] = False

    def record_failure(self, carrier_code: str, error_msg: str) -> str:
        """
        Records a failed query. Returns new state: HEALTHY, DEGRADED, or TRIPPED.
        """
        entry = self._get_entry(carrier_code)
        entry["consecutive_failures"] += 1
        entry["total_failures"] += 1
        entry["last_failure_time"] = time.time()
        entry["last_error"] = str(error_msg)[:200]

        if entry["consecutive_failures"] >= self.failure_threshold:
            if entry["state"] != "TRIPPED":
                logger.warning(
                    f"[CircuitBreaker] Carrier {carrier_code} TRIPPED after {entry['consecutive_failures']} consecutive failures. "
                    f"DOM change or portal block suspected: {error_msg}. Activating fallback aggregator routing."
                )
            entry["state"] = "TRIPPED"
            entry["fallback_active"] = True
        elif entry["consecutive_failures"] >= 3:
            entry["state"] = "DEGRADED"

        return entry["state"]

    def should_use_fallback(self, carrier_code: str) -> bool:
        """Determines if requests for this carrier should bypass broken direct portal."""
        entry = self._get_entry(carrier_code)
        if entry["state"] == "TRIPPED":
            # Test recovery after recovery_timeout_sec
            if time.time() - entry["last_failure_time"] > self.recovery_timeout_sec:
                logger.info(f"[CircuitBreaker] Half-open recovery probe for carrier {carrier_code}.")
                return False  # Let one through to test
            return True
        return False

    def get_all_status(self) -> Dict[str, Any]:
        """Returns health status across all carriers for UI dashboard badges."""
        return {code: dict(data) for code, data in self._stats.items()}


# Singleton instance
circuit_breaker = CarrierCircuitBreaker()
