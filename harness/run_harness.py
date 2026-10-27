"""Run the 300 test cases through the current reviewer (run_review.py: parse_teel0 + dbvo_findings) and score it.

For each case a synthetic TEEL0 file is built from the real ITSG file as template (DSLW date/Abgabegrund
and the DBVO block replaced), parsed with parse_teel0, and checked with dbvo_findings. The reviewer's
MISMATCH flags are then compared with the case's ground truth (data/testcases.json).

Usage:  python harness/run_harness.py [--langfuse] [--limit N]
Output: reports/harness-<run id>.json, summary on stdout. With --langfuse: dataset team10-dbvo-v1,
        one dataset-run trace per case, scores case_correct / detected / false_alarm.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from run_review import parse_teel0, dbvo_findings, load_env  # noqa: E402

TEMPLATE = ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"
DATASET = "team10-dbvo-v1"
STORY_DATASET = "team10-stories-v1"
RULES_VERSION = "VB EEL 13.4 + GG EEL 13.1"
LEVEL = {"BLOCKED": "ERROR", "MISMATCH": "WARNING"}
# Checks that would be the right ones to raise the flag (others may also fire)
RIGHT_CHECK = {"F2 ANZAHL-AU": {"F2", "PARSE"}, "F2/F3 periods": {"F2", "F3"}, "F3 periods / C11": {"F2", "F3", "C11"},
               "F1 Abgabegrund": {"F1"}, "F4 KZ-AK-AU": {"F4"}, "F3 periods": {"F3"},
               "AU-AB-AG (§3.12.2)": {"F5"}, "AU-AB-SV (§3.12.3)": {"F6"}, "order (§3.12.7)": {"F7"},
               "R1": {"C9"}, "R2": {"C9", "C10", "C11", "F2", "F3"}, "R3": {"C12"}, "R4": {"C13"}}


def ymd(s):
    return date.fromisoformat(str(s)).strftime("%Y%m%d")


def dmy(s):
    return date.fromisoformat(str(s)).strftime("%d.%m.%Y")


def build_teel0(case, raw):
    """Template TEEL0 with this case's message date, Abgabegrund and DBVO block."""
    o, today = case["observed_dbvo"], case["scenario"]["today"]
    i, j = raw.index("DSLW"), raw.index("DBVO")
    raw = raw[:i + 41] + ymd(today) + raw[i + 49:i + 200] + o["ABGABEGRUND"] + raw[i + 202:]
    old_len = 32 + 50 * int(raw[j + 30:j + 32])
    block = ("DBVO" + "1" + ymd(o["AU-AB-AG"]) + str(o["AU-AB-SV"]).replace("-", "")[:8].ljust(8, "0")
             + o["KZ-AK-AU"] + "00000000" + f"{o['ANZAHL-AU']:02d}")
    for a, b in o["periods"]:
        block += ymd(a) + ymd(b) + "0" + "0" * 16 + "0" + "0" * 16
    assert len(block) == 32 + 50 * len(o["periods"])
    return raw[:j] + block + raw[j + old_len:]


def review(case, raw, tmpdir):
    path = Path(tmpdir) / f"{case['id']}.teel0"
    path.write_text(build_teel0(case, raw), encoding="latin-1")
    try:
        obs = parse_teel0(path)
    except Exception as exc:   # malformed output: the reviewer must stop, never report PASS
        return None, [{"id": "PARSE", "rule": "TEEL0 parser", "source": "run_review.parse_teel0",
                       "expected": "parsable DBVO", "actual": f"{type(exc).__name__}: {exc}"[:120], "status": "BLOCKED"}]
    sc = case["scenario"]
    current = {"start": dmy(sc["current_start"])}
    if sc["current_end"]:
        current["end"] = dmy(sc["current_end"])
    scenario = {"current_au": current, "today": dmy(sc["today"]), "current_cert": sc["current_cert"],
                "insurance": sc["insurance"],
                "prior_au": [{"start": dmy(p["start"]), "end": dmy(p["end"]), "cert": p["cert"]} for p in sc["prior"]]}
    return obs, dbvo_findings(scenario, obs)


