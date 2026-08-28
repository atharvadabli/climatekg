from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import indexing_config, query_config

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOT = ROOT / "climatekg" / "runtime"
DATA_ROOT = RUNTIME_ROOT / "data" / "papers"
OUTPUT_ROOT = RUNTIME_ROOT / "outputs"
CACHE_ROOT = RUNTIME_ROOT / "cache"
LOG_ROOT = RUNTIME_ROOT / "logs"
FAILED_RUNS_ROOT = RUNTIME_ROOT / "failed_runs"


def load_config(name: str) -> dict[str, Any]:
    """Load JSON-compatible YAML without adding a YAML runtime dependency."""
    return json.loads((ROOT / "config" / name).read_text(encoding="utf-8"))


PIPELINE = indexing_config()
QUERY_PIPELINE = query_config()
STATE_ALIASES = load_config("state_aliases.yaml")
