# SÜSIE the Assistant — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the local `itsg` web bridge with the SÜSIE conversational brain: bilingual LLM chat with two-tier citation discipline, a fail-closed action registry, human-commanded decision gates, and honest degraded modes.

**Architecture:** A new chat module orchestrates each turn — app-state context from the store, corpus retrieval over the FTS5 index, one gateway call via a new `susie_assistant` agent role, deterministic enforcement of the citation/disclaimer rules, and an AgentRun audit envelope per turn. A separate action module owns the whitelisted registry, confirmation tokens, and server-side execution. The existing stdlib `itsg/webserver.py` gains three endpoints. The SÜSIE frontend (action bus, two surfaces) is built by the frontend team against the spec's contract — **not part of this plan**.

**Tech Stack:** Python 3 stdlib only (http.server, sqlite3/FTS5 via existing `pipeline.index`, urllib gateway client, unittest).

**Spec:** `docs/superpowers/specs/2026-10-26-susie-assistant-design.md`

## Global Constraints

- Stdlib only; no new dependencies. Tests: `python3 -m unittest` (repo standard, not pytest).
- Server binds 127.0.0.1 only; LLM token only via `SUSIE_LLM_TOKEN` env or `itsg.secrets` encrypted store — never in source, tests, fixtures, or logs.
- Fail closed everywhere: unknown action → refused; grounded claim without citation → abstain; missing index → no corpus claims; gateway down → structured degraded reply; no fabrication, no silent fallback.
- No agent approves: every gate decision requires a named human reviewer; SÜSIE's author identity (`susie-assistant`) can never be a reviewer (author ≠ reviewer).
- Chat surface language: mirror the user (DE/EN), formal **Sie** register in German. Abstain copy verbatim: "Das kann ich nicht belegen." Disclaimer copy verbatim: "Das steht nicht in meinem Datensatz."
- Work on a new branch off `main` (current branch `amourification/pdf-chunking` is unrelated). Commit steps below assume the human owner's authorization recorded in the board claim (AGENTS.md requires it); without it, stop at the verification step and report.
- Board: claim the work-order ID and file ownership on `.leapfrog/board.md` before Task 1.

## Review Focus

1. **Grounded claim without citation** — a model reply claiming `confidence: "grounded"` with an empty citations list must come back to the user as the verbatim abstain line, never as a confident answer. Test in Task 4.
2. **Unregistered or tampered action** — an action id outside the registry, or a mutating/gate execution without a valid unexpired confirmation token, must be refused, not approximated. Tests in Task 3.
3. **Gate without a named human** — a decision-gate execution with an empty/blank reviewer name must raise, and the recorded decision must never carry `susie-assistant` as reviewer. Test in Task 3.
4. **Missing or empty index** — with no index database or zero accepted versions, corpus retrieval returns nothing and the chat still works with app-state citations only; no fabricated corpus citation may appear. Tests in Tasks 2 and 4.
5. **Gateway unreachable mid-demo** — `POST /api/chat` must return HTTP 200 with the structured degraded reply (rehearsed message, manual path offered), never a 500 the frontend can't converse with. Test in Task 5.

---

### Task 1: `susie_assistant` agent role + public chat completion

**Files:**
- Modify: `itsg/candidates.py` (role constants block, `ROLES`, `ROLE_GATES`)
- Modify: `itsg/llm.py` (model constants, `ROLE_MODELS`, new public function)
- Test: `tests/test_candidates.py`, `tests/test_secrets_llm.py`

**Interfaces:**
- Consumes: existing `AgentRun`, `new_run`, `_chat` transport in `itsg/llm.py`.
- Produces: `candidates.ROLE_SUSIE_ASSISTANT = "susie_assistant"`; `llm.MODEL_ASSISTANT = "vllm/GLM-Flash:Latest"`; `llm.ROLE_MODELS[ROLE_SUSIE_ASSISTANT]`; `llm.chat_completion(endpoint: str, model: str, system_prompt: str, messages: list[dict], token: str, timeout: int = TIMEOUT_S) -> str` where `messages` is `[{"role": "user"|"assistant", "content": str}, ...]`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_candidates.py`:

```python
def test_susie_assistant_role_is_registered_and_gate_free(self):
    from itsg import candidates
    self.assertIn(candidates.ROLE_SUSIE_ASSISTANT, candidates.ROLES)
    self.assertIsNone(candidates.ROLE_GATES[candidates.ROLE_SUSIE_ASSISTANT])
    run = candidates.new_run(
        candidates.ROLE_SUSIE_ASSISTANT, "T10-032", "hessian-ai-vllm-gateway",
        "vllm/GLM-Flash:Latest", [], result={}, author="susie-assistant",
    )
    self.assertEqual(run.role, "susie_assistant")
    self.assertTrue(run.review_required)
