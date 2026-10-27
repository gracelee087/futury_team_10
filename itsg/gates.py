"""Human gate decisions — architecture.md §7 (G0–G6).

Every gate decision records reviewer identity/role, timestamp, decision,
rationale, affected version IDs, and conditions. Fail closed: a decision
without a named reviewer or rationale is invalid, and no code path may
record a gate decision on an agent's behalf alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .timeutil import utc_now

GATE_IDS = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
GATE_NAMES = {
    "G0": "Source intake",
    "G1": "Requirement",
    "G2": "Translation",
    "G3": "Criterion and expected result",
    "G4": "Execution",
    "G5": "Template and report",
    "G6": "Release sign-off",
}
DECISIONS = ("approved", "rejected", "blocked", "escalated")


@dataclass
class GateDecision:
    """One recorded human gate decision (the evidence architecture.md §7 requires)."""

    gate: str
    reviewer: str
    decision: str
    rationale: str
    affected_ids: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    decided_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if self.gate not in GATE_IDS:
            raise ValueError(f"unknown gate id: {self.gate!r} (expected one of {GATE_IDS})")
        if self.decision not in DECISIONS:
            raise ValueError(f"unknown decision: {self.decision!r} (expected one of {DECISIONS})")
        if not self.reviewer or not self.reviewer.strip():
            raise ValueError(f"{self.gate} requires a named human reviewer")
        if not self.rationale or not self.rationale.strip():
            raise ValueError(f"{self.gate} requires a recorded rationale")

    def to_dict(self) -> dict:
        return asdict(self)
