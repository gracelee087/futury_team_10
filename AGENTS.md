# Team 10 Agent Instructions

These rules apply to every AI coding assistant and system agent working with this repository, regardless of provider. Read this file before starting work and follow the shared source of truth in `agent-governance.md`, `DELIVERY.md`, and `.leapfrog/`.

## Chat marker

Begin every human-facing chat response to the team with exactly `Team10-LetzGo! ` as the first text. This confirms the agent received and followed this instruction; it is **not** a truth or hallucination check. Claims still require sources, evidence, and review. Do not add the marker to JSON/API payloads, generated report files, or other machine-readable artifacts.

## Start of every task/session

1. Read `AGENTS.md`, `DELIVERY.md`, and `agent-governance.md`.
2. Read `.leapfrog/CLAUDE.md`, `.leapfrog/index.md`, the latest checkpoint x/v pair, the last five `.leapfrog/log.md` entries, and `.leapfrog/wiki/hot.md`.
3. Read the relevant track file and inspect the shared task board `.leapfrog/board.md`.
4. Before editing, report the current state in one short note: what changed, what was verified, what must not be retried blindly, and the task/file ownership you are taking.

## Work ownership and non-overlap

- No task starts without an ID, one human owner, one agent owner, allowed paths, acceptance criteria, reviewer, and a progress-update deadline in `.leapfrog/board.md`.
- One writer may own a file at a time. Claim the file/task on the board before editing; do not edit, overwrite, rename, or revert another active owner's files.
- If another agent has touched a claimed file, pause and coordinate in the shared task log. Never resolve overlap by last-write-wins.
- Keep changes within the named paths and task scope. Ask the human task owner before adding dependencies, changing shared schemas, or altering legal/form decisions.
- The checked-out repository, approved source versions, and logged human decisions are the source of truth. Chat statements and model outputs are not approvals.

## Frequent progress and checkpoints

- Update the board and append a log entry when a task starts, changes state, reaches a meaningful milestone, becomes blocked, enters review, or completes.
- Post a concise progress note at least every 45 minutes while work is active, and immediately before a handoff or context compaction. Include done, in progress, next, blocker, files owned, and verification evidence.
- Write/update a Leapfrog x/v checkpoint pair every two hours of active work, after any material architecture/interface decision, before handoff, and at session end. Update `hot.md`, `index.md`, active track files, and the append-only logs with the checkpoint.
- Mark work `DONE` only when acceptance criteria are met and verification evidence is recorded. Otherwise use `IN REVIEW`, `BLOCKED`, or `NOT VERIFIED`; never overclaim.
- When an approach fails, log the evidence and the condition required before trying it again. Do not repeat it blindly.

## Safety and authority

- Follow the role boundaries, source/citation, privacy, and fail-closed rules in `agent-governance.md`.
- No agent may approve legal meaning, expected legal values, template applicability, report conformance, or final release.
- Do not use real payroll/personal data or credentials in prompts, fixtures, or logs.
- Do not commit, push, deploy, publish, or send external messages unless a human explicitly authorizes that action.

