"""Stage 0: find the relevant spec sections for Abgabegrund 41 in all 1,219 chunks, and measure how well.

Code shortlists candidates by words in the text (no section numbers, no metadata), the Source finder AI
picks the relevant ones with a reason, and code compares the pick with two answer lists we chose by hand:
  A = VB 3.12-3.12.8 (what the rule writer reads today)
  B = A + VB 3.12.9-3.12.14 (insurer reply) + Beispiel 13-13.5 + GG_EEL 2.1.2

    python orchestrator/find_sources.py            # real Claude (Haiku)
    TEAM10_MOCK=1 python orchestrator/find_sources.py
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(Path(__file__).parent)]
from llm import call, lf_client  # noqa: E402
from run_review import load_env  # noqa: E402

SHORTLIST = 60
WORDS = [r"Vorerkrank", r"\bDBVO\b", r"Abgabegrund\s*[„\"']?41", r"Grund\s*[„\"']?41", r"[„\"']41[“\"']",
         r"Vorerkrankungszeit", r"12-Monatsfrist", r"Arbeitsunfähigkeitszeit"]
GOLD_A = {"VB/3.12.md"} | {f"VB/3.12.{i}.md" for i in range(1, 9)}
GOLD_B = (GOLD_A | {f"VB/3.12.{i}.md" for i in range(9, 15)} | {"Beispiel/13.md"}
          | {f"Beispiel/13.{i}.md" for i in range(1, 6)} | {"GG_EEL/2.1.2.md"})

SYSTEM = """You find the specification sections that matter for one task: the employer's request for prior sickness
periods (Abgabegrund 41, data block DBVO) in the German EEL procedure, and the insurer's answer to it.
You get candidate sections (path, title, start of the text). Pick every section a tester needs to write test criteria
and test cases for this task: field rules, rules for when the request may be sent, the answer data, and worked
examples. Leave out sections about other Abgabegründe or general procedure.
Answer with JSON only: {"relevant":[{"path":"VB/3.12.md","reason":"..."}]}"""


def shortlist(chunks):
    def hits(c):
        return sum(len(re.findall(w, c["title"] + "\n" + c["text"])) for w in WORDS)
    scored = sorted(((hits(c), c) for c in chunks), key=lambda x: -x[0])
    top = [c for n, c in scored[:SHORTLIST] if n > 0]
    # field sections often never say the topic word: a matching section brings its sub-sections along
    keys = {(c["doc"], str(c["section"])) for c in top}
    kids = [c for c in chunks if (c["doc"], str(c["parent"])) in keys and c not in top]
    return top + kids


def _mock(user):
    return {"relevant": [{"path": p, "reason": "mock"} for p in re.findall(r"^\[([^\]]+)\]", user, re.M)[:10]]}


def measure(picked, gold):
    hit = picked & gold
    return {"gold": len(gold), "picked": len(picked), "correct": len(hit),
            "recall": round(len(hit) / len(gold), 3), "precision": round(len(hit) / len(picked), 3) if picked else 0.0,
            "missed": sorted(gold - picked), "extra": sorted(picked - gold)}


def main():
    load_env(ROOT / ".env")
    run_id = f"SOURCES-{datetime.now():%Y%m%d-%H%M%S}"
    lf = lf_client()
    root = lf.start_as_current_span(name="find-sources") if lf else None
    span = root.__enter__() if root else None
    chunks = [json.loads(line) for line in open(ROOT / "chunks" / "chunks.jsonl", encoding="utf-8")]
    cands = shortlist(chunks)
    user = "\n\n".join(f"[{c['path']}] {c['title']}\n{c['text'][:600]}" for c in cands)
    ans = call("source_finder", "light", SYSTEM, user, _mock, max_tokens=8000)
    allowed = {c["path"] for c in cands}
    picked = [r for r in ans.get("relevant", []) if r.get("path") in allowed]   # code drops paths it never offered
    paths = {r["path"] for r in picked}
    result = {"run_id": run_id, "chunks": len(chunks), "shortlist": len(cands),
              "shortlist_vs_A": measure(allowed, GOLD_A), "shortlist_vs_B": measure(allowed, GOLD_B),
              "ai_vs_A": measure(paths, GOLD_A), "ai_vs_B": measure(paths, GOLD_B),
              "dropped_unknown_paths": len(ans.get("relevant", [])) - len(picked), "picked": picked}
    if span:
        span.update_trace(name="find-sources", session_id=run_id, tags=["Team10", "agents", "sources"],
                          output={k: result[k] for k in ("shortlist", "ai_vs_A", "ai_vs_B")})
        for k in ("ai_vs_A", "ai_vs_B"):
            span.score_trace(name=f"source_recall_{k[-1]}", value=result[k]["recall"], data_type="NUMERIC")
        root.__exit__(None, None, None)
        lf.flush()
    out = ROOT / "reports" / f"{result['run_id']}.json"
    out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    for k in ("shortlist_vs_A", "shortlist_vs_B", "ai_vs_A", "ai_vs_B"):
        m = result[k]
        print(f"{k:15} correct {m['correct']}/{m['gold']}  picked {m['picked']}  recall {m['recall']}  "
              f"precision {m['precision']}  missed {m['missed']}")
    print("->", out)


if __name__ == "__main__":
    main()
