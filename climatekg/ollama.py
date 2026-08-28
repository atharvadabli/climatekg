from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .utils import l2_normalize, write_json

T = TypeVar("T", bound=BaseModel)

PROMPT_VERSIONS = {
    "paper_map": "v10",
    "map_consolidation": "v10",
    "section_scout": "v4",
    "query_parse": "v4",
    "final_synthesis": "v4",
}


def prompt_version(stage: str) -> str:
    return f"{stage}_{PROMPT_VERSIONS.get(stage, 'v2')}"


def stage_prompt_version(stage: str) -> str:
    return PROMPT_VERSIONS.get(stage, "v2")


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self.base_url = base_url.rstrip("/")

    def _post(self, endpoint: str, payload: dict[str, Any], timeout: int = 1800) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}{endpoint}", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())

    def embed(self, texts: list[str], model: str, dimension: int = 2048) -> list[list[float]]:
        if not texts:
            return []
        result = self._post("/api/embed", {"model": model, "input": texts, "dimensions": dimension, "truncate": False, "options": {"num_ctx": 32768}})
        return [l2_normalize(vector) for vector in result["embeddings"]]

    def structured(self, *, stage: str, system: str, user: str, schema: type[T], model: str, temperature: float, thinking: str, artifact_dir: Path, paper_id: str, input_block_ids: list[str], retries: int = 2) -> T:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        call_id = str(uuid.uuid4())
        prompt = user
        last_error = ""
        for attempt in range(retries + 1):
            payload: dict[str, Any] = {
                "model": model,
                "stream": False,
                "format": schema.model_json_schema(),
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                "options": {"temperature": temperature, "num_ctx": 32768},
            }
            payload["think"] = False if thinking == "no" else thinking
            request_path = artifact_dir / f"{call_id}.attempt{attempt}.request.json"
            write_json(request_path, payload)
            started = time.time()
            try:
                raw = self._post("/api/chat", payload)
            except urllib.error.HTTPError as exc:
                elapsed = time.time() - started
                body = exc.read().decode("utf-8", "replace")
                error_path = artifact_dir / f"{call_id}.attempt{attempt}.http_error.json"
                write_json(error_path, {"status": exc.code, "reason": exc.reason, "body": body})
                write_json(artifact_dir / f"{call_id}.attempt{attempt}.metrics.json", {"call_id": call_id, "attempt": attempt, "paper_id": paper_id, "stage": stage, "request_path": str(request_path.resolve()), "http_error_path": str(error_path.resolve()), "validated": False, "elapsed_seconds": elapsed})
                write_json(artifact_dir / f"{call_id}.envelope.json", {"call_id": call_id, "paper_id": paper_id, "stage": stage, "model": model, "prompt_version": prompt_version(stage), "thinking_level": thinking, "input_block_ids": input_block_ids, "request_path": str(request_path.resolve()), "validated": False, "retry_number": attempt, "http_error_path": str(error_path.resolve()), "elapsed_seconds": elapsed})
                transient_markers = ("connection was forcibly closed", "connection reset", "wsarecv", "unexpected eof", "loading model")
                if attempt < retries and any(marker in body.lower() for marker in transient_markers):
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"OLLAMA_HTTP_ERROR {stage}: {exc.code} {body[:500]}") from exc
            except urllib.error.URLError as exc:
                elapsed = time.time() - started
                error_path = artifact_dir / f"{call_id}.attempt{attempt}.transport_error.json"
                write_json(error_path, {"reason": str(exc.reason)})
                write_json(artifact_dir / f"{call_id}.attempt{attempt}.metrics.json", {"call_id": call_id, "attempt": attempt, "paper_id": paper_id, "stage": stage, "request_path": str(request_path.resolve()), "transport_error_path": str(error_path.resolve()), "validated": False, "elapsed_seconds": elapsed})
                if attempt < retries:
                    time.sleep(2 ** attempt)
                    continue
                raise RuntimeError(f"OLLAMA_TRANSPORT_ERROR {stage}: {exc.reason}") from exc
            raw_path = artifact_dir / f"{call_id}.attempt{attempt}.json"
            write_json(raw_path, raw)
            elapsed = time.time() - started
            api_metrics = {key: raw.get(key) for key in ("total_duration", "load_duration", "prompt_eval_count", "prompt_eval_duration", "eval_count", "eval_duration")}
            try:
                result = schema.model_validate_json(raw["message"]["content"])
                write_json(artifact_dir / f"{call_id}.attempt{attempt}.metrics.json", {"call_id": call_id, "attempt": attempt, "paper_id": paper_id, "stage": stage, "request_path": str(request_path.resolve()), "raw_response_path": str(raw_path.resolve()), "validated": True, "elapsed_seconds": elapsed, **api_metrics})
                write_json(artifact_dir / f"{call_id}.envelope.json", {"call_id": call_id, "paper_id": paper_id, "stage": stage, "model": model, "prompt_version": prompt_version(stage), "thinking_level": thinking, "input_block_ids": input_block_ids, "request_path": str(request_path.resolve()), "raw_response_path": str(raw_path.resolve()), "validated": True, "retry_number": attempt, "elapsed_seconds": elapsed})
                return result
            except (ValidationError, ValueError, KeyError) as exc:
                last_error = str(exc)
                write_json(artifact_dir / f"{call_id}.attempt{attempt}.metrics.json", {"call_id": call_id, "attempt": attempt, "paper_id": paper_id, "stage": stage, "request_path": str(request_path.resolve()), "raw_response_path": str(raw_path.resolve()), "validated": False, "elapsed_seconds": elapsed, "validation_errors": last_error, **api_metrics})
                prompt = (
                    f"{user}\n\n"
                    "CORRECTION TASK\n\n"
                    "The previous response could not be parsed using the JSON Schema supplied with this request. "
                    "Return the complete JSON object again with the schema errors corrected. Keep scientific content "
                    "grounded in the original input above.\n\n"
                    f"SCHEMA VALIDATION ERRORS\n{last_error}"
                )
        write_json(artifact_dir / f"{call_id}.envelope.json", {"call_id": call_id, "paper_id": paper_id, "stage": stage, "model": model, "validated": False, "retry_number": retries, "validation_errors": last_error})
        raise ValueError(f"FAILED_SCHEMA {stage}: {last_error}")
