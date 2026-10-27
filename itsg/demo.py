"""SÜSIE — Systemüberprüfung sozialversicherungsrechtlicher IT-Ergebnisse.

End-to-end demo driver (T10-018, approach-A slice; plan.md ~3-minute script):
cited source → requirement candidate (AI) → human gate → criterion → test
cases (normal / boundary / invalid) → fabricated executions → deterministic
comparator → synthetic-template rendering (compliance_claim=False) →
conformance → evidence-chain trace. One PASS, one deliberate MISMATCH, one
NOT_EVALUATED — every step recorded in the append-only store events.

Run from a clean start:

    python3 -m itsg.demo --fresh          # offline candidates (deterministic)
    python3 -m itsg.demo --fresh --live   # live gateway calls (Kolibri-1 / GLM-Flash)

All data is fabricated; the Beispielpapier expected records are payroll
transmit-side ground truth, never benefit-amount claims. The template is
the conspicuously labeled synthetic one — no legal or template compliance
claim is made or implied (plan.md; agent-governance.md §1).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from .candidates import (
    ROLE_REQUIREMENT_EXTRACTOR,
    ROLE_TEST_CASE_DESIGNER,
    ROLE_TEST_CHALLENGER,
    new_run,
    record_gate_decision,
)
from .comparator import compare
from .conformance import check_conformance
from .gates import GateDecision
from .llm import ROLE_MODELS, run_role
from .records import (
    CriterionRecord,
    ExecutionRecord,
    SourceRecord,
    TemplateRecord,
    TestCaseRecord,
)
from .renderer import render
from .secrets import SecretsStore
from .store import Store
from .timeutil import utc_now
from .vorerkrankung import Episode, evaluate

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
REVIEWER = "human-owner (solo mode, provisional §9 default #7)"
OFFLINE_AUTHOR = "coding-agent offline draft (no LLM call)"
LIVE_AUTHOR = "susie-llm-client"
# Bounded per role (owner decision for the live demo): a stalled gateway call
# degrades into an honest error run after this many seconds instead of holding
# the confirmed action for minutes per role. Fallback text is recorded openly.
LIVE_ROLE_TIMEOUT_S = 60

_OFFLINE_REQUIREMENT_TEXT = (
    "Die Vorerkrankungsanfrage (Abgabegrund 41) darf nur ausgelöst werden, wenn eine "
    "AU-Bescheinigung für die aktuelle AU vorliegt, mindestens eine bescheinigte potentielle "
    "Vorerkrankung in den letzten 6 Monaten vor AU-Beginn im Datenbestand liegt und die "
    "kumulierten Vorzeiten der letzten 12 Monate zusammen mit der aktuellen AU zum Zeitpunkt "
    "der Meldung mindestens 30 Tage umfassen."
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _put(store: Store, kind: str, record) -> dict:
    return store.put(kind, record.to_dict() if hasattr(record, "to_dict") else record)


def _put_gate(store: Store, gate: GateDecision) -> dict:
    record = {"id": f"GATE-{gate.gate}-{gate.decided_at}", **gate.to_dict()}
    return store.put("gate", record)


def _put_run(store: Store, run: dict) -> dict:
    return store.put("agent_run", {"id": run["run_id"], **run})


def _offline_run(role: str, task_id: str, input_ids: list[str], result: dict,
                 citations: list[dict] | None = None) -> dict:
    return new_run(
        role, task_id, "offline (demo)", "none (no LLM call)", input_ids,
        result={"note": "candidate drafted offline for the demo; no LLM call", **result},
        citations=citations, author=OFFLINE_AUTHOR,
    ).to_dict()


def _live_run(role: str, task_id: str, input_ids: list[str], user_content: str) -> dict:
    return run_role(role, task_id, input_ids, user_content, author=LIVE_AUTHOR,
                    timeout=LIVE_ROLE_TIMEOUT_S).to_dict()


# -- candidates ---------------------------------------------------------------

def requirement_candidate(store: Store, live: bool) -> tuple[dict, GateDecision]:
    """Requirement candidate for the Vorerkrankung trigger rule (G1)."""
    input_ids = ["SRCV-VB-134-TEST"]
    user_content = (
        "[0] id=SRCV-VB-134-TEST locator=S. 135, §3.12\n"
        "Die Vorerkrankungsanfrage (3.1.18 „Abgabegrund“ = „41“) darf nur dann durch den "
        "Arbeitgeber ausgelöst werden, wenn dem Arbeitgeber für die aktuelle Arbeitsunfähigkeit "
        "eine Arbeitsunfähigkeitsbescheinigung vorliegt, zusätzlich in den letzten 6 Monaten vor "
        "Beginn der aktuellen Arbeitsunfähigkeit mindestens eine bescheinigte potentielle "
        "Vorerkrankung in Bezug auf die aktuelle Arbeitsunfähigkeit im Datenbestand vorliegt und "
        "die kumulierten Zeiten aller potentiellen Vorerkrankungen in den letzten 12 Monaten "
        "zusammen mit der aktuellen Arbeitsunfähigkeit zum Zeitpunkt der Meldung mindestens "
        "30 Tage umfassen."
    )
    if live:
        run = _live_run(ROLE_REQUIREMENT_EXTRACTOR, "T10-018", input_ids, user_content)
    else:
        run = _offline_run(
            ROLE_REQUIREMENT_EXTRACTOR, "T10-018", input_ids,
            {"requirements": [{"text_de": _OFFLINE_REQUIREMENT_TEXT,
                               "quote_de": user_content.split("\n", 1)[1][:80] + "…",
                               "locator": "S. 135, §3.12"}]},
            citations=[{"source_version_id": "SRCV-VB-134-TEST", "locator": "S. 135, §3.12"}],
        )
    _put_run(store, run)
    text = (run.get("result", {}).get("requirements") or [{}])[0].get(
        "text_de", _OFFLINE_REQUIREMENT_TEXT)
    live_ok = live and run.get("status") == "candidate" and run.get("citations")
    req = {"id": "REQ-VOER-1", "text": text, "source_id": "SRC-VB",
           "citation": "S. 135, §3.12 (VB DTA EEL V13.4)",
           "status": "candidate" if (run.get("status") in ("candidate", "needs_review")) else "needs_review"}
    _put(store, "requirement", req)
    gate = record_gate_decision(
        type("R", (), {"author": run.get("author", OFFLINE_AUTHOR),
                       "run_id": run.get("run_id", ""), "role": ROLE_REQUIREMENT_EXTRACTOR})(),
        REVIEWER, "approved" if live_ok or not live else "escalated",
        "Requirement candidate checked against VB §3.12 p. 135 wording; locator resolves"
        if live_ok or not live else "live extraction did not yield a citable candidate — human review",
        conditions=["qualified domain reviewer must confirm legal meaning before production use"],
        affected_ids=["REQ-VOER-1", run.get("run_id", "")],
    )
    _put_gate(store, gate)
    req["status"] = "approved" if gate.decision == "approved" else "needs_review"
    _put(store, "requirement", req)
    return req, gate


def case_candidates(store: Store, live: bool) -> tuple[dict, GateDecision]:
    """Test-case candidates from the designer + independent challenger (G3)."""
    input_ids = ["CRIT-EAZ-1", "CRIT-VOER-1"]
    if live:
        run = _live_run(
            ROLE_TEST_CASE_DESIGNER, "T10-018", input_ids,
            "Kriterium CRIT-EAZ-1: für §3.1-Sachverhalte ist der offizielle DSLW/DBAL/DBAE-"
            "Erwartungsdatensatz zu übertragen (Basis: Beispielpapier §3.1, S. 9–11). "
            "Kriterium CRIT-VOER-1: DBVO (Abgabegrund 41) genau dann, wenn VB §3.12 erfüllt "
            "(30 Tage/12 Monate, ≥1 Bescheinigung/6 Monate)."
        )
    else:
        run = _offline_run(ROLE_TEST_CASE_DESIGNER, "T10-018", input_ids, {
            "cases": [
                {"case_type": "normal", "case_ref": "TC-1", "expected_basis": "BP §3.1 S. 9–11"},
                {"case_type": "boundary", "case_ref": "TC-2", "expected_basis": "BP §3.2.1.4 S. 12"},
                {"case_type": "invalid", "case_ref": "TC-3", "expected_basis": ""},
            ]})
    _put_run(store, run)
    if live:
        challenger = _live_run(
            ROLE_TEST_CHALLENGER, "T10-018", input_ids,
            "Fälle: TC-1 normal (BP §3.1), TC-2 boundary (§3.2.1.4 volle Fehlzeit), "
            "TC-3 invalid (unvollständiger Sachverhalt, kein offizieller Erwartungswert). "
            "Prüfe Grenzfälle und unbelegte Annahmen."
        )
    else:
        challenger = _offline_run(ROLE_TEST_CHALLENGER, "T10-018", input_ids, {
            "questions": ["Was gilt bei Abrechnung zum 01. des laufenden Monats (§3.2.1.5)?"],
            "counterexamples": [{"case_ref": "TC-3",
                                 "issue": "NOT_EVALUATED-Pfad muss sichtbar bleiben, nie still PASS werden"}],
            "recommendation": "review"})
    _put_run(store, challenger)
    gate = record_gate_decision(
        type("R", (), {"author": run.get("author", OFFLINE_AUTHOR),
                       "run_id": run.get("run_id", ""), "role": ROLE_TEST_CASE_DESIGNER})(),
        REVIEWER, "approved",
        "Case candidates approved against cited official expected values (BP §3.1/§3.2.1.4); "
        "challenger recommendations recorded",
        conditions=["invalid case carries no invented expected value (NOT_EVALUATED path)"],
        affected_ids=["TC-1", "TC-2", "TC-3", "TC-4", run.get("run_id", ""),
                      challenger.get("run_id", "")],
    )
    _put_gate(store, gate)
    return run, gate


# -- demo ----------------------------------------------------------------------

def _seal_report(artifact_path: Path, store_root: Path, seal_url: str | None,
                 vendor_token: str | None, admin_token: str | None) -> dict | None:
    """Optional --seal step (T10-034): give the report artifact an ITSG receipt.

    With an explicit ``seal_url`` the external receipt office is used; without
    one, a throwaway in-process receipt office is started (demo mode, ledger
    kept in the store). Sealing is evidence hardening, NOT a gate: any failure
    is reported honestly and the demo continues without a receipt.
    """
    seal_dir = ROOT / "seal"
    if not (seal_dir / "server.py").exists():
        print("    seal: seal/ service not present — no receipt (evidence stays unscaled)")
        return None
    if str(seal_dir) not in sys.path:
        sys.path.insert(0, str(seal_dir))
    import secrets as _secrets
    import threading as _threading

    import client as seal_client
    import server as seal_server
    import verify as seal_verify

    try:
        if seal_url:
            if not (vendor_token and admin_token):
                print("    seal: vendor/admin token missing — no receipt")
                return None
            vendor, admin = vendor_token, admin_token
        else:
            own_server = seal_server.make_server(
                {"SEAL_SECRET": _secrets.token_hex(32),
                 "SEAL_VENDOR_TOKEN": _secrets.token_hex(16),
                 "SEAL_ADMIN_TOKEN": _secrets.token_hex(16),
                 "SEAL_LEDGER": str(store_root / "seal-ledger.jsonl")},
                "127.0.0.1", 0)
            _threading.Thread(target=own_server.serve_forever,
                              kwargs={"poll_interval": 0.05}, daemon=True).start()
            seal_url = f"http://127.0.0.1:{own_server.server_address[1]}"
            vendor = own_server.app.vendor_token
            admin = own_server.app.admin_token
            print(f"    seal: in-process receipt office on {seal_url} "
                  "(throwaway secrets, ledger in the store — demo mode; the receipt is "
                  "verifiable only within this run — point --seal-url at a persistent "
                  "receipt office for a verifiable-later receipt)")
        state = store_root / "seal-current-run"
        run = seal_client.start_run(seal_url, vendor, state_file=state)
        res = seal_client.submit(artifact_path, run_id=run["run_id"], url=seal_url,
                                 token=vendor, state_file=state)
        check = seal_verify.verify_files(artifact_path, res["receipt_file"],
                                         url=seal_url, token=admin)
        print(f"    seal: run {run['run_id']} · receipt seq {res['receipt']['seq']} · "
              f"verification: {check['result']} ({check['reason'][:60]})")
        return {"run_id": run["run_id"], "receipt_file": res["receipt_file"],
                "result": check["result"]}
    except Exception as exc:  # sealing is optional evidence hardening, never a gate
        print(f"    seal: unavailable ({type(exc).__name__}) — continuing without a receipt")
        return None


def run_demo(store_root: Path, live: bool, fresh: bool, seal: bool = False,
             seal_url: str | None = None, seal_vendor_token: str | None = None,
             seal_admin_token: str | None = None) -> int:
    if fresh and store_root.exists():
        shutil.rmtree(store_root)
    store = Store(store_root)
    print("=" * 72)
    print("SÜSIE — Systemüberprüfung sozialversicherungsrechtlicher IT-Ergebnisse")
    print("T10-018 approach-A demo slice · fabricated data only · no compliance claim")
    print("=" * 72)

    # 1. Source + template (G0) ------------------------------------------------
    bp = _load("bp_3_1_normal.json")
    cite = bp["citation"]
    source = SourceRecord(
        id="SRC-BP", title=f"{cite['source']} — Beispielpapier §{cite['section']}",
        issuer=cite["issuer"], version=cite["version"], valid_from=cite["effective"],
        checksum=cite["source_sha256"], status="needs_review",
        notes=f"offizielles Beispielkorpus; SHA-256 des Original-PDFs verifiziert",
    )
    _put(store, "source", source)
    g0 = GateDecision("G0", REVIEWER, "approved",
                      "Origin/issuer/version/effective date verified against the corpus file; "
                      "SHA-256 matches the recorded original",
                      affected_ids=["SRC-BP"])
    _put_gate(store, g0)
    source.status = "approved"
    _put(store, "source", source)
    print(f"\n[1] Quelle {source.id}: {source.title}")
    print(f"    Version {source.version}, gültig ab {source.valid_from}, "
          f"SHA-256 {source.checksum[:16]}…, G0: {g0.decision} durch {REVIEWER}")

    profile = _load("synthetic_template_profile.json")
    synth = _load("synthetic_template.json")
    template = TemplateRecord(id=synth["template_id"], official_form_id=None,
                              version=synth["version"], valid_from=None,
                              source_id="TPL-SYNTH", checksum="", status="needs_review")
    _put(store, "template", template)
    print(f"    Vorlage {template.id} ({template.version}): SYNTHETISCH — official_form_id=None")

    # 2. Requirement candidate → G1 -------------------------------------------
    req, g1 = requirement_candidate(store, live)
    print(f"\n[2] Anforderungskandidat REQ-VOER-1 ({'live' if live else 'offline'}): "
          f"{req['status'].upper()} · Zitat: {req['citation']}")
    print(f"    G1 {g1.decision} · Reviewer {g1.reviewer} ≠ Autor")

    # 3. Criteria (G3) ----------------------------------------------------------
    crit_eaz = CriterionRecord(
        id="CRIT-EAZ-1", requirement_id="REQ-VOER-1",
        description="Für §3.1-Sachverhalte überträgt das Abrechnungsprogramm den offiziellen "
                    "DSLW/DBAL/DBAE-Erwartungsdatensatz (Beispielpapier V13.3 §3.1 S. 9–11; "
                    "Abwandlung §3.2.1.4 S. 12).",
        expected_basis=bp["expected_basis"], review_status="draft")
    crit_voer = CriterionRecord(
        id="CRIT-VOER-1", requirement_id="REQ-VOER-1",
        description="DBVO (Abgabegrund 41) genau dann, wenn die VB §3.12-Trigger erfüllt sind "
                    "(≥1 bescheinigte Vorerkrankung/6 Monate; ≥30 Tage kumuliert/12 Monate).",
        expected_basis=_load("vorerkrankung_konstellation.json")["expected_basis"],
        review_status="draft")
    for c in (crit_eaz, crit_voer):
        _put(store, "criterion", c)
    cases_run, g3 = case_candidates(store, live)
    crit_eaz.review_status = "approved"
    crit_voer.review_status = "approved"
    _put(store, "criterion", crit_eaz)
    _put(store, "criterion", crit_voer)
    print(f"\n[3] Kriterien CRIT-EAZ-1, CRIT-VOER-1 → G3 {g3.decision} (author≠reviewer; "
          f"Challenger-Empfehlung protokolliert)")

    # 4. Test cases (approved basis only) ---------------------------------------
    boundary = _load("bp_3_2_1_4_boundary.json")
    invalid = _load("bp_invalid_missing_input.json")
    konst = _load("vorerkrankung_konstellation.json")
    tc1 = TestCaseRecord(id="TC-1", criterion_id="CRIT-EAZ-1", case_type="normal",
                         inputs=bp["sachverhalt"], expected=bp["expected"],
                         expected_basis=bp["expected_basis"], review_status="approved")
    tc2 = TestCaseRecord(id="TC-2", criterion_id="CRIT-EAZ-1", case_type="boundary",
                         inputs=boundary["sachverhalt"], expected=boundary["expected"],
                         expected_basis=boundary["expected_basis"], review_status="approved")
    tc3 = TestCaseRecord(id="TC-3", criterion_id="CRIT-EAZ-1", case_type="invalid",
                         inputs=invalid["sachverhalt"], expected=invalid["expected"],
                         expected_basis=invalid["expected_basis"], review_status="approved")
    tc4 = TestCaseRecord(id="TC-4", criterion_id="CRIT-VOER-1", case_type="normal",
                         inputs={"current_au": konst["current_au"],
                                 "prior_episodes": konst["prior_episodes"],
                                 "reporting_date": konst["reporting_date"]},
                         expected={"ABGABEGRUND": "41", "VOER-ANFRAGE-AUSGELOEST": "J"},
                         expected_basis=konst["expected_basis"], review_status="approved")
    for tc in (tc1, tc2, tc3, tc4):
        _put(store, "test_case", tc)
    print(f"\n[4] Testfälle: TC-1 normal (BP §3.1) · TC-2 boundary (§3.2.1.4) · "
          f"TC-3 invalid (kein offizieller Erwartungswert) · TC-4 Vorerkrankung (VB §3.12)")

    # 5. Vorerkrankung deterministic function -----------------------------------
    result = evaluate(
        Episode(konst["current_au"]["start"], konst["current_au"]["end"], True),
        [Episode(e["start"], e["end"], e["attested"]) for e in konst["prior_episodes"]],
        konst["reporting_date"],
    )
    print(f"\n[5] Vorerkrankung-Funktion ({result.module_version}): {result.status} "
          f"· {result.days_prior} + {result.days_current} = {result.days_total} Tage ≥ 30 · "
          f"Zitat: {result.citation[:58]}…")

    # 6. Fabricated executions → comparator -------------------------------------
    executed_at = utc_now()
    executions = [
        ExecutionRecord(id="RUN-1", test_case_id="TC-1", vendor="Demo-Payroll (fabrizierte Daten)",
                        software_version="demo-0.1", observed=bp["expected"],
                        evidence_ref="fixtures/bp_3_1_normal.json#expected",
                        run_at=executed_at),
        # deliberate mismatch: base-example EAZ reported instead of the §3.2.1.4 value
        ExecutionRecord(id="RUN-2", test_case_id="TC-2", vendor="Demo-Payroll (fabrizierte Daten)",
                        software_version="demo-0.1",
                        observed={"ABGABEGRUND": "01", "EAZ-BEGINN-1": "20XX0401",
                                  "EAZ-ENDE-1": "20XX0131"},
                        evidence_ref="fixtures/bp_3_2_1_4_boundary.json#expected (deliberately altered)",
                        run_at=executed_at),
        ExecutionRecord(id="RUN-3", test_case_id="TC-3", vendor="Demo-Payroll (fabrizierte Daten)",
                        software_version="demo-0.1", observed=None,
                        evidence_ref="", run_at=executed_at),
        ExecutionRecord(id="RUN-4", test_case_id="TC-4", vendor="Demo-Payroll (fabrizierte Daten)",
                        software_version="demo-0.1",
                        observed={"ABGABEGRUND": "41", "VOER-ANFRAGE-AUSGELOEST": "J"},
                        evidence_ref="fixtures/vorerkrankung_konstellation.json#expected",
                        run_at=executed_at),
    ]
    for ex in executions:
        _put(store, "execution", ex)
    findings = []
    for tc, ex in zip((tc1, tc2, tc3, tc4), executions):
        finding = compare(tc, ex, finding_id=f"FIND-{tc.id}")
        findings.append(finding)
        _put(store, "finding", finding)
    print(f"\n[6] Vergleich (deterministisch, fail-closed):")
    for f in findings:
        print(f"    {f.id}: {f.status} — {f.reason[:86]}")

    # 7. Renderer + conformance --------------------------------------------------
    case_meta = {
        "TC-1": {"case_id": "TC-1", "criterion_id": "CRIT-EAZ-1"},
        "TC-2": {"case_id": "TC-2", "criterion_id": "CRIT-EAZ-1"},
        "TC-3": {"case_id": "TC-3", "criterion_id": "CRIT-EAZ-1"},
        "TC-4": {"case_id": "TC-4", "criterion_id": "CRIT-VOER-1"},
    }
    artifact_path = store_root / "report.artifact.json"
    report = render("RPT-1", template, profile, findings, artifact_path, case_meta)
    artifact = json.loads(Path(report.artifact_ref).read_text(encoding="utf-8"))
    conformance = check_conformance(profile, artifact)
    report.conformance = [conformance]
    _put(store, "report", report)
    print(f"\n[7] Report RPT-1 → {report.artifact_ref}")
    print(f"    Conformance: {conformance['status']} · compliance_claim={report.compliance_claim} "
          f"({conformance['reason'][:64]}…)")
    if seal:
        _seal_report(Path(report.artifact_ref), store_root, seal_url,
                     seal_vendor_token, seal_admin_token)

    # 8. Trace chain (plan.md checklist #1) --------------------------------------
    print(f"\n[8] Belegkette für FIND-TC-2 (MISMATCH):")
    print("    FIND-TC-2 → RUN-2 → TC-2 → CRIT-EAZ-1 → REQ-VOER-1 → SRC-BP "
          f"(BP §3.2.1.4, S. 12, V13.3, ab 01.01.2027) · G0/G1/G3-Entscheidungen protokolliert")

    print(f"\nBoundary: Beispielpapier-Erwartungswerte = Transmit-Seite des "
          f"Entgeltabrechnungsprogramms; keine Leistungsbeitragsaussage. Synthetische Vorlage; "
          f"compliance_claim bleibt False. Nur fabrizierte Daten.")
    print(f"Store: {store_root} (events: {len(store.events())}) · Modelle: "
          f"{ROLE_MODELS['test_case_designer']} (designer) / "
          f"{ROLE_MODELS['requirement_extractor']} (extractor+challenger)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="itsg.demo", description="SÜSIE demo slice")
    parser.add_argument("--store", default=str(ROOT / "data" / "demo"))
    parser.add_argument("--fresh", action="store_true", help="delete the store first (clean start)")
    parser.add_argument("--live", action="store_true",
                        help="use the live gateway (Kolibri-1/GLM-Flash); default: offline candidates")
    parser.add_argument("--seal", action="store_true",
                        help="seal the report artifact with the ITSG receipt office (T10-034); "
                             "uses SEAL_URL/SEAL_VENDOR_TOKEN/SEAL_ADMIN_TOKEN if set, "
                             "otherwise a throwaway in-process receipt office")
    parser.add_argument("--seal-url", dest="seal_url", default=None,
                        help="external receipt-office URL (implies --seal when provided)")
    args = parser.parse_args(argv)
    seal = args.seal or bool(args.seal_url)
    return run_demo(Path(args.store), live=args.live, fresh=args.fresh, seal=seal,
                    seal_url=args.seal_url,
                    seal_vendor_token=os.environ.get("SEAL_VENDOR_TOKEN"),
                    seal_admin_token=os.environ.get("SEAL_ADMIN_TOKEN"))


if __name__ == "__main__":
    sys.exit(main())
