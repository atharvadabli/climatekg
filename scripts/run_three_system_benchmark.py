from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from argparse import Namespace
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from baselines.climatekg_comparison.graphrag_adapter import query_index
from baselines.climatekg_comparison.ollama import answer as ollama_answer
from baselines.plain_rag.plain_rag import retrieve as plain_retrieve
from climatekg.models import FinalPaper
from climatekg.query import run_query


DEFAULT_SOURCE_ROOT = Path(
    r"E:\Atharv\lulc_suggestor_poc\19_aug_final\climatekg\runtime\outputs\baseline_comparison_20260830_v2"
)
DEFAULT_QUERIES = Path("Paper_writing/neurips2026_submission/evaluation_queries.json")
DEFAULT_OUTPUT = Path("climatekg/runtime/outputs/three_system_benchmark_20260830")


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if hasattr(value, "tolist"):
        return value.tolist()  # type: ignore[union-attr]
    if hasattr(value, "item"):
        return value.item()  # type: ignore[union-attr]
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def _prefix(namespace: str, identifier: str) -> str:
    return f"{namespace}:{identifier}"


def namespace_paper(namespace: str, raw: dict[str, Any]) -> FinalPaper:
    """Give paper-owned objects corpus-unique IDs while retaining shared States."""
    data = copy.deepcopy(raw)
    data["paper"]["id"] = namespace

    for block in data["source_blocks"]:
        block["id"] = _prefix(namespace, block["id"])
        block["paper_id"] = namespace
    for context in data["contexts"]:
        context["id"] = _prefix(namespace, context["id"])
        context["paper_id"] = namespace
        context["parent_ids"] = [_prefix(namespace, value) for value in context["parent_ids"]]
        context["evidence_block_ids"] = [_prefix(namespace, value) for value in context["evidence_block_ids"]]
    for facet in data["facets"]:
        facet["id"] = _prefix(namespace, facet["id"])
        facet["context_id"] = _prefix(namespace, facet["context_id"])
        facet["evidence_block_ids"] = [_prefix(namespace, value) for value in facet["evidence_block_ids"]]
    for transition in data["transitions"]:
        transition["id"] = _prefix(namespace, transition["id"])
        transition["paper_id"] = namespace
        transition["from_context_id"] = _prefix(namespace, transition["from_context_id"])
        transition["to_context_id"] = _prefix(namespace, transition["to_context_id"])
        transition["evidence_block_ids"] = [_prefix(namespace, value) for value in transition["evidence_block_ids"]]
    for claim in data["claims"]:
        claim["id"] = _prefix(namespace, claim["id"])
        claim["paper_id"] = namespace
        claim["scope_id"] = _prefix(namespace, claim["scope_id"])
        claim["conditioning_facet_ids"] = [_prefix(namespace, value) for value in claim["conditioning_facet_ids"]]
        claim["evidence_block_ids"] = [_prefix(namespace, value) for value in claim["evidence_block_ids"]]
    data["evidence_links"] = []
    return FinalPaper.model_validate(data)


def load_shared_corpus(source_root: Path) -> list[FinalPaper]:
    manifest = json.loads((source_root / "corpus" / "corpus_manifest.json").read_text(encoding="utf-8"))
    source_repository = source_root.parents[3]
    papers = []
    for item in manifest:
        artifact = Path(item["artifact"])
        if not artifact.is_absolute():
            artifact = source_repository / artifact
        raw = json.loads(artifact.read_text(encoding="utf-8"))
        papers.append(namespace_paper(item["namespace"], raw))
    return papers


def _plain_args(index_dir: Path, ollama_url: str, embed_model: str, top_k: int) -> Namespace:
    return Namespace(
        index_dir=str(index_dir),
        ollama_url=ollama_url,
        embed_model=embed_model,
        top_k=top_k,
        intervention=None,
        stressor=None,
        mechanism=None,
        region=None,
        climate_group=None,
        climate_category=None,
        koppen_code=None,
        strict_intervention=False,
        strict_stressor=False,
        strict_mechanism=False,
        strict_region=False,
        strict_climate=False,
        exclude_cold=False,
    )


