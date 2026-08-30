from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RESULTS = Path("climatekg/runtime/outputs/three_system_benchmark_20260830")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def section(title: str, value: Any) -> str:
    content = value if isinstance(value, str) else json.dumps(value, indent=2)
    return f"{'=' * 88}\n{title}\n{'=' * 88}\n\n{content}\n"


def export_plain_or_graph(system: str, source: Path, target: Path) -> None:
    payload = read_json(source)
    retrieval_key = "retrieval" if system == "plain_rag" else "evidence"
    text = section("SYSTEM", system)
    text += section("QUESTION", payload["question"])
    text += section("RETRIEVED EVIDENCE", payload.get(retrieval_key, []))
    text += section("EXACT PROMPT SENT TO QWEN", payload.get("prompt", ""))
    text += section("FULL QWEN THINKING FIELD", payload.get("thinking", ""))
    text += section("FINAL QWEN RESPONSE", payload.get("answer", ""))
    text += section("TIMING AND GENERATION METRICS", {"timings": payload.get("timings"), "generation": payload.get("generation_metrics")})
    target.write_text(text, encoding="utf-8")


def find_model_exchange(artifact_dir: Path, stage: str) -> tuple[dict[str, Any], dict[str, Any]]:
    requests = sorted((artifact_dir / stage).glob("*.attempt*.request.json"))
    for request_path in reversed(requests):
        response_path = request_path.with_name(request_path.name.replace(".request.json", ".json"))
        if response_path.exists():
            return read_json(request_path), read_json(response_path)
    return {}, {}


def export_climate(source: Path, target: Path) -> None:
    payload = read_json(source)
    artifact_dir = Path(payload["artifact_dir"])
    parse_request, parse_response = find_model_exchange(artifact_dir, "parse")
    synthesis_request, synthesis_response = find_model_exchange(artifact_dir, "synthesis")
    text = section("SYSTEM", "climatekg")
    text += section("QUESTION", payload["question"])
    text += section("QUERY SPECIFICATION", payload.get("query_spec"))
    text += section("CONTEXT COMPARISONS", payload.get("context_evidence_comparisons"))
    text += section("CLAIM CANDIDATES", payload.get("claim_candidates"))
    text += section("DIRECT EVIDENCE PATHS", payload.get("direct_evidence_paths"))
    text += section("GRAPH PATHS", payload.get("graph_paths"))
    text += section("QUERY-PARSE REQUEST SENT TO QWEN", parse_request)
    text += section("QUERY-PARSE RESPONSE AND THINKING", parse_response)
    text += section("SYNTHESIS REQUEST SENT TO QWEN", synthesis_request)
    text += section("SYNTHESIS RESPONSE AND THINKING", synthesis_response)
    text += section("RENDERED GROUNDED ANSWER", payload.get("answer", ""))
    target.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export complete human-readable benchmark traces.")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    output = args.results / "human_readable_traces"
    output.mkdir(parents=True, exist_ok=True)
    exported = 0
    for system in ("plain_rag", "graphrag", "climatekg"):
        system_dir = args.results / system
        if not system_dir.exists():
            continue
        for source in sorted(system_dir.glob("*.json")):
            target = output / f"{source.stem}__{system}.txt"
            if system == "climatekg":
                export_climate(source, target)
            else:
                export_plain_or_graph(system, source, target)
            exported += 1
    print(json.dumps({"exported": exported, "output": str(output.resolve())}))


if __name__ == "__main__":
    main()
