from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Recompose saved compound-query evidence without rerunning retrieval.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--input-artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.extraction_models import QueryPlan
    from climatekg.ollama import OllamaClient
    from climatekg.parquet_graph import ParquetGraph
    from climatekg.query import Corpus, _synthesize_combined_evidence
    from climatekg.utils import write_json

    corpus = Corpus(ParquetGraph(args.graph_root).read_corpus())
    client = OllamaClient()
    cases = read_json(args.dataset)
    timings = []
    for index, case in enumerate(cases, 1):
        source_dir = args.input_artifacts / case["id"]
        parent = read_json(source_dir / "query_report.json")
        child_paths = sorted((source_dir / "sq").glob("*/query_report.json"))
        destination = args.output / "artifacts" / case["id"]
        destination.mkdir(parents=True, exist_ok=True)
        started = time.time()
        if child_paths:
            child_reports = [read_json(path) for path in child_paths]
            plan = QueryPlan.model_validate(parent["query_plan"])
            answer, synthesis, warnings = _synthesize_combined_evidence(
                case["question"],
                case["id"],
                plan,
                child_reports,
                corpus,
                client,
                destination,
                parent.get("answer_task", "process"),
            )
            parent["answer"] = answer
            parent["synthesis"] = synthesis
            parent["warnings"] = list(dict.fromkeys([*parent.get("warnings", []), *warnings]))
            parent["recomposition_source"] = str(source_dir.resolve())
        else:
            answer = parent.get("answer", "")
        write_json(destination / "query_report.json", parent)
        (destination / "answer.md").write_text(answer, encoding="utf-8")
        timings.append({"case_id": case["id"], "elapsed_seconds": time.time() - started})
        print(f"[{index}/{len(cases)}] {case['id']}: {'recomposed' if child_paths else 'copied'}", flush=True)
    write_json(args.output / "run_summary.json", {"query_count": len(cases), "query_timings": timings})


if __name__ == "__main__":
    main()
