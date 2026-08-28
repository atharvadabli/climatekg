from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from climatekg.config import PIPELINE
from climatekg.graph import Neo4jHttp
from climatekg.models import FinalPaper
from climatekg.utils import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest and verify one FinalPaper in Neo4j.")
    parser.add_argument("--source-final", type=Path, required=True)
    parser.add_argument("--http-uri", default="http://localhost:7475")
    parser.add_argument("--password", default="climatekg-hierarchy-test")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--round-trip-final", type=Path)
    args = parser.parse_args()

    paper = FinalPaper.model_validate_json(args.source_final.read_text(encoding="utf-8"))
    graph = Neo4jHttp(http_uri=args.http_uri, password=args.password)
    graph.initialize(PIPELINE["embeddings"]["dimension"])
    graph.ingest(paper)
    counts = graph.verify_paper(paper.paper.id)
    reloaded = graph.read_corpus()
    loaded = next(item for item in reloaded if item.paper.id == paper.paper.id)
    report = {
        "paper_id": paper.paper.id,
        "graph_counts": counts,
        "round_trip_counts": {
            "source_blocks": len(loaded.source_blocks),
            "contexts": len(loaded.contexts),
            "facets": len(loaded.facets),
            "transitions": len(loaded.transitions),
            "claims": len(loaded.claims),
            "states": len(loaded.states),
        },
        "expected_counts": {
            "source_blocks": len(paper.source_blocks),
            "contexts": len(paper.contexts),
            "facets": len(paper.facets),
            "transitions": len(paper.transitions),
            "claims": len(paper.claims),
            "states": len(paper.states),
        },
    }
    if report["round_trip_counts"] != report["expected_counts"]:
        raise RuntimeError(f"Neo4j round-trip count mismatch: {report}")
    write_json(args.output, report)
    if args.round_trip_final:
        write_json(args.round_trip_final, loaded.model_dump(by_alias=True))
    print(report)


if __name__ == "__main__":
    main()
