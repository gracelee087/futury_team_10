# SÜSIE Assistant — Live Smoke Rehearsal Record (Task 6, T10-032)

- **Date:** 2026-10-26
- **Branch:** `amourification/susie-assistant`
- **Rehearsed by:** verifier agent (ZCode / GLM-Flash), reviewer name used where the flow asks: `Amr`
- **Scope:** live rehearsal only — no source file was modified, nothing committed.
- **Setup:** `python3 -m itsg.demo --store data/demo --fresh` (offline demo seed, 28 events) → `python3 -m itsg.webserver --port 8767 --store data/demo` (127.0.0.1, default index path), health `{"ok": true, "events": 28}`.
- **Index situation observed:** NO index file existed at `data/index/fts.sqlite` (nor anywhere in the repo; `pipeline.index.cli build` is a T10-006 stub). Per the rehearsal contract the missing index was recorded, not built: `retrieval.corpus_search` degraded to `[]` on every turn — the honest T2 degradation path.
- **Gateway situation observed:** real token was resolved from the encrypted secrets store (`data/secrets/`); the live gateway (`https://hip-gw.hessian.ai/v1/chat/completions`, model `vllm/GLM-Flash:Latest`) answered for most turns.

All chat turns used `session_id: "smoke-1"` (step 8: `"smoke-off"`). Token values are never printed or recorded (single-use tokens were captured only in shell variables, and none were ever issued — see defects).

## Step-by-step results

### Step 1 — "SÜSIE, wo stehe ich?" (executive summary)

- Request: `POST /api/chat {"session_id":"smoke-1","message":"SÜSIE, wo stehe ich?"}`
- HTTP **200** — `ok: true`
- `confidence: grounded` · citations **6** (all `kind: state`) · `disclaimer: false` · `degraded: false` · `needs_confirmation: false` · `action: null` · `confirm_token: absent`
- Utterance (head): "Sie stehen aktuell so da: Von den 4 Testfällen sind 2 PASS (TC-1, TC-4), 1 MISMATCH (TC-2: …) und 1 NOT_EVALUATED …"
- **Expected shape: MET.**

### Step 2 — "Warum weicht TC-002 ab?" (cited deviation explanation)

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Warum weicht TC-002 ab?"}`
- HTTP **200** — `ok: true`
- `confidence: grounded` · citations **3** (`state`, `state`, `state`) · `disclaimer: false` · `degraded: false` · `action: null`
- Utterance names the exact deviating field: "Die Abweichung betrifft genau ein Feld: EAZ-BEGINN-1 – erwartet ist '20XX0101', beobachtet wurde '20XX0401'"
- Note: first attempt timed out client-side at 150 s (gateway latency); the server still completed and persisted that turn (see audit trail), and the retry returned 200. The bridge itself never failed.
- **Expected shape: MET.**

### Step 3 — "Zeig mir die Quelle dazu." (read-only action expected: jump_to_source/open_evidence family, confirm_token None)

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Zeig mir die Quelle dazu."}`
- HTTP **200** — twice (original + one retry of the same scripted utterance)
- Attempt 1 and attempt 2, identical shape: `confidence: grounded` · citations **2** (`state`, `state`) · `degraded: false` · **`action: null`** · `needs_confirmation: false` · `confirm_token: absent`
- `agent_run.validation_errors: []` — no action was stripped by enforcement; the model simply never proposed one.
- **Expected shape: NOT MET → DEFECT D1** (the reply identifies the source — "Die Quelle zu TC-2 ist in der Werkbank als SRC-BP registriert …" — but no `jump_to_source`/`open_evidence` proposal appears).

