# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user: the ITSG review side (hackathon client; demo audience is 3 ITSG
members — legal experts plus systems people). They review whether a payroll
vendor's transmitted social-insurance IT results (DTA EEL) match the official
expectations derived from the law. They create test cases from the law once or
twice a year (after legislative/spec changes), then validate the software
output against them. German is the working language; formal public-sector
register.

## Product Purpose

SÜSIE is a review assistant ("Prüfassistent") that turns a legal text into
versioned test criteria, checks a payroll system's transmitted records against
the official expected values field by field, explains every finding in plain
language, and produces a formal review report. Success for the demo: the five
owner concerns each have a visible button/path — (1) test-case creation from
the law, (2) validation against the external software output, (3) reliable chat
access, (4) report generation, (5) full traceability from report to source.

## Positioning

Governed AI review: separate AI roles (extractor GLM-Flash, designer Kolibri-1,
independent challenger) propose, humans decide at recorded gates (G0–G6,
four-eyes: author ≠ reviewer), the comparison itself is deterministic, and the
report is tamper-evident (SHA-256 + receipt-office seal). No neighboring
hackathon team can show human-gated AI roles plus a manipulation-proof report
exchange.

## Operating Context

Runs fully local (bridge on 127.0.0.1, store on disk). The only outbound calls
are the LLM gateway (text context only, never personal data) and the SHA-256
fingerprint to the in-process receipt office during the seal demo. Data is
synthetic; the template is labeled synthetic; the conformance claim stays NO
(§ 95b SGB IV prescribes no template). Live demo script: docs/demo-script.md
(~8 min, offline-safe except the live AI run).

## Capabilities and Constraints

- Chat agent with a deterministic command layer matched BEFORE the LLM
  (navigation, status, select case, run comparison, export) — the demo never
  depends on the gateway for core flows.
- Field-level Soll/Ist comparison with German glossary, fail-closed
  NOT_EVALUATED on missing evidence.
- Evidence chain RPT → RUN → TC → CRIT → REQ → SRC built from real store
  records, each chip click-through.
- Formal PDF report (preface, executive summary, recommended actions,
  appendix) + integrity seal card (GENUINE/TAMPERED simulation).
- Legacy "Prüfakte" artifact reachable as advanced mode.
- Constraint: live AI pipeline (extractor → designer → challenger) takes
  minutes and must show progress and stay bounded; offline fallback is honest
  and recorded.

## Brand Commitments

Name SÜSIE; crimson accent on warm-neutral surfaces, light default with
dark/contrast themes; 14 px card / 10 px control radii; system-ui stack.
Language: German first, EN toggle. SÜSIE never owns a decision — copy must keep
"KI schlägt vor, der Mensch entscheidet".

## Evidence on Hand

- Official Beispielpapier DTA EEL V13.3 §3.1/§3.2.1.4 and VB §3.12 (S. 135–136)
  as the legal corpus; expected values only from the official example paper.
- Regression harness: 300/300 correct, 0 false alarms (130 clean, 170
  detected, 25 ambiguous escalated NEEDS_REVIEW).
- Full store with real evidence chain in data/demo (regenerated
  deterministic); showcase PDFs in reports/story-showcase/.

## Product Principles

1. Ohne Beleg kein Bestand — fail closed everywhere; missing evidence is never
   a pass.
2. KI schlägt vor, der Mensch entscheidet — every mutating step runs only on
   explicit confirmation and records who decided and who executed.
3. Vollständige Nachvollziehbarkeit — every shown result links back to its run,
   criterion, requirement, and source.
4. Deterministisch, wo es geht; ehrlich, wo nicht — the deterministic layer
   carries the demo; AI gaps degrade visibly, never silently.

## Accessibility & Inclusion

Keyboard-operable cards (role=button, Enter/Space, aria-expanded), tooltips
with Notencode, high-contrast and print styles, reduced-motion-aware
animations; German public-sector WCAG expectations apply.
