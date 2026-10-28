from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------- Status Enums
class Status(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_CHECKED = "NOT_CHECKED"

    def __eq__(self, other):
        if isinstance(other, (str, Enum)):
            val = other.value if isinstance(other, Enum) else str(other)
            s1 = self.value.replace("_", "").replace(" ", "").upper()
            s2 = val.replace("_", "").replace(" ", "").upper()
            return s1 == s2
        return super().__eq__(other)


class FindingStatus(str, Enum):
    MISMATCH = "Mismatch"
    NEEDS_REVIEW = "Needs Review"
    MATCH = "Match"
    NOT_CHECKED = "Not Checked"

    def __eq__(self, other):
        if isinstance(other, (str, Enum)):
            val = other.value if isinstance(other, Enum) else str(other)
            s1 = self.value.replace("_", "").replace(" ", "").upper()
            s2 = val.replace("_", "").replace(" ", "").upper()
            return s1 == s2
        return super().__eq__(other)

    @classmethod
    def from_any(cls, val: Any) -> "FindingStatus":
        if isinstance(val, FindingStatus):
            return val
        s = (val.value if isinstance(val, Enum) else str(val)).replace("_", "").replace(" ", "").upper()
        if s == "MATCH":
            return cls.MATCH
        if s == "MISMATCH":
            return cls.MISMATCH
        if s == "NEEDSREVIEW":
            return cls.NEEDS_REVIEW
        if s == "NOTCHECKED":
            return cls.NOT_CHECKED
        return cls.NEEDS_REVIEW


# ---------------------------------------------------------------- Reference & Source Models
class SourceRef(BaseModel):
    sheet: str
    cell: str

    def display(self) -> str:
        return f"{self.sheet}!{self.cell}"


class SpecSource(BaseModel):
    filename: str
    sheet: str
    cell: str
    label: Optional[str] = None
    row: Optional[int] = None
    col: Optional[int] = None

    def display(self) -> str:
        return f"{self.filename} ({self.sheet}!{self.cell})"


class ArtworkSource(BaseModel):
    filename: str
    page: int  # 1-indexed for display
    bbox: Optional[List[float]] = None  # [x0, y0, x1, y1] in PDF point coordinates
    text: Optional[str] = None
    is_ocr: bool = False
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    color: Optional[List[float]] = None


class Evidence(BaseModel):
    page: int
    snippet: str
    # Rectangles in PDF points [x0, y0, x1, y1] (top-left origin)
    bboxes: List[List[float]] = Field(default_factory=list)
    source: Literal["text_layer", "ocr"] = "text_layer"
    ocr_confidence: Optional[float] = None
    label: Optional[str] = None


class ReferenceField(BaseModel):
    key: str
    label: str
    value: str
    source: SourceRef
    label_source: SourceRef
    note: Optional[str] = None
    note_source: Optional[SourceRef] = None
    # True when workbook marks this field as assumed / unconfirmed / to verify
    flagged: bool = False
    flag_reason: Optional[str] = None


class NutrientReference(BaseModel):
    key: str
    label: str
    amount: Optional[str] = None
    amount_source: Optional[SourceRef] = None
    daily_value: Optional[str] = None
    daily_value_source: Optional[SourceRef] = None
    label_source: Optional[SourceRef] = None


class UnmappedRow(BaseModel):
    sheet: str
    row: int
    text: str


class ReferenceStatus(BaseModel):
    text: Optional[str] = None
    source: Optional[SourceRef] = None
    note: Optional[str] = None
    # False = explicitly draft/unapproved, True = explicitly approved, None = not stated
    approved: Optional[bool] = None


class ReferenceExtraction(BaseModel):
    sheets: List[str]
    status: ReferenceStatus
    fields: Dict[str, ReferenceField]
    nutrition: List[NutrientReference]
    nutrition_title: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    unmapped_rows: List[UnmappedRow] = Field(default_factory=list)


# ---------------------------------------------------------------- Core Finding Model
class Finding(BaseModel):
    id: str
    field_name: str
    field: Optional[str] = None  # alias for field_name
    group: Optional[str] = None
    category: Optional[str] = None
    spec_value: Optional[str] = None
    reference_value: Optional[str] = None
    artwork_value: Optional[str] = None
    expected_value: Optional[str] = None
    status: FindingStatus
    explanation: str
    spec_source: Optional[SpecSource] = None
    reference_source: Optional[SourceRef] = None
    artwork_source: Optional[ArtworkSource] = None
    evidence: List[Evidence] = Field(default_factory=list)
    confidence: Optional[str] = "High"
    reference_status: Optional[str] = None
    reference_approved: Optional[bool] = None
    reference_note: Optional[str] = None
    reference_flagged: bool = False
    review_reason: Optional[str] = None
    limitations: List[str] = Field(default_factory=list)
    safe_fix_available: bool = False
    fix_explanation: Optional[str] = None
    suggested_replacement: Optional[str] = None
    original_text_to_replace: Optional[str] = None
    is_missing_from_artwork: bool = False
    ai_analysis: Optional[str] = None

    @model_validator(mode="after")
    def sync_aliases(self) -> "Finding":
        if not self.field and self.field_name:
            self.field = self.field_name
        elif not self.field_name and self.field:
            self.field_name = self.field

        if self.spec_value is None and self.reference_value is not None:
            self.spec_value = self.reference_value
        elif self.reference_value is None and self.spec_value is not None:
            self.reference_value = self.spec_value

        if not self.category and self.group:
            self.category = self.group
        elif not self.group and self.category:
            self.group = self.category

        if self.spec_source and not self.reference_source:
            self.reference_source = SourceRef(sheet=self.spec_source.sheet, cell=self.spec_source.cell)
        elif self.reference_source and not self.spec_source:
            self.spec_source = SpecSource(
                filename="content_sheet",
                sheet=self.reference_source.sheet,
                cell=self.reference_source.cell,
                label=self.field_name
            )

        if not self.artwork_source and self.evidence:
            first_ev = self.evidence[0]
            bb = first_ev.bboxes[0] if first_ev.bboxes else None
            self.artwork_source = ArtworkSource(
                filename="artwork_pdf",
                page=first_ev.page,
                bbox=bb,
                text=first_ev.snippet,
                is_ocr=(first_ev.source == "ocr")
            )

        return self


# ---------------------------------------------------------------- Summaries & Catalog
class AnalysisSummary(BaseModel):
    total_mismatches: int = 0
    total_needs_review: int = 0
    total_matches: int = 0
    total_not_checked: int = 0
    total_findings: int = 0
    matches_against_unapproved_reference: int = 0
    # Packguard compatibility aliases
    total: Optional[int] = None
    match: Optional[int] = None
    mismatch: Optional[int] = None
    needs_review: Optional[int] = None
    not_checked: Optional[int] = None

    @model_validator(mode="after")
    def sync_summary(self) -> "AnalysisSummary":
        if self.total is None:
            self.total = self.total_findings
        if self.match is None:
            self.match = self.total_matches
        if self.mismatch is None:
            self.mismatch = self.total_mismatches
        if self.needs_review is None:
            self.needs_review = self.total_needs_review
        if self.not_checked is None:
            self.not_checked = self.total_not_checked
        return self


class ComparisonSummary(BaseModel):
    previous_analysis_id: Optional[str] = None
    previous_timestamp: Optional[str] = None
    previous_unresolved_count: int = 0
    current_unresolved_count: int = 0
    resolved_count: int = 0
    persistent_count: int = 0
    new_count: int = 0
    changed_count: int = 0
    resolved_issue_ids: List[str] = Field(default_factory=list)
    persistent_issue_ids: List[str] = Field(default_factory=list)
    new_issue_ids: List[str] = Field(default_factory=list)
    change_descriptions: List[str] = Field(default_factory=list)


class ArtworkVersion(BaseModel):
    version_id: str
    created_at: str
    description: str
    relative_pdf_path: str
    finding_id_fixed: Optional[str] = None
    is_original: bool = False


class FileInfo(BaseModel):
    name: str
    size: int


class PageInfo(BaseModel):
    number: int
    width: float
    height: float
    text_source: Literal["text_layer", "ocr", "none"]
    text_chars: int
    image_count: int
    ocr_confidence: Optional[float] = None
    preview_data_url: Optional[str] = None


class OcrInfo(BaseModel):
    available: bool
    pages_ocr_run: List[int] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class Analysis(BaseModel):
    id: str
    product_id: str
    product_name: str
    timestamp: str
    spec_files: List[str]
    artwork_file: str
    relative_artwork_path: str
    total_pages: int = 1
    summary: AnalysisSummary
    findings: List[Finding]
    comparison_with_previous: Optional[ComparisonSummary] = None
    versions: List[ArtworkVersion] = Field(default_factory=list)
    active_version_id: Optional[str] = None
    # Rich reference status
    reference_status: Optional[ReferenceStatus] = None
    warnings: List[str] = Field(default_factory=list)
    disclaimer: Optional[str] = None


class Product(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    analysis_ids: List[str] = Field(default_factory=list)


class SpecificationConflict(BaseModel):
    field_name: str
    conflict_summary: str
    conflicting_entries: List[Dict[str, Any]]


class DecisionType(str, Enum):
    CONFIRMED_ISSUE = "confirmed_issue"
    ACCEPTED_DIFFERENCE = "accepted_difference"
    NEEDS_INVESTIGATION = "needs_investigation"
    RESOLVED = "resolved"


class ReviewerDecision(BaseModel):
    decision: DecisionType
    note: Optional[str] = Field(default=None, max_length=2000)


class ReportRequest(BaseModel):
    analysis: Analysis
    decisions: Dict[str, ReviewerDecision] = Field(default_factory=dict)
