from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

from climatekg.indexer import index_pdf, load_corpus
from climatekg.models import FinalPaper
from climatekg.parquet_graph import ParquetGraph
from climatekg.utils import write_json
from run_indexing_benchmark import _write_report
from run_reasoning_matrix import apply_profile


ROOT = Path(__file__).resolve().parents[1]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path(r"E:\Atharv\lit_200\files"))
    parser.add_argument("--corpus", type=Path, default=ROOT / "config" / "indexing_benchmark_corpus.json")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--mapping", choices=("no", "low", "medium"), default="low")
    parser.add_argument("--claims", choices=("no", "low", "medium"), default="no")
    parser.add_argument("--downstream", choices=("no", "low", "medium"), default="no")
    parser.add_argument("--report-only", action="store_true")
    return parser


def _write_profile_benchmark(output_root: Path, profile: str) -> None:
    summary = json.loads((output_root / "benchmark_summary.json").read_text(encoding="utf-8"))
    complete = [item for item in summary["papers"] if item["status"] == "complete"]
    failed = [item for item in summary["papers"] if item["status"] not in {"complete", "registered"}]
    minutes = [item["wall_elapsed_seconds"] / 60 for item in complete if item.get("wall_elapsed_seconds") is not None]
    lines = [
        "# Selected Reasoning Profile Benchmark",
        "",
        f"Profile: `{profile}`",
        "",
        f"- Completed papers: {len(complete)}",
        f"- Failed papers: {len(failed)}",
        f"- Mean paper runtime: {statistics.mean(minutes):.2f} minutes" if minutes else "- Mean paper runtime: unavailable",
        f"- Median paper runtime: {statistics.median(minutes):.2f} minutes" if minutes else "- Median paper runtime: unavailable",
        f"- Total LLM time: {summary['llm_wall_seconds'] / 60:.2f} minutes",
        f"- Projected serial time for 50 papers: {statistics.mean(minutes) * 50 / 60:.2f} hours" if minutes else "- Projected serial time for 50 papers: unavailable",
        f"- Parquet/FAISS build: {summary['parquet_build_seconds']:.2f} seconds" if summary.get("parquet_build_seconds") is not None else "- Parquet/FAISS build: unavailable",
        "",
        "| Paper | Status | Runtime min | Contexts | Facets | Transitions | Claims |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for paper in summary["papers"]:
        counts = paper.get("counts", {})
        elapsed = paper.get("wall_elapsed_seconds")
        lines.append(
            f"| `{paper['paper_id']}` | {paper['status']} | {elapsed / 60:.2f} | "
            f"{counts.get('contexts', '')} | {counts.get('facets', '')} | "
            f"{counts.get('transitions', '')} | {counts.get('claims', '')} |"
            if elapsed is not None
            else f"| `{paper['paper_id']}` | {paper['status']} |  |  |  |  |  |"
        )
    if failed:
        lines.extend(["", "## Failures", ""])
        for paper in failed:
            lines.append(f"- `{paper['paper_id']}`: `{json.dumps(paper.get('failure'))}`")
    lines.extend([
        "",
        "See `INDEXING_TIMING_REPORT.md` for every phase, exact request path, raw response path, token count, and LLM-call duration.",
    ])
    (output_root / "BENCHMARK.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = _parser().parse_args()
    profile = apply_profile(args.mapping, args.claims, args.downstream)
    output_root = args.output_root.resolve()
    data_root = output_root / "data"
    output_root.mkdir(parents=True, exist_ok=True)
    corpus_spec: list[dict[str, Any]] = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.paper_ids:
        requested = set(args.paper_ids)
        corpus_spec = [item for item in corpus_spec if item["paper_id"] in requested]
    corpus_spec = corpus_spec[:args.limit]
    write_json(output_root / "corpus_manifest.json", corpus_spec)
    write_json(output_root / "reasoning_profile.json", {"profile": profile, "mapping": args.mapping, "claims": args.claims, "downstream": args.downstream})
    if not args.report_only:
        progress_path = output_root / "benchmark_progress.json"
        progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else []
        progress_by_id = {row["paper_id"]: row for row in progress}
        for item in corpus_spec:
            final_path = data_root / item["paper_id"] / "final" / "final_paper.json"
            if final_path.exists():
                final = FinalPaper.model_validate_json(final_path.read_text(encoding="utf-8"))
                row = {
                    "paper_id": item["paper_id"],
                    "status": "complete",
                    "resume_action": "reused_complete_artifact",
                    "elapsed_seconds": progress_by_id.get(item["paper_id"], {}).get("elapsed_seconds"),
                    "counts": {name: len(getattr(final, name)) for name in ("source_blocks", "contexts", "facets", "transitions", "claims", "states")},
                }
                progress_by_id[item["paper_id"]] = row
                progress = [progress_by_id[spec["paper_id"]] for spec in corpus_spec if spec["paper_id"] in progress_by_id]
                write_json(progress_path, progress)
                print(json.dumps(row), flush=True)
                continue
            started = time.perf_counter()
            try:
                final = index_pdf(args.input_dir / item["filename"], data_root, item["paper_id"])
                row = {
                    "paper_id": item["paper_id"],
                    "status": "complete",
                    "elapsed_seconds": time.perf_counter() - started,
                    "counts": {name: len(getattr(final, name)) for name in ("source_blocks", "contexts", "facets", "transitions", "claims", "states")},
                }
            except Exception as exc:
                row = {"paper_id": item["paper_id"], "status": "failed", "elapsed_seconds": time.perf_counter() - started, "error": {"type": type(exc).__name__, "message": str(exc)}}
            progress_by_id[item["paper_id"]] = row
            progress = [progress_by_id[spec["paper_id"]] for spec in corpus_spec if spec["paper_id"] in progress_by_id]
            write_json(progress_path, progress)
            _write_report(output_root, corpus_spec, None)
            print(json.dumps(row), flush=True)
        graph_started = time.perf_counter()
        counts = ParquetGraph(output_root / "parquet_graph").write_corpus(load_corpus(data_root))
        graph_seconds = time.perf_counter() - graph_started
        write_json(output_root / "parquet_build.json", {"elapsed_seconds": graph_seconds, "table_counts": counts})
    parquet_path = output_root / "parquet_build.json"
    parquet_seconds = json.loads(parquet_path.read_text(encoding="utf-8"))["elapsed_seconds"] if parquet_path.exists() else None
    _write_report(output_root, corpus_spec, parquet_seconds)
    _write_profile_benchmark(output_root, profile)


if __name__ == "__main__":
    main()
