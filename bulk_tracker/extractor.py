"""
Robust Multi-Source AWB Extractor.
Extracts, cleans, and normalizes AWB numbers from text, lists, CSV files, and Excel spreadsheets.
"""

import io
import re
import csv
from pathlib import Path
from typing import BinaryIO, List, Set, Union
import openpyxl


CARRIER_PREFIXES = {
    "312": ("IndiGo CarGo", "6E"),
    "703": ("Neos Air Cargo", "NO"),
    "077": ("EgyptAir Cargo", "MS"),
    "157": ("Qatar Airways Cargo", "QR"),
    "932": ("Virgin Atlantic Cargo", "VS"),
    "125": ("British Airways Cargo", "BA"),
    "229": ("Kuwait Airways", "KU"),
    "176": ("Emirates SkyCargo", "EK"),
    "020": ("Lufthansa Cargo", "LH"),
    "098": ("Air India Cargo", "AI"),
}

# Extended registry of global IATA airline prefixes for recognition and polite skipping
KNOWN_GLOBAL_IATA_PREFIXES = {
    "065": ("Saudi Arabian Airlines (Saudia Cargo)", "SV"),
    "615": ("DHL Aviation / European Air Transport", "QY"),
    "607": ("Etihad Cargo", "EY"),
    "014": ("Air Canada Cargo", "AC"),
    "016": ("United Airlines Cargo", "UA"),
    "001": ("American Airlines Cargo", "AA"),
    "006": ("Delta Cargo", "DL"),
    "057": ("Air France Cargo", "AF"),
    "074": ("KLM Cargo", "KL"),
    "160": ("Cathay Pacific Cargo", "CX"),
    "217": ("Thai Airways Cargo", "TG"),
    "235": ("Turkish Airlines Cargo", "TK"),
    "180": ("Korean Air Cargo", "KE"),
    "618": ("Singapore Airlines Cargo", "SQ"),
    "081": ("Qantas Freight", "QF"),
    "205": ("All Nippon Airways (ANA Cargo)", "NH"),
    "131": ("Japan Airlines (JAL Cargo)", "JL"),
    "288": ("Air Hong Kong", "LD"),
    "406": ("UPS Air Cargo", "5X"),
    "023": ("FedEx Express", "FX"),
    "042": ("TAP Air Portugal", "TP"),
    "043": ("Dragonair", "KA"),
    "072": ("Gulf Air", "GF"),
    "075": ("Iberia Cargo", "IB"),
    "080": ("LOT Polish Airlines", "LO"),
    "082": ("Brussels Airlines", "SN"),
    "083": ("South African Airways", "SA"),
    "096": ("Iran Air", "IR"),
    "105": ("Finnair Cargo", "AY"),
    "114": ("EL AL Israel Airlines", "LY"),
    "117": ("Scandinavian Airlines (SAS)", "SK"),
    "124": ("Air Algerie", "AH"),
    "139": ("Aeromexico Cargo", "AM"),
    "147": ("Royal Air Maroc", "AT"),
    "230": ("Copa Airlines", "CM"),
    "232": ("Malaysia Airlines Cargo", "MH"),
    "423": ("AirBridgeCargo", "RU"),
    "603": ("SriLankan Airlines", "UL"),
    "724": ("Swiss WorldCargo", "LX"),
    "729": ("Avianca Cargo", "AV"),
    "784": ("China Southern Cargo", "CZ"),
    "999": ("Air China Cargo", "CA"),
}

# Regex for common AWB shapes:
# - 11 digits: '312-92989396', '312 92989396', '31292989396', '312-9298-9396'
# - 8 digits serial: '92989396', '13715800'
AWB_PATTERN = re.compile(
    r"\b\d{3}[-\s]?\d{4}[-\s]?\d{4}\b|"
    r"\b\d{3}[-\s]?\d{7,8}\b|"
    r"\b\d{11}\b|"
    r"\b\d{8}\b"
)


