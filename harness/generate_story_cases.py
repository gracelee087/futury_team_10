"""Generate 200 story-based test cases (stories 1, 3, 4, 6) with ground truth -> data/story_cases.json + testCase-stories.md

Story 1 (40)  Work accident / rehab instead of illness. The reason of absence does not matter for a 41
              (VB 13.4 §3.12 p.135: "unabhängig vom Grund der Abwesenheit (Unfall, Krankheit, Rehabilitation etc.)").
Story 3 (40)  Short sick days without a certificate. Reported only if a certified AU follows seamlessly
              (VB 13.4 §3.12 p.135).
Story 4 (60)  The insurer's reply (Abgabegrund 61) to the 41. Field rules VB 13.4 §3.12.2-3.12.14:
              AU-AB-AG = employer's value (§3.12.2); AU-AB-SV = 00000000 unless the insurer's start differs (§3.12.3);
              KZ-AK-AU 0 or 4 (§3.12.4); 12-MONATSFRIST-AB = 00000000 if KZ-AK-AU = 4 (§3.12.5);
              ANZAHL-AU >= employer's (§3.12.6); employer's periods first, same values and order, additions after (§3.12.7);
              KZ-NACHWEIS 1/2/4, TEIL-NACHWEIS only with 2 (§3.12.9-3.12.11); KZ-NACHWEIS 4 -> KZ-AU 2 (§3.12.5);
              KZ-AU 1/2/3/5, TEIL-ANR only with 5 (§3.12.12-3.12.14).
Story 6 (60)  Cancel and correct (Hinweise Testkonstellation): 41 -> 61 -> 01 -> 61 -> 88 -> 01 -> 62.
              88 needs Stornierung J and DATENSATZ-ID-URSPRUNGSMELDUNG of the cancelled message, a new message follows
              when the cancelled one had wrong data (GG EEL 13.1 §2.5); replies carry the employer's DATENSATZ-ID as
              REFERENZ-ID (VB 13.4 §3.1.18).
Usage: python harness/generate_story_cases.py
"""
import json
import random
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_cases import add_months, decide, P, gap_before, DAY  # noqa: E402  same ground-truth rules

ROOT = Path(__file__).resolve().parent.parent
rnd = random.Random(4136)
REASONS = ["illness", "work accident", "rehabilitation", "hospital stay"]


def ser(x):
    return json.loads(json.dumps(x, default=str))


def dmy(d):
    return d.strftime("%d.%m.%Y")


def start_day():
    return date(2026, 3, 1) + rnd.randint(0, 200) * DAY


def scenario(prior, cur_len, reason="illness", insurance="GKV"):
    s = start_day()
    pr = prior(s)
    return {"current_start": s, "current_end": s + (cur_len - 1) * DAY, "today": s + rnd.randint(0, 2) * DAY,
            "current_cert": True, "insurance": insurance, "current_reason": reason, "prior": pr}


def chain_prior(n, lengths=(6, 20), reasons=REASONS):
    def build(s):
        out, nxt = [], s
        for _ in range(n):
            p = gap_before(nxt, rnd.randint(10, 120), rnd.randint(*lengths))
            p["reason"] = rnd.choice(reasons)
            out.append(p)
            nxt = p["start"]
        return out
    return build


def dbvo_of(dbvo):
    return ser(dbvo)


def unwanted_41(sc):
    pr = sorted(sc["prior"], key=lambda p: p["start"], reverse=True)
    return ser({"ABGABEGRUND": "41", "AU-AB-AG": sc["current_start"], "AU-AB-SV": "00000000", "KZ-AK-AU": "0",
                "ANZAHL-AU": len(pr), "periods": [[p["start"], p["end"]] for p in pr]})


def build(make, want_send, want_rule, tries=300):
    for _ in range(tries):
        sc = make()
        got, rule, dbvo = decide(sc)
        if got == want_send and rule == want_rule:
            return sc, dbvo
    raise RuntimeError(f"could not build {want_rule}")


