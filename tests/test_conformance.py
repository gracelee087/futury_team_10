"""Tests for conformance checks (itsg.conformance) — fail closed on unknown profiles."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from itsg.conformance import check_conformance, check_required_fields

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "synthetic_template.json"


class TestRequiredFields(unittest.TestCase):
    def test_complete_artifact_passes_required_fields(self):
        profile = json.loads(FIXTURE.read_text(encoding="utf-8"))
        artifact = {
            "case_id": "TC-1",
            "criterion_id": "CRIT-1",
            "result_status": "PASS",
            "reason": "matches fixture",
            "evidence_links": ["SRC-1", "TC-1", "RUN-1"],
        }
        self.assertEqual(check_required_fields(profile, artifact), [])

    def test_missing_fields_are_reported(self):
        profile = {"required_fields": ["case_id", "result_status"]}
        self.assertEqual(check_required_fields(profile, {"case_id": "TC-1"}), ["result_status"])

    def test_unknown_profile_blocks(self):
        self.assertEqual(
            check_required_fields({}, {"case_id": "TC-1"}),
            ["<profile>: template profile has no required_fields — cannot verify (blocked)"],
        )

    def test_conformance_defaults_to_blocked(self):
        profile = {"required_fields": ["case_id"]}
        result = check_conformance(profile, {"case_id": "TC-1"})
        self.assertEqual(result["status"], "blocked")  # never compliant by default
        self.assertTrue(result["checks"]["required_fields"]["pass"])

    def test_synthetic_template_is_labeled_non_official(self):
        profile = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertIsNone(profile["official_form_id"])
        self.assertIn("SYNTHETIC", profile["warning"])
        self.assertIn("NOT", profile["warning"])


if __name__ == "__main__":
    unittest.main()
