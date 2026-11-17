"""
EgyptAir Cargo (Cargo Flash Portal - 077) Tracking Package.
"""

from cargoflash_tracker.client import (
    CargoFlashClient,
    CargoFlashTrackingError,
    CargoFlashShipmentNotFoundError,
)
from cargoflash_tracker.models import (
    CargoFlashFlightDetail,
    CargoFlashMilestonePlanItem,
    CargoFlashOverview,
    CargoFlashTrackingResult,
)
from cargoflash_tracker.constants import (
    AIRLINE_PREFIX,
    AIRLINE_NAME,
    CARGOFLASH_PORTAL_BASE,
    CARGOFLASH_API_URL,
)

__all__ = [
    "CargoFlashClient",
    "CargoFlashTrackingError",
    "CargoFlashShipmentNotFoundError",
    "CargoFlashFlightDetail",
    "CargoFlashMilestonePlanItem",
    "CargoFlashOverview",
    "CargoFlashTrackingResult",
    "AIRLINE_PREFIX",
    "AIRLINE_NAME",
    "CARGOFLASH_PORTAL_BASE",
    "CARGOFLASH_API_URL",
]