```

In `tests/test_secrets_llm.py`:

```python
def test_chat_completion_refuses_private_endpoint():
    from itsg import llm
    with self.assertRaises(llm.LLMError):
        llm.chat_completion("http://127.0.0.1:9/v1", "m", "sys",
                            [{"role": "user", "content": "hi"}], token="t")

def test_assistant_role_maps_to_glm_flash():
    from itsg import llm, candidates
    self.assertEqual(
        llm.ROLE_MODELS[candidates.ROLE_SUSIE_ASSISTANT], "vllm/GLM-Flash:Latest")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_candidates tests.test_secrets_llm -v`
Expected: FAIL/ERROR — `AttributeError: ROLE_SUSIE_ASSISTANT` / `chat_completion` missing.

- [ ] **Step 3: Implement**

- `candidates.py`: add `ROLE_SUSIE_ASSISTANT = "susie_assistant"`, include it in `ROLES`, add `ROLE_GATES[ROLE_SUSIE_ASSISTANT] = None` (recommendation-only: the assistant never owns a gate — the human does).
- `llm.py`: add `MODEL_ASSISTANT = "vllm/GLM-Flash:Latest"` and the `ROLE_MODELS` entry; refactor `_chat` so the transport loop (validate_endpoint → payload → opener.open with `_NoRedirects` → two-stage max_tokens retry) is shared, and add public `chat_completion(endpoint, model, system_prompt, messages, token, timeout=TIMEOUT_S) -> str` that sends `messages` after the system prompt. `_chat` becomes a two-message wrapper over the shared transport.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests.test_candidates tests.test_secrets_llm -v`
Expected: PASS, including all pre-existing tests in both files.

- [ ] **Step 5: Commit**

```bash
git add itsg/candidates.py itsg/llm.py tests/test_candidates.py tests/test_secrets_llm.py
git commit -m "feat(itsg): add susie_assistant agent role and public chat completion"
```

---

### Task 2: Corpus retrieval wrapper with honest degradation

