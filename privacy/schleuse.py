"""Datenschutz-Schleuse (privacy airlock): find, replace and re-check personal data. T10-007.

Deterministic, standard library only, no AI. Three jobs:

  pseudonymize(text_or_record, key) -> (clean, summary)   replace values with typed tokens (VSNR_1, PERSON_1, ...)
  check_clean(text)                 -> [Hit, ...]         last gate: anything found here means BLOCK
  scrub_for_log(text)               -> str                logs may hold no personal data at all

Tokens are stable inside one run: the same value always gets the same token. Identity is decided with
HMAC-SHA256 (key from env PRIVACY_KEY), so the lookup table never holds a raw value as a key. The summary
holds counts per category only, never a value.

What is NOT personal on its own (and why):
  * AU dates (Arbeitsunfaehigkeit begin/end, e.g. 20260311) and other plain dates. They only become personal
    data when tied to a person, and in this tool they are always fabricated or already pseudonymized together
    with the person. Treating every date as personal would blank out the rulebook. A date is flagged only
    when it is a birth date: after a cue word (geboren am, Geburtsdatum, geb.) or derived from a
    Versicherungsnummer found in the same text.
  * Abgabegrund codes (2 digits), DSIDs / Datensatz-IDs (UUIDs), section numbers (3.1.18), page numbers and
    Datenbaustein names (DBVO, DBNA ...). They are rule vocabulary or technical ids with no link to a person.
    Several of them look like numbers or dates, so the digit patterns below demand a context or a checksum.

Honest limits are listed in privacy/README.md (free-text names without a cue word are not found, and
pseudonymized data is still personal data under GDPR).
"""
import calendar
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional, Tuple

POLICY_VERSION = "privacy-policy-v1"
KEY_ENV = "PRIVACY_KEY"
MIN_KEY_CHARS = 16

CATEGORIES = ("VSNR", "BBNR", "IBAN", "EMAIL", "PHONE", "DOB", "PERSON", "ADDRESS")
_PRIORITY = {c: i for i, c in enumerate(CATEGORIES)}  # lower = wins when two matches overlap

# Per destination: what may leave the system and in which form.
POLICY: Dict[str, dict] = {
    "hessian_ai": {"mode": "pseudonymize", "allowed": True, "final_gate": "block_if_any_hit"},
    "langfuse": {"mode": "pseudonymize", "minimize": True, "allowed": True, "max_string_chars": 200,
                 # top-level keys only; everything not listed here is dropped before it can reach Langfuse
                 "allowed_keys": (
                     "run_id", "report_id", "id", "status", "check", "rule", "source", "expected", "actual", "reason",
                     "scenario", "count", "counts", "total", "messages", "overall_status", "robustness", "result",
                     "tool", "baseline", "attacks", "attack", "kind", "failed_checks", "categories", "policy_version",
                     "report", "findings", "level", "criterion_id", "case_id", "category", "group", "must_flag",
                     "observed_dbvo", "flagged", "outcome", "reviewer", "data", "git_sha",
                     # parsed DBVO fields (no names, no VSNR) from run_review.parse_teel0
                     "ABGABEGRUND", "ANZAHL-AU", "AU-AB-AG", "AU-AB-SV", "KZ-AK-AU", "GRUNDAV", "DATENSATZ-ID",
                     "DATUM-ERSTELLUNG", "AU-ZEITRAEUME", "error")},
    "seal": {"mode": "hash_only", "allowed": True},
    "logs": {"mode": "none", "allowed": True},
}


class PrivacyBlocked(Exception):
    """Personal data was still present at a gate. Carries categories only, never values."""

    def __init__(self, categories):
        self.categories = sorted(set(categories))
        super().__init__("personal data still present after pseudonymization: " + ", ".join(self.categories))


class PrivacyConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Hit:
    """A remaining personal-data hit. Deliberately has no value field, so it is safe to log."""
    category: str
    start: int
    end: int


@dataclass(frozen=True)
class _Span:
    start: int
    end: int
    category: str
    value: str


# ---------------------------------------------------------------- validation helpers

def _valid_date(day: int, month: int, year: Optional[int]) -> bool:
    if not 1 <= month <= 12 or day < 1:
        return False
    if year is None:
        return day <= calendar.monthrange(2000, month)[1]  # 2-digit year: allow 29 Feb
    return day <= calendar.monthrange(year, month)[1]


