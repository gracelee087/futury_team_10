"""Tests for the typed records (itsg.records) — plan.md minimal data contract."""
from __future__ import annotations

import unittest

from itsg.records import (
    FindingRecord,
    SourceRecord,
    TestCaseRecord,
    TemplateRecord,
)


class TestRecords(unittest.TestCase):
    def test_source_matches_plan_contract_keys(self):
        data = SourceRecord(id="SRC-1", title="Demo fixture", issuer="ITSG", version="13.1").to_dict()
        for key in ("id", "title", "issuer", "version", "valid_from", "checksum"):
            self.assertIn(key, data)

    def test_template_defaults_block_until_reviewed(self):
        template = TemplateRecord(id="TPL-1")
        self.assertEqual(template.status, "needs_review")
        self.assertIsNone(template.official_form_id)  # synthetic template marker

    def test_test_case_defaults_fail_closed(self):
        case = TestCaseRecord(id="TC-1")
        self.assertEqual(case.review_status, "draft")
        self.assertEqual(case.expected, {})
        self.assertEqual(case.expected_basis, "")

    def test_finding_status_vocabulary(self):
        finding = FindingRecord(id="FIND-1", status="NOT_EVALUATED", reason="missing evidence")
        self.assertEqual(finding.to_dict()["status"], "NOT_EVALUATED")

    def test_from_dict_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            SourceRecord.from_dict({"id": "SRC-1", "totally_unknown": 1})

    def test_from_dict_round_trip(self):
        record = TemplateRecord(id="TPL-1", version="synthetic-0.1", status="approved")
        self.assertEqual(TemplateRecord.from_dict(record.to_dict()), record)


if __name__ == "__main__":
    unittest.main()
