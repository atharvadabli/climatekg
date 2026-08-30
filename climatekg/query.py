from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .canonicalize import canonical_concept, canonical_direction, state_id
from .config import PIPELINE, QUERY_PIPELINE, ROOT, STATE_ALIASES
from .earth_engine import EarthEngineBackend
from .embeddings import DOMAIN_ORDER, effective_facets, facet_content_text, facet_notion_text
from .enrichment import derive_facets, query_facets
from .extraction_models import ParsedQuery, ParsedQueryFacetBatch, SynthesisItem, SynthesisOutput
from .geocoding import NominatimGeocoder
from .models import Claim, ClaimEndpoint, Context, Facet, FinalPaper, QueryContext, QueryFacet, QuerySpec, SourceBlock, SpatialSupport, State, Transition
from .ollama import OllamaClient, stage_prompt_version
from .spatial import resolve_spatial_support
from .utils import cosine, normalize_text_key, token_count, write_json
from .vector_index import FaissIndexes


@dataclass
class Corpus:
    papers: list[FinalPaper]

    def __post_init__(self) -> None:
        self.contexts = {x.id: x for p in self.papers for x in p.contexts}
        self.facets = {x.id: x for p in self.papers for x in p.facets}
        self.transitions = {x.id: x for p in self.papers for x in p.transitions}
        self.claims = {x.id: x for p in self.papers for x in p.claims}
        self.blocks = {x.id: x for p in self.papers for x in p.source_blocks}
        self.paper_by_id = {p.paper.id: p.paper for p in self.papers}
        self.states = {x.id: x for p in self.papers for x in p.states}
        self.contexts_by_paper = {p.paper.id: p.contexts for p in self.papers}
        self.facets_by_paper = {p.paper.id: p.facets for p in self.papers}

    def effective_facets(self, context_id: str) -> list[Facet]:
        context = self.contexts[context_id]
        return effective_facets(context_id, self.contexts_by_paper[context.paper_id], self.facets_by_paper[context.paper_id])


def _read_prompt(name: str) -> str:
    return (ROOT / "prompts" / name).read_text(encoding="utf-8")


def _query_spec_payload(spec: QuerySpec) -> dict[str, Any]:
    payload = spec.model_dump(by_alias=True)
    for facet in payload["context"]["facets"]:
        facet.pop("notion_embedding", None)
        facet.pop("content_embedding", None)
    return payload


CONTEXT_VARIABLE_PATTERNS = {
    "wind": r"\b(?:wind|flow)\b",
    "temperature_or_heating": r"\b(?:temperature|heating|heat)\b",
    "precipitation": r"\b(?:precipitation|rainfall|rain)\b",
    "moisture": r"\b(?:moisture|humidity|humid)\b",
    "aridity": r"\b(?:aridity|arid)\b",
    "land_cover": r"\b(?:land cover|cropland|forest|vegetation)\b",
    "terrain": r"\b(?:terrain|elevation|slope|relief)\b",
}


def context_evidence_comparisons(spec: QuerySpec) -> list[dict[str, Any]]:
    """Expose overlapping user and dataset context without inferring agreement."""
    user_facets = [facet for facet in spec.context.facets if facet.origin == "user"]
    derived_facets = [facet for facet in spec.context.facets if facet.origin == "derived"]
    comparisons = []
    for user_facet in user_facets:
        user_text = normalize_text_key(f"{user_facet.notion} {user_facet.description}")
        for derived_facet in derived_facets:
            if user_facet.domain != derived_facet.domain:
                continue
            derived_text = normalize_text_key(f"{derived_facet.notion} {derived_facet.description}")
            shared = [
                variable
                for variable, pattern in CONTEXT_VARIABLE_PATTERNS.items()
                if re.search(pattern, user_text) and re.search(pattern, derived_text)
            ]
            if not shared:
                continue
            comparisons.append(
                {
                    "user_facet_id": user_facet.id,
                    "derived_facet_id": derived_facet.id,
                    "shared_variables": shared,
                    "status": "coexisting_not_adjudicated",
                    "user_description": user_facet.description,
                    "derived_description": derived_facet.description,
                }
            )
    return comparisons


def context_comparison_limitations(comparisons: list[dict[str, Any]]) -> list[SynthesisItem]:
    grouped: dict[tuple[str, tuple[str, ...], str], list[dict[str, Any]]] = defaultdict(list)
    for comparison in comparisons:
        key = (
            comparison["user_facet_id"],
            tuple(comparison["shared_variables"]),
            comparison["user_description"],
        )
        grouped[key].append(comparison)
    limitations = []
    for (user_facet_id, variables, user_description), items in grouped.items():
        clean_user_description = user_description.strip().rstrip(".;")
        derived_descriptions = "; ".join(item["derived_description"].strip().rstrip(".;") for item in items)
        text = (
            f'The user specified "{clean_user_description}". Derived context records for {", ".join(variables)} '
            f'report: {derived_descriptions} No categorical threshold or season mapping was supplied, '
            "so agreement or mismatch was not adjudicated."
        )
        limitations.append(
            SynthesisItem(
                text=text,
                support_claim_ids=[],
                support_query_facet_ids=[user_facet_id, *[item["derived_facet_id"] for item in items]],
                kind="limitation",
            )
        )
    return limitations


def _query_mode(parsed: ParsedQuery) -> str:
    if parsed.global_requested:
        return "global"
    if parsed.source and parsed.target:
        return "a_to_b"
    if parsed.source:
        return "forward"
    if parsed.target:
        return "backward"
    return "global"


def _is_unspecified_target_state(value: str) -> bool:
    return normalize_text_key(value) in {
        "affect", "affected", "change", "changed", "effect", "effects",
        "impact", "impacts", "report", "reported", "reporting", "reports",
    }


def _is_spatial_relation_target(endpoint: Any, question: str) -> bool:
    if not endpoint or not re.search(r"\bwhere\b", question, re.I):
        return False
    concept = normalize_text_key(endpoint.concept)
    state = normalize_text_key(endpoint.state)
    return "location" in concept or "relative to" in state


def _is_comparative_endpoint(endpoint: Any) -> bool:
    return bool(endpoint and " or " in normalize_text_key(endpoint.state))


def _is_compound_unspecified_target(endpoint: Any) -> bool:
    return bool(endpoint and not endpoint.state.strip() and re.search(r"\band\b", endpoint.concept, re.I))


