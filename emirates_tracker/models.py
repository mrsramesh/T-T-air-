"""
Pydantic data models for Emirates SkyCargo tracking data.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class EmiratesAirport(BaseModel):
    code: str
    name: Optional[str] = None


class EmiratesItineraryLeg(BaseModel):
    origin: EmiratesAirport
    destination: EmiratesAirport
    carrier_code: str = "EK"
    flight_number: str
    flight_display: str
    flight_date: Optional[str] = None
    aircraft_type: Optional[str] = None
    registration_number: Optional[str] = None
    scheduled_departure: Optional[str] = None
    actual_departure: Optional[str] = None
    scheduled_arrival: Optional[str] = None
    actual_arrival: Optional[str] = None
    movement_status: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "K"
    volume: Optional[float] = None
    volume_unit: str = "CM"


class EmiratesMilestone(BaseModel):
    code: str
    description: str
    station: Optional[str] = None
    timestamp: Optional[str] = None
    timestamp_utc: Optional[int] = None
    is_latest: bool = False
    import_status_message: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "K"


class EmiratesOrderSummary(BaseModel):
    booking_reference_number: str
    job_reference_number: Optional[str] = None
    awb_reference_number: Optional[str] = None
    order_status_code: Optional[str] = None
    order_status_description: Optional[str] = None
    origin: EmiratesAirport
    destination: EmiratesAirport
    commodity: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "K"


class EmiratesOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    booking_reference_number: str
    job_reference_number: Optional[str] = None
    order_status: str
    origin: EmiratesAirport
    destination: EmiratesAirport
    latest_milestone_code: str
    latest_milestone_description: str
    latest_milestone_station: Optional[str] = None
    latest_milestone_time: Optional[str] = None
    commodity: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    special_handling_codes: List[str] = Field(default_factory=list)
    pieces: int
    gross_weight: float
    chargeable_weight: Optional[float] = None
    weight_unit: str = "K"
    volume: float
    volume_unit: str = "CM"


class EmiratesTrackingResult(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Emirates SkyCargo (176)"
    overview: EmiratesOverview
    itinerary: List[EmiratesItineraryLeg] = Field(
        default_factory=list, description="Flight routing legs and transit schedules"
    )
    milestones: List[EmiratesMilestone] = Field(
        default_factory=list, description="Milestones event timeline"
    )
    all_orders: List[EmiratesOrderSummary] = Field(
        default_factory=list, description="All associated bookings/orders for this AWB"
    )
