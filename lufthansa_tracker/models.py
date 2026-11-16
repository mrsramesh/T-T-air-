"""
Pydantic data models for Lufthansa Cargo tracking data.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class LufthansaAirport(BaseModel):
    code: str
    name: Optional[str] = None


class LufthansaFlight(BaseModel):
    flight_number: str
    carrier_code: Optional[str] = None
    flight_date: Optional[str] = None
    origin: LufthansaAirport
    destination: LufthansaAirport
    scheduled_departure: Optional[str] = None
    actual_departure: Optional[str] = None
    scheduled_arrival: Optional[str] = None
    actual_arrival: Optional[str] = None
    aircraft_type: Optional[str] = None


class LufthansaStatusEvent(BaseModel):
    event_code: str
    event_name: str
    station: Optional[str] = None
    event_time: Optional[str] = None
    is_actual: bool = False
    pieces: Optional[int] = None
    weight: Optional[float] = None
    flight_number: Optional[str] = None
    discrepancy_code: Optional[str] = None


class LufthansaBookingSegment(BaseModel):
    flight_number: str
    origin: str
    destination: str
    flight_date: Optional[str] = None
    booking_status: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    volume: Optional[float] = None


class LufthansaOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    origin: LufthansaAirport
    destination: LufthansaAirport
    latest_event: str
    latest_event_description: str
    pieces: int
    gross_weight: float
    weight_unit: str = "KG"
    volume: float
    volume_unit: str = "CBM"
    product_name: Optional[str] = None
    product_code: Optional[str] = None
    special_cargo_codes: List[str] = Field(default_factory=list)
    latest_acceptance_time: Optional[str] = None
    planned_availability_time: Optional[str] = None
    actual_availability_time: Optional[str] = None


class LufthansaTrackingResult(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Lufthansa Cargo (020)"
    overview: LufthansaOverview
    flights: List[LufthansaFlight] = Field(
        default_factory=list, description="Flight movements and schedule"
    )
    status_history: List[LufthansaStatusEvent] = Field(
        default_factory=list, description="Status History / Chronological Events"
    )
    booking_segments: List[LufthansaBookingSegment] = Field(
        default_factory=list, description="Booking and acceptance details"
    )
