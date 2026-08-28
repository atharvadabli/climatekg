# Complete-Setting Hierarchy: Downstream Validation

## Purpose

This run tested whether the redesigned paper map can pass through the existing indexing and query pipeline without adding a later LLM cleanup stage.

Test paper: *The Effect of Land Surface Heterogeneity and Background Wind on Shallow Cumulus Clouds and the Transition to Deeper Convection*.

## Accepted paper map

The accepted map is:

`climatekg/runtime/outputs/map_prompt_corpus_v10/heterogeneity_factorial/extraction/map/paper_map.json`

Its readable tree is:

`climatekg/runtime/outputs/map_prompt_corpus_v10/heterogeneity_factorial/extraction/map/paper_map.tree.txt`

It contains:

- 26 Contexts;
- one common LES root;
- homogeneous and heterogeneous branches;
- patch-size family parents only where they have complete child runs;
- complete leaves such as `HET14U0`, `HET14U1`, `HET14U2`, `HET7U0.5`, and doubled-amplitude runs;
- 4 explicit comparisons.

The earlier v8 map had 34 Contexts. The v10 prompt removed standalone wind-factor leaves such as `U0`, `U1`, and `U2`. This reduced Facet calls by eight without removing complete experiments.

Temporary `CM###` inventory IDs are now used only for referential coverage. They are removed deterministically if the model copies them into scientific aliases. Generated label similarity is not a runtime validation gate.

## Downstream indexing result

Final artifact:

`climatekg/runtime/outputs/hierarchy_e2e_het_v10/final/final_paper.json`

Full timing and count trace:

`climatekg/runtime/outputs/hierarchy_e2e_het_v10/stage_trace.json`

| Stage | Time | Output |
|---|---:|---:|
| Permanent map | 0.003 s | 26 Contexts, 4 Transitions |
| Facet extraction | 1,036.385 s | 59 Facets, 1 hint |
| Claim extraction | 1,161.088 s | 18 Claims |
| Context reconciliation | 143.616 s | 26 Contexts, 0 unresolved |
| Paper consolidation | 83.273 s | no merges or warnings |
| State canonicalization | 0.008 s | 32 States |
| Embeddings | 14.457 s | all final objects embedded |

Total replay time was about 40.7 minutes. Most time was local Qwen inference, not validation.

Every LLM request, raw response, envelope, and validated object is stored under the corresponding `extraction` subfolder.

## Inheritance check

The existing downstream implementation already handled Context hierarchy correctly, so its scientific algorithms did not need redesign.

For example, `HET14U1` has 5 direct Facets and 16 effective Facets. Its effective set includes:

- common LES domain and resolution;
- surface heat-flux pattern and contrast;
- the heterogeneous-surface branch;
- the 14.4 km patch-size parent;
- the run-specific 1 m/s wind, convergence-zone, cloud-advection, and moisture details.

`HET14U0`, `HET14U2`, `HET14U1_Ax2`, and `HET7U0.5` showed the same parent-to-child inheritance behavior.

## Query validation

First-run reports, which exposed the path failure, are under:

`climatekg/runtime/outputs/hierarchy_e2e_het_v10/queries`

The full revised four-query reports are under:

`climatekg/runtime/outputs/hierarchy_e2e_het_v10/queries_v2`

Final synthesis-v4 checks for the two context-dependent answers are under:

`climatekg/runtime/outputs/hierarchy_e2e_het_v10/queries_v4`

The revised run made two bounded changes after observed failures:

1. State mapping uses all 5 configured candidates instead of discarding tied candidates after 3.
2. A blank-state target containing multiple outcomes joined by `and` becomes a forward query. This avoids searching for one nonexistent compound State.
3. Final synthesis receives complete Claim descriptions but only SourceBlock provenance references, not raw passage text. Raw selected passages remain in `query_report.json`. This prevents the writer from turning an unrelated sentence in a supporting block into a relationship absent from the selected Claims.

### Generic query

Question: `How does land-surface heterogeneity affect boundary-layer convection and cloud development?`

Result: 4 paths, 5 grounded answer items, 4 cited Claims. Context gating was correctly disabled because the user supplied no environmental Context.

### 14.4 km, zero-wind query

Question: `Under a heterogeneous chessboard surface with 14.4 km patches and zero background wind, how does land-surface heterogeneity affect the transition from shallow to deep convection?`

Result: 26 Context candidates, 4 context-gated paths, 4 grounded answer items, and 4 cited Claims. The answer retrieves the large-patch deep-convection finding plus secondary-circulation and boundary-layer mechanisms.

The final v4 check produced 5 grounded items with no unsupported wind-response statement.

### Wind comparison query

Question: `For a heterogeneous surface with 14.4 km patches, how does increasing background wind from 0 to 1 m/s change the secondary circulation and moisture distribution?`

Result: 5 paths, 10 grounded answer items, and 5 cited Claims. Retrieved effects include broken circulation symmetry, a downwind convergence-zone shift, increased low-level moisture variability, cloud advection, and maintained convection transition.

The final v4 check keeps the comparison at exactly 0 to 1 m/s and does not invent a higher-wind threshold.

### Remaining failed query

Question: `Under zero background wind, how does increasing heterogeneous patch size from 2.4 km to 4.8 km influence deep convection?`

Result: 0 paths. The system correctly returned no grounded answer.

This is an indexing recall problem, not a reason to weaken path search. The graph contains:

- patch size to moisture-pool formation;
- small patch size to stronger dry-patch updrafts;
- large surface heterogeneity to deep convection;
- moisture-contrast amplitude to deep convection.

It does not contain a directly supported Claim connecting the specific 2.4-to-4.8 km comparison to deep convection. The next fix should therefore be evaluated in the Claim extraction prompt and evidence bundle for explicit comparison outcomes. A later LLM bridge or invented intermediate mechanism would be scientifically incorrect.

The smallest candidate prompt addition for a three-paper regression is:

> For a comparison target, first identify what differs between its start and end settings. Extract each paper-reported response to that difference before extracting secondary mechanisms. Represent the changed quantity as the source endpoint and the reported response as the target endpoint.

This wording is not yet active. It must recover the missing direct comparison Claim without duplicating Claims, turning outcome-defined groups into causes, or reducing recall on the irrigation and forestry regression papers.

## Neo4j status

The graph client now accepts optional connection parameters, and `scripts/validate_single_paper_graph.py` performs initialization, ingestion, count verification, and a full graph-to-`FinalPaper` round trip.

The main Neo4j graph on ports `7474/7687` was not modified because its `P000001` is the wind-farm paper. Starting an isolated container on `7475/7688` was rejected by the execution policy because it requires escalated Docker access, persistent mounts, and exposed ports.

When Docker access is explicitly allowed, run:

```powershell
.\scripts\run_hierarchy_graph_validation.ps1
```

This starts the isolated graph, verifies a full Neo4j round trip, and runs the four queries from graph-reloaded data under `queries_graph`.

## Decision

Keep the complete-setting hierarchy and the existing downstream inheritance algorithms. Keep referential validation cheap. Do not add a generic map-improvement call or a query-time mechanism bridge.

The next scientific task is a focused three-paper Claim-extraction regression for explicit comparison outcomes, followed by the isolated Neo4j round trip and the same four queries through `Neo4jHttp.read_corpus()`.
