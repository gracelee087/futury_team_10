"""Tests for the workflow state machine (itsg.states) and gate decisions (itsg.gates)."""
from __future__ import annotations

import unittest

from itsg.gates import GateDecision
from itsg.states import State, can_transition, transition


class TestStateMachine(unittest.TestCase):
    def test_happy_path_chain_is_legal(self):
        chain = [
            State.INGESTED,
            State.SOURCE_CHECKED,
            State.SEGMENTED,
            State.REQUIREMENTS_CANDIDATE,
            State.HUMAN_APPROVED_REQUIREMENTS,
            State.CASES_CANDIDATE,
            State.HUMAN_APPROVED_CASES,
            State.EXECUTED,
            State.COMPARED,
            State.TEMPLATE_SELECTED,
            State.REPORT_RENDERED,
            State.TEMPLATE_CHECKED,
            State.HUMAN_SIGNED_OFF,
        ]
        for current, target in zip(chain, chain[1:]):
            self.assertTrue(can_transition(current, target), f"{current} -> {target}")
            self.assertEqual(transition(current, target), target)

    def test_gate_skip_is_illegal(self):
        with self.assertRaises(ValueError):
            transition(State.INGESTED, State.SEGMENTED)  # SOURCE_CHECKED skipped
        self.assertFalse(can_transition(State.INGESTED, State.HUMAN_SIGNED_OFF))

    def test_terminal_state_has_no_forward(self):
        self.assertFalse(can_transition(State.HUMAN_SIGNED_OFF, State.INGESTED))
        with self.assertRaises(ValueError):
            transition(State.HUMAN_SIGNED_OFF, State.COMPARED)

    def test_side_states_and_human_release(self):
        self.assertTrue(can_transition(State.SEGMENTED, State.BLOCKED))
        self.assertTrue(can_transition(State.BLOCKED, State.SEGMENTED))
        self.assertTrue(can_transition(State.NEEDS_REVIEW, State.HUMAN_APPROVED_REQUIREMENTS))

    def test_approval_states_are_distinct(self):
        self.assertIsNot(State.HUMAN_APPROVED_REQUIREMENTS, State.HUMAN_APPROVED_CASES)


class TestGateDecisions(unittest.TestCase):
    def test_valid_decision_round_trips(self):
        decision = GateDecision(
            gate="G0",
            reviewer="Team 10 product facilitator",
            decision="approved",
            rationale="official origin verified",
            affected_ids=["SRCV-1-A"],
        )
        self.assertEqual(decision.to_dict()["gate"], "G0")

    def test_missing_reviewer_fails_closed(self):
        with self.assertRaises(ValueError):
            GateDecision(gate="G0", reviewer="  ", decision="approved", rationale="ok")

    def test_missing_rationale_fails_closed(self):
        with self.assertRaises(ValueError):
            GateDecision(gate="G1", reviewer="human", decision="approved", rationale="")

    def test_unknown_gate_and_decision_rejected(self):
        with self.assertRaises(ValueError):
            GateDecision(gate="G9", reviewer="human", decision="approved", rationale="ok")
        with self.assertRaises(ValueError):
            GateDecision(gate="G1", reviewer="human", decision="auto-pass", rationale="ok")


if __name__ == "__main__":
    unittest.main()
