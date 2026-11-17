"""
Constants and event code mappings for Kuwait Airways Cargo (IATA prefix 229).
"""

PORTAL_URL = "https://www.kuwaitairways.com/en/cargo/tracking"
API_ENDPOINT = "https://services.kuwaitairways.com/cargo/api/GetCargoInfo"
AIRLINE_PREFIX = "229"
AIRLINE_NAME = "Kuwait Airways"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.kuwaitairways.com",
    "Referer": "https://www.kuwaitairways.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}

IATA_EVENT_MAP = {
    "RCS": "Received Cargo from Shipper (Accepted at Origin)",
    "BKD": "Shipment Booked",
    "MAN": "Shipment Manifested on Flight",
    "PRE": "Pre-Manifested on Flight",
    "DEP": "Departed from Airport on Flight",
    "ARR": "Arrived at Airport on Flight",
    "RCF": "Received from Flight (Unloaded to Warehouse)",
    "NFD": "Consignee / Agent Notified of Arrival",
    "DLV": "Delivered to Consignee / Agent",
    "AWD": "Air Waybill Documentation Delivered",
    "DIS": "Discrepancy Reported",
    "TFD": "Transferred to Connecting Carrier",
    "FOH": "Freight on Hand",
    "DRN": "Delivery Receipt Notice",
}