def _iban_ok(chars: List[str]) -> bool:
    rearranged = chars[4:] + chars[:4]
    number = "".join(str(int(c, 36)) for c in rearranged)
    return int(number) % 97 == 1


_IBAN_LENGTH = {"DE": 22, "AT": 20, "CH": 21, "LI": 21, "LU": 20, "FR": 27, "BE": 16, "NL": 18, "IT": 27,
                "ES": 24, "PT": 25, "PL": 28, "CZ": 24, "DK": 18, "SE": 24, "NO": 15, "FI": 18, "IE": 22,
                "GB": 22, "GR": 27, "HU": 28, "SK": 24, "SI": 19, "HR": 21, "BG": 22, "RO": 24, "CY": 28,
                "MT": 31, "LT": 20, "LV": 21, "EE": 20, "TR": 26}

# ---------------------------------------------------------------- detectors

_VSNR_COMPACT = re.compile(r"(\d{2})(\d{2})(\d{2})(\d{2})([A-Z])(\d{3})")  # no boundary: DTA fields touch
_VSNR_SPACED = re.compile(r"(?<![A-Za-z0-9])(\d{2})[ \-]?(\d{2})(\d{2})(\d{2})[ \-]?([A-Z])[ \-]?(\d{3})(?!\d)")


def _vsnr_spans(text: str):
    for pattern in (_VSNR_COMPACT, _VSNR_SPACED):
        for m in pattern.finditer(text):
            area, dd, mm, yy, _letter, _serial = m.groups()
            if area != "00" and _valid_date(int(dd), int(mm), None):
                yield _Span(m.start(), m.end(), "VSNR", m.group(0))


def _birth_forms(vsnr: str):
    """Spellings of the birth date inside a VSNR (area 2, DDMMYY, letter, serial 3)."""
    digits = re.sub(r"[^0-9A-Z]", "", vsnr)
    dd, mm, yy = digits[2:4], digits[4:6], digits[6:8]
    for century in (19, 20):
        yyyy = f"{century}{yy}"
        if _valid_date(int(dd), int(mm), int(yyyy)):
            yield from (f"{yyyy}{mm}{dd}", f"{dd}.{mm}.{yyyy}", f"{yyyy}-{mm}-{dd}", f"{dd}{mm}{yyyy}")


_BBNR_CONTEXT = re.compile(r"(?i)(?:betriebsnummer|betriebsnr\.?|bbnr)\b[^\d\n]{0,25}?(\d{8})(?!\d)")
_DTA_HEADER = r"(?:(?<![A-Za-z0-9])|(?<=\\n))(?:VOS[A-Z]|NCS[A-Z]|DS[A-Z]{2})[A-Z]{5}"  # record id + procedure, then the BBNR
_BBNR_DTA_HEADER = re.compile(_DTA_HEADER + r"(\d{8})")
_DTA_HEADER_ANY = re.compile(_DTA_HEADER + r"\d{8}")

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")

_PHONE = [
    re.compile(r"(?<![\w.+])(?:\+|00)49[ \t\-/.]*(?:\(0\)[ \t]*)?0?[1-9]\d{1,4}(?:[ \t\-/.]?\d{2,}){1,3}(?!\d)"),
    re.compile(r"(?<![\w.+])\+(?!49)[1-9]\d{0,2}[ \t\-.]?(?:\(\d+\)[ \t]*)?\d{2,4}(?:[ \t\-.]?\d{2,}){1,3}(?!\d)"),
    re.compile(r"(?<![\w.+])\(0[1-9]\d{1,4}\)[ \t]?\d{3,}(?:-\d{1,4})?(?!\d)"),
    re.compile(r"(?<![\w.+])0[1-9]\d{1,4}[ \t/\-]\d{4,}(?:-\d{1,4})?(?!\d)"),  # 4+ digits: "031-048" is a field range
    re.compile(r"(?<![\w.+])01[5-7]\d{8,9}(?!\d)"),
]
_PHONE_CUE = re.compile(
    r"(?i)\b(?:tel(?:efon)?|fon|fax|mobil(?:funk)?|handy|phone|rufnummer)\b\.?\s*(?:nr\.?|nummer)?\s*[:=]?\s*"
    r"(\+?[\d(][\d \t()/\-.]{4,22}\d)")

