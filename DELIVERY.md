# Team 10 Agile Delivery Protocol

This is the repo-local delivery contract for the 24-hour hackathon and follow-on work. It applies across team members and all AI tools. The team previously requested an `agile-delivery` skill, but that skill was not present in the available catalog or memory files when this protocol was written. Replace or extend this protocol if the team later supplies that skill; do not claim it was used.

## Work item contract

Before work starts, create a row in `.leapfrog/board.md`:

| Field | Required value |
|---|---|
| Task ID | Stable ID such as `T10-001` |
| Outcome | Observable behavior or artifact to deliver |
| Human owner | One accountable team member |
| Agent owner | One named agent/provider/model for implementation; `none` if no AI agent |
| Reviewer | A different person/agent, plus human acceptance owner |
| File scope | Exact paths the owner may change |
| Dependencies | Task IDs or source/template version IDs; `none` if clear |
| Acceptance | Verifiable conditions for completion |
| Status | `READY`, `IN_PROGRESS`, `BLOCKED`, `IN_REVIEW`, `DONE`, or `DROPPED` |
| Next update | Date/time or event trigger |
| Evidence | Commit/diff/artifact path and verification result when available |

Keep one active implementation task per agent. Limit shared files to one writer at a time. Reviewers should not edit the same files while reviewing; they return findings to the owner. Only the named human integration lead resolves merge order and accepts completion.

## Progress cadence

Because team members may not communicate directly, the repository board and append-only log are the canonical asynchronous handoff; chat is supplemental. Do not depend on a meeting or on another agent reading a private conversation. Update the task row and append a short written update at each state transition and milestone, at least every **45 minutes** during active work, and before every handoff, context reset, or session end. If there is no progress, record what is blocking progress and what input is needed; do not leave the board silently stale.

Use this format in the shared chat and append the durable record to `.leapfrog/log.md`:

```text
Team10-LetzGo! [Task ID] [IN_PROGRESS | BLOCKED | IN_REVIEW | DONE]
Done: ...
In progress: ...
Next: ...
Blocker: ... / none
Files owned: ...
Evidence/verification: ...
Handoff/reviewer: ...
```

Every two hours, after a material decision/interface change, before handoff, and at session end, update the current Leapfrog checkpoint pair. A checkpoint is not a substitute for the task board; the board is live work status, while checkpoints preserve recoverable project state.

## Definition of done

A task can move to `DONE` only when:

1. The agreed behavior/artifact exists in its allowed paths.
2. The owner lists changed files and decisions/assumptions.
3. Required verification has been run and its exact result recorded; if not run, state `NOT VERIFIED` and keep the task open or explicitly accepted as a scoped demo limitation by the human owner.
4. A separate reviewer has checked the diff against acceptance criteria and recorded findings or approval.
5. No unresolved blocker, source conflict, privacy issue, or unsupported legal/template claim is hidden.
6. The human owner accepts the item and the board, log, checkpoint, and track reflect the same status.

## Handoff format

```text
Team10-LetzGo! Handoff [Task ID]
Owner → reviewer:
Changed files:
Acceptance items met / unmet:
Verification performed and result:
Known risks or assumptions:
Open questions / next action:
Current branch/commit or artifact location:
```

The receiver acknowledges ownership on the board before editing. Unaccepted or unverified work remains `IN_REVIEW` or `BLOCKED`, not `DONE`.

## Conflict and recovery rules

- File collision: stop both writers, preserve both diffs, have the integration lead assign one owner, then reconcile explicitly. Never overwrite a peer's changes.
- Conflicting model answers: preserve each result and source list; inspect the primary source; route unresolved interpretation to the qualified human reviewer. No majority vote.
- Failed command/approach: record exact command/input, error/result, and the changed condition required for retry. Retry only when that condition changes.
- Stale or missing update: mark the task `BLOCKED` and note `owner confirmation needed`; do not assume completion or reuse the file scope until the owner confirms.
- Scope change: create or amend the work item and acceptance criteria before proceeding; log the decision and affected dependencies.

