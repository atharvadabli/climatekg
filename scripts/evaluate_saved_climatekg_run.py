from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from climatekg.config import QUERY_PIPELINE
from climatekg.query import _balanced_evidence_rows


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def claim_evidence(graph_root: Path) -> dict[str, list[str]]:
    table = pq.read_table(graph_root / "claims.parquet", columns=["id", "evidence_block_ids"])
    result: dict[str, list[str]] = {}
    for row in table.to_pylist():
        value = row["evidence_block_ids"]
        result[row["id"]] = json.loads(value) if isinstance(value, str) else list(value or [])
    return result


def claim_papers(graph_root: Path) -> dict[str, str]:
    table = pq.read_table(graph_root / "claims.parquet", columns=["id", "paper_id"])
    return {row["id"]: row["paper_id"] for row in table.to_pylist()}


def leaf_reports(case_dir: Path) -> list[dict[str, Any]]:
    paths = sorted((case_dir / "sq").glob("q*/query_report.json"))
    if not paths:
        paths = [case_dir / "query_report.json"]
    return [read_json(path) for path in paths]


def candidate_claim_ids(reports: list[dict[str, Any]]) -> list[str]:
    sequences = [
        [item["claim_id"] for item in report.get("claim_candidates", [])]
        for report in reports
    ]
    result: list[str] = []
    depth = 0
    while any(depth < len(sequence) for sequence in sequences):
        for sequence in sequences:
            if depth < len(sequence):
                result.append(sequence[depth])
        depth += 1
    return unique(result)


def delivered_claim_ids(reports: list[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    for report in reports:
        package = report.get("synthesis_package", {})
        for path in package.get("paths", []):
            result.extend(path.get("claim_ids", []))
        result.extend(
            item["claim_id"]
            for item in package.get("contradictions_and_alternatives", [])
        )
    return unique(result)


def replayed_delivered_claim_ids(
    reports: list[dict[str, Any]], paper_by_claim: dict[str, str]
) -> list[str]:
    """Replay only deterministic evidence allocation with the current settings."""
    config = QUERY_PIPELINE["evidence_assembly"]
    result: list[str] = []
    for report in reports:
        eligible = [
            row
            for row in report.get("claim_candidates", [])
            if {"claim_ann", "source_block_ann", "transition_ann"}
            & set(row.get("channels", []))
            and row.get("applicability_status") != "incompatible"
        ]
        selected = _balanced_evidence_rows(
            eligible,
            paper_by_claim,
            set(report.get("dependency_paper_ids", [])),
            config["direct_claim_paths"],
            config["direct_selection_slots"],
        )
        result.extend(row["claim_id"] for row in selected)
        result.extend(
            claim_id
            for path in report.get("graph_paths", [])
            for claim_id in path.get("claim_ids", [])
        )
        result.extend(
            item["claim_id"]
            for item in report.get("contradictions_and_alternatives", [])
        )
    return unique(result)


def cited_claim_ids(report: dict[str, Any]) -> list[str]:
    return unique(
        claim_id
        for item in report.get("synthesis", {}).get("items", [])
        for claim_id in item.get("support_claim_ids", [])
    )


def block_order(claim_ids: list[str], evidence: dict[str, list[str]]) -> list[str]:
    return unique([block for claim_id in claim_ids for block in evidence.get(claim_id, [])])


def recall(items: list[str], gold: set[str], limit: int | None = None) -> float:
    if not gold:
        return 1.0
    selected = items if limit is None else items[:limit]
    return len(set(selected) & gold) / len(gold)


def expected_paper_hit(
    claim_ids: list[str], expected: set[str], paper_by_claim: dict[str, str]
) -> bool:
    return bool({paper_by_claim[item] for item in claim_ids if item in paper_by_claim} & expected)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Score candidate, delivered, and cited evidence in a saved ClimateKG run."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifact-suffix", default="")
    args = parser.parse_args()

    dataset = read_json(args.dataset)
    evidence = claim_evidence(args.graph_root)
    paper_by_claim = claim_papers(args.graph_root)
    rows: list[dict[str, Any]] = []
    for case in dataset:
        pattern = f"{case['id']}{args.artifact_suffix}"
        matches = sorted(path for path in args.artifacts.glob(f"{pattern}*") if path.is_dir())
        if not matches:
            continue
        case_dir = matches[-1]
        if not (case_dir / "query_report.json").exists():
            continue
        top_report = read_json(case_dir / "query_report.json")
        leaves = leaf_reports(case_dir)
        candidate_claims = candidate_claim_ids(leaves)
        delivered_claims = delivered_claim_ids(leaves)
        replayed_delivered_claims = replayed_delivered_claim_ids(leaves, paper_by_claim)
        cited_claims = cited_claim_ids(top_report)
        candidate_blocks = block_order(candidate_claims, evidence)
        delivered_blocks = block_order(delivered_claims, evidence)
        replayed_delivered_blocks = block_order(replayed_delivered_claims, evidence)
        cited_blocks = block_order(cited_claims, evidence)
        gold = {
            item["source_block_id"]
            for item in case.get("gold_evidence", [])
            if item.get("role") == "central"
        }
        expected = {item["paper_id"] for item in case.get("source_papers", [])}
        rows.append(
            {
                "case_id": case["id"],
                "split": case["split"],
                "category": case["category"],
                "question": case["question"],
                "subquery_count": len(leaves),
                "gold_source_block_ids": sorted(gold),
                "candidate_evidence_recall_at_10": recall(candidate_blocks, gold, 10),
                "delivered_evidence_recall": recall(delivered_blocks, gold),
                "replayed_delivered_evidence_recall": recall(
                    replayed_delivered_blocks, gold
                ),
                "cited_evidence_recall": recall(cited_blocks, gold),
                "candidate_expected_paper_hit": expected_paper_hit(
                    candidate_claims, expected, paper_by_claim
                ),
                "delivered_expected_paper_hit": expected_paper_hit(
                    delivered_claims, expected, paper_by_claim
                ),
                "cited_expected_paper_hit": expected_paper_hit(
                    cited_claims, expected, paper_by_claim
                ),
                "candidate_claim_ids": candidate_claims,
                "delivered_claim_ids": delivered_claims,
                "replayed_delivered_claim_ids": replayed_delivered_claims,
                "cited_claim_ids": cited_claims,
                "candidate_source_block_ids": candidate_blocks,
                "delivered_source_block_ids": delivered_blocks,
                "replayed_delivered_source_block_ids": replayed_delivered_blocks,
                "cited_source_block_ids": cited_blocks,
                "artifact_dir": str(case_dir),
            }
        )

    def mean(field: str) -> float:
        return sum(float(row[field]) for row in rows) / len(rows) if rows else 0.0

    summary = {
        "case_count": len(rows),
        "mean_candidate_evidence_recall_at_10": mean("candidate_evidence_recall_at_10"),
        "mean_delivered_evidence_recall": mean("delivered_evidence_recall"),
        "mean_replayed_delivered_evidence_recall": mean(
            "replayed_delivered_evidence_recall"
        ),
        "mean_cited_evidence_recall": mean("cited_evidence_recall"),
        "candidate_expected_paper_hits": sum(row["candidate_expected_paper_hit"] for row in rows),
        "delivered_expected_paper_hits": sum(row["delivered_expected_paper_hit"] for row in rows),
        "cited_expected_paper_hits": sum(row["cited_expected_paper_hit"] for row in rows),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"summary": summary, "cases": rows}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
