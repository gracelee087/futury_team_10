"""Generate 300 synthetic test cases for Abgabegrund 41 (DBVO) with ground truth -> data/testcases.json + testCase.md

Rules (implemented here independently of run_review.py, so the harness is not circular):
  R1  current AU is certified                                   VB 13.4 §3.12 p.135, bullet 1
  R2  >= 1 certified prior AU within 6 months before AU start   VB 13.4 §3.12 p.135, bullet 2
  R3  prior AUs of the last 12 months + current AU >= 30 days;   VB 13.4 §3.12 p.135, bullet 3
      open-ended AU counts until today + 6 days                  Beispiel 13.5 (02.09 -> 08.09)
  R4  no 41 for privately insured or marginally employed         VB 13.4 §3.12 p.136
  R5  report every prior AU linked by gaps <= 6 months, no time limit,
      most recent first                                          VB 13.4 §3.12 p.135, §3.12.7 p.140
  R6  uncertified short AUs are reported only if a certified AU follows seamlessly  VB 13.4 §3.12 p.135
  Fields: AU-AB-AG = AU start (§3.12.2), AU-AB-SV = 00000000 (§3.12.3), KZ-AK-AU = 0 (§3.12.4),
          ANZAHL-AU = number of periods (§3.12.6)
Ambiguity (rule text does not settle it -> expected NEEDS_REVIEW):
  "all potential prior AUs in the last 12 months" vs only the 6-month-linked chain, and AUs that
  straddle the 12-month boundary.
Usage: python harness/generate_cases.py
"""
import calendar
import json
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = 41
DAY = timedelta(days=1)


def add_months(day, months):
    m = day.month - 1 + months
    y, m = day.year + m // 12, m % 12 + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def days(p):
    return (p["end"] - p["start"]).days + 1


def decide(sc):
    """Ground truth: (send_41, rule, expected DBVO or None)."""
    if sc["insurance"] != "GKV":
        return False, "R4", None
    if not sc["current_cert"]:
        return False, "R1", None
    start = sc["current_start"]
    allp = sorted(sc["prior"], key=lambda p: p["start"])
    # R6: uncertified AU counts only if a certified AU (prior or current) starts the day after it ends
    certified_starts = {p["start"] for p in allp if p["cert"]} | {start}
    eligible = [p for p in allp if p["cert"] or p["end"] + DAY in certified_starts]
    # R5: walk back from the current AU while the gap is <= 6 months
    chain, nxt = [], start
    for p in sorted(eligible, key=lambda p: p["end"], reverse=True):
        if add_months(p["end"], 6) < nxt:
            break
        chain.append(p)
        nxt = p["start"]
    if not any(p["cert"] for p in chain):
        return False, "R2", None
    end = sc["current_end"] or sc["today"] + 6 * DAY
    cur = (end - start).days + 1
    limit = add_months(start, -12)
    straddle = any(p["start"] < limit <= p["end"] for p in eligible)
    sum_chain = cur + sum(days(p) for p in chain if p["end"] >= limit)
    sum_all = cur + sum(days(p) for p in eligible if p["end"] >= limit)
    if straddle or (sum_chain >= 30) != (sum_all >= 30):
        return None, "AMBIGUOUS", {"sum_chain": sum_chain, "sum_all": sum_all, "straddle": straddle}
    if sum_chain < 30:
        return False, "R3", {"sum": sum_chain}
    dbvo = {"ABGABEGRUND": "41", "AU-AB-AG": start, "AU-AB-SV": "00000000", "KZ-AK-AU": "0",
            "ANZAHL-AU": len(chain), "periods": [(p["start"], p["end"]) for p in chain], "sum": sum_chain}
    return True, "OK", dbvo


# ---------- scenario builders ----------
rnd = random.Random(SEED)


def P(start, length, cert=True):
    return {"start": start, "end": start + (length - 1) * DAY, "cert": cert}


def base(prior, cur_len=None, open_end=False, insurance="GKV", cert=True):
    start = date(2026, 3, 1) + rnd.randint(0, 200) * DAY
    prior = prior(start)
    if open_end:
        today = start + rnd.randint(0, 4) * DAY
        cur_end = None
    else:
        cur_end = start + (cur_len - 1) * DAY
        today = start + rnd.randint(0, min(3, cur_len - 1)) * DAY
    return {"current_start": start, "current_end": cur_end, "today": today,
            "current_cert": cert, "insurance": insurance, "prior": prior}


