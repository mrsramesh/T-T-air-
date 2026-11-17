"""
High-performance direct REST client for Kuwait Airways Cargo (IATA prefix 229).
Provides failure-proof, bot-detection proof tracking with retry resilience.
"""

import re
import html
import logging
from typing import Dict, List, Optional, Tuple, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from kuwait_tracker.constants import (
    API_ENDPOINT,
    AIRLINE_NAME,
    AIRLINE_PREFIX,
    DEFAULT_HEADERS,
    IATA_EVENT_MAP,
)
from kuwait_tracker.models import (
    KuwaitFlightLeg,
    KuwaitOperationalEvent,
    KuwaitOverview,
    KuwaitStationBox,
    KuwaitTrackingResult,
)

logger = logging.getLogger("kuwait_tracker")


class KuwaitTrackingError(Exception):
    """Base exception for Kuwait Airways Cargo tracking."""
    pass


class KuwaitShipmentNotFoundError(KuwaitTrackingError):
    """Raised when an AWB is not found on Kuwait Airways."""
    pass


class KuwaitCargoClient:
    """
    Production-grade client for Kuwait Airways Cargo (IATA prefix 229).
    Uses the official cargo services REST API with zero-overhead sub-second lookups.
    """

    def __init__(
        self,
        timeout: int = 15,
        max_retries: int = 3,
        session: Optional[requests.Session] = None,
    ):
        self.timeout = timeout
        self._session = session or requests.Session()

        # Resilient connection pooling and exponential backoff
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self._session.headers.update(DEFAULT_HEADERS)

    @staticmethod
    def normalize_awb(awb_input: str) -> Tuple[str, str, str, str]:
        """
        Normalize AWB string to (prefix, serial, formatted, full_digits).
        Accepts: '229-18148900', '229 18148900', '22918148900', or plain '18148900'.
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
                f"Invalid AWB length ({len(raw_digits)} digits) for '{awb_input}'. "
                f"Expected 8 digits serial or 11 digits with prefix {AIRLINE_PREFIX}."
            )

        if prefix != AIRLINE_PREFIX:
            raise ValueError(
                f"Invalid airline prefix '{prefix}' for Kuwait Airways Cargo. Expected '{AIRLINE_PREFIX}'."
            )

        formatted = f"{prefix}-{serial}"
        full_digits = f"{prefix}{serial}"
        return prefix, serial, formatted, full_digits

    @staticmethod
    def format_awb(prefix: str, serial: str) -> str:
        return f"{prefix}-{serial}"

    @staticmethod
    def _clean_text(val: Optional[str]) -> str:
        if not val:
            return ""
        # Remove non-breaking spaces and excessive whitespace
        cleaned = re.sub(r"[\xa0\s]+", " ", str(val)).strip()
        # Strip HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = html.unescape(cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def track(self, awb_input: str, lang: str = "en") -> KuwaitTrackingResult:
        """
        Track a Kuwait Airways Cargo shipment end-to-end.
        """
        prefix, serial, formatted_awb, _ = self.normalize_awb(awb_input)
        url = f"{API_ENDPOINT}/{prefix}/{serial}/{lang}"

        logger.info(f"Querying Kuwait Airways Cargo API: {url}")

        try:
            resp = self._session.get(url, timeout=self.timeout)
        except Exception as e:
            raise KuwaitTrackingError(f"Network error querying Kuwait Airways API: {e}") from e

        if resp.status_code != 200:
            raise KuwaitTrackingError(
                f"Kuwait Airways API returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            data = resp.json()
        except Exception as e:
            raise KuwaitTrackingError(f"Failed to parse JSON response from Kuwait Airways: {e}") from e

        response_code = str(data.get("responseCode") or "")
        response_text = self._clean_text(data.get("responseText"))

        # Error or Not Found check
        if response_code == "-1" or not data.get("awbNo"):
            err_msg = response_text or f"Could not find AWB {formatted_awb}. Please check your request and try again."
            raise KuwaitShipmentNotFoundError(err_msg)

        # Overview
        origin = str(data.get("origin") or "UNK")
        destination = str(data.get("destination") or "UNK")
        try:
            pieces = int(float(data.get("pieces") or 0))
        except (ValueError, TypeError):
            pieces = 0

        try:
            weight = float(data.get("weight") or 0.0)
        except (ValueError, TypeError):
            weight = 0.0

        try:
            volume = float(data.get("volume") or 0.0)
        except (ValueError, TypeError):
            volume = 0.0

        current_status = self._clean_text(data.get("currentStatus"))

        # Routing legs
        flights: List[KuwaitFlightLeg] = []
        raw_routing = data.get("routing") or []
        for r in raw_routing:
            flight_num = self._clean_text(r.get("flightNum"))
            flight_date = self._clean_text(r.get("flightDate"))
            f_orig = self._clean_text(r.get("flightOrigin")) or origin
            f_dest = self._clean_text(r.get("flightDest")) or destination
            f_status = self._clean_text(r.get("status"))
            f_msg = self._clean_text(r.get("statusMessage")) or IATA_EVENT_MAP.get(f_status, f_status)

            try:
                f_pcs = int(float(r.get("pieces") or pieces))
            except (ValueError, TypeError):
                f_pcs = None

            try:
                f_wt = float(r.get("weight") or weight)
            except (ValueError, TypeError):
                f_wt = None

            try:
                f_vol = float(r.get("volume") or volume)
            except (ValueError, TypeError):
                f_vol = None

            flights.append(
                KuwaitFlightLeg(
                    flight_number=flight_num,
                    flight_date=flight_date or None,
                    origin=f_orig,
                    destination=f_dest,
                    pieces=f_pcs,
                    weight=f_wt,
                    volume=f_vol,
                    status_code=f_status or None,
                    status_message=f_msg or None,
                    sequence_no=r.get("sequenceNo"),
                )
            )

        # Station summary boxes
        station_boxes: List[KuwaitStationBox] = []
        raw_boxes = data.get("routingBox") or []
        for b in raw_boxes:
            airport = self._clean_text(b.get("flightAirPort"))
            sc1 = self._clean_text(b.get("statusCode1"))
            sc2 = self._clean_text(b.get("statusCode2"))
            et1 = f"{self._clean_text(b.get('eventDate1'))} {self._clean_text(b.get('eventTime1'))}".strip()
            et2 = f"{self._clean_text(b.get('eventDate2'))} {self._clean_text(b.get('eventTime2'))}".strip()
            sm1 = self._clean_text(b.get("statusMessage1"))
            sm2 = self._clean_text(b.get("statusMessage2"))

            try:
                b_pcs = int(float(b.get("pieces") or pieces))
            except (ValueError, TypeError):
                b_pcs = None

            try:
                b_wt = float(b.get("weight") or weight)
            except (ValueError, TypeError):
                b_wt = None

            station_boxes.append(
                KuwaitStationBox(
                    airport=airport,
                    pieces=b_pcs,
                    weight=b_wt,
                    status_code_1=sc1 or None,
                    status_code_2=sc2 or None,
                    event_time_1=et1 or None,
                    event_time_2=et2 or None,
                    status_message_1=sm1 or None,
                    status_message_2=sm2 or None,
                    box_index=b.get("cBoxNo"),
                )
            )

        # Operational status events / segments
        operational_events: List[KuwaitOperationalEvent] = []
        raw_segments = data.get("segments") or []
        for s in raw_segments:
            code = self._clean_text(s.get("statusCode"))
            name = self._clean_text(s.get("status")) or IATA_EVENT_MAP.get(code, code)
            msg = self._clean_text(s.get("statusMessage"))
            airport = self._clean_text(s.get("flightAirPort"))
            fl_num = self._clean_text(s.get("flightNum"))
            fl_date = self._clean_text(s.get("flightDate"))
            ev_date = self._clean_text(s.get("eventDate"))
            ev_time = self._clean_text(s.get("eventTime"))
            full_details = self._clean_text(s.get("statusFullDetails"))

            try:
                s_pcs = int(float(s.get("numPieces") or pieces))
            except (ValueError, TypeError):
                s_pcs = None

            try:
                s_wt = float(s.get("weight") or weight)
            except (ValueError, TypeError):
                s_wt = None

            try:
                s_vol = float(s.get("volume") or volume)
            except (ValueError, TypeError):
                s_vol = None

            operational_events.append(
                KuwaitOperationalEvent(
                    status_code=code,
                    status_name=name,
                    status_message=msg or None,
                    airport=airport or None,
                    flight_number=fl_num or None,
                    flight_date=fl_date or None,
                    event_date=ev_date or None,
                    event_time=ev_time or None,
                    pieces=s_pcs,
                    weight=s_wt,
                    volume=s_vol,
                    full_details=full_details or None,
                    sequence_no=s.get("sequenceNo"),
                )
            )

        # Determine latest event
        latest_code = None
        latest_airport = None
        latest_time = None
        if operational_events:
            first_ev = operational_events[0]
            latest_code = first_ev.status_code
            latest_airport = first_ev.airport
            latest_time = f"{first_ev.event_date or ''} {first_ev.event_time or ''}".strip() or None

        overview = KuwaitOverview(
            awb_number=serial,
            formatted_awb=formatted_awb,
            origin=origin,
            destination=destination,
            pieces=pieces,
            gross_weight=weight,
            weight_unit="KGS",
            volume=volume,
            volume_unit="CBM",
            current_status=current_status,
            latest_event_code=latest_code,
            latest_event_airport=latest_airport,
            latest_event_time=latest_time,
        )

        return KuwaitTrackingResult(
            awb_number=serial,
            formatted_awb=formatted_awb,
            airline=f"{AIRLINE_NAME} ({AIRLINE_PREFIX})",
            overview=overview,
            flights=flights,
            station_boxes=station_boxes,
            operational_events=operational_events,
        )
