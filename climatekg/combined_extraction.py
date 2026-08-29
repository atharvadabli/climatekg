from __future__ import annotations

from dataclasses import dataclass

from .extraction_models import (
    MapContext,
    MapTransition,
    SmallPaperClaim,
    SmallPaperExtraction,
    SmallPaperExtractionV4,
    SmallPaperFacet,
    SmallPaperClaimV4,
)
from .models import SourceBlock


@dataclass(frozen=True)
class EvidenceCatalog:
    handle_to_block_id: dict[str, str]

    @classmethod
    def from_blocks(cls, blocks: list[SourceBlock]) -> "EvidenceCatalog":
        if not blocks:
            raise ValueError("combined extraction requires at least one cleaned non-reference SourceBlock")
        width = max(3, len(str(len(blocks))))
        return cls({f"E{index:0{width}d}": block.id for index, block in enumerate(blocks, 1)})

    @property
    def handles(self) -> list[str]:
        return list(self.handle_to_block_id)

    def resolve(self, handles: list[str], label: str) -> list[str]:
        unknown = [handle for handle in handles if handle not in self.handle_to_block_id]
        if unknown:
            raise ValueError(f"{label} references unknown evidence handles: {unknown}")
        return [self.handle_to_block_id[handle] for handle in handles]

    def as_rows(self) -> list[dict[str, str]]:
        return [{"handle": handle, "source_block_id": block_id} for handle, block_id in self.handle_to_block_id.items()]


def render_evidence_catalog(blocks: list[SourceBlock], catalog: EvidenceCatalog) -> str:
    block_to_handle = {block_id: handle for handle, block_id in catalog.handle_to_block_id.items()}
    rendered = []
    for block in blocks:
        section = " > ".join(block.section_path)
        rendered.append(
            f"[{block_to_handle[block.id]}] page={block.page} section={section} type={block.block_type}\n{block.text}"
        )
    return "\n\n".join(rendered)


def flatten_small_paper_v4(result: SmallPaperExtractionV4, catalog: EvidenceCatalog) -> SmallPaperExtraction:
    contexts = [
        MapContext(
            temp_id=context.temp_id,
            label=context.label,
            parent_temp_ids=context.parent_temp_ids,
            split_reason=context.split_reason,
            aliases=context.aliases,
            spatial_support=context.spatial_support,
            evidence_block_ids=catalog.resolve(context.evidence_handles, f"Context {context.temp_id}"),
            facet_seed_block_ids=catalog.resolve(context.facet_seed_handles, f"Context {context.temp_id}"),
        )
        for context in result.contexts
    ]

    facets: list[SmallPaperFacet] = []
    facet_ids: dict[tuple[str, str], str] = {}
    for context in result.contexts:
        for facet in context.facets:
            key = (context.temp_id, facet.facet_key)
            if key in facet_ids:
                raise ValueError(f"Context {context.temp_id} contains duplicate facet_key {facet.facet_key}")
            facet_id = f"F{len(facets) + 1}"
            facet_ids[key] = facet_id
            facets.append(SmallPaperFacet(
                temp_id=facet_id,
                context_temp_id=context.temp_id,
                domain=facet.domain,
                notion=facet.notion,
                description=facet.description,
                evidence_block_ids=catalog.resolve(facet.evidence_handles, f"Facet {context.temp_id}/{facet.facet_key}"),
            ))

    transitions = [
        MapTransition(
            temp_id=transition.temp_id,
            from_context_temp_id=transition.from_context_temp_id,
            to_context_temp_id=transition.to_context_temp_id,
            label=transition.label,
            aliases=transition.aliases,
            description=transition.description,
            evidence_block_ids=catalog.resolve(transition.evidence_handles, f"Transition {transition.temp_id}"),
            claim_seed_block_ids=catalog.resolve(transition.claim_seed_handles, f"Transition {transition.temp_id}"),
        )
        for transition in result.transitions
    ]

    claims: list[SmallPaperClaim] = []
    for context in result.contexts:
        for claim in context.claims:
            claims.append(_flatten_claim(claim, "context", context.temp_id, facet_ids, catalog, len(claims) + 1))
    for transition in result.transitions:
        for claim in transition.claims:
            claims.append(_flatten_claim(claim, "transition", transition.temp_id, facet_ids, catalog, len(claims) + 1))

    return SmallPaperExtraction(
        contexts=contexts,
        facets=facets,
        transitions=transitions,
        claims=claims,
        ambiguities=result.ambiguities,
    )


def _flatten_claim(
    claim: SmallPaperClaimV4,
    scope_type: str,
    scope_temp_id: str,
    facet_ids: dict[tuple[str, str], str],
    catalog: EvidenceCatalog,
    ordinal: int,
) -> SmallPaperClaim:
    conditioning_ids = []
    for reference in claim.conditioning_facets:
        key = (reference.context_temp_id, reference.facet_key)
        if key not in facet_ids:
            raise ValueError(
                f"Claim CL{ordinal} references unknown facet {reference.context_temp_id}/{reference.facet_key}"
            )
        conditioning_ids.append(facet_ids[key])
    return SmallPaperClaim(
        temp_id=f"CL{ordinal}",
        scope_type=scope_type,
        scope_temp_id=scope_temp_id,
        **{"from": claim.from_.model_dump()},
        to=claim.to,
        relation=claim.relation,
        description=claim.description,
        evidence_role=claim.evidence_role,
        conditioning_facet_temp_ids=conditioning_ids,
        evidence_block_ids=catalog.resolve(claim.evidence_handles, f"Claim CL{ordinal}"),
    )
