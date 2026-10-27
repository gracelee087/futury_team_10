import os
import sys
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
import frontmatter

from Graph_Schema import GraphExtraction
from Normalizer import normalize_entity_id
from Regular_expression_check import deterministic_cross_document_bridge

ENDPOINT_URL = "https://hip-gw.hessian.ai/v1/chat/completions"  # fixed gateway, never user-supplied
# Fail closed: the gateway key is never stored in source; export HAI_API_KEY to run this script.
HAI_API_KEY = os.environ.get("HAI_API_KEY", "")
if not HAI_API_KEY:
    raise SystemExit("set the HAI_API_KEY environment variable (gateway token stays out of source)")

def chunk_id_of(metadata: dict) -> str:
    # Section numbers repeat across documents (e.g. "2" in GG_EEL and Anl1): the ID must include the document
    return f"{metadata.get('doc', 'unknown')}_{metadata.get('section', 'unknown')}"

def extract_json_payload(raw_text: str) -> str:
    if not raw_text:  # reasoning models can spend all tokens on thinking and return empty content
        raise ValueError("LLM returned empty content (raise max_tokens or retry)")
    cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        return fence_match.group(1)
    return cleaned

# ==========================================
# 1. LLM SEMANTIC EXTRACTION FOR MARKDOWN
# ==========================================
def extract_graph_from_markdown_chunk(text_content: str, metadata: dict) -> dict:
    system_prompt = f"""
    You are a German Social Security (DTA EEL § 107 SGB IV) data architect.
    Extract a Knowledge Graph from this markdown chunk.
    Context Metadata:
    - Document: {metadata.get('doc_title')}
    - Section: {metadata.get('section')} ({metadata.get('title')})
    - Pre-identified Abgabegründe: {metadata.get('abgabegrund')}
    - Pre-identified Datenbausteine: {metadata.get('datenbaustein')}

    Return ONLY one JSON object that validates against this JSON schema (no other keys, no prose):
    {json.dumps(GraphExtraction.model_json_schema(), ensure_ascii=False)}
    """
    
    headers = {
        "Authorization": f"Bearer {HAI_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    payload = {
        "model": "vllm/GLM-Flash:Latest",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text_content}
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }
    
    # Fixed gateway, pinned by host: the URL is a module constant, not user input.
    parsed = urlparse(ENDPOINT_URL)
    if parsed.scheme != "https" or parsed.hostname != "hip-gw.hessian.ai":
        raise ValueError("ENDPOINT_URL must be the https gateway hip-gw.hessian.ai")
    response = requests.post("https://hip-gw.hessian.ai/v1/chat/completions",
                             headers=headers, json=payload, timeout=120, allow_redirects=False)
    response.raise_for_status()
    raw_content = response.json()["choices"][0]["message"]["content"]
    # Fail closed: a reply in any other shape raises instead of silently producing a broken graph
    graph = GraphExtraction.model_validate_json(extract_json_payload(raw_content)).model_dump()
    return normalize_graph(graph)

def normalize_graph(graph: dict) -> dict:
    """Canonical IDs (Normalizer.py) for nodes, and the same mapping for edge endpoints."""
    id_map = {}
    for n in graph["nodes"]:
        id_map[n["id"]] = n["id"] = normalize_entity_id(n["id"], n["type"])
    for e in graph["edges"]:
        e["source_id"] = id_map.get(e["source_id"], e["source_id"])
        e["target_id"] = id_map.get(e["target_id"], e["target_id"])
    return graph

# ==========================================
# 2. DETERMINISTIC BRIDGE USING FRONTMATTER
# ==========================================
def deterministic_markdown_bridge(text_content: str, metadata: dict) -> dict:
    """
    Extracts explicit entities from both the Markdown text via regex 
    AND utilizes the structured YAML frontmatter directly.
    """
    nodes = []
    edges = []
    chunk_id = chunk_id_of(metadata)
    
    # A. Inject Metadata directly into the Graph (Zero LLM hallucination risk!)
    for db in metadata.get('datenbaustein', []):
        nodes.append({"id": db, "type": "Datenbaustein", "name": f"Datenbaustein {db}", "description": "From Frontmatter"})
        edges.append({"source_id": db, "target_id": chunk_id, "type": "MENTIONED_IN", "condition": "Frontmatter Metadata"})
        
    for ag in metadata.get('abgabegrund', []):
        ag_id = f"AG_{ag}"
        nodes.append({"id": ag_id, "type": "Abgabegrund", "name": f"Abgabegrund {ag}", "description": "From Frontmatter"})
        edges.append({"source_id": ag_id, "target_id": chunk_id, "type": "MENTIONED_IN", "condition": "Frontmatter Metadata"})

    # B. Regex scan the text content (shared patterns in Regular_expression_check.py)
    regex_graph = deterministic_cross_document_bridge(text_content, chunk_id, metadata.get('source_file'))
    nodes.extend(regex_graph["nodes"])
    edges.extend(regex_graph["edges"])

    return {
        "chunk_id": chunk_id,
        "source_doc": metadata.get('source_file'),
        "nodes": nodes,
        "edges": edges
    }

