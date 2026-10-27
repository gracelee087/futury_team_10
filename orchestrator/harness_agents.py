"""Run the 300 harness cases through the verdict graph (compare -> findings_critic -> explainer -> G5, gates auto).

The findings critic runs on a sample: every case the code flags (MISMATCH / BLOCKED / NEEDS_REVIEW) plus 10% of the
clean ones (seed 7). Accuracy is scored before and after the critic, so any change the critic makes is visible.

Usage: python orchestrator/harness_agents.py [--limit N]
Output: reports/agents-harness-<run id>.json; Langfuse session = run id, scores case_correct / critic_changed.
"""
import argparse
import json
import os
import random
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parent / "harness")]
from graph import ROOT, build_verdict, run  # noqa: E402
from llm import PROMPT_VERSION, lf_client  # noqa: E402
from run_harness import score  # noqa: E402
from run_review import load_env  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cases", default="testcases.json", help="case file in data/, e.g. expa_sick.json (experiment a)")
    args = ap.parse_args()
    load_env(ROOT / ".env")
    cases = json.loads((ROOT / "data" / args.cases).read_text(encoding="utf-8"))[:args.limit]
    label = os.environ.get("TEAM10_RUN_LABEL")   # parallel runs start in the same second: keep their ids apart
    run_id = f"AGENTS-HARNESS-{datetime.now():%Y%m%d-%H%M%S}" + (f"-{label}" if label else "")
    rnd, graph, lf, rows = random.Random(7), build_verdict(), lf_client(), []
    for c in cases:
        flagged = c["must_flag"] is not None   # decided before the run from the code verdict below
        span_cm = lf.start_as_current_span(name="agent-review-case") if lf else None
        span = span_cm.__enter__() if span_cm else None
        # code verdict first (no critic); if sampled, run again with the critic and the explainer
        first = run(graph, {"case": c, "sampled": False}, auto=True)
        code_flag = any(f["status"] != "PASS" and f["status"] != "NOT EVALUATED" for f in first["findings"])
        sampled = code_flag or rnd.random() < 0.10
        out = run(graph, {"case": c, "sampled": True}, auto=True) if sampled else first
        before, after = first["score"], score(c, out["findings"])
        row = {"id": c["id"], "group": c["group"], "category": c["category"], "sampled": sampled,
               "before": before["outcome"], "after": after["outcome"], "ok_before": before["ok"], "ok_after": after["ok"],
               "critic_changed": out.get("critic_changed", []),
               "critic_on_mismatch": out.get("critic_on_mismatch", []), "summary": out.get("summary")}
        rows.append(row)
        if span:
            span.update_trace(name="agent-review-case", session_id=run_id, tags=["Team10", "agents", c["group"]],
                              input={"case_id": c["id"]}, output=row,
                              metadata={"gates": out.get("gates"), "flagged_by_ground_truth": flagged})
            span.score_trace(name="case_correct", value=1 if after["ok"] else 0, data_type="BOOLEAN", comment=after["outcome"])
            span.score_trace(name="critic_changed", value=len(row["critic_changed"]), data_type="NUMERIC")
            span_cm.__exit__(None, None, None)
    if lf:
        lf.flush()
    summary = {"run_id": run_id, "prompt_version": PROMPT_VERSION, "explainer": not os.environ.get("TEAM10_NO_EXPLAINER"), "cases": len(rows), "critic_runs": sum(r["sampled"] for r in rows),
               "correct_before": sum(r["ok_before"] for r in rows), "correct_after": sum(r["ok_after"] for r in rows),
               "critic_changed_cases": sum(bool(r["critic_changed"]) for r in rows),
               "critic_on_mismatch_cases": sum(bool(r["critic_on_mismatch"]) for r in rows),
               "changes": Counter(f"{r['before']} -> {r['after']}" for r in rows if r["before"] != r["after"])}
    out = ROOT / "reports" / f"{run_id}.json"
    out.write_text(json.dumps({"summary": summary, "results": rows}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print("->", out)


if __name__ == "__main__":
    main()
