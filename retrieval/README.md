# Retrieval: ask a question, get a checked answer

For the UI team (Oussama, Houssem). Owner: Fares (Member 2). Task T10-004.

You give it a question in German or English. It finds the best matching chunks in `chunks/`,
asks the hessian.AI model, checks every quote the model gives, and returns a result you can show.

## 1. Set up the key

1. Create a file called `.env` in the repository root (next to `README.md`).
2. Put one line in it:

   ```
   HESSIAN_API_KEY=your-key-here
   ```

3. `.env` is in `.gitignore`. Never commit it, never paste the key in chat or code.
   You can also set `HESSIAN_API_KEY` as a normal environment variable; the real variable wins over `.env`.

If the key is missing, `ask()` raises `MissingApiKeyError` with the message "HESSIAN_API_KEY is not set".
Show that to the user as a setup problem, not as an answer.

Install the packages with `pip install -r retrieval/requirements.txt`.

## 2. Call it from Python

Run from the repository root:

```python
from retrieval.ask import ask

result = ask("Was muss bei einer Stornierung (Abgabegrund 88) immer gefuellt werden?")
print(result.status)
print(result.answer)
for c in result.citations:
    print(c.chunk_id, c.section, c.page, c.match_level, c.quote)
```

`result` is a pydantic object. `result.model_dump()` gives a plain dict and `result.model_dump_json()` gives JSON.

## 3. Call it from the command line

```
python retrieval/ask.py "Wann wird der Abgabegrund 41 verwendet?"
```

It prints one log line (the audit record) and then the result as JSON.
If you give no question it uses the Abgabegrund 41 example.

## 4. What you get back

```json
{
  "answer": "text of the answer",
  "status": "ANSWERED",
  "citations": [
    {
      "chunk_id": "GG_EEL/2.5",
      "section": "2.5",
      "page": 13,
      "quote": "word-for-word text from the chunk",
      "match_level": "exact"
    }
  ],
  "validation_errors": [],
  "audit": {
    "run_id": "RUN-...",
    "timestamp": "2026-10-26T20:09:48+00:00",
    "provider": "hessian.ai",
    "model_id": "vllm/GLM-Flash:Latest",
    "model_revision": "reported by the API, or \"unavailable\"",
    "prompt_contract_version": "retrieval-qa-v1",
    "input_ids": ["chunk ids that were sent to the model"],
    "status": "ANSWERED",
    "validation_error_count": 0,
    "attempts": 1,
    "response_format_json_object": true
  }
}
```

| Field | Meaning |
|---|---|
| `answer` | The model's answer text. For failures it is a fixed message (see below). |
| `status` | `ANSWERED`, `NEEDS_REVIEW` or `NOT_FOUND`. Always check this first. |
| `citations` | The sources behind the answer. Each has `chunk_id`, `section`, `page`, `quote` and `match_level`. |
| `citations[].match_level` | `"exact"`, `"table"` or `null`. `null` means the quote was rejected. |
| `validation_errors` | List of text messages. Empty means every check passed. |
| `audit` | Who answered, which chunks went in. It holds no question text, no answer text and no key. |

## 5. What each status means and how the UI must show it

| Status | Meaning | UI must |
|---|---|---|
| `ANSWERED` | The model gave an answer, every citation was found in its chunk, and there are no validation errors. | Show as a normal answer, with the citations next to it. |
| `NEEDS_REVIEW` | Something failed: a quote was not found, a section or page was wrong, there were no citations, the model reply was malformed, or the model call failed. Or the model itself said it was unsure. | Show a clear **yellow warning**. **Never** show it like a normal answer. Show `validation_errors` so the reviewer sees why. A human must check it. |
| `NOT_FOUND` | The model says the documents do not contain the answer, or no chunk matched the question. | Show "Not in the documents". Do not show an invented answer. |

Important rules that the code enforces:

- The code can only lower a status (`ANSWERED` to `NEEDS_REVIEW`). It never raises one.
- If the model call fails, or its reply is not valid JSON in the right shape, you get `NEEDS_REVIEW` with a fixed message and an empty `citations` list. This happened in 2 of 3 early live runs, which is why the retries above exist.
- **Retries:** if the model reply is not valid JSON in the required shape, the same request is sent again, up to 3 attempts in total. A reply that parses but has a wrong or missing quote, section or page is **never** retried: it stays `NEEDS_REVIEW` on the first result. Only the final result is returned, and `audit.attempts` says how many calls were made (so the UI can show it). If all 3 attempts are malformed you get `NEEDS_REVIEW` with a fixed message. A failed network call (timeout, auth) is not retried.
- **JSON mode:** the request asks the API for `response_format={"type": "json_object"}`. If the API answers 400/404/422 to that, the request is repeated without it, and `audit.response_format_json_object` is `false`. Replies wrapped in ```` ```json ```` fences are accepted: the fences are removed before parsing.
- `ask()` does not raise for model problems. It only raises `MissingApiKeyError` when there is no key.

## 6. match_level: exact vs table

Every quote the model gives is checked against the chunk it cites.

- `exact`: the quote appears word for word in the chunk (extra spaces and line breaks are ignored).
- `table`: the chunk is a text table where cells are wrapped across lines, so the quote is not contiguous. The code accepted it because all quote words appear in the same order, with at most 4 other words between neighbours, and the quote has at least 6 words.
  **The UI should show a small note: "matched across a table, please spot-check".**
- `null`: not found. The status will be `NEEDS_REVIEW`.

A quote must be at least 15 characters. The checks also need the `chunk_id` to be one of the chunks sent to the model, the `section` to be the chunk's section number (a value like `2.5 Some title` is accepted for chunk `2.5`; `3.1`, `2.50` or text without a number is rejected), and the `page` to be inside the chunk's page range.

## 7. Known limits

- **Keyword search only.** Search is TF-IDF on words, plus a boost for Abgabegrund numbers, Datenbaustein names (like DBSD) and section numbers like `3.1.18` named in the question. It has no embeddings. It handles simple German word endings (for example Stornierung / Stornierungen, Vorerkrankung / Vorerkrankungen) but not synonyms or compound words. It sends the top 5 chunks to the model, so an answer that needs a sixth chunk can be missed.
- **One model.** Only `vllm/GLM-Flash:Latest` on hessian.AI, temperature 0. No second model checks the answer.
- **The quote check proves the quote exists in the chunk. It does not prove the answer is right.** The model can still misread a real quote.
- **No legal approval.** The result is a candidate for a human reviewer. It is not a legal decision and must not be presented as one.
- Search quality was checked on only a few manual questions. There is no benchmark yet.

## 8. Tests

```
python -m pytest retrieval -q
```

These use a fake model, so they need no key and no network. They do not test the live API.
