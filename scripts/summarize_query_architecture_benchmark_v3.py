"""Summarize the 30-case comparison of the strongest three systems."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


SYSTEMS = ("plain_rag", "graphrag", "climatekg_evidence_union")
LABELS = {
    "plain_rag": "PlainRAG",
    "graphrag": "Microsoft GraphRAG",
    "climatekg_evidence_union": "ClimateKG evidence union",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    complete = [record for record in records if record.get("status") == "complete"]
    metrics = [record["metrics"] for record in complete if record.get("metrics")]
    latencies = [float(item["elapsed_seconds"]) for item in metrics]
    return {
        "queries": len(records),
        "complete": len(complete),
        "expected_paper_hits": sum(item.get("expected_paper_hit") is True for item in metrics),
        "mean_reference_token_f1": (
            round(statistics.fmean(item["reference_token_f1"] for item in metrics), 4)
            if metrics
            else None
        ),
        "mean_expected_term_coverage": (
            round(statistics.fmean(item["expected_term_coverage"] for item in metrics), 4)
            if metrics
            else None
        ),
        "median_latency_seconds": round(statistics.median(latencies), 3) if latencies else None,
    }


def table_row(label: str, item: dict[str, Any]) -> str:
    f1 = "--" if item["mean_reference_token_f1"] is None else f"{item['mean_reference_token_f1']:.4f}"
    coverage = (
        "--"
        if item["mean_expected_term_coverage"] is None
        else f"{item['mean_expected_term_coverage']:.4f}"
    )
    latency = (
        "--" if item["median_latency_seconds"] is None else f"{item['median_latency_seconds']:.1f}"
    )
    return (
        f"| {label} | {item['complete']}/{item['queries']} | "
        f"{item['expected_paper_hits']}/{item['queries']} | {f1} | {coverage} | {latency} |"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--variants-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cases = read_json(args.dataset)
    rows = []
    by_system: dict[str, list[dict[str, Any]]] = {system: [] for system in SYSTEMS}
    by_category: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: {system: [] for system in SYSTEMS}
    )
    for case in cases:
        systems = {}
        for system in SYSTEMS:
            record = read_json(args.variants_root / system / "results" / f"{case['id']}.json")
            by_system[system].append(record)
            by_category[case["category"]][system].append(record)
            systems[system] = {
                "status": record.get("status"),
                "answer": record.get("generated_answer", ""),
                "metrics": record.get("metrics"),
                "error": record.get("error"),
            }
        rows.append(
            {
                "id": case["id"],
                "category": case["category"],
                "question": case["question"],
                "reference_answer": case["reference_answer"],
                "gold_evidence": case["gold_evidence"],
                "required_qualifiers": case["required_qualifiers"],
                "systems": systems,
            }
        )

    payload = {
        "protocol": {
            "dataset": str(args.dataset.resolve()),
            "gold_policy": "current-paper findings and analyses only",
            "query_parse": "one prepared QuerySpec used by ClimateKG",
            "metric_note": (
                "Expected-paper hit is a retrieval diagnostic. Token F1 and exact qualifier coverage "
                "are lexical diagnostics, not substitutes for scientific human review."
            ),
        },
        "aggregate": {system: aggregate(records) for system, records in by_system.items()},
        "by_category": {
            category: {system: aggregate(records) for system, records in systems.items()}
            for category, systems in sorted(by_category.items())
        },
        "cases": rows,
    }
    write_json(args.output / "comparison.json", payload)

    header = [
        "| System | Complete | Expected paper hit | Mean token F1 | Mean qualifier coverage | Median latency (s) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    lines = [
        "# Thirty-query retrieval benchmark",
        "",
        "Gold evidence is restricted to findings or analyses presented by the indexed paper itself. "
        "The three systems use the same corpus and questions.",
        "",
        *header,
    ]
    for system in SYSTEMS:
        lines.append(table_row(LABELS[system], payload["aggregate"][system]))
    for category, systems in payload["by_category"].items():
        lines.extend(["", f"## {category.replace('_', ' ').title()}", "", *header])
        for system in SYSTEMS:
            lines.append(table_row(LABELS[system], systems[system]))
    lines.extend(
        [
            "",
            "Expected-paper hit measures whether retrieval reached the paper containing the gold finding. "
            "Token overlap and exact qualifier coverage are diagnostic only; the answers still require "
            "manual review for scientific correctness, support, and handling of contradictions.",
        ]
    )
    (args.output / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
