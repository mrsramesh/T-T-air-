"""
Constants and event code mappings for ParcelsApp & British Airways Cargo (IATA prefix 125).
"""

PARCELSAPP_URL = "https://parcelsapp.com/en/tracking"
PARCELSAPP_DIRECT_URL = "https://parcelsapp.com/en/tracking/{tracking_number}"

AIRLINE_PREFIX = "125"
AIRLINE_NAME = "British Airways Cargo / IAG Cargo"

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// Mask WebGL vendor and renderer to look like a genuine desktop device
const getParam1 = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel(R) Iris(TM) Plus Graphics 655';
    return getParam1.apply(this, arguments);
};

const getParam2 = WebGL2RenderingContext.prototype.getParameter;
WebGL2RenderingContext.prototype.getParameter = function(p) {
    if (p === 37445) return 'Intel Inc.';
    if (p === 37446) return 'Intel(R) Iris(TM) Plus Graphics 655';
    return getParam2.apply(this, arguments);
};
"""

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://parcelsapp.com",
    "Referer": "https://parcelsapp.com/en/tracking",
}
