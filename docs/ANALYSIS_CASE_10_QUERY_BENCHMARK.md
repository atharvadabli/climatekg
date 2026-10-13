# Analysis-case extraction: ten-query benchmark

## Scope

This run re-used the deterministic PDF parse, cleaned text, SourceBlocks, and SourceBlock embeddings from the earlier corpus. It regenerated paper maps, Facets, Claims, analysis cases, consolidation, States, final embeddings, and the Parquet/FAISS graph with the `experiment/analysis-cases-v1` pipeline.

The unchanged benchmark cases were `CKGQ0001` through `CKGQ0010`. Their expected papers were `P000040`, `P000056`, `P000064`, `P000085`, `P000100`, `P000103`, `P000120`, and `P000122`.

Artifacts:

- rebuilt data: `climatekg/runtime/outputs/analysis_case_benchmark_10/data`
- rebuilt graph: `climatekg/runtime/outputs/analysis_case_benchmark_10/parquet_graph`
- new query run: `evaluation/output/climatekg_benchmark/runs/analysis_cases_v2_first10`
- comparison baseline: `evaluation/output/climatekg_benchmark/runs/v1`

## Indexing result

| Paper | Status | Claims | Claims with analysis cases | Final indexing attempt |
|---|---:|---:|---:|---:|
| P000040 | complete | 20 | 3 | 23.6 min |
| P000056 | complete | 35 | 9 | 24.2 min |
| P000064 | complete | 32 | 0 | 19.0 min |
| P000085 | needs review | 0 | 0 | 44.2 min before rejection |
| P000100 | complete | 14 | 9 | 13.7 min |
| P000103 | complete | 29 | 6 | 40.5 min |
| P000120 | complete | 27 | 12 | 11.8 min |
| P000122 | complete | 27 | 1 | 5.1 min for the successful resumed attempt |

The graph contains 7 papers, 1,556 SourceBlocks, 69 Contexts, 184 Facets, 24 Transitions, 184 Claims, 267 States, 609 evidence links, and 3,341 relationships.

`P000085` is a review paper. Map consolidation expanded dozens of cited primary studies into candidate Contexts, and all three responses reached the 32k-token limit before completing the JSON. Accepting those cited studies as findings of `P000085` would violate the provenance invariant. The stale paper was therefore not imported into the rebuilt graph.

`P000122` exposed an evidence-closure bug. Child Facet and Claim prompts could display inherited objects whose supporting blocks were absent from the allowed evidence bundle. The pipeline now includes inherited Facet evidence, scope evidence, and reachable Facet evidence in the corresponding bundle. Reference validation remains unchanged and strict.

## Query result

| Run | Complete | Failed | Expected-paper hit | Median token F1 | Mean token F1 | Median latency |
|---|---:|---:|---:|---:|---:|---:|
| Previous v1 | 9/10 | 1 | 6/9 | 0.2591 | 0.2205 | 184.1 s |
| Rebuilt analysis-case graph | 9/10 | 1 | 7/9 | 0.1441 | 0.1436 | 178.2 s |

Token F1 is lexical overlap with draft reference answers, not a measure of scientific truth. Manual trace review agrees with its overall direction here: the rebuilt pipeline improved extraction recall but did not improve final answer quality across these ten cases.

## Case audit

| Case | Observation |
|---|---|
| CKGQ0001 | **Extraction improved, final answer failed.** `P000100_CL011` contains the wettest/driest comparison, IGP qualifier, and value above 20%, and is the top Claim with analysis-case score 0.787. Its Context was absent from the 30 reranked Contexts, so applicability was unknown and path assembly removed it. Synthesis used the wrong `P000040` irrigation Claim. |
| CKGQ0002 | The correct `P000064` Claims rank first, but their Context applicability is unknown for the same reason. Path assembly replaces them with unrelated known-context irrigation and Amazon Claims. The previous answer was better. |
| CKGQ0003 | Both runs failed before retrieval during mandatory Earth Engine initialization. This is an operational enrichment failure. The expected source is also the rejected review paper `P000085`. |
| CKGQ0004 | Correct source and result recovered. The new answer clearly separates background soil-moisture insensitivity from vertical-depth and seasonal diagnostic dependence. |
| CKGQ0005 | The rebuilt system abstained. Its expected evidence is a secondary-study summary inside rejected review paper `P000085`; the previous answer used unrelated papers. |
| CKGQ0006 | Correct `P000120` neutral and El Nino Claims were extracted and lead Claim ranking, but their applicability is unknown and they are absent from the synthesis paths. The final answer therefore abstains. |
| CKGQ0007 | Extraction preserved the La Nina-versus-El Nino soil-moisture result, but missed the separate precipitation sign difference in `P0047`. A causal-link consistency Claim from `P0049-P0050` was used instead, producing an incorrect statement that precipitation reduction is consistent across both phases. |
| CKGQ0008 | The expected review sentence in `P000122:P0033` was not represented as a Claim. The answer used scientifically related water-deficit Claims from `P000056` and `P000103`, but did not recover all stated cases, including near-saturated high-humidity conditions. |
| CKGQ0009 | The exact fire-driver relationships were extracted from `P000103:P0092` but correctly classified as `CITED_BACKGROUND` and filtered. The benchmark expects an answer about a cited De Faria et al. study from a review paper, so the system abstains by design. |
| CKGQ0010 | Correct source and mechanism recovered. The answer remains strong and explains why root-zone moisture works during SON while surface moisture works better during DJF. |

## Root cause after extraction

The main downstream failure is hierarchical Context crowding:

1. A query with one generic spatial Facet retrieves many descendants that inherit the same parent Facet.
2. These descendants receive identical or near-identical Context scores.
3. One paper can occupy many of the 30 reranking slots.
4. A directly relevant Claim can still enter through Claim ANN, but its supporting Context is absent from the Context report.
5. `require_known_context_for_direct_claims=true` removes that Claim during path/evidence assembly.

For `CKGQ0001`, this happens even though `P000100_CL011` is the top-ranked Claim and exactly contains both requested analysis cases.

## Conclusion

The new representation improves extraction of result strata across several papers, not only `P000100`. It is not yet an end-to-end improvement on this benchmark. The next change should address inherited-Context crowding before adjusting prompts again. A principled solution should deduplicate equivalent effective Context evidence during reranking or allocate reranking capacity across distinct effective settings, while retaining every Context and its hierarchy in the graph.

The benchmark should also distinguish primary-paper questions from questions whose gold answer is a cited result quoted by a review. The latter conflict with the current no-cited-background invariant and should use the cited primary paper as the indexed source.
