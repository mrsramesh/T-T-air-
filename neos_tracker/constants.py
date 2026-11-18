"""
Constants for Neos Air Cargo (IATA code NO, prefix 703) and World Cargo Solutions (WCS Group).
"""

AIRLINE_PREFIX = "703"
AIRLINE_IATA = "NO"
AIRLINE_NAME = "Neos Air Cargo (NO) / World Cargo Solutions (703)"

# World Cargo Solutions Tracking Portal (Embedded by track-trace.com/aircargo)
WCS_PORTAL_URL = "https://world-cs.com/en"
WCS_AJAX_HANDLER = "onTracking"

# Track-trace fallback URL
TRACK_TRACE_URL = "https://www.track-trace.com/aircargo"

# ParcelsApp Tracking URL
PARCELSAPP_URL = "https://parcelsapp.com/en/tracking"
PARCELSAPP_DIRECT_URL = "https://parcelsapp.com/en/tracking/{tracking_number}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://world-cs.com",
    "Referer": "https://world-cs.com/en",
}

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
const getParam1 = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel(R) Iris(TM) Plus Graphics 655';
    return getParam1.apply(this, arguments);
};
"""
