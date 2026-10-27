from typing import List, Literal, Optional
from pydantic import BaseModel, Field

# 1. Restrict Node Types to your DTA EEL Domain
NodeType = Literal[
    "Abgabegrund",      # e.g., "01", "41", "61", "62", "88"
    "Datenbaustein",    # e.g., "DSLW", "DBVO", "DBAL", "DBSD", "DBEE"
    "Datenfeld",        # e.g., "KZ-NACHWEIS", "AU-AB-AG", "DATUM-EGZBIS"
    "Schluesselzahl",   # e.g., "KZ-NACHWEIS=4", "EEL-ENDE-GRUND=99"
    "Pruefkriterium",   # e.g., UUIDs like "f41c7278-..." or rules like "30-Tage-Frist"
    "Rechtsgrundlage",  # e.g., "§ 107 SGB IV", "§ 3 EntgFG", "§ 45 SGB V"
    "Beispiel"          # e.g., "Beispiel_13.1", "Beispiel_16.8"
]

# 2. Restrict Relationship Types
EdgeType = Literal[
    "REQUIRES_BAUSTEIN",  # (Abgabegrund) -> (Datenbaustein)
    "HAS_FIELD",          # (Datenbaustein) -> (Datenfeld)
    "ALLOWS_VALUE",       # (Datenfeld) -> (Schluesselzahl)
    "GOVERNED_BY_RULE",   # (Abgabegrund/Datenbaustein/Datenfeld) -> (Pruefkriterium)
    "TRIGGERS_RESPONSE",  # (Abgabegrund/Schluesselzahl) -> (Abgabegrund)
    "BASED_ON_LAW",       # (Datenbaustein/Datenfeld/Pruefkriterium) -> (Rechtsgrundlage)
    "DEMONSTRATED_IN"     # (Abgabegrund/Datenbaustein/Datenfeld) -> (Beispiel)
]

class Node(BaseModel):
    id: str = Field(
        description="Canonical uppercase ID. E.g., 'AG_41' for Abgabegrund 41, 'DBVO' for Baustein, 'KZ-NACHWEIS' for field (strip 'nn' suffixes)."
    )
    type: NodeType
    name: str = Field(description="Human-readable name in German")
    description: str = Field(description="Contextual rules, conditions, or byte positions from the chunk")

class Edge(BaseModel):
    source_id: str = Field(description="Must match a Node.id")
    target_id: str = Field(description="Must match a Node.id")
    type: EdgeType
    condition: Optional[str] = Field(
        default=None, 
        description="Condition under which this link holds (e.g., 'Nur wenn AU-Nachweis fehlt')"
    )

class GraphExtraction(BaseModel):
    nodes: List[Node]
    edges: List[Edge]