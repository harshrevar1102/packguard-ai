import re
from typing import List, Dict, Any, Optional
from app.models import SpecificationConflict
from app.services.excel_parser import ExtractedField


def normalize_val_for_comparison(val: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(val).strip().lower())
    cleaned = re.sub(r"[,\.;]+$", "", cleaned)
    return cleaned


def canonical_field_key(name: str) -> str:
    n = re.sub(r"[:_/\-]+", " ", str(name).strip().lower())
    n = re.sub(r"\s+", " ", n)
    if "net weight" in n or "package size" in n:
        return "net_weight"
    if "product" in n:
        return "product_name"
    if "brand" in n:
        return "brand"
    if "serving size" in n:
        return "serving_size"
    if "servings" in n:
        return "servings_per_container"
    if "ingredient" in n:
        return "ingredients"
    if "allergen" in n:
        return "allergens"
    if "storage" in n:
        return "storage"
    return n.strip()


class ConflictDetector:
    @staticmethod
    def detect_conflicts(file_fields_map: Dict[str, List[ExtractedField]]) -> List[SpecificationConflict]:
        """
        Takes a mapping of filename -> List[ExtractedField].
        Detects if specification documents contradict each other on product identity or field values.
        """
        conflicts: List[SpecificationConflict] = []
        if len(file_fields_map) <= 1:
            return []

        # Group fields by canonical field key
        grouped_by_field: Dict[str, List[ExtractedField]] = {}
        display_names: Dict[str, str] = {}
        for fname, fields in file_fields_map.items():
            for f in fields:
                ck = canonical_field_key(f.field_name)
                grouped_by_field.setdefault(ck, []).append(f)
                if ck not in display_names:
                    display_names[ck] = f.field_name

        for field_name, items in grouped_by_field.items():
            # Check if this field appears in at least two different files
            files_represented = set(item.source.filename for item in items)
            if len(files_represented) > 1:
                # Group distinct values across different files
                val_map: Dict[str, List[ExtractedField]] = {}
                for it in items:
                    norm = normalize_val_for_comparison(it.value)
                    val_map.setdefault(norm, []).append(it)

                # If more than 1 distinct normalized value exists across files
                if len(val_map) > 1:
                    # Filter out harmless formatting differences (e.g. "500 g" vs "500g")
                    stripped_vals = {re.sub(r"\s+", "", k): k for k in val_map.keys()}
                    if len(stripped_vals) > 1:
                        # Genuine conflict between specifications
                        conflicting_entries = []
                        for norm_v, field_instances in val_map.items():
                            for inst in field_instances:
                                conflicting_entries.append({
                                    "filename": inst.source.filename,
                                    "sheet": inst.source.sheet,
                                    "cell": inst.source.cell,
                                    "value": inst.value
                                })
                        
                        disp_title = display_names.get(field_name, field_name)
                        summary = (
                            f"Contradiction detected for '{disp_title}'. "
                            f"Different specification files specify incompatible values: "
                            + ", ".join([f"'{inst['value']}' in {inst['filename']} ({inst['sheet']}!{inst['cell']})" for inst in conflicting_entries[:4]])
                        )

                        conflicts.append(SpecificationConflict(
                            field_name=disp_title,
                            conflict_summary=summary,
                            conflicting_entries=conflicting_entries
                        ))

        return conflicts
