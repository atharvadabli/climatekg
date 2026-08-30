from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.run_three_system_benchmark import DEFAULT_QUERIES, DEFAULT_SOURCE_ROOT, load_shared_corpus


DEFAULT_RESULTS = REPOSITORY_ROOT / "climatekg" / "runtime" / "outputs" / "three_system_benchmark_20260830"
WORD_RE = re.compile(r"[a-z0-9]+")
PLAIN_CITATION_RE = re.compile(r"\[S(\d+)\]")
CLAIM_ID_RE = re.compile(r"R\d+_P\d+:P\d+_CL\d+")
PLAIN_CLAIM_SIMILARITY_THRESHOLD = 0.55
CONDITION_STOPWORDS = {"a", "an", "and", "in", "of", "or", "the", "to", "with"}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def words(value: str) -> list[str]:
    return WORD_RE.findall(value.lower())


def normalized(value: str) -> str:
    return " ".join(words(value))


def claim_evidence_lookup(source_root: Path) -> tuple[dict[str, list[str]], dict[str, str], dict[str, list[float]]]:
    evidence: dict[str, list[str]] = {}
    paper_by_claim: dict[str, str] = {}
    vectors: dict[str, list[float]] = {}
    for paper in load_shared_corpus(source_root):
        blocks = {block.id: block.text for block in paper.source_blocks}
        for claim in paper.claims:
            evidence[claim.id] = [blocks[block_id] for block_id in claim.evidence_block_ids if block_id in blocks]
            paper_by_claim[claim.id] = paper.paper.id
            vectors[claim.id] = claim.claim_embedding
    return evidence, paper_by_claim, vectors