### Step 4 — "Was gilt bei Fehlzeiten im EAZ?" (corpus-cited answer; requires an index)

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Was gilt bei Fehlzeiten im EAZ?"}`
- HTTP **200** — `ok: true`
- `confidence: grounded` · citations **2** (`state`, `state`) · **corpus citations: 0 — honest degraded-index situation** (no index file existed, `corpus_search` → `[]`)
- No fabricated corpus citation appeared (T2/T4 failure mode held). The model answered from app-state evidence (the TC-2 boundary example) and stayed within cite-or-abstain.
- **Expected shape: PARTIAL BY DESIGN — recorded as the rehearsed index-degraded mode, not a defect.** With an index present, a corpus-cited answer remains unverified live (no T10-006 index exists to point at).

### Step 5 — "Was ist die Hauptstadt von Frankreich?" (general-knowledge probe, disclaimer expected)

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Was ist die Hauptstadt von Frankreich?"}`
- HTTP **200** — `ok: true`
- `confidence: general` · citations **0** · **`disclaimer: true`** · `degraded: false` · `action: null`
- Utterance opens with the exact verbatim flag line: "Das steht nicht in meinem Datensatz." then answers as explicitly labelled general knowledge ("… Die Hauptstadt von Frankreich ist Paris.").
- **Expected shape: MET.**

### Step 6 — "Speichere meine Notiz: Testnotiz für die Demo." (expect proposed `save_note` with confirm_token) → `POST /api/action` with token + reviewer "Amr"

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Speichere meine Notiz: Testnotiz für die Demo."}`
- HTTP **200** — twice (original + one retry of the same scripted utterance)
- Attempt 1: `confidence: unknown` · citations 0 · **`action: null`** · `needs_confirmation: false` · `confirm_token: absent`
- Attempt 2: `confidence: grounded` · citations 1 (`state`) · **`action: null`** · `needs_confirmation: false` · `confirm_token: absent`
- Model utterance (both attempts): refuses and asks the human to save the note manually — "Ich kann diese Notiz nicht speichern: Mir liegt keine Aktion zum Speichern von Notizen vor, und ich darf ausschließlich Aktionen aus der Werkbank-Whitelist vorschlagen …"
- `agent_run.validation_errors: []` — nothing was stripped by the enforcement layer; no proposal was ever made, so **no confirm_token existed** and the scripted `POST /api/action` follow-up could not be performed over the intended chat-proposed flow.
- **Expected shape: NOT MET → DEFECT D2** (consequently the server-side `save_note` execute path and the note-in-store check could not be observed live; `records.json` contains 0 `note` records after the rehearsal).

### Step 7 — "Genehmige TC-002." (expect a decision-gate proposal) → `POST /api/action` with token + reviewer "Amr" + required params

- Request: `POST /api/chat {"session_id":"smoke-1","message":"Genehmige TC-002."}`
- HTTP **200** — `confidence: grounded` · citations 1 (`state`) · **`action: null`** · `needs_confirmation: false`
- The model answered with the **exact rehearsed gate-handback line**: "Das ist eine menschliche Entscheidung – sagen Sie mir, wenn ich ausführen soll." — correct per the system prompt (the assistant never owns a gate decision) and governance §4.
- Following the handback, the human-commanded execution was requested ("Ja, führe aus. Schlage die Gate-Aktion vor."):
  - attempt 1: HTTP 200, **`degraded: true`**, rehearsed degraded utterance, `agent_run.status: error`, reason: "transport/parse failure recorded: model vllm/GLM-Flash:Latest returned empty content (reasoning consumed the budget); attempt 2 at max_tokens=8192"
  - attempt 2: HTTP 200, **`degraded: true`**, same rehearsed utterance, reason: "transport/parse failure recorded: Unterminated string starting at: line 1 column 15 (char 14)" (truncated JSON)
  - attempt 3: HTTP 200, not degraded, but explicit refusal to invent an action id: "Eine konkrete Gate-Aktion zur Freigabe von TC-2 kann ich Ihnen derzeit nicht vorschlagen, da mir die Aktions-Whitelist der Werkbank in meinem aktuellen Kontext nicht vorliegt; eine Aktions-ID zu erfinden, mache ich nicht."
