"""Small Ollama helpers used by both comparison baselines."""

from __future__ import annotations

import json
import math
import urllib.request
from typing import Any

from climatekg.constants import OLLAMA_CONTEXT_TOKENS


def post(base_url: str, endpoint: str, payload: dict[str, Any], timeout: int = 1200) -> dict[str, Any]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{endpoint}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def embed(base_url: str, model: str, texts: list[str]) -> list[list[float]]:
    return post(base_url, "/api/embed", {"model": model, "input": texts})["embeddings"]


def cosine(left: list[float], right: list[float]) -> float:
    denominator = math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right))
    return sum(x * y for x, y in zip(left, right)) / denominator if denominator else 0.0


def answer(base_url: str, model: str, prompt: str, thinking: str = "no") -> dict[str, Any]:
    return post(
        base_url,
        "/api/chat",
        {
            "model": model,
            "stream": False,
            "think": False if thinking == "no" else thinking,
            "options": {"num_ctx": OLLAMA_CONTEXT_TOKENS},
            "messages": [
                {
                    "role": "system",
                    "content": "Follow the task and response requirements in the user message.",
                },
                {"role": "user", "content": prompt},
            ],
        },
    )
