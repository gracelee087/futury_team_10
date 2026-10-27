import re

def normalize_entity_id(raw_id: str, node_type: str) -> str:
    clean = raw_id.strip().upper()
    # Remove quotes
    clean = re.sub(r'[„“"\'\`]', '', clean)
    
    if node_type == "Abgabegrund":
        # Extract the 2-digit number: "Abgabegrund 41" -> "AG_41"
        match = re.search(r'\b(\d{2})\b', clean)
        return f"AG_{match.group(1)}" if match else clean

    if node_type == "Datenbaustein":
        # Extract 4-letter code: "Datenbaustein DBVO" -> "DBVO"
        match = re.search(r'\b(DSLW|DB[A-Z]{2})\b', clean)
        return match.group(1) if match else clean

    if node_type == "Datenfeld":
        # Strip repeating index suffixes: "BEGINN-AU-1" or "BEGINN-AU-NN" -> "BEGINN-AU"
        clean = re.sub(r'[-_\s]+(NN|\d+)$', '', clean)
        clean = clean.replace(" ", "-")
        return clean

    if node_type == "Rechtsgrundlage":
        # One ID per paragraph, whatever the spelling: "SGB-V-45", "SGB_V_45", "§ 45 Abs. 1 SGB V" -> "§ 45 SGB V"
        clean = clean.replace("_", " ")
        law = re.search(r'SGB[\s-]*(XIV|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)\b|ENTGFG|MUSCHG|KVLG(?:[\s-]*1989)?|BBIG', clean)
        if not law:
            return clean
        rest = (clean[:law.start()] + " " + clean[law.end():])
        rest = re.sub(r'\b(?:ABS|SATZ|NR)\.?\s*\d+[A-Z]?', ' ', rest)  # sub-units are not part of the ID
        para = re.search(r'§+\s*(\d+[A-Z]?)\b', rest) or re.search(r'\b(\d+[A-Z]?)\b', rest)
        if not para:
            return clean
        name = law.group(0)
        name = (f"SGB {law.group(1)}" if law.group(1) else
                {"ENTGFG": "EntgFG", "MUSCHG": "MuSchG", "BBIG": "BBiG"}.get(name, "KVLG 1989" if "1989" in name else name))
        return f"§ {para.group(1).lower()} {name}"

    return clean