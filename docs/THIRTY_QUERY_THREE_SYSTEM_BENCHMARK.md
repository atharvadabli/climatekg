# Thirty-Query Three-System Benchmark

## Purpose

This benchmark compares the strongest available configurations of:

- PlainRAG: dense retrieval over source blocks;
- Microsoft GraphRAG: community/entity graph retrieval; and
- ClimateKG: the evidence-union query architecture.

The aim is not to declare one architecture universally superior. The evaluation tests where each representation works and where ClimateKG still loses relevant evidence.

## Corpus and questions

All systems use the same 115-paper corpus. PlainRAG contains 10,102 embedded source blocks. GraphRAG contains 2,363 entities, 1,724 relationships, and 752 communities. ClimateKG uses the corresponding Contexts, Facets, Claims, canonical States, and SourceBlocks.

The benchmark contains 30 questions:

| Question type | Count |
|---|---:|
| Context-dependent finding | 13 |
| Direct paper finding | 8 |
| Mechanism/pathway | 6 |
| Spatial effect | 3 |

The cases cover irrigation, forest conversion, cropland conversion, seasonal and drought dependence, surface-energy partitioning, mesoscale circulations, patch size, non-local warming, and atmospheric moisture recycling.

Gold passages were read as findings, analyses, or mechanisms presented by the indexed paper itself. Draft cases that only summarized cited literature were excluded. Questions about methods alone were also excluded. Every case remains marked as requiring final human verification against the original PDF.

## Protocol

1. The same question text was passed to all three systems.
2. Each ClimateKG question was parsed once, and the saved `QuerySpec` was reused.
3. All systems generated an answer using `qwen3.6:27b`.
4. Retrieval was checked for whether the paper containing the gold finding reached the final answer evidence.
5. Token overlap and exact qualifier coverage were retained as lexical diagnostics.
6. A second Qwen call compared the three answers with system identities hidden and candidate order shuffled per question. It scored scientific correctness, completeness, and directness against the reference answer.

The Qwen review is diagnostic, not independent expert assessment. It uses the same model family as answer generation, its candidate positions are shuffled but not perfectly balanced, and the reference answers have not yet received final human PDF verification.

## Retrieval and latency

| System | Complete | Expected paper reached | Mean token F1 | Mean exact qualifier coverage | Median latency |
|---|---:|---:|---:|---:|---:|
| PlainRAG | 30/30 | 30/30 | 0.3579 | 0.1905 | 24.6 s |
| Microsoft GraphRAG | 30/30 | 27/30 | 0.2620 | 0.2461 | 40.0 s |
| ClimateKG evidence union | 30/30 | 24/30 | 0.2545 | 0.2100 | 190.5 s |

PlainRAG reached the expected paper for every question and was substantially faster. GraphRAG missed three expected papers. ClimateKG missed six and was about 7.7 times slower than PlainRAG at the median.

## Blinded answer review

| System | Correctness (0-4) | Completeness (0-4) | Directness (0-2) | Reference conflicts |
|---|---:|---:|---:|---:|
| PlainRAG | 3.600 | 3.500 | 1.867 | 0 |
| Microsoft GraphRAG | 3.433 | 3.433 | 1.767 | 2 |
| ClimateKG evidence union | 2.567 | 2.367 | 1.300 | 7 |

The overall result favors PlainRAG. The category-level result is more informative:

| Question type | PlainRAG correctness | GraphRAG correctness | ClimateKG correctness |
|---|---:|---:|---:|
| Context-dependent finding | 3.846 | 3.231 | 2.615 |
| Direct paper finding | 3.500 | **3.750** | 1.250 |
| Mechanism/pathway | 3.000 | 3.167 | **3.833** |
| Spatial effect | **4.000** | **4.000** | 3.333 |

ClimateKG's useful strength is mechanism synthesis. It produced the highest mean correctness and completeness on the six mechanism questions. For `CKGQ0046`, it did not retrieve the gold paper but still gave the correct humid-tropical deforestation mechanism from compatible Claims in other papers. This is the type of structured cross-paper reasoning the KG is intended to support.

ClimateKG performed poorly on direct findings. It often replaced a requested paper-specific result with a general synthesis from semantically similar Claims. PlainRAG and GraphRAG were more reliable for these questions.

## ClimateKG miss trace

ClimateKG missed the expected paper for `CKGQ0009`, `CKGQ0026`, `CKGQ0029`, `CKGQ0032`, `CKGQ0041`, and `CKGQ0046`.

All six failures have the same stage pattern:

1. The correct paper's Claim appears in `claim_candidates`.
2. The supporting Context from that paper is absent from `context_candidates`.
3. Context gating therefore removes the Claim before direct evidence-path or graph-path construction.
4. The correct SourceBlock never reaches the synthesis package.

This is not primarily a synthesis-prompt failure. The relevant structured Claim was retrieved, but the current path builder requires its Context to survive the separate Context shortlist. Semantically similar Claims from other papers then occupy the final evidence package.

The pattern is most damaging for direct-finding questions, where the task is to report a paper result rather than assess transferability to a new environment. A future architecture experiment should keep strict Context gating for transfer and multi-Claim mechanism paths, while allowing a separately labelled, high-relevance direct-evidence lane to retain paper-specific Claims with unknown applicability. That change must preserve the distinction between missing Context information and an actual Context mismatch.

## Interpretation

The current ClimateKG is not yet the best general scientific question-answering system. PlainRAG is the strongest default for direct evidence lookup in this benchmark, and GraphRAG is competitive for direct findings and broader synthesis.

The KG is useful where canonical States and Claim relations support mechanism reasoning across papers. Its present bottleneck is not the absence of structured knowledge; it is that the query pipeline discards some of that knowledge when its supporting Context misses the independent top-k Context list.

No retrieval architecture should be selected from the aggregate score alone. A practical combined system would route direct-finding questions to passage evidence and use Context-gated Claim paths for transfer, mechanism, contradiction, and land-use planning questions. That is a design hypothesis for the next experiment, not a result claimed by this benchmark.

## Saved artifacts

Runtime outputs are stored outside Git under:

`evaluation/output/query_architecture_benchmark_v3_30/`

Important files:

- `summary.md`: retrieval, lexical, and latency aggregates;
- `comparison.json`: every gold answer, generated answer, and automatic metric;
- `retrieval_miss_trace.md`: stage presence for every expected-paper miss;
- `query_parse/specs/`: the 30 saved ClimateKG query parses;
- `variants/*/results/`: one complete result JSON per system and question;
- `variants/climatekg_evidence_union/artifacts/`: full ClimateKG query reports and synthesis calls;
- `blinded_judge/summary.json`: aggregate and per-case blinded answer review;
- `blinded_judge/artifacts/`: actual judge prompts and raw model responses.

The audited 30-case dataset is stored under:

`evaluation/output/climatekg_benchmark/dataset_v3_current_findings_30/`
