# Seal: the ITSG receipt office (T10-005)

A small service so a software vendor who runs our review tool **on their own computer** cannot quietly
fake, edit or hide results. Python standard library only. Owner: Fares (Member 2).

## The idea in four steps

1. **Before** the review, the vendor's tool asks ITSG for a **run ID**. ITSG writes it into its ledger.
2. The vendor runs the review and gets a report.
3. The vendor sends ITSG only the **fingerprint (SHA-256 hash)** of the report. ITSG answers with a **receipt**,
   signed with a secret key only ITSG has (HMAC-SHA256). The receipt is also written into the ledger.
4. Later, ITSG gets the report and the receipt and checks them: **GENUINE**, **TAMPERED** or **UNKNOWN_RUN**.

The ledger is a file with one JSON line per event. Every line carries a MAC and the hash of the line before it,
so changing or removing an old line breaks the chain and is reported as **LEDGER_TAMPERED**.

## What it protects against

| Attack | What happens |
|---|---|
| Vendor **edits the report** (for example MISMATCH becomes PASS) | The hash no longer matches the receipt: `TAMPERED`. |
| Vendor **hides a failed run** (starts a run, dislikes the result, never submits) | The run ID was issued first, so `GET /runs` (or `verify.py --runs`) shows it as **NEVER SUBMITTED**. |
| Vendor **replays an old good report** for a new run | The receipt belongs to the old run. Submitting the same report hash for a second run is refused (409). Using the old receipt with another report gives `TAMPERED`. |
| Vendor **forges a receipt** or edits one | The MAC cannot be made without ITSG's secret: `TAMPERED`. A made-up run ID gives `UNKNOWN_RUN`. |
| Someone **edits the ledger file** | Each line has a MAC and the hash of the previous line: `LEDGER_TAMPERED`. The server then also accepts no new runs. |

## Honest limits (please read)

- **A vendor who changes the tool itself, or the software output before the check, is NOT stopped.**
  The seal only proves "this report is exactly what was submitted for this run". It does not prove the report is true.
  ITSG spot checks (re-running, looking at the evidence) stay necessary.
- **A vendor can run the tool many times** and only ever submit the best run. The seal makes this visible
  (many runs, few submissions), it does not prevent it. ITSG has to look at the run list.
- **HMAC means only ITSG can verify.** That is by design: the vendor cannot check a receipt on their own. If anyone ever
  needs to verify without ITSG's secret, we would need public-key signatures instead.
- **Whoever has the server, the secret or the ledger can forge anything.** Protect `SEAL_SECRET`, back up the ledger.
  Deleting the last lines of the ledger is only noticed when someone checks a receipt for the deleted run.
- **The demo secrets are throwaway.** This is not production key management: no rotation, no vault, no hardware key.
- **Port 80 is plain HTTP**: the tokens travel unencrypted. Use it only inside a trusted network, or put TLS in front of it.
- No rate limits yet: a vendor with a valid token can create many runs.
- Only the report hash is sent to ITSG, never the report. Nothing here is a legal approval or certification.
- Not tested: behaviour under heavy load, or several server copies sharing one ledger (do not do that).

## Files

| File | Who | What |
|---|---|---|
| `server.py` | ITSG | The HTTP service and the ledger |
| `client.py` | Vendor | `start` and `submit <report.json>` |
| `verify.py` | ITSG | Check a report and receipt, or list all runs |
| `demo.py` | anyone | Full local demo with throwaway secrets |
| `seal_common.py` | both | Canonical JSON, hash and MAC helpers |
| `test_seal.py` | developers | Tests (`python -m pytest seal -q`) |
| `Dockerfile` | ITSG | Container for the server |

Canonical JSON (what is hashed): `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
So key order and spaces in the report file do not matter, but any change of a value does.

## Try it locally

```
python seal/demo.py                      # built-in example report
python seal/demo.py data/some_report.json
python -m pytest seal -q
```

## The service (ITSG side)

Environment variables (the server refuses to start if one of the first three is missing; it never prints them):

| Variable | Meaning |
|---|---|
| `SEAL_SECRET` | HMAC key. Long and random. |
| `SEAL_VENDOR_TOKEN` | Token for the vendor (start and submit) |
| `SEAL_ADMIN_TOKEN` | Token for ITSG (list runs, verify). Different from the vendor token. |
| `SEAL_LEDGER` | Ledger file, default `./seal-data/ledger.jsonl` |
| `SEAL_HOST`, `SEAL_PORT` | Default `127.0.0.1` and `8080` (the Docker image uses `0.0.0.0:8080`) |

Endpoints (token in the header `Authorization: Bearer <token>`, bodies at most 1 MB):

| Request | Token | Purpose |
|---|---|---|
| `POST /runs/start` | vendor | New run ID |
| `POST /runs/<run_id>/submit` with `{"report_sha256": "<64 hex>"}` | vendor | Receipt (once per run) |
| `GET /runs` | admin | All runs, including never-submitted ones |
| `POST /verify` with `{"report": {...}, "receipt": {...}}` | admin | `GENUINE`, `TAMPERED`, `UNKNOWN_RUN` or `LEDGER_TAMPERED` |

## Vendor commands

```
export SEAL_URL=http://wsvm33
export SEAL_VENDOR_TOKEN=<token ITSG gave you>
python seal/client.py start                      # before the review; remembers the run in .seal_current_run
python seal/client.py submit reports/RPT-xxx.json   # saves reports/RPT-xxx.json.receipt.json
```

Send ITSG the report **and** the `.receipt.json`.

## ITSG commands

```
export SEAL_URL=http://wsvm33
export SEAL_ADMIN_TOKEN=<admin token>
python seal/verify.py report.json report.json.receipt.json    # GENUINE / TAMPERED / UNKNOWN_RUN, exit code 0 only for GENUINE
python seal/verify.py --runs                                  # every run, with NEVER SUBMITTED marked
```

## Run it on our team server wsvm33 with Docker

Not deployed yet. Do these steps on wsvm33, from the repository root:

```
# 1. build
docker build -f seal/Dockerfile -t team10-seal .

# 2. folder for the ledger (the container runs as user 10001)
sudo mkdir -p /srv/team10/seal-data
sudo chown 10001 /srv/team10/seal-data

# 3. secrets file, outside git, readable only by you
umask 077
cat > /srv/team10/seal.env <<'EOF'
SEAL_SECRET=<long random value, e.g. from: openssl rand -hex 32>
SEAL_VENDOR_TOKEN=<random value>
SEAL_ADMIN_TOKEN=<another random value>
EOF

# 4. run
docker run -d --name team10-seal --restart unless-stopped \
  -p 80:8080 \
  --env-file /srv/team10/seal.env \
  -v /srv/team10/seal-data:/data \
  team10-seal

# 5. check
docker logs team10-seal            # should say: ledger /data/ledger.jsonl: OK, 0 entries
```

Never commit `seal.env`, the secrets or `seal-data/` (`seal/.gitignore` already ignores ledger files).
Back up `/srv/team10/seal-data/ledger.jsonl` regularly. If the secret is lost or changed, old receipts and the whole
ledger can no longer be verified.
