"""The six agents: prompt + input builder + mock answer. Authors draft, critics only list issues, nobody approves."""
import json
import re
from pathlib import Path

from llm import PROMPT, call

SCOPE = ("Scope: the employer's request 'Abgabegrund 41' with Datenbaustein DBVO (prior periods of incapacity "
         "for work): when a 41 may be sent and what the employer must put in it. Fields that only the health "
         "insurer fills in its reply (Abgabegrund 61) are out of scope.")

# ---------------------------------------------------------------- 02 requirements
# The code checks that exist (run_review.dbvo_findings). Stage 1 links each criterion to one of them; stage 3 runs
# only the linked checks and sends criteria without a code check to a person.
CHECKS = {
    "F1": "Abgabegrund = 41",
    "F2": "ANZAHL-AU = number of prior AUs to report",
    "F3": "Reported prior AU periods are the right ones",
    "F4": "Employer sends KZ-AK-AU = 0 (default value)",
    "F5": "AU-AB-AG = start of the current AU",
    "F6": "Employer sends AU-AB-SV = 00000000 (default value)",
    "F7": "Prior AUs listed most recent first",
    "C9": "41 only if the current AU and at least one prior AU are certified",
    "C10": "At most 6 months between the start of the current AU and the end of the last prior AU",
    "C11": "Prior AUs included only if each gap is at most 6 months",
    "C12": "Prior AUs of the last 12 months plus the current AU reach at least 30 days",
    "C13": "No 41 for private insurance or marginal employment",
}
CHECK_LIST = "\n".join(f"{k}: {v}" for k, v in CHECKS.items())

REQ_SYSTEM = f"""You turn German rule text into atomic, testable review criteria. {SCOPE}
Use only the rule text you are given. Each criterion needs a quote copied character for character from one chunk
(at most 200 characters) and that chunk's id. Do not invent rules. Set "uncertain": true if the text leaves room
for more than one reading. At most 15 criteria.
Link each criterion to the code check below that tests it ("check"), or null if none of them tests it:
{CHECK_LIST}
Answer with JSON only:
{{"criteria":[{{"id":"R-01","text":"...","chunk":"VB/3.12.md","quote":"...","check":"F5","uncertain":false}}]}}"""

REQ_CRITIC_SYSTEM = f"""You review draft criteria against the rule text. {SCOPE}
List problems only: a rule in the text that no criterion covers, duplicates, a criterion its quote does not support,
a criterion that cannot be tested. You never approve and never rewrite criteria.
Answer with JSON only: {{"issues":[{{"criterion":"R-03 or null","problem":"...","fix":"..."}}]}}
Return an empty list if there is nothing important."""


def chunk_text(chunks):
    return "\n\n".join(f"[{c['path']}] §{c['section']} {c['title']} (p.{c['page_start']})\n{c['text']}" for c in chunks)


def requirement_agent(chunks, draft=None, issues=None):
    user = "RULE TEXT\n" + chunk_text(chunks)
    if draft:
        user += ("\n\nREVISION. Your previous criteria:\n" + json.dumps(draft, ensure_ascii=False)
                 + "\nFix these issues:\n" + json.dumps(issues, ensure_ascii=False))
    return call("requirement_agent", "author", REQ_SYSTEM, user, _mock_requirements)["criteria"]


def requirement_critic(chunks, criteria):
    user = "RULE TEXT\n" + chunk_text(chunks) + "\n\nDRAFT CRITERIA\n" + json.dumps(criteria, ensure_ascii=False)
    return call("requirement_critic", "light", REQ_CRITIC_SYSTEM, user, _mock_critic)["issues"]


