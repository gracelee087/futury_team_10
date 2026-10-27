# Provenance — adopted teammate implementations (T10-031)

**Origin:** Team 10 teammates' work merged on `main`, provided as snapshot
`futury_team_10-main.zip` on 2026-10-26. Audited and adopted by the backend
session (ZCode / GLM-5.3Flash) under task T10-031; the audit evidence is in
`.leapfrog/log.md` and the T10-031 board row.

## Adopted (this directory and siblings)

| Path | What | Audit evidence |
|---|---|---|
| `src/chunking.py` | Deterministic header-based PDF→Markdown segmenter for all six corpus documents (TOC-whitelisted headings, hidden-number handling for VB, table-cell reconstruction, chapter mini-TOC removal) | Re-run against this repo's corpus: **0 words lost** across all six documents (≈237k words), 83/83 VB cross-references validate, zero replacement chars, zero duplicate sections; regenerated chunks are **byte-identical** to the committed ones |
| `src/pdf_to_md.py` | Whole-document Markdown view per PDF (uses chunking.py) | Same reconciliation |
| `chunks/` | 1,219 section chunks + `chunks.jsonl` (canonical JSONL store) + `REPORT.json` (reconciliation report) + `README.md` (chunk index); YAML frontmatter carries doc/version/section/pages/Abgabegrund/Datenbaustein locators | `REPORT.json` regenerated from our corpus — committed values reproduce |
| `run_review.py` | Deterministic TEEL0 wire-format parser + DBVO findings (field positions cited to VB §3.1.5/§3.1.18/§3.12.x; official criterion UUIDs; NEEDS_REVIEW for genuine rule-text ambiguity; malformed → BLOCKED, never PASS) | Included in the 300-case harness run |
| `harness/generate_cases.py` | 300 seeded synthetic DBVO test cases; ground truth derived **independently** of the reviewer (anti-circular); golden cases reproduce Beispiele 13.1–13.5 | `python3 harness/generate_cases.py` regenerates `data/testcases.json` + `testCase.md` |
| `harness/run_harness.py` | Scores the reviewer over all cases (detected / false-alarm / NEEDS_REVIEW escalation) | 300/300 correct, 0 false alarms, 170/170 defects detected (board/log) |
| `harness/generate_story_cases.py`, `data/story_cases.json`, `testCase-stories.md` | **Sync 2026-10-26 late** from updated main (commit 08f0392): 200 additional story cases (1/3/4/6) — accident/rehab neutrality, uncertified short days, insurer 61-reply field rules (VB §3.12.2–3.12.14), cancel-and-correct flow 41→61→01→61→88→01→62 (GG EEL §2.5) | Regeneration from seed 4136 is **byte-identical** to their committed data. NOTE: no runner for the story cases exists on their main yet (`run_harness.py` reads `testcases.json` only) — adopted as data + generator, scoring the 61-reply/flow defects is follow-up work |
| `figures/system-overview.png`, `figures/multi-agent.png` | Pitch figures (16:9, commit 942a05a) | Static images, adopted as-is |
| `seal/` (branch `member2-seal`, commit c9cfc94, Fares/Member 2) | **Adopted T10-034**: the ITSG receipt office — run IDs issued before review, HMAC-SHA256 receipts over report hashes, append-only hash-chained ledger (per-line canonical form + sequence + prev-hash + MAC), replay protection, never-submitted runs visible; stdlib-only HTTP service + client + verifier + demo | Their pytest suite 50/50 in isolated checkout; demo walks all attack paths; audit 2026-10-26 23:25 (log). Gaps fixed on adoption: (A) stdlib-unittest port of the suite at `tests/test_seal.py` (our verification contract; pytest original kept in seal/), (B) SÜSIE wiring: `itsg/demo.py --seal` gives the report artifact a receipt (external office via `--seal-url` + env tokens, or a throwaway in-process office in demo mode). Documented honest limits NOT "fixed" (owner decisions): no rate limiting, HMAC-only, no TLS |
| `data/testcases.json`, `data/case_correct.json`, `testCase.md` | Harness ground truth + the official-constellation reference case | gitignored-`data/` exceptions added in `.gitignore` |

## Deliberately NOT adopted

- **Snapshot `API.py`** — contains a plaintext gateway token. This repo keeps
  `api.py` (team member's file) and routes the token through the encrypted
  store (`itsg/secrets.py`); the key is disposable and must be deleted
  server-side by the owner.
- **Neo4j merge / Langfuse tracing as runtime dependencies** — the graph
  modules (`Graph_Schema.py`, `Normalizer.py`, `Regular_expression_check.py`,
  `Merge_graph_neo.py`) and Langfuse stay with the snapshot's own stack and
  are out of scope for the deterministic SÜSIE core. Langfuse is external
  tracing (opt-in via env keys, off by default); enabling it for real review
  content needs an explicit governance decision.
- **`ui/`** (member 4's standalone UI, commit 582278a) — separate artifact
  from the SÜSIE frontend (`frontend/`, T10-030); left on their main, not
  integrated. Reconciliation between the two UIs is an integration-lead
  decision.

## Conditions recorded at adoption

1. G0/registry flow stays ours: chunks are *derived* artifacts; source PDFs
   enter retrieval only after human G0 acceptance (pipeline/registry).
2. Their code is adopted verbatim (docstring provenance notes excepted); any
   future edit goes through the normal one-writer/review flow.
3. `chunks/`, `chunks.jsonl`, `REPORT.json` are reproducible derived artifacts
   (`python3 src/chunking.py` with `DATA_DIR` pointing at the corpus).
