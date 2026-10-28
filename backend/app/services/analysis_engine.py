from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from app.config import settings
from app.models import (
    AnalysisSummary,
    ArtworkSource,
    Evidence,
    Finding,
    FindingStatus,
    NutrientReference,
    ReferenceExtraction,
    ReferenceField,
    ReferenceStatus,
    SourceRef,
    SpecSource,
    Status,
)
from app.services.ai_service import AIService
from app.services.comparison_engine import ComparisonEngine
from app.services.excel_extractor import extract_reference, is_empty_value
from app.services.excel_parser import ExtractedField
from app.services.pdf_extractor import ArtworkData, extract_pdf
from app.services.text_utils import collapse, slug

log = logging.getLogger(__name__)


def _evaluate_fix_safety(
    spec_val: str,
    artwork_val: str,
    artwork_source: Optional[ArtworkSource],
) -> Tuple[bool, Optional[str]]:
    """
    Evaluates whether a text mismatch in the PDF artwork can be replaced.
    Allows fix option for every mismatch, providing visual candidate preview before saving.
    """
    if not spec_val or not str(spec_val).strip():
        return False, "Specification value is empty."

    if not artwork_source or not artwork_source.bbox:
        return True, "Correction candidate available (coordinates will be resolved)."

    return True, "Correction candidate available for review and application."


def _build_reference_from_fields(spec_fields: List[ExtractedField], default_file: str = "spec.xlsx") -> ReferenceExtraction:
    """Fallback: builds a ReferenceExtraction object from ExtractedField objects when raw bytes are not passed."""
    fields: Dict[str, ReferenceField] = {}
    nutrition: List[NutrientReference] = []

    # Map field names to standard keys
    name_to_key = {
        "product name": "product_name",
        "product": "product_name",
        "brand": "brand",
        "brand name": "brand",
        "net weight": "net_weight",
        "net wt": "net_weight",
        "package size / net weight": "net_weight",
        "serving size": "serving_size",
        "servings per container": "servings_per_container",
        "servings per package": "servings_per_container",
        "servings": "servings_per_container",
        "ingredients": "ingredients",
        "allergen information": "allergens",
        "allergens": "allergens",
        "storage instructions": "storage",
        "storage": "storage",
        "dietary information": "dietary",
        "claims & certifications": "claims",
        "claims": "claims",
        "upc": "upc",
        "barcode": "upc",
        "statement of identity": "legal_name",
        "legal name": "legal_name",
        "status": "sheet_status",
    }

    status_text = None
    approved = None

    for ef in spec_fields:
        low = ef.field_name.lower().strip()
        key = name_to_key.get(low)

        sref = SourceRef(sheet=ef.source.sheet, cell=ef.source.cell)
        lref = SourceRef(sheet=ef.source.sheet, cell=f"A{ef.source.cell[1:]}" if len(ef.source.cell) > 1 else "A1")

        if key == "sheet_status":
            status_text = ef.value
            approved = "approved" in status_text.lower() or "final" in status_text.lower()
            continue

        if ef.category == "Nutrition" or low in ("calories", "total fat", "sodium", "protein", "carbohydrates"):
            nutrition.append(
                NutrientReference(
                    key=slug(ef.field_name),
                    label=ef.field_name,
                    amount=ef.value,
                    amount_source=sref,
                    label_source=lref,
                )
            )
        elif key:
            fields[key] = ReferenceField(
                key=key,
                label=ef.field_name,
                value=ef.value,
                source=sref,
                label_source=lref,
            )
        else:
            # Other fields
            fields[slug(ef.field_name)] = ReferenceField(
                key=slug(ef.field_name),
                label=ef.field_name,
                value=ef.value,
                source=sref,
                label_source=lref,
            )

    return ReferenceExtraction(
        sheets=list({ef.source.sheet for ef in spec_fields}),
        status=ReferenceStatus(text=status_text, approved=approved),
        fields=fields,
        nutrition=nutrition,
        warnings=[],
        unmapped_rows=[],
    )


