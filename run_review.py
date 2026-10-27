"""Run one review: TEEL0 file + test case -> checks -> attacks -> report, traced in Langfuse.

ADOPTED IMPLEMENTATION (T10-031): authored by Team 10 teammates on `main`
(snapshot futury_team_10-main.zip, 2026-10-26), audited and adopted verbatim —
see src/PROVENANCE.md. The duplicate root API.py of the snapshot was NOT
adopted (it contains a plaintext gateway token; this repo keeps api.py plus
the encrypted store, itsg/secrets.py).

Usage:  python run_review.py [--case data/case_correct.json] [--teel0 "ITSG Files/TEEL0-Test1-DBVO"]
                             [--checker-dir checker] [--public]
Env:    LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST (from .env). Without keys the
        review still runs; only tracing is off.
Output: reports/<report id>.json and a human-readable table on stdout.
"""
import argparse
import calendar
import contextlib
import copy
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Field positions (1-based, length) from Verfahrensbeschreibung DTA EEL 13.4
DSLW_FIELDS = {"DATUM-ERSTELLUNG": (42, 8), "DATENSATZ-ID": (99, 36), "ABGABEGRUND": (201, 2)}  # §3.1.5, §3.1.18
DBVO_FIELDS = {"GRUNDAV": (5, 1), "AU-AB-AG": (6, 8), "AU-AB-SV": (14, 8), "KZ-AK-AU": (22, 1),
               "ANZAHL-AU": (31, 2)}  # §3.12.1-3.12.6
DBVO_PERIOD = 50  # §3.12.7-3.12.14: BEGINN 8, ENDE 8, then 34 insurer-side characters per prior AU


def load_env(path):
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"'))


def d(s):
    """'20260311' or '11.03.2026' -> date"""
    return datetime.strptime(s, "%Y%m%d" if "." not in s else "%d.%m.%Y").date()


def fmt(day):
    return day.strftime("%d.%m.%Y")


def add_months(day, months):
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def parse_teel0(path):
    raw = Path(path).read_text(encoding="latin-1")
    dslw = raw[raw.index("DSLW"):]
    out = {k: dslw[a - 1:a - 1 + n] for k, (a, n) in DSLW_FIELDS.items()}
    dbvo = raw[raw.index("DBVO"):]
    out.update({k: dbvo[a - 1:a - 1 + n] for k, (a, n) in DBVO_FIELDS.items()})
    out["AU-ZEITRAEUME"] = []
    if not out["ANZAHL-AU"].isdigit():
        raise ValueError(f"DBVO malformed: ANZAHL-AU {out['ANZAHL-AU']!r} is not a number")
    for k in range(int(out["ANZAHL-AU"])):
        p = dbvo[32 + k * DBVO_PERIOD:32 + (k + 1) * DBVO_PERIOD]
        try:
            out["AU-ZEITRAEUME"].append([fmt(d(p[0:8])), fmt(d(p[8:16]))])
        except ValueError:
            raise ValueError(f"DBVO malformed: ANZAHL-AU = {out['ANZAHL-AU']} but period {k + 1} "
                             f"is not a date pair ({p[:16]!r})") from None
    out["DATUM-ERSTELLUNG"] = fmt(d(out["DATUM-ERSTELLUNG"]))
    out["AU-AB-AG"] = fmt(d(out["AU-AB-AG"]))
    return out


def eligible(prior, current_start):
    """Uncertified AUs count only if a certified AU follows seamlessly (VB 13.4 §3.12 p.135). cert defaults to True."""
    starts = {d(p["start"]) for p in prior if p.get("cert", True)} | {current_start}
    return [[p["start"], p["end"]] for p in prior
            if p.get("cert", True) or d(p["end"]) + timedelta(days=1) in starts]


def chain(periods, current_start):
    """Prior AUs that belong in the 41: going back from the current AU, each gap <= 6 months (criterion aade0289)."""
    kept, nxt = [], current_start
    for start, end in sorted(periods, key=lambda p: d(p[1]), reverse=True):
        if add_months(d(end), 6) < nxt:
            break
        kept.append([start, end])
        nxt = d(start)
    return kept


