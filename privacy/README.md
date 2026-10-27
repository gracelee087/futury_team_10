# Datenschutz-Schleuse (privacy airlock)

Task T10-007. Owner: Fares (Member 2). Status: IN_REVIEW. This is engineering, not legal advice.

The airlock is a small program, no AI, standard library only. It finds personal data in text,
replaces it with a label like `PERSON_1`, and checks again before anything leaves the system.
If anything personal is still left, the request is **BLOCKED** and nothing is sent.

## Files

| File | What it does |
|---|---|
| `schleuse.py` | Detectors, `pseudonymize()`, `check_clean()`, `scrub_for_log()`, log filter, policy per destination |
| `leak_test.py` | Plants personal data in 50 made-up records and searches everything that goes out |
| `test_schleuse.py`, `test_leak.py` | Unit tests and the leak test as tests |
| `../retrieval/ask.py` | Uses the airlock before every model call |
| `../retrieval/test_privacy_integration.py` | Tests of the airlock inside `ask()` |

## What counts as personal data (in scope)

| Category | How it is found |
|---|---|
| `VSNR` Versicherungsnummer | 2 digits area + 6 digits birth date DDMMYY + 1 capital letter + 3 digits (like `17241280Q497`). The date part must be a real date. |
| `BBNR` Betriebsnummer | 8 digits, only after the word Betriebsnummer/Betriebsnr/BBNR, or in the header of a DTA record |
| `IBAN` | Pattern, country length and the mod-97 checksum must be right |
| `EMAIL` | Pattern |
| `PHONE` | German and international formats (`069/8700`, `+49 171 1234567`, `(0221) 123456`, after a word like Telefon) |
| `DOB` date of birth | Only after a cue (geboren am, Geburtsdatum, geb.), or when it is the birth date inside a VSNR found in the same text |
| `PERSON` names | Known name fields (`FAMILIENNAME`, `VORNAME`, `NACHNAME`, `Name:` ...), the name blocks of DTA records (`DBNA` family name + first name, `DBAP` contact person, `DSKO` line), and cue words (Herr, Frau, Dr., "Versicherte(r) Vorname Nachname", "mein Name ist"). A name found once is replaced everywhere in the text, also its parts and the genitive ("Meiers"). |
| `ADDRESS` | Street + house number (and `...straße` / `...strasse` names), `Am Mühlenberg 4` style lines, postal code + city |

### What is deliberately NOT treated as personal

- **AU dates** (begin/end of the Arbeitsunfähigkeit, like `20260311`), **Abgabegrund codes**, **DSIDs** (UUIDs),
  **section numbers** (`3.1.18`), Datenbaustein names (`DBVO`). On their own they point to no person.
  They are rule vocabulary or technical ids, and blanking them would destroy the rulebook questions.
- Why AU dates still matter: together with a person they are **health data** (Art. 9 GDPR) and **social data**
  (§ 35 SGB I, social secrecy). That is why the airlock removes the person (VSNR, name, birth date, contact data)
  and leaves the date: without the person it is no longer linked to anyone. Any date that is attached to a person
  must be treated as personal. In this project all such data is fabricated; real data must not be used
  (see `agent-governance.md`).

## Rules per destination (`POLICY`, version `privacy-policy-v1`)

| Destination | Rule |
|---|---|
| `hessian_ai` | Pseudonymize, then `check_clean`. Anything left = BLOCKED, no API call. Allowed otherwise. |
| `langfuse` | Pseudonymize **and** minimize: only a short list of keys (`run_id`, `status`, `check`, `rule`, `source`, `expected`, `scenario`, `count`, `categories`, `policy_version`), strings cut at 200 characters |
| `seal` | Hash only (HMAC-SHA256 with the privacy key). No text goes to the seal. |
| `logs` | No personal data at all. Every hit becomes `[CATEGORY]`; if something is still found the whole line is replaced by `[withheld ...]`. |

Use `apply_policy("<destination>", payload)`. Langfuse is guarded (see below). The seal client already sends only report hashes.

