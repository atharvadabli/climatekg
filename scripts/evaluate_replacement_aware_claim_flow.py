from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure expected-Claim flow while allowing conservative atomic replacements.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--baseline-graph", type=Path, required=True)
    parser.add_argument("--experiment-graph", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.parquet_graph import ParquetGraph
    from climatekg.query import Corpus
    from climatekg.utils import cosine, normalize_text_key, write_json

    baseline = Corpus(ParquetGraph(args.baseline_graph).read_corpus())
    experiment = Corpus(ParquetGraph(args.experiment_graph).read_corpus())
    claims_by_paper: dict[str, list] = {}
    for claim in experiment.claims.values():
        claims_by_paper.setdefault(claim.paper_id, []).append(claim)

    def match(expected_id: str, available: set[str]) -> dict:
        expected = baseline.claims[expected_id]
        candidates = []
        expected_evidence = set(expected.evidence_block_ids)
        for candidate in claims_by_paper.get(expected.paper_id, []):
            candidate_evidence = set(candidate.evidence_block_ids)
            overlap = len(expected_evidence & candidate_evidence) / max(1, min(len(expected_evidence), len(candidate_evidence)))
            semantic = max(0.0, cosine(expected.claim_embedding or [], candidate.claim_embedding or []))
            exact_text = normalize_text_key(expected.description) == normalize_text_key(candidate.description)
            accepted = exact_text or semantic >= 0.84 or (overlap > 0 and semantic >= 0.68)
            if accepted:
                candidates.append({"claim_id": candidate.id, "semantic_similarity": semantic, "evidence_overlap": overlap, "exact_text": exact_text})
        candidates.sort(key=lambda item: (-item["exact_text"], -item["evidence_overlap"], -item["semantic_similarity"], item["claim_id"]))
        reaching = [item for item in candidates if item["claim_id"] in available]
        return {"expected_claim_id": expected_id, "represented": bool(candidates), "reached": bool(reaching), "best_graph_match": candidates[0] if candidates else None, "best_reaching_match": reaching[0] if reaching else None}

    rows = []
    for case in read_json(args.dataset):
        case_dir = args.artifacts / case["id"]
        parent = read_json(case_dir / "query_report.json")
        children = [read_json(path) for path in sorted((case_dir / "sq").glob("*/query_report.json"))] or [parent]
        candidate_ids = {row["claim_id"] for report in children for row in report.get("claim_candidates", [])}
        selected_ids = {claim_id for report in children for claim_id in (report.get("evidence_subgraph") or {}).get("claim_ids", [])}
        mappings = [match(expected_id, selected_ids) for expected_id in case["expected_claim_ids"]]
        candidate_mappings = [match(expected_id, candidate_ids) for expected_id in case["expected_claim_ids"]]
        rows.append({
            "case_id": case["id"],
            "expected_count": len(mappings),
            "represented_count": sum(item["represented"] for item in mappings),
            "candidate_reached_count": sum(item["reached"] for item in candidate_mappings),
            "selected_reached_count": sum(item["reached"] for item in mappings),
            "mappings": mappings,
        })
    total = sum(row["expected_count"] for row in rows)
    summary = {
        "query_count": len(rows),
        "expected_claim_count": total,
        "graph_representation_rate": sum(row["represented_count"] for row in rows) / total,
        "candidate_recall": sum(row["candidate_reached_count"] for row in rows) / total,
        "selected_evidence_recall": sum(row["selected_reached_count"] for row in rows) / total,
        "acceptance_rule": "exact normalized text, or embedding cosine >= 0.84, or shared evidence plus cosine >= 0.68",
        "cases": rows,
    }
    write_json(args.output, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "cases"}, indent=2))


if __name__ == "__main__":
    main()
