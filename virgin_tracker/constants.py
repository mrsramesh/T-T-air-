"""
Constants and selectors for Virgin Atlantic Cargo (IATA Prefix 932).
Powered by Accelya Offer & Order Platform.
"""

VIRGIN_PORTAL_URL = "https://myvs.virginatlanticcargo.com/app/offerandorder/#/shipments/list"
VIRGIN_DIRECT_DETAIL_URL = "https://myvs.virginatlanticcargo.com/app/offerandorder/#/shipments/list/{booking_ref}?openedTab=tracking-details"

AIRLINE_PREFIX = "932"
AIRLINE_NAME = "Virgin Atlantic Cargo"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# DOM Selectors on Accelya Portal
SELECTOR_DOC_INPUT = "input[placeholder*='Doc. No.']"
SELECTOR_SEARCH_BTN = "button:has-text('Search')"
SELECTOR_TRACKING_DETAILS_BTN = "button:has-text('Tracking Details')"
SELECTOR_RESULTS_HEADER = ".search-results, :text('Search Results')"
SELECTOR_NO_RECORDS = ":text('No matching records found'), :text('Search Results (0)')"
SELECTOR_INCORRECT_FORMAT = ":text('The Doc. No. entered is in an incorrect format')"
