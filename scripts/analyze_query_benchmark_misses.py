"""Report where expected papers disappear from benchmark retrieval traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SYSTEMS = ("plain_rag", "graphrag", "climatekg_evidence_union")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def paper_from_id(value: str) -> str:
    return value.split("_", 1)[0].split(":", 1)[0]


def contains_paper(values: list[str], paper_id: str) -> bool:
    return any(paper_from_id(value) == paper_id for value in values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--variants-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    cases = {case["id"]: case for case in read_json(args.dataset)}
    lines = ["# Retrieval Miss Trace", ""]
    for system in SYSTEMS:
        lines.extend([f"## {system}", ""])
        misses = []
        for case_id, case in cases.items():
            record = read_json(args.variants_root / system / "results" / f"{case_id}.json")
            if record.get("metrics", {}).get("expected_paper_hit") is True:
                continue
            expected = [item["paper_id"] for item in case["source_papers"]]
            misses.append((case_id, case, record, expected))
        if not misses:
            lines.extend(["No expected-paper misses.", ""])
            continue
        for case_id, case, record, expected in misses:
            lines.extend(
                [
                    f"### {case_id}",
                    "",
                    f"- Question: {case['question']}",
                    f"- Expected paper(s): {', '.join(expected)}",
                    "- Final retrieved paper(s): "
                    + ", ".join(record["metrics"].get("retrieved_paper_ids", [])),
                ]
            )
            if system == "climatekg_evidence_union":
                report_path = Path(record["result"]["artifact_dir"]) / "query_report.json"
                report = read_json(report_path)
                context_ids = [item.get("context_id", "") for item in report["context_candidates"]]
                claim_ids = [item["claim_id"] for item in report["claim_candidates"]]
                direct_ids = [
                    claim_id
                    for path in report["direct_evidence_paths"]
                    for claim_id in path["claim_ids"]
                ]
                graph_ids = [
                    claim_id for path in report["graph_paths"] for claim_id in path["claim_ids"]
                ]
                synthesis_ids = [
                    claim_id
                    for path in report["synthesis_package"]["paths"]
                    for claim_id in path["claim_ids"]
                ]
                block_papers = sorted(
                    {
                        block["paper_id"]
                        for blocks in report["source_blocks"].values()
                        for block in blocks
                    }
                )
                for paper_id in expected:
                    lines.extend(
                        [
                            f"- `{paper_id}` in retained Contexts: {contains_paper(context_ids, paper_id)}",
                            f"- `{paper_id}` in ranked Claims: {contains_paper(claim_ids, paper_id)}",
                            f"- `{paper_id}` in direct evidence paths: {contains_paper(direct_ids, paper_id)}",
                            f"- `{paper_id}` in graph paths: {contains_paper(graph_ids, paper_id)}",
                            f"- `{paper_id}` in synthesis paths: {contains_paper(synthesis_ids, paper_id)}",
                            f"- `{paper_id}` in assembled SourceBlocks: {paper_id in block_papers}",
                        ]
                    )
                lines.append(f"- Parser mode: `{report['query_spec']['mode']}`")
                lines.append(
                    "- Parser source/target: `"
                    + json.dumps(
                        {
                            "source": report["query_spec"].get("source"),
                            "target": report["query_spec"].get("target"),
                            "intervention_description": report["query_spec"].get(
                                "intervention_description"
                            ),
                        },
                        ensure_ascii=False,
                    )
                    + "`"
                )
            lines.append("")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
