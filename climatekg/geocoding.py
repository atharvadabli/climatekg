from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class GeocodingDecision:
    geometry: dict[str, Any] | None
    reason: str


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _candidate_text(candidate: dict[str, Any]) -> str:
    address = candidate.get("address") or {}
    return _normalized(" ".join([str(candidate.get("display_name", "")), *map(str, address.values())]))


def _query_parts(query: str) -> list[str]:
    return [_normalized(part) for part in query.split(",") if _normalized(part)]


class NominatimGeocoder:
    """Resolve qualified study-place names once and persist the full decision trace."""

    def __init__(
        self,
        config: dict[str, Any],
        root: Path,
        fetch_json: Callable[[str, dict[str, str], float], list[dict[str, Any]]] | None = None,
    ) -> None:
        if config.get("provider") != "nominatim":
            raise ValueError(f"unsupported geocoding provider: {config.get('provider')}")
        self.endpoint = str(config["endpoint"]).rstrip("/")
        self.user_agent = str(config["user_agent"]).strip()
        if not self.user_agent:
            raise ValueError("geocoder user_agent must be configured")
        configured_path = Path(str(config["cache_path"]))
        self.cache_path = configured_path if configured_path.is_absolute() else root / configured_path
        self.minimum_interval = float(config["minimum_interval_seconds"])
        self.result_limit = int(config["result_limit"])
        self.timeout = float(config["timeout_seconds"])
        self.fetch_json = fetch_json or self._fetch_json
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._cache = self._read_cache()

    def _read_cache(self) -> dict[str, Any]:
        if not self.cache_path.exists():
            return {"provider": "nominatim", "endpoint": self.endpoint, "entries": {}}
        value = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if value.get("provider") != "nominatim" or not isinstance(value.get("entries"), dict):
            raise ValueError(f"invalid geocoding cache: {self.cache_path}")
        return value

    def _write_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self._cache, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.cache_path)

    def _fetch_json(self, url: str, headers: dict[str, str], timeout: float) -> list[dict[str, Any]]:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError("Nominatim response must be a JSON array")
        return payload

    def _request(self, query: str) -> list[dict[str, Any]]:
        parameters = urllib.parse.urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "addressdetails": "1",
                "accept-language": "en",
                "limit": str(self.result_limit),
            }
        )
        with self._lock:
            delay = self.minimum_interval - (time.monotonic() - self._last_request)
            if delay > 0:
                time.sleep(delay)
            result = self.fetch_json(
                f"{self.endpoint}/search?{parameters}",
                {"User-Agent": self.user_agent, "Accept": "application/json"},
                self.timeout,
            )
            self._last_request = time.monotonic()
            return result

    @staticmethod
    def _decide(query: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        parts = _query_parts(query)
        matching = [candidate for candidate in candidates if parts and all(part in _candidate_text(candidate) for part in parts)]
        if len(matching) != 1:
            return {
                "status": "unresolved",
                "reason": "no_unique_qualified_candidate",
                "selected": None,
                "candidates": candidates,
            }
        selected = matching[0]
        try:
            longitude = float(selected["lon"])
            latitude = float(selected["lat"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("selected Nominatim candidate has invalid coordinates") from exc
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError("selected Nominatim coordinates are outside valid bounds")
        return {
            "status": "resolved",
            "reason": "unique_candidate_matching_all_explicit_place_parts",
            "selected": selected,
            "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
            "candidates": candidates,
        }

    def resolve(self, query: str) -> GeocodingDecision:
        key = _normalized(query)
        if not key:
            return GeocodingDecision(None, "empty_query")
        with self._lock:
            cached = self._cache["entries"].get(key)
        if cached is None:
            candidates = self._request(query)
            cached = {
                "query": query,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                **self._decide(query, candidates),
            }
            with self._lock:
                self._cache["entries"][key] = cached
                self._write_cache()
        return GeocodingDecision(cached.get("geometry"), str(cached["reason"]))
