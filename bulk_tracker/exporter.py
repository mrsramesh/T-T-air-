"""
Multi-Carrier Tracking Exporter.
Exports UnifiedTrackingRecord collections to beautifully styled Excel (.xlsx) workbooks and CSV files.
"""

import io
import csv
from datetime import datetime
from typing import List, Optional
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from bulk_tracker.models import UnifiedTrackingRecord, BulkTrackingSummary


class ExcelReportExporter:
    """
    Produces executive-grade Excel spreadsheets with airline styling, status conditional fills,
    zebra striping, auto-filter, and frozen headers.
    """

    # Palette
    NAVY_HEADER = "1E3A8A"
    WHITE = "FFFFFF"
    ZEBRA_BG = "F8FAFC"
    BORDER_COLOR = "CBD5E1"

    # Status fills and font colors
    STATUS_COLORS = {
        "DELIVERED": ("DEF7EC", "03543F"),     # Soft green
        "ARRIVED": ("E1EFFE", "1E429F"),       # Soft blue
        "DEPARTED": ("FEF08A", "713F12"),      # Soft amber
        "IN_TRANSIT": ("FEF08A", "713F12"),    # Soft amber
        "BOOKED": ("E1EFFE", "1E429F"),        # Soft blue
        "ACCEPTED": ("E1EFFE", "1E429F"),      # Soft blue
        "NOT_FOUND": ("FFEDD5", "9A3412"),     # Soft orange
        "ERROR": ("FDE8E8", "9B1C1C"),         # Soft red
    }

    @classmethod
    def export_workbook(cls, records: List[UnifiedTrackingRecord], summary: Optional[BulkTrackingSummary] = None) -> openpyxl.Workbook:
        wb = openpyxl.Workbook()

        # ==========================================
        # Sheet 1: Shipments Tracking
        # ==========================================
        ws = wb.active
        ws.title = "Shipments Tracking"
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "#",
            "AWB Number",
            "Carrier",
            "Prefix",
            "Status",
            "Origin",
            "Destination",
            "Route",
            "Pieces",
            "Gross Weight",
            "Flight Details",
            "Latest Activity",
            "Latest Location",
            "Consignee / Release Party",
            "Time (s)",
            "Status Detail / Error",
        ]

        ws.append(headers)

        header_font = Font(name="Calibri", size=11, bold=True, color=cls.WHITE)
        header_fill = PatternFill(start_color=cls.NAVY_HEADER, end_color=cls.NAVY_HEADER, fill_type="solid")
        header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

        thin_side = Side(border_style="thin", color=cls.BORDER_COLOR)
        grid_border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)

        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            cell.border = grid_border

        ws.row_dimensions[1].height = 28

        # Data rows
        zebra_fill = PatternFill(start_color=cls.ZEBRA_BG, end_color=cls.ZEBRA_BG, fill_type="solid")
        default_font = Font(name="Calibri", size=10)

        for idx, rec in enumerate(records, start=1):
            row_num = idx + 1
            row_data = [
                idx,
                rec.awb,
                rec.carrier_name,
                rec.carrier_prefix,
                rec.status,
                rec.origin,
                rec.destination,
                rec.route,
                rec.pieces if rec.pieces is not None else "---",
                rec.weight or "---",
                rec.flight_details or "---",
                rec.latest_activity or "---",
                rec.latest_location or "---",
                rec.consignee_issued_to or "---",
                rec.execution_time_sec,
                rec.error_message if rec.error_message else rec.status_detail,
            ]
            ws.append(row_data)

            is_zebra = (idx % 2 == 0)
            ws.row_dimensions[row_num].height = 20

            # Row styling
            for col_num in range(1, len(headers) + 1):
                c = ws.cell(row=row_num, column=col_num)
                c.font = default_font
                c.border = grid_border
                c.alignment = Alignment(vertical="center")

                # Center align code/number fields
                if col_num in (1, 4, 6, 7, 8, 9, 15):
                    c.alignment = Alignment(horizontal="center", vertical="center")

                # Zebra shading for non-status cells
                if is_zebra and col_num != 5:
                    c.fill = zebra_fill

                # Special Status Column Formatting (Col 5)
                if col_num == 5:
                    bg, text_color = cls.STATUS_COLORS.get(rec.status, ("F1F5F9", "334155"))
                    c.fill = PatternFill(start_color=bg, end_color=bg, fill_type="solid")
                    c.font = Font(name="Calibri", size=10, bold=True, color=text_color)
                    c.alignment = Alignment(horizontal="center", vertical="center")

        # Auto-fit column widths
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val = str(cell.value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 11)

        # Freeze header row and add auto-filter
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

        # ==========================================
        # Sheet 2: Summary & KPIs
        # ==========================================
        ws2 = wb.create_sheet(title="Summary & KPIs")
        ws2.views.sheetView[0].showGridLines = True

        ws2.column_dimensions["A"].width = 28
        ws2.column_dimensions["B"].width = 30

        total_req = len(records)
        deliv = sum(1 for r in records if r.status == "DELIVERED")
        transit = sum(1 for r in records if r.status in ("IN_TRANSIT", "DEPARTED", "ARRIVED", "BOOKED", "ACCEPTED"))
        errs = sum(1 for r in records if r.status in ("ERROR", "NOT_FOUND"))
        tot_time = round(sum(r.execution_time_sec for r in records), 2)

        summary_rows = [
            ("Metric", "Value"),
            ("Total Shipments Tracked", total_req),
            ("Delivered (POD)", deliv),
            ("In Transit / Active", transit),
            ("Not Found / Errors", errs),
            ("Total Processing Time (s)", f"{tot_time}s"),
            ("Average Time per AWB", f"{round(tot_time / total_req, 2)}s" if total_req else "0s"),
            ("Report Generated At", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ]

        for r_idx, (m_label, m_val) in enumerate(summary_rows, start=1):
            ws2.append([m_label, m_val])
            cell_a = ws2.cell(row=r_idx, column=1)
            cell_b = ws2.cell(row=r_idx, column=2)
            cell_a.border = grid_border
            cell_b.border = grid_border
            if r_idx == 1:
                cell_a.fill = header_fill
                cell_a.font = header_font
                cell_b.fill = header_fill
                cell_b.font = header_font
            else:
                cell_a.font = Font(name="Calibri", size=10, bold=True)
                cell_b.font = Font(name="Calibri", size=10)
                if r_idx % 2 == 0:
                    cell_a.fill = zebra_fill
                    cell_b.fill = zebra_fill

        return wb

    @classmethod
    def export_to_bytes(cls, records: List[UnifiedTrackingRecord], summary: Optional[BulkTrackingSummary] = None) -> bytes:
        wb = cls.export_workbook(records, summary)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    @classmethod
    def save_to_file(cls, records: List[UnifiedTrackingRecord], file_path: str, summary: Optional[BulkTrackingSummary] = None) -> str:
        wb = cls.export_workbook(records, summary)
        wb.save(file_path)
        return file_path


class CSVReportExporter:
    """
    Exports unified records to clean UTF-8 CSV with Excel-compatible BOM.
    """

    @classmethod
    def export_to_string(cls, records: List[UnifiedTrackingRecord]) -> str:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "AWB Number",
            "Carrier",
            "Prefix",
            "Status",
            "Origin",
            "Destination",
            "Route",
            "Pieces",
            "Weight",
            "Flight Details",
            "Latest Activity",
            "Latest Location",
            "Consignee / Release Party",
            "Time (s)",
            "Status Detail / Error",
        ])

        for r in records:
            writer.writerow([
                r.awb,
                r.carrier_name,
                r.carrier_prefix,
                r.status,
                r.origin,
                r.destination,
                r.route,
                r.pieces if r.pieces is not None else "",
                r.weight or "",
                r.flight_details or "",
                r.latest_activity or "",
                r.latest_location or "",
                r.consignee_issued_to or "",
                r.execution_time_sec,
                r.error_message if r.error_message else r.status_detail,
            ])

        return output.getvalue()

    @classmethod
    def export_to_bytes(cls, records: List[UnifiedTrackingRecord]) -> bytes:
        content = cls.export_to_string(records)
        return content.encode("utf-8-sig")

    @classmethod
    def save_to_file(cls, records: List[UnifiedTrackingRecord], file_path: str) -> str:
        b = cls.export_to_bytes(records)
        with open(file_path, "wb") as f:
            f.write(b)
        return file_path
