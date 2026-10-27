# SÜSIE the Assistant — Conversational Wizard Design

**Date:** 2026-10-26 · **Status:** draft for human approval · **Work order:** to be
claimed on `.leapfrog/board.md` before implementation starts.

## Intent and why

SÜSIE (Systemüberprüfung sozialversicherungsrechtlicher IT-Ergebnisse) today is a
menu-driven review surface. The assistant inverts that: a real conversational agent,
bilingual (German/English), who asks what the reviewer wants, understands free-form
input, and **takes over the app** — the reviewer never has to explore a menu. She asks,
she understands, she guides, she informs in explicit detail, she summarizes in executive
manner. Her register is the precise, courteous formal **Sie** a German social-law
expert expects; never chummy. For the live hackathon demo she runs in **GOD mode**:
full operational power over the app, with one engineered exception (below) that keeps
the repo's own governance story intact.

The design doctrine is the *structured-guided conversation* pattern (chatbot-flow-design
skill): neither a scripted decision tree nor an ungrounded hallucinating LLM. A bot
that admits it does not know earns more trust than a bot that fakes confidence — SÜSIE
makes that a designed, visible moment.

## Goals

1. Real conversational agent (LLM-backed), German and English, auto-detected from the
   user's first message and mirrored thereafter.
2. Two presence modes, one shared session/conversation memory:
   - **Fullscreen SÜSIE mode** — opened by a glowing, animated SÜSIE-logo button that is
     the first item in the sidebar. She owns the screen; the chat is the primary surface
     and app state (cases, evidence chains, comparisons) renders inside the conversation.
   - **Floating overlay wizard** — a compact chatbot-style panel docked over the normal
     Prüfakte interface; you watch her steer the actual app underneath. Mode toggle in
     both surfaces; switching never loses the thread.
3. Takeover by confirmation: she proposes an action as a simple yes/no inline question
   with buttons ("Soll ich TC-002 öffnen?"); **Ja** → she executes; **Nein** → she gives
   precise manual instructions instead. She never chains actions silently.
4. GOD mode: she executes everything — navigation, case selection, filters, evidence
   opening, saving notes, running comparisons, exporting the synthetic JSON report,
   mode switching, initiating review flows.
5. Citation discipline, two tiers:
   - App state / accepted corpus claims **must** carry a citation (source passage, case
     record, or comparison result). No citation → she says so: "Das kann ich nicht
     belegen."
   - General-knowledge answers are allowed but a strict system prompt forces her to
     first state "Das steht nicht in meinem Datensatz" and attach a visible
     **disclaimer badge** before answering.
6. Honesty as a hard rule: when she cannot understand an assignment she asks again for
   confirmation or direction (layered fallback: clarifying question → suggested
   intents → honest "I don't know"); when she does not know an answer she says so
   plainly. She never fabricates.
7. Human-commanded decision gates: at approval points (review state, conformance,
   release) she presents the decision, recommends, and executes **on the human's
   explicit word** ("Genehmige TC-002" or one button). The audit record names the
   **human as decision-maker** and SÜSIE as executor. She is not the authority; she is
   the hands.
8. Demo resilience: rehearsed graceful degradation when the LLM gateway is unreachable
   ("Meine Verbindung zum Wissensdienst ist unterbrochen …") — the demo must not die
   on wifi.

## Non-goals

- This document does not design the whole web app (visual identity, non-SÜSIE screens);
  it specifies the **SÜSIE contract** the frontend team builds against (see below).
- No real payroll/personal data anywhere; synthetic fixtures only.
- No new ingestion *design*; the wizard consumes the corpus through the existing
  ingestion pipeline. Landing T10-006 (index build) is an explicit dependency of this
  task, decided by the human owner 2026-10-26 ("FULL option now") — the stubs are being
  replaced by parallel work.
- No autonomous chained actions without confirmation (except explicitly whitelisted
  read-only navigation steps inside one guided flow).

## Anti-goals (would make this a failure even if it "works")

- SÜSIE fabricating a legal claim, a citation, or a conformance result.
- SÜSIE appearing — on stage or in the audit trail — as the legal approver.
- The demo contradicting the repo's own PRODUCT.md/governance docs ("AI suggestions
  remain candidates"; fail-closed everything).
- A dead-air moment when the network hiccups.

## Constraints

- Governance (`agent-governance.md`, `AGENTS.md`): no agent approves legal meaning,
  expected legal values, template applicability, report conformance, or final release;
  cite-or-abstain; append-only audit events; fail closed.
- Secrets: gateway token only via `itsg/secrets.py` (Fernet store). No token in
  frontend code, prompts, fixtures, or logs. (Note: `API.py` currently contains a
  hardcoded key — out of scope here, but must be moved to `itsg/secrets.py` and rotated
  before any commit.)
- Stdlib-first backend like the existing bridge; no heavy new dependencies.
- Server binds 127.0.0.1 only; the LLM token never leaves the server side.
- The existing `itsg/webserver.py` (T10-031) already serves the frontend and a read-only
  JSON API (`/api/health`, `/api/state`, `/api/run`) — the wizard extends it, it does
  not replace it.
