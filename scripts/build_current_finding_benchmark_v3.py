"""Build the 30-case benchmark from audited current-paper findings."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


ADDED_CASE_IDS = [
    "CKGQ0011",
    "CKGQ0013",
    "CKGQ0015",
    "CKGQ0026",
    "CKGQ0028",
    "CKGQ0029",
    "CKGQ0030",
    "CKGQ0031",
    "CKGQ0032",
    "CKGQ0033",
    "CKGQ0036",
    "CKGQ0041",
    "CKGQ0042",
    "CKGQ0043",
    "CKGQ0044",
    "CKGQ0046",
    "CKGQ0047",
    "CKGQ0050",
    "CKGQ0051",
    "CKGQ0054",
]

# The abstract duplicates the two result passages and is not the smallest
# sufficient evidence set for this case.
EVIDENCE_OVERRIDES = {
    "CKGQ0028": ["P000015:S12:P0070", "P000015:S12:P0084"],
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--draft", required=True, type=Path)
    parser.add_argument("--graph-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    base_cases = deepcopy(read_json(args.base))
    draft_by_id = {case["id"]: case for case in read_json(args.draft)}
    missing_cases = [case_id for case_id in ADDED_CASE_IDS if case_id not in draft_by_id]
    if missing_cases:
        raise ValueError(f"Draft cases not found: {missing_cases}")

    papers = {
        row["id"]: row
        for row in pq.read_table(args.graph_root / "papers.parquet", columns=["id", "title", "doi"]).to_pylist()
    }
    blocks = {
        row["id"]: row
        for row in pq.read_table(
            args.graph_root / "source_blocks.parquet",
            columns=["id", "paper_id", "page"],
        ).to_pylist()
    }

    added_cases = []
    for case_id in ADDED_CASE_IDS:
        case = deepcopy(draft_by_id[case_id])
        evidence_ids = EVIDENCE_OVERRIDES.get(
            case_id, [item["source_block_id"] for item in case["gold_evidence"]]
        )
        expected_paper_ids = {item["paper_id"] for item in case["source_papers"]}
        if len(expected_paper_ids) != 1:
            raise ValueError(f"{case_id} is not a single-paper case: {expected_paper_ids}")
        paper_id = next(iter(expected_paper_ids))
        if paper_id not in papers:
            raise ValueError(f"{case_id} paper is absent from benchmark graph: {paper_id}")
        for block_id in evidence_ids:
            if block_id not in blocks:
                raise ValueError(f"{case_id} SourceBlock is absent: {block_id}")
            if blocks[block_id]["paper_id"] != paper_id:
                raise ValueError(f"{case_id} SourceBlock belongs to another paper: {block_id}")

        paper = papers[paper_id]
        case["source_papers"] = [
            {"paper_id": paper_id, "title": paper["title"], "doi": paper.get("doi")}
        ]
        case["gold_evidence"] = [
            {
                "paper_id": paper_id,
                "source_block_id": block_id,
                "page": blocks[block_id]["page"],
                "role": "central",
            }
            for block_id in evidence_ids
        ]
        case["verification"] = {
            "status": "model_checked",
            "verifier": "Codex current-paper semantic provenance audit",
            "date": date.today().isoformat(),
            "notes": (
                "The passage was read as a finding, analysis, or mechanism presented by the indexed "
                "paper itself. Cited-background-only and method-only candidates were excluded. "
                "Human verification against the original PDF remains required."
            ),
        }
        added_cases.append(case)

    cases = base_cases + added_cases
    if len(cases) != 30 or len({case["id"] for case in cases}) != 30:
        raise ValueError("The v3 benchmark must contain 30 distinct cases")

    write_json(args.output_dir / "cases.json", cases)
    write_json(
        args.output_dir / "manifest.json",
        {
            "dataset_version": 3,
            "case_schema_version": 1,
            "status": "model_checked_requires_human_verification",
            "case_count": len(cases),
            "base_dataset": str(args.base),
            "draft_dataset": str(args.draft),
            "added_case_ids": ADDED_CASE_IDS,
            "gold_evidence_policy": (
                "Every answerable case is supported by a finding, analysis, or mechanism produced, "
                "observed, simulated, or presented by the indexed paper itself. Passages that only "
                "summarize cited literature and questions about methods alone are excluded."
            ),
        },
    )


if __name__ == "__main__":
    main()
