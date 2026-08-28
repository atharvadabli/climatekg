from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PREFERRED_STAGES = (
    "paper_map",
    "section_scout",
    "map_consolidation",
    "facet_extraction",
    "claim_extraction",
    "context_reconciliation",
    "paper_consolidation",
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _request_files(paper_dir: Path) -> dict[str, Path]:
    selected: dict[str, Path] = {}
    for envelope_path in sorted((paper_dir / "extraction").rglob("*.envelope.json")):
        envelope = _load(envelope_path)
        stage = envelope.get("stage")
        request_path = envelope.get("request_path")
        if stage not in PREFERRED_STAGES or stage in selected or not request_path:
            continue
        path = Path(request_path)
        if not path.is_absolute() and path.is_file():
            path = path.resolve()
        elif not path.is_absolute():
            path = envelope_path.parent / path
        if path.is_file():
            selected[stage] = path
    return selected


def _render(stage: str, request_path: Path, payload: dict[str, Any]) -> str:
    messages = {item["role"]: item["content"] for item in payload["messages"]}
    header = {
        "stage": stage,
        "model": payload["model"],
        "temperature": payload.get("options", {}).get("temperature"),
        "num_ctx": payload.get("options", {}).get("num_ctx"),
        "thinking": payload.get("think"),
        "captured_request_json": str(request_path.resolve()),
    }
    return (
        "ACTUAL OLLAMA /api/chat REQUEST\n"
        "================================\n\n"
        + json.dumps(header, indent=2, ensure_ascii=False)
        + "\n\nSYSTEM PROMPT\n"
        + "-------------\n"
        + messages["system"]
        + "\n\nUSER PROMPT (FULLY RENDERED)\n"
        + "----------------------------\n"
        + messages["user"]
        + "\n\nJSON SCHEMA SENT IN OLLAMA `format`\n"
        + "-----------------------------------\n"
        + json.dumps(payload["format"], indent=2, ensure_ascii=False)
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paper_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--limit", type=int, default=4)
    args = parser.parse_args()

    requests = _request_files(args.paper_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, str]] = []
    for index, stage in enumerate(PREFERRED_STAGES, start=1):
        if stage not in requests or len(manifest) >= args.limit:
            continue
        request_path = requests[stage]
        output_path = args.output_dir / f"{len(manifest) + 1:02d}_{stage}_actual_prompt_and_schema.txt"
        output_path.write_text(_render(stage, request_path, _load(request_path)), encoding="utf-8")
        manifest.append({"stage": stage, "file": output_path.name, "request_json": str(request_path.resolve())})
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(manifest), "output_dir": str(args.output_dir.resolve()), "stages": [x["stage"] for x in manifest]}, indent=2))


if __name__ == "__main__":
    main()