def gap_before(start, gap_days, length, cert=True):
    """prior AU ending gap_days before `start`"""
    end = start - (gap_days + 1) * DAY
    return {"start": end - (length - 1) * DAY, "end": end, "cert": cert}


def b_normal(n=None):
    n = n or rnd.randint(1, 3)
    def prior(s):
        out, nxt = [], s
        for _ in range(n):
            p = gap_before(nxt, rnd.randint(10, 150), rnd.randint(5, 20))
            out.append(p)
            nxt = p["start"]
        return out
    return base(prior, cur_len=rnd.randint(10, 25))


def b_gap_exact():
    def prior(s):
        end = add_months(s, -6)
        while add_months(end, 6) != s:      # month-end clipping: move until exactly 6 months
            end += DAY
        return [P(end - 19 * DAY, 20)]
    return base(prior, cur_len=rnd.randint(12, 20))


def b_gap_plus1():
    sc = b_gap_exact()
    p = sc["prior"][0]
    p["start"] -= DAY
    p["end"] -= DAY
    return sc


def b_sum(total, open_end=False):
    sc = base(lambda s: [], cur_len=rnd.randint(5, 12), open_end=open_end)
    s = sc["current_start"]
    end = sc["current_end"] or sc["today"] + 6 * DAY
    rest = total - ((end - s).days + 1)
    parts = [rest] if rest < 8 or rnd.random() < 0.5 else [rest // 2, rest - rest // 2]
    nxt = s
    for length in parts:
        p = gap_before(nxt, rnd.randint(10, 60), length)
        sc["prior"].append(p)
        nxt = p["start"]
    return sc


def b_with(kind):
    sc = b_normal(rnd.randint(1, 2))
    if kind in ("PKV", "Minijob"):
        sc["insurance"] = kind
    elif kind == "no_cert":
        sc["current_cert"] = False
    return sc


def b_uncert(seamless, with_cert):
    sc = b_normal(1)
    s, p = sc["current_start"], sc["prior"][0]
    if seamless:     # short uncertified AU immediately before the certified prior AU
        sc["prior"].append(P(p["start"] - 3 * DAY, 3, cert=False))
    else:
        short = gap_before(s, rnd.randint(5, 30), 3, cert=False)
        if with_cert:
            sc["prior"].append(short)
        else:
            sc["prior"] = [short]
    return sc


def b_chain_break():
    sc = b_normal(rnd.randint(1, 2))
    oldest = min(sc["prior"], key=lambda p: p["start"])
    # > 6 months gap and older than 12 months before the AU start, so R3 is not affected
    start13 = add_months(sc["current_start"], -13)
    end = min(add_months(oldest["start"], -7), start13)
    sc["prior"].append(P(end - 9 * DAY, 10))
    return sc


def b_ambiguous():
    """chain sum < 30, but a non-chain prior AU inside the last 12 months would lift it to >= 30"""
    sc = base(lambda s: [], cur_len=8)
    s = sc["current_start"]
    p1 = gap_before(s, rnd.randint(20, 60), 12)                  # chain: 8 + 12 = 20
    end2 = add_months(p1["start"], -6) - rnd.randint(5, 20) * DAY  # > 6 months before p1
    p2 = P(end2 - 14 * DAY, 15)
    sc["prior"] = [p1, p2]
    return sc


def golden():
    y, py = 2025, 2024   # 20XX -> 2025, 20YY -> 2024
    D = lambda dd, mm, yy=y: date(yy, mm, dd)
    g = lambda pr, end=None, today=None: {"current_start": D(31, 8), "current_end": end, "today": today or D(31, 8),
                                          "current_cert": True, "insurance": "GKV",
                                          "prior": [{"start": a, "end": b, "cert": True} for a, b in pr]}
    return [
        ("GOLD-13.1", g([(D(1, 6), D(25, 6))]), "Beispiel 13.1: one prior AU -> 41, ANZAHL-AU 1 "
         "(current AU end not given; assumed open, today 31.08)"),
        ("GOLD-13.2", g([(D(1, 6), D(25, 6)), (D(3, 5), D(6, 5)), (D(1, 10, py), D(28, 10, py))]),
         "Beispiel 13.2: 01.10.YY-28.10.YY excluded (> 6 months), ANZAHL-AU 2"),
        ("GOLD-13.3", g([(D(10, 1), D(28, 1))]), "Beispiel 13.3: no 41, gap > 6 months"),
        ("GOLD-13.4", g([(D(1, 6), D(10, 6)), (D(3, 5), D(6, 5))], end=D(8, 9)), "Beispiel 13.4: no 41, 23 days"),
        ("GOLD-13.5", g([(D(1, 6), D(10, 6)), (D(3, 5), D(6, 5))], today=D(2, 9)),
         "Beispiel 13.5: open end, today 02.09 -> 08.09, 23 days, no 41"),
    ]


GOLDEN_EXPECT = {"GOLD-13.1": (True, 1), "GOLD-13.2": (True, 2), "GOLD-13.3": (False, 0),
                 "GOLD-13.4": (False, 0), "GOLD-13.5": (False, 0)}

# category: (count, builder, expected decision, rule)
DECISION = [
    ("normal", 30, b_normal, True, "OK"),
    ("boundary: gap exactly 6 months", 12, b_gap_exact, True, "OK"),
    ("boundary: gap 6 months + 1 day", 12, b_gap_plus1, False, "R2"),
    ("boundary: exactly 30 days", 12, lambda: b_sum(30), True, "OK"),
    ("boundary: 29 days", 12, lambda: b_sum(29), False, "R3"),
    ("open end: >= 30 days", 10, lambda: b_sum(rnd.randint(30, 45), open_end=True), True, "OK"),
    ("open end: < 30 days", 10, lambda: b_sum(rnd.randint(20, 29), open_end=True), False, "R3"),
    ("negative: private insurance", 6, lambda: b_with("PKV"), False, "R4"),
    ("negative: marginal employment", 6, lambda: b_with("Minijob"), False, "R4"),
    ("negative: current AU not certified", 8, lambda: b_with("no_cert"), False, "R1"),
    ("negative: only uncertified short prior AU", 8, lambda: b_uncert(False, False), False, "R2"),
    ("uncertified short AU not seamless (excluded)", 8, lambda: b_uncert(False, True), True, "OK"),
    ("uncertified short AU seamless (included)", 8, lambda: b_uncert(True, True), True, "OK"),
    ("chain break (old AU excluded)", 8, b_chain_break, True, "OK"),
]

MUTATIONS = [  # (name, count, check that must flag, needs >= 2 periods)
    ("correct output", 40, None, False),
    ("wrong ANZAHL-AU", 9, "F2 ANZAHL-AU", False),
    ("prior AU period missing", 9, "F2/F3 periods", True),
    ("extra AU beyond 6-month chain", 9, "F3 periods / C11", False),
    ("wrong Abgabegrund", 9, "F1 Abgabegrund", False),
    ("KZ-AK-AU not 0", 9, "F4 KZ-AK-AU", False),
    ("AU-AB-AG wrong date", 9, "AU-AB-AG (§3.12.2)", False),
    ("period begin shifted by 1 day", 9, "F3 periods", False),
    ("periods not most-recent-first", 9, "order (§3.12.7)", True),
    ("AU-AB-SV not 00000000", 8, "AU-AB-SV (§3.12.3)", False),
]


def mutate(name, dbvo):
    o = json.loads(json.dumps(dbvo, default=str))
    per = o["periods"]
    if name == "wrong ANZAHL-AU":
        o["ANZAHL-AU"] = o["ANZAHL-AU"] + 1     # count field changed, period list unchanged
    elif name == "prior AU period missing":
        per.pop()
        o["ANZAHL-AU"] -= 1
    elif name == "extra AU beyond 6-month chain":
        last = date.fromisoformat(per[-1][0])
        old_end = add_months(last, -8)
        per.append([str(old_end - 9 * DAY), str(old_end)])
        o["ANZAHL-AU"] += 1
    elif name == "wrong Abgabegrund":
        o["ABGABEGRUND"] = rnd.choice(["01", "61", "88"])
    elif name == "KZ-AK-AU not 0":
        o["KZ-AK-AU"] = "4"
    elif name == "AU-AB-AG wrong date":
        o["AU-AB-AG"] = str(date.fromisoformat(o["AU-AB-AG"]) + rnd.choice([-1, 1]) * DAY)
    elif name == "period begin shifted by 1 day":
        per[0][0] = str(date.fromisoformat(per[0][0]) - DAY)
    elif name == "periods not most-recent-first":
        per.reverse()
    elif name == "AU-AB-SV not 00000000":
        o["AU-AB-SV"] = o["AU-AB-AG"].replace("-", "")
    return o


def ser(x):
    return json.loads(json.dumps(x, default=str))


def build_one(builder, want, rule, tries=200):
    for _ in range(tries):
        sc = builder()
        got, r, dbvo = decide(sc)
        if got == want and r == rule:
            return sc, dbvo
    raise RuntimeError(f"could not build {rule}")


def main():
    cases = []
    # 1) golden check first: the rules must reproduce Beispiel 13.1-13.5
    for cid, sc, note in golden():
        send, rule, dbvo = decide(sc)
        exp_send, exp_n = GOLDEN_EXPECT[cid]
        assert send == exp_send and (not send or dbvo["ANZAHL-AU"] == exp_n), (cid, send, rule, dbvo)
        observed = ser(dbvo) if send else {"sent_41": True, "note": "software sent a 41 that must not exist"}
        cases.append({"id": cid, "group": "golden", "category": note, "scenario": ser(sc),
                      "expected": {"send_41": send, "rule": rule, "dbvo": ser(dbvo) if send else None},
                      "observed_kind": "correct output" if send else "41 sent although not allowed",
                      "must_flag": None if send else rule})
    print("golden 5/5 reproduced")
    # 2) decision cases: software output = correct 41 when allowed, an unwanted 41 when not allowed
    n = 0
    for cat, count, builder, want, rule in DECISION:
        for _ in range(count):
            n += 1
            sc, dbvo = build_one(builder, want, rule)
            cases.append({"id": f"DEC-{n:03d}", "group": "decision", "category": cat, "scenario": ser(sc),
                          "expected": {"send_41": want, "rule": rule, "dbvo": ser(dbvo) if want else None},
                          "observed_kind": "correct output" if want else "41 sent although not allowed",
                          "must_flag": None if want else rule})
    # 3) output conformance: correct scenario, observed DBVO correct or mutated
    n = 0
    for name, count, flag, need2 in MUTATIONS:
        for _ in range(count):
            n += 1
            sc, dbvo = build_one(lambda: b_normal(rnd.randint(2, 3) if need2 else None), True, "OK")
            cases.append({"id": f"OUT-{n:03d}", "group": "output", "category": name, "scenario": ser(sc),
                          "expected": {"send_41": True, "rule": "OK", "dbvo": ser(dbvo)},
                          "observed_kind": name, "observed_dbvo": mutate(name, ser(dbvo)),
                          "must_flag": flag})
    # 4) ambiguous rule text
    for i in range(25):
        sc, info = build_one(b_ambiguous, None, "AMBIGUOUS")
        cases.append({"id": f"AMB-{i + 1:03d}", "group": "ambiguous",
                      "category": "12-month sum: chain only vs all prior AUs disagree", "scenario": ser(sc),
                      "expected": {"send_41": None, "rule": "AMBIGUOUS", "detail": info},
                      "observed_kind": "41 sent (chain only)", "must_flag": "NEEDS_REVIEW",
                      "observed_dbvo": chain_only_41(sc)})
    for c in cases:
        if "observed_dbvo" not in c:
            c["observed_dbvo"] = c["expected"].get("dbvo") or unwanted_41(c["scenario"])
    assert len(cases) == 300 and len({c["id"] for c in cases}) == 300, len(cases)
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "testcases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False), encoding="utf-8")
    write_md(cases)
    print(f"{len(cases)} cases -> data/testcases.json, testCase.md")


def chain_only_41(sc):
    """Ambiguous cases: the 41 a system would send if it counts only the 6-month chain (newest prior AU)."""
    p = max(sc["prior"], key=lambda p: p["start"])
    return ser({"ABGABEGRUND": "41", "AU-AB-AG": sc["current_start"], "AU-AB-SV": "00000000", "KZ-AK-AU": "0",
                "ANZAHL-AU": 1, "periods": [[p["start"], p["end"]]]})


def unwanted_41(sc):
    """What a faulty payroll system would send: every prior AU it knows, newest first."""
    pr = sorted(sc["prior"], key=lambda p: p["start"], reverse=True)
    return {"ABGABEGRUND": "41", "AU-AB-AG": sc["current_start"], "AU-AB-SV": "00000000", "KZ-AK-AU": "0",
            "ANZAHL-AU": len(pr), "periods": [[p["start"], p["end"]] for p in pr]}


def dmy(s):
    return date.fromisoformat(s).strftime("%d.%m.%Y") if s else "open"


def write_md(cases):
    from collections import Counter
    L = ["# Test cases – Abgabegrund 41 (DBVO), 300 synthetic cases",
         "",
         "Generated by `harness/generate_cases.py` (seed 41). Machine-readable: `data/testcases.json`.",
         "All data is fabricated. Ground truth comes from the rule text below, not from an LLM.",
         "",
         "## Rules used for ground truth",
         "| Rule | Content | Source |",
         "|---|---|---|",
         "| R1 | Current AU is certified | VB 13.4 §3.12 p.135 |",
         "| R2 | ≥ 1 certified prior AU within 6 months before AU start | VB 13.4 §3.12 p.135 |",
         "| R3 | Prior AUs (last 12 months) + current AU ≥ 30 days; open end = today + 6 days | VB 13.4 §3.12 p.135, Beispiel 13.5 |",
         "| R4 | No 41 for private insurance or marginal employment | VB 13.4 §3.12 p.136 |",
         "| R5 | Report all prior AUs linked by gaps ≤ 6 months (no time limit), most recent first | VB 13.4 §3.12 p.135, §3.12.7 p.140 |",
         "| R6 | Uncertified short AU only if a certified AU follows seamlessly | VB 13.4 §3.12 p.135 |",
         "| Fields | AU-AB-AG = AU start, AU-AB-SV = 00000000, KZ-AK-AU = 0, ANZAHL-AU = number of periods | VB 13.4 §3.12.2–3.12.6 |",
         "",
         "Assumptions (not settled by the source):",
         "- Days are counted inclusive (Beispiel 13.4: 01.06–10.06 = 10 days).",
         "- The current AU counts until its expected end (Beispiel 13.4) or today + 6 days if open (Beispiel 13.5).",
         "- Beispiel 13.1 gives no end for the current AU; treated as open with today = 31.08.",
         "- \"All potential prior AUs in the last 12 months\" vs only the 6-month chain is unclear → 25 cases are labelled NEEDS_REVIEW.",
         "- Employment during the query period (GG) is not covered.",
         "",
         "## Overview",
         "| Group | Count | What it tests |",
         "|---|---|---|"]
    groups = Counter(c["group"] for c in cases)
    what = {"golden": "Beispiel 13.1–13.5 (must reproduce the official examples)",
            "decision": "Should a 41 be sent at all? Software output = correct 41, or an unwanted 41",
            "output": "41 is correct to send; the DBVO content is correct or has one defect",
            "ambiguous": "Rule text does not decide; reviewer must say NEEDS_REVIEW"}
    for g in ("golden", "decision", "output", "ambiguous"):
        L.append(f"| {g} | {groups[g]} | {what[g]} |")
    L += [f"| **total** | **{len(cases)}** | |", "", "### Categories", "| Category | Count | Expected | Must flag |",
          "|---|---|---|---|"]
    cat = Counter((c["category"] if c["group"] != "golden" else c["id"], c["expected"]["rule"], c["must_flag"]) for c in cases)
    for (k, r, f), v in cat.items():
        L.append(f"| {k} | {v} | {r} | {f or '–'} |")
    L += ["", "## All cases",
          "| ID | Category | Current AU (start – end) | Today | Insurance / cert | Prior AUs (* = uncertified) | Expected | Expected DBVO | Observed output | Must flag |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for c in cases:
        s, e = c["scenario"], c["expected"]
        prior = "; ".join(f"{dmy(p['start'])}–{dmy(p['end'])}{'' if p['cert'] else '*'}"
                          for p in sorted(s["prior"], key=lambda p: p["start"], reverse=True)) or "–"
        exp = {True: "send 41", False: f"no 41 ({e['rule']})", None: "NEEDS_REVIEW"}[e["send_41"]]
        dbvo = (f"ANZAHL {e['dbvo']['ANZAHL-AU']}: " + ", ".join(f"{dmy(a)}–{dmy(b)}" for a, b in e["dbvo"]["periods"])
                if e.get("dbvo") else "–")
        ins = f"{s['insurance']} / {'cert' if s['current_cert'] else 'no cert'}"
        L.append(f"| {c['id']} | {c['category'][:48]} | {dmy(s['current_start'])} – {dmy(s['current_end'])} | "
                 f"{dmy(s['today'])} | {ins} | {prior} | {exp} | {dbvo} | {c['observed_kind']} | {c['must_flag'] or '–'} |")
    (ROOT / "testCase.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
