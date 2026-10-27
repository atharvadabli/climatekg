from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Replace selected papers in a Parquet graph for a labelled experiment.")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--replacement-paper", type=Path, action="append", required=True)
    parser.add_argument("--output-graph", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.project_root.resolve()))

    from climatekg.models import FinalPaper
    from climatekg.parquet_graph import ParquetGraph
    from climatekg.utils import write_json

    source = ParquetGraph(args.source_graph)
    papers = {paper.paper.id: paper for paper in source.read_corpus()}
    replacements = []
    for path in args.replacement_paper:
        paper = FinalPaper.model_validate_json(path.read_text(encoding="utf-8"))
        papers[paper.paper.id] = paper
        replacements.append({"paper_id": paper.paper.id, "source": str(path.resolve())})

    destination = ParquetGraph(args.output_graph)
    counts = destination.write_corpus([papers[paper_id] for paper_id in sorted(papers)])
    valid_states = {state.id for paper in destination.read_corpus() for state in paper.states}
    links = [
        link
        for link in source.read_state_semantic_links()
        if link.source_state_id in valid_states and link.target_state_id in valid_states
    ]
    destination.write_state_semantic_links(links)
    write_json(
        args.output_graph / "experiment_manifest.json",
        {
            "kind": "hybrid_verified-paper-replacement",
            "source_graph": str(args.source_graph.resolve()),
            "replacements": replacements,
            "table_counts": counts,
            "retained_state_semantic_links": len(links),
        },
    )
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