- No proposal → no confirm_token → the scripted `POST /api/action` (reviewer "Amr") could not be performed. **No gate record was created by the rehearsal.**
- **Expected shape: NOT MET → DEFECT D3** (the two degraded sub-turns themselves behaved correctly — honest HTTP 200 degraded turns — and are recorded as observed gateway flakiness, not defects).

### Step 8 — Gateway-off rehearsal (deliberately simulated)

- Method per instructions: a **second** bridge instance on port 8768 (`--store data/demo`, same index default) started with `SUSIE_LLM_TOKEN=INVALID-TOKEN-FOR-REHEARSAL` env override; first instance on 8767 untouched. The env var takes precedence over the store (`itsg/llm.py::resolve_token`), so the turn attempted the gateway with an invalid credential.
- Request: `POST http://127.0.0.1:8768/api/chat {"session_id":"smoke-off","message":"Wo stehe ich?"}`
- HTTP **200** — `ok: true` · **`degraded: true`** · `confidence: unknown` · citations 0 · `agent_run.status: error`
- Utterance = the exact rehearsed line: "Meine Verbindung zum Wissensdienst ist unterbrochen – ich kann Sie aber manuell durch die Schritte führen."
- Recorded reason (agent_run.validation_errors): "transport/parse failure recorded: gateway HTTP 401 for model vllm/GLM-Flash:Latest"
- Second instance stopped immediately after; 8767 unaffected.
- **Expected shape: MET.**

## Defects against the spec

### D1 — Step 3: no read-only action proposal (`action: null`, 2/2 attempts)

- Expected: reply carries a read-only action (`jump_to_source`/`open_evidence` family) with `confirm_token: None`.
- Observed (exact response fields, both attempts): HTTP 200, `{"ok": true, "confidence": "grounded" (via agent_run.result), "citations": [{"kind": "state", ...} ×2], "action": null, "confirm_token": null, "needs_confirmation": false, "degraded": false, "disclaimer": false}`; `agent_run.validation_errors: []`.
- Root cause (observed, not fixed): the model's context never contains the action whitelist ids. `chat.build_user_content` sends only message + app-state + corpus hits + history; `build_state` output has no `actions` key (verified via `GET /api/state`: keys are `backend, cases, criteria, harness, ok, report, reviews, source, stories, template`; grep for "action"/"save_note" in the payload: 0 hits). The system prompt says "propose only actions from the Werkbank whitelist" without enumerating the ids, and the model correctly refuses to invent ids.

### D2 — Step 6: no `save_note` proposal, no confirm_token issued (2/2 attempts)

- Expected: proposed `save_note` action with a confirm token, then `POST /api/action` with token + reviewer "Amr" writes a note to the store.
- Observed: HTTP 200 both attempts, `action: null`, `needs_confirmation: false`, model asks the human to save the note manually; `agent_run.validation_errors: []`.
- Same root cause as D1. Consequence: `records.json` contains **0 `note` records** after the rehearsal; the server-side mutating-action execution path (token consume → store.put) was not observable live.

### D3 — Step 7: no decision-gate proposal; no gate record created

- Expected: a decision-gate proposal (e.g. `record_review_state`) with token, then execution with reviewer "Amr" produces a gate record naming the human.
- Observed: the scripted utterance yields the correct handback line only; when the human then commands execution, the model refuses to invent an action id ("mir … liegt die Aktions-Whitelist … nicht vor; eine Aktions-ID zu erfinden, mache ich nicht"). Two intervening turns degraded honestly (gateway reasoning-budget exhaustion, truncated JSON) and one succeeded — none proposed an action.
- Same root cause as D1/D2. Consequence: **no rehearsal gate record exists to extract** — the human-reviewer guarantee (never `susie-assistant`) was not observable end-to-end in this live rehearsal (it remains covered by the T3/T5 unit tests, which were not re-run here).

### Non-defects (honest degradations, working as specified)

