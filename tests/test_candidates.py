"""Tests for the system-agent candidate envelope and gate rules (itsg.candidates)."""
from __future__ import annotations

import unittest

from itsg.candidates import (
    BLOCKED,
    CANDIDATE,
    NEEDS_REVIEW,
    ROLE_REQUIREMENT_EXTRACTOR,
    ROLE_TEST_CASE_DESIGNER,
    ROLE_TEST_CHALLENGER,
    AgentRun,
    new_run,
    record_gate_decision,
)
from itsg.gates import GateDecision

CITE = [{"source_version_id": "SRCV-1", "locator": "S. 135, §3.12"}]


def extractor_run(**overrides) -> AgentRun:
    defaults = dict(
        role=ROLE_REQUIREMENT_EXTRACTOR, task_id="T10-018",
        provider="test", model_id="test-model", input_ids=["SRCV-1"],
        result={"requirements": [{"text_de": "x"}]}, citations=list(CITE), author="agent-a",
    )
    defaults.update(overrides)
    return new_run(**defaults)


class TestEnvelope(unittest.TestCase):
    def test_review_required_is_forced_on(self):
        run = extractor_run()
        self.assertTrue(run.review_required)
        self.assertEqual(run.status, CANDIDATE)
        self.assertEqual(run.model_revision, "unavailable")

    def test_roundtrip_rejects_unknown_fields(self):
        data = extractor_run().to_dict()
        data["fabricated_field"] = 1
        with self.assertRaises(ValueError):
            AgentRun.from_dict(data)

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError):
            new_run("legal_decider", "T10-018", "p", "m", [], {})

    def test_susie_assistant_role_is_registered_and_gate_free(self):
        from itsg import candidates
        self.assertIn(candidates.ROLE_SUSIE_ASSISTANT, candidates.ROLES)
        self.assertIsNone(candidates.ROLE_GATES[candidates.ROLE_SUSIE_ASSISTANT])
        run = candidates.new_run(
            candidates.ROLE_SUSIE_ASSISTANT, "T10-032", "hessian-ai-vllm-gateway",
            "vllm/GLM-Flash:Latest", [], result={}, author="susie-assistant",
        )
        self.assertEqual(run.role, "susie_assistant")
        self.assertTrue(run.review_required)

    def test_extractor_without_citation_downgrades_to_needs_review(self):
        run = extractor_run(citations=[])
        self.assertEqual(run.status, NEEDS_REVIEW)
        self.assertTrue(any("UNSUPPORTED" in e for e in run.validation_errors))

    def test_malformed_citation_is_recorded(self):
        run = extractor_run(citations=[{"source_version_id": "SRCV-1"}])
        self.assertTrue(any("locator" in e for e in run.validation_errors))


class TestAuthorReviewerSeparation(unittest.TestCase):
    def test_author_cannot_review_own_run(self):
        run = extractor_run(author="agent-a")
        with self.assertRaises(ValueError):
            record_gate_decision(run, "Agent-A", "approved", "self approval")

    def test_reviewer_identity_required(self):
        run = extractor_run(author="agent-a")
        with self.assertRaises(ValueError):
            record_gate_decision(run, "  ", "approved", "no reviewer")

    def test_gate_decision_records_reviewer_and_rationale(self):
        run = extractor_run(author="agent-a")
        decision = record_gate_decision(run, "human-owner", "approved", "checked vs source")
        self.assertIsInstance(decision, GateDecision)
        self.assertEqual(decision.gate, "G1")
        self.assertEqual(decision.reviewer, "human-owner")

    def test_challenger_is_recommendation_only(self):
        run = new_run(ROLE_TEST_CHALLENGER, "T10-018", "p", "m", ["CRIT-1"],
                      {"recommendation": "review"}, author="agent-b")
        with self.assertRaises(ValueError):
            record_gate_decision(run, "human-owner", "approved", "trying to approve")
        self.assertEqual(run.status, CANDIDATE)

    def test_designer_gates_at_g3(self):
        run = new_run(ROLE_TEST_CASE_DESIGNER, "T10-018", "p", "m", ["CRIT-1"],
                      {"cases": []}, author="designer-1")
        decision = record_gate_decision(run, "human-owner", "approved", "ok")
        self.assertEqual(decision.gate, "G3")

    def test_unknown_decision_word_rejected(self):
        run = extractor_run(author="agent-a")
        with self.assertRaises(ValueError):
            record_gate_decision(run, "human-owner", "auto-passed", "not a decision")


if __name__ == "__main__":
    unittest.main()