def load_plain_vectors(index_dir: Path, passage_ids: set[str]) -> dict[str, tuple[list[float], float]]:
    result = {}
    with (index_dir / "chunks.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            if item["id"] in passage_ids:
                result[item["id"]] = (item["embedding"], item["norm"])
    return result


def cosine(left: list[float], right: list[float], right_norm: float) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def passage_supports_block(passage: str, block: str) -> bool:
    passage_norm, block_norm = normalized(passage), normalized(block)
    if not block_norm:
        return False
    if block_norm in passage_norm or passage_norm in block_norm:
        return True
    block_terms = set(words(block))
    if not block_terms:
        return False
    return len(block_terms & set(words(passage))) / len(block_terms) >= 0.75


def map_plain_passages(
    retrieval: list[dict[str, Any]],
    expected: set[str],
    evidence: dict[str, list[str]],
    paper_by_claim: dict[str, str],
    claim_vectors: dict[str, list[float]],
    passage_vectors: dict[str, tuple[list[float], float]],
) -> dict[int, set[str]]:
    mapped: dict[int, set[str]] = defaultdict(set)
    for index, passage in enumerate(retrieval, 1):
        for claim_id in expected:
            if passage.get("paper") != paper_by_claim.get(claim_id):
                continue
            vector, norm = passage_vectors.get(passage["id"], ([], 0.0))
            semantic_match = bool(vector) and cosine(claim_vectors[claim_id], vector, norm) >= PLAIN_CLAIM_SIMILARITY_THRESHOLD
            if semantic_match or any(passage_supports_block(passage.get("text", ""), block) for block in evidence.get(claim_id, [])):
                mapped[index].add(claim_id)
    return mapped


def graph_claim_ids(payload: dict[str, Any]) -> set[str]:
    identifiers = set()
    for item in payload.get("evidence", []):
        paper, claim = item.get("paper"), item.get("claim_id")
        if paper and claim:
            identifiers.add(f"{paper}:{claim}")
    return identifiers


def climate_selected_claim_ids(payload: dict[str, Any]) -> set[str]:
    identifiers = set()
    for field in ("direct_evidence_paths", "graph_paths"):
        for path in payload.get(field, []):
            identifiers.update(path.get("claim_ids", []))
    return identifiers


def condition_coverage(answer: str, conditions: list[str]) -> tuple[int, int]:
    answer_terms = set(words(answer))
    retained = 0
    for condition in conditions:
        terms = {term for term in words(condition) if term not in CONDITION_STOPWORDS}
        retained += bool(terms) and len(terms & answer_terms) / len(terms) >= 0.75
    return retained, len(conditions)


def sentence_citation_coverage(answer: str, citation_pattern: re.Pattern[str]) -> float | None:
    def mask_bracket(match: re.Match[str]) -> str:
        return " __CITED__ " if citation_pattern.search(match.group(0)) else match.group(0).replace(".", "")

    prepared = re.sub(r"\[[^\]]+\]", mask_bracket, answer)
    prepared = re.sub(r"([.!?])\s+(__CITED__)", r" \2\1", prepared)
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", prepared) if len(words(item)) >= 8]
    return ratio(sum("__CITED__" in item or bool(citation_pattern.search(item)) for item in sentences), len(sentences))


def ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def artifact_wall_seconds(payload: dict[str, Any]) -> float | None:
    artifact_dir = Path(payload.get("artifact_dir", ""))
    if not artifact_dir.exists():
        return None
    files = list(artifact_dir.rglob("*"))
    files = [path for path in files if path.is_file()]
    if not files:
        return None
    return round(max(path.stat().st_mtime for path in files) - min(path.stat().st_mtime for path in files), 3)


def evaluate_plain(
    payload: dict[str, Any],
    expected: set[str],
    conditions: list[str],
    evidence: dict[str, list[str]],
    paper_by_claim: dict[str, str],
    claim_vectors: dict[str, list[float]],
    passage_vectors: dict[str, tuple[list[float], float]],
) -> dict[str, Any]:
    retrieval = payload.get("retrieval", [])
    mapped = map_plain_passages(retrieval, expected, evidence, paper_by_claim, claim_vectors, passage_vectors)
    retrieved = set().union(*mapped.values()) if mapped else set()
    cited_indices = {int(value) for value in PLAIN_CITATION_RE.findall(payload.get("answer", ""))}
    answer_claims = set().union(*(mapped.get(index, set()) for index in cited_indices)) if cited_indices else set()
    retained, condition_total = condition_coverage(payload.get("answer", ""), conditions)
    return {
        "retrieved_expected_claim_ids": sorted(retrieved),
        "retrieval_claim_recall": ratio(len(retrieved), len(expected)),
        "answer_supported_expected_claim_ids": sorted(answer_claims),
        "answer_claim_recall": ratio(len(answer_claims), len(expected)),
        "citation_count": len(cited_indices),
        "citation_identifier_validity": ratio(sum(1 <= index <= len(retrieval) for index in cited_indices), len(cited_indices)),
        "sentence_citation_coverage": sentence_citation_coverage(payload.get("answer", ""), PLAIN_CITATION_RE),
        "condition_retention": ratio(retained, condition_total),
        "retrieval_seconds": payload.get("timings", {}).get("retrieval_seconds"),
        "total_seconds": payload.get("timings", {}).get("total_seconds"),
        "thinking_characters": len(payload.get("thinking", "")),
    }


def evaluate_graph(payload: dict[str, Any], expected: set[str], conditions: list[str]) -> dict[str, Any]:
    retrieved = graph_claim_ids(payload)
    cited = set(CLAIM_ID_RE.findall(payload.get("answer", "")))
    retained, condition_total = condition_coverage(payload.get("answer", ""), conditions)
    return {
        "retrieved_expected_claim_ids": sorted(expected & retrieved),
        "retrieval_claim_recall": ratio(len(expected & retrieved), len(expected)),
        "answer_supported_expected_claim_ids": sorted(expected & cited),
        "answer_claim_recall": ratio(len(expected & cited), len(expected)),
        "citation_count": len(cited),
        "citation_identifier_validity": ratio(len(cited & retrieved), len(cited)),
        "sentence_citation_coverage": sentence_citation_coverage(payload.get("answer", ""), CLAIM_ID_RE),
        "condition_retention": ratio(retained, condition_total),
        "total_seconds": payload.get("timings", {}).get("total_seconds"),
        "thinking_characters": len(payload.get("thinking", "")),
    }


def evaluate_climate(payload: dict[str, Any], expected: set[str], conditions: list[str]) -> dict[str, Any]:
    candidates = {item["claim_id"] for item in payload.get("claim_candidates", [])}
    selected = climate_selected_claim_ids(payload)
    cited = set(CLAIM_ID_RE.findall(payload.get("answer", "")))
    retained, condition_total = condition_coverage(payload.get("answer", ""), conditions)
    return {
        "candidate_expected_claim_ids": sorted(expected & candidates),
        "candidate_claim_recall": ratio(len(expected & candidates), len(expected)),
        "retrieved_expected_claim_ids": sorted(expected & selected),
        "retrieval_claim_recall": ratio(len(expected & selected), len(expected)),
        "answer_supported_expected_claim_ids": sorted(expected & cited),
        "answer_claim_recall": ratio(len(expected & cited), len(expected)),
        "citation_count": len(cited),
        "citation_identifier_validity": ratio(len(cited & selected), len(cited)),
        "sentence_citation_coverage": sentence_citation_coverage(payload.get("answer", ""), CLAIM_ID_RE),
        "condition_retention": ratio(retained, condition_total),
        "total_seconds": artifact_wall_seconds(payload),
        "thinking_characters": len(payload.get("thinking", "")),
    }


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    systems = ("plain_rag", "graphrag", "climatekg")
    result: dict[str, Any] = {}
    for system in systems:
        available = [row["systems"][system] for row in rows if system in row["systems"]]
        metrics = {}
        for key in ("retrieval_claim_recall", "answer_claim_recall", "citation_identifier_validity", "sentence_citation_coverage", "condition_retention", "total_seconds"):
            values = [item[key] for item in available if item.get(key) is not None]
            metrics[key] = round(sum(values) / len(values), 4) if values else None
        metrics["queries_completed"] = len(available)
        result[system] = metrics
    return result


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Three-System Query Evaluation",
        "",
        "Status: author-prepared pilot benchmark; independent expert verification is pending.",
        "",
        "Exact Claim-ID recall is used for graph systems. PlainRAG passages are mapped to expected Claims from the same paper using the shared embedding model at cosine similarity >=0.55, or direct supporting-SourceBlock term coverage >=0.75. Citation validity checks identifier resolution, not scientific entailment.",
        "",
        "| System | Queries | Retrieval recall | Answer recall | Citation validity | Sentence citation coverage | Condition retention | Mean total seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for system, values in report["aggregate"].items():
        lines.append(
            f"| {system} | {values['queries_completed']} | {values['retrieval_claim_recall']} | "
            f"{values['answer_claim_recall']} | {values['citation_identifier_validity']} | "
            f"{values['sentence_citation_coverage']} | {values['condition_retention']} | {values['total_seconds']} |"
        )
    lines.extend(["", "## Per Query", ""])
    for row in report["queries"]:
        lines.append(f"### {row['query_id']}")
        lines.append("")
        for system, values in row["systems"].items():
            lines.append(
                f"- `{system}`: retrieval recall {values.get('retrieval_claim_recall')}; "
                f"answer recall {values.get('answer_claim_recall')}; citation validity "
                f"{values.get('citation_identifier_validity')}; condition retention {values.get('condition_retention')}."
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved three-system benchmark outputs.")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--queries", type=Path, default=DEFAULT_QUERIES)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()

    evidence, paper_by_claim, claim_vectors = claim_evidence_lookup(args.source_root)
    query_config = read_json(args.queries)
    rows = []
    for query in query_config["queries"]:
        expected = set(query["expected_claim_ids"])
        row = {"query_id": query["id"], "expected_claim_ids": sorted(expected), "systems": {}}
        paths = {system: args.results / system / f"{query['id']}.json" for system in ("plain_rag", "graphrag", "climatekg")}
        if paths["plain_rag"].exists():
            plain_payload = read_json(paths["plain_rag"])
            passage_ids = {item["id"] for item in plain_payload.get("retrieval", [])}
            passage_vectors = load_plain_vectors(args.source_root / "plain_rag" / "index", passage_ids)
            row["systems"]["plain_rag"] = evaluate_plain(
                plain_payload, expected, query["must_preserve"], evidence, paper_by_claim, claim_vectors, passage_vectors
            )
        if paths["graphrag"].exists():
            row["systems"]["graphrag"] = evaluate_graph(read_json(paths["graphrag"]), expected, query["must_preserve"])
        if paths["climatekg"].exists():
            row["systems"]["climatekg"] = evaluate_climate(read_json(paths["climatekg"]), expected, query["must_preserve"])
        rows.append(row)

    report = {
        "benchmark_version": query_config["version"],
        "annotation_status": query_config["annotation_status"],
        "metric_notes": {
            "graph_systems": "Exact expected Claim IDs among retrieved and cited evidence.",
            "plain_rag": "Same-paper passage match at cosine >=0.55 with the shared embedding model, or supporting SourceBlock term coverage >=0.75.",
            "citation_identifier_validity": "Fraction of cited identifiers resolving to supplied evidence; not entailment.",
            "sentence_citation_coverage": "Fraction of answer sentences with at least eight tokens containing a supplied citation identifier.",
            "condition_retention": "Fraction of required conditions with >=0.75 non-stopword token coverage in the answer.",
        },
        "queries": rows,
        "aggregate": aggregate(rows),
    }
    args.results.mkdir(parents=True, exist_ok=True)
    (args.results / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    write_markdown(args.results / "EVALUATION_REPORT.md", report)
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()
