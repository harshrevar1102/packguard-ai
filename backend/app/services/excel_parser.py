from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import SpecSource
from app.services.excel_extractor import extract_reference, is_empty_value
from app.services.text_utils import collapse


class ExtractedField:
    def __init__(
        self,
        field_name: str,
        value: str,
        source: SpecSource,
        category: Optional[str] = "General",
        raw_key: Optional[str] = None,
    ):
        self.field_name = field_name
        self.value = value
        self.source = source
        self.category = category
        self.raw_key = raw_key

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_name": self.field_name,
            "value": self.value,
            "source": self.source.model_dump(),
            "category": self.category,
            "raw_key": self.raw_key,
        }


def categorize_field(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ["product", "brand", "item", "title", "identity"]):
        return "Identity"
    if any(k in n for k in ["ingredient", "composition"]):
        return "Ingredients"
    if any(k in n for k in ["allergen", "contains", "may contain"]):
        return "Allergens"
    if any(k in n for k in ["calorie", "fat", "sugar", "protein", "sodium", "vitamin", "fiber", "carb", "serving", "nutrition"]):
        return "Nutrition"
    if any(k in n for k in ["weight", "volume", "net wt", "size"]):
        return "Weight/Measurement"
    if any(k in n for k in ["claim", "organic", "gluten", "vegan", "non-gmo", "certified"]):
        return "Claims"
    if any(k in n for k in ["storage", "usage", "direction", "manufacturer"]):
        return "Claims"
    return "General"


class ExcelParser:
    @staticmethod
    def parse_file(file_path: Path, original_filename: str) -> List[ExtractedField]:
        """
        Parses an Excel specification workbook using label-based reference extraction.
        """
        ref = extract_reference(file_path)
        extracted: List[ExtractedField] = []

        # 1. Standard Reference Fields
        for key, rf in ref.fields.items():
            if is_empty_value(rf.value):
                continue
            cat = categorize_field(rf.label)
            src = SpecSource(
                filename=original_filename,
                sheet=rf.source.sheet,
                cell=rf.source.cell,
                label=rf.label,
            )
            extracted.append(
                ExtractedField(
                    field_name=rf.label,
                    value=rf.value,
                    source=src,
                    category=cat,
                    raw_key=key,
                )
            )

        # 2. Nutrition Table Entries
        for nr in ref.nutrition:
            val = nr.amount or ""
            if nr.daily_value:
                val += f" ({nr.daily_value} DV)"
            if not val.strip():
                continue
            src = SpecSource(
                filename=original_filename,
                sheet=nr.amount_source.sheet if nr.amount_source else (nr.label_source.sheet if nr.label_source else "Spec"),
                cell=nr.amount_source.cell if nr.amount_source else (nr.label_source.cell if nr.label_source else "A1"),
                label=nr.label,
            )
            extracted.append(
                ExtractedField(
                    field_name=nr.label,
                    value=val,
                    source=src,
                    category="Nutrition",
                    raw_key=nr.key,
                )
            )

        return extracted
