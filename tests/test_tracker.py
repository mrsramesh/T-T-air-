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
- Neos Air Cargo / World Cargo Solutions (703)
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
from neos_tracker.client import NeosCargoClient, NeosShipmentNotFoundError
from indigo_tracker.client import IndigoCargoClient, IndigoShipmentNotFoundError
import io
import openpyxl
from bulk_tracker import (
    AWBExtractor,
    CarrierDataNormalizer,
    ExcelReportExporter,
    CSVReportExporter,
    BulkCargoTracker,
    UnifiedTrackingRecord,
    BulkTrackingSummary,
)


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
        self.neos_client = NeosCargoClient()
        self.indigo_client = IndigoCargoClient()

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

    def test_neos_awb_normalization(self):
        prefix, serial, formatted, full_digits = self.neos_client.normalize_awb("703-13715800")
        self.assertEqual(prefix, "703")
        self.assertEqual(serial, "13715800")
        self.assertEqual(formatted, "703-13715800")
        self.assertEqual(full_digits, "70313715800")

        # Serial only (prefix 703 auto-inferred)
        prefix, serial, formatted, full_digits = self.neos_client.normalize_awb("13715332")
        self.assertEqual(prefix, "703")
        self.assertEqual(serial, "13715332")
        self.assertEqual(formatted, "703-13715332")
        self.assertEqual(full_digits, "70313715332")

    def test_live_neos_tracking_del_kwi(self):
        res = self.neos_client.track("703-13715800")
        self.assertEqual(res.formatted_awb, "703-13715800")
        self.assertEqual(res.overview.origin, "DEL")
        self.assertEqual(res.overview.destination, "KWI")
        self.assertEqual(res.overview.pieces, 69)
        self.assertEqual(res.overview.commodity, "READY MADE GARM")
        self.assertIn("1535", res.overview.gross_weight or "")
        self.assertEqual(res.overview.latest_event_code, "DLV")
        self.assertEqual(len(res.flights), 1)
        self.assertEqual(res.flights[0].flight_no, "J9410/15NOV26")
        self.assertEqual(len(res.milestones), 10)
        self.assertEqual(res.milestones[0].status_code, "DLV")
        self.assertTrue(res.milestones[0].is_latest)

    def test_live_neos_tracking_del_jed(self):
        res = self.neos_client.track("703-13715332")
        self.assertEqual(res.formatted_awb, "703-13715332")
        self.assertEqual(res.overview.origin, "DEL")
        self.assertEqual(res.overview.destination, "JED")
        self.assertEqual(res.overview.pieces, 40)
        self.assertEqual(res.overview.commodity, "FEEDING BOTTLES")
        self.assertIn("641", res.overview.gross_weight or "")
        self.assertEqual(res.overview.latest_event_code, "DLV")
        self.assertEqual(len(res.flights), 2)
        self.assertEqual(res.flights[0].flight_no, "XY907/25OCT26")
        self.assertEqual(res.flights[1].flight_no, "XY419/26OCT26")
        self.assertEqual(len(res.milestones), 32)
        self.assertEqual(res.milestones[0].status_code, "DLV")
        self.assertTrue(res.milestones[0].is_latest)

    def test_neos_not_found_handling(self):
        with self.assertRaises(NeosShipmentNotFoundError) as ctx:
            self.neos_client.track("703-99999999")
        self.assertIn("Could not find shipment for AWB 703-99999999", str(ctx.exception))

    def test_indigo_awb_normalization(self):
        prefix, serial, formatted, full_digits = self.indigo_client.normalize_awb("312-9298-9396")
        self.assertEqual(prefix, "312")
        self.assertEqual(serial, "92989396")
        self.assertEqual(formatted, "312-92989396")
        self.assertEqual(full_digits, "31292989396")

        # Serial only (prefix 312 auto-inferred)
        prefix, serial, formatted, full_digits = self.indigo_client.normalize_awb("92989396")
        self.assertEqual(prefix, "312")
        self.assertEqual(serial, "92989396")
        self.assertEqual(formatted, "312-92989396")
        self.assertEqual(full_digits, "31292989396")

    def test_live_indigo_tracking_bom_bkk(self):
        res = self.indigo_client.track("312-9298-9396")
        self.assertEqual(res.formatted_awb, "312-92989396")
        self.assertEqual(res.overview.origin, "BOM")
        self.assertEqual(res.overview.destination, "BKK")
        self.assertEqual(res.overview.pieces, 62)
        self.assertEqual(res.overview.gross_weight, "898.00 Kgs")
        self.assertEqual(res.overview.current_status, "Delivered at BKK")
        self.assertEqual(res.overview.issued_to, "ESSILOR MANUFACTURING THAILAND")
        self.assertEqual(len(res.booking_info), 2)
        self.assertEqual(res.booking_info[0].status, "Booked")
        self.assertEqual(res.booking_info[1].status, "Accepted")
        self.assertEqual(len(res.status_history), 4)
        self.assertEqual(res.status_history[-1].milestone, "Delivered")
        self.assertTrue(res.status_history[-1].is_latest)
        self.assertEqual(len(res.delivery_orders), 1)
        self.assertEqual(res.delivery_orders[0].do_number, "DO-BKK-14774813")
        self.assertEqual(res.delivery_orders[0].issued_to, "ESSILOR MANUFACTURING THAILAND")

    def test_indigo_not_found_handling(self):
        with self.assertRaises(IndigoShipmentNotFoundError) as ctx:
            self.indigo_client.track("312-99999999")
        self.assertIn("Could not find shipment for AWB 312-99999999", str(ctx.exception))

    def test_awb_extractor_various_formats(self):
        text = """
        Tracking List:
        312-9298-9396, 703 13715800; 07759060002
        157-5366-1580 | 125-24128344
        229-18148900
        Random string 12345
        312-92989396 (duplicate of first)
        """
        extracted = AWBExtractor.extract_from_text(text)
        self.assertIn("312-92989396", extracted)
        self.assertIn("703-13715800", extracted)
        self.assertIn("077-59060002", extracted)
        self.assertIn("157-53661580", extracted)
        self.assertIn("125-24128344", extracted)
        self.assertIn("229-18148900", extracted)
        # Check deduplication
        awb_keys = [a.replace("-", "").replace(" ", "") for a in extracted]
        self.assertEqual(len(awb_keys), len(set(awb_keys)))

    def test_awb_extractor_from_excel(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Shipments"
        ws.append(["AWB Header", "Notes"])
        ws.append(["312-9298-9396", "IndiGo"])
        ws.append(["703-13715800", "Neos Air"])
        
        ws2 = wb.create_sheet(title="More")
        ws2.append(["ID", "077-59060002"])

        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        extracted = AWBExtractor.extract_from_excel(buf)
        self.assertIn("312-92989396", extracted)
        self.assertIn("703-13715800", extracted)
        self.assertIn("077-59060002", extracted)

    def test_excel_and_csv_report_generation(self):
        record1 = UnifiedTrackingRecord(
            awb="312-92989396",
            raw_input="312-9298-9396",
            carrier_prefix="312",
            carrier_name="IndiGo CarGo (6E)",
            carrier_code="6E",
            status="DELIVERED",
            status_detail="Delivered at BKK",
            origin="BOM",
            destination="BKK",
            route="BOM ➔ BKK",
            pieces=62,
            weight="898.00 Kgs",
            flight_details="6E1087 / 08/11/2026",
            latest_activity="Delivered at BKK",
            latest_location="BKK",
            execution_time_sec=0.45,
        )
        record2 = UnifiedTrackingRecord(
            awb="703-99999999",
            raw_input="703-9999-9999",
            carrier_prefix="703",
            carrier_name="Neos Air Cargo (NO)",
            carrier_code="NO",
            status="NOT_FOUND",
            status_detail="Shipment not found",
            error_message="Shipment not found in system",
            execution_time_sec=0.32,
        )

        records = [record1, record2]
        
        # Test Excel Export
        excel_bytes = ExcelReportExporter.export_to_bytes(records)
        self.assertGreater(len(excel_bytes), 1000)
        
        # Verify Excel can be re-opened and has 2 sheets
        wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
        self.assertIn("Shipments Tracking", wb.sheetnames)
        self.assertIn("Summary & KPIs", wb.sheetnames)

        # Test CSV Export
        csv_bytes = CSVReportExporter.export_to_bytes(records)
        csv_str = csv_bytes.decode("utf-8")
        self.assertIn("312-92989396", csv_str)
        self.assertIn("DELIVERED", csv_str)
        self.assertIn("703-99999999", csv_str)
        self.assertIn("NOT_FOUND", csv_str)

    def test_bulk_cargo_tracker_batch_run(self):
        from unittest.mock import MagicMock
        from indigo_tracker.models import IndigoTrackingResult, IndigoOverview

        tracker = BulkCargoTracker(max_global_workers=2)
        
        # Mock successful tracking for first AWB and not found for second
        mock_overview = IndigoOverview(
            awb_number="31292989396",
            formatted_awb="312-92989396",
            origin="BOM",
            destination="BKK",
            gross_weight="898.00 Kgs",
            pieces=62,
            current_status="Delivered at BKK",
            latest_activity="Delivered at BKK",
            issued_to="ESSILOR MANUFACTURING THAILAND",
            flight_no="6E1087",
        )
        mock_resp = IndigoTrackingResult(
            awb="31292989396",
            awb_prefix="312",
            awb_serial="92989396",
            formatted_awb="312-92989396",
            overview=mock_overview,
            booking_info=[],
            status_history=[],
            delivery_orders=[],
        )

        def mock_track(awb):
            if "9298" in str(awb):
                return mock_resp
            raise IndigoShipmentNotFoundError(f"Could not find shipment for AWB {awb}")

        tracker.clients["312"].track = MagicMock(side_effect=mock_track)

        summary = tracker.track_batch(["312-9298-9396", "312-99999999"])
        self.assertEqual(summary.total_requested, 2)
        self.assertEqual(summary.total_successful, 1)
        self.assertEqual(summary.total_not_found, 1)
        self.assertEqual(summary.total_delivered, 1)

    def test_fastapi_bulk_and_export_endpoints(self):
        from fastapi.testclient import TestClient
        import server

        client = TestClient(server.app)

        payload = {
            "records": [
                {
                    "awb": "312-92989396",
                    "raw_input": "312-9298-9396",
                    "carrier_prefix": "312",
                    "carrier_name": "IndiGo CarGo (6E)",
                    "carrier_code": "6E",
                    "status": "DELIVERED",
                    "status_detail": "Delivered at BKK",
                    "origin": "BOM",
                    "destination": "BKK",
                    "route": "BOM ➔ BKK",
                    "pieces": 62,
                    "weight": "898.00 Kgs",
                    "execution_time_sec": 0.45,
                }
            ]
        }
        res_excel = client.post("/api/v1/export/excel", json=payload)
        self.assertEqual(res_excel.status_code, 200)
        self.assertGreater(len(res_excel.content), 1000)

        res_csv = client.post("/api/v1/export/csv", json=payload)
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("312-92989396", res_csv.text)

        res_health = client.get("/health")
        self.assertEqual(res_health.status_code, 200)
        self.assertEqual(len(res_health.json()["carriers"]), 10)

    def test_unsupported_prefix_skipping(self):
        tracker = BulkCargoTracker(max_global_workers=2)
        # Test 065 (Saudia Cargo) and 615 (DHL Aviation)
        rec1 = tracker.track_single("065-38891834")
        self.assertEqual(rec1.status, "SKIPPED")
        self.assertIn("Saudi Arabian Airlines", rec1.carrier_name)
        self.assertIn("Skipped", rec1.status_detail)

        rec2 = tracker.track_single("615-63964714")
        self.assertEqual(rec2.status, "SKIPPED")
        self.assertIn("DHL Aviation", rec2.carrier_name)
        self.assertIn("Skipped", rec2.status_detail)

    def test_unreachable_portal_flagging(self):
        tracker = BulkCargoTracker(max_global_workers=1)
        err_rec = CarrierDataNormalizer.create_error_record(
            "077-59068973",
            "Failed to resolve 'msres.cargoflash.com' (NameResolutionError): Connection timed out",
            0.12,
            prefix="077",
            carrier_name="EgyptAir Cargo (MS)",
        )
        self.assertEqual(err_rec.status, "UNREACHABLE")
        self.assertIn("timed out", err_rec.error_message.lower())


if __name__ == "__main__":
    unittest.main()
