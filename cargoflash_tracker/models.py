"""
Pydantic data models for EgyptAir Cargo (Cargo Flash Portal - 077).
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class CargoFlashMilestonePlanItem(BaseModel):
    action: str
    station: str
    date_time: Optional[str] = None
    pieces: Optional[int] = None


class CargoFlashFlightDetail(BaseModel):
    event: str
    description: str
    station: str
    flight_no: str
    route: str
    flight_display: str
    flight_date: Optional[str] = None
    total_pieces: Optional[int] = None
    planned_pieces: Optional[int] = None
    gross_weight: Optional[float] = None
    cbm: Optional[float] = None
    created_on: Optional[str] = None


class CargoFlashOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    carrier: str = "EgyptAir Cargo (Cargo Flash) (077)"
    origin: str
    destination: str
    pieces: int
    gross_weight: float
    weight_unit: str = "KG"
    chargeable_weight: Optional[float] = None
    volume: Optional[float] = None
    cbm: Optional[float] = None
    volume_unit: str = "CBM"
    product_name: str
    commodity: Optional[str] = None
    agent_name: Optional[str] = None
    booking_station: Optional[str] = None
    latest_event_action: Optional[str] = None
    latest_event_station: Optional[str] = None
    latest_event_time: Optional[str] = None
    latest_event_message: str


class CargoFlashTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    carrier: str = "EgyptAir Cargo (Cargo Flash) (077)"
    overview: CargoFlashOverview
    milestone_plan: List[CargoFlashMilestonePlanItem] = Field(default_factory=list)
    flight_details: List[CargoFlashFlightDetail] = Field(default_factory=list)
