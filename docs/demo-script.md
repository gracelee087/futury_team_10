# SÜSIE — Live-Demo-Skript (T10-042, 2026-10-27)

Built around the five things the customer cares about. Total runtime: ~8 minutes.
Every step is verified working offline (no gateway needed) except step 3 (live AI
roles), which degrades honestly if the gateway is down.

## Setup (before the audience walks in)

```bash
cd "/Users/amour/Downloads/FUTURY-Team 10"
python3 -m itsg.demo --fresh          # clean store, deterministic, ~2 s
python3 -m itsg.webserver --port 8766 # local bridge, 127.0.0.1 only
# open http://127.0.0.1:8766/  (redirects to the SÜSIE assistant app)
```

Optional (shows AI roles LIVE — needs the gateway/secrets store):

```bash
python3 -m itsg.demo --fresh --live   # real extractor/designer/challenger runs
```

Tip: name the reviewer in the chat onboarding **before** the audience arrives so
the first visible message is SÜSIE's chatty greeting, not onboarding.

## 1 — "Automate test-case creation from the law" (~2 min)

The customer creates test cases once/twice a year from spec changes. Show:

- **The button** (top of the Prüffälle view): **"Testfälle aus dem Gesetz
  erstellen"** → SÜSIE opens in the chat and proposes the full run
  (requirement extraction GLM-Flash → test-case design Kolibri-1 → independent
  challenger → deterministic comparison). Click **Ja, ausführen** — the run
  executes live with a visible progress card
  ("Schritt 1/4: Anforderungsextraktion …"), each AI role bounded to 60 s with
  an honest fallback if the gateway stalls. Typical total: 1.5–3 min.
- In the Sources view: the requirement cites the exact passage
  (VB DTA EEL §3.12, S. 135–136) — extracted by the AI, approved by a human gate
  (G1). The expected values come from the official Beispielpapier V13.3, never
  invented by the model.
- One line to say: "Der Jahreszyklus — Spezifikationsänderung rein, Testfälle
  raus — ist ein einziger nachvollziehbarer Lauf."

## 2 — "Test the cases against the software's output" (~2 min)

- **The button** next to it: **"Abgleich mit Softwareausgabe starten"** →
  proposal → **Ja** → the deterministic field comparison runs in seconds (no
  AI), the case cards refresh.
- Open **TC-2**: the field comparison table shows official vs. transmitted values
  with the deviating field highlighted, and one plain sentence:
  "Beginn Entgeltersatzleistung (Zeitraum 1): erwartet 20XX0101, übermittelt 20XX0401."
- **Chat:** "Zeig mir die Abweichung" → SÜSIE opens the case for you.
- Point out TC-3: incomplete input is **NOT_EVALUATED**, never a silent pass —
  fail closed is a feature, sell it as trust.

## 3 — "Easy access and reliability through the chat agent" (~1.5 min)

- The suggestion chips are one-click reliable: "Wo stehe ich?" gives a live
  status summary with counts, deviations and a recommended next step — computed
  deterministically, no model round-trip, works even if the gateway is down.
- Show navigation: "öffne fall tc-4", "zurück", "Neu starten" — all handled in
  code (deterministic command layer), the LLM handles everything else.
- Toggle DE/EN in the sidebar — SÜSIE mirrors the user's language.

## 4 — "Report generation" (~1.5 min)

- Report view → **"Protokoll exportieren"** → confirm → the formal PDF downloads:
  preface (Vorbemerkung), executive summary with TL;DR and **Empfohlene
  Maßnahmen** (deterministic, per finding), findings in detail, appendix with
  template/conformance status and integrity (SHA-256, machine-generated footer).
- One line: "Der Bericht beginnt mit dem, was eine Führungskraft braucht —
  Befund, Empfehlung — und trägt die Belege im Anhang."

## 4b — The seal moment (USP, ~1 min) — DO NOT SKIP

In the Protokoll view, card **"Integrität & Siegel"**:

1. Click **"Siegel anfordern"** → green chip: *Quittung — GENUINE (Bericht unverändert)*.
   Only the SHA-256 fingerprint went to the receipt office — say that sentence.
2. Click **"Manipulation simulieren"** → red banner: *TAMPERED — der Bericht wurde nach der
   Quittung verändert. Jeder Empfänger erkennt das sofort.* Then the honest note:
   simulated on a COPY; the store original is untouched.
3. One line to say: **"Kein anderes Team kann zeigen, dass sein eigener Prüfbericht
   manipulationsgeschützt ausgetauscht wird."**

(The service refuses re-sealing the same report as a replay and archives ledgers from
older demo runs honestly — both are features, narrate them as such if they appear.)

## 5 — "Full traceability" (~1.5 min)

- In the open TC-2 card: the evidence chain
  **RPT-1 → RUN-2 → TC-2 → CRIT-EAZ-1 → REQ-VOER-1 → SRC-BP** — every chip is a
  real store record; click one to see its human-readable detail (execution
  timestamp, build, evidence file; criterion text; requirement; source with
  version, validity and checksum).
- Sources view: source record with SHA-256 of the original PDF, G0-approved.
- Optional flex: `python3 -m itsg.demo --fresh --seal` gives the report artifact
  an HMAC receipt from the (in-process) ITSG receipt office — tamper-evident
  report exchange.

## Honest boundaries (say them before the customer asks)

- All data is fabricated/synthetic; the template is labeled synthetic; the
  conformance claim stays **NO** (no statutory report form exists — § 95b SGB IV
  prescribes no template).
- The "payroll software" output is a fabricated fixture file — the comparator
  consumes whatever the real software exports (DTA EEL record layout).
- Human gates (G0–G6) are recorded with named reviewers; SÜSIE executes only on
  explicit confirmation and never owns a decision.

## If something breaks live

- Gateway down or slow: each AI role in the live run is bounded to 60 s and
  degrades into an honestly recorded error run; the progress card keeps
  counting. Chat still answers status/navigation/report (deterministic layer).
- Refresh the page — state is server-side in the store; nothing is lost.
- Nuclear option: `python3 -m itsg.demo --fresh` + reload = clean demo state.
