"""
Pydantic data models for Air India Cargo shipment tracking.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class Milestone(BaseModel):
    milestone: str
    status: str
    is_completed: bool = False


class FlightSegment(BaseModel):
    carrier_code: Optional[str] = None
    flight_number: Optional[str] = None
    segment_origin: Optional[str] = None
    segment_destination: Optional[str] = None
    departure_date: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_date: Optional[str] = None
    arrival_time: Optional[str] = None
    pieces: Optional[int] = None


class ActivityEvent(BaseModel):
    event_code: str
    event_name: str
    airport_code: Optional[str] = None
    event_time: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = "K"
    uld_number: Optional[str] = None
    flight_carrier_code: Optional[str] = None
    flight_number: Optional[str] = None
    flight_date: Optional[str] = None
    flight_origin: Optional[str] = None
    flight_destination: Optional[str] = None
    last_updated_time: Optional[str] = None


class ShipmentOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    pieces: int
    stated_weight: float
    weight_unit: str = "KG"
    stated_volume: float
    volume_unit: str = "CBM"
    special_handling_code: Optional[str] = None
    product_name: Optional[str] = None
    shipment_description: Optional[str] = None
    origin_airport_code: str
    destination_airport_code: str
    overall_status: str
    milestones: List[Milestone] = []
    number_of_flights: int = 0


class TrackingResult(BaseModel):
    awb_number: str
    formatted_awb: str
    overview: ShipmentOverview
    tracking_view: List[FlightSegment] = Field(
        default_factory=list,
        description="Flight routes, segments, and schedule details (Tracking View)",
    )
    activity_view: List[ActivityEvent] = Field(
        default_factory=list,
        description="Chronological audit log of cargo events (Activity View)",
    )
