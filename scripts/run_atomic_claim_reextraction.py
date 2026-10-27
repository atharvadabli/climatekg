from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run additive atomic Claim re-extraction on a fixed corpus.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--output-graph", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.atomic_reextract import reextract_atomic_claims
    from climatekg.ollama import OllamaClient
    from climatekg.parquet_graph import ParquetGraph
    from climatekg.utils import write_json

    source = ParquetGraph(args.source_graph)
    papers = source.read_corpus()
    client = OllamaClient()
    updated, summaries = [], []
    started = time.time()
    for index, paper in enumerate(papers, 1):
        paper_started = time.time()
        result, summary = reextract_atomic_claims(paper, args.artifacts, client)
        summary["elapsed_seconds"] = time.time() - paper_started
        updated.append(result)
        summaries.append(summary)
        final_dir = args.artifacts / paper.paper.id / "final"
        write_json(final_dir / "final_paper.json", result.model_dump(by_alias=True))
        print(f"[{index}/{len(papers)}] {paper.paper.id}: {summary['old_claim_count']} -> {summary['combined_claim_count']} Claims")
    counts = ParquetGraph(args.output_graph).write_corpus(updated)
    run_summary = {
        "paper_count": len(updated),
        "elapsed_seconds": time.time() - started,
        "graph_counts": counts,
        "papers": summaries,
    }
    write_json(args.artifacts / "run_summary.json", run_summary)
    print(json.dumps(run_summary, indent=2))


if __name__ == "__main__":
    main()