def run_plain(
    question: str,
    source_root: Path,
    ollama_url: str,
    embed_model: str,
    chat_model: str,
    reasoning: str,
    top_k: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    sources = plain_retrieve(
        _plain_args(source_root / "plain_rag" / "index", ollama_url, embed_model, top_k),
        question,
    )
    evidence = []
    for index, source in enumerate(sources, 1):
        evidence.append(
            f"[S{index}] paper={source['paper']} heading={source.get('heading', 'Document')}\n{source['text']}"
        )
    prompt = (
        "TASK\n\nAnswer the scientific question using only the supplied passages. "
        "Cite every substantive statement with [S1], [S2], and so on. Preserve conditions, "
        "contradictions, null findings, and uncertainty. Do not turn transferable evidence into "
        "a local recommendation.\n\n"
        f"QUESTION\n\n{question}\n\nPASSAGES\n\n" + "\n\n".join(evidence)
    )
    raw = ollama_answer(ollama_url, chat_model, prompt, thinking=reasoning)
    return {
        "question": question,
        "retrieval": sources,
        "prompt": prompt,
        "answer": raw.get("message", {}).get("content", ""),
        "thinking": raw.get("message", {}).get("thinking", ""),
        "generation_metrics": {
            key: raw.get(key)
            for key in (
                "prompt_eval_count",
                "eval_count",
                "prompt_eval_duration",
                "eval_duration",
                "total_duration",
                "load_duration",
            )
        },
        "timings": {"total_seconds": round(time.perf_counter() - started, 3)},
    }


def _climate_summary(report: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    thinking = ""
    response_file = None
    for candidate in sorted((artifact_dir / "synthesis").glob("*.attempt*.json"), reverse=True):
        raw = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(raw.get("message"), dict):
            response_file = candidate
            thinking = raw["message"].get("thinking", "")
            break
    return {
        "question": report["query_spec"]["user_question"],
        "query_spec": report["query_spec"],
        "context_evidence_comparisons": report.get("context_evidence_comparisons", []),
        "context_candidates": report["context_candidates"],
        "claim_candidates": report["claim_candidates"],
        "direct_evidence_paths": report.get("direct_evidence_paths", []),
        "graph_paths": report.get("graph_paths", []),
        "paths": report["paths"],
        "alternatives": report["contradictions_and_alternatives"],
        "answer": report["answer"],
        "thinking": thinking,
        "synthesis_response_file": str(response_file.resolve()) if response_file else None,
        "warnings": report["warnings"],
        "artifact_dir": str(artifact_dir.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an auditable three-system query benchmark.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--system", action="append", choices=("plain_rag", "graphrag", "climatekg"))
    parser.add_argument("--query-id", action="append")
    parser.add_argument("--ollama-url", default="http://localhost:11434")
    parser.add_argument("--embed-model", default="qwen3-embedding:4b")
    parser.add_argument("--chat-model", default="qwen3.6:27b")
    parser.add_argument("--reasoning", choices=("no", "low", "medium", "high"), default="medium")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    config = json.loads(args.queries.read_text(encoding="utf-8"))
    queries = [item for item in config["queries"] if not args.query_id or item["id"] in args.query_id]
    systems = args.system or ["plain_rag", "graphrag", "climatekg"]
    args.output.mkdir(parents=True, exist_ok=True)
    _write_json(
        args.output / "run_config.json",
        {
            **vars(args),
            "queries": [item["id"] for item in queries],
            "reasoning_note": (
                "--reasoning configures PlainRAG and the community graph baseline. "
                "ClimateKG uses the validated per-stage profile in climatekg.constants."
            ),
        },
    )
    papers = load_shared_corpus(args.source_root) if "climatekg" in systems else []

    for query in queries:
        query_id, question = query["id"], query["question"]
        if "plain_rag" in systems:
            output = args.output / "plain_rag" / f"{query_id}.json"
            if not output.exists():
                _write_json(output, run_plain(question, args.source_root, args.ollama_url, args.embed_model, args.chat_model, args.reasoning, args.top_k))
        if "graphrag" in systems:
            output = args.output / "graphrag" / f"{query_id}.json"
            if not output.exists():
                result = query_index(
                    args.source_root / "graphrag",
                    question,
                    args.ollama_url,
                    args.embed_model,
                    args.chat_model,
                    max_relationships=args.top_k,
                    thinking=args.reasoning,
                )
                _write_json(output, result)
        if "climatekg" in systems:
            output = args.output / "climatekg" / f"{query_id}.json"
            artifact_dir = args.output / "climatekg_artifacts" / query_id
            if not output.exists():
                report = run_query(question, query_id, papers, args.output / "climatekg_artifacts")
                _write_json(output, _climate_summary(report, artifact_dir))
        print(json.dumps({"query_id": query_id, "status": "complete"}), flush=True)


if __name__ == "__main__":
    main()
