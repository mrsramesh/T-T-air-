"""
Pydantic data models for Neos Air Cargo (NO - 703) & World Cargo Solutions.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class NeosFlightLeg(BaseModel):
    origin: str
    destination: str
    flight_no: str
    flight_display: str
    status: str
    weight: Optional[str] = None
    departure_time: Optional[str] = None
    arrival_time: Optional[str] = None


class NeosMilestone(BaseModel):
    step: int
    timestamp: str
    status_code: str
    description: str
    origin: str
    destination: str
    flight_no: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[str] = None
    is_latest: bool = False


class NeosOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Neos Air Cargo (NO) / World Cargo Solutions (703)"
    origin: str
    destination: str
    pieces: Optional[int] = None
    gross_weight: Optional[str] = None
    commodity: Optional[str] = None
    current_status: str
    latest_event_time: Optional[str] = None
    latest_event_code: Optional[str] = None
    progress_step: Optional[str] = None
    source: str = "World Cargo Solutions / track-trace"


class NeosTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    airline: str = "Neos Air Cargo (NO) / World Cargo Solutions (703)"
    overview: NeosOverview
    flights: List[NeosFlightLeg] = Field(default_factory=list)
    milestones: List[NeosMilestone] = Field(default_factory=list)
