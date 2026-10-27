import json
import os
import sys

from neo4j import GraphDatabase

# Separate statements instead of one chained query: in a chain, an empty $nodes list makes
# UNWIND return zero rows and the edge step after it never runs.

UPSERT_CHUNK_CYPHER = """
MERGE (c:Chunk {id: $chunk_id})
SET c.source_doc = $source_doc, c.text = $chunk_text
"""

UPSERT_NODES_CYPHER = """
MATCH (c:Chunk {id: $chunk_id})
UNWIND $nodes AS n
MERGE (e:Entity {id: n.id})
ON CREATE SET
    e.type = n.type,
    e.name = n.name,
    e.descriptions = [n.description],
    e.sources = [$source_doc]
ON MATCH SET
    e.descriptions = CASE WHEN NOT n.description IN e.descriptions THEN e.descriptions + n.description ELSE e.descriptions END,
    e.sources = CASE WHEN NOT $source_doc IN e.sources THEN e.sources + $source_doc ELSE e.sources END
MERGE (e)-[:MENTIONED_IN]->(c)
"""

# Edges between entities
UPSERT_EDGES_CYPHER = """
UNWIND $edges AS r
MATCH (source:Entity {id: r.source_id})
MATCH (target:Entity {id: r.target_id})
MERGE (source)-[rel:RELATED_TO {type: r.type}]->(target)
SET rel.condition = r.condition, rel.last_seen_in = $chunk_id
"""

# Edges whose target is the chunk itself: the chunk is a :Chunk, not an :Entity,
# so UPSERT_EDGES_CYPHER would silently drop them
UPSERT_CHUNK_EDGES_CYPHER = """
MATCH (c:Chunk {id: $chunk_id})
UNWIND $edges AS r
MATCH (source:Entity {id: r.source_id})
MERGE (source)-[rel:MENTIONED_IN]->(c)
SET rel.condition = r.condition
"""


def _write_chunk_graph(tx, graph: dict) -> None:
    params = {"chunk_id": graph["chunk_id"], "source_doc": graph.get("source_doc")}
    tx.run(UPSERT_CHUNK_CYPHER, chunk_text=graph.get("chunk_text", ""), **params)
    tx.run(UPSERT_NODES_CYPHER, nodes=graph["nodes"], **params)
    to_chunk = [e for e in graph["edges"] if e["target_id"] == graph["chunk_id"]]
    between = [e for e in graph["edges"] if e["target_id"] != graph["chunk_id"]]
    tx.run(UPSERT_EDGES_CYPHER, edges=between, **params)
    tx.run(UPSERT_CHUNK_EDGES_CYPHER, edges=to_chunk, **params)


def load_graph_jsonl(path: str) -> None:
    """Load the JSONL written by API.py (one chunk graph per line) into Neo4j.
    Connection from env: NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD."""
    driver = GraphDatabase.driver(os.environ["NEO4J_URI"],
                                  auth=(os.environ["NEO4J_USER"], os.environ["NEO4J_PASSWORD"]))
    with driver, driver.session() as session:
        with open(path, encoding="utf-8") as f:
            for line in f:
                session.execute_write(_write_chunk_graph, json.loads(line))


if __name__ == "__main__":
    # Usage: python Merge_graph_neo.py graph.jsonl
    load_graph_jsonl(sys.argv[1])
