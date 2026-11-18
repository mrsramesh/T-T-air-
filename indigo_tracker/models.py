"""
Pydantic data models for IndiGo CarGo (6E - 312) tracking data.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class IndigoBookingItem(BaseModel):
    status: str
    station: str
    destination: str
    pieces: Optional[int] = None
    weight: Optional[str] = None
    flight_no: Optional[str] = None
    event_time: Optional[str] = None


class IndigoStatusHistoryItem(BaseModel):
    station: str
    milestone: str
    pieces: Optional[int] = None
    weight: Optional[str] = None
    flight_no: Optional[str] = None
    flight_date: Optional[str] = None
    origin: str
    destination: str
    uld_or_remarks: Optional[str] = None
    event_time: Optional[str] = None
    is_latest: bool = False


class IndigoDeliveryOrder(BaseModel):
    do_number: str
    awb_number: str
    pieces: Optional[int] = None
    weight: Optional[str] = None
    flight_details: Optional[str] = None
    uld_number: Optional[str] = None
    hawb_number: Optional[str] = None
    issued_to: Optional[str] = None


class IndigoOverview(BaseModel):
    awb_number: str
    formatted_awb: str
    airline: str = "IndiGo CarGo (6E) (312)"
    origin: str
    destination: str
    pieces: Optional[int] = None
    gross_weight: Optional[str] = None
    current_status: str
    latest_activity: str
    flight_no: Optional[str] = None
    issued_to: Optional[str] = None


class IndigoTrackingResult(BaseModel):
    awb: str
    formatted_awb: str
    airline: str = "IndiGo CarGo (6E) (312)"
    overview: IndigoOverview
    booking_info: List[IndigoBookingItem] = Field(default_factory=list)
    status_history: List[IndigoStatusHistoryItem] = Field(default_factory=list)
    delivery_orders: List[IndigoDeliveryOrder] = Field(default_factory=list)
