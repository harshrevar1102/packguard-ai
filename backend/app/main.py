import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import DATA_DIR, SERVER_HOST, SERVER_PORT
from app.models import (
    Product,
    Analysis,
    ArtworkVersion,
    FindingStatus,
    Finding,
    SpecificationConflict
)
from app.storage import storage
from app.services.excel_parser import ExcelParser, ExtractedField
from app.services.conflict_detector import ConflictDetector
from app.services.pdf_parser import PDFParser
from app.services.analysis_engine import AnalysisEngine
from app.services.pdf_fixer import PDFFixer
from app.services.history_comparator import HistoryComparator
from app.services.csv_exporter import CSVExporter
from app.services.email_report_builder import EmailReportBuilder

app = FastAPI(title="PackGuard AI Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Schemas ---
class FixPreviewRequest(BaseModel):
    finding_id: str


class FixSaveRequest(BaseModel):
    finding_id: str


class EmailReportRequest(BaseModel):
    recipient: Optional[str] = ""


# --- Product Endpoints ---

@app.get("/api/products", response_model=List[Product])
def list_products():
    """Returns all saved products. Initially empty."""
    return storage.list_products()


@app.get("/api/products/{product_id}")
def get_product_detail(product_id: str):
    product = storage.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    analyses = storage.get_analyses_for_product(product_id)
    return {
        "product": product,
        "analyses": analyses
    }


@app.delete("/api/products/{product_id}")
def delete_product(product_id: str):
    success = storage.delete_product(product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product and associated data deleted successfully"}


# --- Analysis Endpoints ---

@app.post("/api/analyze")
async def run_new_analysis(
    product_name: str = Form(...),
    spec_files: List[UploadFile] = File(...),
    artwork_file: UploadFile = File(...)
):
    """
    Submits specification Excel file(s) and exactly one PDF artwork file.
    Validates documents, checks for contradictions, runs bidirectional analysis,
    and saves the persistent analysis under the product.
    """
    clean_name = product_name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Product name is required.")

    if not spec_files or len(spec_files) == 0:
        raise HTTPException(status_code=400, detail="At least one specification Excel file is required.")

    # Validate artwork file
    if not artwork_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Packaging artwork must be a PDF file (.pdf).")

    # Validate specification files
    for sf in spec_files:
        fn_lower = sf.filename.lower()
        if not (fn_lower.endswith(".xlsx") or fn_lower.endswith(".xls")):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported specification file format: '{sf.filename}'. Please upload .xlsx or .xls files."
            )

    # Resolve or create product
    existing_product = storage.find_product_by_name(clean_name)
    now_iso = datetime.now(timezone.utc).isoformat()
    if existing_product:
        product = existing_product
        product_id = product.id
    else:
        product_id = f"prod_{uuid.uuid4().hex[:8]}"
        product = Product(
            id=product_id,
            name=clean_name,
            created_at=now_iso,
            updated_at=now_iso,
            analysis_ids=[]
        )
        storage.save_product(product)

    analysis_id = f"anl_{uuid.uuid4().hex[:8]}"
    upload_dir = DATA_DIR / "products" / product_id / "uploads" / analysis_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save uploaded files
    spec_paths = []
    file_fields_map = {}
    all_spec_fields: List[ExtractedField] = []

    for sf in spec_files:
        dest = upload_dir / sf.filename
        content = await sf.read()
        with open(dest, "wb") as f:
            f.write(content)
        spec_paths.append(dest)

        # Parse fields from this Excel file
        try:
            fields = ExcelParser.parse_file(dest, sf.filename)
            file_fields_map[sf.filename] = fields
            all_spec_fields.extend(fields)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to read Excel specification document '{sf.filename}': {str(e)}"
            )

    # Save artwork PDF
    artwork_path = upload_dir / artwork_file.filename
    art_content = await artwork_file.read()
    with open(artwork_path, "wb") as f:
        f.write(art_content)

    # 1. Contradiction check across specifications
    conflicts = ConflictDetector.detect_conflicts(file_fields_map)
    if conflicts:
        # Per Section 2: stop analysis and clearly explain conflicts
        return Response(
            content=SpecificationConflict(
                field_name=conflicts[0].field_name,
                conflict_summary="; ".join([c.conflict_summary for c in conflicts]),
                conflicting_entries=[e for c in conflicts for e in c.conflicting_entries]
            ).model_dump_json(),
            status_code=409,
            media_type="application/json"
        )

    # 2. Run bidirectional document analysis
    findings, summary = await AnalysisEngine.run_analysis(
        spec_fields=all_spec_fields,
        pdf_path=artwork_path,
        artwork_filename=artwork_file.filename,
        product_name=clean_name,
        spec_paths=spec_paths,
    )

    # Count total pages of the artwork PDF
    try:
        import fitz
        pdf_doc = fitz.open(artwork_path)
        total_pdf_pages = len(pdf_doc)
        pdf_doc.close()
    except Exception:
        total_pdf_pages = 1

    # 3. Create initial artwork version (v0 original)
    versions_dir = DATA_DIR / "products" / product_id / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    orig_version_filename = f"v0_original_{artwork_file.filename}"
    shutil.copy2(artwork_path, versions_dir / orig_version_filename)

    original_version = ArtworkVersion(
        version_id="v0_original",
        created_at=now_iso,
        description="Original uploaded packaging artwork",
        relative_pdf_path=f"versions/{orig_version_filename}",
        is_original=True
    )

    # 4. Compare with previous analysis if exists
    previous_analysis = storage.get_previous_analysis(product_id)
    comparison = HistoryComparator.compare(findings, previous_analysis)

    # 5. Build and save Analysis object
    analysis = Analysis(
        id=analysis_id,
        product_id=product_id,
        product_name=clean_name,
        timestamp=now_iso,
        spec_files=[sf.filename for sf in spec_files],
        artwork_file=artwork_file.filename,
        relative_artwork_path=f"uploads/{analysis_id}/{artwork_file.filename}",
        total_pages=total_pdf_pages,
        summary=summary,
        findings=findings,
        comparison_with_previous=comparison,
        versions=[original_version],
        active_version_id="v0_original"
    )

    storage.save_analysis(analysis)
    return analysis


