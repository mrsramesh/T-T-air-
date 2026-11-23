"""
Etihad Cargo Tracking Package (IATA Prefix 607 - EY).
"""

from etihad_tracker.constants import (
    AIRLINE_NAME,
    AIRLINE_CODE,
    AIRLINE_PREFIX,
    ETIHAD_BASE_URL,
    ETIHAD_DIRECT_URL,
    TRACK_TRACE_AIRCARGO_URL,
)
from etihad_tracker.models import (
    EtihadFlightLeg,
    EtihadMilestone,
    EtihadOverview,
    EtihadTrackingResult,
)
from etihad_tracker.client import (
    EtihadCargoClient,
    EtihadShipmentNotFoundError,
    EtihadTrackingError,
)

__all__ = [
    "AIRLINE_NAME",
    "AIRLINE_CODE",
    "AIRLINE_PREFIX",
    "ETIHAD_BASE_URL",
    "ETIHAD_DIRECT_URL",
    "TRACK_TRACE_AIRCARGO_URL",
    "EtihadFlightLeg",
    "EtihadMilestone",
    "EtihadOverview",
    "EtihadTrackingResult",
    "EtihadCargoClient",
    "EtihadShipmentNotFoundError",
    "EtihadTrackingError",
]