def parse_query(question: str, query_id: str, client: OllamaClient, artifact_dir: Path) -> tuple[QuerySpec, list[str]]:
    prompt = _read_prompt("query_parse.txt")
    system, user = prompt.split("USER\n", 1)
    config = QUERY_PIPELINE["ollama"]["stages"]["query_parse"]
    warnings: list[str] = []
    parsed = client.structured(stage="query_parse", system=system.removeprefix("SYSTEM\n").strip(), user=user.format(user_question=question).strip(), schema=ParsedQuery, model=QUERY_PIPELINE["ollama"]["model"], temperature=config["temperature"], thinking=config["thinking"], artifact_dir=artifact_dir / "parse", paper_id=query_id, input_block_ids=[], retries=config["retries"])
    normalized = unicodedata.normalize("NFC", question)
    explicit_global = bool(re.search(r"\b(?:across (?:the )?(?:indexed )?(?:literature|studies)|global(?:ly)?|corpus-wide)\b", normalized, re.I))
    if parsed.global_requested != explicit_global:
        warnings.append("QUERY_GLOBAL_FLAG_NORMALIZED")
        parsed = parsed.model_copy(update={"global_requested": explicit_global})
    if not parsed.explicit_context_facets and not explicit_global and re.match(r"\s*(?:in|under|during)\b", normalized, re.I):
        warnings.append("QUERY_CONTEXT_FACET_REPAIR")
        facet_system = """TASK

Read one land-atmosphere question and extract environmental conditions explicitly stated by the user.

Return valid JSON only in the supplied schema. The output field `explicit_context_facets` is a list. For each condition return:
- `domain`: exactly one of `spatial_configuration`, `land_surface`, `hydrology`, `atmosphere`, `climate`, `substrate_terrain`, or `other`;
- `notion`: a concise 2-8 word name for the condition;
- `description`: a faithful phrase or sentence describing the condition;
- `supporting_text_span`: the exact words copied from the question.

Use only conditions stated in the question."""
        repair_user = f"""USER QUESTION
{question}

The first parse omitted the environmental information at the beginning of this question. Extract the stated climate, season, land surface, hydrology, atmosphere, terrain, and spatial-configuration conditions."""
        repair_config = QUERY_PIPELINE["ollama"]["stages"]["query_parse_context_repair"]
        facet_batch = client.structured(stage="query_parse_context_repair", system=facet_system, user=repair_user, schema=ParsedQueryFacetBatch, model=QUERY_PIPELINE["ollama"]["model"], temperature=repair_config["temperature"], thinking=repair_config["thinking"], artifact_dir=artifact_dir / "parse", paper_id=query_id, input_block_ids=[], retries=repair_config["retries"])
        parsed = parsed.model_copy(update={"explicit_context_facets": facet_batch.explicit_context_facets, "global_requested": False})
    spans = [x.supporting_text_span for x in parsed.explicit_context_facets]
    spans += [x.supporting_text_span for x in (parsed.source, parsed.target) if x]
    if any(unicodedata.normalize("NFC", span) not in normalized for span in spans):
        warnings.append("QUERY_INVALID_SUPPORTING_SPAN_DISCARDED")
    exact = lambda span: unicodedata.normalize("NFC", span) in normalized
    valid_facets = [item for item in parsed.explicit_context_facets if exact(item.supporting_text_span)]
    if parsed.spatial_reference:
        spatial_key = normalize_text_key(parsed.spatial_reference.text)
        without_duplicate_place = [item for item in valid_facets if not (item.domain == "spatial_configuration" and normalize_text_key(item.supporting_text_span) == spatial_key)]
        if len(without_duplicate_place) != len(valid_facets):
            warnings.append("QUERY_DUPLICATE_SPATIAL_FACET_DISCARDED")
            valid_facets = without_duplicate_place
    valid_source = parsed.source if parsed.source and exact(parsed.source.supporting_text_span) else None
    valid_target = parsed.target if parsed.target and exact(parsed.target.supporting_text_span) else None
    if len(valid_facets) != len(parsed.explicit_context_facets) or valid_source is not parsed.source or valid_target is not parsed.target:
        warnings.append("QUERY_UNSUPPORTED_PARSED_ITEM_DISCARDED")
    if valid_target and _is_unspecified_target_state(valid_target.state):
        warnings.append("QUERY_UNSPECIFIED_TARGET_STATE_DISCARDED")
        valid_target = None
    if _is_spatial_relation_target(valid_target, normalized):
        warnings.append("QUERY_SPATIAL_RELATION_TARGET_DISCARDED")
        valid_target = None
    if _is_comparative_endpoint(valid_source) or _is_comparative_endpoint(valid_target):
        # An X-or-Y question is a comparison retrieval task. Keeping only the
        # non-comparative endpoint can hide the Claims representing one side.
        warnings.append("QUERY_COMPARATIVE_ENDPOINTS_DISCARDED")
        valid_source = None
        valid_target = None
    if _is_compound_unspecified_target(valid_target):
        warnings.append("QUERY_COMPOUND_TARGET_TREATED_AS_FORWARD")
        valid_target = None
    for name, endpoint in (("source", valid_source), ("target", valid_target)):
        if not endpoint or not endpoint.state.strip():
            continue
        span_key = normalize_text_key(endpoint.supporting_text_span)
        state_key = normalize_text_key(endpoint.state)
        normalized_direction = canonical_direction(endpoint.state)
        if state_key not in span_key and normalized_direction == state_key:
            warnings.append(f"QUERY_UNSUPPORTED_{name.upper()}_STATE_CLEARED")
            replacement = endpoint.model_copy(update={"state": ""})
            if name == "source":
                valid_source = replacement
            else:
                valid_target = replacement
    parsed = parsed.model_copy(update={"explicit_context_facets": valid_facets, "source": valid_source, "target": valid_target, "global_requested": explicit_global})
    facets = [QueryFacet(id=f"{query_id}_F{index:03d}", domain=x.domain, notion=x.notion, description=x.description, origin="user", supporting_text_span=x.supporting_text_span) for index, x in enumerate(parsed.explicit_context_facets, 1)]
    support: SpatialSupport | None = None
    if parsed.spatial_reference:
        hint = parsed.spatial_reference.kind_hint
        allowed = {"point", "patch", "watershed", "region", "climate_zone", "global", "unresolved"}
        enrichment_config = PIPELINE["enrichment"]
        unresolved = SpatialSupport(
            kind=hint if hint in allowed else "unresolved",
            name=parsed.spatial_reference.text,
            geometry=None,
            enrichable_study_location_name=None if explicit_global else parsed.spatial_reference.text,
            resolution="global" if explicit_global else "unresolved",
        )
        geocoder = None if explicit_global else NominatimGeocoder(enrichment_config["geocoding"], ROOT)
        support = resolve_spatial_support(unresolved, enrichment_config["watershed_registry_path"], geocoder)
        if support.geometry is None:
            if support.enrichable_study_location_name:
                warnings.append("SPATIAL_REFERENCE_AMBIGUOUS")
            warnings.append("QUERY_ENRICHMENT_SKIPPED_UNRESOLVED_SPATIAL_SUPPORT")
        else:
            try:
                backend = EarthEngineBackend(enrichment_config["earth_engine_project"], enrichment_config["datasets"], enrichment_config["reference_period"])
                derived, raw_enrichment, enrichment_warnings = derive_facets(support, backend, enrichment_config)
                facets.extend(query_facets(query_id, len(facets), derived))
                warnings.extend(enrichment_warnings)
                write_json(artifact_dir / "enrichment" / "enrichment.json", {"status": "complete", "spatial_support": support.model_dump(), "raw": raw_enrichment, "derived_facets": [item.model_dump() for item in facets if item.origin == "derived"], "warnings": enrichment_warnings})
            except Exception as exc:
                warning = f"QUERY_ENRICHMENT_FAILED:{type(exc).__name__}"
                write_json(artifact_dir / "enrichment" / "enrichment.json", {"status": "failed", "spatial_support": support.model_dump(), "error": {"type": type(exc).__name__, "message": str(exc)}, "warnings": [warning]})
                raise RuntimeError(f"{warning}: {exc}") from exc
    spec = QuerySpec(query_id=query_id, mode=_query_mode(parsed), context=QueryContext(spatial_support=support, facets=facets), source=ClaimEndpoint(concept=parsed.source.concept, state=parsed.source.state) if parsed.source else None, target=ClaimEndpoint(concept=parsed.target.concept, state=parsed.target.state) if parsed.target else None, intervention_description=parsed.intervention_description, user_question=question, ambiguities=parsed.ambiguities)
    write_json(artifact_dir / "query_spec.json", spec.model_dump(by_alias=True))
    return spec, warnings


