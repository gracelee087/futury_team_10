"""Independent review set for the Datenschutz-Schleuse (T10-007).

These 10 records were written by an independent reviewer, not by the author of schleuse.py
(the author's own tests are in test_schleuse.py and test_leak.py). They are kept unchanged and separate.
First run, before any fix: 18 of 19 planted values were caught, 1 leaked ("Jonas Bergmann" after the
role cue "Versicherter:" with a colon). The detector was then fixed and this file added; the result
after the fix is what pytest shows now. Do not edit the records to make them pass.
"""
import pytest

from privacy.schleuse import pseudonymize

KEY = "independent-review-key-0123"

RECORDS = [
    ("Die Arbeitnehmerin Selin Kaya (SV-Nr. 65 120387 K 512) ist seit 03.02.2026 arbeitsunfähig.",
     ["Selin Kaya", "65 120387 K 512"]),
    ("Rückfragen bitte an h.vogt@lohnbuero-vogt.de oder 0171 2345678.",
     ["h.vogt@lohnbuero-vogt.de", "0171 2345678"]),
    ("Versicherter: Jonas Bergmann, geb. 14.07.1991, wohnhaft Lindenallee 12, 60311 Frankfurt am Main",
     ["Jonas Bergmann", "14.07.1991", "Lindenallee 12", "60311 Frankfurt am Main"]),
    ("Bitte die Erstattung auf DE89 3704 0044 0532 0130 00 überweisen.", ["DE89 3704 0044 0532 0130 00"]),
    ("VSNR 12030575M004 – Krankengeld ab dem 43. Tag.", ["12030575M004"]),
    ("Herr Dr. Klaus-Peter Hoffmann hat die AU vom 01.03. bis 15.03.2026 eingereicht.", ["Klaus-Peter Hoffmann"]),
    ("Ansprechpartnerin: Frau Meier-Schulz, Tel. +49 69 1234-567", ["Meier-Schulz", "+49 69 1234-567"]),
    ("Geburtsdatum 1985-11-30, Name: Ayşe Yılmaz", ["1985-11-30", "Ayşe Yılmaz"]),
    ("Die Betriebsnummer 87654321 des Arbeitgebers ist hinterlegt.", ["87654321"]),
    ("Mitarbeiter Lukas Weber, Mozartstraße 7a, 80336 München, war krank.",
     ["Lukas Weber", "Mozartstraße 7a", "80336 München"]),
]
CASES = [(i + 1, text, value) for i, (text, values) in enumerate(RECORDS) for value in values]


def test_independent_set_has_19_planted_values():
    assert len(RECORDS) == 10 and len(CASES) == 19


@pytest.mark.parametrize("number,text,value", CASES, ids=[f"rec{n}-{v[:18]}" for n, _t, v in CASES])
def test_planted_value_is_removed(number, text, value):
    clean, _summary = pseudonymize(text, KEY)
    assert value not in clean
    # parts of a name must not survive either
    if " " in value and value[0].isupper() and not value[0].isdigit() and "@" not in value:
        for part in value.split():
            assert part not in clean.split(), part
