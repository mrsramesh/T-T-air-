"""
Virgin Atlantic Cargo (IATA Prefix 932) Tracking Package.
"""

from virgin_tracker.constants import (
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    VIRGIN_PORTAL_URL,
    VIRGIN_DIRECT_DETAIL_URL,
)
from virgin_tracker.models import (
    VirginAirport,
    VirginFlightSegment,
    VirginMilestone,
    VirginOverview,
    VirginTrackingResult,
)
from virgin_tracker.client import (
    VirginCargoClient,
    VirginShipmentNotFoundError,
    VirginTrackingError,
)

__all__ = [
    "AIRLINE_NAME",
    "AIRLINE_PREFIX",
    "VIRGIN_PORTAL_URL",
    "VIRGIN_DIRECT_DETAIL_URL",
    "VirginAirport",
    "VirginFlightSegment",
    "VirginMilestone",
    "VirginOverview",
    "VirginTrackingResult",
    "VirginCargoClient",
    "VirginShipmentNotFoundError",
    "VirginTrackingError",
]
