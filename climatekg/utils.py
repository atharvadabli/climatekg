from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable


def normalize_text_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower().strip()
    value = re.sub(r"[\u2010-\u2015]", "-", value)
    value = re.sub(r"[^\w%+./-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[\w%+./-]+", unicodedata.normalize("NFKC", text).lower())


def token_count(text: str) -> int:
    # The local Qwen tokenizer is unavailable as a Python package. This estimate
    # is used only for routing/budget enforcement and errs conservatively.
    return max(1, math.ceil(len(text) / 3.5))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def unique_in_order(values: Iterable[str], order: dict[str, int] | None = None) -> list[str]:
    result = list(dict.fromkeys(values))
    return sorted(result, key=lambda x: order.get(x, 10**12)) if order else result


def cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm else vector