def embed_query(spec: QuerySpec, client: OllamaClient) -> dict[str, list[float] | None]:
    model = QUERY_PIPELINE["embeddings"]["model"]
    dim = QUERY_PIPELINE["embeddings"]["dimension"]
    facets = spec.context.facets
    if facets:
        notions = client.embed([f"Instruct: Retrieve context facets describing the same or a closely related land-atmosphere environmental concept.\n\nQuery:\n{facet_notion_text(x)}" for x in facets], model, dim)
        contents = client.embed([f"Instruct: Retrieve land-atmosphere study contexts with environmentally analogous conditions for transferring scientific mechanisms.\n\nQuery:\n{facet_content_text(x)}" for x in facets], model, dim)
        for facet, notion, content in zip(facets, notions, contents):
            facet.notion_embedding, facet.content_embedding = notion, content
    spatial = ""
    if spec.context.spatial_support:
        spatial = f"Spatial kind: {spec.context.spatial_support.kind}; name: {spec.context.spatial_support.name}\n"
    context_text = spatial + "\n---\n".join(facet_content_text(x) for x in sorted(facets, key=lambda x: (DOMAIN_ORDER.index(x.domain), x.notion, x.id)))
    claim_text = f"Question: {spec.user_question}\nSource: {spec.source.concept + ' | ' + spec.source.state if spec.source else 'NONE'}\nTarget: {spec.target.concept + ' | ' + spec.target.state if spec.target else 'NONE'}"
    texts = [claim_text]
    names = ["claim"]
    if context_text:
        texts.append(f"Instruct: Retrieve land-atmosphere study contexts with environmentally analogous conditions for transferring scientific mechanisms.\n\nQuery:\n{context_text}")
        names.append("context")
    if spec.intervention_description:
        texts.append(f"Intervention: {spec.intervention_description}")
        names.append("intervention")
    vectors = client.embed(texts, model, dim)
    result: dict[str, list[float] | None] = {"claim": None, "context": None, "intervention": None}
    result.update(dict(zip(names, vectors)))
    return result


def facet_pair(query: QueryFacet | Facet, candidate: Facet, alpha: float) -> dict[str, Any]:
    notion = max(0.0, cosine(query.notion_embedding or [], candidate.notion_embedding or []))
    content = max(0.0, cosine(query.content_embedding or [], candidate.content_embedding or []))
    return {"query_facet_id": query.id, "candidate_facet_id": candidate.id, "domain": query.domain, "notion_similarity": notion, "content_similarity": content, "pair_score": alpha * notion + (1 - alpha) * content}


def context_similarity(query_facets: list[QueryFacet | Facet], candidate_facets: list[Facet]) -> dict[str, Any]:
    config = QUERY_PIPELINE["context_retrieval"]
    alpha, missing_lambda = config["notion_weight_alpha"], config["missing_coverage_penalty_lambda"]
    qdomains = {x.domain for x in query_facets}
    matches, missing, domain_scores = [], [], {}
    for domain in sorted(qdomains, key=DOMAIN_ORDER.index):
        qitems = [x for x in query_facets if x.domain == domain]
        citems = [x for x in candidate_facets if x.domain == domain]
        if not citems:
            domain_scores[domain] = {"score": None, "status": "missing_in_candidate"}
            missing.extend(x.id for x in qitems)
            continue
        chosen = []
        for query in qitems:
            pairs = [facet_pair(query, candidate, alpha) for candidate in citems]
            pairs.sort(key=lambda x: (-x["pair_score"], -x["content_similarity"], x["candidate_facet_id"]))
            matches.append(pairs[0])
            chosen.append(pairs[0]["pair_score"])
        domain_scores[domain] = {"score": sum(chosen) / len(chosen), "status": "matched"}
    weights = config["domain_weights"]
    known = [(weights[d], data["score"]) for d, data in domain_scores.items() if data["score"] is not None]
    total_weight = sum(weights[d] for d in qdomains)
    known_weight = sum(weight for weight, _ in known)
    semantic = sum(weight * score for weight, score in known) / known_weight if known_weight else 0.0
    coverage = known_weight / total_weight if total_weight else 0.0
    overall = semantic * (1 - missing_lambda * (1 - coverage))
    return {"semantic_similarity": semantic, "coverage": coverage, "overall_score": overall, "alpha": alpha, "missing_coverage_penalty_lambda": missing_lambda, "domain_scores": domain_scores, "facet_matches": matches, "missing_query_facets": missing}


def retrieve_contexts(spec: QuerySpec, vectors: dict[str, list[float] | None], corpus: Corpus, indexes: FaissIndexes | None = None) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not spec.context.facets:
        return {}, ["CONTEXT_GATE_DISABLED_EMPTY_QUERY_CONTEXT"]
    query_vector = vectors["context"] or []
    top_k = QUERY_PIPELINE["context_retrieval"]["ann_top_k"]
    if indexes:
        candidates = [corpus.contexts[identifier] for identifier, _ in indexes.search("contexts", query_vector, top_k)]
        ann = sorted(((max(0.0, cosine(query_vector, context.retrieval_embedding or [])), context) for context in candidates), key=lambda x: (-x[0], x[1].id))
    else:
        ann = sorted(((max(0.0, cosine(query_vector, context.retrieval_embedding or [])), context) for context in corpus.contexts.values()), key=lambda x: (-x[0], x[1].id))[:top_k]
    reports = {}
    for ann_score, context in ann:
        reports[context.id] = {"context_id": context.id, "paper_id": context.paper_id, "coarse_ann_score": ann_score, "context_similarity": context_similarity(spec.context.facets, corpus.effective_facets(context.id))}
    ordered = sorted(reports.values(), key=lambda x: (-x["context_similarity"]["overall_score"], -x["context_similarity"]["semantic_similarity"], -x["coarse_ann_score"], x["context_id"]))
    retained = ordered[:QUERY_PIPELINE["context_retrieval"]["rerank_top_k"]]
    return {x["context_id"]: x for x in retained}, []


def map_endpoint(endpoint: ClaimEndpoint | None, corpus: Corpus, client: OllamaClient, indexes: FaissIndexes | None = None) -> tuple[list[tuple[str, float]], list[str]]:
    if endpoint is None:
        return [], []
    concept, direction = canonical_concept(endpoint.concept), canonical_direction(endpoint.state)
    exact = [(state.id, 1.0) for state in corpus.states.values() if state.concept == concept and _compatible(direction, state.state)]
    if exact:
        return sorted(exact), []
    vector = client.embed([endpoint.concept], QUERY_PIPELINE["embeddings"]["model"], QUERY_PIPELINE["embeddings"]["dimension"])[0]
    top_k = QUERY_PIPELINE["state_mapping"]["top_k"]
    if indexes:
        pool_k = max(
            top_k * QUERY_PIPELINE["state_mapping"]["exact_fallback_pool_multiplier"],
            QUERY_PIPELINE["state_mapping"]["exact_fallback_pool_minimum"],
        )
        states = [corpus.states[identifier] for identifier, _ in indexes.search("states", vector, pool_k)]
    else:
        states = list(corpus.states.values())
    candidates = sorted(((max(0.0, cosine(vector, state.concept_embedding or [])), state) for state in states if _compatible(direction, state.state)), key=lambda x: (-x[0], x[1].id))[:top_k]
    seeds = [(state.id, score) for score, state in candidates[:QUERY_PIPELINE["state_mapping"]["seed_top_k"]]]
    warnings = []
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < QUERY_PIPELINE["state_mapping"]["candidate_margin"]:
        warnings.append("STATE_MAPPING_AMBIGUOUS")
    return seeds, warnings


