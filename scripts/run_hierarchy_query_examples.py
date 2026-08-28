from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climatekg.models import FinalPaper
from climatekg.query import run_query
from climatekg.utils import write_json


QUERIES = (
    (
        "QHET_GENERIC",
        "How does land-surface heterogeneity affect boundary-layer convection and cloud development?",
    ),
    (
        "QHET_14KM_U0",
        "Under a heterogeneous chessboard surface with 14.4 km patches and zero background wind, how does land-surface heterogeneity affect the transition from shallow to deep convection?",
    ),
    (
        "QHET_WIND_0_TO_1",
        "For a heterogeneous surface with 14.4 km patches, how does increasing background wind from 0 to 1 m/s change the secondary circulation and moisture distribution?",
    ),
    (
        "QHET_PATCH_2_TO_5",
        "Under zero background wind, how does increasing heterogeneous patch size from 2.4 km to 4.8 km influence deep convection?",
    ),
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run traceable hierarchy query examples.")
    parser.add_argument("--source-final", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    paper = FinalPaper.model_validate_json(args.source_final.read_text(encoding="utf-8"))
    args.output_root.mkdir(parents=True, exist_ok=True)
    summary = []
    for query_id, question in QUERIES:
        trace: list[dict] = []

        def record(stage: str, details: dict) -> None:
            item = {"stage": stage, "details": details}
            trace.append(item)
            write_json(args.output_root / query_id / "stage_trace.json", trace)
            print(json.dumps({"query_id": query_id, **item}, ensure_ascii=False), flush=True)

        report = run_query(
            question,
            query_id,
            [paper],
            args.output_root,
            stage_callback=record,
        )
        summary.append(
            {
                "query_id": query_id,
                "question": question,
                "warnings": report["warnings"],
                "context_candidates": len(report["context_candidates"]),
                "claim_candidates": len(report["claim_candidates"]),
                "paths": len(report["paths"]),
                "answer": report["answer"],
            }
        )
    write_json(args.output_root / "summary.json", summary)


if __name__ == "__main__":
    main()