_DATE_VALUE = r"(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})|(\d{4})-(\d{2})-(\d{2})|(\d{8})"
_DOB_CUE = re.compile(
    r"(?i)(?:geburtsdatum|geburtstag|geboren(?:\s+am)?|geb\.(?:\s*am)?|\bgeb\b|date\s+of\s+birth|\bdob\b|\bborn(?:\s+on)?)"
    r"[\s:=]*(" + _DATE_VALUE + r")")

_LETTERS = r"[^\W\d_]"
_NAME_WORD = rf"[A-ZÄÖÜ]{_LETTERS}*(?:[-'’]{_LETTERS}+)*(?!\w)"
_PARTICLE = r"(?:(?:von|van|de|vom|la|le|di|da)[ \t]+)?"  # not "der/zu/zur": they are ordinary words
_NAME_1_3 = rf"{_PARTICLE}{_NAME_WORD}(?:[ \t]+{_PARTICLE}{_NAME_WORD}){{0,2}}"
_NAME_2_3 = rf"{_NAME_WORD}(?:[ \t]+{_PARTICLE}{_NAME_WORD}){{1,2}}"

_NAME_FIELD = re.compile(
    r"(?i:\b(?:familienname|vorname|nachname|zuname|geburtsname|versichertenname|ansprechpartner(?:in)?|name)\b)"
    r"[ \t]*[:=][ \t]*(" + _NAME_1_3 + ")")  # no "|": "Name | Vorname" is a table header in the rulebook
_SALUTATION = re.compile(r"\b(?:Herrn?|Frau|Fr\.|Hr\.|Dr\.|Prof\.)[ \t]+(?:Dr\.[ \t]+)?(" + _NAME_1_3 + ")")
_ROLE_CUE = re.compile(
    r"\b(?:Versicherte[rn]?|Arbeitnehmer(?:in)?|Mitarbeiter(?:in)?|Patient(?:in)?|Antragsteller(?:in)?|Kunde|Kundin|"
    r"Beschäftigte[rn]?|Leistungsempfänger(?:in)?)[ \t]+(" + _NAME_2_3 + ")")
_ROLE_COLON = re.compile(  # "Versicherter: Jonas Bergmann" - with a colon one name word is enough
    r"\b(?:Versicherte[rn]?|Arbeitnehmer(?:in)?|Mitarbeiter(?:in)?|Patient(?:in)?|Antragsteller(?:in)?|Kunde|Kundin|"
    r"Beschäftigte[rn]?|Leistungsempfänger(?:in)?)[ \t]*:[ \t]*(" + _NAME_1_3 + ")")
_SELF_CUE = re.compile(r"(?i:mein name ist|ich heiße|ich heisse|name lautet|namens)[ \t]+(" + _NAME_1_3 + ")")

# Capitalised German nouns that follow a cue word but are not names ("Versicherte Person", "Frau Dr.").
_NOT_A_NAME = frozenset(
    "person personen daten datensatz datensaetze datensätze abgabegrund krankenkasse arbeitgeber arbeitnehmer "
    "versicherter versicherte versicherten mitarbeiter mitarbeiterin patient patientin kunde kundin herr frau "
    "name vorname nachname familienname geburtsdatum meldung mitteilung anforderung antwort anfrage beschäftigung "
    "beschaeftigung entgelt leistung leistungen bescheinigung arbeitsunfähigkeit arbeitsunfaehigkeit "
    "einzugsstelle einzugsstellen sozialversicherung rentenversicherung krankenversicherung dienstleister "
    "sachbearbeiter sachbearbeiterin ansprechpartner ansprechpartnerin vertrag zeitraum zeitraeume zeitraume "
    "bitte wie was wann wer wo warum welche welcher".split())

_NOUN_ENDINGS = ("geld", "ung", "keit", "heit", "schaft", "nummer", "klasse", "linge", "tion", "ität", "kasse",
                 "geber", "nehmer", "zeit", "bescheinigung", "versicherung", "erkrankung", "unfähigkeit")

