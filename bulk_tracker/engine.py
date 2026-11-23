"""
Enterprise Bulk Cargo Tracking Engine.
Coordinates concurrent, resilient, bot-detection-proof tracking across all 10 airline platforms.
Features domain-level concurrency limiting, random jitter, automatic retries, and unified normalization.
"""

import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import Callable, Dict, List, Optional, Tuple, Any

from airindia_tracker.client import AirIndiaCargoClient
from cargoflash_tracker.client import CargoFlashClient, CargoFlashShipmentNotFoundError
from emirates_tracker.client import EmiratesTrackerClient, EmiratesShipmentNotFoundError
from indigo_tracker.client import IndigoCargoClient, IndigoShipmentNotFoundError
from kuwait_tracker.client import KuwaitCargoClient, KuwaitShipmentNotFoundError
from lufthansa_tracker.client import LufthansaCargoClient
from neos_tracker.client import NeosCargoClient, NeosShipmentNotFoundError
from parcels_tracker.client import ParcelsTrackerClient, ParcelsShipmentNotFoundError
from qatar_tracker.client import QatarCargoClient, QatarShipmentNotFoundError
from virgin_tracker.client import VirginCargoClient, VirginShipmentNotFoundError
from turkish_tracker.client import TurkishCargoClient, TurkishShipmentNotFoundError, TurkishTrackingError
from etihad_tracker.client import EtihadCargoClient, EtihadShipmentNotFoundError, EtihadTrackingError

from bulk_tracker.extractor import AWBExtractor, CARRIER_PREFIXES, KNOWN_GLOBAL_IATA_PREFIXES
from bulk_tracker.models import BulkTrackingSummary, UnifiedTrackingRecord
from bulk_tracker.normalizer import CarrierDataNormalizer

logger = logging.getLogger("bulk_tracker")


