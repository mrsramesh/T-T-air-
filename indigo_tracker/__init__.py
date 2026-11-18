"""
IndiGo CarGo (6E - prefix 312) Tracking Package.
Provides production-grade tracking, WebForms automation, and rich models.
"""

from indigo_tracker.client import (
    IndigoCargoClient,
    IndigoShipmentNotFoundError,
    IndigoTrackingError,
)
from indigo_tracker.constants import (
    AIRLINE_CODE,
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    INDIGO_PORTAL_URL,
)
from indigo_tracker.models import (
    IndigoBookingItem,
    IndigoDeliveryOrder,
    IndigoOverview,
    IndigoStatusHistoryItem,
    IndigoTrackingResult,
)

__all__ = [
    "IndigoCargoClient",
    "IndigoShipmentNotFoundError",
    "IndigoTrackingError",
    "IndigoBookingItem",
    "IndigoDeliveryOrder",
    "IndigoOverview",
    "IndigoStatusHistoryItem",
    "IndigoTrackingResult",
    "AIRLINE_CODE",
    "AIRLINE_NAME",
    "AIRLINE_PREFIX",
    "INDIGO_PORTAL_URL",
]
