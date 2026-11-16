"""
Constants and event code mappings for Lufthansa Cargo eTracking.
"""

PORTAL_URL = "https://www.lufthansa-cargo.com/en/eservices/etracking"
API_ENDPOINT = "https://api-external.lufthansa-cargo.com/stp/shipments-details"
AIRLINE_PREFIX = "020"
AIRLINE_NAME = "Lufthansa Cargo"

IATA_EVENT_MAP = {
    "RCS": "Received Cargo from Shipper (Accepted at Origin)",
    "BKD": "Shipment Booked",
    "MAN": "Shipment Manifested on Flight",
    "DEP": "Departed from Airport",
    "ARR": "Arrived at Airport",
    "RCF": "Received from Flight (Unloaded & Transferred to Warehouse)",
    "NFD": "Notified for Delivery (Consignee Advised)",
    "DLV": "Delivered to Consignee / Agent",
    "AWD": "Air Waybill Documentation Delivered",
    "DIS": "Discrepancy Reported",
    "PRE": "Shipment Prepared for Flight",
    "TFD": "Transferred to Connecting Carrier",
    "FOH": "Freight on Hand",
    "DRN": "Delivery Receipt Notice",
}