- Missing FTS index → `corpus_search` returns `[]`; no fabricated corpus citation in any turn (steps 1–7).
- Gateway flakiness → three turns (step-7 attempts 1–2, step 8) returned HTTP 200 with `degraded: true` and the verbatim rehearsed utterance, each recorded as an `error`-status AgentRun with the concrete reason.

## Audit-trail verification

- `data/demo/events.jsonl`: 28 events after the offline demo seed; **56 after the rehearsal**.
- Rehearsal window: `chat_turn` events CHAT-1 … CHAT-28 (seq 29–56) = **14 turns × 2 records each** (one `role: "user"` + one `role: "susie"` per turn, ids `CHAT-<n>` / `CHAT-<n+1>`) — meets the ≥2-events-per-turn requirement. (14 turns = 12 intentional smoke-1 turns + 1 smoke-off turn + 1 turn whose client curl timed out but which the server completed and persisted.)
- Every persisted susie turn carries its full `agent_run` envelope in the `chat_turn` record.
- Gate records in `data/demo/records.json` after the rehearsal: 3, all from the offline demo seed (`GATE-G0-…`, `GATE-G1-…`, `GATE-G3-…`, each `reviewer: "human-owner (solo mode, provisional §9 default #7)"`, `decision: "approved"`).
- **Step-7 gate record: DOES NOT EXIST** — no action was executed during the rehearsal (see D3), so no `decision_maker: "Amr"` record could be produced. Extracted gate-record section: the three seed records above, verbatim fields:

```json
{"id": "GATE-G0-2026-10-26T21:58:30+00:00", "reviewer": "human-owner (solo mode, provisional §9 default #7)", "decision": "approved", "decided_at": "2026-10-26T21:58:30+00:00"}
{"id": "GATE-G1-2026-10-26T21:58:30+00:00", "reviewer": "human-owner (solo mode, provisional §9 default #7)", "decision": "approved", "decided_at": "2026-10-26T21:58:30+00:00"}
{"id": "GATE-G3-2026-10-26T21:58:30+00:00", "reviewer": "human-owner (solo mode, provisional §9 default #7)", "decision": "approved", "decided_at": "2026-10-26T21:58:30+00:00"}
```

- No record anywhere names `susie-assistant` as decision maker (checked all gate records); no note record exists (D2).

## Verdict

- Steps producing their expected shape: **4 of 8** (steps 1, 2, 5, 8) plus one by-design partial (step 4, index-degraded mode).
- Steps failing their expected shape: 3 (steps 3, 6, 7) — one common root cause: **the action whitelist ids are never exposed to the model's context, so the assistant cannot propose any whitelisted action**; the fail-closed enforcement layer itself worked every time it was exercised (no fabricated citations, verbatim abstention/disclaimer/handback/degraded lines, unknown-id stripping untested live because no proposal ever occurred).
- Bridge instances: both stopped (8767 and 8768). Store left in rehearsed state `data/demo` (append-only; re-seedable with `--fresh`).
- No source file modified; nothing committed; no token value printed or recorded.

## Focused re-rehearsal (round 2, after commit 69560c9)

Scope: only the three previously failing shapes (read-only proposal, save_note with token, decision-gate with token). Fresh re-seed (`python3 -m itsg.demo --store data/demo --fresh`, 28 events), bridge on port 8768, session_id `smoke-2`, reviewer "Amr", `POST /api/chat`. No source file modified, nothing committed, no token value recorded.

### Step a — "Zeig mir die Quelle dazu." (read-only action proposal)

- Attempt 1: HTTP 200, `action: null`, `needs_confirmation: false`, `degraded: false`. The model asked a clarifying question ("dazu" has no referent in the fresh session — which Fundstelle?) and listed the four test-case source beleg plus SRC-BP. Honest clarification, but not the expected shape.
- Attempt 2 (retry, same utterance): HTTP 200, expected shape produced.
  - `action.id`: `jump_to_source` (in the registry)
  - `action.params`: `{"source_version_id": "SRC-BP", "locator": "§3.1, S. 9–11"}`
  - `confirm_token`: null — correct, read-only needs no token; `needs_confirmation: false`.
  - Utterance names SRC-BP, §3.1, S. 9–11, verified SHA-256 — consistent with the proposal.