def _compatible(query_state: str, candidate_state: str) -> bool:
    if not normalize_text_key(query_state):
        return True
    directional = {"increase", "decrease", "no_detectable_change"}
    return query_state == candidate_state if query_state in directional or candidate_state in directional else normalize_text_key(query_state) == normalize_text_key(candidate_state)


def _claim_state_ids(claim: Claim) -> tuple[str, str]:
    return state_id(claim.from_.concept, claim.from_.state), state_id(claim.to.concept, claim.to.state)


def _conditioning(claim: Claim, spec: QuerySpec, corpus: Corpus) -> dict[str, Any]:
    if not claim.conditioning_facet_ids:
        return {"score": None, "known_coverage": None, "matches": []}
    matches, known = [], []
    alpha = QUERY_PIPELINE["context_retrieval"]["notion_weight_alpha"]
    for identifier in claim.conditioning_facet_ids:
        facet = corpus.facets[identifier]
        query_items = [x for x in spec.context.facets if x.domain == facet.domain]
        if query_items:
            pairs = [facet_pair(item, facet, alpha) for item in query_items]
            best = max(pairs, key=lambda x: (x["pair_score"], x["content_similarity"], x["query_facet_id"]))
            matches.append(best)
            known.append(best["pair_score"])
    return {"score": sum(known) / len(known) if known else None, "known_coverage": len(known) / len(claim.conditioning_facet_ids), "matches": matches}


def rank_claims(spec: QuerySpec, vectors: dict[str, list[float] | None], corpus: Corpus, context_reports: dict[str, dict[str, Any]], source_seeds: list[tuple[str, float]], target_seeds: list[tuple[str, float]], indexes: FaissIndexes | None = None) -> list[dict[str, Any]]:
    source_map, target_map = dict(source_seeds), dict(target_seeds)
    retained_contexts = set(context_reports)
    channel_map: dict[str, set[str]] = defaultdict(set)
    for claim in corpus.claims.values():
        if claim.scope_type == "context" and claim.scope_id in retained_contexts:
            channel_map[claim.id].add("context_scope")
        elif claim.scope_type == "transition" and corpus.transitions[claim.scope_id].from_context_id in retained_contexts:
            channel_map[claim.id].add("context_scope")
        from_id, to_id = _claim_state_ids(claim)
        if from_id in source_map: channel_map[claim.id].add("source_endpoint")
        if to_id in target_map: channel_map[claim.id].add("target_endpoint")
    claim_top_k = QUERY_PIPELINE["mechanism_retrieval"]["claim_semantic_top_k"]
    semantic_claims = [corpus.claims[identifier] for identifier, _ in indexes.search("claims", vectors["claim"] or [], claim_top_k)] if indexes else list(corpus.claims.values())
    semantic = sorted(((max(0.0, cosine(vectors["claim"] or [], claim.claim_embedding or [])), claim) for claim in semantic_claims), key=lambda x: (-x[0], x[1].id))[:claim_top_k]
    for _, claim in semantic: channel_map[claim.id].add("claim_ann")
    transition_scores: dict[str, float] = {}
    if vectors["intervention"]:
        transition_top_k = QUERY_PIPELINE["mechanism_retrieval"]["transition_top_k"]
        transition_items = [corpus.transitions[identifier] for identifier, _ in indexes.search("transitions", vectors["intervention"] or [], transition_top_k)] if indexes else list(corpus.transitions.values())
        ranked_transitions = sorted(((max(0.0, cosine(vectors["intervention"] or [], item.transition_embedding or [])), item) for item in transition_items), key=lambda x: (-x[0], x[1].id))[:transition_top_k]
        transition_scores = {item.id: score for score, item in ranked_transitions}
        for claim in corpus.claims.values():
            if claim.scope_type == "transition" and claim.scope_id in transition_scores: channel_map[claim.id].add("transition_ann")
    semantic_scores = {claim.id: score for score, claim in semantic}
    rows = []
    for claim_id, channels in channel_map.items():
        claim = corpus.claims[claim_id]
        if claim.scope_type == "context": scope_context = claim.scope_id
        else: scope_context = corpus.transitions[claim.scope_id].from_context_id
        context_report = context_reports.get(scope_context)
        context_score = context_report["context_similarity"]["overall_score"] if context_report else None
        conditioning = _conditioning(claim, spec, corpus)
        beta = QUERY_PIPELINE["conditioning"]["weight_beta"]
        applicability = None if context_score is None else context_score if conditioning["score"] is None else (1 - beta) * context_score + beta * conditioning["score"]
        from_id, to_id = _claim_state_ids(claim)
        source_score, target_score = source_map.get(from_id, 0.0), target_map.get(to_id, 0.0)
        if spec.mode == "forward": endpoint_score = source_score
        elif spec.mode == "backward": endpoint_score = target_score
        elif spec.mode == "a_to_b": endpoint_score = (source_score + target_score) / 2
        else: endpoint_score = (source_score + target_score) / (bool(source_seeds) + bool(target_seeds)) if source_seeds or target_seeds else None
        components = {"context": applicability, "mechanism": semantic_scores.get(claim_id, max(0.0, cosine(vectors["claim"] or [], claim.claim_embedding or []))), "intervention": transition_scores.get(claim.scope_id) if claim.scope_type == "transition" and spec.intervention_description else None, "endpoint": endpoint_score}
        weights = QUERY_PIPELINE["claim_ranking"]["weights"]
        present = [(weights[name], score) for name, score in components.items() if score is not None]
        rank = sum(weight * score for weight, score in present) / sum(weight for weight, _ in present)
        coverage = context_report["context_similarity"]["coverage"] if context_report else 0.0
        rows.append({"claim_id": claim_id, "channels": sorted(channels), "R_claim": rank, "A_claim": applicability, "applicability_known": applicability is not None, "context_coverage": coverage, "S_claim_semantic": components["mechanism"], "S_transition": components["intervention"], "S_endpoint": endpoint_score, "conditioning_match": conditioning, "scope_context_id": scope_context})
    rows.sort(key=lambda x: (-x["R_claim"], -x["applicability_known"], -x["context_coverage"], -(x["A_claim"] if x["A_claim"] is not None else -1), -(x["S_endpoint"] if x["S_endpoint"] is not None else -1), x["claim_id"]))
    return rows[:QUERY_PIPELINE["mechanism_retrieval"]["candidate_claim_top_k"]]


def _ancestor_ids(context_id: str, corpus: Corpus) -> set[str]:
    result, pending = set(), [context_id]
    while pending:
        current = pending.pop()
        if current in result: continue
        result.add(current)
        pending.extend(corpus.contexts[current].parent_ids)
    return result


def _coherence_facets(claim: Claim, corpus: Corpus) -> list[Facet]:
    if claim.scope_type == "context":
        return corpus.effective_facets(claim.scope_id)
    transition = corpus.transitions[claim.scope_id]
    common = _ancestor_ids(transition.from_context_id, corpus) & _ancestor_ids(transition.to_context_id, corpus)
    if not common:
        return corpus.effective_facets(transition.from_context_id)
    paper_facets = corpus.facets_by_paper[claim.paper_id]
    return [facet for facet in paper_facets if facet.context_id in common]


def _adjacent_coherence(left: Claim, right: Claim, corpus: Corpus) -> float | None:
    left_facets, right_facets = _coherence_facets(left, corpus), _coherence_facets(right, corpus)
    if not left_facets or not right_facets:
        return None
    forward = context_similarity(left_facets, right_facets)["overall_score"]
    backward = context_similarity(right_facets, left_facets)["overall_score"]
    return 0.5 * (forward + backward)


