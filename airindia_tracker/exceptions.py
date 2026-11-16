"""
Custom exceptions for Air India Cargo Tracker.
"""

class AirIndiaTrackerException(Exception):
    """Base exception for Air India Cargo Tracker."""
    pass

class InvalidAWBFormatException(AirIndiaTrackerException):
    """Raised when an AWB number format is invalid."""
    pass

class AWBNotFoundException(AirIndiaTrackerException):
    """Raised when the specified AWB is not found in the portal."""
    pass

class PortalAuthException(AirIndiaTrackerException):
    """Raised when anonymous session establishment or authentication fails."""
    pass

class PortalAPIException(AirIndiaTrackerException):
    """Raised when the upstream iCargo Neo portal returns an API error."""
    pass
