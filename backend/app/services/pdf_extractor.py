"""Artwork PDF extraction: text layer via PyMuPDF, OCR via Tesseract (only when needed)."""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

import pymupdf

from app.config import settings
from app.services.text_utils import collapse

log = logging.getLogger(__name__)
BBox = tuple  # (x0, y0, x1, y1) in PDF points


class ProcessingError(Exception):
    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class TextBlock:
    bbox: BBox
    text: str


@dataclass
class OcrWord:
    text: str
    conf: float
    bbox: BBox


@dataclass
class OcrResult:
    words: list = field(default_factory=list)
    error: Optional[str] = None
    mean_conf: Optional[float] = None


@dataclass
class PageData:
    number: int  # 1-based
    width: float
    height: float
    text: str
    blocks: list
    image_count: int = 0
    text_source: str = "text_layer"  # "text_layer" | "ocr" | "none"
    ocr_confidence: Optional[float] = None
    preview_data_url: Optional[str] = None


class ArtworkData:
    """Extracted artwork. OCR and bbox lookup are injected so comparison engine stays pure and testable."""

    def __init__(
        self,
        pages: list[PageData],
        ocr_provider: Optional[Callable[[int], OcrResult]] = None,
        locator: Optional[Callable[[int, str], list]] = None,
        font_lookup: Optional[Callable[[int, list], tuple]] = None,
        closer: Optional[Callable[[], None]] = None,
    ):
        self.pages = pages
        self._ocr_provider = ocr_provider
        self._locator = locator
        self._font_lookup = font_lookup
        self._closer = closer
        self._ocr_cache: dict[int, OcrResult] = {}

    def page(self, number: int) -> PageData:
        return self.pages[number - 1]

    def ocr(self, number: int) -> OcrResult:
        if number not in self._ocr_cache:
            self._ocr_cache[number] = (
                self._ocr_provider(number) if self._ocr_provider else OcrResult(error="OCR is not available.")
            )
        return self._ocr_cache[number]

    @property
    def ocr_pages_run(self) -> list[int]:
        return sorted(self._ocr_cache)

    def locate(self, number: int, needle: str) -> list:
        if not self._locator:
            return []
        try:
            return self._locator(number, needle)
        except Exception:
            return []

    def get_font_info(self, number: int, bbox: list) -> tuple[float, str]:
        if not self._font_lookup:
            return 11.0, "Helvetica"
        try:
            return self._font_lookup(number, bbox)
        except Exception:
            return 11.0, "Helvetica"

    def close(self) -> None:
        if self._closer:
            self._closer()


def ocr_available() -> bool:
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _run_ocr(page: "pymupdf.Page") -> OcrResult:
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return OcrResult(error="OCR libraries (pytesseract/Pillow) are not installed.")
    try:
        rect = page.rect
        scale = min(2.0, 4000.0 / max(rect.width, rect.height, 1))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        d = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, timeout=settings.ocr_timeout_s)
    except pytesseract.TesseractNotFoundError:
        return OcrResult(error="OCR engine (Tesseract) is not installed on the server.")
    except Exception as exc:
        log.warning("OCR failed: %s", type(exc).__name__)
        return OcrResult(error="OCR failed for this page.")
    words = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        try:
            conf = float(d["conf"][i])
        except (TypeError, ValueError):
            continue
        if not t or conf < 0:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        words.append(
            (
                OcrWord(t, conf, (x / scale, y / scale, (x + w) / scale, (y + h) / scale)),
                (d["block_num"][i], d["par_num"][i], d["line_num"][i]),
            )
        )
    mean = sum(w.conf for w, _ in words) / len(words) if words else None
    res = OcrResult(words=[w for w, _ in words], mean_conf=mean)
    res._lines = [k for _, k in words]  # type: ignore[attr-defined]
    return res


def _ocr_to_blocks(res: OcrResult):
    """Rebuild text + blocks from OCR words (used when a page has no usable text layer)."""
    lines: dict = {}
    for w, k in zip(res.words, getattr(res, "_lines", [])):
        lines.setdefault(k, []).append(w)
    blocks: dict = {}
    for (b, p, ln), ws in lines.items():
        blocks.setdefault((b, p), []).append((ln, ws))
    out_blocks, texts = [], []
    for _, ls in sorted(blocks.items()):
        ltxt, xs0, ys0, xs1, ys1 = [], [], [], [], []
        for _ln, ws in sorted(ls, key=lambda x: x[0]):
            ltxt.append(" ".join(w.text for w in ws))
            xs0 += [w.bbox[0] for w in ws]
            ys0 += [w.bbox[1] for w in ws]
            xs1 += [w.bbox[2] for w in ws]
            ys1 += [w.bbox[3] for w in ws]
        t = "\n".join(ltxt)
        texts.append(t)
        out_blocks.append(TextBlock((min(xs0), min(ys0), max(xs1), max(ys1)), t))
    return "\n".join(texts), out_blocks


