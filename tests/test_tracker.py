"""
Unit and integration tests for Multi-Carrier Cargo Tracker:
- Air India Cargo (098)
- Lufthansa Cargo (020)
- Emirates SkyCargo (176)
"""

import unittest
from airindia_tracker.client import AirIndiaCargoClient
from lufthansa_tracker.client import LufthansaCargoClient
from emirates_tracker.client import EmiratesTrackerClient


class TestCargoTrackers(unittest.TestCase):

    def setUp(self):
        self.ai_client = AirIndiaCargoClient()
        self.lh_client = LufthansaCargoClient()
        self.ek_client = EmiratesTrackerClient()

    def test_airindia_awb_normalization(self):
        self.assertEqual(self.ai_client.normalize_awb("098-30244056"), "09830244056")
        self.assertEqual(self.ai_client.normalize_awb("30244056"), "09830244056")
        self.assertEqual(self.ai_client.format_awb("09830244056"), "098-30244056")

    def test_lufthansa_awb_normalization(self):
        # 11 digits with prefix
        prefix, serial = self.lh_client.normalize_awb("020-04585280")
        self.assertEqual(prefix, "020")
        self.assertEqual(serial, "04585280")

        # 8 digits serial only (auto-prefix 020)
        prefix, serial = self.lh_client.normalize_awb("04585280")
        self.assertEqual(prefix, "020")
        self.assertEqual(serial, "04585280")

        self.assertEqual(self.lh_client.format_awb(prefix, serial), "020-04585280")

    def test_emirates_awb_normalization(self):
        # 11 digits with prefix
        prefix, serial, formatted, full_digits = self.ek_client.normalize_awb("176-63116340")
        self.assertEqual(prefix, "176")
        self.assertEqual(serial, "63116340")
        self.assertEqual(formatted, "176-63116340")
        self.assertEqual(full_digits, "17663116340")

        # 8 digits serial only (auto-prefix 176)
        prefix, serial, formatted, full_digits = self.ek_client.normalize_awb("63116340")
        self.assertEqual(prefix, "176")
        self.assertEqual(serial, "63116340")
        self.assertEqual(formatted, "176-63116340")
        self.assertEqual(full_digits, "17663116340")

    def test_live_airindia_tracking(self):
        res = self.ai_client.track("098-30244056")
        self.assertEqual(res.formatted_awb, "098-30244056")
        self.assertEqual(res.overview.pieces, 43)
        self.assertEqual(res.overview.origin_airport_code, "DEL")
        self.assertEqual(res.overview.destination_airport_code, "YYZ")
        self.assertEqual(res.overview.overall_status, "DELIVERED")

    def test_live_lufthansa_tracking(self):
        res = self.lh_client.track("020-04585280")
        self.assertEqual(res.formatted_awb, "020-04585280")
        self.assertEqual(res.overview.origin.code, "DEL")
        self.assertEqual(res.overview.destination.code, "GRU")
        self.assertIn(res.overview.latest_event, ["RCF", "MAN"])
        self.assertGreater(len(res.flights), 0)
        self.assertGreater(len(res.status_history), 0)

    def test_live_emirates_tracking(self):
        res = self.ek_client.track("176-63116340")
        self.assertEqual(res.formatted_awb, "176-63116340")
        self.assertEqual(res.overview.origin.code, "DEL")
        self.assertEqual(res.overview.destination.code, "MLA")
        self.assertEqual(res.overview.latest_milestone_code, "DLV")
        self.assertEqual(res.overview.pieces, 11)
        self.assertEqual(res.overview.gross_weight, 1467.0)
        self.assertEqual(res.overview.weight_unit, "K")
        self.assertIn("Emirates Pharma Plus", res.overview.commodity)
        self.assertGreater(len(res.itinerary), 0)
        self.assertGreater(len(res.milestones), 0)


if __name__ == "__main__":
    unittest.main()