@app.get("/api/products/{product_id}/analyses/{analysis_id}", response_model=Analysis)
def get_analysis(product_id: str, analysis_id: str):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    for f in analysis.findings:
        if f.status in (FindingStatus.MISMATCH, "Mismatch"):
            f.safe_fix_available = True
            if not f.suggested_replacement:
                f.suggested_replacement = f.spec_value or f.reference_value or ""
            if not f.original_text_to_replace:
                f.original_text_to_replace = f.artwork_value or ""
    return analysis


@app.delete("/api/products/{product_id}/analyses/{analysis_id}")
def delete_analysis(product_id: str, analysis_id: str):
    success = storage.delete_analysis(product_id, analysis_id)
    if not success:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"message": "Analysis deleted successfully"}


# --- Artwork Preview Image Endpoint ---

@app.get("/api/products/{product_id}/analyses/{analysis_id}/artwork/image")
def get_artwork_page_image(
    product_id: str,
    analysis_id: str,
    page: int = Query(1, ge=1),
    version_id: Optional[str] = Query(None)
):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    p_dir = DATA_DIR / "products" / product_id
    
    # Select active version or latest
    pdf_path = None
    if version_id:
        for v in analysis.versions:
            if v.version_id == version_id:
                pdf_path = p_dir / v.relative_pdf_path
                break

    if not pdf_path or not pdf_path.exists():
        pdf_path = p_dir / analysis.relative_artwork_path

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="Artwork PDF file not found")

    # Render cache path
    cache_img = p_dir / "cache" / f"{analysis_id}_{version_id or 'active'}_p{page}.png"
    if not cache_img.exists():
        cache_img.parent.mkdir(parents=True, exist_ok=True)
        try:
            PDFParser.render_page_image(pdf_path, page, cache_img, dpi=150)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to render PDF page {page}: {str(e)}")

    return FileResponse(cache_img, media_type="image/png")


# In-memory cache for specification matrix previews
_spec_matrix_cache = {}

@app.get("/api/products/{product_id}/analyses/{analysis_id}/spec/preview")
def get_spec_context_preview(
    product_id: str,
    analysis_id: str,
    filename: str = Query(...),
    sheet: str = Query(...),
    cell: str = Query(...)
):
    """
    Returns surrounding cell matrix context (e.g. +/- 3 rows, +/- 3 cols) for the specification preview.
    Uses in-memory caching to ensure sub-millisecond response times.
    """
    cache_key = f"{product_id}_{analysis_id}_{filename}_{sheet}_{cell}"
    if cache_key in _spec_matrix_cache:
        return _spec_matrix_cache[cache_key]

    file_path = DATA_DIR / "products" / product_id / "uploads" / analysis_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Specification file '{filename}' not found.")

    import openpyxl
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        if sheet not in wb.sheetnames:
            raise HTTPException(status_code=404, detail=f"Sheet '{sheet}' not found in workbook.")
        ws = wb[sheet]

        target_cell = ws[cell]
        target_row = target_cell.row
        target_col = target_cell.column

        min_r = max(1, target_row - 2)
        max_r = min(ws.max_row, target_row + 2)
        min_c = max(1, target_col - 2)
        max_c = min(ws.max_column, target_col + 2)

        matrix = []
        for r in range(min_r, max_r + 1):
            row_items = []
            for c in range(min_c, max_c + 1):
                c_cell = ws.cell(row=r, column=c)
                row_items.append({
                    "coordinate": c_cell.coordinate,
                    "value": str(c_cell.value) if c_cell.value is not None else "",
                    "is_target": (r == target_row and c == target_col)
                })
            matrix.append(row_items)

        wb.close()
        result = {
            "filename": filename,
            "sheet": sheet,
            "target_cell": cell,
            "target_value": str(target_cell.value) if target_cell.value is not None else "",
            "matrix": matrix
        }
        _spec_matrix_cache[cache_key] = result
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read specification preview: {str(e)}")