class AnalysisEngine:
    @classmethod
    async def run_analysis(
        cls,
        spec_fields: Optional[List[ExtractedField]] = None,
        pdf_path: Optional[Path] = None,
        artwork_filename: str = "",
        product_name: str = "",
        spec_paths: Optional[List[Path]] = None,
        pdf_bytes: Optional[bytes] = None,
        spec_bytes: Optional[bytes] = None,
    ) -> Tuple[List[Finding], AnalysisSummary]:
        """
        Executes complete deterministic comparison between specification document(s)
        and PDF artwork, with seamless AI semantic reasoning for unmapped/uncertain items.
        """
        if spec_fields and len(spec_fields) > 0 and isinstance(spec_fields[0], Path):
            if not spec_paths:
                spec_paths = spec_fields  # type: ignore
            spec_fields = None

        if spec_bytes:
            reference = extract_reference(spec_bytes)
        elif spec_paths and len(spec_paths) > 0 and spec_paths[0].exists():
            primary_spec_name = spec_paths[0].name
            reference = extract_reference(spec_paths[0])
            # If multiple spec paths, merge non-conflicting fields
            for sp in spec_paths[1:]:
                if sp.exists():
                    try:
                        extra_ref = extract_reference(sp)
                        for k, rf in extra_ref.fields.items():
                            if k not in reference.fields:
                                reference.fields[k] = rf
                        for n in extra_ref.nutrition:
                            if not any(x.key == n.key for x in reference.nutrition):
                                reference.nutrition.append(n)
                        reference.unmapped_rows.extend(extra_ref.unmapped_rows)
                    except Exception as e:
                        log.warning("Could not merge extra spec file %s: %s", sp.name, e)
        elif spec_fields:
            # Check if any spec_field source path exists
            first_fn = spec_fields[0].source.filename if spec_fields else ""
            primary_spec_name = first_fn or "Specification.xlsx"
            candidate_path = Path(first_fn)
            if candidate_path.exists():
                try:
                    reference = extract_reference(candidate_path)
                except Exception:
                    reference = _build_reference_from_fields(spec_fields, primary_spec_name)
            else:
                reference = _build_reference_from_fields(spec_fields, primary_spec_name)
        else:
            raise ValueError("No specification data provided for analysis.")

        # Ensure product_name is in reference fields if provided
        if product_name and "product_name" not in reference.fields:
            reference.fields["product_name"] = ReferenceField(
                key="product_name",
                label="Product Name",
                value=product_name,
                source=SourceRef(sheet="Spec", cell="A1"),
                label_source=SourceRef(sheet="Spec", cell="A1"),
            )

        # 2. Extract Artwork PDF
        if pdf_bytes:
            artwork = extract_pdf(pdf_bytes, with_previews=True)
        elif pdf_path and pdf_path.exists():
            artwork = extract_pdf(pdf_path, with_previews=True)
        else:
            raise ValueError("No valid artwork PDF provided for analysis.")

        # 3. Run Deterministic Comparison Engine
        try:
            raw_findings = ComparisonEngine(reference, artwork).run()
        finally:
            artwork.close()

        # Re-open doc for font queries if needed
        doc_fitz = None
        if pdf_path and pdf_path.exists():
            try:
                import fitz
                doc_fitz = fitz.open(str(pdf_path))
            except Exception:
                doc_fitz = None

        final_findings: List[Finding] = []

        # 4. Map findings and evaluate safe fix availability
        for rf in raw_findings:
            # Map evidence to ArtworkSource
            art_src: Optional[ArtworkSource] = None
            if rf.evidence:
                ev = rf.evidence[0]
                bb = ev.bboxes[0] if ev.bboxes else None
                f_size, f_name = 11.0, "Helvetica"

                # Look up font info if bbox available
                if bb and doc_fitz and ev.page <= len(doc_fitz):
                    try:
                        page = doc_fitz[ev.page - 1]
                        bx0, by0, bx1, by1 = bb[:4]
                        page_dict = page.get_text("dict")
                        found_font = False
                        for block in page_dict.get("blocks", []):
                            if block.get("type") == 0:
                                for line in block.get("lines", []):
                                    for span in line.get("spans", []):
                                        sb = span.get("bbox", [0, 0, 0, 0])
                                        if not (sb[2] < bx0 or sb[0] > bx1 or sb[3] < by0 or sb[1] > by1):
                                            f_size = float(span.get("size", 11.0))
                                            f_name = str(span.get("font", "Helvetica"))
                                            found_font = True
                                            break
                                    if found_font:
                                        break
                            if found_font:
                                break
                    except Exception:
                        pass

                art_src = ArtworkSource(
                    filename=artwork_filename or "artwork.pdf",
                    page=ev.page,
                    bbox=bb,
                    text=ev.snippet,
                    is_ocr=(ev.source == "ocr"),
                    font_size=f_size,
                    font_name=f_name,
                )

            # Map SpecSource
            spec_src: Optional[SpecSource] = None
            if rf.reference_source:
                spec_src = SpecSource(
                    filename=primary_spec_name,
                    sheet=rf.reference_source.sheet,
                    cell=rf.reference_source.cell,
                    label=rf.field_name,
                )

            # Safe fix evaluation for Mismatches
            spec_v = rf.reference_value or ""
            art_v = rf.artwork_value or ""
            safe_fix = False
            fix_reason = None
            suggested_replacement = None
            original_to_replace = None

            if rf.status == FindingStatus.MISMATCH:
                safe_fix, fix_reason = _evaluate_fix_safety(spec_v, art_v, art_src)
                if safe_fix:
                    suggested_replacement = spec_v
                    original_to_replace = art_v
                else:
                    fix_reason = fix_reason or "Automatic fix is unavailable for this discrepancy."

            rf.spec_source = spec_src
            rf.artwork_source = art_src
            rf.safe_fix_available = safe_fix
            rf.fix_explanation = fix_reason
            rf.suggested_replacement = suggested_replacement
            rf.original_text_to_replace = original_to_replace

            final_findings.append(rf)

        if doc_fitz:
            doc_fitz.close()

        all_art_text = "\n".join(p.text for p in artwork.pages)

        # -------------------------------------------------------------
        # 4b. AI SEMANTIC COMPARISON: Evaluate Phrasing Equivalences
        # -------------------------------------------------------------
        # Combine deterministic findings with AI semantic comparison:
        # Check text findings with differences (MISMATCH or NEEDS_REVIEW) where meaning might be identical despite different words.
        semantic_candidates = []
        for rf in final_findings:
            if (
                rf.status in (FindingStatus.MISMATCH, FindingStatus.NEEDS_REVIEW)
                and rf.reference_value
                and rf.artwork_value
                and rf.artwork_value != "None"
            ):
                if not rf.id.startswith("scope.") and not rf.id.startswith("other."):
                    semantic_candidates.append({
                        "id": rf.id,
                        "field_name": rf.field_name,
                        "spec_value": rf.reference_value,
                        "artwork_value": rf.artwork_value,
                        "current_status": rf.status.value,
                        "explanation": rf.explanation,
                    })

        if semantic_candidates:
            ai_comparisons = await AIService.evaluate_semantic_text_comparison(
                candidate_items=semantic_candidates,
                pdf_text_summary=all_art_text[:4000],
                product_name=product_name or primary_spec_name,
            )
            ai_comp_map = {item.get("id"): item for item in ai_comparisons if item.get("id")}
            for rf in final_findings:
                if rf.id in ai_comp_map:
                    comp = ai_comp_map[rf.id]
                    verdict = comp.get("semantic_verdict")
                    ai_expl = comp.get("explanation", "")
                    rf.ai_analysis = ai_expl

                    if verdict == "SEMANTIC_MATCH" and comp.get("is_equivalent_meaning", True):
                        # Combine both: Upgrade status to Match based on semantic equivalence,
                        # while explicitly recording the deterministic diff in the explanation.
                        rf.status = FindingStatus.MATCH
                        rf.confidence = comp.get("confidence", "High")
                        rf.explanation = (
                            f"Semantic Match (Verified by AI): {ai_expl} "
                            f"[Deterministic text comparison noted: {rf.explanation}]"
                        )
                        # Clear mismatch fix availability since it is now matched
                        rf.safe_fix_available = False
                        rf.fix_explanation = "Matched via verified semantic equivalence."
                    elif verdict == "SUBSTANTIVE_MISMATCH":
                        rf.explanation = f"{rf.explanation} [AI semantic analysis confirms discrepancy: {ai_expl}]"
                    elif verdict == "NEEDS_REVIEW":
                        if not rf.review_reason:
                            rf.review_reason = ai_expl
                        else:
                            rf.review_reason += f" AI Note: {ai_expl}"

        # -------------------------------------------------------------
        # 5. AI FEATURE INTEGRATION: Unmapped Rows & Semantic Analysis
        # -------------------------------------------------------------
        # When reference contains unmapped rows from the workbook (authored rows not covered by standard checks),
        # use AIService (with LLM or deterministic heuristics) to evaluate whether they are relevant packaging
        # content missing from artwork, or internal operational codes.
        if reference.unmapped_rows:
            unmapped_items = []
            for ur in reference.unmapped_rows[:15]:
                # Extract label and value from unmapped row string
                parts = ur.text.split(":", 1)
                lbl = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ur.text
                unmapped_items.append({
                    "field_name": lbl,
                    "value": val,
                    "sheet": ur.sheet,
                    "row": ur.row,
                    "category": "General",
                })

            ai_results = await AIService.analyze_semantic_differences(
                unmatched_spec_fields=unmapped_items,
                pdf_text_summary=all_art_text[:4000],
                product_name=product_name or primary_spec_name,
            )

            for idx, ai_item in enumerate(ai_results):
                src_item = unmapped_items[idx] if idx < len(unmapped_items) else {}
                f_name = ai_item.get("field_name", "Unmapped specification field")
                status_str = ai_item.get("status", "Needs Review")
                status_enum = FindingStatus.from_any(status_str)

                final_findings.append(
                    Finding(
                        id=f"unmapped.{src_item.get('row', idx)}",
                        field_name=f_name,
                        group="Specification Notes",
                        category="General",
                        status=status_enum,
                        spec_value=src_item.get("value", ""),
                        reference_value=src_item.get("value", ""),
                        artwork_value=ai_item.get("artwork_value", "Not found on artwork"),
                        explanation=ai_item.get("explanation", "Extracted from workbook specification row."),
                        spec_source=SpecSource(
                            filename=primary_spec_name,
                            sheet=src_item.get("sheet", "Spec"),
                            cell=f"A{src_item.get('row', 1)}",
                            label=src_item.get("field_name", ""),
                        ),
                        confidence=ai_item.get("confidence", "Medium"),
                        is_missing_from_artwork=ai_item.get("is_missing_from_artwork", True),
                        suggested_replacement=ai_item.get("suggested_replacement"),
                        safe_fix_available=False,
                    )
                )

        # 6. Calculate Summary Metrics
        m_count = sum(1 for f in final_findings if f.status == FindingStatus.MISMATCH)
        nr_count = sum(1 for f in final_findings if f.status == FindingStatus.NEEDS_REVIEW)
        match_count = sum(1 for f in final_findings if f.status == FindingStatus.MATCH)
        nc_count = sum(1 for f in final_findings if f.status == FindingStatus.NOT_CHECKED)
        unapproved_matches = sum(
            1 for f in final_findings if f.status == FindingStatus.MATCH and f.reference_approved is False
        )

        summary = AnalysisSummary(
            total_mismatches=m_count,
            total_needs_review=nr_count,
            total_matches=match_count,
            total_not_checked=nc_count,
            total_findings=len(final_findings),
            matches_against_unapproved_reference=unapproved_matches,
            total=len(final_findings),
            match=match_count,
            mismatch=m_count,
            needs_review=nr_count,
            not_checked=nc_count,
        )

        return final_findings, summary
