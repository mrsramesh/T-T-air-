"""
Constants and selectors for Qatar Airways Cargo (IATA Prefix 157).
Powered by Qatar Airways Cargo Experience Cloud Portal.
"""

QATAR_PORTAL_URL = "https://www.qrcargo.com/s/track-your-shipment"

AIRLINE_PREFIX = "157"
AIRLINE_NAME = "Qatar Airways Cargo"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# DOM Selectors on Qatar Airways Cargo Portal
SELECTOR_PREFIX_INPUT = "input[data-id='docprefix']"
SELECTOR_AWB_INPUT = "input[data-id='docawb']"
SELECTOR_TRACK_BTN = "button:has-text('Track Shipment(s)')"
SELECTOR_COOKIE_CONSENT = "input[value='Yes, got it.']"
SELECTOR_NOT_FOUND_MSG = "text=No result found for the given input"
