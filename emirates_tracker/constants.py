"""
Constants and event mappings for Emirates SkyCargo (IATA prefix 176) tracking.
"""

TRACK_TRACE_URL = "https://www.track-trace.com/aircargo"
EMIRATES_PORTAL_URL = "https://eskycargo.emirates.com/app/offerandorder/"

OAUTH_TOKEN_URL = "https://eskycargo.emirates.com/api/uaa/guest/oauth/token?productName=offerandorder"
SEARCH_URL = "https://eskycargo.emirates.com/api/order/services/cargo/v1/orders/actions/search?view=summary"
ORDER_DETAILS_URL = "https://eskycargo.emirates.com/api/order/services/cargo/v1/orders/b{booking_reference}"

AIRLINE_PREFIX = "176"
AIRLINE_NAME = "Emirates SkyCargo"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "x-referer": "https://EK",
    "referer": "https://eskycargo.emirates.com/app/offerandorder/",
    "origin": "https://eskycargo.emirates.com",
}

IATA_EVENT_MAP = {
    "DLV": "Delivered to Consignee / Agent",
    "NFD": "Notified for Delivery (Consignee Advised)",
    "RCF": "Received from Flight (Unloaded & Transferred to Warehouse)",
    "ARR": "Arrived at Airport",
    "DEP": "Departed from Airport",
    "MAN": "Shipment Manifested on Flight",
    "RCS": "Received Cargo from Shipper (Accepted at Origin)",
    "BKD": "Shipment Booked on Flight",
    "AWD": "Air Waybill Documentation Delivered",
    "DIS": "Discrepancy Reported",
    "PRE": "Shipment Prepared for Flight",
    "TFD": "Transferred to Connecting Carrier",
    "FOH": "Freight on Hand",
    "DRN": "Delivery Receipt Notice",
    "TGC": "Transferred to Ground Carrier",
    "CRC": "Customs Release Consignment",
}
