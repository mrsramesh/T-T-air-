"""
Constants and configuration for Turkish Cargo (IATA Prefix 235 - TK).
"""

import os

AIRLINE_NAME = "Turkish Cargo (TK)"
AIRLINE_PREFIX = "235"
AIRLINE_CODE = "TK"

TURKISH_CARGO_BASE_URL = "https://www.turkishcargo.com"
TURKISH_CARGO_TRACKING_URL = "https://www.turkishcargo.com/en/cargo-tracking"
TURKISH_CARGO_DIRECT_URL = "https://www.turkishcargo.com/en/cargo-tracking?awbPrefix={prefix}&awbNumber={serial}"
PARCELSAPP_DIRECT_URL = "https://parcelsapp.com/en/tracking/{prefix}-{serial}"
TRACK_TRACE_CARGO_URL = "https://www.track-trace.com/aircargo"

# Enterprise Proxy Configuration (Supports HTTP, HTTPS, SOCKS5, and Rotating Residential Proxies)
DEFAULT_PROXY = os.environ.get("TURKISH_CARGO_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.track-trace.com/aircargo",
}

STEALTH_SCRIPT = """
(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    
    // Mask WebGL vendor and renderer to look like genuine hardware
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
})();
"""
