"""Bulk-feed the full synthetic case corpus into the itsg store (T10-044).

The T10-018 demo slice writes exactly 4 test cases into the store, so the
SÜSIE UI shows 4 cases. The generated corpus (300 cases with ground truth in
``data/testcases.json``) lives outside the store and never reached it.

This driver runs every corpus case through the SAME reviewer pipeline the
harness uses (synthetic TEEL0 from the real ITSG file → ``run_review.parse_teel0``
→ ``run_review.dbvo_findings``) and records the results as store records:

  test_case   one per corpus case (grouped under criterion CRIT-DBVO-1)
  execution   the parsed software output (fabricated generator data)
  finding     status derived deterministically from the reviewer's checks:
                any MISMATCH/BLOCKED check → MISMATCH (never a pass — fail closed)
                only NEEDS_REVIEW checks  → NOT_EVALUATED (human review needed)
                only PASS/no findings     → PASS
  report      re-renders RPT-1 over ALL findings in the store (upsert)

The corpus is synthetic generator data with recorded ground truth — no real
payroll or personal data, no compliance claim. Prerequisite: a store prepared
by ``python3 -m itsg.demo --fresh`` (source/template/requirement records).

Run:

    python3 -m itsg.bulk_cases [--store data/demo] [--limit N]
                               [--cases testcases.json] [--fresh-report]
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .comparator import STATUS_MISMATCH, STATUS_NOT_EVALUATED, STATUS_PASS
from .gates import GateDecision
from .records import (
    CriterionRecord,
    ExecutionRecord,
    FindingRecord,
    TemplateRecord,
    TestCaseRecord,
)
from .renderer import render
from .store import Store
from .timeutil import utc_now

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.run_harness import RULES_VERSION, review  # noqa: E402

REVIEWER = "human-owner (solo mode, provisional §9 default #7)"


def _put(store: Store, kind: str, record) -> dict:
    return store.put(kind, record.to_dict() if hasattr(record, "to_dict") else record)


CRIT_DBVO = "CRIT-DBVO-1"
VENDOR = "Synthetic generator (fabrizierte Daten)"
SOFTWARE_VERSION = "generator-1.0"
TEEL0_TEMPLATE = ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"

# Ground-truth taxonomy → the store's case_type vocabulary:
#   clean case            → normal
#   defect (a check fires) → boundary
#   ambiguous (no definitive expected value) → invalid (no official expected record)
_CASE_TYPE = {"clean": "normal", "defect": "boundary", "ambiguous": "invalid"}


def case_type_for(case: dict) -> str:
    if case.get("must_flag") == "NEEDS_REVIEW":
        return _CASE_TYPE["ambiguous"]
    if case.get("must_flag"):
        return _CASE_TYPE["defect"]
    return _CASE_TYPE["clean"]


def expected_for(case: dict) -> dict:
    """Display expectation: the official expected DBVO, or the decision verdict."""
    expected = case.get("expected") or {}
    if expected.get("dbvo"):
        return expected["dbvo"]
    return {"send_41": expected.get("send_41"), "rule": expected.get("rule")}


def finding_from_checks(case: dict, findings: list[dict], tc_id: str, run_id: str) -> FindingRecord:
    """Map the reviewer's per-check findings onto one store finding, fail closed."""
    links = [tc_id, run_id]
    flagged = [f for f in findings if f.get("status") in ("MISMATCH", "BLOCKED")]
    needs = [f for f in findings if f.get("status") == "NEEDS_REVIEW"]
    if flagged:
        parts = [
            f"{f['id']} ({f['status']}): {f.get('actual') or f.get('reason') or 'deviation'}"
            for f in flagged[:10]
        ]
        reason = "; ".join(parts) + (" ..." if len(flagged) > 10 else "")
        return FindingRecord(f"FIND-{tc_id}", STATUS_MISMATCH, reason, links)
    if needs:
        reason = "; ".join(f"{f['id']}: {f.get('reason') or 'needs human review'}" for f in needs[:10])
        return FindingRecord(f"FIND-{tc_id}", STATUS_NOT_EVALUATED, f"NEEDS_REVIEW — {reason}", links)
    return FindingRecord(
        f"FIND-{tc_id}", STATUS_PASS,
        "reviewer raised no findings; observed output matches the expected record", links)


