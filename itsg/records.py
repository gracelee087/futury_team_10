"""Typed records for the MVP vertical slice — plan.md minimal data contract, 1:1.

Status vocabularies (plain strings; validate at boundaries):

  source/template/requirement: needs_review | candidate | approved | rejected | superseded
  criterion.review_status:     draft | approved | rejected
  test_case.review_status:     draft | approved | rejected
  finding.status:              PASS | MISMATCH | NOT_EVALUATED  (never a PASS without evidence)

The comparator and gates enforce the fail-closed behavior; these records
only carry the data. Unknown fields are rejected when loading stored JSON.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields


class _Record:
    def to_dict(self) -> dict:
        return asdict(self)  # type: ignore[attr-defined]

    @classmethod
    def from_dict(cls, data: dict):
        """Rebuild from stored JSON; unknown keys are rejected (agent-governance.md §3)."""
        known = {f.name for f in fields(cls)}  # type: ignore[arg-type]
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown {cls.__name__} fields: {unknown}")
        return cls(**data)


@dataclass
class SourceRecord(_Record):
    """plan.md: issuer/origin, version/date, checksum, citation basis."""

    id: str
    title: str = ""
    issuer: str = ""
    version: str = ""
    valid_from: str | None = None
    checksum: str = ""
    status: str = "needs_review"
    notes: str = ""


@dataclass
class TemplateRecord(_Record):
    """Applicable report form/template; synthetic templates never carry official_form_id."""

    id: str
    official_form_id: str | None = None
    version: str = ""
    valid_from: str | None = None
    source_id: str = ""
    checksum: str = ""
    status: str = "needs_review"


@dataclass
class RequirementRecord(_Record):
    """Cited requirement candidate; human approval moves it forward (gate G1)."""

    id: str
    text: str = ""
    source_id: str = ""
    citation: str = ""  # page/section locator
    status: str = "needs_review"
    working_translation_en: str | None = None


@dataclass
class CriterionRecord(_Record):
    """Approved testable criterion derived from a requirement (gate G3)."""

    id: str
    requirement_id: str = ""
    description: str = ""
    expected_basis: str = ""
    review_status: str = "draft"


@dataclass
class TestCaseRecord(_Record):
    """Normal / boundary / invalid case tied to a criterion; expected values come
    from a human-reviewed basis, never from model memory."""

    id: str
    criterion_id: str = ""
    case_type: str = "normal"  # normal | boundary | invalid
    inputs: dict = field(default_factory=dict)
    expected: dict = field(default_factory=dict)
    expected_basis: str = ""
    review_status: str = "draft"


@dataclass
class ExecutionRecord(_Record):
    """Observed execution output — distinct from vendor documentation by type."""

    id: str
    test_case_id: str = ""
    vendor: str = ""
    software_version: str = "unknown"
    observed: dict | None = None
    evidence_ref: str = ""
    run_at: str = ""


@dataclass
class FindingRecord(_Record):
    """Comparator result with evidence links; status is one of PASS/MISMATCH/NOT_EVALUATED."""

    id: str
    status: str
    reason: str = ""
    links: list[str] = field(default_factory=list)


@dataclass
class ReportRecord(_Record):
    """Rendered report; compliance_claim stays False unless template + conformance prove it."""

    id: str
    template_id: str = ""
    renderer_version: str = ""
    field_map_version: str = ""
    artifact_ref: str = ""
    conformance: list[dict] = field(default_factory=list)
    compliance_claim: bool = False


@dataclass
class ReviewRecord(_Record):
    """One human review event (who, what, when, decision) for the audit trail."""

    reviewer: str
    decision: str
    timestamp: str
    target_id: str = ""
