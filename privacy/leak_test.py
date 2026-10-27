"""Leak test for the Datenschutz-Schleuse (T10-007).

Plants personal data in 50 synthetic records, sends every record through retrieval.ask() with a fake model
client that records everything it receives, and through the logging path. Then it searches every captured
outbound payload and log line for every planted value. Also counts false positives on 50 clean rulebook chunks.

Run from the repository root:   python privacy/leak_test.py
All data is made up by a seeded generator. No real person, no network, no API key.
"""
import json
import logging
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT, ROOT / "retrieval"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from privacy import schleuse  # noqa: E402
from retrieval import ask as ask_mod  # noqa: E402
from retrieval.search import ChunkIndex  # noqa: E402

TEST_KEY = "leak-test-key-not-a-secret"
CHUNK_BLOCK = re.compile(r"<<<CHUNK BEGIN.*?<<<CHUNK END [0-9a-f]+>>>", re.DOTALL)
TOKEN = re.compile(r"\b(?:VSNR|BBNR|IBAN|EMAIL|PHONE|DOB|PERSON|ADDRESS)_\d+\b")

FIRST = ["Anna", "Lukas", "Fatima", "Jürgen", "Sabine", "Mehmet", "Ingrid", "Tobias", "Katharina", "Dimitri",
         "Helga", "Florian", "Svenja", "Ömer", "Birgit", "Matthias", "Yasemin", "Rüdiger", "Nele", "Hannes"]
LAST = ["Müller", "Schäfer", "Kowalski", "Hoffmann", "Öztürk", "Brandt", "Lindqvist", "Wagner", "Böhm", "Zimmermann",
        "Fröhlich", "Keller", "Nowak", "Schröder", "Albrecht", "Engel", "Vogel", "Hartmann", "Lehmann", "Sommer"]
PARTICLE = ["", "", "", "von ", "van "]
STREETS = ["Hauptstraße", "Bahnhofstraße", "Gartenweg", "Lindenallee", "Marktplatz", "Schillerstr.", "Kirchgasse"]
CITIES = [("50667", "Köln"), ("60311", "Frankfurt am Main"), ("80331", "München"), ("20095", "Hamburg"),
          ("70173", "Stuttgart"), ("04109", "Leipzig"), ("01067", "Dresden"), ("99084", "Erfurt"),
          ("28195", "Bremen"), ("30159", "Hannover")]
DOMAINS = ["example.org", "mail-test.de", "web-beispiel.de", "firma-test.com"]
FOLD = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


@dataclass
class Record:
    text: str
    planted: List[Tuple[str, str]] = field(default_factory=list)  # (category, value)


def _person(rng):
    first, last = rng.choice(FIRST), rng.choice(LAST)
    particle = rng.choice(PARTICLE)
    birth = (rng.randint(1, 28), rng.randint(1, 12), rng.randint(1946, 2004))
    dd, mm, yyyy = birth
    letter = last.translate(FOLD)[0].upper()
    vsnr = f"{rng.randint(2, 89):02d}{dd:02d}{mm:02d}{yyyy % 100:02d}{letter}{rng.randint(0, 999):03d}"
    bban = "".join(str(rng.randint(0, 9)) for _ in range(18))
    check = 98 - int(bban + "131400") % 97
    mail = f"{first}.{last}".translate(FOLD).lower() + "@" + rng.choice(DOMAINS)
    phones = [f"069/{rng.randint(100000, 999999)}", f"+49 171 {rng.randint(1000000, 9999999)}",
              f"0171-{rng.randint(1000000, 9999999)}", f"(0221) {rng.randint(100000, 999999)}",
              f"0151 {rng.randint(10000000, 99999999)}", f"+49 (0)30 {rng.randint(1000000, 9999999)}"]
    plz, city = rng.choice(CITIES)
    return {
        "first": first, "last": f"{particle}{last}", "full": f"{first} {particle}{last}", "vsnr": vsnr,
        "dob": f"{dd:02d}.{mm:02d}.{yyyy}", "dob_compact": f"{yyyy}{mm:02d}{dd:02d}",
        "iban": f"DE{check:02d}{bban}", "email": mail, "phone": rng.choice(phones),
        "street": f"{rng.choice(STREETS)} {rng.randint(1, 120)}", "plz_city": f"{plz} {city}",
        "bbnr": str(rng.randint(10000000, 99999999)),
    }


