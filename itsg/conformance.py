"""Deterministic template conformance checks (plan.md acceptance criteria).

Unknown template/profile or unsupported requirement blocks conformance; a
failed or unknown check blocks a compliance claim. An LLM-only visual or
semantic opinion is insufficient (agent-governance.md §4) — these checks
are deterministic field/structure comparisons.

Status vocabulary: ``pass`` | ``failed`` | ``blocked``. The overall status
is ``pass`` only when every check passes; any blocked check blocks the
whole result (fail closed). A passing conformance NEVER implies a
compliance claim: that additionally requires a verified official form
(synthetic templates carry official_form_id=None) and release-gate
sign-off.
"""
from __future__ import annotations

import json

REQUIRED_CHECKS = ("required_fields", "labels_and_order", "output_type", "value_mapping")


def check_required_fields(template_profile: dict, artifact: dict) -> list[str]:
    """Return the required template fields missing from the rendered artifact.

    Fail closed: a profile without ``required_fields`` is itself a blocking
    problem, reported as such rather than treated as "nothing required".
    Artifacts with a ``results`` list (one row per case) carry the required
    fields per row; flat artifacts are checked at the top level.
    """
    if "required_fields" not in template_profile:
        return ["<profile>: template profile has no required_fields — cannot verify (blocked)"]
    required = template_profile["required_fields"]
    if not isinstance(required, list):
        return ["<profile>: required_fields must be a list"]
    rows = artifact.get("results")
    if isinstance(rows, list):
        missing: list[str] = []
        for idx, row in enumerate(rows):
            missing.extend(
                f"results[{idx}]: missing required field {name!r}"
                for name in required
                if name not in row
            )
        return missing
    return [name for name in required if name not in artifact]


def check_labels_and_order(template_profile: dict, artifact: dict) -> list[str]:
    """Artifact keys must appear in the profile's field_order with the profile's labels.

    Rendered rows live under ``results``; each row is checked against
    ``field_order`` (exact sequence) and ``labels`` (declared display label).
    """
    problems: list[str] = []
    field_order = template_profile.get("field_order")
    if not isinstance(field_order, list) or not field_order:
        return ["<profile>: no field_order declared — cannot verify (blocked)"]
    labels = template_profile.get("labels", {})
    if not labels:
        return ["<profile>: no labels declared — cannot verify (blocked)"]
    rows = artifact.get("results")
    if not isinstance(rows, list) or not rows:
        return ["artifact: no results rows to check (blocked)"]
    for idx, row in enumerate(rows):
        keys = list(row.keys())
        if keys != field_order:
            problems.append(
                f"results[{idx}]: field order {keys} != profile order {field_order}"
            )
        for key in field_order:
            if key not in labels:
                problems.append(f"results[{idx}]: no label declared for field {key!r}")
    header_labels = artifact.get("field_labels")
    if header_labels != labels:
        problems.append(
            "artifact: field_labels header does not match the profile labels"
        )
    return problems


def check_output_type(template_profile: dict, artifact: dict) -> list[str]:
    """The artifact must serialize to the declared output type (json here)."""
    declared = template_profile.get("output_type")
    if not declared:
        return ["<profile>: no output_type declared — cannot verify (blocked)"]
    problems: list[str] = []
    try:
        json.dumps(artifact, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        problems.append(f"artifact: not serializable as JSON: {exc}")
    if declared == "json" and not isinstance(artifact, dict):
        problems.append("artifact: declared output_type json but artifact is not an object")
    if declared != "json":
        problems.append(
            f"<profile>: output_type {declared!r} unsupported by this checker — blocked"
        )
    return problems


def check_value_mapping(template_profile: dict, artifact: dict) -> list[str]:
    """Result statuses must be in the profile's permitted vocabulary; ids non-empty."""
    permitted = template_profile.get("permitted_result_status")
    if not permitted:
        return ["<profile>: no permitted_result_status declared — cannot verify (blocked)"]
    problems: list[str] = []
    for idx, row in enumerate(artifact.get("results", [])):
        status = row.get("result_status")
        if status not in permitted:
            problems.append(
                f"results[{idx}]: result_status {status!r} not in permitted vocabulary"
            )
        for id_field in ("case_id", "criterion_id"):
            if id_field in template_profile.get("required_fields", []) and not row.get(id_field):
                problems.append(f"results[{idx}]: required id field {id_field!r} is empty")
    return problems


def check_conformance(template_profile: dict, artifact: dict) -> dict:
    """Run all REQUIRED_CHECKS and return a structured result.

    Fail-closed: unknown or blocked checks can never produce an overall
    ``pass``. ``compliance_claim_allowed`` stays False for a synthetic
    template profile (official_form_id None) regardless of check outcomes.
    """
    checks: dict[str, dict] = {}
    profile_known = bool(template_profile) and "required_fields" in template_profile

    missing = check_required_fields(template_profile, artifact)
    checks["required_fields"] = {"missing": missing, "pass": profile_known and not missing}

    for name, problems in (
        ("labels_and_order", check_labels_and_order(template_profile, artifact)),
        ("output_type", check_output_type(template_profile, artifact)),
        ("value_mapping", check_value_mapping(template_profile, artifact)),
    ):
        blocked = any(p.startswith("<profile>:") for p in problems)
        checks[name] = {
            "problems": problems,
            "pass": not problems,
            "blocked": blocked,
        }

    all_pass = all(check["pass"] and not check.get("blocked") for check in checks.values())
    any_blocked = any(check.get("blocked") for check in checks.values())
    if any_blocked:
        status = "blocked"
    elif all_pass:
        status = "pass"
    else:
        status = "failed"
    return {
        "status": status,
        "checks": checks,
        "compliance_claim_allowed": False,
        "reason": (
            "synthetic template profile: conformance checks are structural only and "
            "cannot authorize a legal or template compliance claim"
            if profile_known
            else "unknown template profile — conformance blocked (never compliant)"
        ),
    }
