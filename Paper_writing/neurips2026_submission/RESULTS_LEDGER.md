# Results Ledger

Only values marked **measured** may appear as completed results in the paper.

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
