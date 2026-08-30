# Results Ledger

Only values marked **measured** may appear as completed results in the paper.

## Current shared-corpus benchmark (measured)

- Shared finalized corpus: 18 papers, 2,746 SourceBlocks, 181 Contexts, 556 Facets, 58 Transitions, and 279 Claims.
- Graph projection: 399 unique canonical State nodes, 279 Claim edges, 132 weakly connected components, largest component 59 States, and 16 possible directed two-hop Claim pairs through seven intermediate States.
- Ten-paper extraction audit: 1,539 SourceBlocks, 114 Contexts, 323 Facets, 35 Transitions, and 185 Claims; all scope, conditioning-Facet, and evidence references resolve in all ten papers.
- Q01 zero-wind heterogeneity: PlainRAG, community graph retrieval, and ClimateKG each recovered and used all four expected Claims. Every cited identifier resolved. ClimateKG retained all required conditions and blocked unsupported spatial translation.
- Q02 0-to-1 m/s wind: PlainRAG recovered/used 2/5 expected Claims; community graph retrieval recovered/used 4/5; ClimateKG recovered/used 5/5. Every cited identifier resolved.
- Complete prompts, retrieval records, Qwen thinking fields, generation metrics, and answers for Q01--Q02 are preserved verbatim in `example_outputs/`.
- Expected Claims and reference propositions are author-prepared from the indexed corpus. They are not independent gold annotations and cannot measure extraction recall.

## Current benchmark still running

- Q03--Q10 are executing on the local Qwen3.6--27B model. Do not report a ten-query aggregate until all three system files exist for every query and `evaluation.json` has been regenerated.
- Wall-clock latency is currently contaminated by another process sharing the same Ollama server. Do not use these wall times for a system-efficiency comparison.

## Measured

- Staged indexing run requested 50 papers, registered 20, completed 17, and
  retained 3 as failures/needs-review before the run stopped.
- The 17 completed papers required 20.02 minutes per paper on average and
  20.92 minutes at the median; total recorded LLM wall time was 300.91 minutes.
- Aggregate completed-paper objects: 2,583 SourceBlocks, 155 Contexts, 497
  Facets, 54 Transitions, and 261 Claims. These totals are computed from the
  `counts` object of each of the 17 completed benchmark records.
- Heterogeneity case study: 163 SourceBlocks, 26 Contexts, 59 Facets, 4
  Transitions, and 18 Claims.
- Existing 10-paper graph validation: 2,184 SourceBlocks, 101 Contexts, 437
  Facets, 51 Transitions, and 213 Claims; all 10 fixed query runs produced a
  schema-valid cited answer after defect-focused reruns.
- The 17 completed staged papers form a Parquet graph with 379 States, 1,341
  evidence links, and 6,057 total relationships.
- A separate combined-route run registered 10 papers and completed 7 using 10
  total extraction calls. Successful papers averaged 3.29 minutes and produced
  906 SourceBlocks, 46 Contexts, 60 Facets, 20 Transitions, and 65 Claims. Its
  cached PDF parsing times make this an operational result, not a controlled
  end-to-end speed comparison with the staged run.
- ANN scaling experiment: exact/ANN results were identical for the one-paper
  scientific query; HNSW candidate generation achieved recall@100 of 1.00 in
  the saved synthetic scaling experiment from 26 to 26,000 Context vectors.

## Qualitatively verified

- A 14.4 km, zero-wind heterogeneous-patch query retrieved the correct
  thresholded transition to deep precipitating convection and cited Claims
  `P000001_CL001`--`P000001_CL004`.
- The Rondonia paper contains regime-dependent results that reverse the naive
  generalization "deforestation increases local rainfall": little/no response
  under rainy-season strong forcing, enhanced shallow cloud under weakened
  break-period wind with little rainfall, and dry-season localized convection.

## Must still be generated

- Same-corpus plain RAG answers for the three frozen questions.
- Same-corpus Microsoft GraphRAG answers and community reports.
- ClimateKG answers for the Rondônia and out-of-corpus target cases using the
  17-paper Parquet corpus.
- Manual evidence audit using the rubric in `evaluation_queries.json`.
- End-to-end latency and token totals for each of the three query systems.

## Observed query failure

- The frozen 17-paper Rondonia query parsed the requested seasonal and wind
  facets. P000019's best Context ranked sixth and its Claims entered the
  candidate set, but `QUERY_UNSUPPORTED_SOURCE_STATE_CLEARED` was emitted and
  all four retained paths used generic P000002 deforestation Claims. The final
  answer grounded itself in those selected Claims and explicitly reported the
  requested evidence as absent. This is a path-seeding/selection recall failure
  after successful extraction and candidate retrieval.
- The frozen out-of-corpus Rajasthan query completed in 290.4 seconds. Query
  parsing took 12.9 seconds (882 prompt / 325 generated tokens); synthesis took
  232.3 seconds (19,224 prompt / 1,026 generated tokens). It returned cited
  mechanisms and an explicit transfer warning, but the 10-15 km pattern was not
  represented as a spatial-configuration Facet and the answer did not reconcile
  user-specified weak monsoon wind with derived JJA wind of 3.09 m/s.

## Unavailable / must not be claimed

- No WRF simulation validates a generated recommendation.
- No farmer, planner, scientist, or community user study has been conducted.
- No statistically powered system-superiority benchmark exists.
- A retrieved applicability score is not a probability that a Claim is true.