def _path_score(claim_rows: list[dict[str, Any]], claim_ids: list[str] | None = None, corpus: Corpus | None = None) -> dict[str, Any]:
    applicability = [x["A_claim"] for x in claim_rows if x["A_claim"] is not None]
    a_path = min(applicability) if applicability else None
    mean_rank = sum(x["R_claim"] for x in claim_rows) / len(claim_rows)
    factor = 1 / (1 + QUERY_PIPELINE["path_search"]["path_length_penalty"] * (len(claim_rows) - 1))
    coherence: list[float] = []
    if claim_ids and corpus and len(claim_ids) > 1:
        coherence = [score for left, right in zip(claim_ids, claim_ids[1:]) if (score := _adjacent_coherence(corpus.claims[left], corpus.claims[right], corpus)) is not None]
    c_path = 1.0 if len(claim_rows) == 1 else min(coherence) if coherence else None
    rank = (a_path if a_path is not None else 1.0) * (c_path if c_path is not None else 1.0) * mean_rank * factor
    return {"A_path": a_path, "C_path": c_path, "M_path": mean_rank, "length_factor": factor, "R_path": rank, "context_unknown": a_path is None, "coherence_unknown": c_path is None}


def _query_focused_rows(
    spec: QuerySpec,
    ranked: list[dict[str, Any]],
    limit: int,
    require_known_context: bool,
) -> list[dict[str, Any]]:
    require_known = bool(spec.context.facets) and require_known_context
    selected = []
    for row in ranked:
        if not ({"claim_ann", "transition_ann"} & set(row["channels"])):
            continue
        if require_known and row["A_claim"] is None:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def search_paths(
    spec: QuerySpec,
    corpus: Corpus,
    ranked: list[dict[str, Any]],
    source_seeds: list[tuple[str, float]],
    target_seeds: list[tuple[str, float]],
    anchor_claim_ids: list[str],
) -> list[dict[str, Any]]:
    config = QUERY_PIPELINE["evidence_assembly"]
    require_known = bool(spec.context.facets) and config["require_known_context_for_graph"]
    rows = {x["claim_id"]: x for x in ranked if not require_known or x["A_claim"] is not None}
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, list[str]] = defaultdict(list)
    for claim_id in rows:
        from_id, to_id = _claim_state_ids(corpus.claims[claim_id])
        outgoing[from_id].append(claim_id)
        incoming[to_id].append(claim_id)
    targets = {x[0] for x in target_seeds}
    completed = []
    reverse = spec.mode == "backward"
    if spec.mode == "a_to_b":
        starts = [x[0] for x in source_seeds]
        beam = [{"state": state, "states": [state], "claims": []} for state in starts]
        expansion_depth = QUERY_PIPELINE["path_search"]["max_path_length"]
    else:
        beam = []
        for claim_id in anchor_claim_ids:
            if claim_id not in rows:
                continue
            from_id, to_id = _claim_state_ids(corpus.claims[claim_id])
            states = [to_id, from_id] if reverse else [from_id, to_id]
            item = {"state": states[-1], "states": states, "claims": [claim_id]}
            item.update(_path_score([rows[claim_id]], [claim_id], corpus))
            beam.append(item)
        expansion_depth = QUERY_PIPELINE["path_search"]["max_path_length"] - 1
    for _ in range(expansion_depth):
        expanded = []
        for partial in beam:
            for claim_id in (incoming if reverse else outgoing).get(partial["state"], []):
                if claim_id in partial["claims"]: continue
                from_id, to_id = _claim_state_ids(corpus.claims[claim_id])
                next_state = from_id if reverse else to_id
                if next_state in partial["states"]: continue
                item = {"state": next_state, "states": partial["states"] + [next_state], "claims": partial["claims"] + [claim_id]}
                item.update(_path_score([rows[x] for x in item["claims"]], item["claims"], corpus))
                expanded.append(item)
                if spec.mode != "a_to_b" or next_state in targets:
                    completed.append(item)
        expanded.sort(key=lambda x: (-x["R_path"], len(x["claims"]), tuple(x["claims"])))
        beam = expanded[:QUERY_PIPELINE["path_search"]["beam_width"]]
        if not beam: break
    completed.sort(key=lambda x: (-x["R_path"], len(x["claims"]), tuple(x["claims"])))
    return [{"claim_ids": x["claims"], "state_ids": x["states"], **{k: x[k] for k in ("A_path", "C_path", "M_path", "length_factor", "R_path", "context_unknown", "coherence_unknown")}} for x in completed[:QUERY_PIPELINE["path_search"]["max_paths"]]]


def select_direct_evidence_paths(
    spec: QuerySpec,
    corpus: Corpus,
    ranked: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep query-focused Claims even when exact State wording blocks traversal."""
    config = QUERY_PIPELINE["evidence_assembly"]
    rows = _query_focused_rows(
        spec,
        ranked,
        config["direct_claim_paths"],
        config["require_known_context_for_direct_claims"],
    )
    selected = []
    for row in rows:
        claim_id = row["claim_id"]
        selected.append(
            {
                "claim_ids": [claim_id],
                "state_ids": list(_claim_state_ids(corpus.claims[claim_id])),
                "evidence_lane": "direct",
                **_path_score([row], [claim_id], corpus),
            }
        )
    return selected


def assemble_evidence_paths(
    direct_paths: list[dict[str, Any]],
    graph_paths: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reserve bounded space for both direct findings and graph-organized chains."""
    config = QUERY_PIPELINE["evidence_assembly"]
    assembled = []
    seen: set[tuple[str, ...]] = set()
    for lane, candidates, limit in (
        ("direct", direct_paths, config["direct_claim_paths"]),
        ("graph", graph_paths, config["graph_paths"]),
    ):
        retained = 0
        for path in candidates:
            key = tuple(path["claim_ids"])
            if key in seen:
                continue
            assembled.append({**path, "evidence_lane": lane})
            seen.add(key)
            retained += 1
            if retained >= limit:
                break
    return assembled


SPATIAL_RULES = {
    "local_advection": ["propagate downwind", "downstream propagation", "background wind carries", "advected downwind", "upstream patch", "downstream patch"],
    "patch_gradient_edge": ["patch", "edge", "boundary", "gradient", "heterogeneity", "mosaic", "dry patch", "wet patch", "patch size"],
    "distance_decay": ["distance-decay", "annulus", "annuli", "halo", "within"],
    "orographic_windward_leeward": ["windward", "leeward", "ridge", "mountain barrier", "rain shadow"],
    "moisture_recycling_source_sink": ["precipitationshed", "moisture recycling", "evaporation source", "precipitation sink", "source region", "sink region", "terrestrial evaporation contribution"],
    "remote_teleconnection": ["teleconnection", "remote circulation response", "distant region", "intercontinental", "remote land-use impact"],
}


def spatial_report(claim: Claim, corpus: Corpus) -> dict[str, Any]:
    text = normalize_text_key(claim.description + " " + " ".join(corpus.facets[x].description for x in claim.conditioning_facet_ids if corpus.facets[x].domain == "spatial_configuration"))
    matches = {family: [phrase for phrase in phrases if phrase in text] for family, phrases in SPATIAL_RULES.items()}
    matches = {family: phrases for family, phrases in matches.items() if phrases}
    families = list(matches) or ["unknown"]
    return {"families": families, "allowed": False, "method": None, "matched_phrases": matches, "parsed_scales": parse_spatial_scales(text), "blocking_reasons": ["query spatial data insufficient for relation-family translation"]}


def parse_spatial_scales(text: str) -> list[dict[str, Any]]:
    records = []
    normalized = text.replace("×", "x").replace("–", "-").replace("—", "-")
    occupied: list[tuple[int, int]] = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)\s*(km|m)\b", normalized, re.I):
        records.append({"kind": "rectangle", "value": None, "min": None, "max": None, "x": float(match.group(1)), "y": float(match.group(2)), "unit": match.group(3).lower(), "source_text": match.group(0)})
        occupied.append(match.span())
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*(km|m)\b", normalized, re.I):
        if any(a <= match.start() < b for a, b in occupied): continue
        spatial = QUERY_PIPELINE["spatial"]
        nearby = normalized[
            max(0, match.start() - spatial["relation_text_lookbehind_characters"]):
            match.end() + spatial["relation_text_lookahead_characters"]
        ].lower()
        kind = "distance_band" if any(word in nearby for word in ("annulus", "annuli", "halo")) else "range"
        records.append({"kind": kind, "value": None, "min": float(match.group(1)), "max": float(match.group(2)), "x": None, "y": None, "unit": match.group(3).lower(), "source_text": match.group(0)})
    return records