def _sentence_records(rng, p) -> List[Record]:
    full, first, last = p["full"], p["first"], p["last"]
    ibanspaced = " ".join(p["iban"][i:i + 4] for i in range(0, len(p["iban"]), 4))
    return [
        Record(f"Frau {full} (VSNR {p['vsnr']}) hat eine AU-Meldung mit Abgabegrund 41 eingereicht. Was ist zu pruefen?",
               [("PERSON", full), ("VSNR", p["vsnr"])]),
        Record(f"Der Versicherte {full}, geboren am {p['dob']}, wohnt in der {p['street']}, {p['plz_city']}. "
               f"Welche Datenbausteine braucht eine Stornierung?",
               [("PERSON", full), ("DOB", p["dob"]), ("ADDRESS", p["street"]), ("ADDRESS", p["plz_city"])]),
        Record(f"Bitte erstatten Sie auf IBAN {ibanspaced} an Herrn {full}. Rueckfragen: {p['email']} oder {p['phone']}. "
               f"Wann gilt Abgabegrund 88?",
               [("IBAN", p["iban"]), ("PERSON", full), ("EMAIL", p["email"]), ("PHONE", p["phone"])]),
        Record(f"Name: {full}; Geburtsdatum: {p['dob']}; Telefon: {p['phone']}; E-Mail: {p['email']}. "
               f"Wie wird DBVO befuellt?",
               [("PERSON", full), ("DOB", p["dob"]), ("PHONE", p["phone"]), ("EMAIL", p["email"])]),
        Record(f"Die Betriebsnummer {p['bbnr']} gehoert zur Firma X, Ansprechpartner ist Frau {full}. "
               f"Was steht in 3.1.18 zum Abgabegrund?",
               [("BBNR", p["bbnr"]), ("PERSON", full)]),
        Record(f"Arbeitnehmerin {first} {last} ruft an unter {p['phone']}. Wie lange gilt die AU vom 11.03.2026 bis 20.03.2026?",
               [("PERSON", f"{first} {last}"), ("PHONE", p["phone"])]),
        Record(f"FAMILIENNAME={last} VORNAME={first} VSNR={p['vsnr']} GEBURTSDATUM={p['dob']} "
               f"EMAIL={p['email']} - welcher Abgabegrund passt?",
               [("PERSON", last), ("PERSON", first), ("VSNR", p["vsnr"]), ("DOB", p["dob"]), ("EMAIL", p["email"])]),
        Record(f"Dr. {full} aus {p['plz_city']} fragt nach der Anforderung von Vorerkrankungszeiten (VSNR {p['vsnr']}).",
               [("PERSON", full), ("ADDRESS", p["plz_city"]), ("VSNR", p["vsnr"])]),
    ]


def _dta_record(rng, p) -> Record:
    contact_first, contact_last = rng.choice(FIRST), rng.choice(LAST)
    contact = f"{contact_first} {contact_last}"
    phone = f"069-{rng.randint(1000, 9999)}"
    mail = f"{contact_first}.{contact_last}".translate(FOLD).lower() + "@itsg-test.example"
    plz, city = rng.choice(CITIES)
    line = (f"DSLWLEIST{p['bbnr']}       00000000       132026021409410800000000{p['vsnr']}{p['dob_compact']}{p['bbnr']}"
            f"       11111111-2222-AAAA-EEEE-111111111111765432166666XXX{'0' * 28}{' ' * 22}N41001JNNNNNNNNNJNNNNNJJN"
            f"DBNA{p['last']:<30}{p['first']:<30}{' ' * 60}DBVO120260311{'0' * 20}202512012025120300000000"
            f"DBAP{contact:<30}{phone:<30}{mail:<60}Testfirma Qualitaetskontrolle  {plz}     {city}")
    planted = [("VSNR", p["vsnr"]), ("DOB", p["dob_compact"]), ("BBNR", p["bbnr"]), ("PERSON", p["last"]),
               ("PERSON", p["first"]), ("PERSON", contact), ("PHONE", phone), ("EMAIL", mail), ("ADDRESS", f"{plz}     {city}")]
    return Record(f"Was bedeutet der Abgabegrund 88 in dieser Zeile?\n{line}", planted)


