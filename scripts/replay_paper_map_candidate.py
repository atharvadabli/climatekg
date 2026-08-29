from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from climatekg.constants import GENERATION_MODEL
from climatekg.extract import _split_prompt, _validate_map, render_paper_map_tree
from climatekg.extraction_models import PaperMap
from climatekg.ollama import OllamaClient
from climatekg.utils import write_json


BLOCK_ID = re.compile(r"P\d{6}:S\d{2}:P\d{4}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-request", type=Path, required=True)
    parser.add_argument("--candidate-prompt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--mode", choices=("paper-map", "map-consolidation"), default="paper-map")
    parser.add_argument("--thinking", choices=("no", "low", "medium"), default="medium")
    args = parser.parse_args()

    original = json.loads(args.original_request.read_text(encoding="utf-8"))
    _, candidate_user_template = _split_prompt(args.candidate_prompt.read_text(encoding="utf-8"))
    candidate_system, _ = _split_prompt(args.candidate_prompt.read_text(encoding="utf-8"))
    original_user = original["messages"][1]["content"]
    expected_prefix = "PAPER IDENTIFIER" if args.mode == "paper-map" else "PAPER METADATA"
    if not candidate_user_template.startswith(expected_prefix):
        raise ValueError(f"candidate prompt does not match {args.mode}")
    block_ids = sorted(set(BLOCK_ID.findall(original_user)))
    result = OllamaClient().structured(
        stage="paper_map_candidate" if args.mode == "paper-map" else "map_consolidation_candidate",
        system=candidate_system,
        user=original_user,
        schema=PaperMap,
        model=GENERATION_MODEL,
        temperature=0.0,
        thinking=args.thinking,
        artifact_dir=args.output_dir,
        paper_id=args.paper_id,
        input_block_ids=block_ids,
        retries=1,
    )
    if args.mode == "map-consolidation":
        expected_mentions = set(re.findall(r"\[(CM\d{3})\]", original_user))
        actual_mentions = set(result.context_mention_resolution)
        if actual_mentions != expected_mentions:
            raise ValueError(
                f"candidate setting inventory mismatch: missing={sorted(expected_mentions - actual_mentions)}, "
                f"extra={sorted(actual_mentions - expected_mentions)}"
            )
    _validate_map(result, set(block_ids))
    write_json(args.output_dir / "paper_map.json", result.model_dump(by_alias=True))
    (args.output_dir / "paper_map.tree.txt").write_text(render_paper_map_tree(result), encoding="utf-8")
    print(json.dumps({"contexts": len(result.contexts), "transitions": len(result.transitions), "output": str(args.output_dir.resolve())}))


if __name__ == "__main__":
    main()
