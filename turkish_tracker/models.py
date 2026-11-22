"""
Pydantic data models for Turkish Cargo (IATA Prefix 235 - TK).
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class TurkishFlightLeg(BaseModel):
    flight_no: str = Field(..., description="Flight number, e.g. TK0717, TK1931")
    flight_date: str = Field(..., description="Flight scheduled date, e.g. 17.09.2026")
    eta: Optional[str] = Field(None, description="Estimated Time of Arrival, e.g. 17.09.2026 10:45")
    etd: Optional[str] = Field(None, description="Estimated Time of Departure, e.g. 17.09.2026 06:30")
    segment: Optional[str] = Field(None, description="Routing sector, e.g. DEL-IST, IST-LHR")
    pieces: Optional[int] = Field(None, description="Package piece count on leg")
    weight: Optional[str] = Field(None, description="Weight on leg, e.g. 470 kg, 200 kg")
    volume: Optional[str] = Field(None, description="Stated volume on leg, e.g. 5.14, 2")
    approval_status: Optional[str] = Field("Approved", description="Reservation status")


class TurkishMilestone(BaseModel):
    date: Optional[str] = Field(None, description="Event timestamp")
    status: str = Field(..., description="Status milestone, e.g. BKD, MAN, DEP, ARR, RCF, DLV")
    station: Optional[str] = Field(None, description="Airport station code")
    details: Optional[str] = Field(None, description="Milestone descriptive text")


class TurkishOverview(BaseModel):
    awb: str = Field(..., description="Clean AWB number")
    formatted_awb: str = Field(..., description="Standard formatted AWB 235-XXXXXXXX")
    prefix: str = Field("235", description="IATA Prefix")
    serial: str = Field(..., description="8-digit serial number")
    status: str = Field("IN_TRANSIT", description="Overall shipment status")
    origin: str = Field("---", description="Origin 3-letter IATA code")
    destination: str = Field("---", description="Destination 3-letter IATA code")
    route: str = Field("---", description="Route display string, e.g. DEL ➔ IST ➔ LHR")
    total_pieces: Optional[int] = Field(None, description="Total piece count")
    gross_weight: Optional[str] = Field(None, description="Total gross weight with unit")
    volume: Optional[str] = Field(None, description="Total volume / CBM")
    last_acceptance_date: Optional[str] = Field(None, description="Last acceptance timestamp")
    latest_activity: Optional[str] = Field(None, description="Latest event description")
    consignee_issued_to: Optional[str] = Field(None, description="Booking customer or consignee")


class TurkishTrackingResult(BaseModel):
    airline: str = Field("Turkish Cargo (TK)", description="Carrier Name")
    formatted_awb: str = Field(..., description="Standard formatted AWB e.g. 235-XXXXXXXX")
    overview: TurkishOverview
    flight_legs: List[TurkishFlightLeg] = Field(default_factory=list, description="Cargo reservation flight legs")
    milestones: List[TurkishMilestone] = Field(default_factory=list, description="Operational milestone events")
    raw_data: Optional[Dict[str, Any]] = None