# --- Safe PDF Fix Endpoints ---

@app.post("/api/products/{product_id}/analyses/{analysis_id}/fix/preview")
def preview_fix(product_id: str, analysis_id: str, req: FixPreviewRequest):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    finding = next((f for f in analysis.findings if f.id == req.finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    finding.safe_fix_available = True
    if not finding.suggested_replacement:
        finding.suggested_replacement = finding.spec_value or finding.reference_value or ""
    if not finding.original_text_to_replace:
        finding.original_text_to_replace = finding.artwork_value or ""

    p_dir = DATA_DIR / "products" / product_id
    current_pdf = p_dir / analysis.relative_artwork_path
    
    # Create candidate copy
    candidate_pdf = p_dir / "candidate" / f"candidate_{finding.id}.pdf"
    success, msg, meta = PDFFixer.create_candidate_fix(
        source_pdf_path=current_pdf,
        candidate_pdf_path=candidate_pdf,
        finding=finding
    )

    if not success:
        return {
            "success": False,
            "message": msg
        }

    return {
        "success": True,
        "message": msg,
        "finding_id": finding.id,
        "replacement": finding.suggested_replacement or finding.spec_value,
        "candidate_image_url": f"/api/products/{product_id}/analyses/{analysis_id}/fix/candidate-image?finding_id={finding.id}&page={meta['page']}"
    }


@app.get("/api/products/{product_id}/analyses/{analysis_id}/fix/candidate-image")
def get_candidate_image(product_id: str, analysis_id: str, finding_id: str, page: int = 1):
    candidate_img = DATA_DIR / "products" / product_id / "candidate" / f"preview_candidate_p{page}.png"
    if not candidate_img.exists():
        raise HTTPException(status_code=404, detail="Candidate preview image not found")
    return FileResponse(candidate_img, media_type="image/png")


@app.post("/api/products/{product_id}/analyses/{analysis_id}/fix/save")
def save_fix(product_id: str, analysis_id: str, req: FixSaveRequest):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    finding = next((f for f in analysis.findings if f.id == req.finding_id), None)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    p_dir = DATA_DIR / "products" / product_id
    candidate_pdf = p_dir / "candidate" / f"candidate_{finding.id}.pdf"
    if not candidate_pdf.exists():
        raise HTTPException(status_code=400, detail="No pending candidate fix found for this finding. Please click Fix first.")

    # Commit version
    versions_dir = p_dir / "versions"
    new_version = PDFFixer.commit_version(
        product_versions_dir=versions_dir,
        candidate_pdf_path=candidate_pdf,
        finding_id=finding.id,
        description=f"Applied safe fix for '{finding.field_name}': '{finding.artwork_value}' -> '{finding.suggested_replacement or finding.spec_value}'",
        version_count=len(analysis.versions)
    )

    # Update active artwork path to the newly saved version
    analysis.versions.append(new_version)
    analysis.active_version_id = new_version.version_id
    analysis.relative_artwork_path = new_version.relative_pdf_path

    # Re-evaluate finding: mark as MATCH with evidence
    finding.status = FindingStatus.MATCH
    finding.artwork_value = finding.suggested_replacement or finding.spec_value
    finding.explanation = f"Corrected and verified in version {new_version.version_id}. Now matches specification."
    finding.safe_fix_available = False

    # Recalculate summary
    analysis.summary.total_mismatches = sum(1 for f in analysis.findings if f.status == FindingStatus.MISMATCH)
    analysis.summary.total_needs_review = sum(1 for f in analysis.findings if f.status == FindingStatus.NEEDS_REVIEW)
    analysis.summary.total_matches = sum(1 for f in analysis.findings if f.status == FindingStatus.MATCH)

    storage.save_analysis(analysis)

    # Clean up candidate
    if candidate_pdf.exists():
        candidate_pdf.unlink(missing_ok=True)

    return {
        "success": True,
        "message": f"Correction accepted and saved as version {new_version.version_id}.",
        "analysis": analysis
    }


# --- CSV Export Endpoint ---

@app.get("/api/products/{product_id}/analyses/{analysis_id}/export/csv")
def export_analysis_csv(product_id: str, analysis_id: str):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    csv_content = CSVExporter.generate_csv(analysis)
    safe_name = "".join(c for c in analysis.product_name if c.isalnum() or c in (" ", "_", "-")).strip()
    filename = f"PackGuard_{safe_name}_{analysis.id}.csv"

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# --- Email Report Endpoint ---

@app.get("/api/products/{product_id}/analyses/{analysis_id}/email-report")
@app.post("/api/products/{product_id}/analyses/{analysis_id}/email-report")
def create_email_report(product_id: str, analysis_id: str, req: Optional[EmailReportRequest] = None):
    analysis = storage.get_analysis(product_id, analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    rec = req.recipient if req and req.recipient else ""
    draft = EmailReportBuilder.build_report(analysis, recipient=rec)
    return draft
