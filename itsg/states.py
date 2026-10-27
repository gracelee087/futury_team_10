"""Workflow state machine — architecture.md §9.

Main chain: INGESTED -> SOURCE_CHECKED -> SEGMENTED -> REQUIREMENTS_CANDIDATE
-> HUMAN_APPROVED -> CASES_CANDIDATE -> HUMAN_APPROVED -> EXECUTED -> COMPARED
-> TEMPLATE_SELECTED -> REPORT_RENDERED -> TEMPLATE_CHECKED -> HUMAN_SIGNED_OFF.

Missing evidence moves an item to BLOCKED or NEEDS_REVIEW; retries never
skip a gate (transitions are validated, not free-form). Release from
BLOCKED/NEEDS_REVIEW is a human decision and may target any main-chain
state at or before the blocking point.
"""
from __future__ import annotations

from enum import Enum


class State(str, Enum):
    INGESTED = "INGESTED"
    SOURCE_CHECKED = "SOURCE_CHECKED"
    SEGMENTED = "SEGMENTED"
    REQUIREMENTS_CANDIDATE = "REQUIREMENTS_CANDIDATE"
    # architecture.md §9 names the two approval states identically ("HUMAN_APPROVED");
    # the enum values are disambiguated here so they stay distinct members.
    HUMAN_APPROVED_REQUIREMENTS = "HUMAN_APPROVED_REQUIREMENTS"
    CASES_CANDIDATE = "CASES_CANDIDATE"
    HUMAN_APPROVED_CASES = "HUMAN_APPROVED_CASES"
    EXECUTED = "EXECUTED"
    COMPARED = "COMPARED"
    TEMPLATE_SELECTED = "TEMPLATE_SELECTED"
    REPORT_RENDERED = "REPORT_RENDERED"
    TEMPLATE_CHECKED = "TEMPLATE_CHECKED"
    HUMAN_SIGNED_OFF = "HUMAN_SIGNED_OFF"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


_CHAIN = [
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

_SIDE_STATES = (State.BLOCKED, State.NEEDS_REVIEW)

ALLOWED_TRANSITIONS: dict[State, frozenset[State]] = {}
for _i, _current in enumerate(_CHAIN):
    forward = {_CHAIN[_i + 1]} if _i + 1 < len(_CHAIN) else set()
    ALLOWED_TRANSITIONS[_current] = frozenset(forward | set(_SIDE_STATES))
for _side in _SIDE_STATES:
    # Human release from a side state: any main-chain state is targetable;
    # the decision and rationale are recorded as a GateDecision (itsg.gates).
    ALLOWED_TRANSITIONS[_side] = frozenset(_CHAIN)


def can_transition(current: State, target: State) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def transition(current: State, target: State) -> State:
    """Validate and return the target state; raises ValueError on an illegal move."""
    if not isinstance(current, State) or not isinstance(target, State):
        raise ValueError(f"states must be State enum members, got {current!r} -> {target!r}")
    if not can_transition(current, target):
        raise ValueError(f"illegal transition {current.value} -> {target.value} (gates cannot be skipped)")
    return target
