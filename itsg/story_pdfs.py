"""Story-case showcase (T10-037, human directive 2026-10-26).

Evaluates a curated, deterministic selection of 10 cases from
``data/story_cases.json`` (200 synthetic cases, seed 4136; ground truth from
the rule text, not from an LLM) through the deterministic SÜSIE layers and
renders one formal report PDF per case via ``itsg.report_pdf``:

  1. DBVO/flow field comparison (expected vs observed — the comparator layer);
  2. the versioned Vorerkrankungsaftregel ``itsg.vorerkrankung`` (VB 13.4
     §3.12) for stories 1/3 — reason-neutral per p.135, PKV outside the
     procedure per p.136;
  3. story-4 61-reply field rules and story-6 cancel-and-correct flow rules
     exactly as tagged by the generator's rule taxonomy (VB 13.4
     §3.12.2–3.12.14; GG EEL 13.1 §2.5);
  4. a ground-truth agreement row: our flagged/clean verdict vs the
     independent ``must_flag`` — a disagreement is reported honestly.

Nothing here interprets law beyond what the story taxonomy states; rule
aspects the layers cannot judge are rendered as NOT_EVALUATED (fail closed).
All data is fabricated; every PDF carries the machine-generation footer and
content hash and makes no compliance claim.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from . import vorerkrankung
from .timeutil import utc_now

SHOWCASE_VERSION = "itsg.story_pdfs/0.1.0"

# Ground-truth taxonomy (testCase-stories.md, generated seed 4136).
STORY_RULES = {
    1: "Reason does not matter (VB 13.4 §3.12 p.135); private insurance → no 41 (p.136)",
    3: "Reported only if a certified AU follows seamlessly (VB 13.4 §3.12 p.135)",
    4: "Field rules VB 13.4 §3.12.2–3.12.14",
    6: "GG EEL 13.1 §2.5, VB 13.4 §3.1.18, Hinweise Testkonstellation",
}

# Deterministic curated selection: first case (sorted by id) per category.
SELECTION = [
    (1, "current AU is a work accident"),
    (1, "rehab stay, mixed prior reasons"),
    (1, "mixed reasons, under 30 days"),
    (1, "privately insured, work accident (BG, outside procedure)"),
    (3, "short uncertified days right before the current AU (included)"),
    (3, "defect: non-seamless short days reported"),
    (4, "correct insurer reply"),
    (4, "defect: employer periods reordered"),
    (6, "correct cancel-and-correct flow"),
    (6, "defect: 88 cancels the 41 instead of the 01"),
]

PASS, MISMATCH, NOT_EVALUATED = "PASS", "MISMATCH", "NOT_EVALUATED"

_CITE_VB = "VB 13.4 §3.12"


def select_cases(cases: list[dict]) -> list[dict]:
    """Exactly one case per SELECTION entry (sorted by id); raises if a category is missing."""
    by_key: dict[tuple[int, str], list[dict]] = {}
    for case in cases:
        by_key.setdefault((case["story"], case["category"]), []).append(case)
    selected = []
    for story, category in SELECTION:
        bucket = by_key.get((story, category)) or []
        if not bucket:
            raise ValueError(f"selection category not found: story {story} — {category!r}")
        selected.append(sorted(bucket, key=lambda c: c["id"])[0])
    return selected


def _diff_paths(expected, observed, prefix=""):
    """Recursive diff of JSON structures; returns dotted paths that differ."""
    if isinstance(expected, dict) and isinstance(observed, dict):
        diffs = []
        for key in sorted(set(expected) | set(observed)):
            diffs += _diff_paths(expected.get(key), observed.get(key),
                                 f"{prefix}.{key}" if prefix else key)
        return diffs
    if isinstance(expected, list) and isinstance(observed, list) and len(expected) == len(observed):
        diffs = []
        for i, (e, o) in enumerate(zip(expected, observed)):
            diffs += _diff_paths(e, o, f"{prefix}[{i}]")
        return diffs
    if expected != observed:
        return [prefix or "$"]
    return []


def _fmt(value) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)


def _row(check: str, criterion: str, status: str, reason: str,
         case_id: str, citation: str) -> dict:
    return {
        "case_id": check,
        "criterion_id": criterion,
        "result_status": status,
        "reason": reason,
        "evidence_links": [case_id, citation],
    }


def _dbvo_row(case: dict) -> dict:
    expected = (case.get("expected") or {}).get("dbvo")
    observed = case.get("observed_dbvo")
    if expected is None and observed is None:
        return _row("DBVO-Feldvergleich", "erwartet vs. übermittelt", PASS,
                    "Kein 41-DBVO erwartet und keiner übermittelt — verfahrensgemäß.",
                    case["id"], _CITE_VB)
    if expected is None and observed is not None:
        return _row("DBVO-Feldvergleich", "erwartet vs. übermittelt", MISMATCH,
                    "Es wurde ein 41-DBVO übermittelt, obwohl keiner zu erwarten war "
                    f"(ABGABEGRUND {observed.get('ABGABEGRUND')}).",
                    case["id"], _CITE_VB)
    if expected is not None and observed is None:
        return _row("DBVO-Feldvergleich", "erwartet vs. übermittelt", MISMATCH,
                    "Erwarteter 41-DBVO wurde nicht übermittelt.", case["id"], _CITE_VB)
    diffs = _diff_paths(expected, observed)
    if not diffs:
        return _row("DBVO-Feldvergleich", "erwartet vs. übermittelt", PASS,
                    "Alle DBVO-Felder stimmen mit den Erwartungswerten überein "
                    f"({len(_flatten(expected))} Felder/Werte geprüft).",
                    case["id"], _CITE_VB)
    detail = "; ".join(f"{p}: erwartet {_fmt(_dig(expected, p))}, "
                       f"übermittelt {_fmt(_dig(observed, p))}" for p in diffs[:3])
    more = f" (+{len(diffs) - 3} weitere)" if len(diffs) > 3 else ""
    return _row("DBVO-Feldvergleich", "erwartet vs. übermittelt", MISMATCH,
                f"{len(diffs)} Abweichung(en): {detail}{more}.",
                case["id"], _CITE_VB)


def _flatten(value, prefix=""):
    if isinstance(value, dict):
        return [x for k, v in value.items() for x in _flatten(v, f"{prefix}.{k}" if prefix else k)]
    if isinstance(value, list):
        return [x for i, v in enumerate(value) for x in _flatten(v, f"{prefix}[{i}]")]
    return [prefix or "$"]


def _dig(value, path: str):
    cur = value
    for part in path.replace("]", "").replace("[", ".").split("."):
        if part == "":
            continue
        cur = cur[int(part)] if isinstance(cur, list) else cur.get(part)
    return cur


def _rule_row(case: dict) -> dict:
    """VB §3.12 trigger via the versioned module; honest NOT_EVALUATED on mixed kinds."""
    scenario = case.get("scenario") or {}
    insurance = scenario.get("insurance")
    if insurance == "PKV":
        sent = case.get("observed_dbvo") is not None
        status = MISMATCH if sent else PASS
        return _row("Regelprüfung", "PKV — außerhalb des Verfahrens (VB §3.12 S. 136)", status,
                    "Privat versichert: keine Vorerkrankungsanfrage (41) zulässig. "
                    + ("Übermittelter 41-DBVO festgestellt." if sent
                       else "Kein 41-DBVO übermittelt."),
                    case["id"], "VB 13.4 §3.12 S. 136")
    kinds = {scenario.get("current_reason")} | {
        p.get("reason") for p in scenario.get("prior") or []}
    if kinds - {None, "illness", "work accident", "rehabilitation", "hospital stay"}:
        return _row("Regelprüfung", _CITE_VB, NOT_EVALUATED,
                    "Ursachenart außerhalb der implementierten Menge — fachliche "
                    "Prüfung durch den Menschen (fail closed).", case["id"], _CITE_VB)
    try:
        current = vorerkrankung.Episode(
            scenario["current_start"], scenario.get("current_end"),
            attested=bool(scenario.get("current_cert")))
        prior = [vorerkrankung.Episode(p["start"], p["end"], attested=bool(p.get("cert")))
                 for p in scenario.get("prior") or []]
        result = vorerkrankung.evaluate(current, prior, scenario["today"])
    except (KeyError, ValueError, TypeError) as exc:
        return _row("Regelprüfung", _CITE_VB, NOT_EVALUATED,
                    f"Szenario nicht auswertbar ({exc}) — fail closed.", case["id"], _CITE_VB)
    expected_send = (case.get("expected") or {}).get("send_41")
    triggered = result.status == vorerkrankung.STATUS_TRIGGER
    if expected_send is None:
        return _row("Regelprüfung", _CITE_VB, NOT_EVALUATED,
                    "Keine Erwartung zur 41-Anfrage im Fall — nichts verglichen.",
                    case["id"], _CITE_VB)
    agrees = triggered == bool(expected_send)
    days = result.criteria.get("cumulative_30_days_12_months", {})
    detail = (f"{result.status} (vorher {days.get('days_prior', 0)} Tage "
              f"+ aktuell {days.get('days_current', 0)} = {days.get('days_total', 0)} Tage "
              f"innerhalb 12 Monaten ab {days.get('window_start', '?')})")
    return _row("Regelprüfung", f"Auslöser Vorerkrankungsanfrage ({_CITE_VB}, "
                                f"{vorerkrankung.MODULE_VERSION})",
                PASS if agrees else MISMATCH,
                f"{detail}; erwartet send_41={expected_send}.",
                case["id"], vorerkrankung.CITATION)


def _reply_row(case: dict) -> dict:
    """Story 4: 61-reply field rules as tagged by the generator taxonomy."""
    employer = case.get("employer_41") or {}
    reply = case.get("observed_61") or {}
    if not reply:
        return _row("61-Antwort-Prüfung", "VB 13.4 §3.12.2–3.12.14", NOT_EVALUATED,
                    "Keine 61-Antwortdaten im Fall.", case["id"], "VB 13.4 §3.12.2–3.12.14")
    problems: list[str] = []
    if reply.get("AU-AB-AG") != employer.get("AU-AB-AG"):
        problems.append(f"AU-AB-AG: 41={employer.get('AU-AB-AG')}, "
                        f"61={reply.get('AU-AB-AG')} (§3.12.x)")
    emp_periods = [tuple(p) for p in employer.get("periods") or []]
    rep_periods = [(p.get("BEGINN"), p.get("ENDE")) for p in reply.get("periods") or []]
    for period in emp_periods:
        if period not in rep_periods:
            problems.append(f"gemeldete Periode {period[0]}–{period[1]} fehlt in der "
                            "Antwort (§3.12.7)")
    positions = [rep_periods.index(p) for p in emp_periods if p in rep_periods]
    if positions != sorted(positions):
        problems.append("Reihenfolge der gemeldeten Perioden in der Antwort verletzt "
                        "(§3.12.7: aktuellste zuerst)")
    for period in reply.get("periods") or []:
        kz_n, kz_au = str(period.get("KZ-NACHWEIS", "")), str(period.get("KZ-AU", ""))
        teil_n = [t for t in period.get("TEIL-NACHWEIS") or [] if str(t) != "00000000"]
        teil_a = [t for t in period.get("TEIL-ANR") or [] if str(t) != "00000000"]
        if kz_n == "4" and kz_au != "2":
            problems.append(f"KZ-NACHWEIS 4 mit KZ-AU {kz_au} "
                            f"(BEGINN {period.get('BEGINN')})")
        if kz_n != "2" and teil_n:
            problems.append(f"TEIL-NACHWEIS gefüllt ohne KZ-NACHWEIS 2 "
                            f"(BEGINN {period.get('BEGINN')})")
        if kz_au != "5" and teil_a:
            problems.append(f"TEIL-ANR gefüllt ohne KZ-AU 5 (BEGINN {period.get('BEGINN')})")
    if str(reply.get("KZ-AK-AU", "")) == "4" and str(reply.get("12-MONATSFRIST-AB", "")) not in (
            "", "00000000"):
        problems.append("KZ-AK-AU 4, aber 12-MONATSFRIST-AB gefüllt")
    tag = case.get("must_flag")
    status = MISMATCH if problems else PASS
    reason = ("Alle geprüften 61-Feldregeln eingehalten "
              f"({len(reply.get('periods') or [])} Perioden, "
              f"ANZAHL-AU {reply.get('ANZAHL-AU')})."
              if not problems else f"{len(problems)} Regelverstoß/öse: " + "; ".join(problems[:3])
              + (f" (+{len(problems) - 3} weitere)" if len(problems) > 3 else ""))
    return _row("61-Antwort-Prüfung", f"VB 13.4 §3.12.2–3.12.14 (Taxonomie-Tag {tag})", status,
                reason, case["id"],
                (case.get("expected") or {}).get("source") or "VB 13.4 §3.12.2–3.12.14")


def _ddmmyyyy(value: str) -> str | None:
    try:
        d, m, y = value.split(".")
        return f"{y}-{m}-{d}"
    except (AttributeError, ValueError):
        return None


def _flow_rows(case: dict) -> list[dict]:
    """Story 6: cancel-and-correct flow checks (GG EEL 13.1 §2.5)."""
    messages = case.get("messages") or []
    scenario = case.get("scenario") or {}
    tag = case.get("must_flag")
    cite = (case.get("expected") or {}).get("source") or "GG EEL 13.1 §2.5"
    rows = []
    if not messages:
        return [_row("Ablauf-Prüfung", "GG EEL 13.1 §2.5", NOT_EVALUATED,
                     "Keine Nachrichten im Fall.", case["id"], cite)]
    azvus = {m.get("AZVU") for m in messages}
    rows.append(_row("Ablauf/AZVU", "AZVU durchgängig identisch",
                     PASS if len(azvus) == 1 else MISMATCH,
                     f"{len(azvus)} verschiedene AZVU-Werte im Ablauf."
                     if len(azvus) != 1 else f"AZVU {next(iter(azvus))} in allen "
                     f"{len(messages)} Nachrichten.", case["id"], cite))
    ag = [m for m in messages if m.get("from") == "AG"]
    ones = [m for m in ag if m.get("Abgabegrund") == "01"]
    eights = [m for m in ag if m.get("Abgabegrund") == "88"]
    for m in eights:
        if m.get("Stornierung") != "J":
            rows.append(_row("Ablauf/88-Kennzeichnung", "88 mit Stornierung J", MISMATCH,
                             f"88 (Nr. {m.get('no')}) trägt Stornierung="
                             f"{m.get('Stornierung')!r}.", case["id"], cite))
    last_one = ones[-1] if ones else None
    for m in eights:
        target = next((o for o in reversed(ones) if o["no"] < m["no"]), None)
        if target is None or m.get("DSID-UR") != target.get("DSID"):
            rows.append(_row("Ablauf/88-Referenz", "88 storniert die letzte 01", MISMATCH,
                             f"88 (Nr. {m.get('no')}) referenziert DSID-UR="
                             f"{m.get('DSID-UR')}, erwartet DSID der letzten 01 "
                             f"({target.get('DSID') if target else 'keine 01 vorhanden'}).",
                             case["id"], cite))
    if last_one is not None and eights:
        corrected = [o for o in ones if o["no"] > eights[-1]["no"]]
        if not corrected:
            rows.append(_row("Ablauf/Korrektur-01", "01-Korrektur nach der 88", MISMATCH,
                             "Nach der letzten 88 folgt keine korrigierte 01.",
                             case["id"], cite))
    final_efz = _ddmmyyyy(scenario.get("expected_efz_final") or "")
    if last_one is not None and final_efz:
        sent_efz = _ddmmyyyy(last_one.get("EFZ_Ende") or "")
        rows.append(_row("Ablauf/EFZ-Ende", "korrigiertes EFZ-Ende = erwartetes Datum",
                         PASS if sent_efz == final_efz else MISMATCH,
                         f"Letzte 01 meldet EFZ_Ende={last_one.get('EFZ_Ende')}, "
                         f"erwartet {scenario.get('expected_efz_final')}.",
                         case["id"], cite))
    for m in messages:
        if m.get("Abgabegrund") == "62":
            valid_ref = last_one is not None and m.get("REF-ID") == last_one.get("DSID")
            rows.append(_row("Ablauf/62-Referenz", "62 referenziert die gültige 01",
                             PASS if valid_ref else MISMATCH,
                             f"62 (Nr. {m.get('no')}) REF-ID={m.get('REF-ID')}, "
                             f"gültige 01 DSID={last_one.get('DSID') if last_one else '?'}.",
                             case["id"], cite))
        if m.get("Abgabegrund") == "61" and m.get("from") == "KK":
            ref41 = next((a for a in ag if a.get("Abgabegrund") == "41"
                          and a.get("no") < m["no"]), None)
            valid_ref = ref41 is not None and m.get("REF-ID") == ref41.get("DSID")
            rows.append(_row("Ablauf/61-Referenz", "61 referenziert die 41",
                             PASS if valid_ref else MISMATCH,
                             f"61 (Nr. {m.get('no')}) REF-ID={m.get('REF-ID')}, "
                             f"41 DSID={ref41.get('DSID') if ref41 else '?'}.",
                             case["id"], cite))
    if len(rows) == 1:  # only AZVU so far — flow had no structured checks to run
        rows.append(_row("Ablauf-Prüfung", "GG EEL 13.1 §2.5", NOT_EVALUATED,
                         "Ablauf enthält keine 01/88/61/62-Struktur für die "
                         "Stornoprüfung.", case["id"], cite))
    return rows


def _ground_truth_row(case: dict, rows: list[dict]) -> dict:
    flagged = any(r["result_status"] == MISMATCH for r in rows)
    tag = case.get("must_flag")
    expected_flag = tag is not None
    agrees = flagged == expected_flag
    if agrees:
        return _row("Ground-Truth-Abgleich", "unabhängige Kennzeichnung (Generator, Seed 4136)",
                    PASS, f"SÜSIE-Befund ({'MISMATCH' if flagged else 'kein Befund'}) "
                          f"stimmt mit der Regeltaxonomie überein (must_flag={tag}).",
                    case["id"], "testCase-stories.md; harness/generate_story_cases.py")
    return _row("Ground-Truth-Abgleich", "unabhängige Kennzeichnung (Generator, Seed 4136)",
                MISMATCH, f"ABWEICHUNG zur unabhängigen Kennzeichnung: SÜSIE "
                          f"{'fand Abweichungen' if flagged else 'fand keine Abweichungen'}, "
                          f"must_flag={tag} — menschliche Prüfung erforderlich.",
                case["id"], "testCase-stories.md; harness/generate_story_cases.py")


def evaluate_case(case: dict) -> dict:
    """Build the report artifact for one story case (deterministic layers)."""
    case_id = case["id"]
    rows: list[dict] = []
    if case["story"] in (1, 3):
        rows.append(_dbvo_row(case))
        rows.append(_rule_row(case))
    elif case["story"] == 4:
        rows.append(_reply_row(case))
    elif case["story"] == 6:
        rows += _flow_rows(case)
    rows.append(_ground_truth_row(case, rows))

    scenario = case.get("scenario") or {}
    tag = case.get("must_flag")
    context = [
        ["Story", f"{case['story']} — {STORY_RULES.get(case['story'], '')}"],
        ["Kategorie", case["category"]],
        ["Regeltaxonomie-Tag", str(tag)],
        ["Versicherung / Stichtag", f"{scenario.get('insurance', '—')} / "
                                    f"{scenario.get('today', '—')}"],
    ]
    mismatches = sum(1 for r in rows if r["result_status"] == MISMATCH)
    notevals = sum(1 for r in rows if r["result_status"] == NOT_EVALUATED)
    return {
        "report_id": f"SHOWCASE-{case_id}",
        "template_id": "TPL-SYNTH-1",
        "template_version": "synthetic-0.1",
        "template_warning": ("SYNTHETIC TEMPLATE PROFILE — NOT an official ITSG form "
                             "profile. Conformance checks against this profile say nothing "
                             "about official-form compliance."),
        "official_form_id": None,
        "renderer_version": SHOWCASE_VERSION,
        "field_map_version": "itsg.storyfieldmap/synth-1",
        "generated_at": utc_now(),
        "field_labels": {"case_id": "Prüfaspekt", "criterion_id": "Regel/Grundlage",
                         "result_status": "Ergebnisstatus", "reason": "Begründung",
                         "evidence_links": "Belegkette"},
        "compliance_claim": False,
        "compliance_claim_reason": ("synthetic template (official_form_id=None): no legal or "
                                    "template compliance claim may be derived; showcase on "
                                    "fabricated data only"),
        "context": context,
        "results": rows,
        "counts": {"PASS": len(rows) - mismatches - notevals,
                   "MISMATCH": mismatches, "NOT_EVALUATED": notevals},
        "case_id": case_id,
    }


def build_all(cases_path: str | Path, out_dir: str | Path,
              generated_at: str | None = None) -> list[dict]:
    """Select, evaluate, render; returns the per-case metadata list."""
    from . import report_pdf

    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta_all = []
    for case in select_cases(cases):
        artifact = evaluate_case(case)
        artifact_path = out_dir / f"artifact-{case['id']}.json"
        artifact_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        meta = report_pdf.generate_report_pdf(
            artifact_path, out_dir / f"SUSIE-showcase-{case['id']}.pdf",
            client_name=f"SÜSIE Story-Showcase · Fall {case['id']} (synthetische Demodaten)",
            generated_at=generated_at)
        meta["case_id"] = case["id"]
        meta["story"] = case["story"]
        meta["category"] = case["category"]
        meta["counts"] = artifact["counts"]
        meta_all.append(meta)
    (out_dir / "index.json").write_text(
        json.dumps(meta_all, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta_all


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        prog="itsg.story_pdfs", description="SÜSIE story-case showcase PDFs (T10-037)")
    parser.add_argument("--cases", default=str(root / "data" / "story_cases.json"))
    parser.add_argument("--out", default=str(root / "reports" / "story-showcase"))
    args = parser.parse_args(argv)
    meta = build_all(args.cases, args.out)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
