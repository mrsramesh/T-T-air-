"""
Pydantic data models for ParcelsApp & British Airways Cargo tracking data.
"""

from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field


class ParcelsCourier(BaseModel):
    name: str
    slug: Optional[str] = None


class ParcelsStateEvent(BaseModel):
    date: Optional[str] = None
    status: str
    location: Optional[str] = None
    carrier_name: Optional[str] = None
    is_latest: bool = False


class ParcelsAttribute(BaseModel):
    key: str
    name: str
    value: str


class ParcelsOverview(BaseModel):
    tracking_number: str
    formatted_tracking_number: str
    origin_country: Optional[str] = None
    origin_location: Optional[str] = None
    destination_country: Optional[str] = None
    destination_location: Optional[str] = None
    weight: Optional[str] = None
    number_of_packages: Optional[str] = None
    pieces: Optional[str] = None
    days_in_transit: Optional[str] = None
    primary_carrier: str = "British Airways Cargo"
    couriers: List[str] = Field(default_factory=list)
    latest_status: str
    latest_location: Optional[str] = None
    latest_date: Optional[str] = None


class ParcelsTrackingResult(BaseModel):
    tracking_number: str
    formatted_tracking_number: str
    airline: str = "British Airways Cargo / IAG Cargo (125)"
    overview: ParcelsOverview
    states: List[ParcelsStateEvent] = Field(
        default_factory=list, description="Chronological milestone and flight states"
    )
    couriers: List[ParcelsCourier] = Field(
        default_factory=list, description="Participating couriers and ground handlers"
    )
    attributes: List[ParcelsAttribute] = Field(
        default_factory=list, description="Extracted shipment attributes"
    )
