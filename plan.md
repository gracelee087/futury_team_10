# ITSG Hackathon — 24-Hour Team Plan

## Goal

Build a small, credible demonstrator of the ITSG review loop: take one technical requirement, turn it into reviewed test cases, compare a fabricated payroll-software output, and produce a traceable report. The presentation's focus is reviewing payroll software for *Entgeltersatzleistungen*. The prototype demonstrates **how evidence is organized and checked**; it does not certify software or calculate a real person's benefit.

## What the team will show

One end-to-end path:

`technical source excerpt + applicable form/template → cited requirement → human-approved criterion → synthetic test case → fabricated execution output → deterministic comparison → mandated-form rendering → conformance check → human-approved report`

The core slice must work before any optional AI features. Use the provided presentation as challenge context, not as a source of benefit formulas. If the team does not have a current authoritative specification and approved expected result, demonstrate the workflow with a clearly labeled synthetic technical fixture. No real payroll or personal data.

## Team roles

| Person | Primary ownership | Concrete deliverables |
|---|---|---|
| Member 1 (Devansh) | Data Ingestion | Text chunking, indexing service, Vector Embeddings|
| Member 2 (Fares) | Retreival | Input/output schema, request to externalAPI to AI  and response |
| Member 3 (Lisa) | Data Ingestion | Text chunking, indexing service, Vector Embeddings|
| Member 4 (Oussama and Houssem) | Test-case workflow and user interface | Test-case list/detail; expected-vs-actual display; clear statuses and report screen |
| Member 5 | Vendor output and report integration | Synthetic CSV/JSON output importer; report renderer; required-field/structure conformance checks; evidence-backed report |
| Member 6 | Scope, source checks, human gates, acceptance, demo narrative | Choose the bounded example; help identify the applicable official report form and its version; confirm form assumptions with a qualified reviewer; keep claims honest; track decisions/blockers; rehearse and present |

The three Bachelor roles can shift based on their strengths. Keep one owner per deliverable and agree on shared record formats early. You do not need to write the legal rules or the core engine to contribute: protect the scope, make sure evidence is visible, and stop the demo from claiming more than it proves.

## Working with multiple AI and coding tools

The AI tools are assistants, not additional decision-makers or votes. Use the same constraints for Kolibri, GLM5.3Flash, OpenAI models, Anthropic models, and any other approved tool. Choose by task fit and availability; provider identity does not make an answer authoritative.

- MSc 1 acts as the human technical integration lead: keeps the shared task board, assigns one coding-agent owner per file/interface, and accepts or rejects integrations.
- You own product scope and the human/domain checkpoints: confirm the official sources and form/template version with an appropriate reviewer, decide what the demo may claim, and stop unresolved issues from being presented as passes.
- Every coding-agent assignment has a task ID, one owner, allowed files, acceptance criteria, required verification, and a named reviewer. No two coding agents edit the same file at once.
- Every system-agent call uses the role contracts and structured outputs in [agent-governance.md](agent-governance.md). Log provider/model, reported revision (or `unavailable`), prompt version, input source IDs, output ID, status, and reviewer decision.
- Keep AI outputs as candidates until deterministic schema/citation checks and the required human gate pass. Do not merge model answers by majority vote. Record disagreements and escalate them against the source.
- Use only fabricated payroll data. Do not put credentials or real employee/payroll records into prompts, shared agent context, logs, or demo fixtures.
- A separate person or agent reviews each code change, but a human owner accepts it. AI review cannot approve legal meaning, expected values, applicable templates, conformance, or the final report.

The complete reusable contract is [agent-governance.md](agent-governance.md). Read it before assigning work to a coding agent or enabling a system-agent role.

## Async progress and checkpoints

Since team members may not coordinate directly, treat `.leapfrog/board.md` and `.leapfrog/log.md` as the canonical shared status. Follow [AGENTS.md](AGENTS.md) and [DELIVERY.md](DELIVERY.md): claim tasks and file ownership before editing; update status at transitions and at least every 45 minutes; hand off with changed files, next step, blocker, and verification evidence; and write paired Leapfrog checkpoints every two hours, after material decisions, before handoff/context reset, and at session end. Chat updates supplement these durable records. The exact `Team10-LetzGo!` prefix is an instruction-following marker only; it is not a factuality check.

## Schedule and decision gates

These are elapsed-time blocks, not a requirement for everyone to work continuously. Take breaks and use short handoffs; a tired final integration is a bigger risk than one fewer stretch feature.