def _is_comparison_query(spec: QuerySpec) -> bool:
    return bool(re.search(r"\b(?:or|versus|vs\.?)\b", spec.intervention_description or "", re.I))


def retrieve_alternatives(paths: list[dict[str, Any]], ranked: list[dict[str, Any]], corpus: Corpus, spec: QuerySpec) -> list[dict[str, Any]]:
    polarity = {"increase": 1, "decrease": -1, "no_detectable_change": 0}
    row_by_id = {row["claim_id"]: row for row in ranked}
    alternatives: dict[str, dict[str, Any]] = {}
    focal_ids = list(dict.fromkeys(identifier for path in paths[:QUERY_PIPELINE["synthesis"]["top_paths"]] for identifier in path["claim_ids"]))
    order = {"opposite": 0, "null_alternative": 1, "supporting_alternative": 2, "alternative": 3}
    per_focal = QUERY_PIPELINE["contradictions"]["per_focal_claim_top_k"]
    for focal_id in focal_ids:
        focal = corpus.claims[focal_id]
        focal_items = []
        for candidate in corpus.claims.values():
            if candidate.id == focal_id or normalize_text_key(candidate.from_.concept) != normalize_text_key(focal.from_.concept) or normalize_text_key(candidate.to.concept) != normalize_text_key(focal.to.concept):
                continue
            left, right = polarity.get(canonical_direction(focal.to.state)), polarity.get(canonical_direction(candidate.to.state))
            if left is not None and right is not None and left * right < 0: kind = "opposite"
            elif {left, right} == {0, 1} or {left, right} == {0, -1}: kind = "null_alternative"
            elif normalize_text_key(candidate.to.state) == normalize_text_key(focal.to.state): kind = "supporting_alternative"
            else: kind = "alternative"
            focal_items.append({"claim_id": candidate.id, "focal_claim_id": focal_id, "classification": kind, "claim": candidate.model_dump(by_alias=True, exclude={"claim_embedding"}), "scores": row_by_id.get(candidate.id)})
        focal_items.sort(key=lambda x: (order[x["classification"]], -(x["scores"]["R_claim"] if x["scores"] else 0), x["claim_id"]))
        for item in focal_items[:per_focal]:
            alternatives.setdefault(item["claim_id"], item)
    if _is_comparison_query(spec):
        focal_papers = {corpus.claims[claim_id].paper_id for claim_id in focal_ids}
        added = 0
        for row in ranked:
            claim_id = row["claim_id"]
            if claim_id in focal_ids or claim_id in alternatives or row["A_claim"] is None or corpus.claims[claim_id].paper_id not in focal_papers:
                continue
            alternatives[claim_id] = {"claim_id": claim_id, "focal_claim_id": None, "classification": "comparison_candidate", "claim": corpus.claims[claim_id].model_dump(by_alias=True, exclude={"claim_embedding"}), "scores": row}
            added += 1
            if added >= per_focal:
                break
    return list(alternatives.values())


def select_source_blocks(paths: list[dict[str, Any]], corpus: Corpus, query_vector: list[float] | None, alternative_claim_ids: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    result = {}
    limit = QUERY_PIPELINE["synthesis"]["max_source_blocks_per_claim"]
    evidence_config = QUERY_PIPELINE["evidence_selection"]
    priority = evidence_config["section_priority"]
    claim_ids = list(dict.fromkeys([*(identifier for path in paths for identifier in path["claim_ids"]), *(alternative_claim_ids or [])]))
    used_facet_ids: list[str] = []
    for claim_id in claim_ids:
        claim = corpus.claims[claim_id]
        blocks = [corpus.blocks[x] for x in corpus.claims[claim_id].evidence_block_ids if x in corpus.blocks]
        if blocks and claim.claim_embedding and query_vector and all(block.embedding for block in blocks):
            def block_score(block: SourceBlock) -> float:
                section = normalize_text_key(" ".join(block.section_path))
                bonus = evidence_config["results_section_bonus"] if any(name in section for name in ("results", "analysis")) else evidence_config["discussion_section_bonus"] if "discussion" in section else 0.0
                return evidence_config["direct_weight"] * max(0.0, cosine(claim.claim_embedding or [], block.embedding or [])) + evidence_config["query_weight"] * max(0.0, cosine(query_vector, block.embedding or [])) + bonus
            blocks.sort(key=lambda block: (-block_score(block), block.order))
        else:
            blocks.sort(key=lambda block: (-max((value for name, value in priority.items() if name in normalize_text_key(" ".join(block.section_path))), default=0), block.order))
        result[claim_id] = [x.model_dump(exclude={"embedding"}) for x in blocks[:limit]]
        used_facet_ids.extend(claim.conditioning_facet_ids)
    for facet_id in dict.fromkeys(used_facet_ids):
        facet = corpus.facets.get(facet_id)
        if facet is None:
            continue
        blocks = [corpus.blocks[x] for x in facet.evidence_block_ids if x in corpus.blocks]
        blocks.sort(key=lambda block: (-(max(0.0, cosine(query_vector or [], block.embedding or [])) if query_vector and block.embedding else 0.0), block.order))
        if blocks:
            result[facet_id] = [blocks[0].model_dump(exclude={"embedding"})]
    return result


def trim_evidence_package(spec: QuerySpec, paths: list[dict[str, Any]], alternatives: list[dict[str, Any]], blocks: dict[str, list[dict[str, Any]]], corpus: Corpus) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, list[dict[str, Any]]], list[str]]:
    cfg = QUERY_PIPELINE["synthesis"]
    budget, hard_budget = cfg["evidence_input_budget_tokens"], cfg["hard_llm_input_budget_tokens"]
    max_claims = cfg["max_claims"]
    warnings: list[str] = []

    def package_tokens(selected_paths: list[dict[str, Any]], selected_alternatives: list[dict[str, Any]], selected_blocks: dict[str, list[dict[str, Any]]]) -> int:
        claim_ids = list(dict.fromkeys(identifier for path in selected_paths for identifier in path["claim_ids"]))
        payload = {
            "query_spec": _query_spec_payload(spec),
            "paths": selected_paths,
            "claims": [corpus.claims[item_id].model_dump(by_alias=True, exclude={"claim_embedding"}) for item_id in claim_ids],
            "alternatives": selected_alternatives,
            "source_blocks": selected_blocks,
        }
        return token_count(json.dumps(payload, ensure_ascii=False))

    selected_paths: list[dict[str, Any]] = []
    selected_alternatives: list[dict[str, Any]] = []
    selected_blocks: dict[str, list[dict[str, Any]]] = {}
    selected_claim_ids: list[str] = []
    for path in paths[:cfg["top_paths"]]:
        path_claims = list(dict.fromkeys(path["claim_ids"]))
        new_claims = [item_id for item_id in path_claims if item_id not in selected_claim_ids]
        if len(selected_claim_ids) + len(new_claims) > max_claims or any(not blocks.get(item_id) for item_id in path_claims):
            continue
        proposal_blocks = {**selected_blocks, **{item_id: [blocks[item_id][0]] for item_id in new_claims}}
        if package_tokens([*selected_paths, path], selected_alternatives, proposal_blocks) > budget:
            break
        selected_paths.append(path)
        selected_claim_ids.extend(new_claims)
        selected_blocks = proposal_blocks

    if not selected_paths and paths:
        truncated_ids: list[str] = []
        for claim_id in dict.fromkeys(paths[0]["claim_ids"]):
            if len(truncated_ids) >= max_claims or not blocks.get(claim_id):
                continue
            proposal_path = {**paths[0], "claim_ids": [*truncated_ids, claim_id]}
            proposal_blocks = {**selected_blocks, claim_id: [blocks[claim_id][0]]}
            if package_tokens([proposal_path], [], proposal_blocks) > hard_budget:
                break
            truncated_ids.append(claim_id)
            selected_blocks = proposal_blocks
        if truncated_ids:
            selected_paths = [{**paths[0], "claim_ids": truncated_ids}]
            selected_claim_ids = truncated_ids
        warnings.append("SOURCEBLOCK_BUDGET_TRUNCATED")

    primary_blocks = {key: value[:1] for key, value in selected_blocks.items()}
    for claim_id in selected_claim_ids:
        if len(blocks.get(claim_id, [])) > 1:
            proposal = {**selected_blocks, claim_id: blocks[claim_id][:cfg["max_source_blocks_per_claim"]]}
            if package_tokens(selected_paths, selected_alternatives, proposal) <= budget:
                selected_blocks = proposal

    for alternative in alternatives:
        claim_id = alternative["claim_id"]
        new_claim = claim_id not in selected_claim_ids
        if (new_claim and len(selected_claim_ids) >= max_claims) or not blocks.get(claim_id):
            continue
        proposal_blocks = {**selected_blocks, claim_id: [blocks[claim_id][0]]}
        if package_tokens(selected_paths, [*selected_alternatives, alternative], proposal_blocks) > budget and selected_blocks != primary_blocks:
            selected_blocks = dict(primary_blocks)
            proposal_blocks = {**selected_blocks, claim_id: [blocks[claim_id][0]]}
        if package_tokens(selected_paths, [*selected_alternatives, alternative], proposal_blocks) > budget:
            break
        selected_alternatives.append(alternative)
        selected_blocks = proposal_blocks
        if new_claim:
            selected_claim_ids.append(claim_id)
            primary_blocks[claim_id] = [blocks[claim_id][0]]

    conditioning_ids = list(dict.fromkeys(facet_id for claim_id in selected_claim_ids for facet_id in corpus.claims[claim_id].conditioning_facet_ids))
    for facet_id in conditioning_ids:
        if not blocks.get(facet_id):
            continue
        proposal = {**selected_blocks, facet_id: blocks[facet_id][:1]}
        if package_tokens(selected_paths, selected_alternatives, proposal) <= budget:
            selected_blocks = proposal
    return selected_paths, selected_alternatives, selected_blocks, warnings