# ---------------------------------------------------------------- 03 test design
TC_SYSTEM = f"""You design test scenarios for a reviewer of the 'Abgabegrund 41' message. {SCOPE}
Use only the approved criteria. Write scenarios, never expected results: code computes those from the rules.
Cover normal, boundary and invalid situations. Dates are ISO yyyy-mm-dd. "current_end" may be null (open end).
"insurance" is one of GKV, PKV, Minijob. "cert" says whether a doctor's certificate exists. At most 20 cases.
Answer with JSON only:
{{"cases":[{{"id":"T-01","criterion":"R-02","kind":"normal|boundary|invalid","idea":"one sentence",
"scenario":{{"current_start":"2026-05-04","current_end":"2026-05-29","today":"2026-05-06","current_cert":true,
"insurance":"GKV","prior":[{{"start":"2026-02-02","end":"2026-02-20","cert":true}}]}}}}]}}"""

TC_CRITIC_SYSTEM = f"""You review a test plan. {SCOPE}
You see the approved criteria and each test case with the expected result that code computed.
List problems only: a criterion without a test, a missing boundary (for example a gap of exactly 6 months, a sum of
exactly 30 days), a case linked to the wrong criterion, duplicates. You never change expected results.
Answer with JSON only: {{"issues":[{{"case":"T-04 or null","problem":"...","fix":"..."}}]}}
Return an empty list if there is nothing important."""


def testcase_agent(criteria, draft=None, issues=None):
    user = "APPROVED CRITERIA\n" + json.dumps(criteria, ensure_ascii=False)
    if draft:
        user += ("\n\nREVISION. Your previous cases:\n" + json.dumps(draft, ensure_ascii=False)
                 + "\nFix these issues:\n" + json.dumps(issues, ensure_ascii=False))
    return call("testcase_agent", "author", TC_SYSTEM, user, _mock_cases)["cases"]


def testcase_critic(criteria, cases):
    user = ("APPROVED CRITERIA\n" + json.dumps(criteria, ensure_ascii=False)
            + "\n\nTEST CASES WITH EXPECTED RESULTS (computed by code)\n" + json.dumps(cases, ensure_ascii=False, default=str))
    return call("testcase_critic", "light", TC_CRITIC_SYSTEM, user, _mock_critic)["issues"]


# ---------------------------------------------------------------- 04 verdict
FINDINGS_CRITIC_V1 = """You double-check the result of a rule-based reviewer for one 'Abgabegrund 41' message.
You see the scenario, the message the payroll software produced and every check with its status.
If a check's status looks doubtful (wrong reading of a date, a rule the check may not cover), name it.
You can only send a check to a person for review. You cannot pass or fail anything.
Answer with JSON only: {"review":[{"check":"C12","note":"why a person should look"}]}
Return an empty list if every status looks right."""

# Experiment 2: flag only with concrete evidence; code drops any flag without it.
FINDINGS_CRITIC_V2 = """You double-check the result of a rule-based reviewer for one 'Abgabegrund 41' message.
You see the scenario, the message the payroll software produced and every check with its status.
Most results are right. Flag a check only if you can point to a concrete fact that contradicts its status:
a field of the message or the scenario, the value you see, and the value it should have.
Do not flag a check because the rule is complex, because you are unsure, or because a person might like to look.
If you cannot give all three facts, do not flag. You cannot pass or fail anything.
Answer with JSON only: {"review":[{"check":"F5","field":"AU-AB-AG","seen":"2026-03-25","expected":"2026-03-24","note":"..."}]}
Return an empty list if you have no such evidence."""

# Experiment 3: the AI sees the code's status and the rule text, and speaks only when it disagrees with the code.
FINDINGS_CRITIC_V3 = """You double-check the result of a rule-based reviewer for one 'Abgabegrund 41' message.
For every check you see the code's status (PASS or MISMATCH), what it expected, what it found, and the rule text.
Most results are right. Speak only when you disagree with the code: a PASS that should be an error, or a MISMATCH
that should pass. For each disagreement give the field, the value you see, the value it should have, and copy the
rule sentence that supports you. Do not repeat errors the code already found. If you agree with every check, say nothing.
Answer with JSON only:
{"review":[{"check":"C11","field":"...","seen":"...","expected":"...","rule_quote":"...","note":"..."}]}
Return an empty list if you agree with the code."""

