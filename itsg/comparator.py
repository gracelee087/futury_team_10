"""Deterministic comparator — plan.md acceptance core.

Returns PASS, MISMATCH, or NOT_EVALUATED with a reason and evidence links.
Missing expected value, missing expected-value basis, unapproved test case,
or missing execution output NEVER produces a pass (fail closed). Plain
structural equality with field-level diffs only — no semantic model
judgment may override deterministic rules (agent-governance.md §4).
"""
from __future__ import annotations

import uuid

from .records import ExecutionRecord, FindingRecord, TestCaseRecord

STATUS_PASS = "PASS"
STATUS_MISMATCH = "MISMATCH"
STATUS_NOT_EVALUATED = "NOT_EVALUATED"


def _diff(expected, observed, prefix: str = "") -> list[str]:
    """Field-level differences between expected and observed structures."""
    diffs: list[str] = []
    if isinstance(expected, dict) and isinstance(observed, dict):
        for key in sorted(set(expected) | set(observed)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in expected:
                diffs.append(f"{path}: unexpected field in observed output")
            elif key not in observed:
                diffs.append(f"{path}: missing in observed output")
            else:
                diffs.extend(_diff(expected[key], observed[key], path))
    elif expected != observed:
        diffs.append(f"{prefix or 'value'}: expected {expected!r}, observed {observed!r}")
    return diffs


def compare(
    test_case: TestCaseRecord,
    execution: ExecutionRecord | None,
    finding_id: str | None = None,
) -> FindingRecord:
    """Compare observed execution output against the human-reviewed expected value."""
    links = [test_case.id] + ([execution.id] if execution else [])
    fid = finding_id or f"FIND-{uuid.uuid4().hex[:8]}"

    if test_case.review_status != "approved":
        return FindingRecord(
            fid,
            STATUS_NOT_EVALUATED,
            f"test case is not human-approved (review_status={test_case.review_status!r})",
            links,
        )
    if not test_case.expected:
        return FindingRecord(fid, STATUS_NOT_EVALUATED, "missing expected value", links)
    if not test_case.expected_basis:
        return FindingRecord(fid, STATUS_NOT_EVALUATED, "missing expected-value basis", links)
    if execution is None or execution.observed is None:
        return FindingRecord(fid, STATUS_NOT_EVALUATED, "missing execution output", links)

    diffs = _diff(test_case.expected, execution.observed)
    if diffs:
        shown = "; ".join(diffs[:10]) + (" ..." if len(diffs) > 10 else "")
        return FindingRecord(fid, STATUS_MISMATCH, shown, links)
    return FindingRecord(fid, STATUS_PASS, "observed output matches expected value", links)
