"""
High-performance direct REST client for Emirates SkyCargo tracking.
Provides sub-second lookups, guest OAuth token caching, and complete tracking details.
"""

import re
import time
import threading
import logging
from typing import Dict, List, Optional, Tuple, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from emirates_tracker.constants import (
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    DEFAULT_HEADERS,
    IATA_EVENT_MAP,
    OAUTH_TOKEN_URL,
    ORDER_DETAILS_URL,
    SEARCH_URL,
)
from emirates_tracker.models import (
    EmiratesAirport,
    EmiratesItineraryLeg,
    EmiratesMilestone,
    EmiratesOrderSummary,
    EmiratesOverview,
    EmiratesTrackingResult,
)

logger = logging.getLogger("emirates_tracker")


class EmiratesTrackingError(Exception):
    """Base exception for Emirates SkyCargo tracking."""
    pass


class EmiratesShipmentNotFoundError(EmiratesTrackingError):
    """Raised when an AWB is not found or has no active records."""
    pass


class EmiratesAuthenticationError(EmiratesTrackingError):
    """Raised when guest authentication token cannot be obtained."""
    pass


class EmiratesTrackerClient:
    """
    Production-grade client for Emirates SkyCargo (IATA prefix 176).
    Uses official guest OAuth token endpoints and REST order query APIs.
    """

    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        self.timeout = timeout
        self._session = session or requests.Session()

        # Configure connection pooling and retries
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(DEFAULT_HEADERS)

        # Token caching state
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._lock = threading.Lock()

    @staticmethod
    def normalize_awb(awb_input: str) -> Tuple[str, str, str, str]:
        """
        Normalize AWB string to (prefix, serial, formatted, full_digits).
        Accepts: '176-63116340', '17663116340', '63116340'.
        """
        raw_digits = re.sub(r"[^\d]", "", str(awb_input or "").strip())
        if not raw_digits:
            raise ValueError(f"Invalid AWB input: '{awb_input}'. Expected numeric digits.")

        if len(raw_digits) == 8:
            prefix = AIRLINE_PREFIX
            serial = raw_digits
        elif len(raw_digits) == 11:
            prefix = raw_digits[:3]
            serial = raw_digits[3:]
        else:
            raise ValueError(
                f"Invalid AWB length ({len(raw_digits)} digits). "
                f"Expected 8 digits or 11 digits starting with {AIRLINE_PREFIX}."
            )

        if prefix != AIRLINE_PREFIX:
            raise ValueError(
                f"Invalid airline prefix '{prefix}' for Emirates SkyCargo. Expected '{AIRLINE_PREFIX}'."
            )

        formatted = f"{prefix}-{serial}"
        full_digits = f"{prefix}{serial}"
        return prefix, serial, formatted, full_digits

    def _get_guest_token(self, force_refresh: bool = False) -> str:
        """
        Retrieve or reuse a cached guest OAuth access token.
        Thread-safe token refresh.
        """
        with self._lock:
            now = time.time()
            if not force_refresh and self._token and now < (self._token_expires_at - 60):
                return self._token

            token_payload = {
                "tenant": "EK",
                "client_id": "mercator",
                "client_secret": "",
            }
            try:
                resp = self._session.post(
                    OAUTH_TOKEN_URL,
                    data=token_payload,
                    timeout=self.timeout,
                )
            except Exception as e:
                raise EmiratesAuthenticationError(f"Network error fetching guest token: {e}") from e

            if resp.status_code != 200:
                raise EmiratesAuthenticationError(
                    f"Failed to obtain guest token (HTTP {resp.status_code}): {resp.text[:200]}"
                )

            token_data = resp.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise EmiratesAuthenticationError("Guest token endpoint did not return access_token.")

            expires_in = token_data.get("expires_in", 3600)
            self._token = access_token
            self._token_expires_at = now + float(expires_in)
            return self._token

    def _get_auth_headers(self) -> Dict[str, str]:
        token = self._get_guest_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def search_orders(self, awb_input: str) -> List[EmiratesOrderSummary]:
        """
        Search Emirates orders for a given AWB.
        Returns list of order summaries.
        """
        _, _, formatted_awb, full_digits = self.normalize_awb(awb_input)
        headers = self._get_auth_headers()

        payload = {
            "orderFilter": {
                "airCapacity": {
                    "documentNumbers": [full_digits],
                    "includeItinerary": False,
                }
            },
            "pageRequest": {"page": 1, "pageSize": 10},
        }

        try:
            resp = self._session.post(
                SEARCH_URL,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            # Handle token expiration (401)
            if resp.status_code == 401:
                headers = {"Authorization": f"Bearer {self._get_guest_token(force_refresh=True)}", "Content-Type": "application/json"}
                resp = self._session.post(SEARCH_URL, json=payload, headers=headers, timeout=self.timeout)

        except Exception as e:
            raise EmiratesTrackingError(f"Failed to query Emirates search endpoint: {e}") from e

        if resp.status_code != 200:
            raise EmiratesTrackingError(f"Search API returned HTTP {resp.status_code}: {resp.text[:300]}")

        data = resp.json().get("data", {})
        raw_orders = data.get("order", [])
        if not raw_orders:
            raise EmiratesShipmentNotFoundError(f"No shipment found for AWB {formatted_awb}")

        summaries: List[EmiratesOrderSummary] = []
        for ord_entry in raw_orders:
            order_items = ord_entry.get("orderItems", {}).get("orderItem", [])
            if not order_items:
                continue
            item = order_items[0]
            ref = item.get("reference", {})
            air = item.get("productInfo", {}).get("airCapacity", {})
            cargo = air.get("cargoInfo", {})
            qty_info = (cargo.get("quantityInfo") or [{}])[0]

            booking_ref = ref.get("bookingReferenceNumber") or ""
            job_ref = ref.get("jobReferenceNumber")
            awb_ref = ref.get("awbReferenceNumber")

            ord_status = ord_entry.get("orderStatus") or {}
            orig_dict = air.get("origin") or {}
            dest_dict = air.get("destination") or {}

            summary = EmiratesOrderSummary(
                booking_reference_number=str(booking_ref),
                job_reference_number=str(job_ref) if job_ref else None,
                awb_reference_number=str(awb_ref) if awb_ref else None,
                order_status_code=ord_status.get("code"),
                order_status_description=ord_status.get("description"),
                origin=EmiratesAirport(
                    code=orig_dict.get("code", "UNK"),
                    name=orig_dict.get("name"),
                ),
                destination=EmiratesAirport(
                    code=dest_dict.get("code", "UNK"),
                    name=dest_dict.get("name"),
                ),
                commodity=cargo.get("commodityCode", {}).get("description") or cargo.get("goodsDescription"),
                pieces=qty_info.get("piece"),
                weight=qty_info.get("weight", {}).get("value"),
                weight_unit=qty_info.get("weight", {}).get("unit", {}).get("code", "K"),
            )
            summaries.append(summary)

        return summaries

    def get_order_details(self, booking_reference: str) -> Dict[str, Any]:
        """
        Fetch full order and milestone details by booking reference number.
        """
        url = ORDER_DETAILS_URL.format(booking_reference=booking_reference)
        headers = self._get_auth_headers()

        try:
            resp = self._session.get(url, headers=headers, timeout=self.timeout)
            if resp.status_code == 401:
                headers = {"Authorization": f"Bearer {self._get_guest_token(force_refresh=True)}"}
                resp = self._session.get(url, headers=headers, timeout=self.timeout)
        except Exception as e:
            raise EmiratesTrackingError(f"Failed to fetch order details for booking {booking_reference}: {e}") from e

        if resp.status_code != 200:
            raise EmiratesTrackingError(
                f"Order details endpoint returned HTTP {resp.status_code}: {resp.text[:300]}"
            )

        return resp.json()

    def track(self, awb_input: str) -> EmiratesTrackingResult:
        """
        Track an Emirates SkyCargo shipment end-to-end.
        Resolves active order, itinerary flights, and full milestone history.
        """
        prefix, serial, formatted_awb, full_digits = self.normalize_awb(awb_input)
        orders = self.search_orders(full_digits)

        if not orders:
            raise EmiratesShipmentNotFoundError(f"Shipment {formatted_awb} not found on Emirates SkyCargo.")

        # Pick primary order: favor non-cancelled order
        primary_order = orders[0]
        for ord_summary in orders:
            if ord_summary.order_status_code != "X":
                primary_order = ord_summary
                break

        details_json = self.get_order_details(primary_order.booking_reference_number)
        order_items = details_json.get("data", {}).get("orderItems", {}).get("orderItem", [])
        if not order_items:
            raise EmiratesTrackingError(f"Empty order item data returned for booking {primary_order.booking_reference_number}")

        item = order_items[0]
        prod_info = item.get("productInfo", {})
        air = prod_info.get("airCapacity", {})
        cargo = air.get("cargoInfo", {})
        qty_info = (cargo.get("quantityInfo") or [{}])[0]

        # Product & Commodity
        product_obj = air.get("product", {}).get("product", {})
        product_name = product_obj.get("name")
        product_desc = product_obj.get("description")
        commodity = cargo.get("commodityCode", {}).get("description") or cargo.get("goodsDescription") or primary_order.commodity

        # Special Handling
        sh_list = qty_info.get("specialHandling", [])
        special_handling_codes = [s.get("code") for s in sh_list if s.get("code")]

        # Quantities
        pieces = qty_info.get("piece") or primary_order.pieces or 0
        weight_val = (qty_info.get("weight") or {}).get("value") or primary_order.weight or 0.0
        weight_unit = (qty_info.get("weight") or {}).get("unit", {}).get("code") or primary_order.weight_unit or "K"
        chargeable_weight = (qty_info.get("chargeableWeight") or {}).get("value")
        volume_val = (qty_info.get("volume") or {}).get("value") or 0.0
        volume_unit = (qty_info.get("volume") or {}).get("unit", {}).get("code") or "CM"

        # Origin / Destination
        orig_dict = air.get("origin") or {}
        dest_dict = air.get("destination") or {}
        origin = EmiratesAirport(code=orig_dict.get("code", primary_order.origin.code), name=orig_dict.get("name"))
        destination = EmiratesAirport(code=dest_dict.get("code", primary_order.destination.code), name=dest_dict.get("name"))

        # Itinerary
        raw_itinerary = air.get("offerItinerary", {}).get("itinerary", [])
        itinerary_legs: List[EmiratesItineraryLeg] = []
        for leg in raw_itinerary:
            board = leg.get("boardPoint", {})
            off = leg.get("offPoint", {})
            transport = leg.get("transportInfo", {})
            carrier = transport.get("carrier") or "EK"
            flight_num = str(transport.get("number") or "")
            vehicle = transport.get("vehicle", {})

            dep_dt = leg.get("departureDateTimeLocal", {})
            arr_dt = leg.get("arrivalDateTimeLocal", {})
            qty = leg.get("quantity", {})

            leg_model = EmiratesItineraryLeg(
                origin=EmiratesAirport(code=board.get("code", "UNK"), name=board.get("description")),
                destination=EmiratesAirport(code=off.get("code", "UNK"), name=off.get("description")),
                carrier_code=carrier,
                flight_number=flight_num,
                flight_display=f"{carrier} {flight_num}".strip(),
                flight_date=transport.get("date"),
                aircraft_type=vehicle.get("type", {}).get("code"),
                registration_number=vehicle.get("registrationNumber"),
                scheduled_departure=dep_dt.get("schedule"),
                actual_departure=dep_dt.get("actual") or dep_dt.get("estimated"),
                scheduled_arrival=arr_dt.get("schedule"),
                actual_arrival=arr_dt.get("actual") or arr_dt.get("estimated"),
                movement_status=leg.get("movementStatus", {}).get("code"),
                pieces=qty.get("piece"),
                weight=qty.get("weight", {}).get("value") if isinstance(qty.get("weight"), dict) else None,
                weight_unit=qty.get("weight", {}).get("unit", {}).get("code", "K") if isinstance(qty.get("weight"), dict) else "K",
                volume=qty.get("volume", {}).get("value") if isinstance(qty.get("volume"), dict) else None,
                volume_unit=qty.get("volume", {}).get("unit", {}).get("code", "CM") if isinstance(qty.get("volume"), dict) else "CM",
            )
            itinerary_legs.append(leg_model)

        # Milestones
        raw_milestones = item.get("fulfillmentInfo", {}).get("serviceInfo", {}).get("milestone", [])
        milestones: List[EmiratesMilestone] = []
        latest_milestone: Optional[EmiratesMilestone] = None

        for m in raw_milestones:
            code_field = m.get("code") or {}
            m_code = code_field.get("code") if isinstance(code_field, dict) else str(code_field or "")
            m_desc = (
                code_field.get("description")
                if isinstance(code_field, dict)
                else (m.get("description") or IATA_EVENT_MAP.get(m_code, m_code))
            )
            station_field = m.get("station") or {}
            st_code = station_field.get("code") if isinstance(station_field, dict) else str(station_field or "")

            status_date = m.get("statusDate") or {}
            ts = status_date.get("achieved") if isinstance(status_date, dict) else str(status_date or "")
            ts_utc = status_date.get("achievedUTC") if isinstance(status_date, dict) else None
            is_latest = bool(m.get("latestMilestone", False))
            import_msg = m.get("importStatusMessage")

            st_data = m.get("statusData") or {}
            st_qty = st_data.get("quantity") or {}
            m_piece = st_qty.get("piece")
            w_dict = st_qty.get("weight") or {}
            m_weight = w_dict.get("value") if isinstance(w_dict, dict) else None
            m_w_unit = w_dict.get("unit", {}).get("code", "K") if isinstance(w_dict, dict) else "K"

            ms_model = EmiratesMilestone(
                code=m_code,
                description=m_desc or IATA_EVENT_MAP.get(m_code, m_code),
                station=st_code or None,
                timestamp=ts or None,
                timestamp_utc=ts_utc,
                is_latest=is_latest,
                import_status_message=import_msg,
                pieces=m_piece,
                weight=m_weight,
                weight_unit=m_w_unit,
            )
            milestones.append(ms_model)
            if is_latest and not latest_milestone:
                latest_milestone = ms_model

        if not latest_milestone and milestones:
            latest_milestone = milestones[0]

        # References
        ref = item.get("reference", {})
        job_ref = ref.get("jobReferenceNumber") or primary_order.job_reference_number

        # Status text
        order_status_text = (
            primary_order.order_status_description
            or (f"Status: {latest_milestone.code} - {latest_milestone.description}" if latest_milestone else "Confirmed")
        )

        overview = EmiratesOverview(
            awb_number=serial,
            formatted_awb=formatted_awb,
            booking_reference_number=primary_order.booking_reference_number,
            job_reference_number=job_ref,
            order_status=order_status_text,
            origin=origin,
            destination=destination,
            latest_milestone_code=latest_milestone.code if latest_milestone else "N/A",
            latest_milestone_description=latest_milestone.description if latest_milestone else "No milestone data",
            latest_milestone_station=latest_milestone.station if latest_milestone else None,
            latest_milestone_time=latest_milestone.timestamp if latest_milestone else None,
            commodity=commodity,
            product_name=product_name,
            product_description=product_desc,
            special_handling_codes=special_handling_codes,
            pieces=pieces,
            gross_weight=weight_val,
            chargeable_weight=chargeable_weight,
            weight_unit=weight_unit,
            volume=volume_val,
            volume_unit=volume_unit,
        )

        return EmiratesTrackingResult(
            awb_number=serial,
            formatted_awb=formatted_awb,
            airline=f"{AIRLINE_NAME} ({AIRLINE_PREFIX})",
            overview=overview,
            itinerary=itinerary_legs,
            milestones=milestones,
            all_orders=orders,
        )
