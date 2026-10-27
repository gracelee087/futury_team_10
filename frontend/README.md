# SÜSIE frontend

Selected **Prüfakte** design, copied into the repository under T10-030. This entire directory is the handoff: HTML, CSS, JavaScript, the ChatGPT-generated transparent logo, design notes, and verification evidence. No npm install, build step, account, backend, or network API is required to run the prototype.

## Run from the repository root

Backend-wired (recommended; serves the frontend plus `/api/state`, `/api/run`, `/api/health` from the itsg demo store):

```sh
python3 -m itsg.webserver --port 8766
```

Static only (the UI then falls back to clearly-labelled synthetic data):

```sh
python3 -m http.server 8766 --bind 127.0.0.1 --directory frontend
```

Open [SÜSIE locally](http://127.0.0.1:8766/). Stop the foreground server with Ctrl+C. Direct entry: `pruefakte.html`.

## What is delivered

- **Backend wiring** (T10-031): `python3 -m itsg.webserver` serves the frontend and a stdlib JSON API over the itsg demo store (`/api/state` typed records, `/api/run` re-runs the demo offline or live, `/api/health`). When the API is unreachable the UI falls back to synthetic data with an explicit "Backend nicht verbunden" badge — never silently. The topline badge, sources view (source record, criteria), report conformance line and audit summary all come from the store when connected.
- **Settings menu** in the sidebar: reading theme, colour mode, language, and API configuration (backend URL, connection check, offline/live demo re-run; live calls require a two-step confirm and never expose credentials to the browser).
- **Theme cycle icon** in the sidebar rotates casual/light → casual/dark → contrast/dark → contrast/light.
- **Language selector EN/DE** in the sidebar; the full UI chrome is translated (case evidence text stays in its source language, German, because it quotes official sources). Preference persists in localStorage; `?lang=de|en` overrides.
- **Elevation & motion**: raised sidebar with offset+blur shadows (High Contrast intentionally uses borders instead), subtle surface shadows, and quiet 160ms opacity+translate feedback that collapses under prefers-reduced-motion.
- Two themes, Casual and High Contrast, each with real light/dark variants.
- Source references, synthetic/backend cases, Soll/Ist evidence (primary field large, remaining DTA fields as key/value rows, mismatches highlighted), filters (including a "Klärungspunkte klären" toggle for non-PASS cases), sorting, notes, output evidence, report JSON export and a blocked release action. The report view lists the session's saved notes and drafts; notes can be deleted with a two-step confirm. Unsaved drafts are marked on the case rows.
- Drafts and notes are stored in sessionStorage for the browser tab, restored on reload, and included in JSON exports. Denied storage shows recovery copy. They are not sent to a backend.
- Generated logo at `assets/susie-logo.png` with derived display-size variants (`susie-logo-380.png`, `susie-logo-760.png`, original untouched) served through `srcset`; exact image-generation prompt and origin in `assets/logo-generation.md`. Dark variants use the same PNG rendered white through CSS. A text fallback handles image load failure.
- Zoomable type, short interruptible feedback with reduced-motion handling, mobile/tablet layouts, and print styling.

## Deliberate prototype boundary

Case data and comparisons are synthetic, local UI examples in `pruefakte.js`. They are not live backend comparator results. The source screen shows reference metadata, not a rendered original PDF. Notes do not approve criteria or findings. The report uses synthetic data and always exports `compliance_claim: false`. No legal, template-compliance, certification or production-readiness claim is made.

Backend T10-018 remains separately owned. Integration must replace the local cases/comparison display with actual typed records and endpoints, preserving states, citation provenance and human gates. No HTTP server/API contract was added by this frontend work. Do not overwrite backend fixtures or modules to make the demo appear integrated.

## Files and verification

- `DESIGN.md`: current design decisions and four-theme tokens; `.impeccable/design.json`: structured design metadata.
- `PRODUCT.md`: product/audience and prototype constraints.
- `verification/import-manifest.json`: all 12 selected source files matched by SHA-256 when copied; previews retained at source.
- `verification/repo-browser-checks.json`: fresh checks against the repo-served URL, not reused preview results.
- `verification/screenshots/`: repo-served theme/viewport evidence.
- `POLISH-VERIFICATION.md`: previous preview-scope checks and limits, retained as history.

Optional browser verification (development only; uses an already installed Playwright package and Chromium, does not install dependencies). Run against the bridge so backend wiring is covered:

```sh
python3 -m itsg.webserver --port 8766 &
SUSIE_BASE_URL=http://127.0.0.1:8766 node frontend/checks/smoke.cjs
```

If Playwright is not locally resolvable, set `PLAYWRIGHT_MODULE` to an existing module directory; if its Chromium is elsewhere set `SUSIE_CHROMIUM_EXECUTABLE` to the installed executable. Runtime UI has no Playwright dependency. The verification report records the exact command used on this machine.

Real Safari, physical devices, screen-reader testing and production backend behavior remain unverified. Independent UI review cleared the external concept demo; repo packaging remains `IN_REVIEW` pending human integration acceptance. Nothing was committed, pushed or deployed.