# ==========================================
# 3. UNIFIED MARKDOWN PIPELINE
# ==========================================
def process_markdown_chunk_fully(raw_markdown_string: str) -> dict:
    # Parse frontmatter and body text cleanly
    post = frontmatter.loads(raw_markdown_string)
    metadata = post.metadata
    text_content = post.content
    
    # 1. Run LLM Extraction
    llm_graph = extract_graph_from_markdown_chunk(text_content, metadata)
    
    # 2. Run Deterministic Bridge (Frontmatter + Regex)
    det_graph = normalize_graph(deterministic_markdown_bridge(text_content, metadata))  # same IDs as the LLM nodes
    
    # 3. Merge Results Safely
    existing_node_ids = {n["id"] for n in llm_graph["nodes"]}
    for node in det_graph["nodes"]:
        if node["id"] not in existing_node_ids:
            llm_graph["nodes"].append(node)
            existing_node_ids.add(node["id"])
            
    seen_edges = {(e["source_id"], e["target_id"], e["type"]) for e in llm_graph["edges"]}
    for edge in det_graph["edges"]:
        if (edge["source_id"], edge["target_id"], edge["type"]) not in seen_edges:
            llm_graph["edges"].append(edge)
            seen_edges.add((edge["source_id"], edge["target_id"], edge["type"]))

    # Fields Merge_graph_neo.py needs to write the chunk node
    llm_graph["chunk_id"] = det_graph["chunk_id"]
    llm_graph["source_doc"] = det_graph["source_doc"]
    llm_graph["chunk_text"] = text_content
    return llm_graph

def process_chunks_dir(chunks_dir: str, out_path: str) -> None:
    """Run every chunk .md under chunks_dir (e.g. chunks/VB) and append one JSON line per chunk.
    A failed chunk is logged and skipped, so one bad LLM reply does not stop the run."""
    base = Path(chunks_dir).resolve()
    if not base.is_dir():
        raise SystemExit(f"chunks dir not found: {base}")
    files = sorted(p for p in base.rglob("*.md") if p.name != "README.md" and p.resolve().is_relative_to(base))
    out = Path(out_path).resolve()
    with open(out, "a", encoding="utf-8") as out_handle:
        for i, path in enumerate(files, 1):
            try:
                graph = process_markdown_chunk_fully(path.read_text(encoding="utf-8"))
                out_handle.write(json.dumps(graph, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(files)}] OK   {path}")
            except Exception as exc:
                print(f"[{i}/{len(files)}] FAIL {path}: {exc}", file=sys.stderr)

# ==========================================
# 4. EXECUTION
# ==========================================
if __name__ == "__main__":
    # Usage: python API.py chunks/VB graph.jsonl   (no arguments: run the built-in example)
    if len(sys.argv) == 3:
        process_chunks_dir(sys.argv[1], sys.argv[2])
        sys.exit(0)
    # Simulate receiving the contents of '2.md' from your colleague
    sample_md_file_content = """---
doc: Anl1
doc_title: Gemeinsames Rundschreiben Kinderkrankengeld (§ 45 SGB V...)
section: '2'
title: Gesetzliche Grundlagen
abgabegrund: []
datenbaustein: []
---

## 2 Gesetzliche Grundlagen

§ 45 SGB V
(1) Versicherte haben Anspruch auf Krankengeld...
§ 12 KVLG 1989
Krankengeld nach den Vorschriften...
"""
    
    result = process_markdown_chunk_fully(sample_md_file_content)
    print(json.dumps(result, indent=2, ensure_ascii=False))