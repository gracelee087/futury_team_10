"""SÜSIE — Systemüberprüfung sozialversicherungsrechtlicher IT-Ergebnisse.

The typed system-agent domain of the ITSG review assistant (agent-
governance.md §2: system agents operate only through scoped data and
typed interfaces), kept deliberately separate from the deterministic
ingestion ``pipeline`` package. Contents mirror plan.md's minimal data
contract and architecture.md §5/§7/§9:

  states       - workflow state machine (retries never skip a gate)
  gates        - human gate decisions G0–G6 (audit records)
  records      - source/template/requirement/criterion/case/execution/finding/report/review
  store        - JSON store + append-only event log (plan.md: versioned JSON files)
  comparator   - deterministic PASS / MISMATCH / NOT_EVALUATED (fail closed)
  renderer     - mandated-form report rendering (synthetic template => compliance_claim=False)
  conformance  - template conformance checks (fail closed)
  vorerkrankung- deterministic DBVO trigger rule (VB DTA EEL §3.12, versioned)
  candidates   - system-agent candidate envelope (§3) + author≠reviewer gates
  llm          - gateway client: Kolibri-1 (designer) / GLM-Flash (extractor, challenger)
  secrets      - locally encrypted credential store (data/secrets, gitignored)
  demo         - T10-018 end-to-end demo slice (python3 -m itsg.demo --fresh)

Naming decision by the human owner (2026-10-26): the app is SÜSIE.
"""

__version__ = "0.2.0"
