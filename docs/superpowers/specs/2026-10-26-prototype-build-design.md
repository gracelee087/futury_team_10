# Prototype Build Design — 24h Demo Slice (Approach A, then B)

**Date:** 2026-10-26
**Status:** Brainstorm outcome (superpowers brainstorming skill, session on branch `amourification/pdf-chunking`). Human owner approved approach **A-then-B** in chat on 2026-10-26. Implementation task: **T10-018** (READY on `.leapfrog/board.md`). Nothing committed/pushed (no authorization).
**Related:** `architecture.md` (system design), `plan.md` (24h team plan, acceptance criteria, scope cuts), `ingestion-pipeline.md` §2 (corpus evidence incl. content deep-dive), `prototype-map.md` (design→code map), `agent-governance.md` §8 (prompt contracts).

## Intent and why

The ITSG challenge asks for an AI review assistant that "supports and potentially even replaces" the system-review testing process for *Entgeltersatzleistungen* (client deck pp. 9–12; prototype explicitly optional — the concept is the core deliverable). Team 10's demo must show the six client objectives as one working, traceable loop — grounded in **official expected values** found in the corpus, not invented numbers. This design records what this brainstorm decided; the full system design stays in `architecture.md`.

## Goals

- One end-to-end path runs live tonight: cited source record → requirement candidate → approved criterion → test cases (normal/boundary/invalid) → expected vs. observed comparison → mandated-form rendering (synthetic template) → conformance check → evidence-backed report.
- Traceability chain visible end to end: finding → report → conformance result → test case → criterion → requirement → source version + exact locator (Beispielpapier section, V13.3, effective 01.01.2027).
- AI visible as candidate drafter + independent challenger (governance §8 contracts); deterministic core decides; fail-closed everywhere.
- Staged-autonomy narrative: AI expert-agents draft and check, humans at milestone gates and execution step — "supports now, replaces later," matching client language.

## Non-goals (tonight)

- Benefit-**amount** calculator: the Rundschreiben carry the rules (70 %, Kalendertagsatz, Höchstbetrag) but the corpus has no official numeric expected values for them; Beispielpapier expected records are the payroll **transmit side** only. The calculator stays a concept in the pitch.
- Live translation QA and live mathematical QA layers (architecture narrative, not code).
- Vector search, graph DB, auto-crawl, multi-document ingestion at scale.
- Any legal/template compliance claim (`compliance_claim=False`; synthetic template conspicuously labeled).

## Anti-goals (failure even if everything works)

- Any `PASS` without a complete evidence chain; missing expected value/source/execution becomes `NOT_EVALUATED`, never a pass.
- Vendor documentation presented as execution evidence.
- Real personal/payroll data anywhere in fixtures, logs, or prompts.

## Constraints

- Solo developer on branch `amourification/pdf-chunking`; stdlib-first code; no commit/push without explicit authorization.
- DELIVERY.md cadence: board/log updates at transitions, progress note every 45 min, checkpoint pair at session end (cp-007 next).
- Event clock: 24h build window started 19:00 on 2026-10-26; freeze features per plan.md.

## Approaches considered

| Approach | What | Tradeoff |
|---|---|---|
| **A — Fixture-first vertical slice** | Hand-curate 2–3 Beispielpapier examples + the Vorerkrankung trigger rule as cited JSON fixtures; wire the existing `itsg/` chain (records → criteria → cases → comparator → renderer/conformance); AI roles as candidate-only agents. | Zero parsing risk; demo-safe early; "AI ingests law" stays design-only tonight. |
| B — A + evidence backbone (T10-004/005/006) | Add importer → segmenter (one document) → FTS5 index; live retrieval panel with German passage beside version metadata. | Real ingestion credibility; segmenter debugging can eat hours (table-heavy Beispielpapier; split-heading quirks). |
| C — Full six-layer showcase | Translation QA, math QA, everything live. | Overreach for one solo dev in 24h; contradicts plan.md schedule gates. Rejected. |

**Chosen: A first, then B if clock allows.** Demo-safe early, matches plan.md scope-cut order (vector/graph already cut; auto-PDF parsing is cut #2), and B upgrades credibility without betting the demo.

## Grounding evidence (why this is legitimate)

Recorded in `ingestion-pipeline.md` §2 "Content deep-dive (2026-10-26, evening)": the official *Beispielpapier DTA EEL V13.3* supplies ~62 worked examples with field-level expected DTA records, including explicit negative results and an edge-case ladder ("Abwandlungen"); `test case/` + `Rules details/` DOCX pair is an official multi-step test constellation with concrete dates; `TEEL0-Test1-DBVO` is a wire-format parser fixture matching it. Boundary: expected records describe what the payroll program must transmit; no Krankenkasse-side benefit-amount claims.

## Decided build order (A)

1. **Fixtures (`fixtures/`):** JSON per example with a citation object (`source`, section, page, version V13.3, effective date): BP §3.1 "Gehaltsempfänger ohne Besonderheiten" (normal), one Abwandlung (boundary — e.g. 3.2.1.4 "Vollständige Fehlzeit im EAZ" or a Kurzarbeit variant), one invalid/missing-input case (expected `NOT_EVALUATED`). Shapes align with `itsg/records.py`.
2. **Vorerkrankung deterministic function:** 30-days/12-months trigger rule (≥ 1 bescheinigte Vorerkrankung within 6 months; cumulative ≥ 30 days within 12 months), versioned module, unit tests, citation to Verfahrensbeschreibung DTA EEL Punkt 3.12.
3. **Wire `itsg/` chain** on the fixtures: store → criteria → cases → `comparator.compare` (exists, fail-closed) → `renderer.render` + `conformance.check_conformance` on the labeled synthetic template, `compliance_claim=False`.
4. **AI candidate roles** (governance §8 prompt contracts): requirement extractor, test-case designer, independent test challenger. Outputs = candidates with citations + `review_required=true`; a human gate record decides; author ≠ reviewer.
5. **Rehearse** plan.md's ~3-minute demo script; one pass, one deliberate mismatch, one blocked/not-evaluated.
6. **B upgrade (stretch, in order):** T10-004 importer (stdlib) → T10-005 segmenter scoped to **one** document (GG_EEL or Verfahrensbeschreibung first, not Anl3) reconciled against the §2 heading baseline → T10-006 FTS5 build + verify hooks.

## Verification

- `python3 -m compileall -q pipeline itsg tests` and `python3 -m unittest discover -s tests` must pass.
- plan.md checklist subset: traceability links; missing evidence → `NOT EVALUATED`; deliberate mismatch surfaces both values; boundary/invalid handled; review separation (candidate ≠ approval); conformance failure blocks compliance; fabricated data only.
- Demo runs from a clean start.

## Left to the builder

- Exact fixture JSON field shapes (align with `itsg/records.py` dataclasses; unknown metadata stays empty, never guessed).
- Interface choice for the demo (CLI sufficient; minimal web view optional — builder's call, state it).
- Concrete prompt texts for the three AI roles (skeleton in governance §8 template).
- Which Abwandlung becomes the boundary fixture (any one qualifies; record the citation).
- Stretch: parser demo on `TEEL0-Test1-DBVO` wire record (only after the slice is stable).