## Langfuse guard (`langfuse_guard.py`, needs review by Sohee)

`run_review.py` and `harness/run_harness.py` belong to Sohee; the changes there are small and commented `T10-007`.
Every payload for Langfuse (span input/output, trace output/metadata, dataset items, scores) goes through
`LangfuseGuard`: minimize (only listed top-level keys, strings cut at 200 characters), pseudonymize, `check_clean`.
A payload that still looks personal is replaced by `[withheld: personal data suspected]`.
`--public` is no longer set when the trace starts: the trace stays private and is made public at the end only if every
payload was clean; otherwise a message says it was refused. Without Langfuse keys nothing changes.
Tests (`test_langfuse_guard.py`) use a fake Langfuse that records everything: the TEEL0 VSNR, names, emails and phone
numbers never appear, and the review findings and counts are the same with and without Langfuse.
Limit: the allowed-key list is hand-made; a new field must be added to it to show up in Langfuse.

## UI tab and retention

- Tab "Datenschutz" (`ui/js/privacy.js`): live preview of what leaves the system, data-flow map with traffic lights built
  from the policy and the server settings, leak-test scorecard (author set and independent set shown separately), a short "why" box.
  Endpoints: `POST /api/privacy/preview` (max 5000 characters, 20 per minute, never returns the original), `GET /api/privacy/flows`,
  `GET /api/privacy/leaktest` (result in `reports/leaktest-latest.json`, made on demand, copy made at Docker build time).
  `BLOCKED` answers from `/api/ask` get their own red card. Needs review by Oussama.
- Retention: `ui/server.py` deletes `RPT-*.json` and `harness-*.json` older than `RETENTION_DAYS` (default 7) at start and daily.
  The seal ledger is not touched. Why this fits the "right to erasure": the ledger holds only hashes and run IDs, no report content, so
  the report (the personal data) can be erased while the ledger stays append-only and verifiable. Whether a keyed hash itself is
  personal data is an open question (see `DPIA.md`). The decision log `review-events.jsonl` (typed reviewer names) is not purged yet.
- `DPIA.md`: one-page draft for ITSG's data-protection officer, not legal advice.

## How tokens work

- `pseudonymize(text_or_record, key)` returns `(clean, summary)`. The summary has counts per category only.
- The same value gets the same token inside one run (`EMAIL_1` every time). Identity is decided with
  HMAC-SHA256 over the normalized value, so the lookup table never holds a raw value as a key.
- The key comes from the environment variable `PRIVACY_KEY` (at least 16 characters, may be in the gitignored `.env`).
  It is never logged. If it is not set, a random key for this process is used (tokens still match inside the run).
  A key that is too short gives BLOCKED.
- `ask()` keeps a token-to-value map **in memory only**, for that one call. The answer shown to the user gets the
  user's own values back (`PERSON_1` -> the name from the question). Tokens that were not in the question stay tokens.
  The map is never written to the audit record or any log.

## What changed in `retrieval/ask.py`

1. The question goes through `pseudonymize` and `check_clean` before search and before the model.
2. Every retrieved chunk goes through `check_clean` (public rulebook text, but same last gate; the rulebook's own
   specimen values such as Mustermann/Max/Musterstraße and printed Betriebsnummern are allowed there).
3. Anything left, or an invalid key: status **`BLOCKED`**, a clear reason, no API call.
4. The audit record has a `privacy` block: `policy_version`, `key_source`, `categories_removed` (counts only),
   `blocked`, and `blocked_categories` when blocked.
5. The `retrieval.ask` logger has a filter that scrubs every message.

The UI shows an unknown status like `BLOCKED` in its "needs human review" box (safe, but not pretty). A proper
`BLOCKED` card is for the UI owner (`ui/` is outside this task).

## Leak test results (measured, `python privacy/leak_test.py`)

