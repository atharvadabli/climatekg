from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the frozen ten-paper graph for the atomic evidence-subgraph experiment.")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-corpus", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--graph-root", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.code_root.resolve()))
    sys.path.insert(1, str(args.project_root.resolve()))

    from climatekg.models import FinalPaper
    from climatekg.parquet_graph import ParquetGraph
    from climatekg.utils import write_json

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    papers = []
    for item in manifest["papers"]:
        path = args.source_corpus / item["paper_id"] / "final" / "final_paper.json"
        papers.append(FinalPaper.model_validate_json(path.read_text(encoding="utf-8")))
    counts = ParquetGraph(args.graph_root).write_corpus(papers)
    write_json(
        args.graph_root / "experiment_manifest.json",
        {
            "source_corpus": str(args.source_corpus.resolve()),
            "paper_ids": [paper.paper.id for paper in papers],
            "table_counts": counts,
        },
    )
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()

