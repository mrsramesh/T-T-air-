"""
Data models for Saudia Cargo (IATA Prefix 065 - SV).
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class SaudiaFlightLeg(BaseModel):
    flight_no: str
    segment: str
    flight_date: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None
    pieces: Optional[str] = None
    weight: Optional[str] = None
    status: Optional[str] = "Confirmed"


class SaudiaMilestone(BaseModel):
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


class SaudiaOverview(BaseModel):
    awb: str
    formatted_awb: str
    origin: str
    destination: str
    route: str
    pieces: Optional[int] = None
    gross_weight: Optional[str] = None
    volume: Optional[str] = None
    flight_category: Optional[str] = "P"
    product_name: str = "General Air Cargo"
    status: str
    latest_activity: str
    latest_station: Optional[str] = None
    latest_time: Optional[str] = None
    track_trace_url: str
    direct_portal_url: str


class SaudiaTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    carrier: str = "Saudia Cargo (SV)"
    carrier_code: str = "SV"
    carrier_prefix: str = "065"
    overview: SaudiaOverview
    flights: List[SaudiaFlightLeg] = Field(default_factory=list)
    milestones: List[SaudiaMilestone] = Field(default_factory=list)
