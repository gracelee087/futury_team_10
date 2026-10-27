# Experiments — AI helpers on the 300 harness cases

Setup for all experiments: `python orchestrator/harness_agents.py` on `data/testcases.json` (300 synthetic cases).
Code verdict first; the Double-check AI (findings_critic, Haiku 5.5) and the Explainer AI run on a sample:
every case the code flags + 10% of the clean ones (seed 7). The Double-check AI can only send a check to a
person (NEEDS_REVIEW); it can never turn a check into PASS. Score = same as the harness (`run_harness.score`).

## Experiment 1 — prompt agents-v1 (2026-10-26)
- Run: `AGENTS-HARNESS-20261026-223252`, report `reports/AGENTS-HARNESS-20261026-223252.json`
- Double-check prompt: "If a check's status looks doubtful, name it." (no evidence required)
- Double-check runs: 188, explanations: 175

| | Result |
|---|---|
| Code only | 300 / 300 |
| After Double-check AI | 183 / 300 |
| Cases where the AI sent checks to a person | 147 |
| Found error → "only person review" | 108 |
| Clean case → unnecessary person review | 9 |
| Missed errors (error turned into PASS) | 0 |

- Checks sent to a person most often: C12 (30-day sum) 101, F1 32, C11 30, F3 26, C9 23, F2 22, F7 20.
- Langfuse export partly failed during the run (timeouts / DNS errors to cloud.langfuse.com); the Langfuse record
  of this run may be incomplete. The local report is complete.
- Reading: the Double-check AI is too cautious. People get more work (opposite of H3). No error was missed.

## Experiment 2 — prompt agents-v2 (evidence required)
- Change: the Double-check AI may flag a check only with concrete evidence (field, value it saw, value it expects);
  code drops any flag without evidence. Everything else unchanged (same cases, same sample seed).
- Run: `AGENTS-HARNESS-20261026-235609`, report `reports/AGENTS-HARNESS-20261026-235609.json` (prompt agents-v2)
- Double-check runs: 188 (same sample as experiment 1), explanations: 179

| | Experiment 1 (v1) | Experiment 2 (v2) |
|---|---|---|
| Code only | 300 / 300 | 300 / 300 |
| After Double-check AI | 183 / 300 | 295 / 300 |
| Cases where the AI sent checks to a person | 147 | 40 |
| Found error → "only person review" | 108 | 5 |
| Clean case → unnecessary person review | 9 | 0 |
| Missed errors | 0 | 0 |

- Checks sent to a person: C11 22, C9 8, F1 6, F7 6, C12 3, F5 3 (exp 1: C12 101 ...).
- Reading: requiring evidence cut the AI's wrong flags from 117 to 5 cases. The AI still never beats code alone
  here, because code alone is already 300/300 on these cases.

## What this means for H1–H3 (so far)
- H1 (test success 100%): holds for code alone on the 300 cases (300/300); with the AI, 295/300 (exp 2).
  Limit: cases and checker come from the same reading of the rules.
- H2 (agent roles lower the failure rate): between prompts, yes (117 → 5 failures). Against no AI, no: on these
  300 cases the AI can only add failures, because code has none. A fair H2 test needs cases where code alone fails
  (for example stories 4/6, which code cannot check).
- H3 (fewer times a person must check): code alone sends 25 cases to a person (the ambiguous group).
  Exp 1 added work (147 cases with AI flags), exp 2 much less (40). Not yet fewer than code alone.

## Rule change after experiment 2 (code, 2026-10-27)
- Before: any AI flag turned the check into NEEDS_REVIEW, also when code had already found the error (MISMATCH).
  That caused all 5 failures of experiment 2: the AI pointed at the same error and the error was downgraded.
- Now: an AI flag on a MISMATCH check keeps it MISMATCH (recorded as `critic_on_mismatch`); only a flag on a PASS
  check goes to a person. Offline what-if on experiment 2's flags: 300 / 300, 21 cases sent to a person (was 40).
  Experiments 1 and 2 ran with the old rule.

## Experiment 3 — prompt agents-v3 (disagree only + rule text)
- Change: the AI sees each check's status, expected/actual value and the German rule text of its source section
  (VB 13.4 §3.12.x, from chunks/), and speaks only when it disagrees with the code; it must give field, seen,
  expected and a rule quote, otherwise code drops the flag. New rule above applies. Same cases, same sample.
- Run: `AGENTS-HARNESS-20261027-002646`, report `reports/AGENTS-HARNESS-20261027-002646.json`

