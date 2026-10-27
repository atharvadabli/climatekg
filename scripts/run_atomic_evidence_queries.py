from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fixed atomic-evidence diagnostic queries.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.parquet_graph import ParquetGraph
    from climatekg.query import run_query
    from climatekg.utils import write_json

    graph = ParquetGraph(args.graph_root)
    papers = graph.read_corpus()
    indexes = graph.read_indexes()
    semantic_links = graph.read_state_semantic_links()
    cases = read_json(args.dataset)
    run_started = time.time()
    timings = []
    for index, case in enumerate(cases, 1):
        query_id = case["id"]
        report_path = args.output / "artifacts" / query_id / "query_report.json"
        if report_path.exists() and not args.force:
            print(f"[{index}/{len(cases)}] {query_id}: reused", flush=True)
            continue
        started = time.time()
        report = run_query(
            case["question"],
            query_id,
            papers,
            args.output / "artifacts",
            indexes=indexes,
            state_semantic_links=semantic_links,
        )
        timings.append({"case_id": query_id, "elapsed_seconds": time.time() - started})
        print(f"[{index}/{len(cases)}] {query_id}: complete", flush=True)
    write_json(
        args.output / "run_summary.json",
        {
            "graph_root": str(args.graph_root.resolve()),
            "paper_count": len(papers),
            "semantic_link_count": len(semantic_links),
            "query_count": len(cases),
            "elapsed_seconds": time.time() - run_started,
            "query_timings": timings,
        },
    )


if __name__ == "__main__":
    main()