def extract_pdf(data_or_path: Union[bytes, Path, str], with_previews: bool = True) -> ArtworkData:
    try:
        if isinstance(data_or_path, (Path, str)):
            doc = pymupdf.open(str(data_or_path))
        else:
            doc = pymupdf.open(stream=data_or_path, filetype="pdf")
    except Exception as exc:
        raise ProcessingError(
            "The artwork file could not be opened as a PDF. The file may be corrupted or not a real PDF."
        ) from exc
    try:
        if doc.needs_pass:
            raise ProcessingError("The artwork PDF is password-protected and cannot be read.")
        if doc.page_count == 0:
            raise ProcessingError("The artwork PDF contains no pages.")
        if doc.page_count > settings.max_pdf_pages:
            raise ProcessingError(
                f"The artwork PDF has {doc.page_count} pages; configured limit is {settings.max_pdf_pages}."
            )
        pages: list[PageData] = []
        auto_ocr: list[int] = []
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text("text") or ""
            blocks = [
                TextBlock((b[0], b[1], b[2], b[3]), b[4])
                for b in page.get_text("blocks")
                if len(b) >= 7 and b[6] == 0 and (b[4] or "").strip()
            ]
            preview = None
            if with_previews:
                try:
                    scale = min(1.5, 2200.0 / max(page.rect.width, page.rect.height, 1))
                    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
                    try:
                        raw = pix.tobytes("jpeg", jpg_quality=82)
                    except TypeError:
                        raw = pix.tobytes("jpeg")
                    preview = "data:image/jpeg;base64," + base64.b64encode(raw).decode()
                except Exception:
                    preview = None
            pd = PageData(
                number=i + 1,
                width=float(page.rect.width),
                height=float(page.rect.height),
                text=text,
                blocks=blocks,
                image_count=len(page.get_images()),
                text_source="text_layer" if len(text.strip()) >= settings.min_text_chars else "none",
                preview_data_url=preview,
            )
            pages.append(pd)
            if pd.text_source == "none":
                auto_ocr.append(i)

        def locator(number: int, needle: str) -> list:
            needle = " ".join(needle.split())
            if not needle or len(needle) > 300:
                return []
            return [[round(r.x0, 2), round(r.y0, 2), round(r.x1, 2), round(r.y1, 2)] for r in doc[number - 1].search_for(needle)][:12]

        def font_lookup(number: int, bbox: list) -> tuple[float, str]:
            if not bbox or len(bbox) < 4:
                return 11.0, "Helvetica"
            page = doc[number - 1]
            bx0, by0, bx1, by1 = bbox[:4]
            page_dict = page.get_text("dict")
            for block in page_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            sb = span.get("bbox", [0, 0, 0, 0])
                            # Overlap check
                            if not (sb[2] < bx0 or sb[0] > bx1 or sb[3] < by0 or sb[1] > by1):
                                return float(span.get("size", 11.0)), str(span.get("font", "Helvetica"))
            return 11.0, "Helvetica"

        art = ArtworkData(
            pages,
            ocr_provider=lambda n: _run_ocr(doc[n - 1]),
            locator=locator,
            font_lookup=font_lookup,
            closer=doc.close,
        )
    except Exception:
        doc.close()
        raise

    # Pages without a usable text layer: OCR them now
    for i in auto_ocr:
        res = art.ocr(i + 1)
        pg = pages[i]
        if res.error or not res.words:
            pg.text_source = "none"
            continue
        ocr_text, ocr_blocks = _ocr_to_blocks(res)
        if len(ocr_text.strip()) <= len(pg.text.strip()) and pg.text.strip():
            pg.text_source = "text_layer"
            continue
        pg.text, pg.blocks = ocr_text, ocr_blocks
        pg.text_source = "ocr"
        pg.ocr_confidence = res.mean_conf
    return art
