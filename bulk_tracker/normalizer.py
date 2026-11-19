"""
Carrier Data Normalizer.
Transforms raw carrier-specific tracking outputs into a consistent UnifiedTrackingRecord.
"""

import re
from typing import Any, Dict, Optional
from bulk_tracker.models import UnifiedTrackingRecord


class CarrierDataNormalizer:
    """
    Normalizes carrier result objects across all 10 supported airlines into UnifiedTrackingRecord.
    """

    @staticmethod
    def _classify_status(text: str) -> str:
        """
        Classifies status string into standard status categories:
        DELIVERED, IN_TRANSIT, ARRIVED, DEPARTED, BOOKED, ACCEPTED, NOT_FOUND, ERROR.
        """
        s = str(text or "").strip().lower()
        if any(w in s for w in ("delivered", "dlv", "pod", "release", "released")):
            return "DELIVERED"
        if any(w in s for w in ("arrived", "arr", "rcf")):
            return "ARRIVED"
        if any(w in s for w in ("departed", "dep", "flying", "in flight")):
            return "DEPARTED"
        if any(w in s for w in ("transit", "transit-in", "manifested", "man", "received on flight")):
            return "IN_TRANSIT"
        if any(w in s for w in ("accepted", "rcs")):
            return "ACCEPTED"
        if any(w in s for w in ("booked", "bkd", "exe", "confirmed", "bk")):
            return "BOOKED"
        if any(w in s for w in ("not found", "details not available", "no result", "does not exist")):
            return "NOT_FOUND"
        return "IN_TRANSIT" if s else "UNKNOWN"

    @classmethod
    def normalize_indigo(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.current_status)
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="312",
            carrier_name="IndiGo CarGo (6E)",
            carrier_code="6E",
            status=status_category,
            status_detail=ov.current_status,
            origin=ov.origin,
            destination=ov.destination,
            route=f"{ov.origin} ➔ {ov.destination}",
            pieces=ov.pieces,
            weight=ov.gross_weight,
            flight_details=ov.flight_no,
            latest_activity=ov.latest_activity,
            latest_location=ov.destination if status_category == "DELIVERED" else ov.origin,
            consignee_issued_to=ov.issued_to,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_neos(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.current_status)
        fl_str = ", ".join(f.flight_no for f in res.flights if getattr(f, "flight_no", None)) if res.flights else None
        lat_act = res.milestones[0].description if res.milestones else ov.current_status
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="703",
            carrier_name="Neos Air Cargo (NO) / WCS",
            carrier_code="NO",
            status=status_category,
            status_detail=ov.current_status,
            origin=ov.origin,
            destination=ov.destination,
            route=f"{ov.origin} ➔ {ov.destination}",
            pieces=ov.pieces,
            weight=ov.gross_weight,
            flight_details=fl_str,
            latest_activity=lat_act,
            latest_location=ov.destination if status_category == "DELIVERED" else ov.origin,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_cargoflash(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.latest_event_action)
        # Deduplicate flight numbers so repeated milestone legs don't create duplicate entries
        unique_flights = []
        if res.flight_details:
            seen_f = set()
            for f in res.flight_details:
                f_no = getattr(f, "flight_no", None)
                if f_no:
                    f_clean = f_no.strip()
                    if f_clean not in seen_f:
                        seen_f.add(f_clean)
                        unique_flights.append(f_clean)
        fl_str = ", ".join(unique_flights) if unique_flights else None
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="077",
            carrier_name="EgyptAir Cargo (MS)",
            carrier_code="MS",
            status=status_category,
            status_detail=ov.latest_event_message,
            origin=ov.origin,
            destination=ov.destination,
            route=f"{ov.origin} ➔ {ov.destination}",
            pieces=ov.pieces,
            weight=f"{ov.gross_weight} {ov.weight_unit}",
            volume=f"{ov.cbm} CBM" if (ov.cbm and ov.cbm > 0) else None,
            flight_details=fl_str,
            latest_activity=ov.latest_event_message,
            latest_location=ov.destination if status_category in ("DELIVERED", "ARRIVED") else ov.origin,
            consignee_issued_to=ov.agent_name,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_qatar(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.overall_status)
        fl_str = ", ".join(f"{f.flight_number} ({f.origin}->{f.destination})" for f in res.flights if getattr(f, "flight_number", None)) if res.flights else None
        lat_act = res.milestones[0].details if res.milestones else (ov.latest_status_message or ov.overall_status)
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="157",
            carrier_name="Qatar Airways Cargo (QR)",
            carrier_code="QR",
            status=status_category,
            status_detail=ov.overall_status,
            origin=ov.origin,
            destination=ov.destination,
            route=f"{ov.origin} ➔ {ov.destination}",
            pieces=ov.pieces,
            weight=f"{ov.weight} {ov.weight_unit}",
            volume=f"{ov.volume} {ov.volume_unit}" if ov.volume else None,
            flight_details=fl_str,
            latest_activity=lat_act,
            latest_location=ov.destination if status_category == "DELIVERED" else ov.origin,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_virgin(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.order_status)
        orig_code = ov.origin.code if hasattr(ov.origin, "code") else str(ov.origin)
        dest_code = ov.destination.code if hasattr(ov.destination, "code") else str(ov.destination)
        fl_str = ", ".join(dict.fromkeys(f.flight_number.strip() for f in res.flights if getattr(f, "flight_number", None))) if res.flights else None
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="932",
            carrier_name="Virgin Atlantic Cargo (VS)",
            carrier_code="VS",
            status=status_category,
            status_detail=f"{ov.order_status} ({ov.shipment_status})",
            origin=orig_code,
            destination=dest_code,
            route=f"{orig_code} ➔ {dest_code}",
            pieces=ov.pieces,
            weight=f"{ov.weight} {ov.weight_unit}",
            volume=f"{ov.volume} {ov.volume_unit}" if ov.volume else None,
            flight_details=fl_str,
            latest_activity=f"Booking Ref: {ov.booking_reference_number or 'N/A'}",
            latest_location=dest_code if status_category == "DELIVERED" else orig_code,
            consignee_issued_to=ov.agent_name,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_parcels(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.latest_status)
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        orig_raw = ov.origin_location or ov.origin_country or "---"
        dest_raw = ov.destination_location or ov.destination_country or "---"
        orig = orig_raw.split(',')[0].strip() if orig_raw != "---" else "---"
        dest = dest_raw.split(',')[0].strip() if dest_raw != "---" else "---"
        formatted_awb = getattr(ov, "formatted_tracking_number", getattr(res, "formatted_tracking_number", getattr(ov, "formatted_awb", raw_input)))
        pcs_val = None
        if ov.pieces:
            digits_pcs = "".join(c for c in str(ov.pieces) if c.isdigit())
            if digits_pcs:
                pcs_val = int(digits_pcs)
        elif ov.number_of_packages:
            digits_pcs = "".join(c for c in str(ov.number_of_packages) if c.isdigit())
            if digits_pcs:
                pcs_val = int(digits_pcs)
        return UnifiedTrackingRecord(
            awb=formatted_awb,
            raw_input=raw_input,
            carrier_prefix="125",
            carrier_name="British Airways Cargo (BA)",
            carrier_code="BA",
            status=status_category,
            status_detail=ov.latest_status,
            origin=orig,
            destination=dest,
            route=f"{orig} ➔ {dest}",
            pieces=pcs_val,
            weight=ov.weight,
            flight_details=None,
            latest_activity=f"{ov.latest_status} ({ov.latest_date or ''})",
            latest_location=ov.latest_location or dest,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_kuwait(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.current_status)
        fl_str = ", ".join(dict.fromkeys(f.flight_number.strip() for f in res.flights if getattr(f, "flight_number", None))) if res.flights else None
        lat_act = res.operational_events[0].status_name if res.operational_events else ov.current_status
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="229",
            carrier_name="Kuwait Airways (KU)",
            carrier_code="KU",
            status=status_category,
            status_detail=ov.current_status,
            origin=ov.origin,
            destination=ov.destination,
            route=f"{ov.origin} ➔ {ov.destination}",
            pieces=ov.pieces,
            weight=f"{ov.gross_weight} {ov.weight_unit}",
            volume=f"{ov.volume} {ov.volume_unit}" if ov.volume else None,
            flight_details=fl_str,
            latest_activity=lat_act,
            latest_location=ov.destination if status_category == "DELIVERED" else ov.origin,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_emirates(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.order_status)
        orig_code = ov.origin.code if hasattr(ov.origin, "code") else str(ov.origin)
        dest_code = ov.destination.code if hasattr(ov.destination, "code") else str(ov.destination)
        fl_str = ", ".join(leg.flight_display for leg in res.itinerary if getattr(leg, "flight_display", None)) if res.itinerary else None
        lat_act = f"{ov.latest_milestone_code} - {ov.latest_milestone_description}" if ov.latest_milestone_code else ov.order_status
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="176",
            carrier_name="Emirates SkyCargo (EK)",
            carrier_code="EK",
            status=status_category,
            status_detail=ov.order_status,
            origin=orig_code,
            destination=dest_code,
            route=f"{orig_code} ➔ {dest_code}",
            pieces=ov.pieces,
            weight=f"{ov.gross_weight} {ov.weight_unit}",
            volume=f"{ov.volume} {ov.volume_unit}" if ov.volume else None,
            flight_details=fl_str,
            latest_activity=lat_act,
            latest_location=ov.latest_milestone_station or (dest_code if status_category == "DELIVERED" else orig_code),
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_lufthansa(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.latest_event)
        orig_code = ov.origin.code if hasattr(ov.origin, "code") else str(ov.origin)
        dest_code = ov.destination.code if hasattr(ov.destination, "code") else str(ov.destination)
        fl_str = ", ".join(dict.fromkeys(f.flight_number.strip() for f in res.flights if getattr(f, "flight_number", None))) if res.flights else None
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="020",
            carrier_name="Lufthansa Cargo (LH)",
            carrier_code="LH",
            status=status_category,
            status_detail=ov.latest_event_description or ov.latest_event,
            origin=orig_code,
            destination=dest_code,
            route=f"{orig_code} ➔ {dest_code}",
            pieces=ov.pieces,
            weight=f"{ov.gross_weight} {ov.weight_unit}",
            volume=f"{ov.volume} {ov.volume_unit}" if ov.volume else None,
            flight_details=fl_str,
            latest_activity=ov.latest_event_description or ov.latest_event,
            latest_location=dest_code if status_category == "DELIVERED" else orig_code,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def normalize_airindia(cls, res: Any, raw_input: str, elapsed_sec: float) -> UnifiedTrackingRecord:
        ov = res.overview
        status_category = cls._classify_status(ov.overall_status)
        fl_str = ", ".join(dict.fromkeys(f"AI {s.flight_number}".strip() for s in res.tracking_view if getattr(s, "flight_number", None))) if res.tracking_view else None
        raw_dict = res.model_dump() if hasattr(res, "model_dump") else res.dict()
        return UnifiedTrackingRecord(
            awb=ov.formatted_awb,
            raw_input=raw_input,
            carrier_prefix="098",
            carrier_name="Air India Cargo (AI)",
            carrier_code="AI",
            status=status_category,
            status_detail=ov.overall_status,
            origin=ov.origin_airport_code,
            destination=ov.destination_airport_code,
            route=f"{ov.origin_airport_code} ➔ {ov.destination_airport_code}",
            pieces=ov.pieces,
            weight=f"{ov.stated_weight} {ov.weight_unit}",
            volume=f"{ov.stated_volume} {ov.volume_unit}" if ov.stated_volume else None,
            flight_details=fl_str,
            latest_activity=ov.shipment_description or ov.overall_status,
            latest_location=ov.destination_airport_code if status_category == "DELIVERED" else ov.origin_airport_code,
            consignee_issued_to=None,
            execution_time_sec=round(elapsed_sec, 3),
            raw_data=raw_dict,
        )

    @classmethod
    def create_error_record(
        cls,
        awb_input: str,
        error_message: str,
        elapsed_sec: float,
        prefix: str = "",
        carrier_name: str = "Unknown Carrier",
        carrier_code: str = "",
        status_override: Optional[str] = None,
    ) -> UnifiedTrackingRecord:
        clean_awb = re.sub(r"[^\d]", "", awb_input)
        formatted = f"{clean_awb[:3]}-{clean_awb[3:]}" if len(clean_awb) == 11 else awb_input
        err_lower = error_message.lower()

        if status_override:
            status = status_override
        elif any(phrase in err_lower for phrase in ("unsupported", "skip", "not in supported")):
            status = "SKIPPED"
        elif any(phrase in err_lower for phrase in (
            "not found", "could not find", "not available", "no result", "does not exist", "no matching"
        )):
            status = "NOT_FOUND"
        elif any(phrase in err_lower for phrase in (
            "failed to resolve", "name resolution", "connection refused", "connection pool",
            "timed out", "timeout", "unreachable", "max retries exceeded", "service unavailable",
            "503", "502", "504", "portal unreachable", "network", "blocked"
        )):
            status = "UNREACHABLE"
        else:
            status = "ERROR"

        return UnifiedTrackingRecord(
            awb=formatted,
            raw_input=awb_input,
            carrier_prefix=prefix or (clean_awb[:3] if len(clean_awb) >= 3 else "---"),
            carrier_name=carrier_name,
            carrier_code=carrier_code,
            status=status,
            status_detail=error_message,
            execution_time_sec=round(elapsed_sec, 3),
            error_message=error_message,
        )
