from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build auditable semantic links among retained ClimateKG States.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--minimum-similarity", type=float)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--candidates-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.config import PIPELINE
    from climatekg.ollama import OllamaClient
    from climatekg.parquet_graph import ParquetGraph
    from climatekg.semantic_links import adjudicate_state_link_candidates, generate_state_link_candidates
    from climatekg.utils import write_json

    config = PIPELINE["state_semantic_links"]
    top_k = args.top_k if args.top_k is not None else config["candidate_top_k"]
    minimum_similarity = (
        args.minimum_similarity
        if args.minimum_similarity is not None
        else config["minimum_candidate_similarity"]
    )
    batch_size = args.batch_size if args.batch_size is not None else config["adjudication_batch_size"]
    graph = ParquetGraph(args.graph_root)
    papers = graph.read_corpus()
    states, candidates = generate_state_link_candidates(
        papers,
        top_k=top_k,
        minimum_similarity=minimum_similarity,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "candidates.json", [item.model_dump() for item in candidates])
    if args.candidates_only:
        summary = {
            "graph_root": str(args.graph_root.resolve()),
            "state_count": len(states),
            "candidate_count": len(candidates),
            "accepted_link_count": 0,
            "status": "candidates_only",
        }
        write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, indent=2))
        return
    links, audit = adjudicate_state_link_candidates(
        states,
        candidates,
        OllamaClient(),
        args.output / "llm_calls",
        batch_size=batch_size,
    )
    count = graph.write_state_semantic_links(links)
    summary = {
        "graph_root": str(args.graph_root.resolve()),
        "state_count": len(states),
        "candidate_count": len(candidates),
        "accepted_link_count": count,
        "decision_counts": {
            relation: sum(item["relation"] == relation for item in audit)
            for relation in ("equivalent_to", "narrower_than", "broader_than", "unrelated", "uncertain")
        },
    }
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