| | Exp 1 (v1, old rule) | Exp 2 (v2, old rule) | Exp 2 flags + new rule (computed) | Exp 3 (v3, new rule) |
|---|---|---|---|---|
| Correct | 183 / 300 | 295 / 300 | 300 / 300 | 299 / 300 |
| Cases the AI sends to a person | 147 | 40 | 21 | 33 |
| Clean case wrongly sent to a person | 9 | 0 | 0 | 1 (DEC-139) |
| Missed errors | 0 | 0 | 0 | 0 |

- Exp 3 also commented on an error the code had already found in 27 cases (kept as errors, no effect).
- The one wrong case: DEC-139 "uncertified short AU seamless (included)" — the AI flagged F2/F3 (it disagrees
  that a short uncertified absence followed by a certified one is reported).
- Most frequent flags: C12 on "gap 6 months + 1 day" cases (11), C11 on "prior AU period missing" (9).
- Reading: rule text + "disagree only" did not beat the evidence prompt v2 under the new rule (33 vs 21 cases to a
  person). Each experiment ran once; part of the difference may be chance.

## Experiment 4 — prompt agents-v2 with the new rule (check of the computed value)
- Change vs experiment 2: only the rule (AI flag on a MISMATCH check keeps it MISMATCH). Prompt v2, same cases, same sample.
- Expected from the computation: 300 / 300, 21 cases to a person.
- Run: `AGENTS-HARNESS-20261027-005809` — see the table under experiments 5a / 5b.

## Experiments 5a / 5b — started in parallel with experiment 4 (2026-10-27 ~01:01)
- 5a (repeat): prompt v2 + new rule, two more runs, labels `v2rep2`, `v2rep3`. With experiment 4 this gives 3 runs of
  the same setup, to see how much the result moves between runs.
- 5b (remove an agent): prompt v2 + new rule without the Explainer AI (`TEAM10_NO_EXPLAINER=1`), label `v2noexpl`.
  Score should not change (the Explainer does not affect the verdict); measures time and calls saved.

| Run | Setup | Correct | Cases to a person | Clean case wrongly sent | AI comment on a found error | Explanations | Time* |
|---|---|---|---|---|---|---|---|
| Exp 4 `005809` | v2 + new rule | 299 / 300 | 16 | 1 | 23 | 179 | 25 min |
| 5a `v2rep2` | same | 300 / 300 | 14 | 0 | 29 | 179 | 24 min |
| 5a `v2rep3` | same | 299 / 300 | 18 | 1 | 22 | 179 | 24 min |
| 5b `v2noexpl` | same, no Explainer AI | 300 / 300 | 18 | 0 | 26 | 0 | 16 min |

*Time = report file time minus start time; all four ran at the same time, so times are comparable with each other only.

- Same setup three times (exp 4, v2rep2, v2rep3): correct 299 / 300 / 299, cases to a person 16 / 14 / 18 (average 16).
  The computed value (300 / 300, 21) is close; run-to-run spread is about ±2 cases.
- Without the Explainer AI: same score range, about a third less time (16 vs 24–25 min), 179 fewer AI calls,
  but no plain-language summary in the report.
- Missed errors in every run: 0.

## Stage 2 → stage 3 connected (2026-10-27 ~01:29)
- New: `python orchestrator/graph.py verdict --auto --from-design reports/AGENTS-design-<id>.json` judges the test
  cases the Test writer AI wrote in stage 2, with the expected values code computed there. Payroll output is
  simulated (no payroll software available): per allowed case the correct 41 + one copy with AU-AB-AG one day late;
  per not-allowed case a 41 sent anyway.
- Run `AGENTS-verdict-20261027-012918` (prompt v2, real Claude): 30 cases from the 20 AI tests (cases without prior
  periods skipped), correct 30 / 30, AI sent 0 to a person.
- Not measured: whether the Explainer's text is right. Example: T-06-bad says the 182-day gap fails the 6-month limit,
  while the check result shows only F5 failing — needs a human look.
- Existing experiment paths unchanged: code harness 300 / 300 and agent harness (mock) behave as before; finished
  experiments 1–5 were not re-run.

## Gaps closed: rules → checks, signature dispute → back, stage 0 source finder (2026-10-27 ~01:40–01:56)
- Rules → checks: the Rule writer links each criterion to one of the 12 code checks (`agents.CHECKS`) or null;
  `citation_check` removes unknown links. In stage 3 only linked checks run; criteria without a check become
  NOT EVALUATED ("a person checks") in the report.
- Dispute → back: `python orchestrator/graph.py full` = design → verdict on the stage-2 cases → one signature on the
  whole report (`sign / dispute g3 <note> / dispute g1 <note>`), at most 2 disputes. Mock-tested both routes.
- Real run `AGENTS-full-20261027-014300` (prompt v2, gates auto): 15 criteria, 12 linked to a check, 3 without
  (R-12 plausibility check by the employer, R-13 all statutory insured, R-15 interim reply code 4) → person checks.
  29 cases from 20 AI tests (1 bad scenario BLOCKED by code), correct 29 / 29, AI sent 0 to a person.
