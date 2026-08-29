from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _dotenv_values() -> dict[str, str]:
    path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            values[key] = value.strip().strip('"').strip("'")
    return values


def environment_value(name: str) -> str | None:
    """Read an explicit process variable, then the repository-local .env."""
    return os.environ.get(name) or _dotenv_values().get(name)
