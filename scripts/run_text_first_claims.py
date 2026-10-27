"""Controlled Claim-pass replay: fixed settings, fresh Claims, separate graph."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from climatekg.canonicalize import canonicalize_claim_states
from climatekg.embeddings import embed_claims_and_states
from climatekg.models import FinalPaper
from climatekg.ollama import OllamaClient
from climatekg.parquet_graph import ParquetGraph
from climatekg.utils import write_json
from climatekg.window_claims import extract_window_claims


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-graph", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--papers", nargs="+", required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.source_graph.resolve():
        raise ValueError("Use a separate output directory")
    papers = {p.paper.id: p for p in ParquetGraph(args.source_graph).read_corpus()}
    missing = set(args.papers) - papers.keys()
    if missing:
        raise ValueError(f"Missing papers: {sorted(missing)}")
    client = OllamaClient()
    results, summaries = [], []
    for paper_id in args.papers:
        paper = papers[paper_id]
        folder = args.output / "data" / paper_id
        started = time.perf_counter()
        claims, hints = extract_window_claims(paper.paper, paper.contexts, paper.transitions,
                                             paper.facets, paper.source_blocks, folder, client)
        extraction_seconds = time.perf_counter() - started
        states = canonicalize_claim_states(claims)
        embed_started = time.perf_counter()
        embed_claims_and_states(client, claims, states)
        links = [{"object_id": item.id, "source_block_id": bid}
                 for items in (paper.contexts, paper.facets, paper.transitions, claims)
                 for item in items for bid in item.evidence_block_ids]
        result = paper.model_copy(update={"claims": claims, "states": states, "evidence_links": links,
            "unresolved_conflicts": [*paper.unresolved_conflicts, *[
                {"type": "unmapped_context_hint", "value": hint} for hint in hints]],
            "metadata": {**paper.metadata, "claim_pass": "text_windows_v2",
                "experiment_source_graph": str(args.source_graph.resolve()),
                "claim_consolidation": "exact_only", "replayed_fixed_registry": True}})
        result = FinalPaper.model_validate(result.model_dump(by_alias=True))
        write_json(folder / "final/final_paper.json", result.model_dump(by_alias=True))
        results.append(result)
        summary = {"paper_id": paper_id, "old_claims": len(paper.claims), "new_claims": len(claims),
                   "extraction_seconds": extraction_seconds,
                   "canonicalization_embedding_seconds": time.perf_counter() - embed_started,
                   "unmapped_context_hints": hints, "contexts_unchanged": result.contexts == paper.contexts,
                   "facets_unchanged": result.facets == paper.facets,
                   "transitions_unchanged": result.transitions == paper.transitions}
        summaries.append(summary)
        write_json(args.output / "benchmark.json", summaries)
        print(json.dumps(summary), flush=True)
    counts = ParquetGraph(args.output / "graph").write_corpus(results)
    write_json(args.output / "graph_counts.json", counts)


if __name__ == "__main__":
    main()
