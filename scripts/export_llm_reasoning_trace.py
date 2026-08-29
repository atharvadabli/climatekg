from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export one exact Ollama request/response as readable text.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()

    request = json.loads(args.request.read_text(encoding="utf-8"))
    response = json.loads(args.response.read_text(encoding="utf-8"))
    message = response.get("message", {})
    sections = [
        f"CASE: {args.label}",
        "",
        "EXACT OLLAMA REQUEST JSON",
        "=========================",
        json.dumps(request, indent=2, ensure_ascii=False),
        "",
        "MODEL THINKING (VERBATIM)",
        "=========================",
        message.get("thinking", "[No thinking field was returned.]"),
        "",
        "FINAL MODEL OUTPUT (VERBATIM)",
        "=============================",
        message.get("content", ""),
        "",
        "FULL RAW OLLAMA RESPONSE JSON",
        "=============================",
        json.dumps(response, indent=2, ensure_ascii=False),
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(sections) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "thinking_chars": len(message.get("thinking", ""))}))


if __name__ == "__main__":
    main()
