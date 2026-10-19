"""Run a blinded reference-answer review of the three benchmark systems."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


SYSTEMS = ("plain_rag", "graphrag", "climatekg_evidence_union")


class CandidateEvaluation(BaseModel):
    candidate: Literal["A", "B", "C"]
    scientific_correctness: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    directness: int = Field(ge=0, le=2)
    covered_qualifiers: list[str]
    missed_qualifiers: list[str]
    conflicts_with_reference: bool
    matches_known_wrong_conclusion: bool
    explanation: str


class JudgeResponse(BaseModel):
    evaluations: list[CandidateEvaluation] = Field(min_length=3, max_length=3)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def blinded_order(case_id: str) -> list[str]:
    seed = int(hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:16], 16)
    systems = list(SYSTEMS)
    random.Random(seed).shuffle(systems)
    return systems


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", required=True, type=Path)
    parser.add_argument("--code-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--variants-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    sys.path.insert(0, str(args.code_root.resolve()))
    sys.path.insert(1, str(args.project_root.resolve()))
    from climatekg.constants import GENERATION_MODEL
    from climatekg.ollama import OllamaClient

    prompt_template = (
        args.project_root / "climatekg/runtime/worktrees/query-architecture-benchmark/prompts/benchmark_answer_judge.txt"
    ).read_text(encoding="utf-8")
    client = OllamaClient()
    cases = read_json(args.dataset)
    records = []
    for index, case in enumerate(cases, start=1):
        target = args.output / "results" / f"{case['id']}.json"
        if target.exists() and not args.force:
            record = read_json(target)
            records.append(record)
            print(f"[{index}/{len(cases)}] {case['id']}: reused", flush=True)
            continue

        order = blinded_order(case["id"])
        label_to_system = dict(zip(("A", "B", "C"), order, strict=True))
        candidates = {}
        for label, system in label_to_system.items():
            result = read_json(args.variants_root / system / "results" / f"{case['id']}.json")
            candidates[label] = result["generated_answer"]
        judge_input = {
            "question": case["question"],
            "reference_answer": case["reference_answer"],
            "required_qualifiers": case["required_qualifiers"],
            "known_wrong_conclusions": case["unsupported_conclusions"],
            "candidates": candidates,
        }
        prompt = prompt_template.replace(
            "{{input_json}}", json.dumps(judge_input, ensure_ascii=False, indent=2)
        )
        print(f"[{index}/{len(cases)}] {case['id']}: judging", flush=True)
        response = client.structured(
            stage="benchmark_answer_judge",
            system="You are an impartial evaluator of scientific question answering.",
            user=prompt,
            schema=JudgeResponse,
            model=GENERATION_MODEL,
            temperature=0.0,
            thinking="low",
            artifact_dir=args.output / "artifacts" / case["id"],
            paper_id=case["id"],
            input_block_ids=[item["source_block_id"] for item in case["gold_evidence"]],
        )
        evaluations = {}
        for item in response.evaluations:
            system = label_to_system[item.candidate]
            evaluations[system] = item.model_dump()
        if set(evaluations) != set(SYSTEMS):
            raise ValueError(f"Judge did not evaluate all candidates for {case['id']}")
        record = {
            "case_id": case["id"],
            "category": case["category"],
            "blinded_mapping": label_to_system,
            "evaluations": evaluations,
        }
        write_json(target, record)
        records.append(record)

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "queries": len(items),
            "mean_scientific_correctness_0_to_4": round(
                statistics.fmean(item["scientific_correctness"] for item in items), 3
            ),
            "mean_completeness_0_to_4": round(
                statistics.fmean(item["completeness"] for item in items), 3
            ),
            "mean_directness_0_to_2": round(
                statistics.fmean(item["directness"] for item in items), 3
            ),
            "reference_conflicts": sum(item["conflicts_with_reference"] for item in items),
            "known_wrong_conclusions": sum(
                item["matches_known_wrong_conclusion"] for item in items
            ),
        }

    overall = {
        system: aggregate([record["evaluations"][system] for record in records])
        for system in SYSTEMS
    }
    by_category_records: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_category_records[record["category"]].append(record)
    by_category = {
        category: {
            system: aggregate([record["evaluations"][system] for record in category_records])
            for system in SYSTEMS
        }
        for category, category_records in sorted(by_category_records.items())
    }
    best_including_ties: Counter[str] = Counter()
    unique_best: Counter[str] = Counter()
    label_positions: Counter[str] = Counter()
    for record in records:
        for label, system in record["blinded_mapping"].items():
            label_positions[f"{system}:{label}"] += 1
        scores = {
            system: (
                record["evaluations"][system]["scientific_correctness"],
                record["evaluations"][system]["completeness"],
                record["evaluations"][system]["directness"],
            )
            for system in SYSTEMS
        }
        best_score = max(scores.values())
        winners = [system for system, score in scores.items() if score == best_score]
        best_including_ties.update(winners)
        if len(winners) == 1:
            unique_best.update(winners)
    write_json(
        args.output / "summary.json",
        {
            "protocol": (
                "System identities were hidden and candidate order was deterministically shuffled per case. "
                "The same Qwen model reviewed all answers against the gold answer; scores are diagnostic "
                "and require human confirmation."
            ),
            "aggregate": overall,
            "by_category": by_category,
            "best_answer_counts_including_ties": dict(best_including_ties),
            "unique_best_answer_counts": dict(unique_best),
            "blinded_label_positions": dict(label_positions),
            "records": records,
        },
    )


if __name__ == "__main__":
    main()
