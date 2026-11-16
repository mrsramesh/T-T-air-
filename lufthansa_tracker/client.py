"""
Lufthansa Cargo Production Client.
Fast, reliable direct REST API client for Lufthansa Cargo eTracking data.
"""

import re
import logging
from typing import Dict, Any, List, Optional
import requests

from .constants import API_ENDPOINT, AIRLINE_PREFIX, IATA_EVENT_MAP
from .models import (
    LufthansaAirport,
    LufthansaFlight,
    LufthansaStatusEvent,
    LufthansaBookingSegment,
    LufthansaOverview,
    LufthansaTrackingResult,
)

logger = logging.getLogger("lufthansa_tracker")


class LufthansaCargoClient:
    """Client for tracking Lufthansa Cargo shipments."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.lufthansa-cargo.com",
            "Referer": "https://www.lufthansa-cargo.com/en/eservices/etracking",
        })

    @staticmethod
    def normalize_awb(awb_input: str) -> tuple[str, str]:
        """
        Normalize AWB input into (airline_prefix, 8_digit_serial).
        Accepts: '020-04585280', '020 04585280', '02004585280', or '04585280'.
        Returns: ('020', '04585280') and standard formatted '020-04585280'.
        """
        if not awb_input or not isinstance(awb_input, str):
            raise ValueError("AWB number cannot be empty.")

        cleaned = re.sub(r"[\s\-_]+", "", awb_input.strip())
        if not cleaned.isdigit():
            raise ValueError(f"Invalid AWB '{awb_input}': contains non-numeric characters.")

        if len(cleaned) == 8:
            prefix = AIRLINE_PREFIX
            serial = cleaned
        elif len(cleaned) == 11:
            prefix = cleaned[:3]
            serial = cleaned[3:]
        else:
            raise ValueError(
                f"Invalid AWB length for '{awb_input}'. Expected 8 or 11 digits."
            )

        return prefix, serial

    @staticmethod
    def format_awb(prefix: str, serial: str) -> str:
        """Format into standard display format e.g. '020-04585280'."""
        return f"{prefix}-{serial}"

    def track(self, awb_input: str) -> LufthansaTrackingResult:
        """Track a Lufthansa Cargo shipment by AWB number."""
        prefix, serial = self.normalize_awb(awb_input)
        full_awb = f"{prefix}{serial}"
        formatted = self.format_awb(prefix, serial)

        url = f"{API_ENDPOINT}/{full_awb}"

        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 404:
                raise ValueError(f"No shipment found for AWB {formatted}.")
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"Network error communicating with Lufthansa Cargo API: {e}")

        # Parse Overview
        awb_details = data.get("awbDetails") or {}
        orig = awb_details.get("originAirport") or {}
        dest = awb_details.get("destinationAirport") or {}
        pcs_info = awb_details.get("piecesInformation") or {}
        product_info = awb_details.get("product") or {}
        latest_event = awb_details.get("latestEvent") or "UNKNOWN"

        # Last event message descriptor
        last_desc = awb_details.get("lastEventMessageDescriptor") or {}
        last_flight = last_desc.get("flight") or {}
        desig = last_flight.get("flightDesignator") or {}
        flight_str = f"{desig.get('carrierCode', '')}{desig.get('flightNumber', '')}"
        fl_date = last_flight.get("flightDate", "")
        fl_orig = (last_flight.get("originAirport") or {}).get("airportCode", "")
        fl_dest = (last_flight.get("destinationAirport") or {}).get("airportCode", "")

        event_desc = IATA_EVENT_MAP.get(latest_event, f"Latest status: {latest_event}")
        if flight_str and fl_orig and fl_dest:
            event_desc = f"{latest_event} - Shipment processed on flight {flight_str} ({fl_orig} - {fl_dest})"

        overview = LufthansaOverview(
            awb_number=full_awb,
            formatted_awb=formatted,
            origin=LufthansaAirport(code=orig.get("airportCode", ""), name=orig.get("airportName", "")),
            destination=LufthansaAirport(code=dest.get("airportCode", ""), name=dest.get("airportName", "")),
            latest_event=latest_event,
            latest_event_description=event_desc,
            pieces=int(pcs_info.get("piecesCount") or 0),
            gross_weight=float(pcs_info.get("piecesWeight") or 0.0),
            weight_unit="KG",
            volume=float(pcs_info.get("piecesVolume") or 0.0),
            volume_unit="CBM",
            product_name=product_info.get("productName"),
            product_code=product_info.get("productCode"),
            special_cargo_codes=product_info.get("specialCargoCodes") or [],
            latest_acceptance_time=awb_details.get("latestAcceptanceTime"),
            planned_availability_time=awb_details.get("plannedTimeOfAvailability"),
            actual_availability_time=awb_details.get("actualTimeOfAvailability"),
        )

        # Parse Flight Information
        flights = []
        for fl in data.get("flightInformation") or []:
            fl_orig_data = fl.get("originAirport") or {}
            fl_dest_data = fl.get("destinationAirport") or {}
            flights.append(
                LufthansaFlight(
                    flight_number=fl.get("flightNumber") or "",
                    flight_date=fl.get("flightDate"),
                    origin=LufthansaAirport(code=fl_orig_data.get("airportCode", ""), name=fl_orig_data.get("airportName")),
                    destination=LufthansaAirport(code=fl_dest_data.get("airportCode", ""), name=fl_dest_data.get("airportName")),
                    scheduled_departure=fl.get("scheduledDepartureTime"),
                    actual_departure=fl.get("actualDepartureTime"),
                    scheduled_arrival=fl.get("scheduledArrivalTime"),
                    actual_arrival=fl.get("actualArrivalTime"),
                    aircraft_type=fl.get("aircraftType"),
                )
            )

        # Parse Status History (statusHistories)
        status_events = []
        for sh_item in data.get("statusHistories") or []:
            code = sh_item.get("cargoEventType") or ""
            station_info = sh_item.get("stationAirport") or {}
            station_code = station_info.get("airportCode", "")

            # Check actual vs planned
            actual = sh_item.get("actualCargoEvent") or {}
            planned = sh_item.get("planedCargoEvent") or {}

            is_actual = bool(actual.get("eventDateTime"))
            ev_time = actual.get("eventDateTime") or planned.get("eventDateTime")

            p_info = actual.get("pieceInformation") if is_actual else planned.get("pieceInformation")
            p_info = p_info or {}

            fl_obj = sh_item.get("flight") or {}
            fl_desig = fl_obj.get("flightDesignator") or {}
            fl_code = f"{fl_desig.get('carrierCode', '')}{fl_desig.get('flightNumber', '')}" if fl_desig else None

            status_events.append(
                LufthansaStatusEvent(
                    event_code=code,
                    event_name=IATA_EVENT_MAP.get(code, f"Status: {code}"),
                    station=station_code,
                    event_time=ev_time,
                    is_actual=is_actual,
                    pieces=p_info.get("piecesCount"),
                    weight=p_info.get("piecesWeight"),
                    flight_number=fl_code,
                    discrepancy_code=actual.get("discrepancyCode"),
                )
            )

        # Parse Booking Segments
        booking_segments = []
        last_booking = (data.get("bookingDetailsInformation") or {}).get("lastBookingDetails") or {}
        for b_seg in last_booking.get("bookingSegments") or []:
            fl_obj = b_seg.get("flight") or {}
            desig = fl_obj.get("flightDesignator") or {}
            fl_str = f"{desig.get('carrierCode', '')}{desig.get('flightNumber', '')}"
            b_orig = (fl_obj.get("originAirport") or {}).get("airportCode", "")
            b_dest = (fl_obj.get("destinationAirport") or {}).get("airportCode", "")
            b_pcs = b_seg.get("piecesInformation") or {}

            booking_segments.append(
                LufthansaBookingSegment(
                    flight_number=fl_str,
                    origin=b_orig,
                    destination=b_dest,
                    flight_date=fl_obj.get("flightDate"),
                    booking_status=b_seg.get("bookingStatus"),
                    pieces=b_pcs.get("piecesCount"),
                    weight=b_pcs.get("piecesWeight"),
                    volume=b_pcs.get("piecesVolume"),
                )
            )

        return LufthansaTrackingResult(
            awb_number=full_awb,
            formatted_awb=formatted,
            overview=overview,
            flights=flights,
            status_history=status_events,
            booking_segments=booking_segments,
        )