def synthesize(spec: QuerySpec, context_comparisons: list[dict[str, Any]], paths: list[dict[str, Any]], ranked: list[dict[str, Any]], alternatives: list[dict[str, Any]], blocks: dict[str, list[dict[str, Any]]], corpus: Corpus, client: OllamaClient, artifact_dir: Path) -> tuple[str, dict[str, Any], list[str]]:
    selected_paths = []
    row_by_id = {x["claim_id"]: x for x in ranked}
    for path in paths[:QUERY_PIPELINE["synthesis"]["top_paths"]]:
        selected_paths.append({**path, "claims": [{"claim": corpus.claims[x].model_dump(by_alias=True, exclude={"claim_embedding"}), "scores": row_by_id[x], "spatial_transfer": spatial_report(corpus.claims[x], corpus)} for x in path["claim_ids"]]})
    prompt = _read_prompt("final_synthesis.txt")
    system, user = prompt.split("USER QUESTION\n", 1)
    selected_claim_ids = [x for path in paths[:QUERY_PIPELINE["synthesis"]["top_paths"]] for x in path["claim_ids"]]
    spatial_translation = any(spatial_report(corpus.claims[x], corpus)["allowed"] for x in selected_claim_ids)
    synthesis_config = QUERY_PIPELINE["synthesis"]
    complex_evidence = bool(alternatives) or len(selected_paths) >= synthesis_config["complex_min_paths"] or spatial_translation or len({corpus.claims[x].to.state for x in selected_claim_ids}) >= synthesis_config["complex_min_outcome_states"]
    stage_name = "final_synthesis_complex" if complex_evidence else "final_synthesis"
    llm_config = QUERY_PIPELINE["ollama"]["stages"][stage_name]
    rendered = "USER QUESTION\n" + user
    query_payload = _query_spec_payload(spec)
    query_payload["context"]["facets"] = [facet for facet in query_payload["context"]["facets"] if facet["origin"] == "user"]
    block_references = {
        claim_id: [
            {key: block[key] for key in ("id", "page", "section_path", "block_type") if key in block}
            for block in claim_blocks
        ]
        for claim_id, claim_blocks in blocks.items()
    }
    rendered = rendered.format(question=spec.user_question, query_spec=json.dumps(query_payload), query_context=json.dumps(query_payload["context"]), selected_paths=json.dumps(selected_paths), contradictions=json.dumps(alternatives), source_blocks=json.dumps(block_references))
    output = client.structured(stage="final_synthesis", system=system.removeprefix("SYSTEM\n").strip(), user=rendered, schema=SynthesisOutput, model=QUERY_PIPELINE["ollama"]["model"], temperature=llm_config["temperature"], thinking=llm_config["thinking"], artifact_dir=artifact_dir / "synthesis", paper_id=spec.query_id, input_block_ids=[item["id"] for values in blocks.values() for item in values], retries=llm_config["retries"])
    allowed_claims = {x for path in paths[:QUERY_PIPELINE["synthesis"]["top_paths"]] for x in path["claim_ids"]} | {x["claim_id"] for x in alternatives}
    allowed_facets = {x.id for x in spec.context.facets}
    warnings, valid = [], []
    scientific = {"direct_finding", "transfer_inference", "mechanism", "spatial_guidance"}
    for item in output.direct_answer + output.mechanisms + output.spatial_guidance + output.conditions_and_limitations + output.contradictory_evidence:
        okay = set(item.support_claim_ids) <= allowed_claims and set(item.support_query_facet_ids) <= allowed_facets
        if item.kind in scientific and not item.support_claim_ids: okay = False
        if item.kind == "spatial_guidance" and item.support_query_facet_ids and not any(spatial_report(corpus.claims[c], corpus)["allowed"] for c in item.support_claim_ids): okay = False
        if okay: valid.append(item)
        else: warnings.append("UNSUPPORTED_SYNTHESIS_ITEM")
    valid.extend(context_comparison_limitations(context_comparisons))
    if not any(x.kind in scientific for x in valid):
        warnings.append("FINAL_GROUNDING_VALIDATION_FAILED")
        return "Retrieved evidence could not support a grounded answer to this question.", {"items": [], "limitations": [item.model_dump() for item in output.conditions_and_limitations]}, warnings
    rendered_items = []
    provenance = {}
    for item in valid:
        citations = []
        for claim_id in item.support_claim_ids:
            claim = corpus.claims[claim_id]
            paper = corpus.paper_by_id[claim.paper_id]
            pages = sorted({corpus.blocks[x].page for x in claim.evidence_block_ids if x in corpus.blocks and corpus.blocks[x].page})
            citation = f"{paper.title} ({paper.year or 'n.d.'}), pp. {','.join(map(str, pages))}, Claim {claim_id}"
            citations.append(citation)
            provenance[claim_id] = {"paper_id": paper.id, "title": paper.title, "doi": paper.doi, "source_block_ids": claim.evidence_block_ids, "pages": pages}
        citation_text = f" [{'; '.join(citations)}]" if citations else ""
        rendered_items.append(f"{item.text}{citation_text}")
    return "\n\n".join(rendered_items), {"items": [x.model_dump() for x in valid], "provenance": provenance}, warnings


