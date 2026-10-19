"""Create a readable provenance audit for proposed benchmark cases."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--graph-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append")
    args = parser.parse_args()

    requested = set(args.case or [])
    cases = [
        case
        for case in read_json(args.dataset)
        if not requested or case["id"] in requested
    ]
    papers = {
        row["id"]: row
        for row in pq.read_table(
            args.graph_root / "papers.parquet", columns=["id", "title", "doi"]
        ).to_pylist()
    }
    blocks = {
        row["id"]: row
        for row in pq.read_table(
            args.graph_root / "source_blocks.parquet",
            columns=["id", "paper_id", "page", "section_path", "text"],
        ).to_pylist()
    }
    own_result_claims_by_block: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for claim in pq.read_table(
        args.graph_root / "claims.parquet",
        columns=["id", "paper_id", "description", "evidence_role", "evidence_block_ids"],
    ).to_pylist():
        if claim["evidence_role"] != "OWN_RESULT":
            continue
        for block_id in claim["evidence_block_ids"]:
            own_result_claims_by_block[block_id].append(claim)

    lines = [
        "# Benchmark Gold-Provenance Audit",
        "",
        "Automated checks below establish ownership and extracted `OWN_RESULT` links. ",
        "They do not replace reading each passage for cited-background leakage.",
        "",
    ]
    for case in cases:
        expected_papers = {item["paper_id"] for item in case["source_papers"]}
        lines.extend(
            [
                f"## {case['id']}",
                "",
                f"**Question:** {case['question']}",
                "",
                f"**Gold answer:** {case['reference_answer']}",
                "",
                "**Expected papers:** "
                + "; ".join(
                    f"{paper_id}: {papers.get(paper_id, {}).get('title', 'UNKNOWN')}"
                    for paper_id in sorted(expected_papers)
                ),
                "",
            ]
        )
        for evidence in case["gold_evidence"]:
            block_id = evidence["source_block_id"]
            block = blocks.get(block_id)
            if block is None:
                lines.extend([f"### {block_id}", "", "**ERROR: block missing.**", ""])
                continue
            owner_ok = block["paper_id"] in expected_papers
            linked = own_result_claims_by_block.get(block_id, [])
            linked_same_paper = [
                claim for claim in linked if claim["paper_id"] == block["paper_id"]
            ]
            lines.extend(
                [
                    f"### {block_id}",
                    "",
                    f"- Owner: `{block['paper_id']}` ({'PASS' if owner_ok else 'FAIL'})",
                    f"- Page: {block['page']}",
                    f"- Section: {' > '.join(block['section_path'])}",
                    "- Current-paper `OWN_RESULT` link: "
                    + ("PASS" if linked_same_paper else "FAIL"),
                    "",
                    block["text"].strip(),
                    "",
                    "Linked current-paper claims:",
                    "",
                ]
            )
            if linked_same_paper:
                lines.extend(
                    f"- `{claim['id']}`: {claim['description']}"
                    for claim in linked_same_paper
                )
            else:
                lines.append("- None")
            lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {args.output}")


if __name__ == "__main__":
    main()