def finding(fid, rule, source, expected, actual, status=None, reason=None, criterion_id=None):
    f = {"id": fid}
    if criterion_id:
        f["criterion_id"] = criterion_id
    f.update(rule=rule, source=source, expected=expected, actual=actual,
             status=status or ("PASS" if expected == actual else "MISMATCH"))
    if reason:
        f["reason"] = reason
    return f


def dbvo_findings(scenario, obs):
    cur_au = scenario["current_au"]
    cur = d(cur_au["start"])
    prior = scenario["prior_au"]
    exp_chain = chain(eligible(prior, cur), cur)
    file_periods = obs["AU-ZEITRAEUME"]
    au_start = d(obs["AU-AB-AG"])
    last_end = max(d(e) for _, e in file_periods) if file_periods else None
    newest_first = sorted(file_periods, key=lambda p: d(p[0]), reverse=True)
    f = [
        finding("F1", "Abgabegrund = 41", "VB 13.4 §3.1.18 p.43", "41", obs["ABGABEGRUND"]),
        finding("F2", "ANZAHL-AU = number of prior AUs to report", "VB 13.4 §3.12.6 p.139",
                f"{len(exp_chain):02d}", obs["ANZAHL-AU"]),
        finding("F3", "Reported prior AU periods (order-independent)", "VB 13.4 §3.12.7/3.12.8 p.140-141",
                sorted(exp_chain), sorted(file_periods)),
        finding("F4", "Employer sends KZ-AK-AU = 0 (Grundstellung)", "VB 13.4 §3.12.4 p.138", "0", obs["KZ-AK-AU"]),
        finding("F5", "AU-AB-AG = start of the current AU", "VB 13.4 §3.12.2 p.137", fmt(cur), obs["AU-AB-AG"]),
        finding("F6", "Employer sends AU-AB-SV = 00000000 (Grundstellung)", "VB 13.4 §3.12.3 p.137",
                "00000000", obs.get("AU-AB-SV")),
        finding("F7", "Prior AUs listed most recent first", "VB 13.4 §3.12.7 p.140", newest_first, file_periods),
    ]
    if "current_cert" in scenario:
        cert_ok = bool(scenario["current_cert"]) and any(
            p.get("cert", True) for p in prior if [p["start"], p["end"]] in exp_chain)
        f.append(finding("C9", "41 only if current AU and >=1 prior AU are certified", "SRC-CRIT; VB 13.4 §3.12 p.135",
                         True, cert_ok, criterion_id="f41c7278-b5a5-4ec3-b321-39bca5c3aeeb"))
    else:
        f.append(finding("C9", "41 only if current AU and >=1 prior AU are certified", "SRC-CRIT; VB 13.4 §3.12 p.135",
                         True, None, "NOT EVALUATED", "certificate status is in neither the message nor the test case",
                         "f41c7278-b5a5-4ec3-b321-39bca5c3aeeb"))
    if "insurance" in scenario:
        f.append(finding("C13", "No 41 for private insurance or marginal employment", "VB 13.4 §3.12 p.136",
                         "GKV", scenario["insurance"]))
    else:
        f.append(finding("C13", "No 41 for private insurance or marginal employment", "VB 13.4 §3.12 p.136",
                         "GKV", None, "NOT EVALUATED", "insurance type is in neither the message nor the test case"))
    if last_end:
        gap = (au_start - last_end).days
        f.append(finding("C10", "<= 6 months between start of current AU and end of last prior AU",
                         "SRC-CRIT; VB 13.4 §3.12 p.135", "<= 6 months",
                         f"{gap} days ({fmt(last_end)} -> {fmt(au_start)})",
                         "PASS" if au_start <= add_months(last_end, 6) else "MISMATCH",
                         criterion_id="0cefe80e-4fd9-41e1-be4f-3ae1ecbde646"))
    else:
        f.append(finding("C10", "<= 6 months to last prior AU", "SRC-CRIT", "<= 6 months", None, "MISMATCH",
                         "no prior AU in the 41", "0cefe80e-4fd9-41e1-be4f-3ae1ecbde646"))
    f.append(finding("C11", "Prior AUs included only if each gap <= 6 months", "SRC-CRIT; VB 13.4 §3.12 p.135",
                     len(file_periods), len(chain(file_periods, au_start)),
                     criterion_id="aade0289-e8f9-4e12-9c49-464cf6cd0789"))
    f.append(c12(cur_au, scenario, obs, prior, cur, file_periods))
    return f


