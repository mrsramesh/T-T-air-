"""
Unified tracking data models for multi-carrier bulk air cargo tracking.
Standardizes records across all 10 major airlines.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UnifiedTrackingRecord(BaseModel):
    """
    Standardized tracking record across all air cargo carriers.
    Provides consistent fields for table displays, Excel sheets, and JSON APIs.
    """
    awb: str = Field(description="Normalized AWB formatted with hyphen (e.g. 312-92989396)")
    raw_input: str = Field(description="Original uncleaned AWB input string")
    carrier_prefix: str = Field(description="3-digit airline prefix (e.g. 312, 703, 077)")
    carrier_name: str = Field(description="Full airline name (e.g. IndiGo CarGo (6E))")
    carrier_code: str = Field(default="", description="IATA 2-letter airline code (e.g. 6E, NO, MS)")
    
    # Standard status categories: DELIVERED, IN_TRANSIT, ARRIVED, DEPARTED, BOOKED, ACCEPTED, NOT_FOUND, ERROR
    status: str = Field(default="UNKNOWN", description="Standardized status category")
    status_detail: str = Field(default="", description="Verbatim status description from carrier portal")
    
    # Routing
    origin: str = Field(default="---", description="Origin airport IATA code (e.g. BOM, DEL)")
    destination: str = Field(default="---", description="Destination airport IATA code (e.g. BKK, KWI)")
    route: str = Field(default="---", description="Formatted route string (e.g. BOM ➔ BKK)")
    
    # Cargo metrics
    pieces: Optional[int] = Field(default=None, description="Total piece count")
    weight: Optional[str] = Field(default=None, description="Gross weight with unit (e.g. 898.00 Kgs)")
    volume: Optional[str] = Field(default=None, description="Volume with unit if available")
    
    # Movement & logistics
    flight_details: Optional[str] = Field(default=None, description="Flight number and dates (e.g. 6E1087 / 08/11/2026)")
    latest_activity: Optional[str] = Field(default=None, description="Latest event description and date/time")
    latest_location: Optional[str] = Field(default=None, description="Station/airport where latest activity took place")
    consignee_issued_to: Optional[str] = Field(default=None, description="Consignee or delivery order release party")
    
    # Performance & Diagnostics
    execution_time_sec: float = Field(default=0.0, description="Time taken to track this shipment in seconds")
    error_message: Optional[str] = Field(default=None, description="Error message if tracking failed")
    
    # Optional full underlying carrier data
    raw_data: Optional[Dict[str, Any]] = Field(default=None, description="Underlying airline-specific data model dictionary")


class BulkTrackingSummary(BaseModel):
    """
    Summary metrics and aggregation of a bulk tracking batch.
    """
    total_requested: int = Field(default=0)
    total_successful: int = Field(default=0)
    total_delivered: int = Field(default=0)
    total_in_transit: int = Field(default=0)
    total_not_found: int = Field(default=0)
    total_errors: int = Field(default=0)
    total_time_sec: float = Field(default=0.0)
    records: List[UnifiedTrackingRecord] = Field(default_factory=list)