def run_query(
    question: str,
    query_id: str,
    papers: list[FinalPaper],
    output_root: Path,
    client: OllamaClient | None = None,
    stage_callback: Callable[[str, dict[str, Any]], None] | None = None,
    indexes: FaissIndexes | None = None,
) -> dict[str, Any]:
    client = client or OllamaClient()
    artifact_dir = output_root / query_id
    corpus = Corpus(papers)

    def stage(name: str, details: dict[str, Any]) -> None:
        if stage_callback:
            stage_callback(name, details)

    stage("corpus_loaded", {"papers": len(papers), "contexts": len(corpus.contexts), "facets": len(corpus.facets), "claims": len(corpus.claims), "states": len(corpus.states)})
    spec, warnings = parse_query(question, query_id, client, artifact_dir)
    context_comparisons = context_evidence_comparisons(spec)
    stage("query_parsed", {"mode": spec.mode, "facet_count": len(spec.context.facets), "source": spec.source.model_dump() if spec.source else None, "target": spec.target.model_dump() if spec.target else None, "intervention_description": spec.intervention_description, "warnings": list(warnings)})
    stage("context_evidence_compared", {"comparison_count": len(context_comparisons), "comparisons": context_comparisons})
    vectors = embed_query(spec, client)
    stage("query_embedded", {name: len(vector) if vector else 0 for name, vector in vectors.items()})
    context_reports, more = retrieve_contexts(spec, vectors, corpus, indexes)
    warnings.extend(more)
    stage("contexts_retrieved", {"candidate_count": len(context_reports), "top_contexts": [{"context_id": row["context_id"], "overall_score": row["context_similarity"]["overall_score"], "coverage": row["context_similarity"]["coverage"]} for row in list(context_reports.values())[:QUERY_PIPELINE["reporting"]["top_contexts"]]], "warnings": more})
    source_seeds, more = map_endpoint(spec.source, corpus, client, indexes); warnings.extend(more)
    source_warnings = more
    target_seeds, more = map_endpoint(spec.target, corpus, client, indexes); warnings.extend(more)
    stage("states_mapped", {"source_seeds": source_seeds, "target_seeds": target_seeds, "warnings": source_warnings + more})
    ranked = rank_claims(spec, vectors, corpus, context_reports, source_seeds, target_seeds, indexes)
    stage("claims_ranked", {"candidate_count": len(ranked), "top_claims": [{key: row[key] for key in ("claim_id", "R_claim", "A_claim", "context_coverage", "channels")} for row in ranked[:QUERY_PIPELINE["reporting"]["top_claims"]]]})
    direct_paths = select_direct_evidence_paths(spec, corpus, ranked)
    anchor_rows = _query_focused_rows(
        spec,
        ranked,
        QUERY_PIPELINE["evidence_assembly"]["graph_anchor_claims"],
        QUERY_PIPELINE["evidence_assembly"]["require_known_context_for_graph"],
    )
    graph_paths = search_paths(spec, corpus, ranked, source_seeds, target_seeds, [row["claim_id"] for row in anchor_rows])
    paths = assemble_evidence_paths(direct_paths, graph_paths)
    stage("paths_searched", {"path_count": len(graph_paths), "top_paths": [{key: row[key] for key in ("claim_ids", "R_path", "A_path", "C_path", "context_unknown", "coherence_unknown")} for row in graph_paths[:QUERY_PIPELINE["reporting"]["top_paths"]]]})
    stage("evidence_assembled", {"direct_path_count": len(direct_paths), "graph_path_count": len(graph_paths), "assembled_path_count": len(paths), "assembled_paths": [{"claim_ids": row["claim_ids"], "evidence_lane": row["evidence_lane"]} for row in paths]})
    alternatives = retrieve_alternatives(paths, ranked, corpus, spec)
    stage("alternatives_retrieved", {"count": len(alternatives), "claim_ids": [row["claim_id"] for row in alternatives]})
    selected_blocks = select_source_blocks(paths[:QUERY_PIPELINE["synthesis"]["top_paths"]], corpus, vectors["claim"], [item["claim_id"] for item in alternatives])
    stage("evidence_selected", {"object_count": len(selected_blocks), "source_block_count": sum(len(items) for items in selected_blocks.values()), "object_ids": sorted(selected_blocks)})
    synthesis_paths, synthesis_alternatives, selected_blocks, more = trim_evidence_package(spec, paths, alternatives, selected_blocks, corpus); warnings.extend(more)
    stage("evidence_trimmed", {"path_count": len(synthesis_paths), "alternative_count": len(synthesis_alternatives), "source_block_count": sum(len(items) for items in selected_blocks.values()), "warnings": more})
    answer, synthesis, more = synthesize(spec, context_comparisons, synthesis_paths, ranked, synthesis_alternatives, selected_blocks, corpus, client, artifact_dir); warnings.extend(more)
    stage("answer_synthesized", {"answer_characters": len(answer), "grounded_item_count": len(synthesis.get("items", [])), "provenance_claim_count": len(synthesis.get("provenance", {})), "warnings": more})
    report = {"query_id": query_id, "query_pipeline_version": "0.2-experiment", "query_spec": _query_spec_payload(spec), "context_evidence_comparisons": context_comparisons, "context_gate_disabled_reason": "empty_query_context" if not spec.context.facets else None, "context_candidates": list(context_reports.values()), "state_mapping": {"source_seeds": source_seeds, "target_seeds": target_seeds}, "claim_candidates": ranked, "direct_evidence_paths": direct_paths, "graph_paths": graph_paths, "paths": paths, "contradictions_and_alternatives": alternatives, "synthesis_package": {"paths": synthesis_paths, "contradictions_and_alternatives": synthesis_alternatives}, "source_blocks": selected_blocks, "synthesis": synthesis, "answer": answer, "prompt_versions": {"query_parse": stage_prompt_version("query_parse"), "final_synthesis": stage_prompt_version("final_synthesis")}, "models": {"generation": QUERY_PIPELINE["ollama"]["model"], "embedding": QUERY_PIPELINE["embeddings"]}, "state_alias_registry_version": STATE_ALIASES["version"], "effective_parameters": QUERY_PIPELINE, "warnings": list(dict.fromkeys(warnings))}
    write_json(artifact_dir / "query_report.json", report)
    (artifact_dir / "answer.md").write_text(answer, encoding="utf-8")
    stage("artifacts_written", {"query_report": str(artifact_dir / "query_report.json"), "answer": str(artifact_dir / "answer.md")})
    return report
