from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render accepted State semantic links for scientific review.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.parquet_graph import ParquetGraph

    papers = ParquetGraph(args.graph_root).read_corpus()
    states = {state.id: state for paper in papers for state in paper.states}
    decisions = json.loads(args.decisions.read_text(encoding="utf-8"))["decisions"]
    accepted = [
        item
        for item in decisions
        if item.get("accepted", item["relation"] not in {"unrelated", "uncertain"})
    ]
    lines = [
        "# State Semantic Link Audit",
        "",
        "These links organize retrieved evidence. They are never treated as causal Claim edges.",
        "",
        "| Pair | Relation | State A | State B | Rationale |",
        "|---|---|---|---|---|",
    ]
    for item in accepted:
        left, right = states[item["state_a_id"]], states[item["state_b_id"]]
        rationale = item["rationale"].replace("|", "\\|")
        lines.append(
            f"| {item['pair_id']} | {item['relation']} | {left.concept} [{left.state}] | "
            f"{right.concept} [{right.state}] | {rationale} |"
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(accepted)} accepted links to {args.output}")


if __name__ == "__main__":
    main()
