"""
Constants and event code mappings for Air India Cargo (iCargo Neo Portal).
"""

PORTAL_BASE_URL = "https://aicargoportal.airindia.com"
GRAPHQL_ENDPOINT = f"{PORTAL_BASE_URL}/portalgateway/graphql"
DEFAULT_COMPANY_CODE = "AI"
DEFAULT_AIRLINE_PREFIX = "098"

# Standard IATA Cargo Event Codes & Human-readable descriptions
IATA_EVENT_DESCRIPTIONS = {
    "RCS": "Received Cargo from Shipper (Accepted at Origin)",
    "BKD": "Shipment Booked",
    "MAN": "Shipment Manifested on Flight",
    "DEP": "Departed from Origin/Transit Station",
    "ARR": "Arrived at Station",
    "RCF": "Received from Flight (Unloaded & Transferred to Warehouse)",
    "NFD": "Notified for Delivery (Consignee Advised)",
    "DLV": "Delivered to Consignee / Authorized Agent",
    "DIS": "Discrepancy Reported",
    "PRE": "Shipment Prepared",
    "TFD": "Transferred to Connecting Carrier",
    "FOH": "Freight on Hand (Received without full documentation)",
    "DRN": "Delivery Receipt Notice",
    "RCT": "Received from Transfer Carrier",
    "EXE": "Air Waybill Executed",
    "FIW": "Freight in Warehouse",
    "FOW": "Freight out of Warehouse",
}

# Milestone badge colors & status representations
MILESTONE_STATUS_MAP = {
    "done": "Completed",
    "in progress": "In Progress",
    "pending": "Pending",
}
