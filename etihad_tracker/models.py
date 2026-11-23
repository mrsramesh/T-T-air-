"""
Data models for Etihad Cargo (IATA Prefix 607 - EY).
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class EtihadFlightLeg(BaseModel):
    flight_no: str
    segment: str
    flight_date: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    pieces: Optional[str] = None
    weight: Optional[str] = None
    status: Optional[str] = "Confirmed"


class EtihadMilestone(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    event_code: Optional[str] = None
    status: str
    station: Optional[str] = None
    details: Optional[str] = None
    flight_no: Optional[str] = None
    pieces: Optional[str] = None
    weight: Optional[str] = None
    is_latest: bool = False


class EtihadOverview(BaseModel):
    awb: str
    formatted_awb: str
    origin: str
    destination: str
    route: str
    pieces: Optional[int] = None
    gross_weight: Optional[str] = None
    product_name: str = "General Cargo"
    special_handling_code: Optional[str] = "GEN, EYP"
    status: str
    latest_activity: str
    latest_station: Optional[str] = None
    latest_time: Optional[str] = None
    track_trace_url: str
    direct_portal_url: str


class EtihadTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    carrier: str = "Etihad Cargo (EY)"
    carrier_code: str = "EY"
    carrier_prefix: str = "607"
    overview: EtihadOverview
    flights: List[EtihadFlightLeg] = Field(default_factory=list)
    milestones: List[EtihadMilestone] = Field(default_factory=list)
