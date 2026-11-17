"""
Constants, URLs, and action codes for EgyptAir Cargo (Cargo Flash Portal).
"""

AIRLINE_PREFIX = "077"
AIRLINE_NAME = "EgyptAir Cargo (Cargo Flash)"
CARGOFLASH_PORTAL_BASE = "https://msres.cargoflash.com/Tracking/AWB"
CARGOFLASH_API_URL = "https://msres.cargoflash.com/Services/Shipment/AWBTrackingService.svc/GetAWBTrackingRecord"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Standard event descriptions from Garuda Cargo Flash frontend
ACTION_DESCRIPTIONS = {
    "BKD": "Booking confirmed",
    "EXE": "Booking executed",
    "RCS": "Shipment accepted",
    "REPLAN": "Shipment Re-planned",
    "RCT": "Shipment transferred",
    "PRE": "Pre-manifested",
    "MAN": "Manifested",
    "DEP": "Departed",
    "RCF": "Received from flight",
    "TFD": "Shipment transferred",
    "ARR": "AWB Arrived",
    "NFD": "Ready for pick-up",
    "AWD": "Document arrived",
    "DLV": "Delivered",
}

ACTION_SENTENCES = {
    "BKD": "has been booked at",
    "EXE": "has been executed at",
    "RCS": "has been accepted at",
    "REPLAN": "has been Re-planned at",
    "RCT": "has been transferred at",
    "PRE": "has been pre-manifested at",
    "MAN": "has been manifested at",
    "DEP": "has been Departed from",
    "ARR": "has been arrived at",
    "RCF": "has been arrived at",
    "TFD": "has been transferred at",
    "NFD": "has been notified at",
    "AWD": "document has arrived at",
    "DLV": "has been delivered at",
}
