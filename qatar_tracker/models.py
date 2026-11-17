"""
Pydantic data models for Qatar Airways Cargo (157).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class QatarFlightSegment(BaseModel):
    flight_number: str
    origin: str
    destination: str
    departure_date_time: Optional[str] = None
    arrival_date_time: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "Kg"
    volume: Optional[float] = None
    volume_unit: str = "m³"
    flight_status: Optional[str] = "Departed"
    operation_type: Optional[str] = "PAX"
    booking_status: Optional[str] = None


class QatarMilestone(BaseModel):
    status_code: str
    details: str
    airport: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "Kg"
    is_latest: bool = False
    created_date: Optional[str] = None


class QatarOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Qatar Airways Cargo (157)"
    origin: Optional[str] = None
    destination: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    weight_unit: str = "Kg"
    volume: Optional[float] = None
    volume_unit: str = "m³"
    overall_status: str = "Unknown"
    latest_status_message: Optional[str] = None
    latest_arrival_message: Optional[str] = None
    shipment_info: Optional[str] = None


class QatarTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    carrier: str = "Qatar Airways Cargo (157)"
    overview: QatarOverview
    flights: List[QatarFlightSegment] = Field(default_factory=list)
    milestones: List[QatarMilestone] = Field(default_factory=list)