_STREET_SUFFIX = r"stra(?:ß|ss|�)e|str\."
_STREET_OTHER = r"weg|allee|platz|gasse|ring|damm|ufer|chaussee|steig|pfad"
_STREET = re.compile(
    rf"(?<![^\W\d_])[A-ZÄÖÜ][A-Za-zäöüÄÖÜß\-]*(?:(?:{_STREET_SUFFIX})(?:[ \t]{{1,40}}\d{{1,4}}[ \t]?[a-zA-Z]?(?:[ \t]*-[ \t]*\d{{1,4}})?)?"
    rf"|(?:{_STREET_OTHER})[ \t]{{1,40}}\d{{1,4}}[ \t]?[a-zA-Z]?(?:[ \t]*-[ \t]*\d{{1,4}})?)(?!\w)")
_STREET_PREPOSITION = re.compile(
    r"\b(?:Am|An der|Auf dem|Auf der|Im|In der|Zum|Zur|Unter den|Hinter dem)[ \t]+[A-ZÄÖÜ][A-Za-zäöüÄÖÜß\-]*(?:berg|tal|hof|markt|mühle|muehle|weg|feld|wiese|garten|bach|brücke|bruecke|anger|park|wald|"
    r"ring|platz|damm|ufer|graben|kamp|busch|stein|höhe|hoehe|eck|winkel|born|brunnen)[ \t]+\d{1,4}[ \t]?[a-zA-Z]?(?!\w)")  # "Am Mühlenberg 4", not "Im Abschnitt 4"
_POSTCODE = re.compile(
    rf"(?<!\d)(0[1-9]\d{{3}}|[1-9]\d{{4}})(?!\d)[ \t]+([A-ZÄÖÜ]{_LETTERS}+(?:(?:[ ](?:am|an der|im|ob der)[ ]|[ \-])[A-ZÄÖÜ]{_LETTERS}+){{0,2}})")
_NOT_A_CITY = frozenset(
    "zeichen stellen bytes datensätze datensatz datensaetze euro cent tage tagen mal satz sätze saetze seiten "
    "stunden monate monaten jahre jahren prozent personen buchstaben ziffern felder zeilen".split())

_ORG_WORDS = ("gmbh", "ag", "kg", "ohg", "firma", "kasse", "bkk", "aok", "itsg", "svt", "qualit", "verband",
              "stelle", "amt", "gesellschaft", "stiftung", "versicherung")
_RUN = re.compile(r"\S+(?: \S+)*")  # a run of text; two or more spaces end it (fixed-width fields)
_TWO_CAPITALISED = re.compile(r"[A-ZÄÖÜ][a-zäöüß]+ [A-ZÄÖÜ][a-zäöüß]+")

# Public specimen values in the ITSG rulebook (Beispiel chunks). Only used when checking public chunks.
SPECIMEN_MARK = "muster"
SPECIMEN_EXACT = frozenset({"max", "erika", "maxi", "max mustermann", "erika mustermann"})


def _name_ok(value: str) -> bool:
    words = re.split(r"[ \t\-]+", value.strip())
    if not words or any(len(w) < 2 for w in words):
        return False
    return not all(w.casefold().rstrip(".") in _NOT_A_NAME for w in words)


def _group_span(m: "re.Match", group: int, category: str) -> _Span:
    return _Span(m.start(group), m.end(group), category, m.group(group))


def _iban_spans(text: str):
    for m in re.finditer(r"(?<![0-9])([A-Za-z]{2})\d{2}(?=[ ]?[A-Za-z0-9])", text):
        length = _IBAN_LENGTH.get(m.group(1).upper())
        if not length:
            continue
        chars, j = [], m.start()
        while j < len(text) and len(chars) < length:
            ch = text[j]
            if ch.isascii() and ch.isalnum():
                chars.append(ch.upper())
                j += 1
            elif ch == " " and j + 1 < len(text) and text[j + 1].isascii() and text[j + 1].isalnum():
                j += 1
            else:
                break
        if len(chars) == length and _iban_ok(chars):
            yield _Span(m.start(), j, "IBAN", text[m.start():j])


def _phone_spans(text: str):
    for pattern in _PHONE:
        for m in pattern.finditer(text):
            yield _Span(m.start(), m.end(), "PHONE", m.group(0))
    for m in _PHONE_CUE.finditer(text):
        if 6 <= len(re.sub(r"\D", "", m.group(1))) <= 15:
            yield _group_span(m, 1, "PHONE")


