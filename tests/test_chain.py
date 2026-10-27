"""End-to-end chain test: SÜSIE demo slice on a temp store (offline, hermetic).

Covers the plan.md acceptance subset named in the design doc: ≥3 cited test
cases, comparator PASS/MISMATCH/NOT_EVALUATED with evidence links, missing
evidence never passes, conformance blocks by default, review separation
(author ≠ reviewer), and a clean-start run.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from itsg import demo
from itsg.conformance import check_conformance
from itsg.store import Store


class TestDemoChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._dir = tempfile.TemporaryDirectory()
        cls.store_root = Path(cls._dir.name) / "demo"
        demo.run_demo(cls.store_root, live=False, fresh=True)
        cls.store = Store(cls.store_root)

    @classmethod
    def tearDownClass(cls):
        cls._dir.cleanup()

    def findings(self) -> dict:
        return {f["id"]: f for f in self.store.all("finding")}

    def test_three_case_types_with_cited_expected_values(self):
        cases = self.store.all("test_case")
        types = sorted(c["case_type"] for c in cases)
        self.assertEqual(types, ["boundary", "invalid", "normal", "normal"])
        for case in cases:
            if case["case_type"] != "invalid":
                self.assertTrue(case["expected"], case["id"])
                self.assertTrue(case["expected_basis"], case["id"])
                self.assertEqual(case["review_status"], "approved")
        # invalid case carries no invented expected value
        invalid = next(c for c in cases if c["case_type"] == "invalid")
        self.assertEqual(invalid["expected"], {})

    def test_comparator_results_with_evidence_chain(self):
        findings = self.findings()
        self.assertEqual(findings["FIND-TC-1"]["status"], "PASS")
        self.assertEqual(findings["FIND-TC-2"]["status"], "MISMATCH")
        self.assertEqual(findings["FIND-TC-3"]["status"], "NOT_EVALUATED")
        self.assertEqual(findings["FIND-TC-4"]["status"], "PASS")
        # deliberate mismatch surfaces both values
        self.assertIn("20XX0101", findings["FIND-TC-2"]["reason"])
        self.assertIn("20XX0401", findings["FIND-TC-2"]["reason"])
        # every finding links its test case and execution
        self.assertIn("TC-2", findings["FIND-TC-2"]["links"])
        self.assertIn("RUN-2", findings["FIND-TC-2"]["links"])

    def test_missing_evidence_is_never_pass(self):
        findings = self.findings()
        self.assertNotEqual(findings["FIND-TC-3"]["status"], "PASS")
        self.assertIn("missing expected value", findings["FIND-TC-3"]["reason"])

    def test_report_and_conformance(self):
        report = self.store.get("report", "RPT-1")
        self.assertIsNotNone(report)
        self.assertFalse(report["compliance_claim"])
        artifact = json.loads(Path(report["artifact_ref"]).read_text(encoding="utf-8"))
        profile = json.loads(
            (demo.FIXTURES / "synthetic_template_profile.json").read_text(encoding="utf-8"))
        conformance = check_conformance(profile, artifact)
        self.assertEqual(conformance["status"], "pass")
        self.assertFalse(conformance["compliance_claim_allowed"])
        self.assertIsNone(artifact["official_form_id"])

    def test_review_separation_recorded(self):
        runs = {r["run_id"]: r for r in self.store.all("agent_run")}
        gates = self.store.all("gate")
        self.assertTrue(runs, "candidate runs must be recorded")
        for run in runs.values():
            self.assertTrue(run["review_required"])
        for gate in gates:
            self.assertTrue(gate["reviewer"])
            self.assertTrue(gate["rationale"])
        author_runs = {r["author"] for r in runs.values()}
        reviewers = {g["reviewer"] for g in gates}
        self.assertNotIn(OFFLINE_AUTHOR := "coding-agent offline draft (no LLM call)", reviewers)
        self.assertTrue(author_runs)

    def test_source_and_gates_recorded(self):
        source = self.store.get("source", "SRC-BP")
        self.assertEqual(source["version"], "13.3")
        self.assertEqual(source["valid_from"], "2027-01-01")
        self.assertEqual(source["status"], "approved")
        gate_ids = {g["gate"] for g in self.store.all("gate")}
        self.assertGreaterEqual(gate_ids, {"G0", "G1", "G3"})

    def test_store_event_log_appends(self):
        events = self.store.events()
        self.assertGreater(len(events), 20)
        self.assertEqual([e["seq"] for e in events], list(range(1, len(events) + 1)))


if __name__ == "__main__":
    unittest.main()
