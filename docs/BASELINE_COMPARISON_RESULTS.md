# Shared-corpus baseline comparison results

## Run

The completed run is under:

`climatekg/runtime/outputs/baseline_comparison_20260830_v2/`

It contains 18 deduplicated papers: 17 staged-index papers plus the heterogeneous-patch paper. Both baselines used `qwen3-embedding:4b`, `qwen3.6:27b`, and a 32,768-token Ollama context.

| Index | Papers | Indexed objects | Build time |
|---|---:|---:|---:|
| Plain RAG | 18 | 287 passage chunks | 54.26 s |
| Entity-adapted GraphRAG | 18 | 399 States, 279 Claims, 134 communities | 16.87 s |

GraphRAG produced only level-0 communities. This is expected for the current sparse graph: most connected components are already smaller than the configured maximum community size, so hierarchical Leiden has little hierarchy to add.

| Query | Plain RAG | GraphRAG |
|---|---:|---:|
| Q1: 14.4 km heterogeneous patches | 27.63 s | 38.34 s |
| Q2: Rondonia season and wind response | 36.35 s | 55.94 s |
| Q3: transfer to semi-arid Rajasthan | 40.30 s | 40.76 s |

These are single local runs, not statistically stable latency benchmarks.

## Q1: heterogeneous 14.4 km patches

Plain RAG's leading three passages came from the correct heterogeneous-patch paper. Its answer preserved zero background wind, 14.4 km patches, secondary circulations, deeper clouds, and precipitation.

GraphRAG selected all four expected extracted Claims (`P000001_CL001` through `P000001_CL004`) from the namespaced heterogeneous paper. It clearly described the directed mechanism: patch-scale heat-flux contrast -> secondary circulation and stronger thermals -> deep convection and precipitation. It also preserved the counterintuitive reduction of near-surface dry-wet temperature contrast by horizontal mixing.

One GraphRAG sentence confused a HET7 label while discussing the 14.4 km case. This is a synthesis error and shows that preserving Claim identifiers is necessary but does not guarantee perfect reading of experimental labels embedded in evidence text.

## Q2: Rondonia seasons and synoptic wind

Both baselines answered the question substantially better than the existing ClimateKG query run.

Plain RAG retrieved seven of its eight passages from the correct Rondonia paper. It separated rainy, break, and dry periods and distinguished original from weakened synoptic wind.

GraphRAG selected 18 Claims, all from `P000019`. Its answer preserved:

- negligible rainy-season land-cover influence under both wind settings;
- break-period mesoscale circulation without rain under original wind;
- enhanced low cloud but little rain under wind reduced by a factor of ten;
- dry-season localized deep convection and broader rain coverage during weak-wind periods;
- loss of the land-cover signature when dry-season synoptic winds strengthened.

This comparison isolates the ClimateKG failure. The ClimateKG query had already retrieved all 33 `P000019` Claims, but exact source-State path construction retained only generic `P000002` deforestation energy-flux paths. The evidence existed and was retrievable; State seeding and final path selection removed it before synthesis.

## Q3: transfer to Rajasthan

Plain RAG returned general irrigation, roughness, monsoon, model-resolution, and water-source considerations. It did not retrieve the heterogeneous-patch paper and therefore did not ground the 10-15 km scale in the closest experiment.

GraphRAG retrieved the heterogeneous-patch Claims and a semi-arid observational Claim. It connected dry-soil afternoon convection preference with the reported >5 km zero-wind transition to deeper convection, then explicitly stated that a weak non-zero monsoon wind may disrupt the mechanism.

The GraphRAG answer is scientifically more specific, but one phrase suggested that planners might "leverage" the dry-patch tendency. That is too close to a local recommendation. The evidence supports a mechanism hypothesis, not a Rajasthan intervention, because local geometry, water constraints, non-zero wind sensitivity, and validation are missing.

## Interpretation

- ClimateKG is a graph, but its exact canonical-State mechanism projection is under-connected.
- Current alias normalization is active but deliberately conservative; only explicit aliases merge.
- Community formation is absent from the original ClimateKG query pipeline. Adding Leiden communities creates thematic neighborhoods, not scientifically valid causal chains.
- The Rondonia failure is actionable: Context/Claim retrieval worked, while exact State path seeding overruled query-specific evidence.
- GraphRAG's use of ClimateKG entities is not an independent extraction baseline. It tests whether community-and-relationship retrieval can use the already extracted scientific objects more effectively.

No claim that one system is generally superior is justified from three queries. A blinded evidence-completeness and citation-correctness audit over a larger query set is still required.
