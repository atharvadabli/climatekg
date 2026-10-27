from __future__ import annotations

import os
from argparse import Namespace
from pathlib import Path
from typing import Any, Callable

from climatekg.config import OUTPUT_ROOT
from climatekg.utils import write_json


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_ROOT = Path(os.environ["CLIMATEKG_BASELINE_ROOT"]) if os.environ.get("CLIMATEKG_BASELINE_ROOT") else OUTPUT_ROOT / "three_system_benchmark" / "baselines"
PLAIN_RAG_INDEX = BASELINE_ROOT / "plain_rag" / "index"
GRAPHRAG_INDEX = BASELINE_ROOT / "graphrag"
PROMPT_ROOT = PROJECT_ROOT / "prompts"

ANSWER_SYSTEMS = (
    {"id": "graphrag", "label": "Microsoft GraphRAG"},
    {"id": "plain_rag", "label": "Plain RAG"},
    {"id": "climatekg", "label": "ClimateKG"},
)
DEFAULT_ANSWER_SYSTEM = "graphrag"


def readiness() -> dict[str, bool]:
    return {
        "graphrag_ready": all(
            (GRAPHRAG_INDEX / name).exists()
            for name in ("communities.parquet", "relationships.parquet", "text_units.parquet")
        ),
        "plain_rag_ready": (PLAIN_RAG_INDEX / "chunks.jsonl").exists(),
    }


