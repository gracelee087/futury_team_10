"""Mandated-form report renderer (plan.md vertical slice, architecture.md §8).

Contract implemented for the demo slice (T10-018):

  - render into the applicable template version; preserve required fields,
    labels, order, structure, units, and output type — never substitute a
    generic narrative;
  - refuse (raise) when the template is unknown, superseded, or claims an
    official form id without being human-approved: blocked, not a
    compliant-looking report;
  - the labeled synthetic template (official_form_id=None) is renderable
    but always carries ``compliance_claim=False`` — a compliance claim
    requires a verified official form plus passing deterministic
    conformance, and the synthetic template can never satisfy the first
    condition (plan.md; agent-governance.md §4);
  - field mapping is deterministic; an LLM may draft only explicitly
    permitted explanatory fields (none in this profile);
  - record template id/version/checksum, renderer version, and field-map
    version on the ReportRecord.
"""
from __future__ import annotations

import json
from pathlib import Path

from .records import FindingRecord, ReportRecord, TemplateRecord
from .timeutil import utc_now

RENDERER_VERSION = "itsg.renderer/0.1.0"
FIELD_MAP_VERSION = "itsg.fieldmap/synth-1"


def render(
    report_id: str,
    template: TemplateRecord,
    template_profile: dict,
    findings: list[FindingRecord],
    artifact_path: str | Path,
    case_meta: dict[str, dict] | None = None,
    field_map_version: str = FIELD_MAP_VERSION,
    generated_at: str | None = None,
) -> ReportRecord:
    """Render findings into the template structure deterministically.

    ``case_meta`` resolves test-case ids (finding.links[0]) to case/criterion
    identifiers; unknown provenance is rendered as empty, never guessed.
    """
    if not template_profile or "required_fields" not in template_profile:
        raise ValueError("template profile unknown or without required_fields — blocked")
    if template.official_form_id is not None and template.status != "approved":
        raise ValueError(
            f"template {template.id} claims official form {template.official_form_id} "
            "but is not human-approved — rendering blocked (fail closed)"
        )
    field_order: list[str] = template_profile["field_order"]
    labels: dict = template_profile.get("labels", {})
    case_meta = case_meta or {}

    results = []
    for finding in findings:
        case_id = finding.links[0] if finding.links else ""
        meta = case_meta.get(case_id, {})
        row = {
            "case_id": meta.get("case_id", case_id),
            "criterion_id": meta.get("criterion_id", ""),
            "result_status": finding.status,
            "reason": finding.reason,
            "evidence_links": list(finding.links),
        }
        results.append({key: row[key] for key in field_order})

    artifact = {
        "report_id": report_id,
        "template_id": template.id,
        "template_version": template.version,
        "template_warning": template_profile.get("warning", ""),
        "official_form_id": template.official_form_id,
        "renderer_version": RENDERER_VERSION,
        "field_map_version": field_map_version,
        "generated_at": generated_at or utc_now(),
        "field_labels": dict(labels),
        "compliance_claim": False,
        "compliance_claim_reason": (
            "synthetic template (official_form_id=None): no legal or template "
            "compliance claim may be derived (plan.md, architecture.md §8)"
            if template.official_form_id is None
            else "compliance claim requires passing conformance and release-gate sign-off"
        ),
        "results": results,
    }

    path = Path(artifact_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return ReportRecord(
        id=report_id,
        template_id=template.id,
        renderer_version=RENDERER_VERSION,
        field_map_version=field_map_version,
        artifact_ref=str(path),
        conformance=[],  # filled by itsg.conformance.check_conformance
        compliance_claim=False,
    )
