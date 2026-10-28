import asyncio
from pathlib import Path
from app.services.analysis_engine import AnalysisEngine
from app.models import FindingStatus


async def test_dancing_fish_sample():
    root_dir = Path(__file__).resolve().parent.parent.parent
    sample_dir = root_dir / "packguard-ai" / "sample_data"
    sheet_path = sample_dir / "DancingFish_Granola_BerryCrunch_US_Content_Sheet.xlsx"
    pdf_path = sample_dir / "DancingFish_Granola_Berry_US_Carton.pdf"

    assert sheet_path.exists(), f"Sample sheet not found at {sheet_path}"
    assert pdf_path.exists(), f"Sample pdf not found at {pdf_path}"

    print(f"Testing real sample: {sheet_path.name} against {pdf_path.name}...")

    findings, summary = await AnalysisEngine.run_analysis(
        pdf_path=pdf_path,
        artwork_filename=pdf_path.name,
        spec_paths=[sheet_path],
        product_name="Dancing Fish Berry Crunch Granola"
    )

    print(f"\n--- Analysis Complete ---")
    print(f"Total findings: {summary.total_findings}")
    print(f"Matches: {summary.total_matches}")
    print(f"Mismatches: {summary.total_mismatches}")
    print(f"Needs Review: {summary.total_needs_review}")
    print(f"Not Checked: {summary.total_not_checked}")
    print(f"Matches against unapproved reference: {summary.matches_against_unapproved_reference}")

    print("\nSample Findings Breakdown:")
    for f in findings[:10]:
        print(f"[{f.status.value}] {f.field_name}: spec='{f.spec_value}' vs art='{f.artwork_value}'")
        if f.review_reason:
            print(f"   Review reason: {f.review_reason}")
        if f.limitations:
            print(f"   Limitations: {f.limitations}")
        if f.safe_fix_available:
            print(f"   Safe Fix Available: {f.safe_fix_available}")

    # Specific assertions matching packguard-ai rules
    assert summary.total_findings > 0
    # Net weight check
    net_weight_finding = next((f for f in findings if "weight" in f.field_name.lower()), None)
    assert net_weight_finding is not None
    print(f"\nNet weight finding: status={net_weight_finding.status.value}, spec={net_weight_finding.spec_value}, art={net_weight_finding.artwork_value}")

    # Product name check
    pname_finding = next((f for f in findings if "product name" in f.field_name.lower()), None)
    assert pname_finding is not None
    print(f"Product name finding: status={pname_finding.status.value}, spec={pname_finding.spec_value}, art={pname_finding.artwork_value}")

    print("\nSAMPLE PACKGUARD VERIFICATION TEST PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(test_dancing_fish_sample())
