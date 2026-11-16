"""
Emirates SkyCargo Tracking Package.
Provides both high-performance direct REST tracking and Playwright browser tracking.
"""

from emirates_tracker.constants import (
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    IATA_EVENT_MAP,
    TRACK_TRACE_URL,
    EMIRATES_PORTAL_URL,
)
from emirates_tracker.models import (
    EmiratesAirport,
    EmiratesItineraryLeg,
    EmiratesMilestone,
    EmiratesOrderSummary,
    EmiratesOverview,
    EmiratesTrackingResult,
)
from emirates_tracker.client import (
    EmiratesTrackerClient,
    EmiratesTrackingError,
    EmiratesShipmentNotFoundError,
    EmiratesAuthenticationError,
)
from emirates_tracker.browser import EmiratesBrowserTracker

__all__ = [
    "AIRLINE_NAME",
    "AIRLINE_PREFIX",
    "IATA_EVENT_MAP",
    "TRACK_TRACE_URL",
    "EMIRATES_PORTAL_URL",
    "EmiratesAirport",
    "EmiratesItineraryLeg",
    "EmiratesMilestone",
    "EmiratesOrderSummary",
    "EmiratesOverview",
    "EmiratesTrackingResult",
    "EmiratesTrackerClient",
    "EmiratesTrackingError",
    "EmiratesShipmentNotFoundError",
    "EmiratesAuthenticationError",
    "EmiratesBrowserTracker",
]