def score(case, findings):
    flagged = sorted(f["id"] for f in findings if f["status"] in ("MISMATCH", "BLOCKED"))
    review = sorted(f["id"] for f in findings if f["status"] == "NEEDS_REVIEW")
    must = case["must_flag"]
    if must is None:
        if flagged:
            return {"flagged": flagged, "ok": False, "outcome": "FALSE ALARM"}
        if review:
            return {"flagged": review, "ok": False, "outcome": "unnecessary NEEDS_REVIEW"}
        return {"flagged": [], "ok": True, "outcome": "clean"}
    if must == "NEEDS_REVIEW":
        ok = bool(review)
        return {"flagged": flagged + review, "ok": ok,
                "outcome": "escalated (NEEDS_REVIEW)" if ok else f"not escalated (flagged {flagged})"}
    right = RIGHT_CHECK.get(must)
    if not flagged:
        return {"flagged": review, "ok": False, "outcome": "only NEEDS_REVIEW" if review else "MISSED"}
    ok = bool(right & set(flagged))
    if "PARSE" in flagged:
        outcome = "BLOCKED (malformed output)"
    else:
        outcome = "detected" if ok else "flagged, but by an unrelated check"
    return {"flagged": flagged, "ok": ok, "outcome": outcome}


def evaluate(case, raw, tmpdir):
    """Findings + score for one case. Story 4/6 cases (insurer reply, message flow) have no checker yet."""
    if "observed_dbvo" not in case:
        return [], {"flagged": [], "ok": None, "outcome": "NOT EVALUATED (no checker)"}
    _, findings = review(case, raw, tmpdir)
    return findings, score(case, findings)


def retry(fn, **kw):
    """Langfuse public API allows ~100 requests/min (429 seen in practice): wait and retry."""
    import time
    from langfuse.api.core.api_error import ApiError
    for _ in range(10):
        try:
            return fn(**kw)
        except ApiError as exc:
            if exc.status_code != 429:
                raise
            time.sleep(int((exc.body or {}).get("details", {}).get("retryAfterSeconds", 30)) + 1)
    raise RuntimeError("Langfuse rate limit: gave up after 10 retries")


