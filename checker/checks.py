import json, sys
from datetime import datetime

RULE_VERSION = "checks.py 0.2"

# Source IDs are placeholders until Member 1 confirms the shared ID format
SOURCES = {
    "SRC-TK": "ITSG Hinweise_DTA-EEL-Bespiel_Vorerkrankung_Testkonstellation.docx",
    "SRC-GG": "Gemeinsame Grundsaetze DTA EEL, Version 13.1, Stand 06.05.2025",
    "SRC-VB": "Verfahrensbeschreibung DTA EEL, Version 13.4, Stand 10.03.2026",
}

EXPECTED = {
    "AZVU": "1234-5678-007",
    "EFZ_Ende_final": "27.03.2026",
}

def valid_date(s):
    try:
        datetime.strptime(s, "%d.%m.%Y")
        return True
    except (TypeError, ValueError):
        return False

def run_checks(case):
    m = case.get("messages", [])
    tc = case.get("test_case_id", "TC-1")
    run = case.get("run_id", "RUN-1")
    out = []

    def add(cid, rule, src, locator, verified, field, expected, observed, missing=None):
        if missing:
            status, reason = "NOT_EVALUATED", missing
        elif expected is None:
            status, reason = "NOT_EVALUATED", "No approved expected value"
        elif expected == observed:
            status, reason = "PASS", "Observed value equals expected value"
        else:
            status, reason = "MISMATCH", f"Field '{field}': expected {expected!r}, observed {observed!r}"
        out.append({"finding_id": f"F-{run}-{cid}", "check_id": cid, "status": status,
                    "reason": reason, "rule": rule, "field": field,
                    "expected": expected, "observed": observed,
                    "citation": {"source_id": src, "source": SOURCES[src], "locator": locator,
                                 "status": "verified" if verified else "needs_review"},
                    "rule_version": RULE_VERSION, "links": [src, tc, run],
                    "id": cid, "source": f"{SOURCES[src]} - {locator}", "actual": observed})

    codes = [x.get("Abgabegrund") for x in m]
    ag01 = [i for i, x in enumerate(m) if x.get("Abgabegrund") == "01"]
    st88 = [i for i, x in enumerate(m) if x.get("Abgabegrund") == "88"]
    no88 = None if st88 else "No cancellation (88) in observed output"

    add("C1", "All messages use the same AZVU", "SRC-TK", "ID table, column AZVU", True,
        "AZVU", [EXPECTED["AZVU"]], sorted({str(x.get("AZVU")) for x in m}))
    add("C2", "Exactly one cancellation (88) is sent", "SRC-TK", "ID table, Abgabegrund rows", True,
        "count(Abgabegrund=88)", 1, len(st88))
    add("C3", "The cancellation is flagged Stornierung = J", "SRC-TK", "ID table, column Stornierung", True,
        "Stornierung", "J", m[st88[0]].get("Stornierung") if st88 else None, no88)
    add("C4", "DSID-UR of the 88 references the cancelled 01 message", "SRC-GG",
        "Section 2.5, page 13: DATENSATZ-ID-URSPRUNGSMELDUNG is always filled", True,
        "DSID-UR", m[ag01[0]].get("DSID") if ag01 else None,
        m[st88[0]].get("DSID-UR") if st88 else None,
        None if (st88 and ag01) else "No 88 or no earlier 01 in observed output")
    add("C5", "A new corrected 01 is sent after the cancellation", "SRC-GG",
        "Section 2.5, page 13: new message with correct data after cancellation", True,
        "01 after 88", True, bool(st88) and any(i > st88[0] for i in ag01), no88)
    add("C6", "Final sick-pay end (EFZ) after the correction", "SRC-TK",
        "Text: EFZ ends 27.03.2026 after the corrected 61", True,
        "EFZ_Ende", EXPECTED["EFZ_Ende_final"], m[ag01[-1]].get("EFZ_Ende") if ag01 else None,
        None if ag01 else "No 01 message in observed output")
    add("C7", "Prior-illness request (41) comes before the first 01", "SRC-TK", "ID table, row order", True,
        "order(41 before 01)", True,
        "41" in codes and "01" in codes and codes.index("41") < codes.index("01"))
    dates = [x[f] for x in m for f in ("Beginn_12_Monatsfrist", "EFZ_Ende", "Ende_EEL") if f in x]
    add("C8", "All dates are valid calendar dates (DD.MM.YYYY)", "SRC-VB",
        "Date field format: section not yet located", False,
        "date fields", True, all(valid_date(d) for d in dates))
    return out

if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8-sig") as f:
        case = json.load(f)
    findings = run_checks(case)
    for r in findings:
        flag = "" if r["citation"]["status"] == "verified" else "  (citation needs review)"
        print(f"[{r['status']}] {r['check_id']} {r['rule']}{flag}")
        if r["status"] != "PASS":
            print(f"        {r['reason']}")
    counts = {s: sum(r["status"] == s for r in findings) for s in ("PASS", "MISMATCH", "NOT_EVALUATED")}
    print(f"\n{counts}")
    with open("data/findings.json", "w", encoding="utf-8") as f:
        json.dump(findings, f, indent=2, ensure_ascii=False)
