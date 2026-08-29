from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from climatekg.indexer import index_pdf, load_corpus
from climatekg.config import PIPELINE
from climatekg.parquet_graph import ParquetGraph
from climatekg.utils import write_json


ROOT = Path(__file__).resolve().parents[1]


def _relative(path: str | Path, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(candidate)


def _collect_llm_calls(data_root: Path, output_root: Path) -> list[dict[str, Any]]:
    calls = []
    for path in sorted(data_root.glob("P*/extraction/**/*.attempt*.metrics.json")):
        item = json.loads(path.read_text(encoding="utf-8"))
        for key in ("request_path", "raw_response_path", "http_error_path", "transport_error_path"):
            if item.get(key):
                item[key] = _relative(item[key], output_root)
        item["metrics_path"] = _relative(path, output_root)
        item["ollama_total_seconds"] = (item.get("total_duration") or 0) / 1_000_000_000
        item["ollama_prompt_eval_seconds"] = (item.get("prompt_eval_duration") or 0) / 1_000_000_000
        item["ollama_generation_seconds"] = (item.get("eval_duration") or 0) / 1_000_000_000
        calls.append(item)
    return calls


def _paper_rows(data_root: Path) -> list[dict[str, Any]]:
    rows = []
    for paper_dir in sorted(data_root.glob("P*")):
        manifest_path = paper_dir / "manifest.json"
        timing_path = paper_dir / "metrics" / "indexing_timing.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        timing = json.loads(timing_path.read_text(encoding="utf-8")) if timing_path.exists() else {}
        rows.append({
            "paper_id": manifest["paper_id"],
            "status": manifest["status"],
            "wall_elapsed_seconds": timing.get("wall_elapsed_seconds"),
            "measured_phase_seconds": timing.get("measured_phase_seconds"),
            "counts": manifest.get("counts", {}),
            "failure": manifest.get("failure"),
            "timing_path": timing_path.as_posix() if timing_path.exists() else None,
            "phases": timing.get("phases", []),
        })
    return rows


def _write_report(output_root: Path, corpus_spec: list[dict[str, str]], parquet_seconds: float | None, route: str) -> None:
    data_root = output_root / "data"
    papers = _paper_rows(data_root)
    calls = _collect_llm_calls(data_root, output_root)
    complete = [item for item in papers if item["status"] == "complete"]
    total_llm = sum(item["elapsed_seconds"] for item in calls)
    paper_seconds = [item["wall_elapsed_seconds"] for item in complete if item["wall_elapsed_seconds"] is not None]
    phase_groups: dict[str, list[float]] = {}
    for paper in complete:
        for phase in paper["phases"]:
            phase_groups.setdefault(phase["name"], []).append(phase["elapsed_seconds"])
    phase_aggregates = [
        {"phase": name, "papers": len(values), "total_seconds": sum(values), "mean_seconds": statistics.mean(values), "median_seconds": statistics.median(values)}
        for name, values in sorted(phase_groups.items(), key=lambda item: -sum(item[1]))
    ]
    llm_groups: dict[str, list[dict[str, Any]]] = {}
    for call in calls:
        llm_groups.setdefault(call["stage"], []).append(call)
    llm_stage_aggregates = [
        {
            "stage": name,
            "attempts": len(items),
            "total_seconds": sum(item["elapsed_seconds"] for item in items),
            "mean_seconds": statistics.mean(item["elapsed_seconds"] for item in items),
            "prompt_tokens": sum(item.get("prompt_eval_count") or 0 for item in items),
            "output_tokens": sum(item.get("eval_count") or 0 for item in items),
        }
        for name, items in sorted(llm_groups.items(), key=lambda item: -sum(row["elapsed_seconds"] for row in item[1]))
    ]
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "extraction_route": route,
        "requested_papers": len(corpus_spec),
        "registered_papers": len(papers),
        "completed_papers": len(complete),
        "failed_papers": len([item for item in papers if item["status"] not in {"complete", "registered"}]),
        "llm_attempts": len(calls),
        "llm_wall_seconds": total_llm,
        "indexing_wall_seconds": sum(paper_seconds),
        "mean_paper_seconds": statistics.mean(paper_seconds) if paper_seconds else None,
        "median_paper_seconds": statistics.median(paper_seconds) if paper_seconds else None,
        "parquet_build_seconds": parquet_seconds,
        "phase_aggregates": phase_aggregates,
        "llm_stage_aggregates": llm_stage_aggregates,
        "papers": papers,
        "llm_calls": calls,
    }
    write_json(output_root / "benchmark_summary.json", summary)

    lines = [
        "# Indexing Runtime Benchmark",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "## Scope",
        "",
        f"- Extraction route: `{route}`",
        f"- Requested papers: {summary['requested_papers']}",
        f"- Completed papers: {summary['completed_papers']}",
        f"- LLM attempts: {summary['llm_attempts']}",
        f"- Total measured LLM wall time: {total_llm:.1f} s ({total_llm / 60:.1f} min)",
        f"- Total indexing wall time: {sum(paper_seconds):.1f} s ({sum(paper_seconds) / 3600:.2f} h)",
        f"- Mean paper time: {statistics.mean(paper_seconds) / 60:.2f} min" if paper_seconds else "- Mean paper time: unavailable",
        f"- Median paper time: {statistics.median(paper_seconds) / 60:.2f} min" if paper_seconds else "- Median paper time: unavailable",
        f"- Parquet build time: {parquet_seconds:.3f} s" if parquet_seconds is not None else "- Parquet build: not yet run",
        "",
        "## Paper Runtime",
        "",
        "| Paper | Status | Wall time (min) | LLM time (min) | Contexts | Facets | Claims | Timing JSON |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for paper in papers:
        paper_calls = [item for item in calls if item["paper_id"] == paper["paper_id"]]
        llm_seconds = sum(item["elapsed_seconds"] for item in paper_calls)
        elapsed = paper["wall_elapsed_seconds"]
        elapsed_minutes = f"{elapsed / 60:.2f}" if elapsed is not None else ""
        timing_link = _relative(paper["timing_path"], output_root) if paper["timing_path"] else ""
        counts = paper["counts"]
        lines.append(
            f"| `{paper['paper_id']}` | {paper['status']} | {elapsed_minutes} | "
            f"{llm_seconds / 60:.2f} | {counts.get('contexts', '')} | {counts.get('facets', '')} | "
            f"{counts.get('claims', '')} | `{timing_link}` |"
        )
    lines.extend([
        "",
        "## Aggregate Phase Runtime",
        "",
        "| Phase | Papers | Total minutes | Mean seconds | Median seconds |",
        "|---|---:|---:|---:|---:|",
    ])
    for item in phase_aggregates:
        lines.append(f"| `{item['phase']}` | {item['papers']} | {item['total_seconds'] / 60:.2f} | {item['mean_seconds']:.2f} | {item['median_seconds']:.2f} |")
    lines.extend([
        "",
        "## Aggregate LLM Runtime",
        "",
        "| LLM stage | Attempts | Total minutes | Mean seconds | Prompt tokens | Output tokens |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for item in llm_stage_aggregates:
        lines.append(f"| `{item['stage']}` | {item['attempts']} | {item['total_seconds'] / 60:.2f} | {item['mean_seconds']:.2f} | {item['prompt_tokens']} | {item['output_tokens']} |")
    lines.extend([
        "",
        "## Phase Runtime",
        "",
        "Each row below is checkpointed immediately after the phase. Failed phases are retained.",
        "",
        "| Paper | Phase | Status | Seconds |",
        "|---|---|---|---:|",
    ])
    for paper in papers:
        for phase in paper["phases"]:
            lines.append(f"| `{paper['paper_id']}` | `{phase['name']}` | {phase['status']} | {phase['elapsed_seconds']:.3f} |")
    lines.extend([
        "",
        "## Exact LLM Calls",
        "",
        "Every request path below contains the exact model name, system message, populated user message, JSON Schema, temperature, context window, and thinking level sent to Ollama. The response path contains the raw Ollama response. No prompt is reconstructed from a template in this report.",
        "",
        "| Paper | Stage | Attempt | Valid | Wall seconds | Prompt tokens | Output tokens | Exact request | Raw response |",
        "|---|---|---:|---|---:|---:|---:|---|---|",
    ])
    for item in calls:
        response = f"`{item.get('raw_response_path', '')}`" if item.get("raw_response_path") else ""
        lines.append(
            f"| `{item['paper_id']}` | `{item['stage']}` | {item['attempt']} | {item['validated']} | "
            f"{item['elapsed_seconds']:.3f} | {item.get('prompt_eval_count', '')} | {item.get('eval_count', '')} | "
            f"`{item['request_path']}` | {response} |"
        )
    lines.extend([
        "",
        "## Files",
        "",
        "- `benchmark_summary.json`: machine-readable paper, phase, and LLM-call measurements.",
        "- `benchmark_progress.json`: updated after each attempted paper.",
        "- `data/P*/extraction/**/*.request.json`: exact populated LLM requests.",
        "- `data/P*/extraction/**/*.attempt*.json`: raw LLM responses.",
        "- `data/P*/extraction/**/*.attempt*.metrics.json`: per-attempt timing and token counts.",
        "- `parquet_graph/`: final Parquet graph and FAISS indexes for completed papers.",
    ])
    (output_root / "INDEXING_TIMING_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path(r"E:\Atharv\lit_200\files"))
    parser.add_argument("--corpus", type=Path, default=ROOT / "config" / "indexing_benchmark_corpus.json")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--paper-id", action="append", dest="paper_ids")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--route", choices=("combined", "staged"), required=True)
    parser.add_argument("--thinking", choices=("no", "low", "medium", "high"))
    return parser


def main() -> None:
    args = _parser().parse_args()
    output_root = args.output_root.resolve()
    PIPELINE["paper_mapping"]["combined_extraction_enabled"] = args.route == "combined"
    if args.thinking:
        stage_name = "small_paper_extraction" if args.route == "combined" else "paper_map"
        PIPELINE["ollama"]["stages"][stage_name]["thinking"] = args.thinking
    data_root = output_root / "data"
    output_root.mkdir(parents=True, exist_ok=True)
    corpus_spec = json.loads(args.corpus.read_text(encoding="utf-8"))
    if args.paper_ids:
        requested = set(args.paper_ids)
        corpus_spec = [item for item in corpus_spec if item["paper_id"] in requested]
    corpus_spec = corpus_spec[: args.limit]
    write_json(output_root / "corpus_manifest.json", corpus_spec)
    write_json(output_root / "run_configuration.json", {
        "route": args.route,
        "thinking_override": args.thinking,
        "combined_extraction_enabled": PIPELINE["paper_mapping"]["combined_extraction_enabled"],
    })
    if args.report_only:
        parquet_path = output_root / "parquet_build.json"
        parquet_seconds = json.loads(parquet_path.read_text(encoding="utf-8"))["elapsed_seconds"] if parquet_path.exists() else None
        _write_report(output_root, corpus_spec, parquet_seconds, args.route)
        return
    progress = []
    for item in corpus_spec:
        pdf_path = args.input_dir / item["filename"]
        started = time.perf_counter()
        try:
            result = index_pdf(pdf_path, data_root, item["paper_id"])
            row = {"paper_id": item["paper_id"], "status": "complete", "elapsed_seconds": time.perf_counter() - started, "counts": {name: len(getattr(result, name)) for name in ("source_blocks", "contexts", "facets", "transitions", "claims", "states")}}
        except Exception as exc:
            row = {"paper_id": item["paper_id"], "status": "failed", "elapsed_seconds": time.perf_counter() - started, "error": {"type": type(exc).__name__, "message": str(exc)}}
        progress.append(row)
        write_json(output_root / "benchmark_progress.json", progress)
        _write_report(output_root, corpus_spec, None, args.route)
        print(json.dumps(row), flush=True)

    parquet_started = time.perf_counter()
    counts = ParquetGraph(output_root / "parquet_graph").write_corpus(load_corpus(data_root))
    parquet_seconds = time.perf_counter() - parquet_started
    write_json(output_root / "parquet_build.json", {"elapsed_seconds": parquet_seconds, "table_counts": counts})
    _write_report(output_root, corpus_spec, parquet_seconds, args.route)
    print(json.dumps({"parquet_seconds": parquet_seconds, "table_counts": counts}), flush=True)


if __name__ == "__main__":
    main()