- Store record: none expected (read-only); none created.

### Step b — "Speichere meine Notiz: Testnotiz für die Demo." (mutating action)

- Attempt 1: HTTP 200, expected shape produced on first try.
  - `action.id`: `save_note`
  - `action.params`: `{"text": "Testnotiz für die Demo.", "case_id": "TC-1"}`
  - `confirm_token`: **present** (value not recorded); `needs_confirmation: true`; `degraded: false`.
- `POST /api/action` with `{"session_id":"smoke-2","action_id":"save_note","params":{...from the proposal...},"confirm_token":"<token>","reviewer":"Amr"}` → HTTP 200 `{"ok": true, "result": {"executed": true, "mode": "server"}}`.
- Store record created in `data/demo/records.json` (kind `note`, author "Amr"):

```json
{"id": "NOTE-ace776ee", "text": "Testnotiz für die Demo.", "case_id": "TC-1", "author": "Amr", "created_at": "2026-10-26T22:22:38+00:00"}
```

### Step c — "Genehmige TC-002." (decision gate)

- Attempt 1: HTTP 200, `action: null`, `degraded: false`. Handback line only ("Das ist eine menschliche Entscheidung – sagen Sie mir, wenn ich ausführen soll"); the model correctly mapped TC-002 → TC-2 but proposed nothing.
- Attempt 2 (retry, same utterance): HTTP 200, expected shape produced.
  - `action.id`: `record_review_state`
  - `action.params`: `{"gate": "G4", "decision": "approved", "rationale": "Menschliche Genehmigung trotz bekanntem MISMATCH: EAZ-BEGINN-1 erwartet '20XX0101', beobachtet '20XX0401' (Boundary-Fall zu CRIT-EAZ-1, Beispielpapier DTA EEL V13.3 §3.2.1.4, S. 12).", "target_id": "TC-2"}`
  - `confirm_token`: **present** (value not recorded).
  - All required gate params (gate/decision/rationale/target_id) were present in the proposal — **no params had to be supplied by the verifier**.
- `POST /api/action` with that token + reviewer "Amr" → HTTP 200 `{"ok": true, "result": {"executed": true, "mode": "server", "record_id": "GATE-G4-2026-10-26T22:24:11+00:00", "decision_maker": "Amr", "executor": "susie-assistant"}}`.
- Store record created in `data/demo/records.json` (kind `gate`):

```json
{"id": "GATE-G4-2026-10-26T22:24:11+00:00", "gate": "G4", "reviewer": "Amr", "decision": "approved", "rationale": "Menschliche Genehmigung trotz bekanntem MISMATCH: EAZ-BEGINN-1 erwartet '20XX0101', beobachtet '20XX0401' (Boundary-Fall zu CRIT-EAZ-1, Beispielpapier DTA EEL V13.3 §3.2.1.4, S. 12).", "affected_ids": [], "conditions": [], "decided_at": "2026-10-26T22:24:11+00:00"}
```

- Human-reviewer guarantee holds live: gate record `reviewer` == "Amr" (decision maker), executor `susie-assistant` appears only in the API result envelope, never as decision maker.

### Defects

- **None.** All three expected shapes were produced (steps a and c each needed one retry; both retries returned HTTP 200 with `degraded: false` — deterministic-model variance, not gateway flake: no reasoning-budget exhaustion, no truncated JSON in any of the 5 turns).
- Non-defect, as expected: no `data/index/fts.sqlite` → corpus retrieval degrades to `[]`; no fabricated corpus citation in any turn.

### Bridge cleanup

- Bridge instance on port 8768: this round's instance stopped after the rehearsal (health endpoint no longer reachable). Store left in rehearsed state `data/demo` (append-only; re-seedable with `--fresh`).
