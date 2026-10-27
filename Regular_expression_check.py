import re

# Longest numerals first + \b: otherwise "SGB IV" matches as "SGB I", "SGB VII" as "SGB V", "SGB XIV" as "SGB X"
LAW_PATTERN = (r'§+\s*\d+[a-z]?\s*(?:Abs\.\s*\d+[a-z]?\s*)?(?:Satz\s*\d+\s*)?'
               r'(?:SGB\s*(?:XIV|XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)\b|EntgFG|MuSchG|KVLG(?:\s*1989)?|BBiG)')
# Only a few non-word characters between the word and the code ("Abgabegrund „41“", "„Abgabegrund“ = „41“")
ABGABE_PATTERN = r'Abgabegr(?:und|ünde)\W{0,6}(\d{2})\b'
BAUSTEIN_PATTERN = (r'\b(DSLW|DSKO|DSRV|DBNA|DBAN|DBAL|DBAE|DBZA|DBEE|DBAW|DBFR|DBUN|DBMU|DBVO|DBHE|DBBE'
                    r'|DBLT|DBSF|DBTK|DBAP|DBID|DBSD|DBFE)\b')


def deterministic_cross_document_bridge(chunk_text: str, chunk_id: str, source_doc: str) -> dict:
    """
    Scans a document chunk using regex to extract rigid DTA EEL entities 
    (Datenbausteine, Abgabegründe, and Legal Paragraphs) and links them 
    directly to the chunk for high-recall cross-document bridging.
    """
    nodes = []
    edges = []
    
    # 1. Extract Datenbausteine (e.g., DSLW, DBVO, DBAL, DBSD, DBEE)
    bausteins = set(re.findall(BAUSTEIN_PATTERN, chunk_text))
    for b in bausteins:
        nodes.append({
            "id": b,
            "type": "Datenbaustein",
            "name": f"Datenbaustein {b}",
            "description": f"Deterministically extracted from {source_doc}"
        })
        edges.append({
            "source_id": b,
            "target_id": chunk_id,
            "type": "MENTIONED_IN",
            "condition": "Deterministic Regex Match"
        })
        
    # 2. Extract Abgabegründe (e.g., Abgabegrund '41', Abgabegrund 01)
    abgabegruende = set(re.findall(ABGABE_PATTERN, chunk_text, re.IGNORECASE))
    for ag in abgabegruende:
        node_id = f"AG_{ag}"
        nodes.append({
            "id": node_id,
            "type": "Abgabegrund",
            "name": f"Abgabegrund {ag}",
            "description": f"Deterministically extracted from {source_doc}"
        })
        edges.append({
            "source_id": node_id,
            "target_id": chunk_id,
            "type": "MENTIONED_IN",
            "condition": "Deterministic Regex Match"
        })
        
    # 3. Extract Legal Paragraphs (e.g., § 107 SGB IV, § 3 EntgFG, § 45 SGB V)
    laws = set(re.findall(LAW_PATTERN, chunk_text))
    for law in laws:
        clean_law = " ".join(law.split())
        nodes.append({
            "id": clean_law,
            "type": "Rechtsgrundlage",
            "name": clean_law,
            "description": f"Deterministically extracted from {source_doc}"
        })
        edges.append({
            "source_id": clean_law,
            "target_id": chunk_id,
            "type": "MENTIONED_IN",
            "condition": "Deterministic Regex Match"
        })
        
    return {
        "chunk_id": chunk_id,
        "source_doc": source_doc,
        "nodes": nodes,
        "edges": edges
    }