class AWBExtractor:
    """
    Enterprise-grade extractor for air waybills from varied input streams.
    """

    @classmethod
    def clean_awb(cls, raw: str) -> str:
        """
        Cleans an AWB candidate string and formats it as 'PPP-SSSSSSSS' where possible.
        """
        digits = re.sub(r"[^\d]", "", str(raw or "").strip())
        if len(digits) == 11:
            return f"{digits[:3]}-{digits[3:]}"
        elif len(digits) == 8:
            return digits
        elif len(digits) > 11 and digits[:3] in CARRIER_PREFIXES:
            return f"{digits[:3]}-{digits[3:11]}"
        return str(raw).strip()

    @classmethod
    def extract_from_text(cls, text: str) -> List[str]:
        """
        Extracts AWBs from arbitrary string input (comma, newline, space, tab, or mixed).
        Preserves original appearance while removing empty tokens and duplicates.
        """
        if not text:
            return []

        awbs: List[str] = []
        seen: Set[str] = set()

        # Step 1: Direct regex search across the entire text
        for match in AWB_PATTERN.finditer(str(text)):
            candidate = match.group(0)
            digits = re.sub(r"[^\d]", "", candidate)
            if len(digits) in (8, 11):
                cleaned = cls.clean_awb(digits)
                if cleaned not in seen:
                    seen.add(cleaned)
                    awbs.append(cleaned)

        # Step 2: Fallback to token splitting if no regex matches found
        if not awbs:
            tokens = re.split(r"[,;\n\r\t|]+", str(text))
            for tok in tokens:
                digits = re.sub(r"[^\d]", "", tok.strip())
                if len(digits) in (8, 11):
                    cleaned = cls.clean_awb(digits)
                    if cleaned not in seen:
                        seen.add(cleaned)
                        awbs.append(cleaned)

        return awbs

    @classmethod
    def extract_from_csv(cls, file_or_path: Union[str, Path, bytes, BinaryIO]) -> List[str]:
        """
        Extracts AWBs from a CSV file (path, byte buffer, or text buffer).
        Inspects headers or scans every cell automatically.
        """
        if isinstance(file_or_path, (str, Path)):
            with open(file_or_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                content = f.read()
        elif isinstance(file_or_path, bytes):
            content = file_or_path.decode("utf-8-sig", errors="ignore")
        else:
            raw_b = file_or_path.read()
            if isinstance(raw_b, bytes):
                content = raw_b.decode("utf-8-sig", errors="ignore")
            else:
                content = str(raw_b)

        awbs: List[str] = []
        seen: Set[str] = set()

        # Parse CSV
        reader = csv.reader(io.StringIO(content))
        for row in reader:
            for cell in row:
                cell_awbs = cls.extract_from_text(cell)
                for a in cell_awbs:
                    if a not in seen:
                        seen.add(a)
                        awbs.append(a)

        return awbs

    @classmethod
    def extract_from_excel(cls, file_or_path: Union[str, Path, bytes, BinaryIO]) -> List[str]:
        """
        Extracts AWBs from an Excel file (.xlsx or .xlsm).
        Scans all worksheets and cells for AWB number matches.
        """
        if isinstance(file_or_path, (str, Path)):
            wb = openpyxl.load_workbook(file_or_path, data_only=True, read_only=True)
        elif isinstance(file_or_path, bytes):
            wb = openpyxl.load_workbook(io.BytesIO(file_or_path), data_only=True, read_only=True)
        else:
            wb = openpyxl.load_workbook(file_or_path, data_only=True, read_only=True)

        awbs: List[str] = []
        seen: Set[str] = set()

        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                for cell in row:
                    if cell is not None:
                        cell_str = str(cell).strip()
                        extracted = cls.extract_from_text(cell_str)
                        for a in extracted:
                            if a not in seen:
                                seen.add(a)
                                awbs.append(a)

        return awbs

    @classmethod
    def extract_from_any(cls, source: Union[str, Path, bytes, BinaryIO], filename: str = "") -> List[str]:
        """
        High-level dispatcher that detects file format (.xlsx, .csv, .txt, or plain string)
        and extracts all valid AWBs.
        """
        fname = str(filename or "").lower()
        if isinstance(source, (str, Path)) and not filename:
            p = Path(source)
            if p.exists() and p.is_file():
                fname = p.name.lower()

        if fname.endswith((".xlsx", ".xlsm", ".xls")):
            return cls.extract_from_excel(source)
        elif fname.endswith(".csv"):
            return cls.extract_from_csv(source)
        elif isinstance(source, bytes):
            # Check for zip magic number (PK..) indicating an xlsx file
            if source.startswith(b"PK\x03\x04"):
                return cls.extract_from_excel(source)
            try:
                text = source.decode("utf-8-sig", errors="ignore")
                return cls.extract_from_text(text)
            except Exception:
                return []
        else:
            return cls.extract_from_text(str(source))