def _dob_spans(text: str):
    for m in _DOB_CUE.finditer(text):
        g = m.groups()  # g[1:4] dotted, g[4:7] ISO, g[7] compact
        if g[2] is not None:
            options = [(int(g[1]), int(g[2]), int(g[3]) if len(g[3]) == 4 else None)]
        elif g[4] is not None:
            options = [(int(g[6]), int(g[5]), int(g[4]))]
        else:
            d = g[7]  # YYYYMMDD or DDMMYYYY: accept whichever reads as a real date
            options = [(int(d[6:]), int(d[4:6]), int(d[:4])), (int(d[:2]), int(d[2:4]), int(d[4:]))]
        if any((y is None or 1900 <= y <= date.today().year) and _valid_date(dd, mm, y) for dd, mm, y in options):
            yield _group_span(m, 1, "DOB")


def _address_spans(text: str):
    for m in _STREET.finditer(text):
        yield _Span(m.start(), m.end(), "ADDRESS", m.group(0))
    for m in _STREET_PREPOSITION.finditer(text):
        yield _Span(m.start(), m.end(), "ADDRESS", m.group(0))
    for m in _POSTCODE.finditer(text):
        if m.group(2).split()[0].casefold() not in _NOT_A_CITY:
            yield _Span(m.start(), m.end(), "ADDRESS", m.group(0))


def _trimmed_name(text: str, start: int, end: int) -> Optional[_Span]:
    """Cut a captured name at the first word that is a field label (followed by = or :) or a common noun."""
    last = None
    for token in re.finditer(r"\S+", text[start:end]):
        stop = start + token.end()
        word = token.group(0).casefold().rstrip(".,;")
        if text[stop:stop + 1] in ("=", ":", "-") or word in _NOT_A_NAME or (  # "Arznei-, Verband-" is a cut compound
                len(word) > 8 and word.endswith(_NOUN_ENDINGS)):  # "Frau Mutterschaftsgeld" is a noun, not a name
            break
        last = stop
    if last is None or not _name_ok(text[start:last]):
        return None
    return _Span(start, last, "PERSON", text[start:last])


def _cue_names(pattern, text: str):
    """Names after a cue word. Scanning resumes right after the trimmed name, so "A=x B=y" finds both."""
    pos = 0
    while True:
        m = pattern.search(text, pos)
        if not m:
            return
        span = _trimmed_name(text, m.start(1), m.end(1))
        if span:
            yield span
        pos = max(span.end if span else m.end(1), m.start() + 1)


def _person_spans(text: str):
    for pattern in (_NAME_FIELD, _SALUTATION, _ROLE_CUE, _ROLE_COLON, _SELF_CUE):
        yield from _cue_names(pattern, text)
    # fixed-width DTA records: names sit in known blocks, separated by two or more spaces
    for m in _DTA_HEADER_ANY.finditer(text):
        stop = min([i for i in (text.find("\n", m.start()), text.find("\r", m.start()), text.find("\\n", m.start()))
                    if i != -1], default=len(text))
        yield from _dta_name_spans(text[m.start():stop], m.start())


def _dta_name_spans(line: str, base: int):
    def run_span(run, category="PERSON"):
        return _Span(base + run.start(), base + run.end(), category, run.group(0))

    for tag, take in (("DBNA", 2), ("DBAP", 1)):
        pos = line.find(tag, 9)
        if pos == -1:
            continue
        taken = 0
        for run in _RUN.finditer(line, pos + len(tag), pos + len(tag) + 200):
            word = run.group(0)
            if re.match(r"DB[A-Z]{2}", word) or "@" in word or re.search(r"\d{3}", word):
                break
            if taken < take and re.fullmatch(r"[A-Za-zÄÖÜäöüß'’. \-]{2,60}", word):
                yield run_span(run)
                taken += 1
            if taken >= take:
                break
    if line.startswith("DSKO"):
        for run in _RUN.finditer(line, 17):
            hit = _TWO_CAPITALISED.search(run.group(0))
            if hit and not any(w in hit.group(0).casefold() for w in _ORG_WORDS):
                yield _Span(base + run.start() + hit.start(), base + run.start() + hit.end(), "PERSON", hit.group(0))