- Reduced-motion preference: the glowing sidebar button skips its animation, consistent
  with the app's existing motion rules.
- Frontend direction (human owner, 2026-10-26): the closed static `pruefakte.js`
  artifact will be **replaced by an actual web app built by the frontend team**. This
  document specifies the contract SÜSIE needs from that app; the team owns the
  framework choice and the rest of the product design.

## Approaches considered

1. **A — Thin Python service extending the existing web bridge (CHOSEN).** Extend
   `itsg/webserver.py` with chat endpoints; reuse `itsg/llm.py` (gateway client,
   SSRF-hardened endpoint policy, encrypted token), `pipeline/index/fts.py` for cited
   retrieval over G0-accepted sources, and a server-side **action registry** that
   validates every proposed action against a whitelist before the frontend may run it.
   Chat turns are logged to the append-only audit JSONL. Balances build speed (~a day)
   with a real, demonstrable governance story.
2. **B — Browser-direct.** JavaScript calls the gateway directly, client-side prompt
   assembly, pre-built corpus snapshot as static JSON. Fastest to stand up, but ships
   the API token to the browser, trusts the client for every action, and reduces the
   fail-closed story to set dressing. Rejected.
3. **C — Deep itsg integration.** Every chat turn formally wrapped in the
   `itsg/candidates.py` AgentRun envelope with cite-or-abstain enforced in code,
   extending `itsg/demo.py` into the chat backend. Most governance-pure, heaviest, and
   coupled to unfinished pipeline stubs (T10-004/005/006).

**Decision (human owner, 2026-10-26): Approach A, borrowing C's AgentRun envelope for
chat turns** — every SÜSIE answer is a logged, citation-carrying candidate record,
without waiting on the unfinished pipeline stages. Plus the rehearsed gateway-timeout
fallback from the start. Two owner refinements on the builder check:

- **Retrieval: full T10-006.** The accepted-only FTS5 index is landed for real (parallel
  work is already replacing the stubs); SÜSIE retrieves against the full dataset, not a
  stopgap.
- **Frontend: new web app.** The static artifact is replaced by a real web app built by
  the frontend team to the SÜSIE contract below — a first-class action bus instead of
  extensions to a closed IIFE.

## The decided how

### Backend (extension of `itsg/webserver.py`)

- `POST /api/chat` — body: conversation so far + current app-state context id. Server
  assembles the system prompt (persona, two-tier citation discipline, disclaimer
  rule, language mirroring, formal Sie), injects current `/api/state` data and
  retrieval results from the accepted-only FTS index, calls the gateway via
  `itsg/llm.py`, and returns a structured reply.
- Structured reply contract (JSON): `utterance` (her spoken line), `citations[]`
  (record/segment ids she used), `proposed_action` (optional, registry-validated),
  `needs_confirmation` (true for any non-read-only action), `disclaimer` (optional,
  general-knowledge flag), `agent_run` (the AgentRun envelope, written to the audit
  JSONL before the reply is sent).
- `POST /api/action` — body: action id + params + the confirmation token from the
  yes/no button. Validated against the **action registry whitelist**; anything not
  whitelisted fails closed. Read-only actions (select case, open evidence, filter,
  jump to source) may be auto-executed inside a guided flow; mutating actions (save
  note, export report, run comparison, initiate review flow) always require the
  click; **decision-gate actions** additionally require the human's explicit command
  word/button and are recorded with `decision_maker: human`, `executor: SÜSIE`.
- `GET /api/chat/history` — session replay (bounded).
- Fallback behavior: on gateway timeout/unreachability the server returns a
  structured degraded-mode reply; the frontend renders the rehearsed message and
  offers the manual path. No fabricated content ever.

### Action registry (initial whitelist)

Read-only: `select_case`, `open_evidence`, `filter_cases`, `jump_to_source`,
`show_comparison`, `switch_mode`.
Mutating (confirmation required): `save_note`, `export_report`, `run_comparison`,
`initiate_review_flow`.
Decision-gate (human command required): `record_review_state`, `record_conformance`,
`request_release` — each only through the existing itsg gates logic; gates cannot be
skipped (states.py).

