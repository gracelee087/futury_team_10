# Error & change log — Team 10

Every error and every problem found while building and testing, with what was changed.
Add a row whenever something fails or an experiment shows a problem. **Approved by** is filled in by a person
(name + date); Claude never fills it. Status: `open` · `fixed – awaiting approval` · `approved` · `won't fix`.

Where to look for details: run reports `reports/*.json` and `reports/*.log`, experiment write-ups `experiments.md`,
per-step traces in Langfuse (session = run id).

| # | When | Found in (run / experiment) | Kind | What went wrong | What was changed | Status | Approved by |
|---|---|---|---|---|---|---|---|
| E-01 | 2026-10-26 | mock test `TEAM10_MOCK=broken` | code | Endless loop (GraphRecursionError): a BLOCKED step was auto-approved at the rule gate in harness mode | Harness gates stop on BLOCKED; rule/test gates count BLOCKED as a reject (`orchestrator/graph.py` `gate`, `g1`, `g3`) | fixed – awaiting approval | |
| E-02 | 2026-10-26 | first real design run | AI call | Rule writer answer cut off (stop_reason max_tokens at 8,000) → run BLOCKED (fail-closed worked) | Streaming + max_tokens 32,000 for writers, 8,000 for checkers (`orchestrator/llm.py`) | fixed – awaiting approval | |
| E-03 | 2026-10-26 | experiment 1 `AGENTS-HARNESS-20261026-223252` | Langfuse | Export failures (timeouts / DNS errors to cloud.langfuse.com); 4 cases missing in Langfuse | None in code; local report is complete; noted in `experiments.md` | won't fix (network) | |
| E-04 | 2026-10-26 | experiment 1 | prompt | Double-check AI (prompt v1) too cautious: 117 wrong results, 147 cases sent to a person | Prompt v2: a flag needs field / seen / expected evidence, code drops flags without it (`orchestrator/agents.py`) | fixed – awaiting approval | |
| E-05 | 2026-10-27 | experiment 2 `AGENTS-HARNESS-20261026-235609` | code rule | All 5 failures: the AI pointed at an error code had already found, and the error was downgraded to "needs review" | AI flag on a MISMATCH keeps it MISMATCH (`critic_on_mismatch`); only flags on PASS go to a person (`graph.py` `f_critic`) | fixed – awaiting approval | |
| E-06 | 2026-10-27 | experiment 3 `AGENTS-HARNESS-20261027-002646` | prompt | Prompt v3 (rule text, disagree only) sent more cases to a person (33) than v2 (≈16–21); 1 clean case wrong (DEC-139) | Kept v2 as default; v3 stays selectable (`TEAM10_PROMPT=v3`) | won't fix | |
| E-07 | 2026-10-27 | experiments 4 / 5a | AI variance | Same setup three runs: 299 / 300 / 299 correct, 16 / 14 / 18 to a person (run-to-run spread ≈ ±2) | None; recorded | open | |
| E-08 | 2026-10-27 | workflow review | design gap | Stage 3 did not use stage 2's tests | `graph.py verdict --from-design` | fixed – awaiting approval | |
| E-09 | 2026-10-27 | workflow review | design gap | Stage 3 ran a fixed list of 12 checks; approved criteria from stage 1 were not used | Criteria link to a code check (`agents.CHECKS`); stage 3 runs only linked checks, unlinked criteria → "person checks" | fixed – awaiting approval | |
| E-10 | 2026-10-27 | workflow review | design gap | A dispute at the report signature could not go back to tests or rules | `graph.py full`: report signature, `dispute g3|g1`, max 2 | fixed – awaiting approval | |
| E-11 | 2026-10-27 | design (relevance) | design gap | Relevant sections were picked by hand-coded section numbers, not found by AI | Stage 0 `orchestrator/find_sources.py` (22 / 22 on answer list B) | fixed – awaiting approval | |
| E-12 | 2026-10-27 | stage 0 mock run | code | Keyword search missed field sections that never use the topic word (e.g. VB 3.12.2) → shortlist 9 → 5 of 9 | Shortlist also takes sub-sections of matching sections (`find_sources.shortlist`) | fixed – awaiting approval | |
| E-13 | 2026-10-27 | `AGENTS-full-20261027-014300` | AI output | Test writer wrote 1 impossible scenario (T-20: current AU ends before it starts) | None needed: code BLOCKED it before expected results | won't fix | |
| E-14 | 2026-10-27 | `AGENTS-full-20261027-014300` | AI review note | Test checker left 11 open notes at test approval, incl. doubts on T-12 / T-13 day counts; not resolved (gates were auto) | None yet — a person should review the notes | open | |
| E-15 | 2026-10-27 | Langfuse check of the full run | Langfuse | Stage 0 calls had no session; stage 3 code checks not logged one by one; 1 rule-writer and 1 rule-checker call arrived without session (cause not found) | Session + recall scores for stage 0; one span per check in the full loop | fixed – awaiting approval (arrival confirmed 02:30: `SOURCES-20261027-021434` own session, `AGENTS-verdict-20261027-021514` 29 × each check) | |
| E-16 | 2026-10-27 | Explainer AI, `AGENTS-verdict-20261027-012918` | AI accuracy | T-06-bad summary talks about a 182-day gap failing although only F5 failed; Explainer accuracy is not measured | None yet | open | |
| E-17 | ongoing | ITSG brief, objective 5 | scope | No payroll software: output files are simulated | None possible here | open | |
| E-18 | 2026-10-27 | Langfuse check after the fix | monitoring | New records looked missing: Langfuse showed them only about 10–15 min later, and the v2 observations query with `fromStartTime` returned nothing | None in code; check Langfuse again after ~15 min before saying something is missing | won't fix | |
| E-19 | 2026-10-27 | `AGENTS-full-20261027-014300` (found 02:35) | code rule | Check F1 (Abgabegrund = 41) ran in 0 of 29 cases: no criterion linked F1, and since gap A only linked checks run; a wrong message type would be missed | F1, F4, F6 (message format) always run (`graph.py` `ALWAYS`). Re-judged 29 cases `AGENTS-verdict-20261027-024151`: F1 in 29/29, still 29/29 correct; a 42 instead of 41 is now detected | fixed – awaiting approval | |
