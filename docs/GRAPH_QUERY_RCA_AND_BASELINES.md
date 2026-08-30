# ClimateKG graph and query failure audit

## What failed in Q2 and Q3

The saved Qwen responses include both the final response and `message.thinking` whenever thinking was enabled. Query parsing used `think=false`, so there is no hidden reasoning trace for that call. Final synthesis used medium thinking.

### Q2: Rondonia seasons and synoptic wind

This was a retrieval/path-selection failure, not a final-generation failure.

- Query parsing correctly represented Rondonia, rainy/break/dry simulation periods, and synoptic wind as user context.
- The correct paper was retrieved. `P000019_C015` ranked sixth among Context candidates, and all 33 `P000019` Claims appeared among the 200 Claim candidates.
- The parser produced the source `deforestation` with no state. Mapping temporarily formed `state::deforestation::land_cover_change`, then emitted `QUERY_UNSUPPORTED_SOURCE_STATE_CLEARED`.
- Path search retained only four paths: `P000002_CL005`, `P000002_CL004`, `P000002_CL006`, and `P000002_CL004 -> P000002_CL007`. None came from `P000019`.
- The synthesis package therefore contained generic deforestation energy-flux evidence rather than the requested seasonal Rondonia experiment.
- Qwen's thinking explicitly inventoried those four supplied Claims and recognized that rainy/break/dry and synoptic-wind results were absent. The grounded refusal was correct for the evidence it received.

The raw final response is at:

`climatekg/runtime/outputs/indexing_50_medium_map_20260829/paper_queries/Q2_IN_RONDONIA/synthesis/101c6023-9bcd-40af-ac9c-702742db91aa.attempt0.json`

Its `message.thinking` is 18,173 characters. The validated call took 351.74 seconds for 12,611 prompt tokens and 446 generated tokens. A previous timed-out wrapper left a duplicate request running, which explains the two parse and two synthesis artifacts in this query folder.

**Root cause:** an underspecified source endpoint became an exact State seed. When that State was unsupported, the implementation cleared it but still favored generic endpoint-connected paths. Query-specific Context and Claim retrieval succeeded, but it did not control path construction or final evidence selection strongly enough.

### Q3: Rajasthan transfer query

This was a query-representation and evidence-packaging failure followed by a mostly careful synthesis.

- Semi-arid climate, strong daytime heating, and weak monsoon wind became Context Facets.
- `10-15 km alternating irrigated and dry land patches` did not become a spatial-configuration Facet. It was compressed into source `{concept: land cover pattern, state: alternating irrigated and dry land patches}`, losing the numerical scale as a separately matchable condition.
- Enrichment derived BWh and P/PET 0.209, which support the semi-arid description.
- The user supplied `weak monsoon background wind`, while derived ERA5 JJA wind was 3.09 m/s with persistence 0.99. Both were retained, but their tension was not surfaced or adjudicated.
- Selected paths used Claims from `P000005` and `P000014`; `P000019` Claims were candidates but did not enter the leading paths.
- Qwen's thinking correctly recognized the proposed patch scale and the transfer to a new climate regime. Its answer warned that the cited studies did not establish a Rajasthan-specific effect or placement. It could not restore the missing scale match because the evidence package did not contain one.

The raw response is at:

`climatekg/runtime/outputs/indexing_50_medium_map_20260829/paper_queries/Q3_OUT_SEMIARID/synthesis/6926f7cc-cd65-403d-92cc-2c28ed74316b.attempt0.json`

Its `message.thinking` is 18,914 characters. The call took 232.33 seconds for 19,224 prompt tokens and 1,026 generated tokens.

**Root cause:** the parser used one endpoint field for a structured spatial intervention, while enrichment added a potentially inconsistent wind estimate without a conflict-resolution step. The final model reasoned within those limitations.

## Is ClimateKG a graph?

Yes. The stored property graph contains Paper, SourceBlock, StudyContext, ContextFacet, Transition, ScientificClaim, and canonical State nodes with explicit relationships. Scientific mechanism traversal uses a projection in which each Claim is a directed State-to-State edge:

`State -> ScientificClaim -> State`

The full graph also connects each Claim to its scope, conditioning Facets, Paper, and exact supporting SourceBlocks. It is therefore more than a collection of Claim records. However, its current mechanism projection is sparse.

The reproducible audit command is:

```powershell
py -3.13 scripts/audit_graph_topology.py climatekg/runtime/outputs/indexing_50_medium_map_20260829
```

For the 17-paper graph:

| Measure | Result |
|---|---:|
| Scientific Claims | 261 |
| Unique canonical States used by Claims | 367 |
| Weakly connected components | 118 |
| Largest component | 59 States |
| States shared by more than one paper | 7 |
| Exact directed 2-Claim paths | 16 (9 cross-paper) |
| Exact directed 3-Claim paths | 12 (9 cross-paper) |
| Exact directed 4-Claim paths | 5 (4 cross-paper) |

An actual cross-paper three-Claim chain is:

1. `P000015_CL001`: natural vegetation to agriculture -> surface albedo decrease.
2. `P000013_CL001`: surface albedo decrease -> absorbed solar radiation increase.
3. `P000013_CL002`: absorbed solar radiation increase -> surface air temperature increase.

These chains are real, but rare. Most extracted endpoint phrases occur once, so many Claims look independent in the visualizer.

## How State identity works

A State is the pair `(concept, state)`, not either value alone. For example:

`("surface air temperature", "increase") -> state::surface_air_temperature::increase`

`climatekg/canonicalize.py` normalizes case and spacing, then applies only aliases explicitly listed in `config/state_aliases.yaml`. The registry currently has six concept groups and a broader set of direction aliases. Thus `near-surface temperature` can become `surface air temperature`, and `warmer` can become `increase`.

Unknown scientific wording remains distinct. Embedding similarity does not silently merge States, and `State.aliases` is currently emitted as an empty list rather than retaining observed raw variants. This conservative rule prevents scientifically wrong merges, but it also causes under-connection. Communities were not part of ClimateKG's original query pipeline.

## Baseline design

The comparison uses one deduplicated corpus: the 17 staged papers plus the heterogeneous-patch paper. References and page furniture are excluded, while SourceBlock and page markers remain in the exported text.

- **Plain RAG:** chunks cleaned SourceBlock text, embeds chunks, retrieves passages, and asks the same Qwen model for a cited answer. It does not use ClimateKG Claims or entities.
- **Entity-adapted GraphRAG:** maps canonical States to GraphRAG entities and ScientificClaims to directed relationships. Claim relation type, StudyContext identifier, conditioning ContextFacets, Paper, and SourceBlock evidence remain attached. It uses Microsoft GraphRAG 3.1.1's pinned hierarchical Leiden implementation to form communities, then retrieves communities and their Claim relationships for answer synthesis.

Both answer generators explicitly request the repository's configured 32,768-token Ollama context. An interrupted pilot exposed that Ollama otherwise loaded this model with a 4,096-token default, which could silently truncate the eight retrieved passages.

GraphRAG communities are thematic clusters. They do not by themselves validate a scientific mechanism path or make incompatible StudyContexts composable. ClimateKG's Context gating remains a separate scientific constraint.

Runtime results are written under `climatekg/runtime/outputs/baseline_comparison_20260830_v2/` and are intentionally excluded from Git because they contain embeddings and generated output. The directory without `_v2` records a diagnosed concurrent-writer failure from the first attempt and must not be used for evaluation.