class BulkCargoTracker:
    """
    Production-ready batch tracking engine.
    - Manages shared carrier clients to avoid redundant connection setup.
    - Limits domain-specific concurrency to prevent triggering airline WAFs and bot detection.
    - Injects polite jitter between consecutive requests to the same platform.
    - Recovers from transient connection resets with automatic backoff.
    """

    def __init__(self, max_global_workers: int = 5, max_domain_workers: int = 2):
        self.max_global_workers = max_global_workers
        self.max_domain_workers = max_domain_workers

        # Singleton carrier clients
        self.clients = {
            "312": IndigoCargoClient(),
            "703": NeosCargoClient(),
            "077": CargoFlashClient(),
            "157": QatarCargoClient(),
            "932": VirginCargoClient(),
            "125": ParcelsTrackerClient(),
            "229": KuwaitCargoClient(),
            "176": EmiratesTrackerClient(),
            "020": LufthansaCargoClient(),
            "098": AirIndiaCargoClient(),
            "235": TurkishCargoClient(),
            "607": EtihadCargoClient(),
        }

        # Domain level locks to prevent hammering any single airline portal
        self._carrier_locks: Dict[str, Lock] = {prefix: Lock() for prefix in CARRIER_PREFIXES}
        self._last_request_time: Dict[str, float] = {prefix: 0.0 for prefix in CARRIER_PREFIXES}

    @staticmethod
    def identify_carrier(awb_input: str) -> Tuple[str, str, str, bool]:
        """
        Identifies carrier prefix, full name, 2-letter code, and active support status.
        Returns (prefix, carrier_name, carrier_code, is_supported).
        """
        digits = "".join(c for c in str(awb_input) if c.isdigit())
        if len(digits) >= 3:
            prefix = digits[:3]
            if prefix in CARRIER_PREFIXES:
                name, code = CARRIER_PREFIXES[prefix]
                return prefix, name, code, True
            if prefix in KNOWN_GLOBAL_IATA_PREFIXES:
                name, code = KNOWN_GLOBAL_IATA_PREFIXES[prefix]
                return prefix, name, code, False
            return prefix, f"IATA Carrier ({prefix})", "XX", False

        if len(digits) == 8:
            # 8 digits serial defaults to IndiGo (SmartKargo)
            return "312", CARRIER_PREFIXES["312"][0], CARRIER_PREFIXES["312"][1], True

        return "UNK", "Unknown Carrier", "XX", False

    def _polite_domain_delay(self, prefix: str):
        """
        Ensures a modest jittered pause between requests to the same airline portal,
        preventing IP blocks and rate limits.
        """
        lock = self._carrier_locks.get(prefix)
        if not lock:
            return

        with lock:
            now = time.time()
            elapsed = now - self._last_request_time.get(prefix, 0.0)
            target_delay = random.uniform(0.15, 0.35)
            if elapsed < target_delay:
                time.sleep(target_delay - elapsed)
            self._last_request_time[prefix] = time.time()

    def track_single(self, raw_awb: str, max_retries: int = 2) -> UnifiedTrackingRecord:
        """
        Tracks a single AWB safely with automatic retry on transient network errors.
        Guarantees a clean UnifiedTrackingRecord is always returned without raising.
        Flags unsupported airline prefixes as SKIPPED.
        Flags unreachable / timed out portals as UNREACHABLE.
        """
        t0 = time.time()
        prefix, carrier_name, carrier_code, is_supported = self.identify_carrier(raw_awb)

        # 1. Immediate Skip for Unsupported IATA Airline Prefixes
        if not is_supported:
            logger.info(f"Skipping AWB {raw_awb}: IATA prefix '{prefix}' ({carrier_name}) is unsupported.")
            return CarrierDataNormalizer.create_error_record(
                raw_awb,
                f"IATA Prefix '{prefix}' ({carrier_name}) is not currently supported - Skipped",
                time.time() - t0,
                prefix=prefix,
                carrier_name=carrier_name,
                carrier_code=carrier_code,
                status_override="SKIPPED",
            )

        # 2. Query Supported Carrier Portals
        for attempt in range(max_retries):
            try:
                self._polite_domain_delay(prefix)

                if prefix == "312":
                    res = self.clients["312"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_indigo(res, raw_awb, time.time() - t0)

                elif prefix == "703":
                    res = self.clients["703"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_neos(res, raw_awb, time.time() - t0)

                elif prefix == "077":
                    res = self.clients["077"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_cargoflash(res, raw_awb, time.time() - t0)

                elif prefix == "157":
                    res = self.clients["157"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_qatar(res, raw_awb, time.time() - t0)

                elif prefix == "932":
                    res = self.clients["932"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_virgin(res, raw_awb, time.time() - t0)

                elif prefix == "125":
                    res = self.clients["125"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_parcels(res, raw_awb, time.time() - t0)

                elif prefix == "229":
                    res = self.clients["229"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_kuwait(res, raw_awb, time.time() - t0)

                elif prefix == "176":
                    res = self.clients["176"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_emirates(res, raw_awb, time.time() - t0)

                elif prefix == "020":
                    res = self.clients["020"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_lufthansa(res, raw_awb, time.time() - t0)

                elif prefix == "098":
                    res = self.clients["098"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_airindia(res, raw_awb, time.time() - t0)

                elif prefix == "235":
                    res = self.clients["235"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_turkish(res, raw_awb, time.time() - t0)

                elif prefix == "607":
                    res = self.clients["607"].track(raw_awb)
                    return CarrierDataNormalizer.normalize_etihad(res, raw_awb, time.time() - t0)

                else:
                    return CarrierDataNormalizer.create_error_record(
                        raw_awb, f"Carrier prefix {prefix} not routed", time.time() - t0, prefix=prefix, carrier_name=carrier_name, carrier_code=carrier_code
                    )

            except (
                IndigoShipmentNotFoundError,
                NeosShipmentNotFoundError,
                CargoFlashShipmentNotFoundError,
                QatarShipmentNotFoundError,
                VirginShipmentNotFoundError,
                ParcelsShipmentNotFoundError,
                KuwaitShipmentNotFoundError,
                EmiratesShipmentNotFoundError,
                TurkishShipmentNotFoundError,
                EtihadShipmentNotFoundError,
            ) as e:
                # Do not retry definitive 404 Not Found responses
                return CarrierDataNormalizer.create_error_record(
                    raw_awb, str(e), time.time() - t0, prefix=prefix, carrier_name=carrier_name, carrier_code=carrier_code
                )
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} tracking {raw_awb} ({carrier_name}) error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    return CarrierDataNormalizer.create_error_record(
                        raw_awb, str(e), time.time() - t0, prefix=prefix, carrier_name=carrier_name, carrier_code=carrier_code
                    )

        return CarrierDataNormalizer.create_error_record(
            raw_awb, "Tracking timed out after multiple retries", time.time() - t0, prefix=prefix, carrier_name=carrier_name, carrier_code=carrier_code
        )

    def track_batch(
        self,
        awb_inputs: List[str],
        progress_callback: Optional[Callable[[int, int, UnifiedTrackingRecord], None]] = None,
    ) -> BulkTrackingSummary:
        """
        Executes concurrent batch tracking across a list of AWBs.
        Calls optional progress_callback(completed, total, record) on each completed shipment.
        Returns a complete BulkTrackingSummary.
        """
        t_batch_start = time.time()
        cleaned_awbs = [AWBExtractor.clean_awb(a) for a in awb_inputs if str(a).strip()]
        total_count = len(cleaned_awbs)

        records_map: Dict[int, UnifiedTrackingRecord] = {}
        completed_count = 0

        # Run with ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_global_workers) as executor:
            future_to_idx = {
                executor.submit(self.track_single, awb): idx
                for idx, awb in enumerate(cleaned_awbs)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    record = future.result()
                except Exception as ex:
                    record = CarrierDataNormalizer.create_error_record(
                        cleaned_awbs[idx], f"Unexpected tracking failure: {ex}", 0.0
                    )

                records_map[idx] = record
                completed_count += 1

                if progress_callback:
                    try:
                        progress_callback(completed_count, total_count, record)
                    except Exception:
                        pass

        # Maintain original order of inputs
        ordered_records = [records_map[i] for i in range(total_count)]

        # Aggregate summary metrics
        total_time = round(time.time() - t_batch_start, 2)
        deliv = sum(1 for r in ordered_records if r.status == "DELIVERED")
        transit = sum(1 for r in ordered_records if r.status in ("IN_TRANSIT", "DEPARTED", "ARRIVED", "BOOKED", "ACCEPTED"))
        not_found = sum(1 for r in ordered_records if r.status == "NOT_FOUND")
        unreachable = sum(1 for r in ordered_records if r.status == "UNREACHABLE")
        skipped = sum(1 for r in ordered_records if r.status == "SKIPPED")
        errors = sum(1 for r in ordered_records if r.status == "ERROR")
        success = sum(1 for r in ordered_records if r.status in ("DELIVERED", "IN_TRANSIT", "DEPARTED", "ARRIVED", "BOOKED", "ACCEPTED"))

        return BulkTrackingSummary(
            total_requested=total_count,
            total_successful=success,
            total_delivered=deliv,
            total_in_transit=transit,
            total_not_found=not_found,
            total_unreachable=unreachable,
            total_skipped=skipped,
            total_errors=errors,
            total_time_sec=total_time,
            records=ordered_records,
        )
