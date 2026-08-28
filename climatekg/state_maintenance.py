from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .canonicalize import canonicalize_claim_states, state_id
from .config import STATE_ALIASES
from .embeddings import embed_claims_and_states
from .models import FinalPaper
from .ollama import OllamaClient
from .utils import write_json


def recanonicalize_corpus(data_root: Path, client: OllamaClient | None = None) -> list[dict[str, Any]]:
    """Rebuild canonical States and dependent embeddings without rerunning extraction."""
    client = client or OllamaClient()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results: list[dict[str, Any]] = []
    for final_path in sorted(data_root.glob("P*/final/final_paper.json")):
        original_text = final_path.read_text(encoding="utf-8")
        paper = FinalPaper.model_validate_json(original_text)
        old_endpoints = _endpoint_ids(paper)
        old_state_count = len(paper.states)

        states = canonicalize_claim_states(paper.claims)
        embed_claims_and_states(client, paper.claims, states)
        paper.states = states
        validated = FinalPaper.model_validate(paper.model_dump(by_alias=True))

        backup = final_path.parent / "history" / timestamp / "final_paper.json"
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(original_text, encoding="utf-8")
        write_json(final_path, validated.model_dump(by_alias=True))

        new_endpoints = _endpoint_ids(validated)
        changes = [
            {"claim_id": claim_id, "endpoint": endpoint, "old_state_id": old_id, "new_state_id": new_endpoints[(claim_id, endpoint)]}
            for (claim_id, endpoint), old_id in old_endpoints.items()
            if old_id != new_endpoints[(claim_id, endpoint)]
        ]
        audit = {
            "paper_id": validated.paper.id,
            "timestamp": timestamp,
            "alias_registry_version": STATE_ALIASES["version"],
            "old_state_count": old_state_count,
            "new_state_count": len(states),
            "changed_endpoints": changes,
            "backup": str(backup),
        }
        write_json(final_path.parent / "state_recanonicalization.json", audit)
        results.append(audit)
    return results


def _endpoint_ids(paper: FinalPaper) -> dict[tuple[str, str], str]:
    return {
        (claim.id, endpoint_name): state_id(endpoint.concept, endpoint.state)
        for claim in paper.claims
        for endpoint_name, endpoint in (("from", claim.from_), ("to", claim.to))
    }