| Time | Milestone | Exit check / decision |
|---|---|---|
| 0:00–0:45 | Align on demo story, inspect sources, choose one example | Write one sentence describing the demo. Identify the required report form/template and applicable version/date. Confirm whether the official form and instructions are available; if not, explicitly switch to a synthetic template demo with no compliance claim. |
| 0:45–2:00 | Define record formats, template metadata, agent work orders, and report sketch | Agree on IDs, citations, execution-output schema, template metadata, comparison statuses, `BLOCKED / NEEDS_REVIEW` behavior, file ownership, and one work order per coding-agent task. Sample records exist before parallel coding. |
| 2:00–5:00 | Build source/requirement intake and comparator foundation | Source and template can be recorded with version/citation metadata; comparator reads a fixture and returns a structured result. Agents stay within assigned file scopes. |
| 5:00–8:00 | Build test, execution-output, and report-template views | User can see the requirement, expected and observed results, applicable template version, required fields, and evidence links. |
| 8:00–11:00 | Connect the vertical slice | At least one case runs from source/template records through render and conformance check with no hidden manual edits. Fix integration/schema issues before adding AI. |
| 11:00–14:00 | Add review events, edge cases, and failure paths | Missing citation/expected value/template version, missing required form field, or failed structure check blocks the report; mismatch is visible; audit history is retained. |
| 14:00–17:00 | Add optional AI assistance only if core path is stable | AI may draft requirement candidates or extra test ideas with citations and a visible “needs human review” status. No AI-generated formula or auto-approval. |
| 17:00–20:00 | Freeze features, rehearse, improve report clarity | Run demo from a clean start. Prepare backup screenshots/fixtures and a short explanation of limitations. |
| 20:00–24:00 | Demo window / buffer / final polish | Present the working vertical slice, show one mismatch and its evidence chain, then explain what would need expert validation for real use. |

## Acceptance criteria

The MVP is ready to demonstrate when all of these are true:

- One source document or excerpt is stored with issuer/origin, version/date, checksum or stable file ID, and a page/section citation.
- A requirement is shown as a candidate until a human approves it; its source passage is one click or one visible panel away.
- At least three synthetic test cases cover a normal case, a boundary/edge case, and an invalid or missing-input case. Expected results are manually reviewed and tied to the fixture/criterion.
- Vendor documentation and observed execution output are represented separately. A manual or claim cannot masquerade as a test run.
- A deterministic comparator returns `PASS`, `MISMATCH`, or `NOT EVALUATED` with the reason and linked evidence. Missing source, expected value, or execution output never produces a pass.
- The report is rendered in the applicable official mandated form/template, not only as a generic narrative. Its template ID/version, source, validity period, and checksum or stable artifact reference are recorded.
- A conformance check verifies required fields/sections, labels, order/structure, permitted blanks, output type, and value mapping against the verified template profile. A failed or unknown check blocks a compliance claim and appears in the report/audit record.
- If the official form/version is not available to verify during the hackathon, the demo uses a conspicuously labeled synthetic template and explicitly claims no legal/template compliance.
- The report identifies the source version, criterion, test ID, software/build label if known, observed result, reviewer state, and unresolved limitations.
- A human review event and a second independent check are visible for the high-impact criterion or comparator logic.
- Every system-agent output records provider/model, reported revision (or `unavailable`), prompt-contract version, input source IDs, schema validation, status, and human review state; any rejection or disagreement remains in the audit trail.
- Coding changes have a human-issued task ID, scoped file ownership, a named independent reviewer, and a verification handoff; unreviewed agent code is not part of the demo.
- The demo contains only fabricated data and makes no zero-error, legal-compliance, or real-benefit calculation claim.

## Minimal data contract

Use JSON or database records with these fields; do not over-design the schema during the first two hours.

```json
{
  "source": {"id": "SRC-1", "title": "Demo fixture", "issuer": "...", "version": "...", "valid_from": null, "checksum": "..."},
  "template": {"id": "TPL-1", "official_form_id": "...", "version": "...", "valid_from": null, "source_id": "SRC-2", "checksum": "...", "status": "needs_review"},
  "requirement": {"id": "REQ-1", "text": "...", "source_id": "SRC-1", "citation": "page/section", "status": "needs_review"},
  "test_case": {"id": "TC-1", "criterion_id": "CRIT-1", "inputs": {}, "expected": {}, "expected_basis": "...", "review_status": "approved"},
  "execution": {"id": "RUN-1", "vendor": "Demo only", "software_version": "unknown", "test_case_id": "TC-1", "observed": {}, "evidence_ref": "..."},
  "report": {"id": "RPT-1", "template_id": "TPL-1", "renderer_version": "...", "field_map_version": "...", "artifact_ref": "...", "conformance": [{"check": "required_fields", "status": "pass"}]},
  "finding": {"status": "NOT EVALUATED", "reason": "...", "links": ["SRC-1", "REQ-1", "TC-1", "RUN-1"]},
  "review": {"reviewer": "...", "decision": "...", "timestamp": "..."}
}
```

`valid_from` may remain null when the source does not establish it. Do not fill unknown metadata with guesses.

