# Deploying the demo UI on wsvm33 (not done yet)

Public URL after deployment: **http://130.83.85.181:33080** (outside port 33080 maps to port 80 on wsvm33).
Only one public web port exists, so the UI takes port 80 and the seal becomes private (reachable only by the UI,
over a Docker network). Run these steps on wsvm33 from a checkout of this branch/PR, in the repository root.

## 1. Build both images

```
git fetch && git switch ui-integration        # or main, once the PR is merged
docker build -f seal/Dockerfile -t team10-seal .
docker build -f ui/Dockerfile   -t team10-ui .
```

## 2. Private network and the seal (no host port)

The running seal container is called `seal` (the image is `team10-seal`) and listens on `127.0.0.1:8081`.
Replace it; the ledger lives in `/srv/team10/seal-data` and is kept.

```
docker network create team10
docker rm -f seal
docker run -d --name seal --network team10 --restart unless-stopped \
  --env-file /srv/team10/seal.env \
  -v /srv/team10/seal-data:/data \
  team10-seal
docker logs seal            # should say: ledger /data/ledger.jsonl: OK, N entries
```

No `-p` option: nothing outside the `team10` network can reach the seal.

## 3. Secrets file for the UI (never commit it)

```
umask 077
{
  read -rsp "HESSIAN_API_KEY: " KEY; echo
  echo "HESSIAN_API_KEY=$KEY"
  echo "SEAL_URL=http://seal:8080"
  grep -E '^SEAL_(VENDOR|ADMIN)_TOKEN=' /srv/team10/seal.env
  echo "PRIVACY_KEY=$(openssl rand -hex 32)"
  echo "RETENTION_DAYS=7"
} > /srv/team10/ui.env
chmod 600 /srv/team10/ui.env
```

`SEAL_SECRET` is deliberately NOT copied: only the seal itself needs it.

- `PRIVACY_KEY` is the key for the privacy airlock (tokens are HMAC-SHA256 with it). Generated on the server, stored only in
  `ui.env`, never committed or logged. At least 16 characters; a shorter key makes every question BLOCKED. Without it a
  random key per process is used (works, but the Datenschutz tab shows a yellow light). Keep the same key when you
  re-create the container if you want tokens to stay comparable between runs.
- `RETENTION_DAYS` (default 7): review reports (`RPT-*.json`) and harness results (`harness-*.json`) in the reports volume
  older than this are deleted when the server starts and then once a day. The review-decision log and the seal ledger
  are not touched. The seal ledger holds only hashes, no report content, so deleting a report does not break the chain
  and the ledger can stay append-only.

## 4. Reports folder and the UI container

The container runs as user 10001 and writes review reports, harness results and the review-decision log
(`review-events.jsonl`) into the reports volume.

```
sudo mkdir -p /srv/team10/reports
sudo chown 10001 /srv/team10/reports
docker run -d --name team10-ui --network team10 --restart unless-stopped \
  -p 80:8000 \
  --env-file /srv/team10/ui.env \
  -v /srv/team10/reports:/app/reports \
  team10-ui
```

## 5. Check

```
docker logs team10-ui
curl -s http://localhost/api/health          # on wsvm33; shows checker, retrieval, seal, harness
```

Also check the privacy airlock: `curl -s http://localhost/api/privacy/flows` should show a green light for the AI model
(a yellow light means `PRIVACY_KEY` is missing in `ui.env`).

Then open http://130.83.85.181:33080 and click through the demo path in `ui/README.md`.
On the Overview tab all four parts should be "available". If "seal" is unavailable, check that both containers are on
the `team10` network (`docker network inspect team10`) and that `SEAL_URL` is `http://seal:8080`.

## Things to know

- There is **no login**. Anyone who can open the URL can run reviews, ask questions (each one uses the hessian.AI key,
  limited to 10 per minute per client address) and record review decisions with any typed name. Fine for a demo; not for real use.
- Traffic is plain HTTP.
- Back up `/srv/team10/reports/review-events.jsonl` and `/srv/team10/seal-data/ledger.jsonl` if they matter.
- Update later: rebuild the images (step 1), then `docker rm -f team10-ui` and repeat step 4 (and step 2 for the seal).
- Rollback to the old seal setup: `docker rm -f seal team10-ui`, then start the old container (named `seal`) as documented in `seal/README.md`.
