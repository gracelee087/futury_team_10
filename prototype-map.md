# Prototype Implementation Map — SÜSIE

**SÜSIE — Systemüberprüfung sozialversicherungsrechtlicher IT-Ergebnisse** (app name decided
by the human owner, 2026-10-26).

**Status:** skeleton created 2026-10-26 under work order T10-015; demo slice implemented
2026-10-26 under T10-018 (approach A, per
`docs/superpowers/specs/2026-10-26-prototype-build-design.md`). This file is the single map
from documented design to code. It does not replace `architecture.md` (system design) or
`ingestion-pipeline.md` (ingestion design) — it points into them.

## Package layout

```text
pipeline/                  # deterministic ingestion (agent-governance §2: coding-agent domain)
  ids.py                   # IMPLEMENTED: SRC-/SRCV-/SEG- ID scheme, SHA-256 checksums
  audit.py                 # IMPLEMENTED: append-only AuditRecord JSONL (governance §3 pattern)
  registry/                # Stage A — T10-004 (ingestion-pipeline.md §5)
    manifest.py            # IMPLEMENTED: architecture §4 fields, G0 status vocabulary, strict JSON load
    g0.py                  # IMPLEMENTED: human-only accept/reject/supersede (fail closed)
    importer.py            # IMPLEMENTED (T10-031): inbox → sources, checksum dedupe
                           #   (GG_EEL twin case), G0-candidate default, audit record
    fetch.py               # PARTIAL: URL policy enforced (http/https, no private/loopback/reserved);
                           #   fetch_to_inbox STUB → T10-004 (§9 #5 default: no auto-crawl)
    cli.py                 # STUB entry point

src/                       # ADOPTED teammate implementations (T10-031, see src/PROVENANCE.md)
  chunking.py              # deterministic header-based PDF→Markdown segmenter, all 6 docs;
                           #   built-in reconciliation (chunks/REPORT.json: 0 words lost)
  pdf_to_md.py             # whole-document Markdown view per PDF

harness/                   # ADOPTED teammate harness (T10-031)
  generate_cases.py        # 300 seeded synthetic DBVO cases, independent ground truth
  generate_story_cases.py  # 200 story cases (1/3/4/6): 61-reply field rules, cancel/correct
                           #   flow — sync from updated main; no runner on their main yet
  run_harness.py           # scores the reviewer; run: python3 harness/run_harness.py
seal/                      # ADOPTED (T10-034, branch member2-seal): ITSG receipt office —
                           #   run IDs, HMAC receipts over report hashes, hash-chained
                           #   ledger; itsg/demo --seal gives the report artifact a receipt
                           #   (pytest original suite kept; stdlib port in tests/test_seal.py)
run_review.py              # ADOPTED: deterministic TEEL0 parser + DBVO findings (§3.12)
chunks/                    # ADOPTED derived corpus: 1,219 chunks + chunks.jsonl + REPORT.json
figures/                   # ADOPTED pitch figures (system-overview, multi-agent)
data/testcases.json        # harness ground truth (tracked despite data/* ignore)
data/story_cases.json      # story-case ground truth (tracked; no runner yet on their main)
data/case_correct.json     # official-constellation reference case
  segmenter/               # Stage B — T10-005 (ingestion-pipeline.md §6)
    models.py              # IMPLEMENTED: Segment + ExtractionWarning, JSONL dump/load
    pdf_extractor.py       # IMPLEMENTED (T10-031): adapter over the ADOPTED teammate
                           #   core src/chunking.py (deterministic header-based
                           #   segmentation, TOC whitelist, hidden-number handling);
                           #   maps to typed Segments + disclosed reconstruction warnings;
                           #   reconciliation evidence in chunks/REPORT.json (0 words lost)
    docx_extractor.py      # STUB → T10-005 follow-up (adopted core covers PDFs only)
    chunker.py             # IMPLEMENTED (T10-031): dispatch; pdf → adopted core, docx → stub
    cli.py                 # STUB entry point
  index/                   # Stage C — T10-006 (ingestion-pipeline.md §7)
    fts.py                 # IMPLEMENTED: FTS5 schema + open_db + insert_segment +
                           #   build_index (T10-031: accepted-versions-only, audit record)
    query.py               # IMPLEMENTED: accepted-versions-only search, fails closed
    verify.py              # IMPLEMENTED (T10-031): the six §8 hooks (word-level purity +
                           #   adopted reconciliation, heading/TOC reconciliation via
                           #   chunks/REPORT.json, gate filtering in a sandbox — agents
                           #   never set accepted on real data, dedupe, rebuild determinism)
    cli.py                 # STUB entry point

itsg/                      # typed system-agent domain — SÜSIE (governance §2: typed interfaces)
  states.py                # IMPLEMENTED: §9 state machine, gates cannot be skipped
  gates.py                 # IMPLEMENTED: G0–G6 human decision records (reviewer required)
  records.py               # IMPLEMENTED: plan.md minimal data contract as dataclasses
  store.py                 # IMPLEMENTED: JSON store + append-only events.jsonl
  comparator.py            # IMPLEMENTED: PASS / MISMATCH / NOT_EVALUATED, fail closed
  renderer.py              # IMPLEMENTED (T10-018): synthetic-template rendering,
                           #   compliance_claim always False; official claim w/o approval raises
  conformance.py           # IMPLEMENTED (T10-018): required_fields (incl. per-row),
                           #   labels_and_order, output_type, value_mapping; blocked never passes
  vorerkrankung.py         # IMPLEMENTED (T10-018): DBVO trigger rule (VB DTA EEL §3.12),
                           #   versioned, official constellation reproduced (25+10=35 days)
  candidates.py            # IMPLEMENTED (T10-018): §3 AgentRun envelope, cite-or-abstain,
                           #   review_required forced, author≠reviewer, challenger recommendation-only
  llm.py                   # IMPLEMENTED (T10-018): gateway client — vllm/GLM-Flash:Latest
                           #   (extractor, challenger) + vllm/Kolibri-1 (designer); §8 prompt
                           #   contracts; SSRF-hardened endpoint policy; token via itsg.secrets
  webserver.py             # IMPLEMENTED (T10-031): stdlib HTTP bridge — serves frontend/ +
                           #   GET /api/state | /api/health, POST /api/run (offline/live demo
                           #   re-run); read-only over the store; no credentials to the browser
  secrets.py               # IMPLEMENTED (T10-018): Fernet+PBKDF2 encrypted store under
                           #   data/secrets/ (gitignored); token never in source/fixtures/logs
  demo.py                  # IMPLEMENTED (T10-018): SÜSIE end-to-end demo slice;
                           #   python3 -m itsg.demo --fresh [--live]

fixtures/                  # cited demo fixtures (T10-018; fabricated data only)
  synthetic_template.json  # labeled SYNTHETIC template — never claim compliance with it
  synthetic_template_profile.json  # profile: field_order, labels, permitted statuses
  bp_3_1_normal.json       # BP §3.1 pp. 9–11 — official expected DSLW/DBAL/DBAE (normal)
  bp_3_2_1_4_boundary.json # BP §3.2.1.4 p. 12 — Vollständige Fehlzeit im EAZ (boundary)
  bp_invalid_missing_input.json    # incomplete Sachverhalt → NOT_EVALUATED by design
  vorerkrankung_konstellation.json # official test constellation + VB §3.12 citation

tests/                     # stdlib unittest suite: python3 -m unittest discover -s tests
```

