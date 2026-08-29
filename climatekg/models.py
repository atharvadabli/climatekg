from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Domain = Literal["spatial_configuration", "land_surface", "hydrology", "atmosphere", "climate", "substrate_terrain", "other"]
BlockType = Literal["title", "abstract", "heading", "paragraph", "list", "table", "table_caption", "figure_caption", "equation", "footnote", "reference", "other"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Paper(StrictModel):
    id: str
    title: str
    source_file: str
    doi: str | None = None
    year: int | None = None


class SpatialSupport(StrictModel):
    kind: Literal["point", "patch", "watershed", "region", "climate_zone", "global", "unresolved"]
    name: str
    geometry: dict[str, Any] | None = None
    enrichable_study_location_name: str | None = None
    resolution: Literal["exact", "approximate", "named_region", "global", "unresolved"]


class Context(StrictModel):
    id: str
    paper_id: str
    parent_ids: list[str] = Field(default_factory=list)
    label: str
    aliases: list[str] = Field(default_factory=list)
    spatial_support: SpatialSupport | None = None
    evidence_block_ids: list[str] = Field(default_factory=list)
    retrieval_embedding: list[float] | None = None


class ProvenanceSource(StrictModel):
    type: str | None = None
    id: str | None = None
    dataset: str | None = None
    version: str | None = None
    method: str | None = None
    temporal_window: str | None = None
    geometry_hash: str | None = None


class Facet(StrictModel):
    id: str
    context_id: str
    domain: Domain
    notion: str
    description: str
    origin: Literal["reported", "derived"]
    source: ProvenanceSource | None = None
    evidence_block_ids: list[str] = Field(default_factory=list)
    notion_embedding: list[float] | None = None
    content_embedding: list[float] | None = None


class Transition(StrictModel):
    id: str
    paper_id: str
    from_context_id: str
    to_context_id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    evidence_block_ids: list[str] = Field(default_factory=list)
    transition_embedding: list[float] | None = None


class ClaimEndpoint(StrictModel):
    concept: str
    state: str


class Claim(StrictModel):
    id: str
    paper_id: str
    scope_type: Literal["context", "transition"]
    scope_id: str
    from_: ClaimEndpoint = Field(alias="from", serialization_alias="from")
    to: ClaimEndpoint
    relation: Literal["causal", "associative"]
    description: str
    evidence_role: Literal["OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT", "CITED_BACKGROUND", "HYPOTHESIS_OR_PROPOSAL"]
    conditioning_facet_ids: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str] = Field(default_factory=list)
    claim_embedding: list[float] | None = None


class State(StrictModel):
    id: str
    concept: str
    state: str
    aliases: list[str] = Field(default_factory=list)
    concept_embedding: list[float] | None = None


class SourceBlock(StrictModel):
    id: str
    paper_id: str
    order: int
    page: int | None = None
    section_path: list[str] = Field(default_factory=list)
    block_type: BlockType
    text: str
    source_locator: dict[str, Any]
    oversize_hard_split: bool = False
    embedding: list[float] | None = None


class FinalPaper(StrictModel):
    schema_version: str = "0.1"
    pipeline_version: str = "0.1"
    paper: Paper
    source_blocks: list[SourceBlock]
    contexts: list[Context]
    facets: list[Facet]
    transitions: list[Transition]
    claims: list[Claim]
    states: list[State]
    evidence_links: list[dict[str, Any]] = Field(default_factory=list)
    unresolved_conflicts: list[dict[str, Any] | str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> "FinalPaper":
        blocks = {x.id: x for x in self.source_blocks}
        contexts = {x.id: x for x in self.contexts}
        facets = {x.id for x in self.facets}
        transitions = {x.id: x for x in self.transitions}
        for context in self.contexts:
            if context.paper_id != self.paper.id or not context.label.strip() or any(p not in contexts for p in context.parent_ids):
                raise ValueError(f"invalid Context references: {context.id}")
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(context_id: str) -> None:
            if context_id in visiting:
                raise ValueError(f"Context inheritance cycle at {context_id}")
            if context_id in visited:
                return
            visiting.add(context_id)
            for parent_id in contexts[context_id].parent_ids:
                visit(parent_id)
            visiting.remove(context_id)
            visited.add(context_id)

        for context_id in contexts:
            visit(context_id)
        for facet in self.facets:
            if facet.context_id not in contexts or (facet.origin == "reported" and not facet.evidence_block_ids):
                raise ValueError(f"invalid Facet references: {facet.id}")
        for transition in self.transitions:
            if transition.paper_id != self.paper.id or transition.from_context_id not in contexts or transition.to_context_id not in contexts or transition.from_context_id == transition.to_context_id or not transition.evidence_block_ids:
                raise ValueError(f"invalid Transition references: {transition.id}")
        for claim in self.claims:
            scopes = set(contexts) if claim.scope_type == "context" else transitions
            if claim.scope_id not in scopes or any(x not in facets for x in claim.conditioning_facet_ids):
                raise ValueError(f"invalid Claim references: {claim.id}")
            scoped_contexts = {claim.scope_id} if claim.scope_type == "context" else {
                transitions[claim.scope_id].from_context_id,
                transitions[claim.scope_id].to_context_id,
            }
            reachable_contexts: set[str] = set()
            pending = list(scoped_contexts)
            while pending:
                context_id = pending.pop()
                if context_id not in reachable_contexts:
                    reachable_contexts.add(context_id)
                    pending.extend(contexts[context_id].parent_ids)
            if any(next(f.context_id for f in self.facets if f.id == facet_id) not in reachable_contexts for facet_id in claim.conditioning_facet_ids):
                raise ValueError(f"unreachable conditioning Facet on Claim: {claim.id}")
            if not claim.evidence_block_ids or any(x not in blocks for x in claim.evidence_block_ids):
                raise ValueError(f"invalid Claim evidence: {claim.id}")
            if all(blocks[x].block_type == "reference" for x in claim.evidence_block_ids):
                raise ValueError(f"reference-only Claim evidence: {claim.id}")
        return self


class QueryFacet(StrictModel):
    id: str
    domain: Domain
    notion: str
    description: str
    origin: Literal["user", "provided_dataset", "derived"]
    source: ProvenanceSource | None = None
    supporting_text_span: str | None = None
    notion_embedding: list[float] | None = None
    content_embedding: list[float] | None = None


class QueryContext(StrictModel):
    spatial_support: SpatialSupport | None = None
    facets: list[QueryFacet] = Field(default_factory=list)


class QuerySpec(StrictModel):
    query_id: str
    mode: Literal["forward", "backward", "a_to_b", "global"]
    context: QueryContext
    source: ClaimEndpoint | None = None
    target: ClaimEndpoint | None = None
    intervention_description: str | None = None
    user_question: str
    ambiguities: list[str] = Field(default_factory=list)


class AnswerItem(StrictModel):
    kind: Literal["direct_finding", "transfer_inference", "mechanism", "spatial_guidance", "limitation"]
    text: str
    support_claim_ids: list[str] = Field(default_factory=list)
    support_query_facet_ids: list[str] = Field(default_factory=list)


class Answer(StrictModel):
    answer: str
    items: list[AnswerItem]
    limitations: list[str] = Field(default_factory=list)