Execution model: `/api/action` executes **server-side** into the itsg store using the
existing records/gates logic — the audit story is real, not narrated. Mutating actions
write real records; `export_report` is generated server-side from the store and
delivered as a download. `request_release` records and narrates the release *request*
and routes it to the human; the release control itself stays disabled with its visible
explanation (the existing product decision is not superseded). Reviewer identity for
gate records: SÜSIE asks at session start "Mit wem arbeite ich?" (or "Who am I working
with?"); the given name is carried as the human reviewer on every gate decision,
satisfying the author ≠ reviewer rule because her AgentRun is never recorded as
reviewer.

### Intent architecture (chatbot-flow-design)

Named intents covering the review workflow: `explain_case`, `explain_deviation`,
`show_source`, `where_am_i` (executive summary of review progress), `next_step`,
`do_action`, `export`, `general_question`. Target 70–90% coverage of the demo script;
everything else falls to the layered fallback: one clarifying question → suggested
intents (as clickable chips) → honest "das kann ich nicht belegen". No more than two
consecutive clarification rounds before she says honestly what she cannot do. Escalation
trigger: any request at a human decision gate is handed back with the way there —
"Das ist eine menschliche Entscheidung – sagen Sie mir, wenn ich ausführen soll."

### Frontend contract — the SÜSIE-era web app (built by the frontend team)

The frontend team owns framework choice and product design. This contract is what SÜSIE
requires the app to expose; anything not listed is theirs.

**1. Action bus (the takeover surface).** A first-class, whitelisted command API —
`app.actions.invoke(actionId, params, confirmationToken)` — mapping 1:1 to the server's
action registry. Every invocation reports success/failure with a typed result so SÜSIE
can narrate outcomes ("TC-002 ist geöffnet"). No synthetic DOM-event clicking; the bus
is the only way she touches the app. The app must also **emit state-change events**
(`case_selected`, `evidence_opened`, `filter_applied`, `note_saved`, …) so her
conversation and the app state can never drift apart.

**2. Two presence surfaces, one session.**
- *Fullscreen SÜSIE mode:* full-viewport takeover; the chat is the primary surface and
  app state (cases, evidence chains, comparison results) renders as cards inside the
  conversation flow.
- *Floating overlay wizard:* docked panel (~380 px) over the normal interface; the
  reviewer watches her steer the live app underneath.
- Shared conversation memory; a mode toggle in both surfaces; switching never loses the
  thread.

**3. Entry point.** The first sidebar item is the SÜSIE logo with a glowing CSS pulse
halo (`prefers-reduced-motion` disables the pulse); click opens fullscreen mode.

**4. SÜSIE UI components** (themeable, must meet the existing contrast minima across
all four theme variants):
- Chat bubbles with streaming text (SSE from `POST /api/chat`).
- Yes/no confirmation buttons rendered from `proposed_action`; Nein → she narrates the
  manual steps instead.
- **Disclaimer badge** for general-knowledge answers (the visible "not in my dataset"
  moment).
- **Citation chips** bound to `citations[]`, jumping to the source passage on click.
- Degraded-mode banner for the rehearsed gateway-off message.
- Intent suggestion chips for the fallback path ("Meintest du …?").

**5. Language.** SÜSIE auto-detects German/English from the first user message and
mirrors it; her surface (chat, buttons, badges, mode toggle, degraded copy) is
bilingual with DE default and formal Sie in German. The rest of the app chrome is the
frontend team's decision (existing artifact is German-only).

**6. Reviewer onboarding.** At session start SÜSIE asks "Mit wem arbeite ich?"; the
answer is sent with the session and becomes the human-reviewer name on gate records.
The app must surface this once and allow correction.

**7. Continuity.** Synthetic-data labelling, human-review framing, notes-as-non-durable
semantics, and print/forced-colors behavior carry over from the existing DESIGN.md;
the wizard adds no certification authority and never renders an approval that the
audit trail does not name a human for.

### Demo script (party-trick arc, synthetic data only)

1. "SÜSIE, wo stehe ich?" → executive summary of the review state.
2. "Warum weicht TC-002 ab?" → cited explanation, evidence rendered inline.
3. "Zeig mir die Quelle dazu." → she executes the jump (read-only, no prompt).
4. "Was gilt bei Fehlzeiten im EAZ?" → cited answer from the accepted corpus.
5. A general-knowledge probe → disclaimer badge, honest tier separation.
6. "Speichere meine Notiz und exportiere das Protokoll." → yes/no confirm, executes.
7. "Genehmige TC-002." → she presents, recommends, executes on command; audit record
   names the human.
8. (Rehearsed) gateway off → graceful degraded message, manual path offered.

## What's left to the builder

- SSE vs. polling for streaming (SSE preferred); exact system-prompt wording (must
  implement the citation/disclaimer rules, reviewed before demo).
- Visual design of chat bubbles within the four-theme system (Casual/High Contrast,
  light/dark) — must pass the existing contrast minima. Frontend team's territory
  within the contract above.
- Exact AgentRun envelope field mapping for chat turns (reuse `itsg/candidates.py`
  shapes; `review_required` semantics for chat do not block display).
- Test strategy: stdlib `unittest` for the server (registry validation, fail-closed
  paths, degraded mode); manual demo rehearsal for the conversation UX.
- Store location for chat audit records (append to existing `events.jsonl` pattern).
- Dependency sequencing: T10-006 index build lands before or with the wizard work;
  the chat backend must degrade honestly (app-state-only citations, clearly labelled)
  if the index is not yet populated.

## Open items for the human owner

- Confirm the demo script arc above is the party-trick order you want.
- Board claim: this needs a work-order ID and owner before implementation starts
  (backend/wizard) — the frontend team's app build is tracked separately against the
  contract section.
- This spec is not committed to git yet; committing requires your explicit
  authorization per AGENTS.md.