Synthetic records only, seeded generator. 50 records mix names, VSNR, IBAN, email, phone, birth dates and
addresses into German sentences and DTA-like fixed-width lines. Each goes through `ask()` with a fake client that
records everything it receives, plus a careless log line, plus the audit record. Then every planted value is
searched (also in spaced/reformatted spellings).

| Measure | Result |
|---|---|
| Records / planted personal values | 50 / 224 |
| **Values that leaked** (model payload, logs, audit) | **0** |
| Records blocked | 0 |
| Extra seeds 1-8 (8 x 50 records, 1837 values) | 0 leaked |
| Stress: 10 names in plain free text, no cue word | **10 of 10 leaked** (known limit, see below) |
| False positives, 50 evenly spaced rulebook chunks | 0 of 50 (strict and specimens allowed) |
| False positives, all 1219 rulebook chunks, strict | 1 chunk (a printed example Betriebsnummer) |
| False positives, all 1219 chunks, specimens allowed (what the gate uses) | 0 |

Also tested: the real `ITSG Files/TEEL0-Test1-DBVO` file. Its VSNR `17241280Q497`, birth date, Betriebsnummer, all
names (Mustermann, Peter, Mia Testfrau), both email addresses and the phone numbers never reach the fake model;
the AU dates and the Abgabegrund field stay (`pytest privacy`).

Commands: `python -m pytest privacy retrieval -q` -> 91 passed. `python privacy/leak_test.py` as above.

### Independent review set (`test_independent.py`)

An independent reviewer (not the author) wrote 10 new records with 19 planted values (`privacy/test_independent.py`,
kept separate from the author's tests).

| Run | Result |
|---|---|
| First run, before any fix | **18 of 19 caught, 1 leaked**: the name "Jonas Bergmann" in `Versicherter: Jonas Bergmann, geb. ...` |
| Cause | Role cue words (Versicherter, Arbeitnehmer, Mitarbeiter ...) followed by a colon were not recognised |
| After the fix (new `_ROLE_COLON` pattern) | 19 of 19 removed |

The 19 of 19 is again a result after a fix made because of these very records, so it is also not independent evidence.
The honest independent number is the first one: 18 of 19 (94.7 %) on a small set. Another reviewer with new records
is still needed.

**Read these numbers carefully.** The first run of the leak test found leaks and blocked 25 of 50 records. I then
fixed the detectors (DTA headers inside logged text, "A=x B=y" name fields, particles like "von", false alarms such as
"eine Frau Mutterschaftsgeld"). So "0 leaked" is **not** an independent result: the detectors were tuned on the same
kind of records the test generates. The extra seeds only change random draws, not the templates. An independent
check needs records written by someone else, ideally with different wording.

## Honest limits

- **Regex detection misses free-text names.** A name without a cue word ("Gestern hat Hans Meier angerufen") is
  not found (10 of 10 leaked in the stress test). Other things it can miss: unusual number formats, typos,
  names inside long compound words, data in images or PDFs, any language other than German/English patterns.
- It can also flag harmless text (a few rulebook words were falsely flagged during tuning and were fixed one by one).
  A false alarm means BLOCKED, which is the safe direction but annoying.
- The DTA name-block positions (`DBNA`, `DBAP`, `DSKO`) come from one sample file (TEEL0), not from the verified
  record layout. If the layout differs, names can be missed.
- **Pseudonymized data is still personal data under GDPR** while someone can link the token back (here: the key
  and the in-memory map). It lowers risk; it does not make the data anonymous.
- Quasi-identifiers (rare job title + small town + AU dates) can still point to a person even without a name.
- `PRIVACY_KEY` management is minimal (an environment variable). No rotation, no vault, no independent security review.
- Only `ask()` and the `retrieval.ask` logger are protected today. Other logs, the UI server log, Langfuse traces in
  `run_review.py` and the seal client do not use the airlock yet.
- The model answer is not re-scanned. It only saw tokens, but a model could invent personal-looking text.
- This is engineering work, not legal advice. Whether a use is allowed under GDPR/SGB needs a qualified human.
