# Data-protection impact assessment (DPIA) – sketch for the Team 10 prototype

**Draft for discussion, not legal advice.** Written by the engineering team (T10-007). It is meant to give ITSG's data-protection
officer something concrete to correct. Nothing here has been reviewed by a lawyer or a data-protection officer.

## 1. Purpose
An AI-assisted review loop helps ITSG check whether payroll software sends sick-leave data (DTA EEL, Abgabegrund 41 and the message flow)
correctly. The prototype reads software test output, applies deterministic checks, answers rulebook questions with checked quotes, and
produces a report that a person approves.

## 2. Data and data subjects
| Data | Where it could appear | Sensitivity |
|---|---|---|
| Versicherungsnummer, names, birth date, address, phone, email, IBAN | Real payroll test output; user questions | Personal data; with sick-leave dates it is **health data** (Art. 9 GDPR) and **social data** (§ 35 SGB I) |
| AU dates, Abgabegrund codes | Test output, reports | Health data when linked to a person; harmless alone |
| Betriebsnummer | Test output | Employer identifier (can identify a sole trader) |
| Reviewer names typed in the decision log | `reports/review-events.jsonl` | Personal data of staff |

Data subjects: insured employees, employer contacts, reviewers. **Current rule: the prototype uses fabricated data only.**
The questions below matter if ITSG wants to use anything real.

## 3. Recipients and places
- hessian.AI (model provider, stated to be in Germany with self-hosted open-weight models; not verified by us): receives pseudonymized questions and public rulebook text.
- Langfuse (tracing, external) only if keys are set: receives minimized, pseudonymized fields.
- Team server (Docker volume): reports, decision log, seal ledger (hashes only).
- ITSG seal: receives hashes and run IDs only.

## 4. Risks and measures
| Risk | Measure in the prototype |
|---|---|
| Personal data sent to the model | Airlock: detect and replace, then re-check; anything left = BLOCKED, no API call (`privacy/schleuse.py`, `retrieval/ask.py`) |
| Personal data in traces | Langfuse guard: minimize, pseudonymize, check; public trace refused unless every payload was clean |
| Personal data in logs | Log filter on the ask and UI loggers; servers do not log user text |
| Data kept too long | Reports and harness results deleted after `RETENTION_DAYS` (default 7) |
| Vendor edits or hides results | Seal with HMAC receipts and hash-chained ledger (hashes only) |
| Re-identification from tokens | Tokens come from a keyed hash; key in the server environment only; mapping kept in memory for one request |
| Data minimization / privacy by design | Only the fields needed for a check go anywhere; protection is in the code path (Art. 25, Art. 5(1)(c)) |
| Storage limitation | Retention job (Art. 5(1)(e)) |
| Erasure requests vs append-only ledger | The ledger stores hashes of reports, not report content. Deleting a report removes the personal data; the remaining hash is not meaningful without it. Whether a keyed hash still counts as personal data is an open legal question (see section 6). |

## 5. Residual risks (honest list)
- Regex detection misses free-text names without a cue word (10 of 10 in our stress test) and unusual formats.
- Our leak numbers come from synthetic records and detectors tuned on them; an independent reviewer set caught 18 of 19 before a fix.
- Pseudonymized data is still personal data under GDPR while anyone can link it back.
- Quasi-identifiers (rare job, small town, AU dates) can identify a person without a name.
- The decision log keeps typed reviewer names and is not purged automatically; there is no login.
- `PRIVACY_KEY` handling is minimal (environment variable, no rotation or vault); plain HTTP on the demo URL.
- Langfuse receives data only when keys are set; its location and contract terms were not assessed.
- The airlock protects `ask()`, the two loggers and the Langfuse calls; other future code paths are not covered automatically.

## 6. Open questions for ITSG's data-protection officer
1. Is a DPIA mandatory here (large-scale health data), and who is the controller and who the processor (ITSG, hessian.AI, Langfuse, us)?
2. Which legal basis applies to processing test data that comes from real payroll software, and can real data be used at all?
3. Is pseudonymized data with an in-memory mapping acceptable for sending to hessian.AI? Is a data-processing agreement in place and where exactly is the model hosted?
4. Does a keyed hash in the append-only ledger count as personal data, and does that conflict with a right to erasure?
5. Which retention period is acceptable for reports and the decision log?
6. Which technical measures does ITSG require (key management, access control, audit logging, TLS) before any real data is used?
7. Who approves changes to the detection rules and the leak-test evidence?
