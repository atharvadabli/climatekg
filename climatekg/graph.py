from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any

from .config import PIPELINE
from .models import FinalPaper


class Neo4jHttp:
    def __init__(self, http_uri: str | None = None, database: str | None = None, user: str | None = None, password: str | None = None) -> None:
        config = PIPELINE["graph"]
        self.url = f"{http_uri or config['neo4j_http_uri']}/db/{database or config['database']}/tx/commit"
        resolved_password = password or os.environ.get(config["password_env"], "climatekg-test")
        self.auth = base64.b64encode(f"{user or config['user']}:{resolved_password}".encode()).decode()

    def execute(self, statements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        request = urllib.request.Request(self.url, data=json.dumps({"statements": statements}).encode(), headers={"Content-Type": "application/json", "Authorization": f"Basic {self.auth}"})
        with urllib.request.urlopen(request, timeout=300) as response:
            result = json.loads(response.read())
        if result.get("errors"):
            raise RuntimeError(f"FAILED_GRAPH_INGEST: {result['errors']}")
        return result.get("results", [])

    def initialize(self, dimension: int = 2048) -> None:
        constraints = [
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (n:Paper) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT context_id IF NOT EXISTS FOR (n:Context) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT facet_id IF NOT EXISTS FOR (n:Facet) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT transition_id IF NOT EXISTS FOR (n:Transition) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (n:Claim) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT state_id IF NOT EXISTS FOR (n:State) REQUIRE n.id IS UNIQUE",
            "CREATE CONSTRAINT source_block_id IF NOT EXISTS FOR (n:SourceBlock) REQUIRE n.id IS UNIQUE",
        ]
        self.execute([{"statement": statement} for statement in constraints])
        indexes = [
            "CREATE FULLTEXT INDEX state_text IF NOT EXISTS FOR (n:State) ON EACH [n.concept, n.state]",
            "CREATE FULLTEXT INDEX context_text IF NOT EXISTS FOR (n:Context) ON EACH [n.label, n.aliases]",
            f"CREATE VECTOR INDEX context_vector IF NOT EXISTS FOR (n:Context) ON n.retrieval_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX facet_notion_vector IF NOT EXISTS FOR (n:Facet) ON n.notion_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX facet_content_vector IF NOT EXISTS FOR (n:Facet) ON n.content_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX claim_vector IF NOT EXISTS FOR (n:Claim) ON n.claim_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX transition_vector IF NOT EXISTS FOR (n:Transition) ON n.transition_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
            f"CREATE VECTOR INDEX state_vector IF NOT EXISTS FOR (n:State) ON n.concept_embedding OPTIONS {{indexConfig: {{`vector.dimensions`: {dimension}, `vector.similarity_function`: 'cosine'}}}}",
        ]
        self.execute([{"statement": statement} for statement in indexes])

    def ingest(self, paper: FinalPaper) -> None:
        data = paper.model_dump(by_alias=True)
        paper_row = _flatten(data["paper"])
        block_rows = [_flatten(x) for x in data["source_blocks"]]
        context_rows = [_flatten(x) for x in data["contexts"]]
        facet_rows = [_flatten(x) for x in data["facets"]]
        transition_rows = [_flatten(x) for x in data["transitions"]]
        state_rows = [_flatten(x) for x in data["states"]]
        claim_rows = []
        for row in data["claims"]:
            flat = _flatten(row)
            flat.update({"from_concept": row["from"]["concept"], "from_state": row["from"]["state"], "to_concept": row["to"]["concept"], "to_state": row["to"]["state"], "from_state_id": _state_key(row["from"]), "to_state_id": _state_key(row["to"])})
            claim_rows.append(flat)
        # One commit endpoint call is one Neo4j transaction. Paper-owned nodes
        # are deleted first; shared State nodes are preserved and MERGEd.
        statements = [
            {"statement": "MATCH (p:Paper {id:$id}) OPTIONAL MATCH (b:SourceBlock)-[:IN_PAPER]->(p) OPTIONAL MATCH (p)-[:HAS_CONTEXT|HAS_TRANSITION|HAS_CLAIM]->(n) OPTIONAL MATCH (n)-[:HAS_FACET]->(f) DETACH DELETE b,f,n,p", "parameters": {"id": paper.paper.id}},
            {"statement": "CREATE (p:Paper) SET p=$paper", "parameters": {"paper": paper_row}},
            {"statement": "UNWIND $rows AS row MATCH (p:Paper {id:row.paper_id}) CREATE (b:SourceBlock) SET b=row CREATE (b)-[:IN_PAPER]->(p)", "parameters": {"rows": block_rows}},
            {"statement": "UNWIND $rows AS row MATCH (p:Paper {id:row.paper_id}) CREATE (c:Context) SET c=row CREATE (p)-[:HAS_CONTEXT]->(c)", "parameters": {"rows": context_rows}},
            {"statement": "UNWIND $rows AS row MATCH (child:Context {id:row.id}) UNWIND row.parent_ids AS pid MATCH (parent:Context {id:pid}) CREATE (parent)-[:PARENT_OF]->(child)", "parameters": {"rows": context_rows}},
            {"statement": "UNWIND $rows AS row MATCH (c:Context {id:row.context_id}) CREATE (f:Facet) SET f=row CREATE (c)-[:HAS_FACET]->(f)", "parameters": {"rows": facet_rows}},
            {"statement": "UNWIND $rows AS row MATCH (p:Paper {id:row.paper_id}), (a:Context {id:row.from_context_id}), (b:Context {id:row.to_context_id}) CREATE (t:Transition) SET t=row CREATE (p)-[:HAS_TRANSITION]->(t), (t)-[:FROM]->(a), (t)-[:TO]->(b)", "parameters": {"rows": transition_rows}},
            {"statement": "UNWIND $rows AS row MERGE (s:State {id:row.id}) SET s += row", "parameters": {"rows": state_rows}},
            {"statement": "UNWIND $rows AS row MATCH (p:Paper {id:row.paper_id}) CREATE (c:Claim) SET c=row CREATE (p)-[:HAS_CLAIM]->(c) WITH c,row MATCH (a:State {id:row.from_state_id}), (b:State {id:row.to_state_id}) CREATE (c)-[:FROM]->(a), (c)-[:TO]->(b)", "parameters": {"rows": claim_rows}},
            {"statement": "UNWIND $rows AS row MATCH (c:Claim {id:row.id}) MATCH (scope {id:row.scope_id}) CREATE (c)-[:SCOPED_TO]->(scope)", "parameters": {"rows": claim_rows}},
            {"statement": "UNWIND $rows AS row MATCH (c:Claim {id:row.id}) UNWIND row.conditioning_facet_ids AS fid MATCH (f:Facet {id:fid}) CREATE (c)-[:CONDITIONED_BY]->(f)", "parameters": {"rows": claim_rows}},
        ]
        for label, rows in (("Context", context_rows), ("Facet", facet_rows), ("Transition", transition_rows), ("Claim", claim_rows)):
            statements.append({"statement": f"UNWIND $rows AS row MATCH (n:{label} {{id:row.id}}) UNWIND row.evidence_block_ids AS bid MATCH (b:SourceBlock {{id:bid}}) CREATE (n)-[:SUPPORTED_BY]->(b)", "parameters": {"rows": rows}})
        statements.append({"statement": "MATCH (s:State) WHERE NOT (s)<-[:FROM|TO]-(:Claim) DETACH DELETE s"})
        self.execute(statements)

    def verify_paper(self, paper_id: str) -> dict[str, int]:
        statement = "MATCH (p:Paper {id:$id}) OPTIONAL MATCH (p)-[:HAS_CONTEXT]->(c) OPTIONAL MATCH (p)-[:HAS_TRANSITION]->(t) OPTIONAL MATCH (p)-[:HAS_CLAIM]->(cl) RETURN count(DISTINCT c) AS contexts,count(DISTINCT t) AS transitions,count(DISTINCT cl) AS claims"
        result = self.execute([{"statement": statement, "parameters": {"id": paper_id}, "resultDataContents": ["row"]}])
        row = result[0]["data"][0]["row"]
        return dict(zip(("contexts", "transitions", "claims"), row))

    def read_corpus(self) -> list[FinalPaper]:
        paper_rows = self._property_rows("MATCH (n:Paper) RETURN properties(n) AS item ORDER BY n.id")
        papers: list[FinalPaper] = []
        for paper_row in paper_rows:
            paper_id = paper_row["id"]
            parameters = {"id": paper_id}
            blocks = self._property_rows("MATCH (n:SourceBlock)-[:IN_PAPER]->(:Paper {id:$id}) RETURN properties(n) AS item ORDER BY n.order", parameters)
            contexts = self._property_rows("MATCH (:Paper {id:$id})-[:HAS_CONTEXT]->(n:Context) RETURN properties(n) AS item ORDER BY n.id", parameters)
            facets = self._property_rows("MATCH (:Paper {id:$id})-[:HAS_CONTEXT]->(:Context)-[:HAS_FACET]->(n:Facet) RETURN properties(n) AS item ORDER BY n.id", parameters)
            transitions = self._property_rows("MATCH (:Paper {id:$id})-[:HAS_TRANSITION]->(n:Transition) RETURN properties(n) AS item ORDER BY n.id", parameters)
            claims = self._property_rows("MATCH (:Paper {id:$id})-[:HAS_CLAIM]->(n:Claim) RETURN properties(n) AS item ORDER BY n.id", parameters)
            states = self._property_rows("MATCH (:Paper {id:$id})-[:HAS_CLAIM]->(:Claim)-[:FROM|TO]->(n:State) RETURN DISTINCT properties(n) AS item ORDER BY item.id", parameters)
            for claim in claims:
                for key in ("from_concept", "from_state", "to_concept", "to_state", "from_state_id", "to_state_id"):
                    claim.pop(key, None)
            evidence_links = [
                {"object_id": item["id"], "source_block_id": block_id}
                for collection in (contexts, facets, transitions, claims)
                for item in collection
                for block_id in item.get("evidence_block_ids", [])
            ]
            papers.append(FinalPaper.model_validate({"paper": paper_row, "source_blocks": blocks, "contexts": contexts, "facets": facets, "transitions": transitions, "claims": claims, "states": states, "evidence_links": evidence_links}))
        return papers

    def _property_rows(self, statement: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        result = self.execute([{"statement": statement, "parameters": parameters or {}, "resultDataContents": ["row"]}])
        return [_inflate(row["row"][0]) for row in result[0].get("data", [])]


def _state_key(endpoint: dict[str, str]) -> str:
    from .canonicalize import state_id
    return state_id(endpoint["concept"], endpoint["state"])


def _flatten(row: dict[str, Any]) -> dict[str, Any]:
    """Convert schema objects to legal Neo4j property values losslessly."""
    result: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict):
            result[f"{key}_json"] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        elif value is None or isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, list) and all(item is None or isinstance(item, (str, int, float, bool)) for item in value):
            result[key] = value
        elif isinstance(value, list):
            result[f"{key}_json"] = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            result[f"{key}_json"] = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return result


def _inflate(row: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in row.items():
        if key.endswith("_json"):
            result[key[:-5]] = json.loads(value)
        else:
            result[key] = value
    return result
