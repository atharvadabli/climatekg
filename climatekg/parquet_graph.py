from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from .canonicalize import state_id
from .config import PIPELINE
from .models import FinalPaper
from .utils import write_json
from .vector_index import FaissIndexes

FORMAT_VERSION = "1.0"
OBJECT_TABLES = (
    "source_blocks",
    "contexts",
    "facets",
    "transitions",
    "claims",
    "states",
    "evidence_links",
)


class ParquetGraph:
    """A local, tabular materialization of the ClimateKG graph.

    Parquet stores nodes and an explicit edge list. Scientific querying still
    runs through the deterministic Python algorithms in ``climatekg.query``.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write_corpus(self, papers: Iterable[FinalPaper]) -> dict[str, int]:
        papers = list(papers)
        self.root.mkdir(parents=True, exist_ok=True)

        paper_rows: list[dict[str, Any]] = []
        rows_by_table = {name: [] for name in OBJECT_TABLES}
        relationship_rows: list[dict[str, Any]] = []

        for paper_order, final in enumerate(papers):
            paper_id = final.paper.id
            paper_row = _encode_row(final.paper.model_dump(by_alias=True))
            paper_row.update(
                {
                    "schema_version": final.schema_version,
                    "pipeline_version": final.pipeline_version,
                    "unresolved_conflicts_json": _json(final.unresolved_conflicts),
                    "metadata_json": _json(final.metadata),
                    "_row_order": paper_order,
                }
            )
            paper_rows.append(paper_row)

            for table_name in OBJECT_TABLES:
                values = getattr(final, table_name)
                for row_order, value in enumerate(values):
                    raw = value.model_dump(by_alias=True) if hasattr(value, "model_dump") else value
                    row = _encode_row(raw)
                    row["owner_paper_id"] = paper_id
                    row["_row_order"] = row_order
                    rows_by_table[table_name].append(row)

            relationship_rows.extend(_relationships(final))

        _write_table(self.root / "papers.parquet", paper_rows)
        for table_name, rows in rows_by_table.items():
            _write_table(self.root / f"{table_name}.parquet", rows)
        _write_table(self.root / "relationships.parquet", relationship_rows)

        embedding_dimensions = {
            len(context.retrieval_embedding or [])
            for paper in papers
            for context in paper.contexts
        }
        if len(embedding_dimensions) != 1 or 0 in embedding_dimensions:
            raise ValueError(f"Corpus must have one nonzero embedding dimension: {embedding_dimensions}")
        dimension = embedding_dimensions.pop()
        ann_config = PIPELINE["graph"]["ann"]
        FaissIndexes.build(
            papers,
            self.root / "ann",
            dimension,
            connectivity=ann_config["connectivity"],
            ef_construction=ann_config["ef_construction"],
            ef_search=ann_config["ef_search"],
        )

        counts = {"papers": len(paper_rows), **{name: len(rows) for name, rows in rows_by_table.items()}, "relationships": len(relationship_rows)}
        write_json(
            self.root / "manifest.json",
            {
                "format": "climatekg-parquet-graph",
                "format_version": FORMAT_VERSION,
                "ann": {"backend": "faiss_hnsw", "path": "ann"},
                "tables": counts,
            },
        )
        return counts

    def read_corpus(self) -> list[FinalPaper]:
        manifest_path = self.root / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Parquet graph manifest not found: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != "climatekg-parquet-graph" or manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"Unsupported Parquet graph format: {manifest}")

        object_rows = {name: _read_table(self.root / f"{name}.parquet") for name in OBJECT_TABLES}
        papers: list[FinalPaper] = []
        for paper_row in _read_table(self.root / "papers.parquet"):
            paper_id = paper_row["id"]
            schema_version = paper_row.pop("schema_version")
            pipeline_version = paper_row.pop("pipeline_version")
            unresolved = json.loads(paper_row.pop("unresolved_conflicts_json"))
            metadata = json.loads(paper_row.pop("metadata_json"))
            paper_row.pop("_row_order", None)

            collections: dict[str, list[dict[str, Any]]] = {}
            for table_name, all_rows in object_rows.items():
                owned = [dict(row) for row in all_rows if row.get("owner_paper_id") == paper_id]
                owned.sort(key=lambda row: row.get("_row_order", 0))
                for row in owned:
                    row.pop("owner_paper_id", None)
                    row.pop("_row_order", None)
                collections[table_name] = owned

            papers.append(
                FinalPaper.model_validate(
                    {
                        "schema_version": schema_version,
                        "pipeline_version": pipeline_version,
                        "paper": _decode_row(paper_row),
                        **{name: [_decode_row(row) for row in rows] for name, rows in collections.items()},
                        "unresolved_conflicts": unresolved,
                        "metadata": metadata,
                    }
                )
            )
        return papers

    def read_indexes(self) -> FaissIndexes:
        return FaissIndexes.load(self.root / "ann")

    def table_counts(self) -> dict[str, int]:
        return {
            path.stem: pq.read_metadata(path).num_rows
            for path in sorted(self.root.glob("*.parquet"))
        }


def _write_table(path: Path, rows: list[dict[str, Any]]) -> None:
    table = pa.Table.from_pylist(rows) if rows else pa.table({})
    pq.write_table(table, path, compression="zstd")


def _read_table(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Required Parquet graph table not found: {path}")
    return pq.read_table(path).to_pylist()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _encode_row(row: dict[str, Any]) -> dict[str, Any]:
    encoded: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, dict) or isinstance(value, list) and any(isinstance(item, (dict, list)) for item in value):
            encoded[f"{key}_json"] = _json(value)
        else:
            encoded[key] = value
    return encoded


def _decode_row(row: dict[str, Any]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in row.items():
        if key.endswith("_json"):
            decoded[key[:-5]] = json.loads(value) if value is not None else None
        else:
            decoded[key] = value
    return decoded


def _edge(paper_id: str, source_id: str, relation: str, target_id: str) -> dict[str, str]:
    return {
        "paper_id": paper_id,
        "source_id": source_id,
        "relationship_type": relation,
        "target_id": target_id,
    }


def _relationships(final: FinalPaper) -> list[dict[str, str]]:
    paper_id = final.paper.id
    rows: list[dict[str, str]] = []
    rows.extend(_edge(paper_id, block.id, "IN_PAPER", paper_id) for block in final.source_blocks)
    for context in final.contexts:
        rows.append(_edge(paper_id, paper_id, "HAS_CONTEXT", context.id))
        rows.extend(_edge(paper_id, parent_id, "PARENT_OF", context.id) for parent_id in context.parent_ids)
    for facet in final.facets:
        rows.append(_edge(paper_id, facet.context_id, "HAS_FACET", facet.id))
    for transition in final.transitions:
        rows.extend(
            (
                _edge(paper_id, paper_id, "HAS_TRANSITION", transition.id),
                _edge(paper_id, transition.id, "FROM", transition.from_context_id),
                _edge(paper_id, transition.id, "TO", transition.to_context_id),
            )
        )
    for claim in final.claims:
        rows.extend(
            (
                _edge(paper_id, paper_id, "HAS_CLAIM", claim.id),
                _edge(paper_id, claim.id, "FROM", state_id(claim.from_.concept, claim.from_.state)),
                _edge(paper_id, claim.id, "TO", state_id(claim.to.concept, claim.to.state)),
                _edge(paper_id, claim.id, "SCOPED_TO", claim.scope_id),
            )
        )
        rows.extend(_edge(paper_id, claim.id, "CONDITIONED_BY", facet_id) for facet_id in claim.conditioning_facet_ids)
    for collection in (final.contexts, final.facets, final.transitions, final.claims):
        for item in collection:
            rows.extend(_edge(paper_id, item.id, "SUPPORTED_BY", block_id) for block_id in item.evidence_block_ids)
    return rows
