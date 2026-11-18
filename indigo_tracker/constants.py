"""
Constants for IndiGo CarGo (IATA prefix 312, IATA code 6E) powered by SmartKargo.
"""

AIRLINE_PREFIX = "312"
AIRLINE_IATA = "6E"
AIRLINE_CODE = "6E"
AIRLINE_NAME = "IndiGo CarGo (6E) (312)"

INDIGO_PORTAL_URL = "https://6ecargo.goindigo.in/FrmAWBTracking.aspx"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://6ecargo.goindigo.in",
    "Referer": "https://6ecargo.goindigo.in/FrmAWBTracking.aspx",
}
