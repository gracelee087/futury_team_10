import re
from datetime import datetime

# Valid message codes ("Abgabegrund") as listed in GG EEL 13.1, sections 2.1-2.5
ALLOWED_CODES = {"01","02","03","04","11","12","21","22","23","31","41","42",
                 "51","61","62","66","67","71","72","73","88"}
ID_FORMAT = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$")
MAX_MESSAGES = 100

def is_date(v):
    if not isinstance(v, str):
        return False
    try:
        datetime.strptime(v, "%d.%m.%Y")
        return True
    except ValueError:
        return False

def is_id(v):
    return isinstance(v, str) and bool(ID_FORMAT.match(v))

# Allowlist: the ONLY fields accepted, each with its exact format
FIELDS = {
    "no":                    lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= MAX_MESSAGES,
    "from":                  lambda v: v in ("AG", "KK"),
    "Abgabegrund":           lambda v: v in ALLOWED_CODES,
    "Stornierung":           lambda v: v in ("J", "N"),
    "DSID":                  is_id,
    "DSID-UR":               is_id,
    "REF-ID":                is_id,
    "AZVU":                  lambda v: isinstance(v, str) and bool(re.match(r"^\d{4}-\d{4}-\d{3}$", v)),
    "Beginn_12_Monatsfrist": is_date,
    "EFZ_Ende":              is_date,
    "Ende_EEL":              is_date,
    "Ende_EEL_Grund":        lambda v: isinstance(v, str) and bool(re.match(r"^\d{2}$", v)),
}
REQUIRED = ("from", "Abgabegrund", "AZVU")

def validate(case):
    """Returns a list of problems. Empty list = input is safe to check."""
    if not isinstance(case, dict):
        return ["Input is not a JSON object"]
    msgs = case.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return ["'messages' must be a non-empty list"]
    if len(msgs) > MAX_MESSAGES:
        return [f"Too many messages (max {MAX_MESSAGES})"]
    problems = []
    for i, msg in enumerate(msgs, 1):
        if not isinstance(msg, dict):
            problems.append(f"Message {i}: not an object")
            continue
        for key, value in msg.items():
            if key not in FIELDS:
                problems.append(f"Message {i}: unknown field '{key}' rejected")
            elif not FIELDS[key](value):
                problems.append(f"Message {i}: invalid value in '{key}'")
        for key in REQUIRED:
            if key not in msg:
                problems.append(f"Message {i}: missing required field '{key}'")
    return problems
