"""
Air India Cargo Client (iCargo Neo Portal GraphQL Client).
Provides industry-level tracking with automatic anonymous session authentication,
token renewal, AWB sanitization, and comprehensive error handling.
"""

import re
import time
import logging
from typing import List, Dict, Optional, Any
from concurrent.futures import ThreadPoolExecutor
import requests

from .constants import (
    PORTAL_BASE_URL,
    GRAPHQL_ENDPOINT,
    DEFAULT_AIRLINE_PREFIX,
    IATA_EVENT_DESCRIPTIONS,
)
from .models import (
    Milestone,
    FlightSegment,
    ActivityEvent,
    ShipmentOverview,
    TrackingResult,
)
from .exceptions import (
    InvalidAWBFormatException,
    AWBNotFoundException,
    PortalAuthException,
    PortalAPIException,
)

logger = logging.getLogger("airindia_tracker")


class AirIndiaCargoClient:
    """Client for tracking Air India Cargo shipments via iCargo Neo portal."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.id_token: Optional[str] = None
        self.token_expiry: float = 0.0

        self.base_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": PORTAL_BASE_URL,
            "Referer": f"{PORTAL_BASE_URL}/icargoneoportal/app/main/",
        }

    @staticmethod
    def normalize_awb(awb_input: str) -> str:
        """
        Normalize AWB string into clean 11-digit format (e.g. '09830244056').
        Accepts: '098-30244056', '098 30244056', '09830244056', or '30244056'.
        """
        if not awb_input or not isinstance(awb_input, str):
            raise InvalidAWBFormatException("AWB number cannot be empty.")

        cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
        if not cleaned.isdigit():
            raise InvalidAWBFormatException(
                f"Invalid AWB '{awb_input}': contains non-numeric characters."
            )

        if len(cleaned) == 8:
            # Missing airline prefix, default to Air India 098
            cleaned = DEFAULT_AIRLINE_PREFIX + cleaned
        elif len(cleaned) == 11:
            pass
        else:
            raise InvalidAWBFormatException(
                f"Invalid AWB length for '{awb_input}'. Expected 8 or 11 digits."
            )

        return cleaned

    @staticmethod
    def format_awb(awb_clean: str) -> str:
        """Format 11-digit AWB into standard '098-XXXXXXXX' display format."""
        if len(awb_clean) == 11:
            return f"{awb_clean[:3]}-{awb_clean[3:]}"
        return awb_clean

    def _ensure_authenticated(self, force_refresh: bool = False) -> None:
        """Ensure a valid anonymous session token exists."""
        now = time.time()
        if not force_refresh and self.id_token and now < (self.token_expiry - 60):
            return

        login_mutation = """
        mutation loginAsAnonymousUser {
            loginAsAnonymousUser {
                security {
                    id_token
                    exp
                }
                loginProfile {
                    company_code
                    user_id
                }
                errors {
                    error_description
                    error_code
                }
            }
        }
        """

        try:
            resp = self.session.post(
                GRAPHQL_ENDPOINT,
                json={
                    "operationName": "loginAsAnonymousUser",
                    "query": login_mutation,
                    "variables": {},
                },
                headers=self.base_headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            payload = data.get("data", {}).get("loginAsAnonymousUser", {})
            errors = payload.get("errors")
            if errors:
                raise PortalAuthException(f"Anonymous login failed: {errors}")

            security = payload.get("security", {})
            token = security.get("id_token")
            exp = security.get("exp", 3600)

            if not token:
                raise PortalAuthException("No ID token returned by anonymous login.")

            self.id_token = token
            self.token_expiry = now + float(exp)
            logger.debug("Successfully acquired anonymous session token.")

        except requests.RequestException as exc:
            raise PortalAuthException(f"Network error during authentication: {exc}")

    def _execute_query(
        self,
        operation_name: str,
        query: str,
        variables: Dict[str, Any],
        retry_on_unauth: bool = True,
    ) -> Dict[str, Any]:
        """Execute a GraphQL query against the iCargo Neo endpoint."""
        self._ensure_authenticated()

        headers = dict(self.base_headers)
        headers["Authorization"] = f"Bearer {self.id_token}"
        headers["ICO-NEO-PORTAL-Authorization"] = self.id_token

        payload = {
            "operationName": operation_name,
            "query": query,
            "variables": variables,
        }

        try:
            resp = self.session.post(
                GRAPHQL_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            result = resp.json()

            # Check for GraphQL errors
            errors = result.get("errors")
            if errors:
                first_err = errors[0].get("error_code") or errors[0].get("message")
                if "admin.user.notloggedIn" in str(first_err) and retry_on_unauth:
                    logger.info("Session expired, renewing token and retrying...")
                    self._ensure_authenticated(force_refresh=True)
                    return self._execute_query(
                        operation_name, query, variables, retry_on_unauth=False
                    )
                raise PortalAPIException(f"GraphQL error: {errors}")

            return result.get("data", {})

        except requests.RequestException as exc:
            raise PortalAPIException(f"Network error querying iCargo portal: {exc}")

    def get_shipment_overview(self, awb_clean: str) -> ShipmentOverview:
        """Fetch general shipment metadata & milestones."""
        query = """
        fragment ShipmentFragment on TrackingItem {
            awb_number
            pieces
            stated_weight
            stated_volume
            special_handling_code
            product_name
            shipment_description
            origin_airport_code
            destination_airport_code
            milestones {
                milestone
                status
            }
            departure_time
            departure_time_postfix
            arrival_time
            arrival_time_postfix
            transit_stations {
                number_of_flights
                stops
            }
            units_of_measure {
                weight
                volume
            }
        }
        query GetShipmentsByAwbs($shipmentNumbers: [String]!) {
            GetShipmentsByAwbs(shipmentNumbers: $shipmentNumbers) {
                ...ShipmentFragment
            }
        }
        """

        data = self._execute_query(
            "GetShipmentsByAwbs", query, {"shipmentNumbers": [awb_clean]}
        )
        shipments = data.get("GetShipmentsByAwbs") or []
        if not shipments:
            raise AWBNotFoundException(
                f"No tracking data found for AWB {self.format_awb(awb_clean)}. "
                "Please verify the number."
            )

        item = shipments[0]
        milestones = []
        overall_status = "UNKNOWN"

        for m in item.get("milestones", []):
            m_name = m.get("milestone", "")
            m_stat = m.get("status", "")
            is_done = m_stat.lower() == "done"
            milestones.append(
                Milestone(milestone=m_name, status=m_stat, is_completed=is_done)
            )
            if is_done:
                overall_status = m_name

        if overall_status == "UNKNOWN" and milestones:
            overall_status = milestones[0].milestone

        units = item.get("units_of_measure") or {}
        w_unit = "KG" if units.get("weight") == "K" else units.get("weight", "KG")
        v_unit = "CBM" if units.get("volume") == "B" else units.get("volume", "CBM")

        transit = item.get("transit_stations") or {}
        n_flights = transit.get("number_of_flights", 0)

        return ShipmentOverview(
            awb_number=awb_clean,
            formatted_awb=self.format_awb(awb_clean),
            pieces=item.get("pieces") or 0,
            stated_weight=float(item.get("stated_weight") or 0.0),
            weight_unit=w_unit,
            stated_volume=float(item.get("stated_volume") or 0.0),
            volume_unit=v_unit,
            special_handling_code=item.get("special_handling_code"),
            product_name=item.get("product_name"),
            shipment_description=item.get("shipment_description"),
            origin_airport_code=item.get("origin_airport_code") or "",
            destination_airport_code=item.get("destination_airport_code") or "",
            overall_status=overall_status,
            milestones=milestones,
            number_of_flights=n_flights,
        )

    def get_tracking_view(self, awb_clean: str) -> List[FlightSegment]:
        """Fetch flight segments and routing details (Tracking View)."""
        booking_query = """
        query GetBookingDetails($shipmentKey: String!) {
            GetBookingDetails(shipmentKey: $shipmentKey) {
                arrival_date
                arrival_time
                arrival_time_type_postfix
                departure_date
                departure_time
                departure_time_type_postfix
                flight_carrier_code
                flight_number
                pieces
                segment_destination
                segment_origin
            }
        }
        """

        data = self._execute_query(
            "GetBookingDetails", booking_query, {"shipmentKey": awb_clean}
        )
        raw_segments = data.get("GetBookingDetails") or []

        segments = []
        for s in raw_segments:
            segments.append(
                FlightSegment(
                    carrier_code=s.get("flight_carrier_code"),
                    flight_number=s.get("flight_number"),
                    segment_origin=s.get("segment_origin"),
                    segment_destination=s.get("segment_destination"),
                    departure_date=s.get("departure_date"),
                    departure_time=s.get("departure_time"),
                    arrival_date=s.get("arrival_date"),
                    arrival_time=s.get("arrival_time"),
                    pieces=s.get("pieces"),
                )
            )

        return segments

    def get_activity_view(self, awb_clean: str) -> List[ActivityEvent]:
        """Fetch full chronological audit log of cargo activities (Activity View)."""
        activity_query = """
        query GetShipmentActivityByAwb($shipmentNumber: String!) {
            GetShipmentActivityByAwb(shipmentNumber: $shipmentNumber) {
                items {
                    event
                    pieces
                    reason
                    airport_code
                    event_time
                    weight
                    weight_unit
                    from_carrier
                    to_carrier
                    uld_number
                    arrival_time
                    departure_time
                    last_updated_time
                    flight {
                        flight_carrier_code
                        flight_number
                        flight_date
                        origin
                        destination
                    }
                    departure_time_postfix
                    arrival_time_postfix
                }
            }
        }
        """

        data = self._execute_query(
            "GetShipmentActivityByAwb", activity_query, {"shipmentNumber": awb_clean}
        )
        raw_items = data.get("GetShipmentActivityByAwb", {}).get("items") or []

        events = []
        for it in raw_items:
            code = it.get("event") or ""
            name = IATA_EVENT_DESCRIPTIONS.get(code, f"Status: {code}")
            flight_data = it.get("flight") or {}

            events.append(
                ActivityEvent(
                    event_code=code,
                    event_name=name,
                    airport_code=it.get("airport_code"),
                    event_time=it.get("event_time"),
                    pieces=it.get("pieces"),
                    weight=float(it.get("weight")) if it.get("weight") is not None else None,
                    weight_unit=it.get("weight_unit") or "K",
                    uld_number=it.get("uld_number"),
                    flight_carrier_code=flight_data.get("flight_carrier_code"),
                    flight_number=flight_data.get("flight_number"),
                    flight_date=flight_data.get("flight_date"),
                    flight_origin=flight_data.get("origin"),
                    flight_destination=flight_data.get("destination"),
                    last_updated_time=it.get("last_updated_time"),
                )
            )

        return events

    def track(self, awb_input: str) -> TrackingResult:
        """
        Comprehensive tracking function: normalizes AWB, queries overview,
        flight segments (Tracking View), and event audit trail (Activity View).
        """
        awb_clean = self.normalize_awb(awb_input)
        overview = self.get_shipment_overview(awb_clean)
        tracking_view = self.get_tracking_view(awb_clean)
        activity_view = self.get_activity_view(awb_clean)

        return TrackingResult(
            awb_number=awb_clean,
            formatted_awb=self.format_awb(awb_clean),
            overview=overview,
            tracking_view=tracking_view,
            activity_view=activity_view,
        )

    def track_batch(
        self, awb_list: List[str], max_workers: int = 5
    ) -> Dict[str, Any]:
        """Track multiple AWBs concurrently."""
        results: Dict[str, Any] = {}

        def _track_single(raw_awb: str):
            try:
                res = self.track(raw_awb)
                return raw_awb, res, None
            except Exception as e:
                return raw_awb, None, str(e)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_track_single, awb) for awb in awb_list]
            for future in futures:
                awb, res, err = future.result()
                if res:
                    results[awb] = res
                else:
                    results[awb] = {"error": err}

        return results