def _detect(text: str) -> List[_Span]:
    spans: List[_Span] = []
    spans.extend(_vsnr_spans(text))
    spans.extend(_iban_spans(text))
    spans.extend(_email_spans(text))
    spans.extend(_group_span(m, 1, "BBNR") for m in _BBNR_CONTEXT.finditer(text))
    spans.extend(_group_span(m, 1, "BBNR") for m in _BBNR_DTA_HEADER.finditer(text))
    spans.extend(_phone_spans(text))
    spans.extend(_dob_spans(text))
    spans.extend(_person_spans(text))
    spans.extend(_address_spans(text))
    return spans


def _email_spans(text: str):
    for m in _EMAIL.finditer(text):
        yield _Span(m.start(), m.end(), "EMAIL", m.group(0))


def _find_all(text: str, needle: str, category: str, whole_word: bool) -> List[_Span]:
    if whole_word:
        genitive = "s?" if category == "PERSON" else ""  # "Meiers Versicherungsnummer"
        pattern = re.compile(r"(?<![a-zäöüß0-9_])" + re.escape(needle) + genitive + r"(?![a-zäöüß0-9_])")
    else:
        pattern = re.compile(re.escape(needle))
    return [_Span(m.start(), m.end(), category, needle) for m in pattern.finditer(text)]


def _expand(text: str, spans: List[_Span]) -> List[_Span]:
    """Known-value propagation: a value found once is replaced everywhere it appears in the text."""
    extra: List[_Span] = []
    for span in spans:
        if span.category == "VSNR":
            for form in _birth_forms(span.value):
                extra.extend(_find_all(text, form, "DOB", whole_word=False))
        elif span.category == "PERSON":
            extra.extend(_find_all(text, span.value, "PERSON", whole_word=True))
            for part in re.split(r"[ \t\-]+", span.value):
                if len(part) >= 3 and part.casefold() not in _NOT_A_NAME:
                    for variant in {part, part.upper()}:
                        extra.extend(_find_all(text, variant, "PERSON", whole_word=True))
        elif span.category in ("BBNR", "EMAIL", "PHONE", "IBAN", "ADDRESS", "DOB"):
            extra.extend(_find_all(text, span.value, span.category, whole_word=span.category == "ADDRESS"))
    return spans + extra


def _resolve(spans: List[_Span]) -> List[_Span]:
    """Overlaps: higher-priority category wins, then the longer match."""
    chosen: List[_Span] = []
    for span in sorted(spans, key=lambda s: (_PRIORITY[s.category], -(s.end - s.start), s.start)):
        if span.end > span.start and all(span.end <= c.start or span.start >= c.end for c in chosen):
            chosen.append(span)
    return sorted(chosen, key=lambda s: s.start)


def _is_specimen(span: _Span) -> bool:
    if span.category == "BBNR":  # Betriebsnummern in the public rulebook are institution or example numbers
        return True
    value = re.sub(r"\s+", " ", span.value).strip().casefold()
    return SPECIMEN_MARK in value or value in SPECIMEN_EXACT


def find_personal_data(text: str, extra_names=()) -> List[_Span]:
    """All personal-data spans in text (internal: carries values, never log these)."""
    spans = _detect(text)
    for name in extra_names:
        spans.append(_Span(0, 0, "PERSON", name))  # only seeds the propagation below
    return _resolve(_expand(text, spans))


# ---------------------------------------------------------------- keys and tokens

def get_key(key=None) -> Tuple[bytes, str]:
    """Key bytes and where they came from ("argument", "env" or "ephemeral"). Never logs the key.

    No PRIVACY_KEY set: a random per-process key is used. Tokens stay stable inside the run, they just
    cannot be linked across restarts, which is the safer default for a demo.
    """
    if key is None:
        key = os.environ.get(KEY_ENV, "").strip()
        source = "env"
    else:
        source = "argument"
    if not key or not str(key).strip():
        return secrets.token_bytes(32), "ephemeral"
    if isinstance(key, str):
        key = key.encode("utf-8")
    if len(key) < MIN_KEY_CHARS:
        raise PrivacyConfigError(f"{KEY_ENV} must be at least {MIN_KEY_CHARS} characters")
    return key, source


