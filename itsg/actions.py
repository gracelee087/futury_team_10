"""SÜSIE action registry — the fail-closed whitelist of operations the chat
layer may propose and execute (task 3, SÜSIE assistant backend).

The assistant never gets free rein: every action must be in one of three
explicit sets, and anything that changes state needs a fresh, single-use,
unexpired confirmation token; anything that records a human gate decision
additionally needs a non-blank human reviewer and a gate id inside that
action's allowed set. Every refusal raises ``PermissionError`` with a plain
reason string (the web server maps it to HTTP 403). Unknown action ids at
propose time raise ``ValueError``.

Confirmation is proposal-bound: a token is only valid for the exact params
that were proposed (compared as canonical JSON), so a human's "yes" can never
be replayed against different parameters. Gate executions additionally
refuse the assistant identity as reviewer (a human decides, never the agent)
and enforce the G0–G6 ordering — gates cannot be skipped.

Every successful execution appends exactly one ``action_audit`` record to
the store (read-only, mutating, and gate alike), so the append-only trail
carries one event per executed action. Gate executions record their
``GateDecision`` in addition to that audit record.

`GateDecision` itself validates reviewer/rationale (itsg.gates) — this
module's job is the access control *before* that delegation, plus stamping
the result with ``decision_maker: <reviewer>`` and
``executor: "susie-assistant"`` so the store never shows an agent as the
decision maker.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from uuid import uuid4

from . import gates
from .store import Store
from .timeutil import utc_now

# -- whitelists (verbatim from the task brief) --------------------------------

READ_ONLY_ACTIONS = (
    "select_case", "open_evidence", "filter_cases", "jump_to_source",
    "show_comparison", "switch_mode", "start_over", "go_back",
    "next_case", "prev_case",
)
MUTATING_ACTIONS = (
    "save_note", "export_report", "run_comparison", "initiate_review_flow",
)
DECISION_GATE_ACTIONS: dict[str, set[str]] = {
    "record_review_state": {"G4", "G5"},
    "record_conformance": {"G5"},
    "request_release": {"G6"},
}

CONFIRM_TTL_S = 300  # a confirmation token lives five minutes, then it is dead

# token -> (expiry, session_id, payload {"action_id": ..., "params": ...}),
# guarded by _LOCK so concurrent proposals can never race the pending map.
_PENDING: dict[str, tuple[float, str, dict]] = {}
_LOCK = threading.Lock()


def _now() -> float:
    """Clock seam: tests monkeypatch this to simulate expiry."""
    return time.time()


def _all_actions() -> set[str]:
    return set(READ_ONLY_ACTIONS) | set(MUTATING_ACTIONS) | set(DECISION_GATE_ACTIONS)


def _purge_expired(pending: dict, now: float) -> None:
    for token in [t for t, (expiry, _s, _p) in pending.items() if expiry <= now]:
        del pending[token]


def propose(action_id: str, params: dict, session_id: str) -> dict:
    """Whitelist check + confirmation-token issue for one proposed action."""
    if action_id not in _all_actions():
        raise ValueError(f"unknown action id: {action_id!r}")
    proposed = {"id": action_id, "params": params}
    if action_id in READ_ONLY_ACTIONS:
        return {"action": proposed, "confirm_token": None}
    token = secrets.token_urlsafe(16)
    with _LOCK:
        _purge_expired(_PENDING, _now())
        _PENDING[token] = (_now() + CONFIRM_TTL_S, session_id,
                           {"action_id": action_id, "params": params})
    return {"action": proposed, "confirm_token": token}


def _consume_token(action_id: str, confirm_token: str | None,
                   session_id: str | None) -> dict:
    """Fail-closed token check; on success removes the token (single use)."""
    if not confirm_token:
        raise PermissionError(f"{action_id} requires a confirmation token")
    with _LOCK:
        entry = _PENDING.get(confirm_token)
        if entry is None:
            raise PermissionError("unknown or already used confirmation token")
        expiry, entry_session, payload = entry
        if expiry <= _now():
            del _PENDING[confirm_token]
            raise PermissionError("confirmation token expired — propose the action again")
        if payload["action_id"] != action_id:
            raise PermissionError("confirmation token was issued for a different action")
        if session_id is not None and entry_session != session_id:
            raise PermissionError("confirmation token was issued for a different session")
        del _PENDING[confirm_token]
    return payload


def _canonical_params(params: dict) -> str:
    """Canonical JSON form of a params dict (order-insensitive comparison)."""
    return json.dumps(params, sort_keys=True)


def execute(action_id: str, params: dict, confirm_token: str | None,
            store_root: Path, reviewer: str, session_id: str | None = None) -> dict:
    """Execute a whitelisted action — fail closed on every missing credential.

    Every successful execution appends one ``action_audit`` record to the
    store; gate executions keep their GateDecision record in addition.
    """
    if action_id in READ_ONLY_ACTIONS:
        # The frontend action bus performs it; the execution is audit-logged here.
        _write_action_audit(store_root, action_id, session_id, "client", reviewer)
        return {"executed": True, "mode": "client"}

    payload = _consume_token(action_id, confirm_token, session_id)
    if _canonical_params(payload["params"]) != _canonical_params(params):
        raise PermissionError("confirmed parameters do not match the proposal")

    if action_id in MUTATING_ACTIONS:
        result = _execute_mutating(action_id, params, store_root, reviewer)
    elif action_id in DECISION_GATE_ACTIONS:
        result = _execute_gate(action_id, params, store_root, reviewer,
                               DECISION_GATE_ACTIONS[action_id])
    else:
        raise PermissionError(f"action {action_id!r} is not executable")  # unreachable

    _write_action_audit(store_root, action_id, session_id,
                        result.get("mode", "server"), reviewer)
    return result


def _write_action_audit(store_root: Path, action_id: str, session_id: str | None,
                        mode: str, reviewer: str) -> dict:
    """Append the execution trace (one audit record per executed action)."""
    return Store(store_root).put("action_audit", {
        "id": f"ACT-{uuid4().hex[:8]}",
        "action_id": action_id,
        "session_id": session_id or "",
        "mode": mode,
        "reviewer": reviewer or "",
        "at": utc_now(),
    })


def _execute_mutating(action_id: str, params: dict, store_root: Path, reviewer: str) -> dict:
    store = Store(store_root)
    if action_id == "save_note":
        store.put("note", {
            "id": f"NOTE-{uuid4().hex[:8]}",
            "text": params.get("text", ""),
            "case_id": params.get("case_id", ""),
            "author": reviewer,
            "created_at": utc_now(),
        })
        return {"executed": True, "mode": "server"}
    if action_id == "export_report":
        return {
            "report": store.all("report"),
            "cases": store.all("test_case"),
            "notes": store.all("note"),
            "gates": store.all("gate"),
            "generated_by": reviewer,
            "executed_by": "susie-assistant",
        }
    if action_id == "run_comparison":
        # Both buttons ("Create test cases from the law" = live, "Run comparison" = offline)
        # work on Team 10's 30 cases only (data/eaz_cases.json): load them and compare all
        # again. The old demo seed (TC-1..TC-4) is no longer used by the website.
        live = bool(params.get("live", False))
        from . import eaz_import
        eaz_import.run_import(Path(store_root), eaz_import.ROOT / "data" / "eaz_cases.json")
        return {"executed": True, "mode": "server", "live": live}
    # initiate_review_flow opens the review dialog client-side; nothing to record here.
    return {"executed": True, "mode": "client"}


def _execute_gate(action_id: str, params: dict, store_root: Path, reviewer: str,
                  allowed_gates: set[str]) -> dict:
    if not reviewer or not reviewer.strip():
        raise PermissionError(f"{action_id} requires a named human reviewer")
    if reviewer.strip().lower() == "susie-assistant":
        raise PermissionError(
            "the susie-assistant identity may never record a gate decision — "
            "a named human reviewer is required")
    gate_id = params.get("gate")
    if gate_id not in allowed_gates:
        raise PermissionError(
            f"gate {gate_id!r} is not allowed for {action_id} (allowed: {sorted(allowed_gates)})")
    _check_gate_ordering(store_root, gate_id)
    decision = gates.GateDecision(
        gate_id, reviewer, params.get("decision", ""),
        params.get("rationale", ""),
        affected_ids=params.get("affected_ids", []),
        conditions=params.get("conditions", []),
    )
    record = {"id": f"GATE-{gate_id}-{decision.decided_at}", **decision.to_dict()}
    Store(store_root).put("gate", record)
    return {
        "executed": True,
        "mode": "server",
        "record_id": record["id"],
        "decision_maker": reviewer,
        "executor": "susie-assistant",
    }


def _check_gate_ordering(store_root: Path, gate_id: str) -> None:
    """Skip protection: a gate may only be recorded directly after its predecessor.

    The requested gate id must not be more than one step ahead of the highest
    gate id already recorded in the store — the next gate in sequence is
    allowed, earlier/repeat gates are allowed (re-approval), skipping is
    refused. On a fresh store only the first gate (G0) may be recorded.
    """
    recorded_indexes = [
        gates.GATE_IDS.index(g["gate"])
        for g in Store(store_root).all("gate")
        if g.get("gate") in gates.GATE_IDS
    ]
    highest = max(recorded_indexes, default=-1)
    if gates.GATE_IDS.index(gate_id) > highest + 1:
        required = gates.GATE_IDS[highest + 1] if highest + 1 < len(gates.GATE_IDS) else gate_id
        raise PermissionError(
            f"gate {gate_id} cannot be recorded: {required} must be recorded first "
            "(gates cannot be skipped)")
