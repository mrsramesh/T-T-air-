"""
Unit and integration tests for Multi-Carrier Cargo Tracker:
- Air India Cargo (098)
- Lufthansa Cargo (020)
- Emirates SkyCargo (176)
- Kuwait Airways Cargo (229)
- British Airways Cargo (125)
- Virgin Atlantic Cargo (932)
- Qatar Airways Cargo (157)
- EgyptAir Cargo / Cargo Flash (077)
"""

import unittest
from airindia_tracker.client import AirIndiaCargoClient
from lufthansa_tracker.client import LufthansaCargoClient
from emirates_tracker.client import EmiratesTrackerClient
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError
from parcels_tracker.client import ParcelsTrackerClient, ParcelsShipmentNotFoundError
from virgin_tracker.client import VirginCargoClient, VirginShipmentNotFoundError
from qatar_tracker.client import QatarCargoClient, QatarShipmentNotFoundError
from cargoflash_tracker.client import CargoFlashClient, CargoFlashShipmentNotFoundError


class TestCargoTrackers(unittest.TestCase):

    def setUp(self):
        self.ai_client = AirIndiaCargoClient()
        self.lh_client = LufthansaCargoClient()
        self.ek_client = EmiratesTrackerClient()
        self.kw_client = KuwaitCargoClient()
        self.parcels_client = ParcelsTrackerClient()
        self.virgin_client = VirginCargoClient()
        self.qatar_client = QatarCargoClient()
        self.cargoflash_client = CargoFlashClient()

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

    def test_kuwait_awb_normalization(self):
        # 11 digits with prefix
        prefix, serial, formatted, full_digits = self.kw_client.normalize_awb("229-18148900")
        self.assertEqual(prefix, "229")
        self.assertEqual(serial, "18148900")
        self.assertEqual(formatted, "229-18148900")
        self.assertEqual(full_digits, "22918148900")

        # 8 digits serial only (auto-prefix 229)
        prefix, serial, formatted, full_digits = self.kw_client.normalize_awb("18148900")
        self.assertEqual(prefix, "229")
        self.assertEqual(serial, "18148900")
        self.assertEqual(formatted, "229-18148900")
        self.assertEqual(full_digits, "22918148900")

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
        self.assertTrue(bool(res.overview.latest_event))
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

    def test_live_kuwait_tracking(self):
        res = self.kw_client.track("229-18148900")
        self.assertEqual(res.formatted_awb, "229-18148900")
        self.assertEqual(res.overview.origin, "BOM")
        self.assertEqual(res.overview.destination, "LHR")
        self.assertEqual(res.overview.pieces, 2)
        self.assertEqual(res.overview.gross_weight, 1180.0)
        self.assertEqual(res.overview.volume, 1.68)
        self.assertIn("Delivered", res.overview.current_status)
        self.assertEqual(len(res.flights), 2)
        self.assertEqual(len(res.station_boxes), 3)
        self.assertGreaterEqual(len(res.operational_events), 10)

    def test_kuwait_not_found_handling(self):
        with self.assertRaises(KuwaitShipmentNotFoundError) as ctx:
            self.kw_client.track("229-17349566")
        self.assertIn("Could not find AWB 229-17349566", str(ctx.exception))

    def test_parcels_awb_normalization(self):
        prefix, serial, formatted, full_digits = self.parcels_client.normalize_tracking_number("125-24128344")
        self.assertEqual(prefix, "125")
        self.assertEqual(serial, "24128344")
        self.assertEqual(formatted, "125-24128344")
        self.assertEqual(full_digits, "12524128344")

        # Serial only
        prefix, serial, formatted, full_digits = self.parcels_client.normalize_tracking_number("24128344")
        self.assertEqual(prefix, "125")
        self.assertEqual(serial, "24128344")
        self.assertEqual(formatted, "125-24128344")
        self.assertEqual(full_digits, "12524128344")

    def test_live_parcels_british_airways_tracking(self):
        res = self.parcels_client.track("125-24128344", headless=True)
        self.assertEqual(res.formatted_tracking_number, "125-24128344")
        self.assertIn("British Airways", res.overview.primary_carrier)
        self.assertIn("DEL", res.overview.origin_location or "")
        self.assertIn("ATL", res.overview.destination_location or "")
        self.assertEqual(res.overview.number_of_packages, "65")
        self.assertIn("1103", res.overview.weight or "")
        self.assertGreaterEqual(len(res.states), 15)
        self.assertGreaterEqual(len(res.couriers), 1)

    def test_virgin_awb_normalization(self):
        prefix, serial, formatted, full_digits = self.virgin_client.normalize_awb("932-78989514")
        self.assertEqual(prefix, "932")
        self.assertEqual(serial, "78989514")
        self.assertEqual(formatted, "932-78989514")
        self.assertEqual(full_digits, "93278989514")

        # 8-digit input (auto-prefix 932)
        prefix, serial, formatted, full_digits = self.virgin_client.normalize_awb("78989514")
        self.assertEqual(prefix, "932")
        self.assertEqual(serial, "78989514")
        self.assertEqual(formatted, "932-78989514")
        self.assertEqual(full_digits, "93278989514")

    def test_live_virgin_tracking(self):
        res = self.virgin_client.track("932-78989514", headless=True)
        self.assertEqual(res.formatted_awb, "932-78989514")
        self.assertEqual(res.overview.origin.code, "DEL")
        self.assertEqual(res.overview.destination.code, "JFK")
        self.assertEqual(res.overview.pieces, 4)
        self.assertEqual(res.overview.weight, 1780.0)
        self.assertEqual(res.overview.weight_unit, "K")
        self.assertIn("confirmed", res.overview.order_status.lower())
        self.assertEqual(res.overview.job_reference_number, "6532966")
        self.assertEqual(res.overview.booking_reference_number, "7598319")
        self.assertEqual(len(res.flights), 2)
        self.assertEqual(res.flights[0].flight_number, "VS 0303")
        self.assertEqual(res.flights[1].flight_number, "VS 0045")
        self.assertGreaterEqual(len(res.milestones), 2)

    def test_virgin_not_found_handling(self):
        with self.assertRaises(VirginShipmentNotFoundError) as ctx:
            self.virgin_client.track("932-99999999", headless=True)
        self.assertIn("Could not find AWB 932-99999999", str(ctx.exception))

    def test_qatar_awb_normalization(self):
        prefix, serial, formatted, portal_serial = self.qatar_client.normalize_awb("157-5366-1580")
        self.assertEqual(prefix, "157")
        self.assertEqual(serial, "53661580")
        self.assertEqual(formatted, "157-53661580")
        self.assertEqual(portal_serial, "53661580")

        # 8-digit serial input (prefix 157 auto-inferred)
        prefix, serial, formatted, portal_serial = self.qatar_client.normalize_awb("53661580")
        self.assertEqual(prefix, "157")
        self.assertEqual(serial, "53661580")
        self.assertEqual(formatted, "157-53661580")
        self.assertEqual(portal_serial, "53661580")

    def test_live_qatar_tracking(self):
        res = self.qatar_client.track("157-5366-1580", headless=True)
        self.assertEqual(res.formatted_awb, "157-53661580")
        self.assertEqual(res.overview.origin, "DEL")
        self.assertEqual(res.overview.destination, "LUN")
        self.assertEqual(res.overview.pieces, 2)
        self.assertEqual(res.overview.weight, 1065.0)
        self.assertEqual(res.overview.volume, 2.706)
        self.assertEqual(res.overview.overall_status, "Delivered")
        self.assertEqual(len(res.flights), 3)
        self.assertEqual(res.flights[0].flight_number, "QR-0579")
        self.assertEqual(len(res.milestones), 17)
        self.assertEqual(res.milestones[0].status_code, "DLV")
        self.assertTrue(res.milestones[0].is_latest)

    def test_qatar_not_found_handling(self):
        with self.assertRaises(QatarShipmentNotFoundError) as ctx:
            self.qatar_client.track("157-99999999", headless=True)
        self.assertIn("No result found", str(ctx.exception))

    def test_cargoflash_awb_normalization(self):
        prefix, serial, formatted, full_digits = self.cargoflash_client.normalize_awb("077-59060002")
        self.assertEqual(prefix, "077")
        self.assertEqual(serial, "59060002")
        self.assertEqual(formatted, "077-59060002")
        self.assertEqual(full_digits, "07759060002")

        # 8-digit serial input (prefix 077 auto-inferred)
        prefix, serial, formatted, full_digits = self.cargoflash_client.normalize_awb("59060945")
        self.assertEqual(prefix, "077")
        self.assertEqual(serial, "59060945")
        self.assertEqual(formatted, "077-59060945")
        self.assertEqual(full_digits, "07759060945")

    def test_live_cargoflash_tracking_del_lon(self):
        res = self.cargoflash_client.track("077-59060002")
        self.assertEqual(res.formatted_awb, "077-59060002")
        self.assertEqual(res.overview.origin, "DEL")
        self.assertEqual(res.overview.destination, "LON")
        self.assertEqual(res.overview.pieces, 3)
        self.assertEqual(res.overview.gross_weight, 304.0)
        self.assertEqual(res.overview.latest_event_action, "RCF")
        self.assertEqual(res.overview.latest_event_station, "LHR")
        self.assertIn("27-Sep-2026", res.overview.latest_event_time)
        self.assertEqual(len(res.milestone_plan), 8)
        self.assertEqual(len(res.flight_details), 8)
        self.assertEqual(res.flight_details[0].flight_no, "MS-5518")

    def test_live_cargoflash_tracking_del_chi(self):
        res = self.cargoflash_client.track("077-59060945")
        self.assertEqual(res.formatted_awb, "077-59060945")
        self.assertEqual(res.overview.origin, "DEL")
        self.assertEqual(res.overview.destination, "CHI")
        self.assertEqual(res.overview.pieces, 22)
        self.assertEqual(res.overview.gross_weight, 169.0)
        self.assertEqual(res.overview.latest_event_action, "RCF")
        self.assertEqual(res.overview.latest_event_station, "ORD")
        self.assertIn("11-Oct-2026", res.overview.latest_event_time)
        self.assertEqual(len(res.milestone_plan), 13)
        self.assertEqual(len(res.flight_details), 13)
        self.assertEqual(res.flight_details[0].flight_no, "MS-5518")

    def test_cargoflash_not_found_handling(self):
        with self.assertRaises(CargoFlashShipmentNotFoundError) as ctx:
            self.cargoflash_client.track("077-99999999")
        self.assertIn("Could not find shipment for AWB 077-99999999", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
