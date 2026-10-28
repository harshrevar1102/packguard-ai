import io
import csv
from typing import Any
from app.models import Analysis


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitizes values against spreadsheet formula injection (=, +, -, @, tab).
    """
    if value is None:
        return ""
    s = str(value)
    if s.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{s}"
    return s


class CSVExporter:
    @staticmethod
    def generate_csv(analysis: Analysis) -> str:
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header row as specified in Section 8
        headers = [
            "Product Name",
            "Analysis ID",
            "Analysis Timestamp",
            "Finding ID",
            "Field / Issue Name",
            "Specification Value",
            "Artwork Value",
            "Expected Value",
            "Status",
            "Explanation",
            "Specification Filename",
            "Sheet Reference",
            "Cell Reference",
            "Artwork Filename",
            "PDF Page",
            "Artwork Location (BBox)",
            "Recommended Action",
            "Fix Status"
        ]
        writer.writerow(headers)

        for f in analysis.findings:
            spec_file = f.spec_source.filename if f.spec_source else ""
            sheet_ref = f.spec_source.sheet if f.spec_source else ""
            cell_ref = f.spec_source.cell if f.spec_source else ""
            
            art_file = f.artwork_source.filename if f.artwork_source else ""
            art_page = str(f.artwork_source.page) if f.artwork_source else ""
            art_bbox = str(f.artwork_source.bbox) if f.artwork_source and f.artwork_source.bbox else ""

            # Determine Recommended Action
            if f.status.value == "Mismatch":
                if f.safe_fix_available:
                    recommended_action = "Apply safe correction or review typography"
                else:
                    recommended_action = "Manual graphic design correction required"
            elif f.status.value == "Needs Review":
                recommended_action = "Review specification requirement against packaging artwork"
            elif f.status.value == "Match":
                recommended_action = "Verified match — no action required"
            else:
                recommended_action = "Verify if information is required on packaging"

            # Fix status
            if f.safe_fix_available:
                fix_status = "Available (Safe layout verification passed)"
            elif f.fix_explanation:
                fix_status = f"Unavailable: {f.fix_explanation}"
            else:
                fix_status = "N/A"

            row = [
                sanitize_csv_cell(analysis.product_name),
                sanitize_csv_cell(analysis.id),
                sanitize_csv_cell(analysis.timestamp),
                sanitize_csv_cell(f.id),
                sanitize_csv_cell(f.field_name),
                sanitize_csv_cell(f.spec_value),
                sanitize_csv_cell(f.artwork_value),
                sanitize_csv_cell(f.expected_value or ""),
                sanitize_csv_cell(f.status.value),
                sanitize_csv_cell(f.explanation),
                sanitize_csv_cell(spec_file),
                sanitize_csv_cell(sheet_ref),
                sanitize_csv_cell(cell_ref),
                sanitize_csv_cell(art_file),
                sanitize_csv_cell(art_page),
                sanitize_csv_cell(art_bbox),
                sanitize_csv_cell(recommended_action),
                sanitize_csv_cell(fix_status)
            ]
            writer.writerow(row)

        return output.getvalue()
