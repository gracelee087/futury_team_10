"""Tests for the report renderer and conformance checks (T10-018 demo slice)."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from itsg.comparator import STATUS_MISMATCH, STATUS_NOT_EVALUATED, STATUS_PASS
from itsg.conformance import check_conformance
from itsg.records import FindingRecord, TemplateRecord
from itsg.renderer import render

ROOT = Path(__file__).resolve().parent.parent
PROFILE = json.loads((ROOT / "fixtures" / "synthetic_template_profile.json").read_text(encoding="utf-8"))

TEMPLATE = TemplateRecord(id="TPL-SYNTH-1", official_form_id=None, version="synthetic-0.1",
                          status="needs_review")


def finding(fid: str, status: str, case_id: str = "TC-1") -> FindingRecord:
    return FindingRecord(fid, status, "demo reason", [case_id, "RUN-1"])


class TestRenderer(unittest.TestCase):
    def test_renders_synthetic_template_without_compliance_claim(self):
        report = render("RPT-1", TEMPLATE, PROFILE,
                        [finding("F-1", STATUS_PASS)], Path("/tmp") / "susie-test-rpt.json",
                        case_meta={"TC-1": {"case_id": "TC-1", "criterion_id": "CRIT-1"}},
                        generated_at="2026-10-26T00:00:00+00:00")
        self.assertFalse(report.compliance_claim)
        artifact = json.loads(Path(report.artifact_ref).read_text(encoding="utf-8"))
        self.assertFalse(artifact["compliance_claim"])
        self.assertIn("SYNTHETIC", artifact["template_warning"])
        self.assertEqual(artifact["results"][0]["case_id"], "TC-1")
        self.assertEqual(artifact["results"][0]["criterion_id"], "CRIT-1")
        self.assertEqual(list(artifact["results"][0].keys()), PROFILE["field_order"])
        self.assertEqual(artifact["field_labels"], PROFILE["labels"])
        Path(report.artifact_ref).unlink()

    def test_official_form_without_approval_is_blocked(self):
        official = TemplateRecord(id="TPL-OFF", official_form_id="FORM-1", version="1.0",
                                  status="needs_review")
        with self.assertRaises(ValueError):
            render("RPT-2", official, PROFILE, [finding("F-1", STATUS_PASS)],
                   Path("/tmp") / "susie-test-rpt2.json")

    def test_unknown_profile_is_blocked(self):
        with self.assertRaises(ValueError):
            render("RPT-3", TEMPLATE, {}, [finding("F-1", STATUS_PASS)],
                   Path("/tmp") / "susie-test-rpt3.json")

    def test_rendered_result_statuses_come_from_findings(self):
        report = render("RPT-4", TEMPLATE, PROFILE,
                        [finding("F-1", STATUS_PASS), finding("F-2", STATUS_MISMATCH),
                         finding("F-3", STATUS_NOT_EVALUATED, "TC-3")],
                        Path("/tmp") / "susie-test-rpt4.json", generated_at="2026-10-26T00:00:00+00:00")
        artifact = json.loads(Path(report.artifact_ref).read_text(encoding="utf-8"))
        self.assertEqual([row["result_status"] for row in artifact["results"]],
                         [STATUS_PASS, STATUS_MISMATCH, STATUS_NOT_EVALUATED])
        Path(report.artifact_ref).unlink()


class TestConformance(unittest.TestCase):
    def artifact(self) -> dict:
        report = render("RPT-C", TEMPLATE, PROFILE, [finding("F-1", STATUS_PASS, "TC-1")],
                        Path("/tmp") / "susie-test-rptc.json",
                        case_meta={"TC-1": {"case_id": "TC-1", "criterion_id": "CRIT-1"}},
                        generated_at="2026-10-26T00:00:00+00:00")
        artifact = json.loads(Path(report.artifact_ref).read_text(encoding="utf-8"))
        Path(report.artifact_ref).unlink()
        return artifact

    def test_rendered_artifact_passes_conformance(self):
        result = check_conformance(PROFILE, self.artifact())
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["compliance_claim_allowed"])

    def test_missing_required_field_fails(self):
        artifact = self.artifact()
        del artifact["results"][0]["reason"]
        result = check_conformance(PROFILE, artifact)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["checks"]["required_fields"]["pass"])

    def test_changed_field_order_fails(self):
        artifact = self.artifact()
        row = artifact["results"][0]
        artifact["results"][0] = {k: row[k] for k in reversed(list(row))}
        result = check_conformance(PROFILE, artifact)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("order" in p for p in result["checks"]["labels_and_order"]["problems"]))

    def test_changed_labels_fail(self):
        artifact = self.artifact()
        artifact["field_labels"] = {**PROFILE["labels"], "case_id": "Falsches Label"}
        result = check_conformance(PROFILE, artifact)
        self.assertEqual(result["status"], "failed")

    def test_invented_status_fails_value_mapping(self):
        artifact = self.artifact()
        artifact["results"][0]["result_status"] = "COMPLIANT"
        result = check_conformance(PROFILE, artifact)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("permitted" in p for p in
                            result["checks"]["value_mapping"]["problems"]))

    def test_unknown_profile_is_blocked_never_compliant(self):
        result = check_conformance({}, {"case_id": "TC-1"})
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["compliance_claim_allowed"])

    def test_conformance_never_authorizes_compliance(self):
        for artifact in (self.artifact(), {}, {"results": []}):
            self.assertFalse(check_conformance(PROFILE, artifact)["compliance_claim_allowed"])


if __name__ == "__main__":
    unittest.main()
