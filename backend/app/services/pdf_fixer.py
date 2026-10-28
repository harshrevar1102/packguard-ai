import uuid
import shutil
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import fitz
from app.models import Finding, ArtworkVersion
from app.services.pdf_parser import PDFParser


import re
from app.services.text_utils import collapse


class PDFFixer:
    @staticmethod
    def create_candidate_fix(
        source_pdf_path: Path,
        candidate_pdf_path: Path,
        finding: Finding
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Creates a temporary candidate PDF with the corrected text applied.
        Renders the candidate page for visual inspection.
        Does NOT alter the original source PDF.
        Supports both single-line and multi-line paragraph text wrapping.
        """
        replacement = finding.suggested_replacement or finding.spec_value or finding.reference_value
        orig_text = finding.original_text_to_replace or finding.artwork_value

        if not replacement or not str(replacement).strip():
            return False, "Specification value is empty.", None

        page_num = 1
        bbox = None
        font_size = 11.0
        font_name = "helv"

        if finding.artwork_source:
            page_num = finding.artwork_source.page or 1
            if finding.artwork_source.bbox and len(finding.artwork_source.bbox) >= 4:
                bbox = finding.artwork_source.bbox
            font_size = finding.artwork_source.font_size or 11.0
            font_name = finding.artwork_source.font_name or "helv"

        try:
            candidate_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            doc = fitz.open(source_pdf_path)
            
            # If bbox is missing, search for artwork text or words across pages
            if not bbox:
                search_targets = [orig_text[:40]] if orig_text else []
                if orig_text and len(orig_text) > 40:
                    search_targets.append(orig_text[:20])
                for p_idx in range(len(doc)):
                    p = doc[p_idx]
                    for st in search_targets:
                        hits = p.search_for(st)
                        if hits:
                            bbox = [hits[0].x0, hits[0].y0, hits[0].x1, hits[0].y1]
                            page_num = p_idx + 1
                            break
                    if bbox:
                        break

            if not bbox or len(bbox) < 4:
                doc.close()
                return False, "Target text location coordinates could not be isolated on the artwork PDF.", None

            if page_num < 1 or page_num > len(doc):
                doc.close()
                return False, f"Invalid page number {page_num}", None

            page = doc[page_num - 1]
            rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])

            # Map standard font names to fitz supported base fonts
            base_font = "helv"
            f_lower = font_name.lower()
            if "bold" in f_lower and "italic" in f_lower:
                base_font = "hebi"
            elif "bold" in f_lower:
                base_font = "hebo"
            elif "italic" in f_lower:
                base_font = "heit"
            elif "times" in f_lower:
                base_font = "times"
            elif "courier" in f_lower:
                base_font = "couri"

            # 1. Redact the old text area with clean white fill
            page.add_redact_annot(rect, fill=(1, 1, 1))
            page.apply_redactions()

            # 2. Insert new replacement text
            # Multi-line / paragraph check: use insert_textbox with text-wrapping
            is_multiline = (rect.height > font_size * 1.5) or (len(str(replacement)) > 35) or ("\n" in str(replacement))
            
            if is_multiline:
                # Insert inside bounded textbox with dynamic font scaling to fit cleanly
                f_sz = font_size
                rc = page.insert_textbox(
                    rect,
                    str(replacement),
                    fontsize=f_sz,
                    fontname=base_font,
                    color=(0, 0, 0)
                )
                # If negative return (text deficit / overflow), scale font down until it fits
                while rc < 0 and f_sz >= 3.5:
                    f_sz -= 0.3
                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()
                    rc = page.insert_textbox(
                        rect,
                        str(replacement),
                        fontsize=f_sz,
                        fontname=base_font,
                        color=(0, 0, 0)
                    )
            else:
                # Single-line text on baseline
                baseline_y = max(rect.y0 + font_size * 0.8, rect.y1 - 2)
                page.insert_text(
                    fitz.Point(rect.x0, baseline_y),
                    str(replacement),
                    fontsize=font_size,
                    fontname=base_font,
                    color=(0, 0, 0)
                )

            # Save to temporary candidate PDF
            doc.save(candidate_pdf_path)
            doc.close()

            # Verify replacement appears in resulting PDF
            verify_doc = fitz.open(candidate_pdf_path)
            verify_text = verify_doc[page_num - 1].get_text()
            verify_doc.close()

            c_rep = collapse(str(replacement))
            c_ver = collapse(verify_text)
            if c_rep not in c_ver and str(replacement).strip() not in verify_text:
                # Check if key words appear
                words = [w for w in re.split(r'[\s,.;:()]+', str(replacement)) if len(w) > 3]
                if words and not any(w in verify_text for w in words):
                    return False, "Candidate verification failed — replacement text was not detected in output PDF.", None

            # Render candidate page image for browser preview
            preview_img_path = candidate_pdf_path.parent / f"preview_candidate_p{page_num}.png"
            render_meta = PDFParser.render_page_image(
                candidate_pdf_path,
                page_num=page_num,
                output_image_path=preview_img_path
            )

            return True, "Candidate correction generated successfully.", {
                "candidate_pdf_path": str(candidate_pdf_path),
                "preview_image_path": str(preview_img_path),
                "page": page_num,
                "replacement": str(replacement),
                "render_meta": render_meta
            }

        except Exception as e:
            import traceback
            traceback.print_exc()
            return False, f"Error applying candidate fix: {str(e)}", None

    @staticmethod
    def commit_version(
        product_versions_dir: Path,
        candidate_pdf_path: Path,
        finding_id: str,
        description: str,
        version_count: int
    ) -> ArtworkVersion:
        """
        Commits an approved candidate correction into a persistent, immutable saved version.
        Never overwrites the original uploaded PDF.
        """
        product_versions_dir.mkdir(parents=True, exist_ok=True)
        version_id = f"v{version_count + 1}_{uuid.uuid4().hex[:6]}"
        version_filename = f"{version_id}.pdf"
        target_path = product_versions_dir / version_filename

        shutil.copy2(candidate_pdf_path, target_path)

        from datetime import datetime, timezone
        now_str = datetime.now(timezone.utc).isoformat()

        return ArtworkVersion(
            version_id=version_id,
            created_at=now_str,
            description=description,
            relative_pdf_path=f"versions/{version_filename}",
            finding_id_fixed=finding_id,
            is_original=False
        )
