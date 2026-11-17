"""
Pydantic data models for Virgin Atlantic Cargo (932).
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class VirginAirport(BaseModel):
    code: str
    name: Optional[str] = None


class VirginFlightSegment(BaseModel):
    flight_number: str
    origin: VirginAirport
    destination: VirginAirport
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = "K"
    volume: Optional[float] = None
    volume_unit: Optional[str] = "CM"
    status: str = "Confirmed"


class VirginMilestone(BaseModel):
    code: str
    description: str
    station: Optional[str] = None
    timestamp: Optional[str] = None
    flight_number: Optional[str] = None
    board_point: Optional[str] = None
    off_point: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: Optional[str] = "K"
    is_latest: bool = False


class VirginOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Virgin Atlantic Cargo (932)"
    job_reference_number: Optional[str] = None
    booking_reference_number: Optional[str] = None
    order_status: str
    shipment_status: Optional[str] = None
    origin: VirginAirport
    destination: VirginAirport
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "K"
    volume: Optional[float] = None
    volume_unit: str = "CM"
    commodity: Optional[str] = None
    product_name: Optional[str] = None
    agent_name: Optional[str] = None
    transit_duration: Optional[str] = None
    latest_milestone_code: Optional[str] = None
    latest_milestone_description: Optional[str] = None
    latest_milestone_time: Optional[str] = None


class VirginTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    carrier: str = "Virgin Atlantic Cargo (932)"
    overview: VirginOverview
    flights: List[VirginFlightSegment] = Field(default_factory=list)
    milestones: List[VirginMilestone] = Field(default_factory=list)
