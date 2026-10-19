"""Blindly compare baseline and decomposed ClimateKG answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class AnswerScore(BaseModel):
    candidate: Literal["A", "B"]
    scientific_correctness: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    directness: int = Field(ge=0, le=2)
    explanation: str


class PairReview(BaseModel):
    evaluations: list[AnswerScore] = Field(min_length=2, max_length=2)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-root", required=True, type=Path)
    parser.add_argument("--dataset", required=True, type=Path)
    parser.add_argument("--baseline-results", required=True, type=Path)
    parser.add_argument("--candidate-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args()

    sys.path.insert(0, str(args.code_root.resolve()))
    from climatekg.config import QUERY_PIPELINE
    from climatekg.ollama import OllamaClient

    cases = {item["id"]: item for item in read_json(args.dataset)}
    client = OllamaClient()
    rows = []
    system = """TASK

Compare two answers to one land-atmosphere science question against a supplied reference answer.

Score each candidate independently:
- `scientific_correctness`: 0-4;
- `completeness`: 0-4;
- `directness`: 0-2;
- `explanation`: one short sentence identifying the main strength or failure.

The reference answer defines the expected scientific content. Citations may add useful detail, but unsupported or contradictory statements reduce correctness. Return valid JSON only using the supplied schema."""
    config = QUERY_PIPELINE["ollama"]["stages"]["query_combined_synthesis"]
    for case_id in args.case:
        case = cases[case_id]
        baseline = read_json(args.baseline_results / f"{case_id}.json")["generated_answer"]
        candidate = read_json(args.candidate_results / f"{case_id}.json")["generated_answer"]
        systems = [("baseline", baseline), ("decomposed", candidate)]
        random.Random(int(hashlib.sha256(case_id.encode()).hexdigest()[:16], 16)).shuffle(systems)
        labels = {"A": systems[0][0], "B": systems[1][0]}
        user = (
            f"QUESTION\n{case['question']}\n\nREFERENCE ANSWER\n{case['reference_answer']}\n\n"
            f"CANDIDATE A\n{systems[0][1]}\n\nCANDIDATE B\n{systems[1][1]}"
        )
        review = client.structured(
            stage="query_combined_synthesis",
            system=system,
            user=user,
            schema=PairReview,
            model=QUERY_PIPELINE["ollama"]["model"],
            temperature=config["temperature"],
            thinking=config["thinking"],
            artifact_dir=args.output / "artifacts" / case_id,
            paper_id=case_id,
            input_block_ids=[],
            retries=config["retries"],
        )
        scores = {
            labels[item.candidate]: item.model_dump(exclude={"candidate"})
            for item in review.evaluations
        }
        row = {"case_id": case_id, "label_mapping": labels, "scores": scores}
        rows.append(row)
        write_json(args.output / "cases" / f"{case_id}.json", row)
        print(f"{case_id}: {scores}", flush=True)

    summary = {}
    for system_name in ("baseline", "decomposed"):
        summary[system_name] = {
            metric: round(sum(row["scores"][system_name][metric] for row in rows) / len(rows), 3)
            for metric in ("scientific_correctness", "completeness", "directness")
        }
    write_json(args.output / "summary.json", {"case_count": len(rows), "systems": summary})


if __name__ == "__main__":
    main()
