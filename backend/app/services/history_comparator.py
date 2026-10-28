from typing import Optional, List, Dict
from app.models import Analysis, Finding, FindingStatus, ComparisonSummary


class HistoryComparator:
    @staticmethod
    def compare(
        current_findings: List[Finding],
        previous_analysis: Optional[Analysis]
    ) -> Optional[ComparisonSummary]:
        if not previous_analysis:
            return None

        prev_unresolved = [
            f for f in previous_analysis.findings
            if f.status in [FindingStatus.MISMATCH, FindingStatus.NEEDS_REVIEW]
        ]
        curr_unresolved = [
            f for f in current_findings
            if f.status in [FindingStatus.MISMATCH, FindingStatus.NEEDS_REVIEW]
        ]

        resolved_count = 0
        persistent_count = 0
        new_count = 0
        changed_count = 0

        resolved_ids: List[str] = []
        persistent_ids: List[str] = []
        new_ids: List[str] = []
        change_descriptions: List[str] = []

        # Index previous findings by field_name and category
        prev_map: Dict[str, Finding] = {f.field_name.lower(): f for f in previous_analysis.findings}
        curr_map: Dict[str, Finding] = {f.field_name.lower(): f for f in current_findings}

        # Check previously unresolved issues
        for prev_f in prev_unresolved:
            key = prev_f.field_name.lower()
            if key in curr_map:
                curr_f = curr_map[key]
                # Did it become a Match?
                if curr_f.status == FindingStatus.MATCH:
                    resolved_count += 1
                    resolved_ids.append(curr_f.id)
                    change_descriptions.append(
                        f"Resolved: '{prev_f.field_name}' previously was '{prev_f.status.value}' "
                        f"('{prev_f.artwork_value}') and now matches specification ('{curr_f.artwork_value}')."
                    )
                elif curr_f.status in [FindingStatus.MISMATCH, FindingStatus.NEEDS_REVIEW]:
                    persistent_count += 1
                    persistent_ids.append(curr_f.id)
                    if curr_f.status != prev_f.status or curr_f.artwork_value != prev_f.artwork_value:
                        changed_count += 1
                        change_descriptions.append(
                            f"Changed: '{prev_f.field_name}' updated from '{prev_f.status.value}' ({prev_f.artwork_value}) "
                            f"to '{curr_f.status.value}' ({curr_f.artwork_value})."
                        )
            else:
                # Disappeared from extraction - per spec: do not count as resolved solely because it disappeared
                persistent_count += 1
                change_descriptions.append(
                    f"Unverified: '{prev_f.field_name}' ({prev_f.status.value}) was not present in the current extraction and remains unresolved."
                )

        # Check newly detected issues in current analysis
        for curr_f in curr_unresolved:
            key = curr_f.field_name.lower()
            if key not in prev_map:
                new_count += 1
                new_ids.append(curr_f.id)
                change_descriptions.append(
                    f"Newly detected issue: '{curr_f.field_name}' ({curr_f.status.value}) — {curr_f.explanation}"
                )

        return ComparisonSummary(
            previous_analysis_id=previous_analysis.id,
            previous_timestamp=previous_analysis.timestamp,
            previous_unresolved_count=len(prev_unresolved),
            current_unresolved_count=len(curr_unresolved),
            resolved_count=resolved_count,
            persistent_count=persistent_count,
            new_count=new_count,
            changed_count=changed_count,
            resolved_issue_ids=resolved_ids,
            persistent_issue_ids=persistent_ids,
            new_issue_ids=new_ids,
            change_descriptions=change_descriptions
        )