def git_sha():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True).stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--langfuse", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--stories", action="store_true", help="story cases (data/story_cases.json) instead of the 300")
    ap.add_argument("--cases", help="another case file in data/, e.g. expa_sick.json (experiment a)")
    args = ap.parse_args()
    if args.cases:
        dataset, src = f"team10-{Path(args.cases).stem}", args.cases
    elif args.stories:
        dataset, src = STORY_DATASET, "story_cases.json"
    else:
        dataset, src = DATASET, "testcases.json"
    cases = json.loads((ROOT / "data" / src).read_text(encoding="utf-8"))[:args.limit]
    for c in cases:
        c.setdefault("group", f"story{c.get('story')}")
    raw = TEMPLATE.read_text(encoding="latin-1")
    run_id = "HARNESS-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    sha = git_sha()

    lf, items = None, {}
    if args.langfuse:
        load_env(ROOT / ".env")
        from langfuse import get_client
        lf = get_client()
        # T10-043: Fares's privacy guard — all Langfuse payloads below go through guard.safe()
        # (minimize + pseudonymize + check_clean, policy "langfuse" in privacy/schleuse.py)
        from privacy.langfuse_guard import LangfuseGuard
        guard = LangfuseGuard()
        try:
            have = {it.id for it in retry(lf.get_dataset, name=dataset).items}
        except Exception:
            retry(lf.create_dataset, name=dataset, description=f"Synthetic EEL cases, data/{src}")
            have = set()
        for c in cases:   # id = case id, so re-running does not duplicate items
            if f"{dataset}-{c['id']}" not in have:
                observed = c.get("observed_dbvo") or c.get("observed_61") or c.get("messages")
                retry(lf.create_dataset_item, dataset_name=dataset, id=f"{dataset}-{c['id']}",
                      input=guard.safe({"scenario": c["scenario"], "observed": observed}),
                      expected_output=guard.safe({"expected": c["expected"], "must_flag": c["must_flag"]}),
                      metadata=guard.safe({"group": c["group"], "category": c["category"]}))
        items = {it.id: it for it in retry(lf.get_dataset, name=dataset).items}

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for c in cases:
            if lf:
                import time
                time.sleep(0.7)   # item.run makes one API call per case; stay under the rate limit
                with items[f"{dataset}-{c['id']}"].run(run_name=run_id, run_metadata={"git_sha": sha}) as span:
                    findings, s = evaluate(c, raw, tmp)
                    for f in findings:
                        with lf.start_as_current_span(name=f"check {f['id']}",
                                                      input=guard.safe({"rule": f["rule"], "source": f["source"],
                                                                        "criterion_id": f.get("criterion_id")}),
                                                      output=guard.safe({k: f.get(k) for k in ("expected", "actual", "status", "reason")}),
                                                      level=LEVEL.get(f["status"], "DEFAULT")):
                            pass
                    span.update_trace(name="review-case", session_id=run_id, version=sha,
                                      tags=["Team10", "harness", "Abgabegrund-41", c["group"]],
                                      input=guard.safe({"case_id": c["id"], "category": c["category"]}),
                                      output=guard.safe({"flagged": s["flagged"], "outcome": s["outcome"]}),
                                      metadata=guard.safe({"case_id": c["id"], "report_id": f"{run_id}-{c['id']}",
                                                           "rules_version": RULES_VERSION, "must_flag": c["must_flag"],
                                                           "reviewer": "run_review.dbvo_findings", "data": "synthetic"}))
                    not_eval = sum(f["status"] == "NOT EVALUATED" for f in findings)
                    if s["ok"] is None:   # no checker for this case: record it, never count it as right or wrong
                        span.score_trace(name="not_evaluated", value=1, data_type="NUMERIC", comment=guard.safe(s["outcome"]))
                    else:
                        span.score_trace(name="case_correct", value=1 if s["ok"] else 0, data_type="BOOLEAN",
                                         comment=guard.safe(s["outcome"]))
                        span.score_trace(name="not_evaluated", value=not_eval, data_type="NUMERIC",
                                         comment="checks with status NOT EVALUATED")
                        if c["must_flag"]:
                            span.score_trace(name="detected", value=1 if s["ok"] else 0, data_type="BOOLEAN")
                        else:
                            span.score_trace(name="false_alarm", value=0 if s["ok"] else 1, data_type="BOOLEAN")
            else:
                findings, s = evaluate(c, raw, tmp)
            results.append({"id": c["id"], "group": c["group"], "category": c["category"],
                            "must_flag": c["must_flag"], **s,
                            "findings": [{k: f.get(k) for k in ("id", "expected", "actual", "status")} for f in findings]})
    if lf:
        lf.flush()

    by_cat = defaultdict(Counter)
    for r in results:
        by_cat[(r["group"], r["category"] if r["group"] != "golden" else r["id"])][r["outcome"]] += 1
    evaluated = [r for r in results if r["ok"] is not None]
    clean = [r for r in evaluated if r["must_flag"] is None]
    must = [r for r in evaluated if r["must_flag"]]
    summary = {"run_id": run_id, "git_sha": sha, "dataset": dataset, "cases": len(results),
               "evaluated": len(evaluated), "not_evaluated": len(results) - len(evaluated),
               "correct": sum(bool(r["ok"]) for r in evaluated),
               "false_alarms": sum(not r["ok"] for r in clean), "clean_cases": len(clean),
               "detected": sum(r["ok"] for r in must), "must_flag_cases": len(must),
               "by_category": {f"{g} | {k}": dict(v) for (g, k), v in by_cat.items()}}
    out = ROOT / "reports" / f"harness-{run_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