- Stage 0 `python orchestrator/find_sources.py` (run `SOURCES-20261027-015353`, Haiku): code keyword search over all
  1,219 chunks + sub-sections of hits → 66 candidates; the AI picked 39.
  Answer list A (VB 3.12–3.12.8, 9): 9 / 9 found. Answer list B (A + VB 3.12.9–14 + Beispiel 13–13.5 + GG 2.1.2, 22):
  22 / 22 found. 17 picks outside B, 12 of them Beispiel 16.x (insurer answers to the request) — not checked whether
  B should include them. Answer lists were chosen by us, not by ITSG.
- `graph.py design|full --sources reports/SOURCES-*.json` lets stage 1 read the picked sections (mock-tested only;
  default stays VB 3.12–3.12.8).

## Experiment a — three new sets of 200 cases (2026-10-27 02:04–02:22)
- New sets from `python harness/generate_expa.py` (seed 2610, same ground-truth rules): `data/expa_sick.json`
  (golden 5 + decision 100 + output 80 + ambiguous 15), `data/expa_story1.json` (work accident / rehab, 5 × story 1),
  `data/expa_story3.json` (short uncertified days, 5 × story 3). Old data files unchanged.
- Code only: `python harness/run_harness.py --cases expa_<set>.json` → 200 / 200 on all three
  (`harness-HARNESS-20261027-020413`, `-020421`, `-020431`).
- With AI helpers, setup as experiment 4 (prompt v2, new rule, Explainer on):
  `TEAM10_RUN_LABEL=expa-<set> python orchestrator/harness_agents.py --cases expa_<set>.json`, run `AGENTS-HARNESS-20261027-020511-expa-*`.

| Set | Correct (code → with AI) | Double-check runs | Cases the AI sent to a person | of these, clean cases | AI comment on a found error | Time* | Langfuse export failures |
|---|---|---|---|---|---|---|---|
| Sick leave | 200 → 200 | 125 | 12 | 0 | 13 | 17 min | 0 |
| Story 1 | 200 → 200 | 113 | 13 | 0 | 4 | 15 min | 0 |
| Story 3 | 200 → 200 | 71 | 3 | 0 | 12 | 10 min | 0 |

*Report file time minus start time; the three ran at the same time.
- Every case the AI sent to a person already had an error found by code (the AI flagged another, PASS check in the
  same case), so no result changed and no clean case got extra work. Missed errors: 0.
- Sick-leave outcomes: 87 clean, 92 detected, 6 BLOCKED (malformed output), 15 escalated (ambiguous rule).
- Limit: cases and checker come from the same reading of the rules (same as the 300).


## Stories 4 and 6 through the message-flow checker (T10-008, 2026-10-27)
- Command: `python harness/run_harness.py --stories` (200 story cases, code only, no AI, no Langfuse), before and after
  `harness/story_flow_adapter.py` + `run_harness.score_story`. Reports `reports/harness-HARNESS-20261027-072602.json` (before) and
  `-072656` (after).
- Checker = Fares' C1-C8 (`checker/checks.py`). Expected AZVU and final EFZ end come from each story-6 case's own `scenario`.

| Story | Before | After |
|---|---|---|
| 1 (40 cases) | 40 evaluated, 40 correct | unchanged |
| 3 (40 cases) | 40 evaluated, 40 correct | unchanged |
| 4 insurer reply 61 (60 cases) | 60 NOT EVALUATED | 60 NOT EVALUATED |
| 6 cancellation 88 (60 cases) | 60 NOT EVALUATED | 60 evaluated: 20 clean cases, 0 false alarms; 32 of 40 defects detected by the right check; 8 MISSED |
| All 200 | 80 evaluated, 80 correct, 120 not evaluated | 140 evaluated, 132 correct, 60 not evaluated, 0 false alarms, 62 of 70 defects detected |

- Story 4 stays NOT EVALUATED on purpose: a story-4 case holds only the employer 41 and the insurer 61 as field values, with no AZVU,
  message IDs or 01/88/62 messages. C1-C8 check the message flow, so none of the eight checks can run. The 61 rules (VB 13.4 3.12.x)
  have no checker yet.
- The 8 missed story-6 defects are "61 does not refer to the 41" (4) and "62 refers to the cancelled 01" (4): C1-C8 have no REF-ID check.
- Unchanged: `python harness/run_harness.py` 300/300 correct, 0 false alarms; `python checker/attacks.py` 14/14, baseline no false alarm.
- Limit: cases and checker come from the same reading of the rules; the right-check mapping (`RIGHT_FLOW`) is ours.