def _normalise(category: str, value: str) -> str:
    if category in ("VSNR", "IBAN"):
        return re.sub(r"[^0-9A-Za-z]", "", value).upper()
    if category in ("BBNR", "PHONE"):
        digits = re.sub(r"\D", "", value)
        return re.sub(r"^(?:0049|49)", "0", digits) if category == "PHONE" else digits
    if category == "DOB":  # 24.12.1980, 1980-12-24 and 19801224 are one value
        digits = re.sub(r"\D", "", value)
        if len(digits) == 8:
            iso = digits if digits[:2] in ("19", "20") and _valid_date(int(digits[6:]), int(digits[4:6]), int(digits[:4]))                 else digits[4:] + digits[2:4] + digits[:2]
            return iso
        return digits
    if category == "EMAIL":
        return value.casefold()
    return re.sub(r"\s+", " ", value).strip().casefold()


class Schleuse:
    """One run of the airlock: same value -> same token. Create one per request or per run."""

    def __init__(self, key=None, keep_reverse: bool = False):
        self._key, self.key_source = get_key(key)
        self._index: Dict[Tuple[str, str], int] = {}  # (category, HMAC digest) -> number, no raw values
        self._counts: Dict[str, int] = {}
        self._replaced: Dict[str, int] = {}
        self._reverse: Optional[Dict[str, str]] = {} if keep_reverse else None
        self._seen_values: List[Tuple[str, str]] = []  # memory only, used by the second-pass check
        self._names: List[str] = []

    # ---- tokens
    def _digest(self, category: str, value: str) -> str:
        message = f"{category}\0{_normalise(category, value)}".encode("utf-8")
        return hmac.new(self._key, message, hashlib.sha256).hexdigest()

    def _token(self, category: str, value: str) -> str:
        slot = (category, self._digest(category, value))
        if slot not in self._index:
            self._counts[category] = self._counts.get(category, 0) + 1
            self._index[slot] = self._counts[category]
            self._seen_values.append((category, value))
            if self._reverse is not None:
                self._reverse[f"{category}_{self._index[slot]}"] = value
        return f"{category}_{self._index[slot]}"

    # ---- pseudonymize
    def _clean_text(self, text: str) -> str:
        spans = find_personal_data(text, self._names)
        out, last = [], 0
        for span in spans:
            out.append(text[last:span.start])
            out.append(self._token(span.category, span.value))
            self._replaced[span.category] = self._replaced.get(span.category, 0) + 1
            if span.category == "PERSON":
                self._remember_name(span.value)
            last = span.end
        out.append(text[last:])
        return "".join(out)

    def _clean(self, obj):
        if isinstance(obj, str):
            return self._clean_text(obj)
        if isinstance(obj, dict):
            self._learn_names(obj)
            return {k: self._clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            for item in obj:
                if isinstance(item, dict):
                    self._learn_names(item)
            return [self._clean(v) for v in obj]
        return obj

    _NAME_KEYS = frozenset(
        "FAMILIENNAME VORNAME NACHNAME ZUNAME GEBURTSNAME NAME VERSICHERTENNAME ANSPRECHPARTNER ANSPRECHPARTNERIN "
        "FIRSTNAME LASTNAME SURNAME FULLNAME GIVENNAME".split())

    @classmethod
    def _is_name_key(cls, key) -> bool:
        return re.sub(r"[^A-Za-z]", "", str(key)).upper() in cls._NAME_KEYS

    def _remember_name(self, name: str) -> None:
        if name not in self._names:
            self._names.append(name)

    def _learn_names(self, record: dict) -> None:
        """Values of known name fields are personal by definition, before any text is read."""
        for key, value in record.items():
            if self._is_name_key(key) and isinstance(value, str) and _name_ok(value.strip()):
                self._remember_name(value.strip())

    def pseudonymize(self, obj):
        """Return (clean, summary). obj is a string or a record (dict/list of strings)."""
        before = dict(self._replaced)
        clean = self._clean(obj)
        counts = {c: self._replaced[c] - before.get(c, 0) for c in self._replaced if self._replaced[c] > before.get(c, 0)}
        return clean, {"policy_version": POLICY_VERSION, "key_source": self.key_source,
                       "categories": counts, "total": sum(counts.values())}

    def restore(self, text: str) -> str:
        """Map tokens back to the original values seen in this run (only if keep_reverse was set)."""
        if not self._reverse:
            return text
        return re.sub(r"\b([A-Z]+_\d+)\b", lambda m: self._reverse.get(m.group(1), m.group(0)), text)

    # ---- check
    def check_clean(self, text: str, allow_specimen: bool = False) -> List[Hit]:
        """Hits left in text, including any value this run has already seen (second pass)."""
        hits = check_clean(text, allow_specimen)
        for category, value in self._seen_values:
            if len(value) >= 3:
                hits.extend(Hit(category, s.start, s.end) for s in _find_all(text, value, category, whole_word=category in ("PERSON", "ADDRESS")))
        return hits


# ---------------------------------------------------------------- module-level helpers

def pseudonymize(text_or_record, key=None):
    """(clean, summary) for a string or a record. Summary: counts per category only."""
    return Schleuse(key).pseudonymize(text_or_record)


def check_clean(text: str, allow_specimen: bool = False) -> List[Hit]:
    """Remaining personal-data hits (empty list = clean). Last gate: any hit means BLOCK.

    allow_specimen skips the fabricated specimen values printed in the public ITSG rulebook
    (Mustermann, Max, Musterstrasse ...). Never use it for user input.
    """
    spans = find_personal_data(text)
    if allow_specimen:
        spans = [s for s in spans if not _is_specimen(s)]
    return [Hit(s.category, s.start, s.end) for s in spans]


def scrub_for_log(text: str) -> str:
    """Logs may hold no personal data at all: every hit becomes [CATEGORY], leftovers withhold the line."""
    spans = find_personal_data(text)
    out, last = [], 0
    for span in spans:
        out.append(text[last:span.start])
        out.append(f"[{span.category}]")
        last = span.end
    out.append(text[last:])
    scrubbed = "".join(out)
    return "[withheld: personal data suspected]" if check_clean(scrubbed) else scrubbed


class LogFilter(logging.Filter):
    """Attach to a logger so every message passes scrub_for_log before it is written."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = scrub_for_log(record.getMessage())
        except Exception:  # never let a logging problem leak the original text
            record.msg = "[withheld: log message could not be checked]"
        record.args = ()
        if record.exc_info:  # the traceback text can quote values; keep the type only
            record.msg += f" ({record.exc_info[0].__name__})"
            record.exc_info = None
        record.exc_text = None
        return True


# ---------------------------------------------------------------- policy per destination

def hash_only(value, key=None) -> str:
    """Keyed hash for the seal: proves "this exact content" without revealing it."""
    key_bytes, _ = get_key(key)
    data = value if isinstance(value, str) else json.dumps(value, sort_keys=True, ensure_ascii=False)
    return "hmac-sha256:" + hmac.new(key_bytes, data.encode("utf-8"), hashlib.sha256).hexdigest()


def _minimize(obj, policy, top=True):
    limit = policy["max_string_chars"]
    if isinstance(obj, dict):
        return {k: _minimize(v, policy, False) for k, v in obj.items() if not top or k in policy["allowed_keys"]}
    if isinstance(obj, (list, tuple)):
        return [_minimize(v, policy, False) for v in obj]
    if isinstance(obj, str) and len(obj) > limit:
        return obj[:limit] + "...[truncated]"
    return obj


def apply_policy(destination: str, payload, key=None):
    """Prepare payload for a destination. Returns (safe_payload, summary). Raises PrivacyBlocked on a failed gate."""
    policy = POLICY.get(destination)
    if policy is None or not policy.get("allowed"):
        raise PrivacyBlocked(["DESTINATION_NOT_ALLOWED"])
    mode = policy["mode"]
    if mode == "hash_only":
        return hash_only(payload, key), {"policy_version": POLICY_VERSION, "destination": destination, "mode": mode}
    if mode == "none":
        safe = scrub_for_log(payload if isinstance(payload, str) else repr(payload))
        return safe, {"policy_version": POLICY_VERSION, "destination": destination, "mode": mode}
    schleuse = Schleuse(key)
    if policy.get("minimize"):
        payload = _minimize(payload, policy)
    clean, summary = schleuse.pseudonymize(payload)
    if policy.get("minimize"):
        clean = _minimize(clean, policy)
    leftovers = schleuse.check_clean(clean if isinstance(clean, str) else repr(clean))
    if leftovers:
        raise PrivacyBlocked(h.category for h in leftovers)
    return clean, {**summary, "destination": destination, "mode": mode}
