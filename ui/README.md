# Team 10 demo app (UI + server)

The screens the judges see. Built on Oussama's Task 4 skeleton (T10-003) and extended by Fares and Oussama (T10-006).
All data is **synthetic**. No legal compliance claim; the banner at the top says so on every tab.

## Run it

```
pip install -r requirements.txt -r retrieval/requirements.txt    # once
python ui/server.py                                              # then open http://localhost:8000
```

Optional, in a `.env` file in the repository root (or as real environment variables). Never commit `.env`:

| Variable | Used for |
|---|---|
| `HESSIAN_API_KEY` | "Ask the rulebook" |
| `SEAL_URL`, `SEAL_VENDOR_TOKEN`, `SEAL_ADMIN_TOKEN` | "Trust & seal" (the secrets stay on the server, the browser never sees them) |
| `UI_HOST`, `UI_PORT` | Bind address, default `0.0.0.0:8000` |

A part that is not configured shows as **unavailable** on the Overview tab. Nothing is faked.

Opening `ui/index.html` as a file (no server) still works: the page then shows a red **OFFLINE SAMPLE DATA** banner and
Oussama's fabricated examples from `js/data.js`. Sample and real data are never mixed.

Tests: `python -m pytest ui -q` (server, security rules, frontend rules; seal tests use a throwaway seal server).
Docker and wsvm33 deployment: `ui/Dockerfile`, `ui/DEPLOY.md`.

## What each tab shows

| Tab | What it shows | Real data from |
|---|---|---|
| Overview | `figures/system-overview.png`, the problem in one paragraph, the pipeline with live availability and versions | `/api/health` |
| Review report | "Run review" button, counts, findings table (status filter, click an ID for its evidence chain), robustness block (attacks + baseline), review-decision form and history | `run_review.py` → `reports/RPT-*.json`; decisions in `reports/review-events.jsonl` |
| Test cases | 500 cases (300 generated + 200 stories) with search and filters, detail with expected vs observed (differences in red), harness summary and "Run harness" | `data/testcases.json`, `data/story_cases.json`, `harness/run_harness.py` |
| Ask the rulebook | Question box, 3 examples, answer with status, citations (doc/section/page/quote/match level), validation errors, audit | `retrieval.ask.ask()` |
| Trust & seal | "Who checks the vendor?", the vendor-honesty demo (GENUINE → TAMPERED → NEVER SUBMITTED), runs table, honest limits | the seal server |
| Sources & requirements | The sources cited by the latest report's checks, with an "ask the rulebook" shortcut. Oussama's sample source/requirement cards appear only in offline mode | latest report |

Status badges: PASS green · MISMATCH red · NOT EVALUATED gray (never styled like a pass) · NEEDS_REVIEW yellow ·
BLOCKED dark · ANSWERED green · NOT_FOUND gray · GENUINE green · TAMPERED red · NEVER SUBMITTED orange.
A status the page does not know is shown gray, never green.

## The 3-minute demo (matches the demo script in `plan.md`)

1. **Overview (30 s):** read the problem sentence, point at the pipeline: all four parts "available". Banner: synthetic data.
2. **Review report (60 s):** click **Run review**. Show the counts and the findings table; filter on NOT EVALUATED and explain
   that missing evidence never becomes a pass. Click a finding ID: evidence chain report → run → test case → criterion → source.
   Show the robustness block (14/14 planted errors stopped, baseline no false alarm). Record a decision as a human reviewer.
3. **Test cases (30 s):** search `OUT-088`, open it: one red row (AU-AB-AG wrong date), and the harness verdict.
4. **Ask the rulebook (30 s):** click the Stornierung example, **Ask**. Show the checked quote and match level.
5. **Trust & seal (30 s):** **Run vendor-honesty demo**: GENUINE, then TAMPERED after one status was edited, then the run that was never submitted.
6. **Boundary (10 s):** read the honest limits; nothing here certifies software or decides legal meaning.

## Safety rules the code follows

- Every text from a report, test case, AI answer or quote is put on the page with `textContent`; the UI has no `innerHTML`
  (a test checks this). A `<script>` or `<img onerror>` in an AI answer is shown as plain text.
- A `NEEDS_REVIEW` answer is a yellow warning with the model text folded away, never a normal answer.
- Tokens and keys live only in the server environment; no response and no log line contains them (tested).
- Only files under `ui/` (html, js, css) and `figures/` are served; path traversal is blocked. Bodies are limited to 64 KB,
  questions to 500 characters, 10 questions per minute per client. POSTs need a custom header and a matching origin.
- The review decision is an append-only log. The system never approves anything by itself.

## Known limits

- **No login (accepted for the 1-day demo; say so in the pitch).** Anyone with the URL can run reviews, spend API calls (rate-limited) and record decisions under any typed name.
  The reviewer name is not verified, so the decision log is a demo of the human gate, not an audit-grade record.
- The report file never changes after a decision; the decision lives in `reports/review-events.jsonl`.
- The live Sources tab shows only what the report cites. Source records, requirement text and criterion approvals are not part
  of the real data yet.
- The harness covers the 300 generated cases only; story cases (200) are shown, but nothing scores them yet. Their
  expected-vs-observed view is only compared field by field for DBVO outputs.
- "Run review" uses the sample TEEL0 file and test case already in the repository. It does not upload vendor output.
- Ask answers come from one model on keyword-retrieved passages; a verified quote does not prove the answer is right (see `retrieval/README.md`).
- Seal limits are listed on the Trust & seal tab (see `seal/README.md`): a vendor who changes the tool or the output before sealing is not stopped.
- Browser tests: no Playwright is installed here. Manual check list (5 minutes):
  1. Open every tab at 1366 px width; nothing overflows horizontally.
  2. Stop the server, reload: red OFFLINE banner, sample data only, server-only tabs say they need the server.
  3. In the browser console run `showAnswer(document.getElementById("ask-result"), {status:"ANSWERED", answer:"<script>alert(1)</script><img src=x onerror=alert(2)>", citations:[], validation_errors:[], audit:{}})`
     (on the Ask tab): the text appears literally and no alert pops up.
  4. Ask with the key missing: a plain "not set up on this server" message, no stack trace.

## Files

| File | What it is |
|---|---|
| `server.py` | Standard-library HTTP server: static files + JSON API |
| `index.html`, `css/styles.css` | Page shell and styles (Oussama's, extended) |
| `js/app.js` | Tabs, start-up (live or offline), Overview, Sources |
| `js/report.js`, `js/cases.js`, `js/ask.js`, `js/seal.js` | One file per tab |
| `js/util.js`, `js/api.js` | Safe DOM builder, status badges, server calls |
| `js/offline.js`, `js/data.js` | Oussama's sample screens and fabricated records, offline mode only |
| `test_server.py` | Tests |
| `Dockerfile`, `DEPLOY.md` | Container and wsvm33 steps |

## API (all JSON)

`GET /api/health` · `POST /api/review/run` · `GET /api/review/latest` · `GET /api/testcases?source=&group=&category=&kind=&q=&page=&page_size=` ·
`GET /api/testcases/<id>` · `GET /api/harness/latest` · `POST /api/harness/run {limit}` · `POST /api/ask {question}` ·
`POST /api/seal/demo` · `GET /api/seal/runs` · `POST /api/review/decision {reviewer, decision, comment}` · `GET /api/review/decision`