def c12(cur_au, scenario, obs, prior, cur, file_periods):
    """Prior AUs of the last 12 months + current AU >= 30 days. The current AU counts until its expected end
    (Beispiel 13.4), or today + 6 days if it is open-ended (VB 13.4 §3.12 p.135, Beispiel 13.5: 02.09 -> 08.09)."""
    rule, src, cid = ("Prior AUs (12 months) + current AU >= 30 days", "SRC-CRIT; VB 13.4 §3.12 p.135; Beispiel 13.4/13.5",
                      "9c8c9b58-4d0f-4066-98ac-973095418d63")
    end = cur_au.get("end") or cur_au.get("end_final") or cur_au.get("end_initial")
    if end:
        cur_end, how = d(end), "expected end"
    else:
        today = d(scenario.get("today") or obs["DATUM-ERSTELLUNG"])
        cur_end, how = today + timedelta(days=6), f"open end: {fmt(today)} + 6 days"
    cur_days = (cur_end - cur).days + 1
    limit = add_months(cur, -12)
    span = lambda ps: sum((d(e) - d(s)).days + 1 for s, e in ps if d(e) >= limit)
    reported = cur_days + span(file_periods)
    all_known = cur_days + span(eligible(prior, cur))
    straddle = any(d(s) < limit <= d(e) for s, e in file_periods + eligible(prior, cur))
    actual = f"{reported} days (current {cur_days}, {how})"
    if straddle or (reported >= 30) != (all_known >= 30):
        why = ("an AU straddles the 12-month limit" if straddle else
               f"reported chain gives {reported} days, all prior AUs of the last 12 months give {all_known}")
        return finding("C12", rule, src, ">= 30", actual, "NEEDS_REVIEW",
                       f"rule text does not settle this: {why}", cid)
    return finding("C12", rule, src, ">= 30", actual, "PASS" if reported >= 30 else "MISMATCH", criterion_id=cid)


def robustness(case):
    try:
        from attacks import mutations, evaluate
    except ImportError:
        return {"result": "NOT EVALUATED", "reason": "checker/attacks.py not found", "attacks": []}
    baseline, _ = evaluate(copy.deepcopy(case))
    rows = []
    for kind, name, fn in mutations():
        c = copy.deepcopy(case)
        fn(c)
        status, failed = evaluate(c)
        rows.append({"kind": kind, "attack": name, "result": status, "failed_checks": failed})
    stopped = sum(r["result"] in ("CAUGHT", "BLOCKED") for r in rows)
    return {"tool": "checker/attacks.py", "baseline": "no false alarm" if baseline == "MISSED" else f"FALSE ALARM ({baseline})",
            "result": f"{stopped}/{len(rows)} stopped", "attacks": rows}