def make_records(n: int = 50, seed: int = 20261027) -> List[Record]:
    rng = random.Random(seed)
    records: List[Record] = []
    while len(records) < n:
        person = _person(rng)
        options = _sentence_records(rng, person) + [_dta_record(rng, person)] * 2  # DTA lines are weighted up
        records.append(rng.choice(options))
    return records


def make_uncued_names(n: int = 10, seed: int = 99) -> List[Record]:
    """Stress cases outside the 50: a name in plain free text with no cue word. Known weak spot of regex."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        out.append(Record(f"Gestern hat {first} {last} wegen der Meldung angerufen. Was gilt bei Abgabegrund 41?",
                          [("PERSON", f"{first} {last}")]))
    return out


# ---------------------------------------------------------------- fake model and capture

class RecordingClient:
    """Looks like the OpenAI client; stores everything it is sent; answers NOT_FOUND and echoes tokens."""

    def __init__(self):
        self.payloads: List[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.payloads.append(json.dumps(kwargs, ensure_ascii=False, default=str))
        user = kwargs["messages"][-1]["content"]
        tokens = sorted(set(TOKEN.findall(user.rsplit("Question:", 1)[-1])))
        reply = {"answer": "Keine Regel gefunden fuer " + ", ".join(tokens), "status": "NOT_FOUND", "citations": []}
        message = SimpleNamespace(content=json.dumps(reply))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], model="fake-model")


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines: List[str] = []

    def emit(self, record):
        self.lines.append(self.format(record))


def _variants(category: str, value: str) -> List[str]:
    """Spellings a leak could take, as (lowercase) substrings of a whitespace/punctuation-stripped haystack."""
    plain = re.sub(r"[^0-9A-Za-z]", "", value).lower()
    if category in ("VSNR", "IBAN", "BBNR"):
        return [plain]
    if category == "PHONE":
        digits = re.sub(r"\D", "", value)
        return [digits[-7:]]
    if category == "DOB":
        if "." in value:
            d, m, y = value.split(".")
            return [plain, f"{y}{m}{d}"]
        return [plain, f"{value[6:8]}{value[4:6]}{value[:4]}"]
    return [plain]


def _leaked(category: str, value: str, payload: str) -> bool:
    if value in payload:
        return True
    squeezed = re.sub(r"[^0-9A-Za-z]", "", payload).lower()
    if category == "PERSON":
        parts = [w for w in re.split(r"\s+", value) if len(w) >= 3 and w.lower() not in ("von", "van")]
        return any(re.search(r"(?<![A-Za-zÄÖÜäöüß])" + re.escape(w) + r"(?![A-Za-zÄÖÜäöüß])", payload) for w in parts)
    if category in ("EMAIL",):
        return value.lower() in payload.lower()
    if category == "ADDRESS":
        return re.sub(r"\s+", " ", value) in re.sub(r"\s+", " ", payload)
    return any(v and v in squeezed for v in _variants(category, value))


def run_records(records: List[Record], key: str = TEST_KEY):
    """Send records through ask() and the log path. Returns (leaks, stats)."""
    import os
    old_key = os.environ.get(schleuse.KEY_ENV)
    os.environ[schleuse.KEY_ENV] = key  # the same key path the real service uses
    capture = LogCapture()
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(capture)
    root.setLevel(logging.DEBUG)
    careless = logging.getLogger("retrieval.ask")  # simulates a caller that logs the raw input
    careless_level = careless.level
    careless.setLevel(logging.DEBUG)
    leaks, stats = [], {"records": len(records), "planted": 0, "blocked": 0, "answered_not_found": 0, "restored": 0, "block_reasons": []}
    try:
        for index, record in enumerate(records):
            client = RecordingClient()
            careless.info("received question: %s", record.text)
            careless.info("received question: %r", {"text": record.text})
            result = ask_mod.ask(record.text, client=client)
            # Retrieved chunks are public rulebook text with their own gate (check_clean on every chunk);
            # ordinary words such as "Sommer" or "Engel" can be both a surname and rulebook vocabulary.
            outbound = CHUNK_BLOCK.sub("[chunk]", "\n".join(client.payloads))
            logs = "\n".join(capture.lines)
            audit = json.dumps(result.audit, ensure_ascii=False)
            stats["planted"] += len(record.planted)
            if result.status == "BLOCKED":
                stats["block_reasons"].extend(result.audit["privacy"].get("blocked_categories", []))
            stats["blocked"] += result.status == "BLOCKED"
            stats["answered_not_found"] += result.status == "NOT_FOUND"
            stats["restored"] += bool(result.status == "NOT_FOUND" and not TOKEN.search(result.answer))
            for slot, (category, value) in enumerate(record.planted):
                for where, haystack in (("model_payload", outbound), ("log_output", logs), ("audit", audit)):
                    if _leaked(category, value, haystack):
                        leaks.append((index, slot, category, where))
            capture.lines.clear()
    finally:
        if old_key is None:
            os.environ.pop(schleuse.KEY_ENV, None)
        else:
            os.environ[schleuse.KEY_ENV] = old_key
        root.removeHandler(capture)
        root.setLevel(old_level)
        careless.setLevel(careless_level)
    return leaks, stats


def false_positives(count: int = 50):
    """Airlock on `count` evenly spaced clean rulebook chunks, and on every chunk.

    Returns (sample_size, sample_strict, sample_lenient, all_size, all_strict, all_lenient); the lists hold
    (chunk_id, [(category, first 40 chars)]) for chunks with hits. "lenient" skips the public specimen values
    (Mustermann, Max, Musterstrasse, Betriebsnummern printed in the rulebook).
    """
    chunks = ChunkIndex().chunks
    step = max(len(chunks) // count, 1)
    sample = [chunks[i * step] for i in range(count)]

    def scan(items):
        strict, lenient = [], []
        for chunk in items:
            spans = schleuse.find_personal_data(chunk.title + chr(10) + chunk.text)
            kept = [s for s in spans if not schleuse._is_specimen(s)]
            for bucket, found in ((strict, spans), (lenient, kept)):
                if found:
                    bucket.append((chunk.chunk_id, [(s.category, s.value[:40]) for s in found][:3]))
        return strict, lenient

    return (len(sample), *scan(sample), len(chunks), *scan(chunks))


def independent_set():
    """The reviewer-written records from test_independent.py (read with ast, so no pytest is needed here)."""
    import ast

    tree = ast.parse((Path(__file__).resolve().parent / "test_independent.py").read_text(encoding="utf-8"))
    records = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "RECORDS" for t in node.targets))
    planted = leaked = 0
    for text, values in records:
        clean, _summary = schleuse.pseudonymize(text, TEST_KEY)
        for value in values:
            planted += 1
            leaked += value in clean
    return {"records": len(records), "planted": planted, "leaked_after_fix": leaked,
            "first_run_before_fix": {"caught": 18, "leaked": 1, "note": "name after 'Versicherter:' was not recognised"}}


KNOWN_LIMITS = [
    "Names in plain free text without a cue word (Herr, Frau, Name:, Versicherter ...) are not found.",
    "0 leaked on the author's records is not independent evidence: the detectors were tuned on that kind of record.",
    "DTA name-block positions (DBNA, DBAP, DSKO) come from one sample file, not from the verified record layout.",
    "Pseudonymized data is still personal data under GDPR while it can be linked back.",
    "Only ask(), the retrieval.ask/ui.server loggers and the Langfuse calls of run_review/harness use the airlock.",
]


def collect() -> dict:
    """Run everything and return the results as plain data (printed by main, served by the UI)."""
    from datetime import datetime, timezone

    leaks, stats = run_records(make_records(50))
    distinct = {(i, slot) for i, slot, _c, _w in leaks}
    stress_leaks, stress_stats = run_records(make_uncued_names(10))
    extra_planted = extra_leaked = 0
    for seed in range(1, 9):  # same generator, other random draws
        extra_leaks, extra_stats = run_records(make_records(50, seed))
        extra_planted += extra_stats["planted"]
        extra_leaked += len({(i, slot) for i, slot, _c, _w in extra_leaks})
    total, s_strict, s_lenient, all_total, a_strict, a_lenient = false_positives(50)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "policy_version": schleuse.POLICY_VERSION,
        "author": {"records": stats["records"], "planted": stats["planted"], "leaked": len(distinct),
                   "leaks": [{"record": i, "category": c, "where": w} for i, _s, c, w in leaks],
                   "blocked": stats["blocked"], "reached_model": stats["answered_not_found"],
                   "tokens_mapped_back": stats["restored"],
                   "extra_seeds": {"seeds": 8, "planted": extra_planted, "leaked": extra_leaked},
                   "stress_uncued_names": {"planted": stress_stats["planted"],
                                           "leaked": len({(i, s) for i, s, _c, _w in stress_leaks})}},
        "independent": independent_set(),
        "false_positives": {"sample": {"chunks": total, "strict": len(s_strict), "specimens_allowed": len(s_lenient)},
                            "all": {"chunks": all_total, "strict": len(a_strict), "specimens_allowed": len(a_lenient),
                                    "examples": [{"chunk": c, "hits": h} for c, h in a_lenient][:10]}},
        "known_limits": KNOWN_LIMITS,
    }


def main() -> int:
    json_path = sys.argv[sys.argv.index("--json") + 1] if "--json" in sys.argv else None
    r = collect()
    a, ind, fp = r["author"], r["independent"], r["false_positives"]

    print("== Datenschutz-Schleuse leak test (synthetic data only) ==")
    print(f"records sent through ask() + log path : {a['records']}")
    print(f"planted personal values               : {a['planted']}")
    print(f"LEAKED values (goal 0)                : {a['leaked']}")
    for leak in a["leaks"]:
        print(f"  leak: record {leak['record']}, {leak['category']}, found in {leak['where']}")
    print(f"records BLOCKED (nothing sent)        : {a['blocked']}")
    print(f"records that reached the fake model   : {a['reached_model']}")
    print(f"answers with tokens mapped back       : {a['tokens_mapped_back']}")
    print(f"extra seeds 1-8 (8 x 50 records)      : planted {a['extra_seeds']['planted']}, leaked {a['extra_seeds']['leaked']}")
    print()
    print("-- independent reviewer set (test_independent.py) --")
    print(f"{ind['records']} records, {ind['planted']} planted values: first run before the fix "
          f"{ind['first_run_before_fix']['caught']} caught / {ind['first_run_before_fix']['leaked']} leaked; "
          f"now leaked {ind['leaked_after_fix']}")
    print()
    print("-- stress, outside the 50: names in plain free text without any cue word --")
    print(f"planted names {a['stress_uncued_names']['planted']}, leaked {a['stress_uncued_names']['leaked']} (known limit of regex detection)")
    print()
    print("-- false positives on clean ITSG rulebook chunks (real hits, not a goal) --")
    print(f"50-chunk sample, strict               : {fp['sample']['strict']} of {fp['sample']['chunks']} chunks")
    print(f"50-chunk sample, specimens allowed    : {fp['sample']['specimens_allowed']} of {fp['sample']['chunks']} chunks")
    print(f"all chunks, strict                    : {fp['all']['strict']} of {fp['all']['chunks']} chunks")
    print(f"all chunks, specimens allowed         : {fp['all']['specimens_allowed']} of {fp['all']['chunks']} chunks")
    for example in fp["all"]["examples"]:
        print(f"  {example['chunk']}: {example['hits']}")
    if json_path:  # for the UI: the result is saved and the exit code stays 0, the file holds the verdict
        Path(json_path).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {json_path}")
        return 0
    return 1 if a["leaked"] else 0


if __name__ == "__main__":
    sys.exit(main())
