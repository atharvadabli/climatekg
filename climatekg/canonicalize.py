from __future__ import annotations

import re
from typing import Iterable

from .config import STATE_ALIASES
from .models import Claim, State
from .utils import normalize_text_key


def _alias_map(group: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for canonical, aliases in STATE_ALIASES[group].items():
        for alias in [canonical, *aliases]:
            result[normalize_text_key(alias)] = canonical
    return result


CONCEPT_ALIASES = _alias_map("concept_aliases")
STATE_DIRECTIONS = _alias_map("state_directions")


def canonical_concept(raw: str) -> str:
    key = normalize_text_key(raw)
    # Expand only explicitly verified aliases. Unknown vocabulary retains its
    # normalized scientific modifiers and becomes a new canonical concept.
    return CONCEPT_ALIASES.get(key, key)


def canonical_direction(raw: str) -> str:
    key = normalize_text_key(raw)
    return STATE_DIRECTIONS.get(key, key)


def state_id(concept: str, state: str) -> str:
    slug = lambda value: re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return f"state::{slug(concept)}::{slug(state)}"


def canonicalize_claim_states(claims: Iterable[Claim]) -> list[State]:
    by_id: dict[str, State] = {}
    for claim in claims:
        for endpoint in (claim.from_, claim.to):
            concept = canonical_concept(endpoint.concept)
            direction = canonical_direction(endpoint.state)
            endpoint.concept = concept
            endpoint.state = direction
            identifier = state_id(concept, direction)
            if identifier not in by_id:
                by_id[identifier] = State(id=identifier, concept=concept, state=direction, aliases=[])
    return sorted(by_id.values(), key=lambda item: item.id)
