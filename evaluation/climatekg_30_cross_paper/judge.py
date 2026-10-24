"""Run a supplemental batched Qwen review of generated answers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AnswerEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    verdict: Literal["correct", "mostly_correct", "partly_correct", "incorrect"]
    scientific_correctness: int = Field(ge=0, le=4)
    completeness: int = Field(ge=0, le=4)
    directness: int = Field(ge=0, le=2)
    covered_qualifiers: list[str]
    missed_qualifiers: list[str]
    unsupported_conclusion_present: bool
    problems: list[str]
    explanation: str


class EvaluationBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluations: list[AnswerEvaluation]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=5)
    args = parser.parse_args()

    sys.path.insert(0, str(args.project_root.resolve()))
    from climatekg.constants import GENERATION_MODEL
    from climatekg.ollama import OllamaClient

    rows = read_json(args.responses)
    prompt = (Path(__file__).parent / "judge_prompt.txt").read_text(encoding="utf-8")
    system, user_template = prompt.split("USER\n", 1)
    client = OllamaClient()
    evaluations: list[dict] = []
    for start in range(0, len(rows), args.batch_size):
        batch = rows[start : start + args.batch_size]
        records = [
            {
                "id": row["id"],
                "question": row["question"],
                "reference_answer": row["reference_answer"],
                "required_qualifiers": row["required_qualifiers"],
                "unsupported_conclusions": row["unsupported_conclusions"],
                "answer": row["generated_answer"],
            }
            for row in batch
        ]
        expected_ids = [row["id"] for row in batch]
        result = client.structured(
            stage="query_answer_diagnostic_judge",
            system=system.removeprefix("SYSTEM\n").strip(),
            user=user_template.format(input_json=json.dumps(records, ensure_ascii=False, indent=2)).strip(),
            schema=EvaluationBatch,
            model=GENERATION_MODEL,
            temperature=0.0,
            thinking="no",
            artifact_dir=args.output / "calls" / f"batch_{start // args.batch_size + 1:02d}",
            paper_id=f"judge_batch_{start // args.batch_size + 1:02d}",
            input_block_ids=expected_ids,
            retries=2,
        )
        actual_ids = [item.id for item in result.evaluations]
        if actual_ids != expected_ids:
            raise ValueError(f"Judge returned IDs {actual_ids}; expected {expected_ids}")
        evaluations.extend(item.model_dump() for item in result.evaluations)
        write_json(args.output / "progress.json", evaluations)
        print(f"Judged {len(evaluations)}/{len(rows)} answers", flush=True)

    write_json(args.output / "evaluations.json", evaluations)
    verdicts = {name: 0 for name in ("correct", "mostly_correct", "partly_correct", "incorrect")}
    for item in evaluations:
        verdicts[item["verdict"]] += 1
    lines = [
        "# Supplemental Qwen answer review",
        "",
        "This is a same-model diagnostic comparison against the development references. It is not independent human evaluation and does not verify citations.",
        "",
        "## Verdicts",
        "",
        *[f"- `{name}`: {count}" for name, count in verdicts.items()],
        "",
        "| ID | Verdict | Correctness | Completeness | Directness | Explanation |",
        "|---|---|---:|---:|---:|---|",
    ]
    for item in evaluations:
        lines.append(
            f"| {item['id']} | {item['verdict']} | {item['scientific_correctness']}/4 | "
            f"{item['completeness']}/4 | {item['directness']}/2 | {item['explanation']} |"
        )
    lines.append("")
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
