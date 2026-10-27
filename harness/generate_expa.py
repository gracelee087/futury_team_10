"""Experiment a: three new test sets of 200 cases each, same ground-truth rules, new random seed.

  data/expa_sick.json    sick-leave 41 (golden 5 + decision 100 + output 80 + ambiguous 15), like data/testcases.json
  data/expa_story1.json  story 1, work accident / rehab (5 x the 40 of data/story_cases.json)
  data/expa_story3.json  story 3, short uncertified days (5 x the 40)

Usage: python harness/generate_expa.py
"""
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_cases as gc  # noqa: E402
import generate_story_cases as gs  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = 2610

# same categories as generate_cases, counts scaled from 150 / 120 / 25 to 100 / 80 / 15
DECISION = [(cat, n, b, want, rule) for (cat, _, b, want, rule), n in
            zip(gc.DECISION, [20, 8, 8, 8, 8, 7, 7, 4, 4, 5, 5, 5, 5, 6])]
MUTATIONS = [(name, n, flag, need2) for (name, _, flag, need2), n in zip(gc.MUTATIONS, [26] + [6] * 9)]
AMBIGUOUS = 15


def sick():
    gc.rnd.seed(SEED)
    cases = []
    for cid, sc, note in gc.golden():
        send, rule, dbvo = gc.decide(sc)
        cases.append({"id": cid, "group": "golden", "category": note, "scenario": gc.ser(sc),
                      "expected": {"send_41": send, "rule": rule, "dbvo": gc.ser(dbvo) if send else None},
                      "observed_kind": "correct output" if send else "41 sent although not allowed",
                      "must_flag": None if send else rule})
    n = 0
    for cat, count, builder, want, rule in DECISION:
        for _ in range(count):
            n += 1
            sc, dbvo = gc.build_one(builder, want, rule)
            cases.append({"id": f"A-DEC-{n:03d}", "group": "decision", "category": cat, "scenario": gc.ser(sc),
                          "expected": {"send_41": want, "rule": rule, "dbvo": gc.ser(dbvo) if want else None},
                          "observed_kind": "correct output" if want else "41 sent although not allowed",
                          "must_flag": None if want else rule})
    n = 0
    for name, count, flag, need2 in MUTATIONS:
        for _ in range(count):
            n += 1
            sc, dbvo = gc.build_one(lambda: gc.b_normal(gc.rnd.randint(2, 3) if need2 else None), True, "OK")
            cases.append({"id": f"A-OUT-{n:03d}", "group": "output", "category": name, "scenario": gc.ser(sc),
                          "expected": {"send_41": True, "rule": "OK", "dbvo": gc.ser(dbvo)},
                          "observed_kind": name, "observed_dbvo": gc.mutate(name, gc.ser(dbvo)), "must_flag": flag})
    for i in range(AMBIGUOUS):
        sc, info = gc.build_one(gc.b_ambiguous, None, "AMBIGUOUS")
        cases.append({"id": f"A-AMB-{i + 1:03d}", "group": "ambiguous",
                      "category": "12-month sum: chain only vs all prior AUs disagree", "scenario": gc.ser(sc),
                      "expected": {"send_41": None, "rule": "AMBIGUOUS", "detail": info},
                      "observed_kind": "41 sent (chain only)", "must_flag": "NEEDS_REVIEW",
                      "observed_dbvo": gc.chain_only_41(sc)})
    for c in cases:
        if "observed_dbvo" not in c:
            c["observed_dbvo"] = c["expected"].get("dbvo") or gc.unwanted_41(c["scenario"])
    return cases


def story(fn, n):
    gs.rnd.seed(SEED + n)
    cases = fn(k=5)
    for i, c in enumerate(cases, 1):
        c["id"], c["group"] = f"A-S{n}-{i:03d}", f"story{n}"
    return cases


def main():
    for name, cases in [("sick", sick()), ("story1", story(gs.story1, 1)), ("story3", story(gs.story3, 3))]:
        assert len(cases) == 200 and len({c["id"] for c in cases}) == 200, (name, len(cases))
        (ROOT / "data" / f"expa_{name}.json").write_text(json.dumps(cases, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: 200 cases -> data/expa_{name}.json")


if __name__ == "__main__":
    main()