## Test and review checklist

Keep this as a short manual checklist or automated checks if time permits:

1. **Traceability:** every reported result links to a test, criterion, requirement, source version, and exact locator.
2. **Missing evidence:** remove the expected value or source link; verify the result becomes `NOT EVALUATED` or blocked.
3. **Mismatch:** change one observed output; verify the report highlights the exact field and both values.
4. **Boundary and invalid input:** verify the case is labeled and the comparator handles it without crashing or inventing an expected legal result.
5. **Version change:** update the source version; verify the old run remains reproducible and the new version does not silently overwrite it.
6. **Review separation:** verify a generated candidate is not approved until a person records a decision; reviewer/author are visible.
7. **Input separation:** verify vendor documentation and execution output have different types and are displayed distinctly.
8. **Template version:** an unknown, superseded, or date-inapplicable template blocks a compliance claim; earlier rendered reports retain their original template version.
9. **Template conformance:** remove a required field, change its label/order, or use the wrong file format; verify the check fails and the report is blocked or marked non-compliant.
10. **Privacy:** inspect all demo data and logs; confirm there are no real employee identifiers or payroll records.

## Scope cuts and stretch goals

Cut in this order if time slips:

1. Remove vector search and graph database; retain stable IDs and explicit links in a small relational store or JSON.
2. Remove automatic PDF parsing; manually enter one excerpt and retain its page citation.
3. Remove AI extraction and translation; use human-entered candidates.
4. Reduce the number of cases, but keep one pass, one mismatch, and one blocked/not-evaluated example.

Only after the vertical slice works, consider:

- AI requirement suggestions that quote the source and always require approval.
- AI-generated extra edge cases with a separate reviewer check.
- A graph visualization of the citation-to-result chain.
- A working translation with independent bilingual review.

Do not stretch into a benefit calculator unless the team has a verified current source, an explicitly scoped formula, qualified review, and time for independent mathematical validation. Otherwise the calculator is an unsafe distraction from the challenge's review workflow.

## Risks and responses

| Risk | Response |
|---|---|
| No authoritative current technical specification or formula is available during the event | Use a conspicuously synthetic technical fixture. Demonstrate provenance and comparisons; state that no legal result is being validated. |
| Applicable official report form/template or instructions cannot be verified | Show a clearly labeled illustrative template only; mark conformance as unverified and do not claim the report meets legal or ITSG requirements. |
| Template has changed or applicability date is unclear | Block report compliance status; preserve the prior template and report; ask the qualified reviewer to resolve the applicable version. |
| Rendered output omits or changes a required field, order, or format | Fail the deterministic conformance check and prevent final sign-off until corrected. |
| Unclear source version or effective date | Mark the requirement blocked and show the review handoff. Never guess which version applies. |
| AI fabricates a citation or expected value | Require locator validation against the stored source; keep AI output as a candidate; compare only against a human-reviewed expected value. |
| Team builds infrastructure before it has a working user path | Start with JSON/SQLite, one page, and one deterministic comparator. Add graph/vector services only after the path works. |
| Vendor manual gets confused with actual software behavior | Keep document and execution schemas separate; report only observed outputs as execution evidence. |
| Parser or integration work overruns | Allow manual entry of a small excerpt and a fixed CSV/JSON fixture; preserve the same evidence chain. |
| Sensitive data enters a demo or external model | Use fabricated data only; do not upload payroll data; remove any accidental sensitive content from demo fixtures and logs. |
| The team is exhausted before presenting | Freeze features by hour 17, rotate breaks, rehearse from a clean start, and keep a backup recording/screenshots. |

## Demo script (about 3 minutes)

1. **Frame the problem:** ITSG reviews payroll software for *Entgeltersatzleistungen*. The prototype supports review; it does not replace the legal expert.
2. **Show the source:** open one excerpt and its version/citation metadata.
3. **Show the requirement:** point to the exact passage and its human-review status.
4. **Show test cases:** explain one normal and one edge case, with expected values from the clearly identified demo fixture.
5. **Run the comparison:** import fabricated output and show a pass plus a deliberate mismatch or missing-evidence result.
6. **Open the report:** show the applicable form/template version, the generated mandated layout, conformance-check results, then follow a finding back through execution, case, criterion, requirement, and source; show review history.
7. **State the boundary:** if the official form was not available, say the displayed layout is illustrative and unverified. Actual legal rules, form applicability, translations, and calculations require authoritative current material and qualified review before real use.

## Finish-line message

“This prototype demonstrates a traceable way to turn reviewed technical requirements into test cases, compare payroll-software output, and render the result using a versioned report template with explicit conformance checks. It uses fabricated data. If the applicable official form was not verified, the displayed template is illustrative only. The prototype does not establish that a real payroll result is legally correct; that requires current authoritative sources, expert approval, and much broader validation.”

