import asyncio
from pathlib import Path
import openpyxl
import fitz

from app.models import Product, FindingStatus
from app.storage import storage
from app.services.excel_parser import ExcelParser
from app.services.conflict_detector import ConflictDetector
from app.services.pdf_parser import PDFParser
from app.services.analysis_engine import AnalysisEngine
from app.services.pdf_fixer import PDFFixer
from app.services.history_comparator import HistoryComparator
from app.services.csv_exporter import CSVExporter
from app.services.email_report_builder import EmailReportBuilder


async def test_full_engine():
    print("--- 1. Testing Clean Empty Catalog ---")
    initial_products = storage.list_products()
    assert isinstance(initial_products, list)

    test_dir = Path("./test_fixtures")
    test_dir.mkdir(exist_ok=True)

    # --- Create Sample Excel 1 ---
    spec1_path = test_dir / "Spec_Approved.xlsx"
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.title = "Product Details"
    ws1["A1"] = "Product Name"
    ws1["B1"] = "Nature Valley Granola"
    ws1["A2"] = "Net Weight"
    ws1["B2"] = "500g"
    ws1["A3"] = "Serving Size"
    ws1["B3"] = "50g"
    ws1["A4"] = "Calories"
    ws1["B4"] = "210 kcal"
    ws1["A5"] = "Allergens"
    ws1["B5"] = "Contains: Oats, Almonds. May contain: Milk"
    ws1["A6"] = "Storage Instructions"
    ws1["B6"] = "Store in a cool, dry place"
    wb1.save(spec1_path)

    # --- Create Sample Conflicting Excel 2 ---
    spec2_conflict_path = test_dir / "Spec_Draft_Conflict.xlsx"
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.title = "Draft Details"
    ws2["A1"] = "Product Name"
    ws2["B1"] = "Nature Valley Granola"
    ws2["A2"] = "Net Weight"
    ws2["B2"] = "400g"  # Conflicting weight!
    wb2.save(spec2_conflict_path)

    print("\n--- 2. Testing Specification Contradiction Detector ---")
    fields1 = ExcelParser.parse_file(spec1_path, "Spec_Approved.xlsx")
    fields2 = ExcelParser.parse_file(spec2_conflict_path, "Spec_Draft_Conflict.xlsx")
    file_map = {
        "Spec_Approved.xlsx": fields1,
        "Spec_Draft_Conflict.xlsx": fields2
    }
    conflicts = ConflictDetector.detect_conflicts(file_map)
    print(f"Conflicts detected: {len(conflicts)}")
    assert len(conflicts) > 0
    print(f"Conflict Summary: {conflicts[0].conflict_summary}")
    assert "Net Weight" in conflicts[0].field_name

    # --- Create Sample Artwork PDF ---
    pdf_path = test_dir / "Artwork_Packaging.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4

    # Add artwork text with one deliberate mismatch (Net Weight 450g instead of 500g)
    # and one match (Product Name: Nature Valley Granola)
    # and one unverified claim (100% Organic Oats)
    page.insert_text(fitz.Point(50, 80), "Nature Valley Granola", fontsize=18, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(50, 120), "Net Weight 450g", fontsize=12, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(50, 150), "Contains: Oats, Almonds. May contain: Milk", fontsize=10, fontname="helv", color=(0, 0, 0))
    page.insert_text(fitz.Point(50, 180), "100% Organic Oats", fontsize=11, fontname="helv", color=(0, 0, 0))
    doc.save(pdf_path)
    doc.close()

    print("\n--- 3. Testing PDF Parser ---")
    spans, pages_meta = PDFParser.extract_spans_and_pages(pdf_path)
    print(f"Extracted {len(spans)} text spans across {len(pages_meta)} page(s)")
    loc = PDFParser.find_best_location_for_text(pdf_path, "Nature Valley Granola", "Artwork_Packaging.pdf")
    assert loc is not None
    print(f"Found title at page {loc.page}, bbox: {loc.bbox}")

    print("\n--- 4. Testing Bidirectional Analysis Engine ---")
    findings, summary = await AnalysisEngine.run_analysis(
        spec_fields=fields1,
        pdf_path=pdf_path,
        artwork_filename="Artwork_Packaging.pdf",
        product_name="Nature Valley Granola"
    )

    print(f"Total findings: {len(findings)}")
    print(f"Summary: Mismatches={summary.total_mismatches}, Needs Review={summary.total_needs_review}, Matches={summary.total_matches}")
    
    # Assertions
    mismatch_findings = [f for f in findings if f.status == FindingStatus.MISMATCH]
    match_findings = [f for f in findings if f.status == FindingStatus.MATCH]
    print(f"Mismatches: {[f.field_name for f in mismatch_findings]}")
    assert any("Weight" in f.field_name for f in mismatch_findings)
    assert any("Product Name" in f.field_name for f in match_findings)

    print("\n--- 5. Testing Safe PDF Fix Workflow ---")
    weight_mismatch = next(f for f in mismatch_findings if "Weight" in f.field_name)
    print(f"Weight mismatch safe_fix_available: {weight_mismatch.safe_fix_available}")
    assert weight_mismatch.safe_fix_available is True

    candidate_pdf_path = test_dir / "candidate_fix.pdf"
    success, msg, meta = PDFFixer.create_candidate_fix(
        source_pdf_path=pdf_path,
        candidate_pdf_path=candidate_pdf_path,
        finding=weight_mismatch
    )
    print(f"DEBUG: create_candidate_fix result: success={success}, msg={msg}")
    assert success is True
    print(f"Candidate fix generated: {msg}")

    # Commit version
    version_dir = test_dir / "versions"
    version = PDFFixer.commit_version(
        product_versions_dir=version_dir,
        candidate_pdf_path=candidate_pdf_path,
        finding_id=weight_mismatch.id,
        description="Applied safe fix for Net Weight",
        version_count=0
    )
    print(f"Committed new version: {version.version_id} ({version.relative_pdf_path})")

    # Verify original is untouched
    orig_doc = fitz.open(pdf_path)
    orig_text = orig_doc[0].get_text()
    orig_doc.close()
    assert "450g" in orig_text
    print("Original PDF verified untouched!")

    # Verify version has replacement
    fixed_doc = fitz.open(test_dir / version.relative_pdf_path)
    fixed_text = fixed_doc[0].get_text()
    fixed_doc.close()
    assert "500g" in fixed_text
    print("Corrected version contains verified '500g' replacement!")

    print("\n--- 6. Testing CSV Exporter with Formula Injection Escaping ---")
    from app.models import Analysis, ArtworkVersion
    test_analysis = Analysis(
        id="anl_test123",
        product_id="prod_test123",
        product_name="=HYPERLINK('http://evil.com') Nature Valley",
        timestamp="2026-10-27T18:00:00Z",
        spec_files=["Spec_Approved.xlsx"],
        artwork_file="Artwork_Packaging.pdf",
        relative_artwork_path="test_fixtures/Artwork_Packaging.pdf",
        summary=summary,
        findings=findings,
        versions=[version],
        active_version_id=version.version_id
    )
    csv_str = CSVExporter.generate_csv(test_analysis)
    assert "'=HYPERLINK" in csv_str  # Formula escaped with single quote
    print("CSV export formula protection verified successfully!")

    print("\n--- 7. Testing Email Report Builder ---")
    email_draft = EmailReportBuilder.build_report(test_analysis, recipient="quality@packaging.com")
    assert "mailto:quality@packaging.com" in email_draft["mailto_url"]
    assert "Note on Attachments" in email_draft["body"]
    print("Email report draft built with verified structure and mailto link!")

    print("\n--- 8. Testing History Comparator ---")
    # Simulate a second analysis where the weight was fixed and matches
    fixed_findings = []
    for f in findings:
        f_copy = f.model_copy()
        if "Weight" in f_copy.field_name:
            f_copy.status = FindingStatus.MATCH
            f_copy.artwork_value = "500g"
        fixed_findings.append(f_copy)

    comp = HistoryComparator.compare(fixed_findings, test_analysis)
    assert comp is not None
    print(f"History comparison: Resolved={comp.resolved_count}, Persistent={comp.persistent_count}, New={comp.new_count}")
    assert comp.resolved_count >= 1
    print("History comparison audit delta verified successfully!")

    print("\nALL BACKEND ENGINE TESTS PASSED!")


if __name__ == "__main__":
    asyncio.run(test_full_engine())