# ---------------------------------------------------------------- story 1
def story1(k=1):   # k: multiply the case counts (k=1 = the original 40)
    out = []
    def case(cat, sc, dbvo, observed, must, kind):
        out.append({"story": 1, "category": cat, "scenario": ser(sc),
                    "expected": {"send_41": dbvo is not None and must is None or kind == "defect",
                                 "dbvo": dbvo_of(dbvo) if dbvo else None},
                    "observed_kind": kind, "observed_dbvo": observed, "must_flag": must})
    for _ in range(10 * k):
        sc, d = build(lambda: scenario(chain_prior(rnd.randint(1, 3), reasons=["illness"]), rnd.randint(12, 25),
                                       reason="work accident"), True, "OK")
        case("current AU is a work accident", sc, d, dbvo_of(d), None, "correct output")
    for _ in range(10 * k):
        sc, d = build(lambda: scenario(chain_prior(rnd.randint(1, 3)), rnd.randint(14, 28), reason="rehabilitation"),
                      True, "OK")
        case("rehab stay, mixed prior reasons", sc, d, dbvo_of(d), None, "correct output")
    for _ in range(10 * k):
        sc, d = build(lambda: scenario(chain_prior(1, lengths=(3, 8)), rnd.randint(5, 12),
                                       reason=rnd.choice(REASONS)), False, "R3")
        case("mixed reasons, under 30 days", sc, None, unwanted_41(sc), "R3", "41 sent although not allowed")
    for _ in range(5 * k):
        sc, d = build(lambda: scenario(chain_prior(rnd.randint(1, 2)), rnd.randint(12, 25),
                                       reason="work accident", insurance="PKV"), False, "R4")
        case("privately insured, work accident (BG, outside procedure)", sc, None, unwanted_41(sc), "R4",
             "41 sent although not allowed")
    for _ in range(5 * k):   # payroll software treats an accident period as "not illness" and drops it
        def mk():
            sc = scenario(chain_prior(2, reasons=["illness"]), rnd.randint(14, 25))
            sc["prior"][rnd.randint(0, 1)]["reason"] = "work accident"
            return sc
        sc, d = build(mk, True, "OK")
        acc = [p for p in sc["prior"] if p["reason"] == "work accident"][0]
        bad = dbvo_of(d)
        bad["periods"] = [x for x in bad["periods"] if x[0] != str(acc["start"])]
        bad["ANZAHL-AU"] = len(bad["periods"])
        out.append({"story": 1, "category": "defect: accident period left out", "scenario": ser(sc),
                    "expected": {"send_41": True, "dbvo": dbvo_of(d)}, "observed_kind": "accident period dropped",
                    "observed_dbvo": bad, "must_flag": "F2/F3 periods"})
    return out


# ---------------------------------------------------------------- story 3
def story3(k=1):   # k: multiply the case counts (k=1 = the original 40)
    out = []
    def add(cat, sc, d, observed, must, kind, send):
        out.append({"story": 3, "category": cat, "scenario": ser(sc),
                    "expected": {"send_41": send, "dbvo": dbvo_of(d) if d else None},
                    "observed_kind": kind, "observed_dbvo": observed, "must_flag": must})
    def with_short(where):
        def mk():
            sc = scenario(chain_prior(1, lengths=(15, 25), reasons=["illness"]), rnd.randint(10, 20))
            s, p = sc["current_start"], sc["prior"][0]
            n = rnd.randint(1, 3)
            if where == "before prior":        # seamless to the certified prior AU
                short = P(p["start"] - n * DAY, n, cert=False)
            elif where == "before current":    # seamless to the certified current AU
                short = P(s - n * DAY, n, cert=False)
                p_shift = gap_before(short["start"], rnd.randint(20, 60), p["end"] - p["start"] + DAY and 15)
                sc["prior"] = [p_shift]
            else:                              # one or more days gap: not seamless
                short = gap_before(s, rnd.randint(2, 20), n, cert=False)
            short["reason"] = "illness"
            sc["prior"].append(short)
            return sc
        return mk
    for _ in range(10 * k):
        sc, d = build(with_short("before prior"), True, "OK")
        add("short uncertified days right before a certified AU (included)", sc, d, dbvo_of(d), None, "correct output", True)
    for _ in range(10 * k):
        sc, d = build(with_short("before current"), True, "OK")
        add("short uncertified days right before the current AU (included)", sc, d, dbvo_of(d), None, "correct output", True)
    for _ in range(10 * k):
        sc, d = build(with_short("gap"), True, "OK")
        add("short uncertified days with a gap (left out)", sc, d, dbvo_of(d), None, "correct output", True)
    for _ in range(5 * k):
        def mk():
            sc = scenario(lambda s: [], rnd.randint(10, 20))
            sc["prior"] = [dict(gap_before(sc["current_start"], rnd.randint(3, 40), rnd.randint(1, 3), cert=False),
                                reason="illness")]
            return sc
        sc, d = build(mk, False, "R2")
        add("only uncertified short days, none seamless", sc, None, unwanted_41(sc), "R2", "41 sent although not allowed", False)
    for _ in range(5 * k):   # software also reports the non-seamless short absence
        sc, d = build(with_short("gap"), True, "OK")
        short = [p for p in sc["prior"] if not p["cert"]][0]
        bad = dbvo_of(d)
        bad["periods"] = sorted(bad["periods"] + [[str(short["start"]), str(short["end"])]], reverse=True)
        bad["ANZAHL-AU"] = len(bad["periods"])
        add("defect: non-seamless short days reported", sc, d, bad, "F2/F3 periods", "uncertified days included", True)
    return out


