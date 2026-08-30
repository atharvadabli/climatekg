"""Map ClimateKG's mechanism projection into Microsoft GraphRAG communities."""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from .corpus import CorpusPaper
from .ollama import answer, cosine, embed


def _state_lookup(data: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {(item["concept"], item["state"]): item["id"] for item in data["states"]}


def _state_label(state: dict[str, Any]) -> str:
    return f"{state['concept']} [{state['state']}]"


def build_tables(papers: list[CorpusPaper]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    states: dict[str, dict[str, Any]] = {}
    relationships = []
    text_units: dict[str, dict[str, Any]] = {}
    degree: Counter[str] = Counter()

    for item in papers:
        data = item.data
        lookup = _state_lookup(data)
        context_by_id = {context["id"]: context for context in data["contexts"]}
        facet_by_id = {facet["id"]: facet for facet in data["facets"]}
        block_by_id = {block["id"]: block for block in data["source_blocks"]}
        for state in data["states"]:
            states.setdefault(
                state["id"],
                {
                    "id": state["id"],
                    "title": state["id"],
                    "label": _state_label(state),
                    "description": _state_label(state),
                    "aliases": state.get("aliases", []),
                },
            )
        for claim in data["claims"]:
            source = lookup[(claim["from"]["concept"], claim["from"]["state"])]
            target = lookup[(claim["to"]["concept"], claim["to"]["state"])]
            degree.update((source, target))
            evidence_ids = [f"{item.namespace}:{value}" for value in claim["evidence_block_ids"]]
            for original_id, text_id in zip(claim["evidence_block_ids"], evidence_ids, strict=True):
                block = block_by_id[original_id]
                text_units[text_id] = {
                    "id": text_id,
                    "paper": item.namespace,
                    "paper_title": data["paper"]["title"],
                    "block_id": original_id,
                    "page": block.get("page"),
                    "text": block["text"],
                }
            context = context_by_id.get(claim["scope_id"]) if claim["scope_type"] == "context" else None
            facet_ids = claim.get("conditioning_facet_ids", [])
            facets = [
                f"{facet_by_id[value]['domain']}: {facet_by_id[value]['notion']} = {facet_by_id[value]['description']}"
                for value in facet_ids
                if value in facet_by_id
            ]
            relationships.append(
                {
                    "id": f"{item.namespace}:{claim['id']}",
                    "claim_id": claim["id"],
                    "paper": item.namespace,
                    "paper_title": data["paper"]["title"],
                    "source": source,
                    "target": target,
                    "description": claim["description"],
                    "relation": claim["relation"],
                    "evidence_role": claim["evidence_role"],
                    "scope_id": claim["scope_id"],
                    "context_name": context.get("name") if context else None,
                    "conditioning_facets": facets,
                    "text_unit_ids": evidence_ids,
                    "weight": 1.0,
                }
            )

    entity_rows = []
    for state_id, state in states.items():
        entity_rows.append(
            {
                **state,
                "human_readable_id": len(entity_rows),
                "type": "CanonicalState",
                "text_unit_ids": [],
                "frequency": degree[state_id],
                "degree": degree[state_id],
            }
        )
    relationship_rows = []
    for index, row in enumerate(relationships):
        relationship_rows.append(
            {
                **row,
                "human_readable_id": index,
                "combined_degree": degree[row["source"]] + degree[row["target"]],
            }
        )
    return pd.DataFrame(entity_rows), pd.DataFrame(relationship_rows), pd.DataFrame(text_units.values())


def create_communities(entities: pd.DataFrame, relationships: pd.DataFrame, vendor_root: Path) -> pd.DataFrame:
    sys.path.insert(0, str(vendor_root))
    from graphrag.index.operations.cluster_graph import cluster_graph

    clusters = cluster_graph(relationships[["source", "target", "weight"]], 25, False, seed=42)
    rows = []
    by_community: dict[tuple[int, int], list[str]] = defaultdict(list)
    parents = {}
    for level, community, parent, state_ids in clusters:
        by_community[(level, community)].extend(state_ids)
        parents[(level, community)] = parent
    for (level, community), state_ids in sorted(by_community.items()):
        state_set = set(state_ids)
        edge_ids = relationships.loc[
            relationships["source"].isin(state_set) & relationships["target"].isin(state_set), "id"
        ].tolist()
        rows.append(
            {
                "id": f"community:{level}:{community}",
                "community": community,
                "level": level,
                "parent": parents[(level, community)],
                "title": f"Community {community}",
                "entity_ids": sorted(state_ids),
                "relationship_ids": edge_ids,
                "size": len(state_ids),
            }
        )
    return pd.DataFrame(rows)


def community_texts(
    communities: pd.DataFrame, entities: pd.DataFrame, relationships: pd.DataFrame
) -> list[str]:
    labels = dict(zip(entities["id"], entities["label"], strict=True))
    edge_by_id = relationships.set_index("id").to_dict("index")
    texts = []
    for row in communities.to_dict("records"):
        lines = ["States: " + "; ".join(labels[value] for value in row["entity_ids"])]
        for edge_id in row["relationship_ids"]:
            edge = edge_by_id[edge_id]
            lines.append(
                f"[{edge_id}] {labels[edge['source']]} -> {labels[edge['target']]}: {edge['description']}"
            )
        texts.append("\n".join(lines))
    return texts


def build_index(
    papers: list[CorpusPaper], output_dir: Path, vendor_root: Path, ollama_url: str, embed_model: str
) -> dict[str, Any]:
    started = time.perf_counter()
    output_dir.mkdir(parents=True, exist_ok=True)
    entities, relationships, text_units = build_tables(papers)
    communities = create_communities(entities, relationships, vendor_root)
    descriptions = community_texts(communities, entities, relationships)
    vectors = []
    for start in range(0, len(descriptions), 8):
        vectors.extend(embed(ollama_url, embed_model, descriptions[start : start + 8]))
    communities["full_content"] = descriptions
    communities["embedding"] = vectors
    entities.to_parquet(output_dir / "entities.parquet", index=False)
    relationships.to_parquet(output_dir / "relationships.parquet", index=False)
    text_units.to_parquet(output_dir / "text_units.parquet", index=False)
    communities.to_parquet(output_dir / "communities.parquet", index=False)
    meta = {
        "paper_count": len(papers),
        "entity_count": len(entities),
        "relationship_count": len(relationships),
        "community_count": len(communities),
        "community_levels": sorted(communities["level"].unique().tolist()),
        "cluster_implementation": "Microsoft GraphRAG 3.1.1 hierarchical Leiden",
        "mechanism_projection": "Canonical State entities connected by Claim relationships",
        "seconds": round(time.perf_counter() - started, 3),
    }
    (output_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def query_index(
    output_dir: Path,
    question: str,
    ollama_url: str,
    embed_model: str,
    chat_model: str,
    top_communities: int = 5,
    max_relationships: int = 18,
) -> dict[str, Any]:
    started = time.perf_counter()
    communities = pd.read_parquet(output_dir / "communities.parquet")
    relationships = pd.read_parquet(output_dir / "relationships.parquet")
    text_units = pd.read_parquet(output_dir / "text_units.parquet")
    query_vector = embed(ollama_url, embed_model, [question])[0]
    communities["score"] = communities["embedding"].apply(lambda value: cosine(query_vector, list(value)))
    selected = communities.sort_values("score", ascending=False).head(top_communities)
    selected_edge_ids = {value for values in selected["relationship_ids"] for value in values}
    candidates = relationships[relationships["id"].isin(selected_edge_ids)].copy()
    candidate_texts = [
        f"{row.source} -> {row.target}. {row.description}. {'; '.join(row.conditioning_facets)}"
        for row in candidates.itertuples()
    ]
    edge_vectors = embed(ollama_url, embed_model, candidate_texts) if candidate_texts else []
    candidates["score"] = [cosine(query_vector, value) for value in edge_vectors]
    chosen = candidates.sort_values("score", ascending=False).head(max_relationships)
    unit_by_id = text_units.set_index("id").to_dict("index")
    evidence = []
    for row in chosen.to_dict("records"):
        blocks = [unit_by_id[value] for value in row["text_unit_ids"] if value in unit_by_id]
        evidence.append(
            {
                "evidence_id": row["id"],
                "claim_id": row["claim_id"],
                "paper": row["paper"],
                "paper_title": row["paper_title"],
                "source_state": row["source"],
                "target_state": row["target"],
                "relation": row["relation"],
                "description": row["description"],
                "conditioning_facets": row["conditioning_facets"],
                "blocks": blocks,
                "score": row["score"],
            }
        )
    prompt = (
        "TASK\n\n"
        "Answer the scientific question using only the evidence records supplied below. "
        "Each record has a bracketed identifier, a finding, the reported relationship type, "
        "relevant study conditions when available, and exact supporting text from a paper. "
        "Consider whether study conditions support transfer to the location or scenario in the question.\n\n"
        f"QUESTION\n\n{question}\n\nEVIDENCE RECORDS\n\n"
        + "\n\n".join(
            f"[{item['evidence_id']}] {item['description']}\n"
            f"Relation: {item['relation']}; conditions: {'; '.join(item['conditioning_facets']) or 'not specified'}\n"
            + "\n".join(f"SourceBlock {block['block_id']} page {block['page']}: {block['text']}" for block in item["blocks"])
            for item in evidence
        )
        + "\n\nOUTPUT\n\n"
        "Write a direct answer in 2-5 short paragraphs. Cite every substantive scientific statement "
        "with one or more bracketed evidence identifiers exactly as supplied. Clearly separate findings "
        "reported by the papers from application to a new location. State important missing conditions "
        "or uncertainties."
    )
    raw = answer(ollama_url, chat_model, prompt)
    return {
        "question": question,
        "selected_communities": selected[["id", "level", "size", "score"]].to_dict("records"),
        "evidence": evidence,
        "prompt": prompt,
        "answer": raw.get("message", {}).get("content", ""),
        "thinking": raw.get("message", {}).get("thinking", ""),
        "timings": {"total_seconds": round(time.perf_counter() - started, 3)},
    }
