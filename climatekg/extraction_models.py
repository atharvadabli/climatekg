from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ClaimEndpoint, Domain, SpatialSupport, StrictModel


class CompleteOutputModel(StrictModel):
    """Expose every response field as required to constrained generation."""

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema)
        if "properties" in schema:
            schema["required"] = list(schema["properties"])
        return schema


class MapContext(CompleteOutputModel):
    temp_id: str
    label: str
    parent_temp_ids: list[str] = Field(default_factory=list)
    split_reason: Literal["separate_reported_finding", "sign_or_null_reversal", "misleading_parent_scope", "explicit_transition_state"] | None = None
    aliases: list[str] = Field(default_factory=list)
    spatial_support: SpatialSupport | None = None
    evidence_block_ids: list[str]
    facet_seed_block_ids: list[str] = Field(default_factory=list)


class MapTransition(CompleteOutputModel):
    temp_id: str
    from_context_temp_id: str
    to_context_temp_id: str
    label: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    evidence_block_ids: list[str]
    claim_seed_block_ids: list[str] = Field(default_factory=list)


class PaperMap(CompleteOutputModel):
    contexts: list[MapContext]
    transitions: list[MapTransition]
    context_mention_resolution: dict[str, str] = Field(default_factory=dict)
    global_claim_seed_block_ids: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class ScoutMention(StrictModel):
    name: str
    description: str
    block_ids: list[str]


class SectionScout(CompleteOutputModel):
    context_mentions: list[ScoutMention] = Field(default_factory=list)
    location_mentions: list[ScoutMention] = Field(default_factory=list)
    comparison_mentions: list[ScoutMention] = Field(default_factory=list)
    facet_seed_block_ids: list[str] = Field(default_factory=list)
    claim_seed_block_ids: list[str] = Field(default_factory=list)
    cross_references: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class FacetCandidate(StrictModel):
    domain: Domain
    notion: str
    description: str
    evidence_block_ids: list[str]


class FacetBatch(StrictModel):
    context_id: str
    facets: list[FacetCandidate]
    unmapped_context_hints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class ClaimCandidate(StrictModel):
    from_: ClaimEndpoint = Field(alias="from", serialization_alias="from")
    to: ClaimEndpoint
    relation: Literal["causal", "associative"]
    description: str
    evidence_role: Literal["OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT", "CITED_BACKGROUND", "HYPOTHESIS_OR_PROPOSAL"]
    conditioning_facet_ids: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str]


class ClaimBatch(StrictModel):
    scope_id: str
    claims: list[ClaimCandidate]
    unmapped_context_hints: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)


class SmallPaperFacet(CompleteOutputModel):
    temp_id: str
    context_temp_id: str
    domain: Domain
    notion: str
    description: str
    evidence_block_ids: list[str]


class SmallPaperClaim(CompleteOutputModel):
    temp_id: str
    scope_type: Literal["context", "transition"]
    scope_temp_id: str
    from_: ClaimEndpoint = Field(alias="from", serialization_alias="from")
    to: ClaimEndpoint
    relation: Literal["causal", "associative"]
    description: str
    evidence_role: Literal["OWN_RESULT", "AUTHORS_INTERPRETATION_OF_OWN_RESULT", "CITED_BACKGROUND", "HYPOTHESIS_OR_PROPOSAL"]
    conditioning_facet_temp_ids: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str]


class SmallPaperExtraction(CompleteOutputModel):
    contexts: list[MapContext]
    facets: list[SmallPaperFacet]
    transitions: list[MapTransition]
    claims: list[SmallPaperClaim]
    ambiguities: list[str] = Field(default_factory=list)


class ConsolidationDecision(StrictModel):
    object_type: Literal["context", "facet", "claim"]
    left_id: str
    right_id: str
    decision: Literal["SAME", "DISTINCT", "PARENT_CHILD", "UNCERTAIN"]
    parent_id: str | None = None
    child_id: str | None = None


class ConsolidationBatch(StrictModel):
    decisions: list[ConsolidationDecision]
    unresolved_conflicts: list[str] = Field(default_factory=list)


class ContextHintDecision(StrictModel):
    hint_id: str
    action: Literal["ATTACH_TO_EXISTING_CONTEXT", "ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT", "IGNORE_AS_NOT_A_CONTEXT", "UNRESOLVED"]
    existing_context_id: str | None = None
    parent_context_id: str | None = None
    new_context_label: str | None = None
    aliases: list[str] = Field(default_factory=list)
    affected_claim_ids: list[str] = Field(default_factory=list)
    evidence_block_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_action_fields(self) -> "ContextHintDecision":
        if self.action == "ATTACH_TO_EXISTING_CONTEXT" and not self.existing_context_id:
            raise ValueError("ATTACH_TO_EXISTING_CONTEXT requires existing_context_id")
        if self.action in ("ADD_CHILD_CONTEXT", "ADD_INDEPENDENT_CONTEXT"):
            if not self.new_context_label or not self.evidence_block_ids:
                raise ValueError(f"{self.action} requires new_context_label and evidence_block_ids")
        if self.action == "ADD_CHILD_CONTEXT" and not self.parent_context_id:
            raise ValueError("ADD_CHILD_CONTEXT requires parent_context_id")
        return self


class ContextReconciliationBatch(StrictModel):
    decisions: list[ContextHintDecision]
    ambiguities: list[str] = Field(default_factory=list)


class ParsedEndpoint(StrictModel):
    concept: str
    state: str
    supporting_text_span: str


class ParsedQueryFacet(StrictModel):
    domain: Domain
    notion: str
    description: str
    supporting_text_span: str


class ParsedQueryFacetBatch(StrictModel):
    explicit_context_facets: list[ParsedQueryFacet]


class SpatialReference(StrictModel):
    text: str
    kind_hint: str | None = None


class ParsedQuery(StrictModel):
    source: ParsedEndpoint | None = None
    target: ParsedEndpoint | None = None
    intervention_description: str | None = None
    explicit_context_facets: list[ParsedQueryFacet] = Field(default_factory=list)
    spatial_reference: SpatialReference | None = None
    global_requested: bool = False
    ambiguities: list[str] = Field(default_factory=list)


class SynthesisItem(StrictModel):
    text: str
    support_claim_ids: list[str]
    support_query_facet_ids: list[str]
    kind: Literal["direct_finding", "transfer_inference", "mechanism", "spatial_guidance", "limitation"]


class SynthesisOutput(StrictModel):
    direct_answer: list[SynthesisItem]
    mechanisms: list[SynthesisItem]
    spatial_guidance: list[SynthesisItem]
    conditions_and_limitations: list[SynthesisItem]
    contradictory_evidence: list[SynthesisItem]
