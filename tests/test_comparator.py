"""Tests for the deterministic comparator (itsg.comparator) — the fail-closed core."""
from __future__ import annotations

import unittest

from itsg.comparator import STATUS_MISMATCH, STATUS_NOT_EVALUATED, STATUS_PASS, compare
from itsg.records import ExecutionRecord, TestCaseRecord


def approved_case(**overrides) -> TestCaseRecord:
    defaults = dict(
        id="TC-1",
        criterion_id="CRIT-1",
        case_type="normal",
        expected={"mitteilung": {"betrag_cent": 1000, "anzahl": 2}},
        expected_basis="demo fixture (synthetic, not a legal value)",
        review_status="approved",
    )
    defaults.update(overrides)
    return TestCaseRecord(**defaults)


def execution(**overrides) -> ExecutionRecord:
    defaults = dict(
        id="RUN-1",
        test_case_id="TC-1",
        vendor="Demo only",
        software_version="unknown",
        observed={"mitteilung": {"betrag_cent": 1000, "anzahl": 2}},
        evidence_ref="fixtures/run1.json",
    )
    defaults.update(overrides)
    return ExecutionRecord(**defaults)


class TestComparatorFailClosed(unittest.TestCase):
    def test_unapproved_case_never_passes(self):
        result = compare(approved_case(review_status="draft"), execution())
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)
        self.assertIn("not human-approved", result.reason)

    def test_missing_expected_value_never_passes(self):
        result = compare(approved_case(expected={}), execution())
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)
        self.assertIn("missing expected value", result.reason)

    def test_missing_expected_basis_never_passes(self):
        result = compare(approved_case(expected_basis=""), execution())
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)
        self.assertIn("missing expected-value basis", result.reason)

    def test_missing_execution_never_passes(self):
        self.assertEqual(compare(approved_case(), None).status, STATUS_NOT_EVALUATED)
        result = compare(approved_case(), execution(observed=None))
        self.assertEqual(result.status, STATUS_NOT_EVALUATED)
        self.assertIn("missing execution output", result.reason)

    def test_blocked_case_status_is_never_pass(self):
        result = compare(approved_case(review_status="rejected"), execution())
        self.assertNotEqual(result.status, STATUS_PASS)


class TestComparatorResults(unittest.TestCase):
    def test_exact_match_passes(self):
        result = compare(approved_case(), execution())
        self.assertEqual(result.status, STATUS_PASS)
        self.assertIn("TC-1", result.links)
        self.assertIn("RUN-1", result.links)

    def test_field_mismatch_reports_both_values(self):
        observed = {"mitteilung": {"betrag_cent": 1500, "anzahl": 2}}
        result = compare(approved_case(), execution(observed=observed))
        self.assertEqual(result.status, STATUS_MISMATCH)
        self.assertIn("betrag_cent", result.reason)
        self.assertIn("1000", result.reason)
        self.assertIn("1500", result.reason)

    def test_nested_and_missing_fields(self):
        observed = {"mitteilung": {"betrag_cent": 1000}}
        result = compare(approved_case(), execution(observed=observed))
        self.assertEqual(result.status, STATUS_MISMATCH)
        self.assertIn("anzahl", result.reason)

        extra = {"mitteilung": {"betrag_cent": 1000, "anzahl": 2, "extra": 1}}
        result = compare(approved_case(), execution(observed=extra))
        self.assertEqual(result.status, STATUS_MISMATCH)
        self.assertIn("unexpected field", result.reason)

    def test_finding_id_is_stable_when_given(self):
        result = compare(approved_case(), execution(), finding_id="FIND-fixed")
        self.assertEqual(result.id, "FIND-fixed")


if __name__ == "__main__":
    unittest.main()