def run_baseline(
    system: str,
    retrieval_question: str,
    display_question: str,
    query_id: str,
    artifact_dir: Path,
    derived_facets: list[dict[str, Any]],
    answer_task: str,
    ollama_url: str,
    embedding_model: str,
    generation_model: str,
    stage_callback: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    if system == "graphrag":
        return _run_graphrag(
            retrieval_question, display_question, query_id, artifact_dir, derived_facets,
            answer_task, ollama_url, embedding_model, generation_model, stage_callback,
        )
    if system == "plain_rag":
        return _run_plain_rag(
            retrieval_question, display_question, query_id, artifact_dir, derived_facets,
            answer_task, ollama_url, embedding_model, generation_model, stage_callback,
        )
    raise ValueError(f"unsupported baseline answer system: {system}")


def _run_graphrag(
    retrieval_question: str,
    display_question: str,
    query_id: str,
    artifact_dir: Path,
    derived_facets: list[dict[str, Any]],
    answer_task: str,
    ollama_url: str,
    embedding_model: str,
    generation_model: str,
    stage_callback: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    from baselines.climatekg_comparison.graphrag_adapter import query_index

    if not (GRAPHRAG_INDEX / "communities.parquet").exists():
        raise FileNotFoundError(f"Microsoft GraphRAG index not found: {GRAPHRAG_INDEX}")
    stage_callback("graphrag_retrieval_started", {"index": str(GRAPHRAG_INDEX)})
    report = _json_safe(query_index(
        GRAPHRAG_INDEX, retrieval_question, ollama_url, embedding_model,
        generation_model, thinking="no", answer_instructions=rag_answer_instructions(answer_task),
    ))
    stage_callback("graphrag_answer_synthesized", {
        "communities": len(report["selected_communities"]),
        "evidence_records": len(report["evidence"]),
    })
    write_json(artifact_dir / "graphrag_report.json", report)
    return {
        "query_id": query_id, "system": "graphrag", "system_label": "Microsoft GraphRAG",
        "question": display_question, "answer": report["answer"], "mode": "community graph retrieval",
        "derived_facets": derived_facets, "communities": report["selected_communities"],
        "evidence": report["evidence"], "contexts": [], "claims": [], "paths": [], "provenance": {},
        "citation_details": _graphrag_citation_details(report["evidence"]),
        "warnings": ["GraphRAG uses graph communities and relationship evidence; it does not apply ClimateKG context gating."],
        "artifact_dir": str(artifact_dir),
    }


def _run_plain_rag(
    retrieval_question: str,
    display_question: str,
    query_id: str,
    artifact_dir: Path,
    derived_facets: list[dict[str, Any]],
    answer_task: str,
    ollama_url: str,
    embedding_model: str,
    generation_model: str,
    stage_callback: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    from baselines.plain_rag import plain_rag

    if not (PLAIN_RAG_INDEX / "chunks.jsonl").exists():
        raise FileNotFoundError(f"Plain RAG index not found: {PLAIN_RAG_INDEX}")
    args = Namespace(
        index_dir=str(PLAIN_RAG_INDEX), ollama_url=ollama_url,
        embed_model=embedding_model, chat_model=generation_model, think="no", top_k=5,
        intervention=None, stressor=None, mechanism=None, region=None, climate_group=None,
        climate_category=None, koppen_code=None, strict_intervention=False,
        strict_stressor=False, strict_mechanism=False, strict_region=False,
        strict_climate=False, exclude_cold=False,
    )
    stage_callback("plain_rag_retrieval_started", {"index": str(PLAIN_RAG_INDEX)})
    sources = plain_rag.retrieve(args, retrieval_question)
    prompt = _plain_rag_prompt(retrieval_question, sources, answer_task)
    answer, thinking = plain_rag.chat(ollama_url, generation_model, prompt, "no")
    report = {
        "question": retrieval_question, "sources": sources, "prompt": prompt,
        "answer": answer, "thinking": thinking,
    }
    stage_callback("plain_rag_answer_synthesized", {"source_chunks": len(sources)})
    write_json(artifact_dir / "plain_rag_report.json", report)
    return {
        "query_id": query_id, "system": "plain_rag", "system_label": "Plain RAG",
        "question": display_question, "answer": answer, "mode": "passage retrieval",
        "derived_facets": derived_facets, "sources": sources,
        "contexts": [], "claims": [], "paths": [], "provenance": {},
        "citation_details": {
            f"S{index}": {
                "kind": "source_excerpt",
                "citation_id": f"S{index}",
                "paper": {"title": item["paper"]},
                "source_blocks": [{
                    "id": f"S{index}",
                    "section_path": item.get("heading") or item.get("section"),
                    "text": item["text"],
                }],
            }
            for index, item in enumerate(sources, 1)
        },
        "warnings": ["Plain RAG retrieves source passages; it does not use graph paths or ClimateKG context gating."],
        "artifact_dir": str(artifact_dir),
    }


def append_environmental_context(question: str, facets: list[dict[str, Any]]) -> str:
    if not facets:
        return question
    facts = "\n".join(f"- {item['domain']} / {item['notion']}: {item['description']}" for item in facets)
    return f"{question}\n\nEnvironmental context derived for the selected watershed:\n{facts}"


def rag_answer_instructions(answer_task: str) -> str:
    filename = "webapp_land_use_rag_answer.txt" if answer_task == "planning" else "webapp_process_rag_answer.txt"
    return (PROMPT_ROOT / filename).read_text(encoding="utf-8").strip()


def _plain_rag_prompt(question: str, sources: list[dict[str, Any]], answer_task: str) -> str:
    records = "\n\n".join(
        f"[S{index}] Paper: {item['paper']}; section: {item.get('heading') or item['section']}\n{item['text']}"
        for index, item in enumerate(sources, 1)
    )
    return (
        f"{rag_answer_instructions(answer_task)}\n\n"
        "QUESTION\n\n"
        f"{question}\n\nSOURCE EXCERPTS\n\n{records}"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return _json_safe(value.tolist())
    if hasattr(value, "item"):
        return value.item()
    return value


def _graphrag_citation_details(evidence: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    details = {}
    for item in evidence:
        claim_id = item["claim_id"]
        details[claim_id] = {
            "kind": "graphrag_relationship",
            "citation_id": claim_id,
            "paper": {"id": item["paper"], "title": item["paper_title"]},
            "claim": {
                "id": claim_id,
                "from_state_id": item["source_state"],
                "to_state_id": item["target_state"],
                "relation": item["relation"],
                "description": item["description"],
            },
            "conditioning_facets": item.get("conditioning_facets", []),
            "source_blocks": [
                {
                    "id": block["block_id"],
                    "page": block.get("page"),
                    "text": block.get("text", ""),
                }
                for block in item.get("blocks", [])
            ],
        }
    return details
