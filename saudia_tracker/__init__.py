"""
Saudia Cargo Tracking Package (IATA Prefix 065 - SV).
"""

from saudia_tracker.constants import (
    AIRLINE_NAME,
    AIRLINE_CODE,
    AIRLINE_PREFIX,
    SAUDIA_BASE_URL,
    SAUDIA_DIRECT_URL,
    TRACK_TRACE_AIRCARGO_URL,
)
from saudia_tracker.models import (
    SaudiaFlightLeg,
    SaudiaMilestone,
    SaudiaOverview,
    SaudiaTrackingResult,
)
from saudia_tracker.client import (
    SaudiaCargoClient,
    SaudiaShipmentNotFoundError,
    SaudiaTrackingError,
)

__all__ = [
    "AIRLINE_NAME",
    "AIRLINE_CODE",
    "AIRLINE_PREFIX",
    "SAUDIA_BASE_URL",
    "SAUDIA_DIRECT_URL",
    "TRACK_TRACE_AIRCARGO_URL",
    "SaudiaFlightLeg",
    "SaudiaMilestone",
    "SaudiaOverview",
    "SaudiaTrackingResult",
    "SaudiaCargoClient",
    "SaudiaShipmentNotFoundError",
    "SaudiaTrackingError",
]