# ---------------------------------------------------------------- story 4
def insurer_reply(d, rng):
    """A correct 61 for the employer's 41 (dict with periods) following VB §3.12.2-3.12.14."""
    rows = []
    for a, b in d["periods"]:
        a, b = date.fromisoformat(a), date.fromisoformat(b)
        nw = rng.choice(["1", "1", "1", "2", "4"])
        tn = ["00000000", "00000000"]
        if nw == "2":
            cut = a + rng.randint(1, max(1, (b - a).days)) * DAY
            tn = [cut.strftime("%Y%m%d"), b.strftime("%Y%m%d")]
        kz = "2" if nw == "4" else rng.choice(["1", "1", "2", "3", "5"])
        ta = ["00000000", "00000000"]
        if kz == "5":
            ta = [a.strftime("%Y%m%d"), (a + max(0, (b - a).days // 2) * DAY).strftime("%Y%m%d")]
        rows.append({"BEGINN": str(a), "ENDE": str(b), "KZ-NACHWEIS": nw, "TEIL-NACHWEIS": tn, "KZ-AU": kz, "TEIL-ANR": ta})
    added = []
    for _ in range(rng.randint(0, 2)):   # insurer finds further relevant AUs: appended after the employer's
        last = date.fromisoformat(rows[-1]["BEGINN"]) if not added else date.fromisoformat(added[-1]["BEGINN"])
        end = last - rng.randint(10, 60) * DAY
        added.append({"BEGINN": str(end - 6 * DAY), "ENDE": str(end), "KZ-NACHWEIS": "1",
                      "TEIL-NACHWEIS": ["00000000", "00000000"], "KZ-AU": "1", "TEIL-ANR": ["00000000", "00000000"]})
    kz_ak = rng.choice(["0", "0", "0", "4"])
    au_sv = "00000000"
    if rng.random() < 0.25:
        au_sv = (date.fromisoformat(d["AU-AB-AG"]) - rng.randint(1, 3) * DAY).strftime("%Y%m%d")
    frist = "00000000" if kz_ak == "4" else date.fromisoformat(rows[-1]["BEGINN"]).strftime("%Y%m%d")
    return {"ABGABEGRUND": "61", "AU-AB-AG": d["AU-AB-AG"], "AU-AB-SV": au_sv, "KZ-AK-AU": kz_ak,
            "12-MONATSFRIST-AB": frist, "ANZAHL-AU": len(rows) + len(added), "periods": rows + added,
            "employer_count": len(rows)}


R61 = {  # defect -> (rule that must flag, source)
    "employer periods reordered": ("R61-order", "VB 13.4 §3.12.7"),
    "employer period dropped": ("R61-keep", "VB 13.4 §3.12.6/3.12.7"),
    "added period placed first": ("R61-order", "VB 13.4 §3.12.7"),
    "AU-AB-AG replaced by insurer date": ("R61-AU-AB-AG", "VB 13.4 §3.12.2"),
    "KZ-NACHWEIS 4 but KZ-AU not 2": ("R61-KZ-AU", "VB 13.4 §3.12.5/3.12.12"),
    "TEIL-NACHWEIS filled without KZ-NACHWEIS 2": ("R61-TEIL-NACHWEIS", "VB 13.4 §3.12.10"),
    "TEIL-ANR filled without KZ-AU 5": ("R61-TEIL-ANR", "VB 13.4 §3.12.13"),
    "KZ-AK-AU 4 but 12-month start filled": ("R61-12-MONATSFRIST", "VB 13.4 §3.12.5"),
}


def break_reply(r, kind, rng):
    r = json.loads(json.dumps(r))
    emp = r["periods"][:r["employer_count"]]
    if kind == "employer periods reordered":
        r["periods"][:r["employer_count"]] = list(reversed(emp))
    elif kind == "employer period dropped":
        r["periods"].pop(rng.randrange(r["employer_count"]))
        r["ANZAHL-AU"] -= 1
    elif kind == "added period placed first":
        extra = {"BEGINN": "2025-01-06", "ENDE": "2025-01-10", "KZ-NACHWEIS": "1", "TEIL-NACHWEIS": ["00000000", "00000000"],
                 "KZ-AU": "1", "TEIL-ANR": ["00000000", "00000000"]}
        r["periods"].insert(0, extra)
        r["ANZAHL-AU"] += 1
    elif kind == "AU-AB-AG replaced by insurer date":
        r["AU-AB-AG"] = str(date.fromisoformat(r["AU-AB-AG"]) - 2 * DAY)
    elif kind == "KZ-NACHWEIS 4 but KZ-AU not 2":
        r["periods"][0].update({"KZ-NACHWEIS": "4", "TEIL-NACHWEIS": ["00000000", "00000000"], "KZ-AU": "1",
                                "TEIL-ANR": ["00000000", "00000000"]})
    elif kind == "TEIL-NACHWEIS filled without KZ-NACHWEIS 2":
        p = r["periods"][0]
        p.update({"KZ-NACHWEIS": "1", "TEIL-NACHWEIS": [p["BEGINN"].replace("-", ""), p["ENDE"].replace("-", "")]})
    elif kind == "TEIL-ANR filled without KZ-AU 5":
        p = r["periods"][0]
        p.update({"KZ-NACHWEIS": "1", "TEIL-NACHWEIS": ["00000000", "00000000"], "KZ-AU": "1",
                  "TEIL-ANR": [p["BEGINN"].replace("-", ""), p["ENDE"].replace("-", "")]})
    elif kind == "KZ-AK-AU 4 but 12-month start filled":
        r["KZ-AK-AU"] = "4"
        r["12-MONATSFRIST-AB"] = r["periods"][-1]["BEGINN"].replace("-", "")
    return r


def story4():
    out = []
    for i in range(60):
        sc, d = build(lambda: scenario(chain_prior(rnd.randint(2, 3), reasons=["illness"]), rnd.randint(12, 25)),
                      True, "OK")
        reply = insurer_reply(dbvo_of(d), rnd)
        if i < 20:
            out.append({"story": 4, "category": "correct insurer reply", "scenario": ser(sc),
                        "employer_41": dbvo_of(d), "observed_kind": "correct 61", "observed_61": reply,
                        "expected": {"reply_valid": True}, "must_flag": None})
        else:
            kind = list(R61)[(i - 20) % len(R61)]
            rule, src = R61[kind]
            out.append({"story": 4, "category": f"defect: {kind}", "scenario": ser(sc), "employer_41": dbvo_of(d),
                        "observed_kind": kind, "observed_61": break_reply(reply, kind, rnd),
                        "expected": {"reply_valid": False, "source": src}, "must_flag": rule})
    return out


# ---------------------------------------------------------------- story 6
def uid():
    return str(uuid.UUID(int=rnd.getrandbits(128))).upper()


def flow(rng):
    azvu = f"{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(1, 999):03d}"
    start = start_day()
    efz_wrong = start + rng.randint(15, 25) * DAY
    efz_right = efz_wrong - rng.randint(1, 5) * DAY
    end_eel = efz_right + rng.randint(1, 10) * DAY
    id41, id01a, id88, id01b = uid(), uid(), uid(), uid()
    first61 = add_months(start, -rng.randint(4, 10))
    msgs = [
        {"no": 1, "from": "AG", "Abgabegrund": "41", "Stornierung": "N", "DSID": id41, "AZVU": azvu},
        {"no": 2, "from": "KK", "Abgabegrund": "61", "Stornierung": "N", "REF-ID": id41, "AZVU": azvu,
         "Beginn_12_Monatsfrist": dmy(first61)},
        {"no": 3, "from": "AG", "Abgabegrund": "01", "Stornierung": "N", "DSID": id01a, "AZVU": azvu, "EFZ_Ende": dmy(efz_wrong)},
        {"no": 4, "from": "KK", "Abgabegrund": "61", "Stornierung": "N", "REF-ID": id41, "AZVU": azvu,
         "Beginn_12_Monatsfrist": dmy(first61)},
        {"no": 5, "from": "AG", "Abgabegrund": "88", "Stornierung": "J", "DSID": id88, "DSID-UR": id01a, "AZVU": azvu},
        {"no": 6, "from": "AG", "Abgabegrund": "01", "Stornierung": "N", "DSID": id01b, "AZVU": azvu, "EFZ_Ende": dmy(efz_right)},
        {"no": 7, "from": "KK", "Abgabegrund": "62", "Stornierung": "N", "REF-ID": id01b, "AZVU": azvu,
         "Ende_EEL": dmy(end_eel), "Ende_EEL_Grund": "99"},
    ]
    return {"messages": msgs, "expected_efz_final": dmy(efz_right), "azvu": azvu}


FLOW_DEFECTS = {
    "cancellation 88 missing": ("F-88", "GG EEL 13.1 §2.5", lambda m: m.pop(4)),
    "88 not flagged Stornierung J": ("F-88-flag", "GG EEL 13.1 §2.5", lambda m: m[4].update({"Stornierung": "N"})),
    "88 points to the wrong message": ("F-88-UR", "GG EEL 13.1 §2.5", lambda m: m[4].update({"DSID-UR": m[0]["DSID"]})),
    "no corrected 01 after the 88": ("F-new-01", "GG EEL 13.1 §2.5", lambda m: m.pop(5)),
    "corrected 01 sent before the 88": ("F-order", "GG EEL 13.1 §2.5", lambda m: m.insert(4, m.pop(5))),
    "AZVU differs in one message": ("F-AZVU", "VB 13.4 (AKTENZEICHEN-VERURSACHER)", lambda m: m[2].update({"AZVU": m[2]["AZVU"][:-1] + "9"})),
    "62 refers to the cancelled 01": ("F-REF-62", "VB 13.4 §3.1.18 REFERENZ-ID", lambda m: m[6].update({"REF-ID": m[2]["DSID"]})),
    "61 does not refer to the 41": ("F-REF-61", "VB 13.4 §3.1.18 REFERENZ-ID", lambda m: m[1].update({"REF-ID": m[2]["DSID"]})),
    "corrected 01 repeats the wrong date": ("F-correction", "Hinweise Testkonstellation", lambda m: m[5].update({"EFZ_Ende": m[2]["EFZ_Ende"]})),
    "88 cancels the 41 instead of the 01": ("F-88-UR", "GG EEL 13.1 §2.5", lambda m: m[4].update({"DSID-UR": m[0]["DSID"]}) ),
}


def story6():
    out = []
    names = list(FLOW_DEFECTS)
    for i in range(60):
        f = flow(rnd)
        case = {"story": 6, "scenario": {"azvu": f["azvu"], "expected_efz_final": f["expected_efz_final"]},
                "messages": f["messages"]}
        if i < 20:
            case.update(category="correct cancel-and-correct flow", observed_kind="correct flow",
                        expected={"flow_valid": True}, must_flag=None)
        else:
            kind = names[(i - 20) % len(names)]
            rule, src, fn = FLOW_DEFECTS[kind]
            fn(case["messages"])
            case.update(category=f"defect: {kind}", observed_kind=kind, expected={"flow_valid": False, "source": src},
                        must_flag=rule)
        out.append(case)
    return out


def main():
    cases = story1() + story3() + story4() + story6()
    for i, c in enumerate(cases, 1):
        c["id"] = f"S{c['story']}-{i:03d}"
    assert len(cases) == 200, len(cases)
    (ROOT / "data" / "story_cases.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False), encoding="utf-8")
    write_md(cases)
    from collections import Counter
    print(Counter(c["story"] for c in cases))
    print(f"{len(cases)} cases -> data/story_cases.json, testCase-stories.md")


def short(d):
    return date.fromisoformat(str(d)).strftime("%d.%m.%y")


def write_md(cases):
    from collections import Counter
    L = ["# Story test cases – 200 synthetic cases (stories 1, 3, 4, 6)", "",
         "Generated by `harness/generate_story_cases.py` (seed 4136). Machine-readable: `data/story_cases.json`.",
         "All people, IDs and dates are fabricated. Ground truth comes from the rule text, not from an LLM.", "",
         "| Story | Cases | Situation | Rules (source) |", "|---|---|---|---|",
         "| 1 | 40 | Work accident or rehab instead of illness | Reason does not matter (VB 13.4 §3.12 p.135); private insurance → no 41 (p.136) |",
         "| 3 | 40 | Short sick days without a certificate | Reported only if a certified AU follows seamlessly (VB 13.4 §3.12 p.135) |",
         "| 4 | 60 | The insurer's reply (61) to the 41 | Field rules VB 13.4 §3.12.2–3.12.14 |",
         "| 6 | 60 | Cancel and correct a 01 (41→61→01→61→88→01→62) | GG EEL 13.1 §2.5, VB 13.4 §3.1.18, Hinweise Testkonstellation |",
         "", "## Categories", "| Story | Category | Cases | Must flag |", "|---|---|---|---|"]
    for (s, cat, must), n in Counter((c["story"], c["category"], c["must_flag"]) for c in cases).items():
        L.append(f"| {s} | {cat} | {n} | {must or '–'} |")
    L += ["", "## Stories 1 and 3: prior-illness request (41)",
          "| ID | Category | Current AU (reason) | Prior AUs (* = no certificate) | Expected | Must flag |", "|---|---|---|---|---|---|"]
    for c in cases:
        if c["story"] not in (1, 3):
            continue
        s = c["scenario"]
        pr = "; ".join(f"{short(p['start'])}–{short(p['end'])}{'' if p['cert'] else '*'} ({p.get('reason', 'illness')})"
                       for p in sorted(s["prior"], key=lambda p: p["start"], reverse=True))
        exp = "send 41" if c["expected"]["send_41"] else "no 41"
        L.append(f"| {c['id']} | {c['category']} | {short(s['current_start'])}–{short(s['current_end'])} ({s['current_reason']}, {s['insurance']}) "
                 f"| {pr} | {exp} | {c['must_flag'] or '–'} |")
    L += ["", "## Story 4: insurer reply (61)",
          "| ID | Category | Employer periods | Reply periods (KZ-NACHWEIS/KZ-AU) | KZ-AK-AU | Must flag |", "|---|---|---|---|---|---|"]
    for c in cases:
        if c["story"] != 4:
            continue
        r = c["observed_61"]
        emp = ", ".join(f"{short(a)}–{short(b)}" for a, b in c["employer_41"]["periods"])
        rep = ", ".join(f"{short(p['BEGINN'])}–{short(p['ENDE'])} ({p['KZ-NACHWEIS']}/{p['KZ-AU']})" for p in r["periods"])
        L.append(f"| {c['id']} | {c['category']} | {emp} | {rep} | {r['KZ-AK-AU']} | {c['must_flag'] or '–'} |")
    L += ["", "## Story 6: cancel and correct",
          "| ID | Category | AZVU | Message codes | Corrected EFZ end | Must flag |", "|---|---|---|---|---|---|"]
    for c in cases:
        if c["story"] != 6:
            continue
        codes = " → ".join(m["Abgabegrund"] for m in c["messages"])
        L.append(f"| {c['id']} | {c['category']} | {c['scenario']['azvu']} | {codes} | {c['scenario']['expected_efz_final']} | {c['must_flag'] or '–'} |")
    (ROOT / "testCase-stories.md").write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
