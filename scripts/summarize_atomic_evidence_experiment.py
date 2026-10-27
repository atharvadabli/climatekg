from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def recall(expected: set[str], actual: set[str]) -> float:
    return len(expected & actual) / len(expected) if expected else 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Claim flow for the atomic-evidence experiment.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for case in read_json(args.dataset):
        case_dir = args.artifacts / case["id"]
        report = read_json(case_dir / "query_report.json")
        child_reports = [read_json(path) for path in sorted((case_dir / "sq").glob("*/query_report.json"))]
        retrieval_reports = child_reports or [report]
        expected = set(case["expected_claim_ids"])
        candidates = {item["claim_id"] for item in report.get("claim_candidates", [])}
        paths = {claim_id for path in report.get("paths", []) for claim_id in path["claim_ids"]}
        synthesis_paths = report.get("synthesis_package", {}).get("paths", []) or report.get("paths", [])
        synthesis = {claim_id for path in synthesis_paths for claim_id in path["claim_ids"]}
        selected = {
            claim_id
            for child in retrieval_reports
            for claim_id in (child.get("evidence_subgraph") or {}).get("claim_ids", [])
        }
        uncovered = [
            item
            for child in retrieval_reports
            for item in (child.get("evidence_subgraph") or {}).get("uncovered_requirement_ids", [])
        ]
        rows.append(
            {
                "case_id": case["id"],
                "expected_claim_count": len(expected),
                "candidate_recall": recall(expected, candidates),
                "subgraph_recall": recall(expected, selected),
                "path_recall": recall(expected, paths),
                "synthesis_recall": recall(expected, synthesis),
                "missing_from_candidates": sorted(expected - candidates),
                "missing_from_subgraph": sorted(expected - selected),
                "missing_from_synthesis": sorted(expected - synthesis),
                "uncovered_requirements": uncovered,
                "answer": report.get("answer", ""),
            }
        )
    summary = {
        "query_count": len(rows),
        "mean_candidate_recall": sum(row["candidate_recall"] for row in rows) / len(rows),
        "mean_subgraph_recall": sum(row["subgraph_recall"] for row in rows) / len(rows),
        "mean_path_recall": sum(row["path_recall"] for row in rows) / len(rows),
        "mean_synthesis_recall": sum(row["synthesis_recall"] for row in rows) / len(rows),
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