def run_bulk(store_root: Path, cases_file: str, limit: int | None) -> int:
    store = Store(store_root)
    records = store._load_records()  # noqa: SLF001 — single-process bridge, same as webserver

    missing = [k for k in ("source", "template", "requirement") if not records.get(k)]
    if missing:
        print(f"store {store_root} is missing {missing} — run `python3 -m itsg.demo --fresh` first")
        return 2

    cases = json.loads((ROOT / "data" / cases_file).read_text(encoding="utf-8"))
    if limit:
        cases = cases[:limit]
    raw = TEEL0_TEMPLATE.read_text(encoding="latin-1")

    # Criterion for the DBVO record corpus + recorded basis (solo-mode reviewer).
    if CRIT_DBVO not in records.get("criterion", {}):
        crit = CriterionRecord(
            id=CRIT_DBVO, requirement_id="REQ-VOER-1",
            description="Das übermittelte DBVO-Ergebnis (Abgabegrund 41) entspricht dem "
                        "offiziellen Erwartungsdatensatz, und die Prüffehler F1–F7/C9–C13 "
                        "treten genau bei den durch die Ground Truth markierten Abweichungen auf.",
            expected_basis=f"generator ground truth data/{cases_file} · {RULES_VERSION}",
            review_status="draft")
        _put(store, "criterion", crit)
        gate = GateDecision(
            "G3", REVIEWER, "approved",
            "Synthetic corpus with recorded ground truth (data/testcases.json); no real "
            "payroll data, no legal-meaning approval — expected values come from the "
            "documented generator taxonomy, cross-checked by harness runs",
            affected_ids=[CRIT_DBVO],
            conditions=["expected values are generator ground truth, not an official "
                        "Beispielpapier record; NOT a compliance claim"])
        _put(store, "gate", {"id": f"GATE-G3-bulk-{gate.decided_at}", **gate.to_dict()})
        crit.review_status = "approved"
        _put(store, "criterion", crit)

    # Idempotency: re-running replaces the same ids (upsert), never duplicates.
    existing = set(records.get("test_case", {}))
    stats: Counter = Counter()
    executed_at = utc_now()
    with tempfile.TemporaryDirectory() as tmp:
        for case in cases:
            tc_id = case["id"]
            tc = TestCaseRecord(
                id=tc_id, criterion_id=CRIT_DBVO, case_type=case_type_for(case),
                inputs=case.get("scenario") or {},
                expected=expected_for(case),
                expected_basis=f"{case.get('category', '')} ({case.get('group', '')} — "
                               f"generator ground truth, data/{cases_file})",
                review_status="approved")
            _put(store, "test_case", tc)

            run_id = f"RUN-{tc_id}"
            if "observed_dbvo" not in case:
                # Story 4/6-style case without a DBVO checker: record it, never fake a result.
                _put(store, "execution", ExecutionRecord(
                    id=run_id, test_case_id=tc_id, vendor=VENDOR,
                    software_version=SOFTWARE_VERSION, observed=None,
                    evidence_ref=f"data/{cases_file}#{tc_id} (no DBVO checker)",
                    run_at=executed_at))
                _put(store, "finding", FindingRecord(
                    f"FIND-{tc_id}", STATUS_NOT_EVALUATED,
                    "no DBVO checker for this case kind (not evaluated, never a pass)",
                    [tc_id, run_id]))
                stats["NOT_EVALUATED"] += 1
                continue

            obs, checks = review(case, raw, tmp)
            # The execution's observed value is the fabricated software output, in the
            # same shape as the expected record (the reviewer's parsed TEEL0 view stays
            # internal to the verdict; on a parse failure nothing usable was observed).
            observed = case["observed_dbvo"] if obs is not None else None
            _put(store, "execution", ExecutionRecord(
                id=run_id, test_case_id=tc_id, vendor=VENDOR,
                software_version=SOFTWARE_VERSION, observed=observed,
                evidence_ref=f"data/{cases_file}#{tc_id}",
                run_at=executed_at))
            finding = finding_from_checks(case, checks, tc_id, run_id)
            _put(store, "finding", finding)
            stats[finding.status] += 1
            if tc_id in existing:
                stats["replaced"] += 1

    # Re-render the report over ALL findings now in the store (upsert RPT-1).
    records = store._load_records()  # noqa: SLF001
    findings = [FindingRecord.from_dict(f) for f in records.get("finding", {}).values()]
    template = TemplateRecord.from_dict(records["template"][next(iter(records["template"]))])
    profile = json.loads((ROOT / "fixtures" / "synthetic_template_profile.json").read_text(encoding="utf-8"))
    case_meta = {
        tc_id: {"case_id": tc_id, "criterion_id": tc.get("criterion_id", "")}
        for tc_id, tc in records.get("test_case", {}).items()
    }
    report = render("RPT-1", template, profile, findings,
                    store_root / "report.artifact.json", case_meta)
    from .conformance import check_conformance
    artifact = json.loads(Path(report.artifact_ref).read_text(encoding="utf-8"))
    report.conformance = [check_conformance(profile, artifact)]
    _put(store, "report", report)

    print(f"bulk feed complete: {store_root}")
    print(f"  corpus: {len(cases)} cases from data/{cases_file}"
          + (f" (limit {limit})" if limit else "")
          + (f", {stats['replaced']} replaced" if stats["replaced"] else ""))
    print("  findings: " + ", ".join(f"{k}={v}" for k, v in sorted(stats.items()) if k != "replaced"))
    print(f"  report RPT-1 re-rendered over {len(findings)} findings → {report.artifact_ref} "
          f"(conformance {report.conformance[0]['status']}, compliance_claim=False)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itsg.bulk_cases", description="feed the full case corpus into the store")
    parser.add_argument("--store", default=str(ROOT / "data" / "demo"))
    parser.add_argument("--cases", default="testcases.json", help="case file in data/ (default: testcases.json)")
    parser.add_argument("--limit", type=int, help="feed only the first N cases (smoke runs)")
    args = parser.parse_args(argv)
    return run_bulk(Path(args.store), args.cases, args.limit)


if __name__ == "__main__":
    sys.exit(main())
