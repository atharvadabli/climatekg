from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import DATA_ROOT, OUTPUT_ROOT, PIPELINE
from .graph import Neo4jHttp
from .indexer import index_pdf, load_corpus
from .parquet_graph import ParquetGraph
from .query import run_query
from .query_validation import run_validation_suite
from .state_maintenance import recanonicalize_corpus


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="climatekg")
    commands = parser.add_subparsers(dest="command", required=True)
    index = commands.add_parser("index")
    index.add_argument("pdfs", nargs="+")
    index.add_argument("--data-root", type=Path, default=DATA_ROOT)
    index.add_argument("--start-id", type=int, default=1)
    index.add_argument("--rebuild-derived", action="store_true", help="Rebuild mapping and all downstream artifacts while retaining parse and SourceBlock caches.")
    graph = commands.add_parser("ingest")
    graph.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parquet = commands.add_parser("build-parquet")
    parquet.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parquet.add_argument("--output", type=Path, default=OUTPUT_ROOT / "parquet_graph")
    inspect_parquet = commands.add_parser("inspect-parquet")
    inspect_parquet.add_argument("--graph-root", type=Path, default=OUTPUT_ROOT / "parquet_graph")
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--query-id", default="Q000001")
    query.add_argument("--data-root", type=Path, default=DATA_ROOT)
    query.add_argument("--output-root", type=Path, default=OUTPUT_ROOT / "queries")
    query.add_argument("--storage", choices=("parquet", "neo4j"), default="parquet")
    query.add_argument("--graph-root", type=Path, default=OUTPUT_ROOT / "parquet_graph")
    validate = commands.add_parser("validate-queries")
    validate.add_argument("--suite", type=Path)
    validate.add_argument("--output-root", type=Path)
    validate.add_argument("--query-id", action="append", dest="query_ids")
    validate.add_argument("--storage", choices=("parquet", "neo4j"), default="parquet")
    validate.add_argument("--graph-root", type=Path, default=OUTPUT_ROOT / "parquet_graph")
    recanonicalize = commands.add_parser("recanonicalize-states")
    recanonicalize.add_argument("--data-root", type=Path, default=DATA_ROOT)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "index":
        for offset, raw_path in enumerate(args.pdfs):
            paper_id = f"P{args.start_id + offset:06d}"
            try:
                result = index_pdf(Path(raw_path), args.data_root, paper_id, rebuild_derived=args.rebuild_derived)
                print(json.dumps({"paper_id": result.paper.id, "status": "complete", "counts": {name: len(getattr(result, name)) for name in ("source_blocks", "contexts", "facets", "transitions", "claims", "states")}}), flush=True)
            except Exception as exc:
                print(json.dumps({"paper_id": paper_id, "status": "NEEDS_REVIEW", "error": str(exc)}), flush=True)
    elif args.command == "ingest":
        graph = Neo4jHttp()
        graph.initialize(PIPELINE["embeddings"]["dimension"])
        for paper in load_corpus(args.data_root):
            graph.ingest(paper)
            print(json.dumps({"paper_id": paper.paper.id, "graph_counts": graph.verify_paper(paper.paper.id)}))
    elif args.command == "build-parquet":
        counts = ParquetGraph(args.output).write_corpus(load_corpus(args.data_root))
        print(json.dumps({"graph_root": str(args.output), "table_counts": counts}, indent=2))
    elif args.command == "inspect-parquet":
        graph = ParquetGraph(args.graph_root)
        papers = graph.read_corpus()
        indexes = graph.read_indexes()
        ann_counts = {name: data["count"] for name, data in indexes.manifest["collections"].items()}
        print(json.dumps({"graph_root": str(args.graph_root), "table_counts": graph.table_counts(), "ann_counts": ann_counts, "paper_ids": [paper.paper.id for paper in papers]}, indent=2))
    elif args.command == "query":
        if args.storage == "parquet":
            graph = ParquetGraph(args.graph_root)
            papers, indexes = graph.read_corpus(), graph.read_indexes()
        else:
            papers, indexes = Neo4jHttp().read_corpus(), None
        report = run_query(args.question, args.query_id, papers, args.output_root, indexes=indexes)
        print(report["answer"])
    elif args.command == "validate-queries":
        summary = run_validation_suite(args.suite, args.output_root, args.query_ids, args.storage, args.graph_root)
        print(json.dumps({key: summary[key] for key in ("run_id", "query_count", "passed", "failed", "errors", "blocked", "blocker")}, indent=2))
        if summary["blocked"] or summary["errors"] or summary["failed"]:
            raise SystemExit(1)
    else:
        for result in recanonicalize_corpus(args.data_root):
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
