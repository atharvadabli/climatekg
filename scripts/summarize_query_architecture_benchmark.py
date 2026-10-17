"""Combine the ten-query baseline and query-architecture experiment records."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any


SYSTEMS = (
    "plain_rag",
    "graphrag",
    "climatekg_baseline",
    "evidence_union",
    "soft_context",
    "graph_expansion",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def event_data(record: dict[str, Any], stage: str) -> dict[str, Any]:
    for event in record.get("events", []):
        if event.get("stage") == stage:
            return event.get("data", {})
    return {}


def trace_summary(record: dict[str, Any]) -> dict[str, Any]:
    contexts = event_data(record, "contexts_retrieved")
    claims = event_data(record, "claims_ranked")
    paths = event_data(record, "paths_searched")
    assembled = event_data(record, "evidence_assembled")
    return {
        "top_context_ids": [item["context_id"] for item in contexts.get("top_contexts", [])],
        "top_claim_ids": [item["claim_id"] for item in claims.get("top_claims", [])],
        "path_count": paths.get("path_count"),
        "direct_evidence_count": assembled.get("direct_path_count"),
        "graph_evidence_count": assembled.get("graph_path_count"),
    }


def compact_record(record: dict[str, Any], structured: bool = False) -> dict[str, Any]:
    output = {
        "status": record.get("status"),
        "answer": record.get("generated_answer", ""),
        "metrics": record.get("metrics", {}),
    }
    if structured:
        output["trace"] = trace_summary(record)
        output["warnings"] = record.get("result", {}).get("warnings", [])
    return output


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [record for record in records if record.get("status") == "complete"]
    metrics = [record.get("metrics", {}) for record in complete]
    latencies = [float(item["elapsed_seconds"]) for item in metrics if item.get("elapsed_seconds") is not None]
    return {
        "queries": len(records),
        "complete": len(complete),
        "expected_paper_hits": sum(item.get("expected_paper_hit") is True for item in metrics),
        "mean_reference_token_f1": round(statistics.fmean(item.get("reference_token_f1", 0.0) for item in metrics), 4)
        if metrics
        else None,
        "mean_expected_term_coverage": round(
            statistics.fmean(item.get("expected_term_coverage", 0.0) for item in metrics), 4
        )
        if metrics
        else None,
        "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else None,
    }


def markdown(payload: dict[str, Any]) -> str:
    labels = {
        "plain_rag": "PlainRAG",
        "graphrag": "Microsoft GraphRAG",
        "climatekg_baseline": "ClimateKG baseline",
        "evidence_union": "ClimateKG evidence union",
        "soft_context": "ClimateKG soft context",
        "graph_expansion": "ClimateKG graph expansion",
    }
    lines = [
        "# Ten-query architecture benchmark",
        "",
        "All systems answer the same ten development questions. ClimateKG variants reuse frozen query parses so retrieval changes are compared without query-parser variation. Metrics are deterministic diagnostics, not a substitute for scientific review.",
        "",
        "| System | Complete | Expected paper hit | Mean token F1 | Mean qualifier coverage | Median latency (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for system in SYSTEMS:
        item = payload["aggregate"][system]
        lines.append(
            f"| {labels[system]} | {item['complete']}/{item['queries']} | "
            f"{item['expected_paper_hits']}/{item['queries']} | {item['mean_reference_token_f1']:.4f} | "
            f"{item['mean_expected_term_coverage']:.4f} | {item['median_latency_seconds']:.1f} |"
        )
    lines.extend(
        [
            "",
            "## Per-query token F1",
            "",
            "| Query | PlainRAG | GraphRAG | Baseline | Evidence union | Soft context | Graph expansion |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for case in payload["cases"]:
        values = [case["systems"][system]["metrics"].get("reference_token_f1", 0.0) for system in SYSTEMS]
        lines.append(f"| {case['id']} | " + " | ".join(f"{value:.4f}" for value in values) + " |")
    lines.extend(
        [
            "",
            "The complete questions, reference answers, generated answers, metrics, and compact ClimateKG traces are stored in `comparison.json` beside this file.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = args.project_root.resolve()
    prior = read_json(root / "evaluation/output/climatekg_benchmark/runs/v1/results_full.json")[:10]
    baseline_override = read_json(args.output / "variants/baseline/results/CKGQ0003.json")
    cases: list[dict[str, Any]] = []
    records_by_system: dict[str, list[dict[str, Any]]] = {system: [] for system in SYSTEMS}

    for old in prior:
        case_id = old["case"]["id"]
        raw: dict[str, dict[str, Any]] = {
            "plain_rag": old["systems"]["plain_rag"],
            "graphrag": old["systems"]["graphrag"],
            "climatekg_baseline": baseline_override if case_id == "CKGQ0003" else old["systems"]["climatekg"],
        }
        for variant in ("evidence_union", "soft_context", "graph_expansion"):
            raw[variant] = read_json(args.output / f"variants/{variant}/results/{case_id}.json")
        systems = {}
        for system, record in raw.items():
            records_by_system[system].append(record)
            systems[system] = compact_record(record, structured=system.startswith("climatekg") or system in {
                "evidence_union", "soft_context", "graph_expansion"
            })
        cases.append(
            {
                "id": case_id,
                "category": old["case"].get("category"),
                "question": old["case"]["question"],
                "reference_answer": old["case"]["reference_answer"],
                "expected_paper_ids": [item["paper_id"] for item in old["case"].get("source_papers", [])],
                "required_qualifiers": old["case"].get("required_qualifiers", []),
                "systems": systems,
            }
        )

    payload = {
        "protocol": {
            "query_count": 10,
            "corpus_papers": 115,
            "climatekg_query_parse": "frozen and shared by all three architecture variants",
            "baseline_note": "CKGQ0003 baseline was rerun with its frozen parse because the original record failed during Earth Engine authentication.",
        },
        "aggregate": {system: aggregate(records) for system, records in records_by_system.items()},
        "cases": cases,
    }
    write_json(args.output / "comparison.json", payload)
    (args.output / "summary.md").write_text(markdown(payload), encoding="utf-8")


if __name__ == "__main__":
    main()