def human(report):
    r, cnt = report["report"], report["report"]["counts"]
    short = lambda v: (json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)[:12] if v is not None else "-"
    lines = [f"REVIEW REPORT {r['id']} – Abgabegrund 41 (DBVO)     Overall: {r['overall_status']}",
             f"Template: {r['template']}",
             f"Test data: {report['execution']['file']}   ID {report['execution']['observed'].get('DATENSATZ-ID', '-')}",
             f"Test case: {report['test_case']['source']}",
             "Result: " + " · ".join(f"{v} {k}" for k, v in cnt.items() if v or k in ("PASS", "MISMATCH")),
             "-" * 79,
             f"{'ID':4} {'Check':38} {'Expected':12} {'Actual':12} {'Status':15} Source"]
    for f in report["findings"]:
        lines.append(f"{f['id']:4} {f['rule'][:38]:38} {short(f['expected']):12} {short(f['actual']):12} "
                     f"{f['status']:15} {f['source'][:24]}")
    rb = report["robustness"]
    lines += ["-" * 79, f"Robustness: {rb['result']} · baseline {rb.get('baseline', '-')}",
              f"Reviewer: {report['review']['decision']}        Trace: {report['trace_url'] or 'tracing off'}"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default=str(ROOT / "data" / "case_correct.json"))
    ap.add_argument("--teel0", default=str(ROOT / "ITSG Files" / "TEEL0-Test1-DBVO"))
    ap.add_argument("--checker-dir", default=str(ROOT / "checker"))
    ap.add_argument("--public", action="store_true", help="make the Langfuse trace viewable by link")
    args = ap.parse_args()

    load_env(ROOT / ".env")
    lf = None
    if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
        from langfuse import get_client
        lf = get_client()
    # T10-043: Fares's privacy guard (privacy/langfuse_guard.py) sits between this code and Langfuse —
    # every payload is minimized, pseudonymized and check_clean'd first (policy "langfuse",
    # privacy/schleuse.py). Without Langfuse keys nothing changes.
    guard = None
    if lf:
        sys.path.insert(0, str(ROOT))
        from privacy.langfuse_guard import LangfuseGuard
        guard = LangfuseGuard()
    span = (lambda **kw: lf.start_as_current_span(**guard.kwargs(**kw))) if lf else (lambda **kw: contextlib.nullcontext())

    report_id = "RPT-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    case = json.loads(Path(args.case).read_text(encoding="utf-8-sig"))
    with span(name="review-run", input={"case": args.case, "teel0": args.teel0}):
        if lf:
            # T10-007: the trace starts private; --public is applied at the end, only if every payload was clean
            lf.update_current_trace(**guard.kwargs(name="review-run", tags=["Team10", "Abgabegrund-41", "DBVO"],
                                                   metadata={"report_id": report_id, "test_case": case.get("source")}))
        with span(name="load_test_case", input=args.case, output={"scenario": case["scenario"], "messages": len(case["messages"])}):
            pass
        try:
            observed = parse_teel0(args.teel0)
            dbvo = dbvo_findings(case["scenario"], observed)
        except ValueError as exc:   # malformed output: stop, never PASS (svg "Malformed -> blocked")
            observed = {"error": str(exc)}
            dbvo = [finding("PARSE", "TEEL0 output is parsable", "VB 13.4 §3.12", "valid DBVO", str(exc), "BLOCKED")]
        with span(name="parse_teel0", input=args.teel0, output=observed,
                  level="ERROR" if "error" in observed else "DEFAULT"):
            pass
        findings = dbvo
        with span(name="checks", output={"total": len(findings)}):
            for f in findings:
                with span(name=f"check {f['id']}", input={"rule": f["rule"], "source": f["source"], "expected": f["expected"]},
                          output={"actual": f["actual"], "status": f["status"], "reason": f.get("reason")},
                          level="DEFAULT" if f["status"] == "PASS" else "WARNING"):
                    pass
        sys.path.insert(0, str(args.checker_dir))   # checker/attacks.py
        rb = robustness(case)
        with span(name="attacks", output=rb):
            pass

        order = ("BLOCKED", "MISMATCH", "NEEDS_REVIEW", "NOT EVALUATED", "PASS")
        counts = {s: sum(f["status"] == s for f in findings) for s in reversed(order)}
        overall = next(s for s in order if counts[s] or s == "PASS")
        trace_url = lf.get_trace_url(trace_id=lf.get_current_trace_id()) if lf else None
        report = {
            "report": {"id": report_id, "created_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
                       "scope": "DTA EEL – Abgabegrund 41 (DBVO)",
                       "template": "SYNTHETIC – no official ITSG report form found; no compliance claim",
                       "overall_status": overall, "counts": counts},
            "test_case": {"id": "TC-1", "source": case.get("source", args.case), "inputs": case["scenario"]},
            "execution": {"id": "RUN-" + report_id[4:], "file": Path(args.teel0).name, "observed": observed,
                          "observed_sources": {"message_1_41": "TEEL0 file (software output)"}},
            "findings": findings,
            "robustness": rb,
            "review": {"reviewer": None, "decision": "pending", "timestamp": None},
            "trace_url": trace_url,
        }
        with span(name="report", output=report):
            pass
        if lf:
            lf.update_current_trace(**guard.kwargs(output={"overall_status": overall, "counts": counts,
                                                           "robustness": rb["result"]}))
            if args.public and guard.all_clean:   # T10-007: refuse a public trace unless every payload passed check_clean
                lf.update_current_trace(public=True)
            elif args.public:
                print(f"--public refused: {guard.withheld} Langfuse payload(s) still looked personal and were withheld; "
                      "the trace stays private.")

    if lf:
        lf.flush()
    out = ROOT / "reports" / f"{report_id}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(human(report))
    print(f"\nSaved: {out}")


if __name__ == "__main__":
    main()