EXPLAINER_SYSTEM = """You explain a review result to a payroll clerk in plain English, at most three short sentences.
Name the checks that failed or need review and what to do. Use only the facts given.
Answer with JSON only: {"summary":"..."}"""


_CHUNKS = None


def rule_text(source, limit=2500):
    """German rule text for a check's source, e.g. 'VB 13.4 §3.12.2 p.137' -> chunk VB/3.12.2.md."""
    global _CHUNKS
    if _CHUNKS is None:
        path = Path(__file__).resolve().parent.parent / "chunks" / "chunks.jsonl"
        _CHUNKS = {c["section"]: c["text"] for c in map(json.loads, open(path, encoding="utf-8")) if c["doc"] == "VB"}
    m = re.search(r"§(3\.12(?:\.\d+)?)", source or "")
    return _CHUNKS.get(m.group(1), "")[:limit] if m else ""


def findings_critic(case, findings):
    user = json.dumps({"scenario": case["scenario"], "observed_message": case.get("observed_dbvo"),
                       "checks": [{k: f.get(k) for k in ("id", "rule", "expected", "actual", "status")} for f in findings]},
                      ensure_ascii=False, default=str)
    if PROMPT == "v3":
        user = json.dumps({"scenario": case["scenario"], "observed_message": case.get("observed_dbvo"),
                           "checks": [{**{k: f.get(k) for k in ("id", "rule", "source", "expected", "actual", "status")},
                                       "rule_text": rule_text(f.get("source", ""))} for f in findings]},
                          ensure_ascii=False, default=str)
        review = call("findings_critic", "light", FINDINGS_CRITIC_V3, user, lambda u: {"review": []}, 8000)["review"]
        return [r for r in review if all(str(r.get(k) or "").strip() for k in ("field", "seen", "expected", "rule_quote"))]
    if PROMPT == "v1":
        return call("findings_critic", "light", FINDINGS_CRITIC_V1, user, lambda u: {"review": []}, 8000)["review"]
    review = call("findings_critic", "light", FINDINGS_CRITIC_V2, user, lambda u: {"review": []}, 8000)["review"]
    return [r for r in review if all(str(r.get(k) or "").strip() for k in ("field", "seen", "expected"))]


def explainer(findings):
    user = json.dumps([{k: f.get(k) for k in ("id", "rule", "source", "expected", "actual", "status", "note")}
                       for f in findings], ensure_ascii=False, default=str)
    return call("explainer", "light", EXPLAINER_SYSTEM, user,
                lambda u: {"summary": "Mock summary: see the checks marked MISMATCH or NEEDS_REVIEW."}, 8000)["summary"]


# ---------------------------------------------------------------- mocks (TEAM10_MOCK=1)
def _mock_critic(user):
    """First draft gets one issue, a revision gets none: exercises exactly one loop round."""
    return {"issues": [] if "REVISION" in user else [{"criterion": None, "problem": "mock issue", "fix": "mock fix"}]}


def _mock_requirements(user):
    out = []
    for i, m in enumerate(re.finditer(r"^\[(VB/[^\]]+)\][^\n]*\n(.{40,})", user, re.M), 1):
        if i > 3:
            break
        out.append({"id": f"R-{i:02d}", "text": f"mock criterion {i}", "chunk": m.group(1),
                    "quote": m.group(2)[:60], "check": ["F5", "C12", None][i - 1], "uncertain": False})
    return {"criteria": out}


def _mock_cases(user):
    sc = {"current_start": "2026-05-04", "current_end": "2026-05-29", "today": "2026-05-06", "current_cert": True,
          "insurance": "GKV", "prior": [{"start": "2026-02-02", "end": "2026-02-20", "cert": True}]}
    return {"cases": [{"id": "T-01", "criterion": "R-01", "kind": "normal", "idea": "mock", "scenario": sc},
                      {"id": "T-02", "criterion": "R-02", "kind": "invalid", "idea": "mock",
                       "scenario": dict(sc, insurance="PKV")}]}
