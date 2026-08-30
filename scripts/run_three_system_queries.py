#!/usr/bin/env python3
"""Run the ClimateKG query pipeline over the shared three-system benchmark corpus.

Plain RAG and entity-adapted GraphRAG are driven by
`baselines/climatekg_comparison/run.py`. This script covers the third system so
that all three answer the same questions against the same 18 papers, and records
per-stage retrieval telemetry alongside wall-clock latency.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from climatekg.parquet_graph import ParquetGraph
from climatekg.query import run_query


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--query-id", action="append", dest="query_ids")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    queries = json.loads(args.queries.read_text(encoding="utf-8"))["queries"]
    if args.query_ids:
        wanted = set(args.query_ids)
        queries = [query for query in queries if query["id"] in wanted]

    graph = ParquetGraph(args.graph_root)
    papers, indexes = graph.read_corpus(), graph.read_indexes()
    args.output_root.mkdir(parents=True, exist_ok=True)

    timings_path = args.output_root / "timings.json"
    timings = json.loads(timings_path.read_text(encoding="utf-8")) if timings_path.exists() else {}

    for query in queries:
        query_id = query["id"]
        report_path = args.output_root / query_id / "query_report.json"
        if report_path.exists() and not args.overwrite:
            print(f"skip {query_id}: {report_path} exists", flush=True)
            continue
        stages: list[dict[str, object]] = []
        started = time.perf_counter()

        def record(name: str, details: dict[str, object]) -> None:
            stages.append({"stage": name, "elapsed_seconds": round(time.perf_counter() - started, 3), "details": details})
            print(f"  [{stages[-1]['elapsed_seconds']:>8.2f}s] {name}", flush=True)

        print(f"running {query_id}", flush=True)
        report = run_query(query["question"], query_id, papers, args.output_root, stage_callback=record, indexes=indexes)
        elapsed = time.perf_counter() - started
        (args.output_root / query_id / "stage_trace.json").write_text(
            json.dumps(stages, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        timings[query_id] = {
            "answer_seconds": round(elapsed, 3),
            "warnings": report["warnings"],
            "path_count": len(report["paths"]),
            "claim_candidate_count": len(report["claim_candidates"]),
        }
        timings_path.write_text(json.dumps(timings, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"done {query_id} in {elapsed:.2f}s", flush=True)

    print(json.dumps(timings, indent=2))


if __name__ == "__main__":
    main()
