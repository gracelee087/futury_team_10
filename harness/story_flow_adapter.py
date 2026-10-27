"""Story 4 / 6 cases -> Fares' message-flow checker (checker/guard.py + checker/checks.py, C1-C8). T10-008.

Nothing is invented: the checker input is built ONLY from fields that exist in the case.
  story 6 (cancellation 88): case["messages"] already use the checker's field names; the expected AZVU and the
           final EFZ end come from the case's own ground truth (case["scenario"]["azvu"], ["expected_efz_final"]).
  story 4 (insurer reply 61): the case holds ONE employer 41 and ONE insurer 61 as field dicts (no AZVU, no message
           IDs, no 01/88/62 messages). C1-C8 check the flow 41->61->01->61->88->01->62, so none of them can be
           evaluated: all eight stay NOT EVALUATED with that reason. The 61 rules (VB 13.4 3.12.x) have no checker yet.
The ITSG fixture values in checker/checks.py (EXPECTED) are not used for story cases and are not changed.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "checker")]
from run_review import finding  # noqa: E402
from checks import run_checks  # noqa: E402
from guard import validate  # noqa: E402

CHECK_IDS = [f"C{i}" for i in range(1, 9)]
STATUS = {"PASS": "PASS", "MISMATCH": "MISMATCH", "NOT_EVALUATED": "NOT EVALUATED"}


def to_checker_input(case):
    """-> (checker_case, expected, None) or (None, None, reason why the case cannot be checked)."""
    if case.get("story") == 6 and isinstance(case.get("messages"), list):
        sc = case.get("scenario") or {}
        # a missing ground-truth value stays None -> the checker reports NOT EVALUATED for that check
        expected = {"AZVU": sc.get("azvu"), "EFZ_Ende_final": sc.get("expected_efz_final")}
        return {"messages": case["messages"], "test_case_id": case.get("id", "TC-1")}, expected, None
    if case.get("story") == 4:
        return None, None, ("story 4 case has only the employer 41 and the insurer 61 as field values "
                            "(no AZVU, message IDs, 01/88/62 messages); C1-C8 check the cancellation message flow")
    return None, None, "not a story 4/6 case"


def story_findings(case):
    """Findings (same shape as run_review.finding) for a story 4/6 case."""
    checker_case, expected, reason = to_checker_input(case)
    if checker_case is None:
        return [finding(cid, "message flow check", "checker/checks.py", None, None, "NOT EVALUATED", reason)
                for cid in CHECK_IDS]
    problems = validate(checker_case)   # the guard stays on: unknown fields / bad formats -> BLOCKED, never PASS
    if problems:
        return [finding("GUARD", "checker input is valid", "checker/guard.py", "valid", "; ".join(problems[:3]), "BLOCKED")]
    out = []
    for r in run_checks(checker_case, expected):
        note = r["reason"]
        if r["check_id"] in ("C1", "C6"):
            note += " (expected value from the story case's own ground truth)"
        out.append(finding(r["id"], r["rule"], r["source"], r["expected"], r["actual"], STATUS[r["status"]], note))
    return out
