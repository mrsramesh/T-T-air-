"""
Unit and integration tests for Air India Cargo Tracker.
"""

import unittest
from airindia_tracker.client import AirIndiaCargoClient
from airindia_tracker.exceptions import InvalidAWBFormatException, AWBNotFoundException


class TestAirIndiaTracker(unittest.TestCase):

    def setUp(self):
        self.client = AirIndiaCargoClient()

    def test_awb_normalization(self):
        # 11 digits with hyphen
        self.assertEqual(self.client.normalize_awb("098-30244056"), "09830244056")
        # 11 digits without hyphen
        self.assertEqual(self.client.normalize_awb("09830244056"), "09830244056")
        # 11 digits with spaces
        self.assertEqual(self.client.normalize_awb("098 30244056"), "09830244056")
        # 8 digits serial (auto-adds Air India prefix 098)
        self.assertEqual(self.client.normalize_awb("30244056"), "09830244056")

        # Formatting
        self.assertEqual(self.client.format_awb("09830244056"), "098-30244056")

    def test_invalid_awb_raises(self):
        with self.assertRaises(InvalidAWBFormatException):
            self.client.normalize_awb("")

        with self.assertRaises(InvalidAWBFormatException):
            self.client.normalize_awb("abc-1234567")

        with self.assertRaises(InvalidAWBFormatException):
            self.client.normalize_awb("1234")  # too short

    def test_live_tracking_sample_awb(self):
        """Integration test against Air India live portal with sample AWB."""
        res = self.client.track("098-30244056")

        # Verify Overview
        self.assertEqual(res.awb_number, "09830244056")
        self.assertEqual(res.formatted_awb, "098-30244056")
        self.assertEqual(res.overview.pieces, 43)
        self.assertEqual(res.overview.stated_weight, 271.0)
        self.assertEqual(res.overview.stated_volume, 2.31)
        self.assertEqual(res.overview.origin_airport_code, "DEL")
        self.assertEqual(res.overview.destination_airport_code, "YYZ")
        self.assertEqual(res.overview.overall_status, "DELIVERED")

        # Verify Tracking View (Flight Segments)
        self.assertGreater(len(res.tracking_view), 0)
        first_segment = res.tracking_view[0]
        self.assertEqual(first_segment.segment_origin, "DEL")
        self.assertEqual(first_segment.segment_destination, "YYZ")

        # Verify Activity View (Events)
        self.assertGreater(len(res.activity_view), 0)
        event_codes = [ev.event_code for ev in res.activity_view]
        self.assertIn("DLV", event_codes)
        self.assertIn("RCS", event_codes)


if __name__ == "__main__":
    unittest.main()