## Verification commands

```bash
python3 -m compileall -q pipeline itsg tests
python3 -m unittest discover -s tests -v
```

Both must pass with the standard library only. `pymupdf` and `python-docx`
(see `requirements.txt`) are needed only when T10-005 is implemented — the
extractors import them lazily.

## Provisional decisions in force (§9 of ingestion-pipeline.md, solo directive)

| # | Decision | Provisional default |
|---|---|---|
| 1 | MVP index stack | SQLite FTS5 only; vectors deferred |
| 2 | Chunk storage | JSONL canonical (`segments.jsonl` per version) |
| 3 | Tables for v1 | kept inside their section chunk |
| 4 | Demo corpus scope | full corpus indexed; Anl3 (406 pp.) is the stress case |
| 5 | Fetch policy | no auto-crawl; fetch helper stub carries the URL policy |
| 6 | Embedding model | deferred with vectors |
| 7 | G0 owner | provisionally the solo human owner, until named by the team |

These are recorded in `.leapfrog/log.md` and revisitable at the T10-003
review; code treats them as defaults, not as accepted design.

## Build order (fastest path to the plan.md demo)

1. **T10-004** `registry.importer.register_inbox` — pure stdlib; unlocks dedupe (hook §8.5) and G0 flows.
2. **T10-005** segmenter — needs `pip install pymupdf python-docx`; reconcile heading counts against the §2 baseline.
3. **T10-006** `index.fts.build_index` + `verify.py` hooks — wire stages together; gate filtering (§8.4) falls out of `query.search`.
4. **Demo slice** (plan.md vertical path): fixture source → `records.py`/`store.py` → `comparator.compare` → `renderer.render` + `conformance.check_conformance` → report with `compliance_claim=False` unless a verified official template exists.

## Fail-closed behaviors already enforced (tested)

- Comparator never returns PASS with missing expected value, basis, execution output, or approval.
- G0 acceptance requires a named human reviewer and rationale; agents cannot set `accepted`.
- Retrieval serves only G0-accepted versions; an empty accepted set returns nothing.
- Fetch URLs must be http/https to public hosts (no loopback/private/link-local/reserved).
- Manifests and records reject unknown fields at the JSON boundary.
- Conformance defaults to `blocked`, never to compliant.

## Formal report document layer (T10-036, 2026-10-26)

- `itsg/report_pdf.py` — renders the deterministic report artifact as a formal German-style
  PDF (PyMuPDF, already a requirements.txt dependency — no new dependency): header with
  Prüfobjekt (client) name + honest logo placeholder, every-page footer "Maschinell erzeugt
  von SÜSIE" + SÜSIE logo + timestamp + SHA-256 of the canonical artifact, formal
  Helvetica/Arial layout (DIN-5008-inspired; NO DIN/official-form claim — see
  `.leapfrog/wiki/findings/2026-10-26-report-template-legal-basis.md`), sections:
  Kopfdaten / Grundlagen und Grenzen / Ergebnisse (deterministic table, MISMATCH highlighted) /
  Zusammenfassung / Konformitätshinweis (`compliance_claim` stays False) / Integrität.
- Optional GLM summary: `draft_summary_live` (role `report_explainer`, recommendation-only,
  gateway model `vllm/GLM-Flash:Latest`) drafts a plain-language summary from the
  deterministic results only, rendered as "KI-Entwurf – ungeprüft"; offline/gateway failure →
  PDF still generated with an honest note + recorded error `agent_run` (fail closed).
- Surfaces: CLI `python3 -m itsg.report_pdf --store data/demo [--live]`;
  bridge `GET|POST /api/report/pdf` (`itsg/webserver.py`, additive); frontend report-view
  button "Formalreport als PDF herunterladen" (offline → honest toast).
- Determinism: pinned `--generated-at` ⇒ byte-identical PDF (`no_new_id`); the printed hash
  covers the artifact content, not the timestamp.
