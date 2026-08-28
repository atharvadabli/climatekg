from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .config import PIPELINE
from .models import Claim, Context, Facet, SourceBlock, State, Transition
from .ollama import OllamaClient

DOMAIN_ORDER = ["spatial_configuration", "land_surface", "hydrology", "atmosphere", "climate", "substrate_terrain", "other"]


def facet_notion_text(facet: Facet) -> str:
    return f"{facet.domain} | {facet.notion}"


def facet_content_text(facet: Facet) -> str:
    return f"Domain: {facet.domain}\nNotion: {facet.notion}\nDescription: {facet.description}"


def effective_facets(context_id: str, contexts: list[Context], facets: list[Facet]) -> list[Facet]:
    by_context = {item.id: item for item in contexts}
    visited: set[str] = set()
    ordered_contexts: list[str] = []

    def visit(identifier: str) -> None:
        if identifier in visited:
            return
        visited.add(identifier)
        for parent in by_context[identifier].parent_ids:
            visit(parent)
        ordered_contexts.append(identifier)

    visit(context_id)
    order = {identifier: index for index, identifier in enumerate(ordered_contexts)}
    return sorted((item for item in facets if item.context_id in order), key=lambda x: (order[x.context_id], DOMAIN_ORDER.index(x.domain), x.notion, x.id))


def context_text(context: Context, contexts: list[Context], facets: list[Facet]) -> str:
    grouped: dict[str, list[Facet]] = defaultdict(list)
    for facet in effective_facets(context.id, contexts, facets):
        grouped[facet.domain].append(facet)
    lines = [f"Context: {context.label}"]
    for domain in DOMAIN_ORDER:
        if grouped[domain]:
            lines.append(f"\n[{domain}]")
            lines.extend(f"{facet.notion}:\n{facet.description}" for facet in grouped[domain])
    return "\n".join(lines)


def claim_text(claim: Claim) -> str:
    return f"FROM: {claim.from_.concept} | {claim.from_.state}\nTO: {claim.to.concept} | {claim.to.state}\nRELATION: {claim.relation}\nDESCRIPTION: {claim.description}"


def transition_text(transition: Transition, contexts: list[Context]) -> str:
    labels = {item.id: item.label for item in contexts}
    return f"FROM CONTEXT: {labels[transition.from_context_id]}\nTO CONTEXT: {labels[transition.to_context_id]}\nTRANSITION: {transition.description}"


def _embed_batches(client: OllamaClient, texts: list[str], batch_size: int = 32) -> list[list[float]]:
    config = PIPELINE["embeddings"]
    result = []
    for offset in range(0, len(texts), batch_size):
        result.extend(client.embed(texts[offset:offset + batch_size], config["model"], config["dimension"]))
    return result


def embed_source_blocks(client: OllamaClient, blocks: list[SourceBlock], cache_path: Path | None = None) -> None:
    if not PIPELINE["embeddings"]["block_embeddings"]:
        return
    cached: dict[str, list[float]] = {}
    if cache_path and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
    dimension = PIPELINE["embeddings"]["dimension"]
    if set(cached) == {item.id for item in blocks} and all(len(vector) == dimension for vector in cached.values()):
        for item in blocks:
            item.embedding = cached[item.id]
        return
    texts = [f"Section: {' > '.join(x.section_path)}\nType: {x.block_type}\nText: {x.text}" for x in blocks]
    for item, vector in zip(blocks, _embed_batches(client, texts)):
        item.embedding = vector
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({item.id: item.embedding for item in blocks}, ensure_ascii=False), encoding="utf-8")


def embed_paper(client: OllamaClient, blocks: list[SourceBlock], contexts: list[Context], facets: list[Facet], transitions: list[Transition], claims: list[Claim], states: list[State]) -> dict[str, str]:
    if PIPELINE["embeddings"]["block_embeddings"] and any(item.embedding is None for item in blocks):
        embed_source_blocks(client, blocks)
    notion_vectors = _embed_batches(client, [facet_notion_text(x) for x in facets])
    content_vectors = _embed_batches(client, [facet_content_text(x) for x in facets])
    for item, notion, content in zip(facets, notion_vectors, content_vectors):
        item.notion_embedding, item.content_embedding = notion, content
    context_texts = {x.id: context_text(x, contexts, facets) for x in contexts}
    for item, vector in zip(contexts, _embed_batches(client, list(context_texts.values()))):
        item.retrieval_embedding = vector
    for item, vector in zip(claims, _embed_batches(client, [claim_text(x) for x in claims])):
        item.claim_embedding = vector
    for item, vector in zip(transitions, _embed_batches(client, [transition_text(x, contexts) for x in transitions])):
        item.transition_embedding = vector
    for item, vector in zip(states, _embed_batches(client, [x.concept for x in states])):
        item.concept_embedding = vector
    return context_texts


def embed_claims_and_states(client: OllamaClient, claims: list[Claim], states: list[State]) -> None:
    """Refresh embeddings whose text changes during State recanonicalization."""
    for item, vector in zip(claims, _embed_batches(client, [claim_text(x) for x in claims])):
        item.claim_embedding = vector
    for item, vector in zip(states, _embed_batches(client, [x.concept for x in states])):
        item.concept_embedding = vector