**Files:**
- Create: `itsg/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `pipeline.index.fts.open_db`, `pipeline.index.query.search(conn, query, accepted_versions, limit)` returning `SearchResult` rows; `itsg.store.Store`.
- Produces: `retrieval.accepted_version_ids(store_root: Path) -> set[str]` (source records with `status == "approved"`); `retrieval.corpus_search(store_root: Path, index_path: Path, query: str, limit: int = 5) -> list[dict]`, each dict `{"source_version_id", "segment_id", "heading_path", "title", "text", "page_start", "page_end"}`. Returns `[]` (never raises) when the index file is missing, unreadable, the query is invalid, or the accepted set is empty.

- [ ] **Step 1: Write the failing tests**

```python
class RetrievalTests(unittest.TestCase):
    def setUp(self):  # build in-memory-shaped fixture: temp store + temp index file
        # store root with one approved source SRC-BP and one needs_review SRC-X
        # index db via pipeline.index.fts.open_db(tmp/index.sqlite) + insert_segment
        #   two segments (one per version) from pipeline.segmenter.models.Segment
    def test_only_accepted_versions_are_served(self):
        hits = retrieval.corpus_search(store, index, "Fehlzeit")
        self.assertEqual([h["source_version_id"] for h in hits], ["SRC-BP"])
    def test_missing_index_degrades_to_empty(self):
        self.assertEqual(retrieval.corpus_search(store, tmp / "nope.sqlite", "Fehlzeit"), [])
    def test_no_accepted_versions_returns_empty(self):
        self.assertEqual(retrieval.corpus_search(empty_store, index, "Fehlzeit"), [])
    def test_invalid_query_returns_empty_not_error(self):
        self.assertEqual(retrieval.corpus_search(store, index, '"unbalanced'), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_retrieval -v`
Expected: FAIL — `ModuleNotFoundError: itsg.retrieval`.

- [ ] **Step 3: Implement `itsg/retrieval.py`**

Thin wrapper exactly per the Produces contract. `corpus_search` catches `sqlite3.Error`, `ValueError` (invalid FTS query), and a missing `index_path` → `[]`. No index build here — T10-006 lands separately; this module only reads.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_retrieval -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add itsg/retrieval.py tests/test_retrieval.py
git commit -m "feat(itsg): accepted-only corpus retrieval wrapper with degradation"
```

---

### Task 3: Fail-closed action registry

**Files:**
- Create: `itsg/actions.py`
- Test: `tests/test_actions.py`

**Interfaces:**
- Consumes: `itsg.store.Store`, `itsg.gates.GateDecision`/`GATE_IDS`/`DECISIONS`, `itsg.demo.run_demo` (lazy import).
- Produces:
  - `READ_ONLY_ACTIONS = ("select_case", "open_evidence", "filter_cases", "jump_to_source", "show_comparison", "switch_mode")`
  - `MUTATING_ACTIONS = ("save_note", "export_report", "run_comparison", "initiate_review_flow")`
  - `DECISION_GATE_ACTIONS = {"record_review_state": {"G4", "G5"}, "record_conformance": {"G5"}, "request_release": {"G6"}}`
  - `propose(action_id: str, params: dict, session_id: str) -> dict` — returns `{"action": {"id", "params"}, "confirm_token": None}` for read-only; for mutating/gate returns a random `confirm_token` and remembers `(payload, session_id, expiry=now+300s)`. Unknown id raises `ValueError`.
  - `execute(action_id: str, params: dict, confirm_token: str | None, store_root: Path, reviewer: str) -> dict`
    - read-only → `{"executed": True, "mode": "client"}` (the frontend action bus performs it; the call is audit-logged by the caller).
    - mutating → token must match a pending, unexpired token for that action+session, else `PermissionError`.
    - decision-gate → token **and** non-blank `reviewer`, else `PermissionError`; `gate` param must be in the action's allowed set, `decision` in `gates.DECISIONS`; records `GateDecision(...).to_dict()` via `store.put("gate", ...)`; result includes `decision_maker: reviewer, executor: "susie-assistant"`.
    - `save_note` → `store.put("note", {"id": f"NOTE-{uuid4().hex[:8]}", "text", "case_id", "author": reviewer, "created_at"})`.
    - `export_report` → returns `{"report": store.all("report"), "cases": ..., "notes": store.all("note"), "gates": store.all("gate"), "generated_by": reviewer, "executed_by": "susie-assistant"}`.
    - `run_comparison` → lazy `from . import demo; demo.run_demo(store_root, live=False, fresh=False)`, returns `{"executed": True, "mode": "server"}`.

- [ ] **Step 1: Write the failing tests**

```python
class ActionRegistryTests(unittest.TestCase):
    def test_unknown_action_propose_raises(self):
        with self.assertRaises(ValueError):
            actions.propose("deploy_missiles", {}, "s1")
    def test_read_only_needs_no_token(self):
        out = actions.propose("select_case", {"case_id": "TC-002"}, "s1")
        self.assertIsNone(out["confirm_token"])
    def test_mutating_execution_without_token_refused(self):
        with self.assertRaises(PermissionError):
            actions.execute("save_note", {"text": "x"}, None, self.store_root, "Amr")
    def test_mutating_execution_with_token_writes_note(self):
        tok = actions.propose("save_note", {"text": "Notiz", "case_id": "TC-002"}, "s1")["confirm_token"]
        out = actions.execute("save_note", {"text": "Notiz", "case_id": "TC-002"}, tok, self.store_root, "Amr")
        self.assertTrue(any(n["text"] == "Notiz" for n in Store(self.store_root).all("note")))
    def test_expired_token_refused(self):  # monkeypatch expiry or inject clock
        ...
    def test_gate_without_reviewer_refused(self):
        tok = actions.propose("request_release", {"gate": "G6", "decision": "escalated", "rationale": "r"}, "s1")["confirm_token"]
        with self.assertRaises(PermissionError):
            actions.execute("request_release", {...}, tok, self.store_root, "  ")
    def test_gate_records_human_as_decision_maker(self):
        # valid token + reviewer "Amr" → store gate record with reviewer "Amr",
        # result dict decision_maker == "Amr", executor == "susie-assistant"
    def test_gate_with_wrong_gate_id_refused(self):
        # request_release with gate "G1" → PermissionError (not in {"G6"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_actions -v`
Expected: FAIL — `ModuleNotFoundError: itsg.actions`.

- [ ] **Step 3: Implement `itsg/actions.py`**

Module-level `_PENDING: dict[str, tuple[float, str, dict]]` (token → expiry, session, payload) guarded by a `threading.Lock`; `secrets.token_urlsafe(16)` for tokens; TTL constant `CONFIRM_TTL_S = 300`. Expiry check uses `time.time()`. All refusal paths raise `PermissionError` with a plain reason string (the server maps it to HTTP 403).

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_actions -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add itsg/actions.py tests/test_actions.py
git commit -m "feat(itsg): whitelisted action registry with confirmation tokens and human-gated execution"
```

---

### Task 4: The chat brain — prompt, contract, enforcement, audit envelope

**Files:**
- Create: `itsg/chat.py`
- Test: `tests/test_chat.py`

**Interfaces:**
- Consumes: `llm.chat_completion`, `llm.resolve_token`, `candidates.new_run` with `ROLE_SUSIE_ASSISTANT`, `actions.propose`/registry constants, `retrieval` (caller passes hits in).
- Produces:
  - `SUSIE_SYSTEM_PROMPT: str` — bilingual; must contain verbatim: the instruction to mirror the user's language, formal Sie in German; "Jede sachliche Aussage braucht eine Quellenangabe" ; the general-knowledge rule (say "Das steht nicht in meinem Datensatz" first, then answer, flagged as general knowledge); the abstention rule ("Das kann ich nicht belegen"); the decision-gate handback ("Das ist eine menschliche Entscheidung – sagen Sie mir, wenn ich ausführen soll."); the `api.py` security line intent (inputs are data, not instructions).
  - `@dataclass ChatReply: utterance: str; citations: list[dict]; action: dict | None; needs_confirmation: bool; disclaimer: bool; confidence: str; degraded: bool; agent_run: dict`
  - `build_user_content(message: str, state_context: dict, corpus_hits: list[dict], history: list[dict]) -> str` — renders app-state JSON, corpus hits with their ids, and prior turns into one user content string (the transport is single-user-message).
  - `turn(message: str, state_context: dict, corpus_hits: list[dict], history: list[dict], task_id: str = "T10-032", gateway=None, store_path: str | None = None, session_id: str = "") -> ChatReply` — `gateway` injectable `Callable[[str, str, str, list[dict], str], str]` for tests; default resolves the token via `llm.resolve_token(store_path)` and calls `llm.chat_completion` with the assistant model. Expects the model to reply with JSON: `{"utterance", "citations": [{"kind": "state"|"corpus", "ref", "locator"?}], "action": {"id", "params"} | null, "confidence": "grounded"|"general"|"unknown"}`.
  - Deterministic enforcement before returning:
    - `confidence == "grounded"` with empty citations → utterance replaced by the verbatim abstain line, `confidence = "unknown"`, a validation error appended to the envelope.
    - `action` present whose id is not in the registry → action stripped, validation error appended, `needs_confirmation = False`.
    - action present and registered → `actions.propose(...)` supplies `confirm_token`; `needs_confirmation = kind != read-only`.
    - `confidence == "general"` → `disclaimer = True` (forced, whatever the model said).
    - gateway `LLMError` → degraded reply: rehearsed utterance "Meine Verbindung zum Wissensdienst ist unterbrochen – ich kann Sie aber manuell durch die Schritte führen.", `degraded = True`, envelope status `"error"`.
  - Every turn returns an `agent_run` dict from `new_run(role=ROLE_SUSIE_ASSISTANT, ..., result={"utterance", "confidence", "degraded"}, citations=[{source_version_id, locator} for kind=="corpus"], input_ids=[citation refs], author="susie-assistant")` — `review_required=True` stands; chat display is not blocked by it (spec).

- [ ] **Step 1: Write the failing tests**

```python
def _gw(reply_json: str):
    return lambda *a, **k: reply_json

GROUNDED = json.dumps({"utterance": "TC-002 weicht ab, weil …", "confidence": "grounded",
    "citations": [{"kind": "state", "ref": "TC-002"}], "action": None})
GROUNDED_NO_CITE = json.dumps({"utterance": "Sicher gilt …", "confidence": "grounded",
    "citations": [], "action": None})
GENERAL = json.dumps({"utterance": "Allgemein gilt …", "confidence": "general",
    "citations": [], "action": None})
PROPOSES = json.dumps({"utterance": "Soll ich TC-002 öffnen?", "confidence": "grounded",
    "citations": [{"kind": "state", "ref": "TC-002"}],
    "action": {"id": "open_evidence", "params": {"case_id": "TC-002"}}})
HALLUCINATES_ACTION = json.dumps({"utterance": "Erledigt.", "confidence": "grounded",
    "citations": [], "action": {"id": "wipe_store", "params": {}}})

class ChatTurnTests(unittest.TestCase):
    def test_grounded_with_citation_passes(self):
        r = chat.turn("Warum weicht TC-002 ab?", {}, [], [], gateway=_gw(GROUNDED))
        self.assertEqual(r.utterance, "TC-002 weicht ab, weil …")
        self.assertFalse(r.disclaimer); self.assertFalse(r.degraded)
    def test_grounded_without_citation_is_forced_to_abstain(self):
        r = chat.turn("…", {}, [], [], gateway=_gw(GROUNDED_NO_CITE))
        self.assertIn("Das kann ich nicht belegen", r.utterance)
        self.assertEqual(r.confidence, "unknown")
        self.assertTrue(r.agent_run["validation_errors"])
    def test_general_knowledge_forces_disclaimer_flag(self):
        r = chat.turn("…", {}, [], [], gateway=_gw(GENERAL))
        self.assertTrue(r.disclaimer)
    def test_registered_action_gets_confirmation_token(self):
        r = chat.turn("…", {}, [], [], gateway=_gw(PROPOSES))
        self.assertEqual(r.action["id"], "open_evidence")
        self.assertFalse(r.needs_confirmation)  # read-only
    def test_mutating_action_needs_confirmation(self):  # save_note variant → True + token
    def test_unregistered_action_is_stripped(self):
        r = chat.turn("…", {}, [], [], gateway=_gw(HALLUCINATES_ACTION))
        self.assertIsNone(r.action)
    def test_gateway_failure_is_degraded_not_fatal(self):
        def boom(*a, **k): raise llm.LLMError("down")
        r = chat.turn("…", {}, [], [], gateway=boom)
        self.assertTrue(r.degraded)
        self.assertIn("Wissensdienst", r.utterance)
    def test_every_turn_carries_agent_run_envelope(self):
        r = chat.turn("…", {}, [], [], gateway=_gw(GROUNDED))
        self.assertEqual(r.agent_run["role"], "susie_assistant")
        self.assertTrue(r.agent_run["review_required"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_chat -v`
Expected: FAIL — `ModuleNotFoundError: itsg.chat`.

- [ ] **Step 3: Implement `itsg/chat.py`**

Prompt per the Produces contract (bilingual, all verbatim rules present). Reply parsing via `llm.extract_json_payload` + `json.loads`; any parse failure counts as a gateway failure → degraded reply. Enforcement order: parse → validate citations → validate action via `actions.propose` → force disclaimer/abstain → build envelope. Keep the module under ~200 lines; prompt text may live in a module-level constant block.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_chat -v`
Expected: PASS (8+ tests).

- [ ] **Step 5: Commit**

```bash
git add itsg/chat.py tests/test_chat.py
git commit -m "feat(itsg): SÜSIE chat turn with citation enforcement and audit envelope"
```

---

### Task 5: Web endpoints — chat, action, history, degraded mode

**Files:**
- Modify: `itsg/webserver.py` (handler `do_POST`/`do_GET`, module constants)
- Modify: `tests/test_webserver.py`

**Interfaces:**
- Consumes: `chat.turn`, `chat.ChatReply`, `actions.execute`, `retrieval.corpus_search`, `webserver.build_state`, `Store` for history.
- Produces:
  - `POST /api/chat` body `{"session_id", "message", "reviewer": ""}` → assembles `state_context = build_state(self.store_root)`, `corpus_hits = retrieval.corpus_search(self.store_root, self.index_path, message)`, history from the store, calls `chat.turn(...)`, persists one `chat_turn` record per side via `store.put("chat_turn", {"id": f"CHAT-{n}", "session_id", "role": "user"|"susie", "utterance"/"message", "at", "agent_run"?})` — user turn and assistant turn as separate records, so the append-only event log carries the full audit. Responds `{"ok": True, "utterance", "citations", "action", "confirm_token", "needs_confirmation", "disclaimer", "degraded", "agent_run"}`. Gateway failure still HTTP 200 with `degraded: true` (Review Focus #5).
  - `POST /api/action` body `{"session_id", "action_id", "params", "confirm_token", "reviewer"}` → `actions.execute(...)`; `PermissionError` → HTTP 403 `{"ok": False, "error": reason}`; success → `{"ok": True, "result"}`. Result dict of `export_report` served inline (frontend turns it into a download).
  - `GET /api/chat/history?session_id=...` → `{"ok": True, "turns": [...]}` ordered by id.
  - New `--index` CLI arg (default `data/index/fts.sqlite`), stored on the handler class like `store_root`.

- [ ] **Step 1: Write the failing tests**

Follow the existing `tests/test_webserver.py` pattern (spawn handler against a temp store). Add:

```python
def test_chat_endpoint_returns_envelope_and_persists_history(self):
    # monkeypatch itsg.webserver chat turn pathway (inject fake gateway at module level)
    # POST /api/chat {"session_id": "s1", "message": "Wo stehe ich?"}
    # assert 200, payload["agent_run"]["role"] == "susie_assistant",
    # and GET /api/chat/history?session_id=s1 → 2 turns (user + susie)
def test_chat_endpoint_degraded_when_gateway_down(self):
    # fake gateway raises LLMError → 200, payload["degraded"] is True
def test_action_endpoint_refuses_missing_token(self):
    # POST /api/action save_note without token → 403
def test_action_endpoint_executes_with_token(self):
    # propose via actions.propose → execute through endpoint → note in store, 200
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m unittest tests.test_webserver -v`
Expected: FAIL — 404 on the new endpoints.

- [ ] **Step 3: Implement the endpoints**

Extend `SUSIEHandler.do_POST` with the two routes and `do_GET` with history; keep the existing security posture (JSON only, no credentials in responses — `agent_run` contains none). Inject the chat gateway for tests via a module-level `CHAT_GATEWAY = None` (None → real `chat.turn` default).

- [ ] **Step 4: Run the full suite**

Run: `python3 -m compileall -q pipeline itsg tests && python3 -m unittest discover -s tests -v`
Expected: all PASS, no new warnings.

- [ ] **Step 5: Commit**

```bash
git add itsg/webserver.py tests/test_webserver.py
git commit -m "feat(itsg): SÜSIE chat/action/history endpoints on the local bridge"
```

---

### Task 6: Live smoke rehearsal (no new code)

**Files:**
- Create: `docs/superpowers/plans/2026-10-26-susie-assistant-smoke.md` (checklist, results recorded there)

- [ ] **Step 1: Start the bridge with a seeded store**

Run: `python3 -m itsg.demo data/demo --fresh && python3 -m itsg.webserver --port 8766`
Expected: bridge up on 127.0.0.1:8766.

- [ ] **Step 2: Rehearse the demo arc over HTTP**

`curl` the eight spec steps in order (summary → deviation → jump → Fehlzeiten/EAZ → general-knowledge probe → note+export → "Genehmige TC-002" → gateway-off). Record per step: HTTP status, `confidence`, citations present, `disclaimer`, `needs_confirmation`, `decision_maker` on the gate record. Any step that cannot produce its expected shape is a defect against the spec — file it, do not paper over it.

- [ ] **Step 3: Verify the audit trail**

`data/demo/events.jsonl` must contain one event per chat turn and per executed action, and the gate record from step 7 must name the human reviewer, never `susie-assistant`.

- [ ] **Step 4: Commit the rehearsal record**

```bash
git add docs/superpowers/plans/2026-10-26-susie-assistant-smoke.md
git commit -m "docs: SÜSIE assistant smoke rehearsal record"
```

---

## Self-Review

- **Spec coverage:** two-tier citations + disclaimer (T4), layered fallback + abstain (T4, verbatim copy), action registry + yes/no tokens + GOD-mode gates with human decision-maker (T3, T5), bilingual Sie + language mirroring (T4 prompt), AgentRun envelope per turn (T1, T4), append-only audit persistence (T5), degraded modes for index (T2) and gateway (T4, T5), reviewer onboarding name (T3/T5 `reviewer` field), endpoints (T5), rehearsal (T6). Frontend contract: intentionally absent — frontend team's separate plan per spec.
- **Step scan:** every step names one artifact (test, function with exact signature, command, commit); no TBDs.
- **Type consistency:** `confirm_token` naming consistent across T3/T5; `ChatReply` fields match T5's response keys; `corpus_hits` dict shape matches T2's Produces contract.
- **Review Focus:** each of the five failure modes has its pinning test in the task listed above.
- **Proportion:** plan ≈ spec length; code blocks are tests and signatures only.
