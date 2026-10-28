import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from app.models import ArtworkSource


class PDFTextSpan:
    def __init__(
        self,
        text: str,
        page: int,
        bbox: List[float],
        font_size: float,
        font_name: str,
        color: int,
        flags: int
    ):
        self.text = text
        self.page = page
        self.bbox = bbox  # [x0, y0, x1, y1]
        self.font_size = font_size
        self.font_name = font_name
        self.color = color
        self.flags = flags


class PDFParser:
    @staticmethod
    def extract_spans_and_pages(pdf_path: Path) -> Tuple[List[PDFTextSpan], List[Dict[str, Any]]]:
        """
        Extracts all text spans with exact bounding boxes and page dimensions from a PDF.
        """
        doc = fitz.open(pdf_path)
        all_spans: List[PDFTextSpan] = []
        pages_meta: List[Dict[str, Any]] = []

        for p_idx in range(len(doc)):
            page = doc[p_idx]
            rect = page.rect
            pages_meta.append({
                "page": p_idx + 1,
                "width": rect.width,
                "height": rect.height
            })

            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") == 0:  # text block
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                all_spans.append(PDFTextSpan(
                                    text=text,
                                    page=p_idx + 1,
                                    bbox=list(span.get("bbox", [0, 0, 0, 0])),
                                    font_size=span.get("size", 10.0),
                                    font_name=span.get("font", "Helvetica"),
                                    color=span.get("color", 0),
                                    flags=span.get("flags", 0)
                                ))
        doc.close()
        return all_spans, pages_meta

    @staticmethod
    def extract_full_text(pdf_path: Path) -> str:
        doc = fitz.open(pdf_path)
        text_parts = []
        for p_idx in range(len(doc)):
            page = doc[p_idx]
            text_parts.append(f"--- PAGE {p_idx + 1} ---\n" + page.get_text())
        doc.close()
        return "\n".join(text_parts)

    @staticmethod
    def find_location_in_spans(
        spans: List[PDFTextSpan],
        search_text: str,
        filename: str
    ) -> Optional[ArtworkSource]:
        """
        Fast in-memory lookup over pre-extracted text spans.
        """
        if not search_text or not search_text.strip():
            return None

        clean_search = search_text.strip()
        search_lower = clean_search.lower()

        # 1. Exact match (case-sensitive)
        for s in spans:
            if s.text == clean_search:
                return ArtworkSource(
                    filename=filename,
                    page=s.page,
                    bbox=[round(s.bbox[0], 2), round(s.bbox[1], 2), round(s.bbox[2], 2), round(s.bbox[3], 2)],
                    text=s.text,
                    is_ocr=False,
                    font_size=s.font_size,
                    font_name=s.font_name
                )

        # 2. Case-insensitive substring match
        for s in spans:
            s_lower = s.text.lower()
            if search_lower in s_lower or s_lower in search_lower:
                return ArtworkSource(
                    filename=filename,
                    page=s.page,
                    bbox=[round(s.bbox[0], 2), round(s.bbox[1], 2), round(s.bbox[2], 2), round(s.bbox[3], 2)],
                    text=s.text,
                    is_ocr=False,
                    font_size=s.font_size,
                    font_name=s.font_name
                )

        # 3. Numeric match
        num_match = re.search(r"\d+(?:\.\d+)?", clean_search)
        if num_match:
            num_str = num_match.group(0)
            for s in spans:
                if num_str in s.text:
                    return ArtworkSource(
                        filename=filename,
                        page=s.page,
                        bbox=[round(s.bbox[0], 2), round(s.bbox[1], 2), round(s.bbox[2], 2), round(s.bbox[3], 2)],
                        text=s.text,
                        is_ocr=False,
                        font_size=s.font_size,
                        font_name=s.font_name
                    )

        # 4. Leading words match
        words = clean_search.split()
        if len(words) > 1:
            lead = " ".join(words[:2]).lower()
            for s in spans:
                if lead in s.text.lower():
                    return ArtworkSource(
                        filename=filename,
                        page=s.page,
                        bbox=[round(s.bbox[0], 2), round(s.bbox[1], 2), round(s.bbox[2], 2), round(s.bbox[3], 2)],
                        text=s.text,
                        is_ocr=False,
                        font_size=s.font_size,
                        font_name=s.font_name
                    )

        return None

    @staticmethod
    def find_best_location_for_text(
        pdf_path: Path,
        search_text: str,
        filename: str
    ) -> Optional[ArtworkSource]:
        """
        Extracts spans and finds the best location for text in the PDF.
        """
        spans, _ = PDFParser.extract_spans_and_pages(pdf_path)
        return PDFParser.find_location_in_spans(spans, search_text, filename)

    @staticmethod
    def render_page_image(pdf_path: Path, page_num: int, output_image_path: Path, dpi: int = 150) -> Dict[str, Any]:
        """
        Renders a PDF page to a PNG file and returns metadata.
        page_num is 1-indexed.
        """
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise ValueError(f"Page {page_num} out of range (total pages: {len(doc)})")

        page = doc[page_num - 1]
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        width_pts = page.rect.width
        height_pts = page.rect.height
        pix.save(str(output_image_path))
        doc.close()

        return {
            "page": page_num,
            "width_points": width_pts,
            "height_points": height_pts,
            "width_px": pix.width,
            "height_px": pix.height,
            "dpi": dpi
        }
