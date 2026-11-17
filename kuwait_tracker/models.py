"""
Pydantic data models for Kuwait Airways Cargo tracking data.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class KuwaitFlightLeg(BaseModel):
    flight_number: str
    flight_date: Optional[str] = None
    origin: str
    destination: str
    pieces: Optional[int] = None
    weight: Optional[float] = None
    volume: Optional[float] = None
    status_code: Optional[str] = None
    status_message: Optional[str] = None
    sequence_no: Optional[int] = None


class KuwaitStationBox(BaseModel):
    airport: str
    pieces: Optional[int] = None
    weight: Optional[float] = None
    status_code_1: Optional[str] = None
    status_code_2: Optional[str] = None
    event_time_1: Optional[str] = None
    event_time_2: Optional[str] = None
    status_message_1: Optional[str] = None
    status_message_2: Optional[str] = None
    box_index: Optional[int] = None


class KuwaitOperationalEvent(BaseModel):
    status_code: str
    status_name: str
    status_message: Optional[str] = None
    airport: Optional[str] = None
    flight_number: Optional[str] = None
    flight_date: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    pieces: Optional[int] = None
    weight: Optional[float] = None
    volume: Optional[float] = None
    full_details: Optional[str] = None
    sequence_no: Optional[int] = None


class KuwaitOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    origin: str
    destination: str
    pieces: int
    gross_weight: float
    weight_unit: str = "KGS"
    volume: float
    volume_unit: str = "CBM"
    current_status: str
    latest_event_code: Optional[str] = None
    latest_event_airport: Optional[str] = None
    latest_event_time: Optional[str] = None


class KuwaitTrackingResult(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "Kuwait Airways (229)"
    overview: KuwaitOverview
    flights: List[KuwaitFlightLeg] = Field(
        default_factory=list, description="Flight legs and routing segments"
    )
    station_boxes: List[KuwaitStationBox] = Field(
        default_factory=list, description="Routing transit station summary cards"
    )
    operational_events: List[KuwaitOperationalEvent] = Field(
        default_factory=list, description="Chronological operational tracking status events"
    )
