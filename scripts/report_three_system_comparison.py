#!/usr/bin/env python3
"""Collate plain RAG, entity-adapted GraphRAG, and ClimateKG answers for one query set.

Each system stores its run artifacts in a different shape. This script reduces all
three to the same record - retrieved evidence, papers touched, generation settings,
latency, thinking trace size, and answer text - so the benchmark tables in the paper
are produced from the saved runs instead of being transcribed by hand.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

CLAIM_PATTERN = re.compile(r"P\d{6}_CL\d{3}")
PLAIN_SOURCE_PATTERN = re.compile(r"^\[S(\d+)\] score=([\d.]+).*?paper=(\S+)", re.MULTILINE)


def namespace_to_paper(namespace: str, heterogeneity_paper_id: str) -> str:
    """Map a shared-corpus namespace such as R1_P000019 to its ClimateKG paper id."""
    if namespace.startswith("R2_"):
        return heterogeneity_paper_id
    return namespace.removeprefix("R1_")


def read_plain_rag(path: Path, heterogeneity_paper_id: str) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    thinking = ""
    if "THINKING" in text and "END THINKING" in text:
        thinking = text.split("THINKING", 1)[1].split("END THINKING", 1)[0].strip()
        text = text.split("END THINKING", 1)[1]
    answer, _, sources = text.partition("\nSources:\n")
    ranked = [
        {"rank": int(rank), "score": float(score), "paper": namespace_to_paper(namespace, heterogeneity_paper_id)}
        for rank, score, namespace in PLAIN_SOURCE_PATTERN.findall(sources)
    ]
    return {
        "system": "plain_rag",
        "granularity": "passage",
        "retrieved_claim_ids": [],
        "retrieved_papers": list(dict.fromkeys(row["paper"] for row in ranked)),
        "retrieved_units": ranked,
        "answer": answer.strip(),
        "thinking_characters": len(thinking),
    }


def renamespace_claim(claim_id: str, namespace: str, heterogeneity_paper_id: str) -> str:
    """Rewrite a baseline claim id into shared-corpus paper numbering.

    The heterogeneity paper was indexed on its own and kept the identifier
    P000001, which the shared corpus assigns to the wind-farm paper. Its claim
    ids therefore have to move with its paper id before they can be compared
    against gold evidence.
    """
    paper = namespace_to_paper(namespace, heterogeneity_paper_id)
    return f"{paper}{claim_id[7:]}" if len(claim_id) > 7 else claim_id


def read_graphrag(path: Path, heterogeneity_paper_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    evidence = payload["evidence"]
    claim_ids = [renamespace_claim(row["claim_id"], row["paper"], heterogeneity_paper_id) for row in evidence]
    return {
        "system": "microsoft_graphrag",
        "granularity": "claim_edge",
        "retrieved_claim_ids": claim_ids,
        "retrieved_papers": list(
            dict.fromkeys(namespace_to_paper(row["paper"], heterogeneity_paper_id) for row in evidence)
        ),
        "retrieved_units": [
            {"rank": index + 1, "score": float(row["score"]), "claim_id": claim_id}
            for index, (row, claim_id) in enumerate(zip(evidence, claim_ids))
        ],
        "selected_communities": [row["id"] for row in payload["selected_communities"]],
        "answer": payload["answer"].strip(),
        "thinking_characters": len(payload.get("thinking") or ""),
        "thinking_budget": payload.get("thinking_budget", "no"),
        "latency_seconds": payload["timings"]["total_seconds"],
    }


def read_climatekg(query_dir: Path) -> dict[str, Any]:
    report = json.loads((query_dir / "query_report.json").read_text(encoding="utf-8"))
    claim_ids = list(dict.fromkeys(claim for path in report["paths"] for claim in path["claim_ids"]))
    synthesis_dir = query_dir / "synthesis"
    thinking_characters = 0
    latency_seconds = None
    for envelope in sorted(synthesis_dir.glob("*.envelope.json")):
        payload = json.loads(envelope.read_text(encoding="utf-8"))
        if not payload.get("validated"):
            continue
        latency_seconds = payload.get("elapsed_seconds")
        response = synthesis_dir / f"{payload['call_id']}.attempt{payload['retry_number']}.json"
        if response.exists():
            message = json.loads(response.read_text(encoding="utf-8")).get("message", {})
            thinking_characters = len(message.get("thinking") or "")
    return {
        "system": "climatekg",
        "granularity": "claim_path",
        "retrieved_claim_ids": claim_ids,
        "retrieved_papers": list(dict.fromkeys(claim[:7] for claim in claim_ids)),
        "retrieved_units": [
            {
                "rank": index + 1,
                "claim_ids": path["claim_ids"],
                "evidence_lane": path.get("evidence_lane"),
            }
            for index, path in enumerate(report["paths"])
        ],
        "context_candidates": [row["context_id"] for row in report["context_candidates"][:5]],
        "answer": report["answer"].strip(),
        "thinking_characters": thinking_characters,
        "latency_seconds": latency_seconds,
        "warnings": report["warnings"],
    }


def score(record: dict[str, Any], gold_claims: list[str], gold_papers: list[str]) -> dict[str, Any]:
    retrieved_claims = set(record["retrieved_claim_ids"])
    retrieved_papers = set(record["retrieved_papers"])
    gold_claim_set, gold_paper_set = set(gold_claims), set(gold_papers)
    answer_claims = set(CLAIM_PATTERN.findall(record["answer"]))
    # Plain RAG retrieves passages, so it has no claim-level retrieval to score.
    claim_level = record["granularity"] != "passage"
    return {
        "gold_claim_recall": round(len(retrieved_claims & gold_claim_set) / len(gold_claim_set), 3)
        if gold_claim_set and claim_level
        else None,
        "gold_paper_recall": round(len(retrieved_papers & gold_paper_set) / len(gold_paper_set), 3)
        if gold_paper_set
        else None,
        "retrieved_paper_precision": round(len(retrieved_papers & gold_paper_set) / len(retrieved_papers), 3)
        if retrieved_papers and gold_paper_set
        else None,
        "cited_claims_in_answer": sorted(answer_claims),
        "cited_claims_outside_retrieval": sorted(answer_claims - retrieved_claims),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", type=Path, required=True)
    parser.add_argument("--plain-rag-dir", type=Path, required=True)
    parser.add_argument("--graphrag-dir", type=Path, required=True)
    parser.add_argument("--climatekg-dir", type=Path, required=True)
    parser.add_argument("--heterogeneity-paper-id", default="P000018")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    queries = json.loads(args.queries.read_text(encoding="utf-8"))["queries"]
    results: list[dict[str, Any]] = []
    for query in queries:
        query_id = query["id"]
        gold_claims = query.get("expected_evidence", [])
        gold_papers = query.get("expected_papers") or sorted({claim[:7] for claim in gold_claims})
        systems: dict[str, Any] = {}
        plain_path = args.plain_rag_dir / f"{query_id}.txt"
        if plain_path.exists():
            systems["plain_rag"] = read_plain_rag(plain_path, args.heterogeneity_paper_id)
        graph_path = args.graphrag_dir / f"{query_id}.json"
        if graph_path.exists():
            systems["microsoft_graphrag"] = read_graphrag(graph_path, args.heterogeneity_paper_id)
        climate_dir = args.climatekg_dir / query_id
        if (climate_dir / "query_report.json").exists():
            systems["climatekg"] = read_climatekg(climate_dir)
        for record in systems.values():
            record["scores"] = score(record, gold_claims, gold_papers)
        results.append(
            {
                "query_id": query_id,
                "question": query["question"],
                "corpus_relation": query.get("corpus_relation"),
                "gold_claim_ids": gold_claims,
                "gold_paper_ids": gold_papers,
                "systems": systems,
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    separator = "=" * 78
    for row in results:
        print(f"\n{separator}\n{row['query_id']}  ({row['corpus_relation']})")
        print(f"gold claims: {row['gold_claim_ids'] or '-'}")
        print(
            f"{'system':20} {'papers':>7} {'claims':>7} {'gold_cl':>8} "
            f"{'gold_pap':>9} {'prec':>6} {'think':>7} {'sec':>8}"
        )
        for name, record in row["systems"].items():
            scores = record["scores"]
            print(
                f"{name:20} {len(record['retrieved_papers']):>7} {len(record['retrieved_claim_ids']):>7} "
                f"{str(scores['gold_claim_recall']):>8} {str(scores['gold_paper_recall']):>9} "
                f"{str(scores['retrieved_paper_precision']):>6} {record['thinking_characters']:>7} "
                f"{str(record.get('latency_seconds')):>8}"
            )
    print(f"\nwritten: {args.output}")


if __name__ == "__main__":
    main()
