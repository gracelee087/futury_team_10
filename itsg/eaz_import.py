"""Import Team 10's 30 sick-leave cases in the format of Beispielpapier §3.1 (TC-1) into the itsg store.

Cases come from Team 10's generator (harness/generate_eaz.py, Langfuse dataset team10-eaz-v1): the same 12
Sachverhalt fields as TC-1, 13 expected DTA fields mapped from the Sachverhalt by code, and a synthetic payroll
output (10 of them with one planted error). They hang under the existing criterion CRIT-EAZ-1 and are judged
here with the same comparator as TC-1 (itsg.comparator.compare). review_status "approved": format and two
sample cases were approved by Sohee Lee on 2026-10-27; that approval is written into expected_basis.

Run:
    python -m itsg.eaz_import --cases data/eaz_cases.json [--store data/demo]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from .bulk_cases import _put
from .comparator import compare
from .records import ExecutionRecord, FindingRecord, TemplateRecord, TestCaseRecord
from .renderer import render
from .store import Store
from .timeutil import utc_now

ROOT = Path(__file__).resolve().parent.parent
APPROVAL = "approved by Sohee Lee (2026-10-27, format + 2 sample cases)"


def run_import(store_root: Path, cases_path: Path) -> int:
    store = Store(store_root)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    stats: Counter = Counter()
    at = utc_now()
    for case in cases:
        tc = TestCaseRecord(
            id=case["id"], criterion_id="CRIT-EAZ-1",
            case_type="invalid" if case.get("must_flag") else "normal",
            inputs=case["sachverhalt"], expected=case["expected"],
            expected_basis=f"{case['expected_basis']} · {APPROVAL}", review_status="approved")
        ex = ExecutionRecord(
            id=f"RUN-{case['id']}", test_case_id=case["id"], vendor="synthetic payroll output (Team 10 harness)",
            software_version="harness", observed=case["observed"],
            evidence_ref=f"{cases_path.name}#{case['id']}", run_at=at)
        finding = compare(tc, ex, finding_id=f"FIND-{case['id']}")
        _put(store, "test_case", tc)
        _put(store, "execution", ex)
        _put(store, "finding", finding)
        stats[finding.status] += 1
    # re-render RPT-1 over every finding in the store (same as itsg.bulk_cases / itsg.mu_import)
    records = store._load_records()  # noqa: SLF001
    findings = [FindingRecord.from_dict(f) for f in records.get("finding", {}).values()]
    template = TemplateRecord.from_dict(records["template"][next(iter(records["template"]))])
    profile = json.loads((ROOT / "fixtures" / "synthetic_template_profile.json").read_text(encoding="utf-8"))
    case_meta = {i: {"case_id": i, "criterion_id": tc.get("criterion_id", "")}
                 for i, tc in records.get("test_case", {}).items()}
    report = render("RPT-1", template, profile, findings, store_root / "report.artifact.json", case_meta)
    from .conformance import check_conformance
    report.conformance = [check_conformance(profile, json.loads(Path(report.artifact_ref).read_text(encoding="utf-8")))]
    _put(store, "report", report)
    print(f"eaz import: {len(cases)} cases from {cases_path.name}: "
          + ", ".join(f"{k}={n}" for k, n in sorted(stats.items())))
    print(f"report RPT-1 re-rendered over {len(findings)} findings")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="itsg.eaz_import", description="import §3.1-style sick-leave cases")
    ap.add_argument("--store", default=str(ROOT / "data" / "demo"))
    ap.add_argument("--cases", required=True)
    a = ap.parse_args(argv)
    return run_import(Path(a.store), Path(a.cases))


if __name__ == "__main__":
    raise SystemExit(main())
