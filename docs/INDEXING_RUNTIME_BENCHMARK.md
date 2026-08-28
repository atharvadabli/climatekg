# Indexing Runtime Benchmark

Date: 2026-08-28

## Scope

Seven representative papers were indexed from PDF through final scientific objects, embeddings,
Parquet graph tables, and FAISS indexes. The original target was ten papers. The first paper took
29.88 minutes, so the run used the requested six-to-seven-paper fallback rather than committing to
an approximately five-hour serial run.

The run used only:

- NVIDIA Nemotron-Parse v1.2 for PDF parsing;
- `qwen3.6:27b` for structured scientific extraction;
- `qwen3-embedding:4b` with 2,048 dimensions for embeddings;
- the configured prompts, schemas, reasoning levels, thresholds, and validation behavior.

No scientific extraction or retrieval algorithm was changed for this benchmark. The added code
records timing and model-call metadata only.

## Corpus

| Paper | Indexed title | Main coverage |
|---|---|---|
| `P000001` | Impacts of wind farms on surface air temperatures | Wind-farm surface temperature |
| `P000002` | Decreased cloud cover partially offsets cooling from deforestation albedo change | Deforestation, albedo, cloud cover |
| `P000003` | Effects of global irrigation on the near-surface climate | Irrigation and near-surface climate |
| `P000004` | Present-day irrigation mitigates heat extremes | Irrigation and heat extremes |
| `P000005` | Impact of mesoscale vegetation heterogeneities on the planetary boundary layer | Vegetation heterogeneity and boundary-layer dynamics |
| `P000006` | Afternoon rain more likely over drier soils | Soil moisture and precipitation |
| `P000007` | Cooling of US Midwest summer temperature extremes from cropland intensification | Cropland intensification and heat extremes |

## End-to-End Results

| Measure | Result |
|---|---:|
| Completed papers | 7 |
| Total indexing wall time | 3.65 h |
| Mean per paper | 31.25 min |
| Median per paper | 29.88 min |
| Total generative LLM attempts | 110 |
| Valid structured responses | 110 |
| Retry attempts | 0 |
| Time inside generative LLM calls | 3.04 h |
| Parquet and FAISS build | 2.12 s |
| Output size, including PDFs and all artifacts | 261.61 MB |

Per-paper fresh runtimes were 29.88, 31.29, 43.86, 28.50, 35.05, 22.01, and 28.15 minutes.

The completed graph contains:

| Object | Count |
|---|---:|
| Papers | 7 |
| SourceBlocks | 996 |
| Contexts | 63 |
| Facets | 189 |
| Transitions | 21 |
| Claims | 81 |
| States | 126 |
| Evidence links | 556 |
| Relationships | 2,265 |

FAISS indexes contain 63 Contexts, 81 Claims, 125 distinct State vectors, and 21 Transitions.

## Phase Timing

| Phase | Total minutes | Share of indexing time |
|---|---:|---:|
| Claim extraction | 80.35 | 36.7% |
| Paper mapping | 55.30 | 25.3% |
| Facet extraction | 39.46 | 18.0% |
| Nemotron PDF parsing | 26.28 | 12.0% |
| Paper consolidation | 9.28 | 4.2% |
| Context reconciliation | 6.04 | 2.8% |
| Final object embeddings | 1.12 | 0.5% |
| SourceBlock embeddings | 0.86 | 0.4% |
| Cleaning, SourceBlocks, IDs, State canonicalization, and final assembly | less than 0.1 | less than 0.1% |

Graph construction is not a performance problem. Deterministic cleaning, validation, ID assignment,
State construction, and serialization are also negligible. Optimization should focus on generative
extraction and, secondarily, Nemotron parsing.

## LLM Timing

| Stage | Calls | Total minutes | Mean seconds per call | Prompt tokens | Output tokens |
|---|---:|---:|---:|---:|---:|
| Claim extraction | 21 | 78.58 | 224.5 | 401,390 | 15,803 |
| Facet extraction | 61 | 34.11 | 33.6 | 540,000 | 25,764 |
| Whole-paper mapping | 4 | 26.18 | 392.7 | 78,418 | 9,501 |
| Long-paper map consolidation | 3 | 18.91 | 378.2 | 62,203 | 7,640 |
| Section scouting | 9 | 10.21 | 68.1 | 67,760 | 15,505 |
| Paper consolidation | 7 | 8.44 | 72.4 | 24,668 | 1,701 |
| Reconciliation Claim extraction | 2 | 3.58 | 107.5 | 13,833 | 500 |
| Context reconciliation | 1 | 2.11 | 126.4 | 5,103 | 332 |
| Reconciliation Facet extraction | 2 | 0.35 | 10.4 | 6,687 | 380 |

Every response passed its JSON Schema on the first attempt. Schema repair and retry validation added
no time in this run.

## What Each LLM Received

Every call retains three adjacent artifacts:

- `*.attempt0.request.json`: the exact Ollama request, including model, system prompt, populated user
  prompt, complete JSON Schema, temperature, context window, and thinking setting;
- `*.attempt0.json`: the raw Ollama response, including reasoning and structured response text;
- `*.attempt0.metrics.json`: wall time, Ollama durations, prompt/output token counts, validation
  result, and paths to the exact request and response.

The full call-by-call index is in
`climatekg/runtime/outputs/indexing_benchmark_20260828/INDEXING_TIMING_REPORT.md`. It lists all 110
calls and the relative path of each exact request and response. The machine-readable equivalent is
`benchmark_summary.json`.

## Root Causes

### 1. Reasoning generation dominates several stages

The responses contain 661,469 characters in the saved `message.thinking` fields and 240,217
characters in structured response content. About 126.6 minutes of LLM time lies outside Ollama's
reported prompt-evaluation, structured-output generation, and model-load durations. This time is
concentrated in stages configured with low or medium thinking:

| Stage | Wall minutes | Time outside prompt/output/load metrics | Thinking characters |
|---|---:|---:|---:|
| Claim extraction | 78.58 | 63.85 | 401,606 |
| Whole-paper mapping | 26.18 | 19.44 | 114,512 |
| Map consolidation | 18.91 | 14.09 | 74,158 |
| Paper consolidation | 8.44 | 6.07 | 38,168 |

This does not prove that reasoning can be removed without a quality loss. It proves that reasoning
level is the first variable worth testing under controlled scientific comparison.

### 2. Embedding/generation model switching is repeated

Generative calls spent 17.29 minutes loading models. Facet extraction accounted for 10.93 minutes
and Claim extraction for 3.76 minutes. Evidence-bundle construction invokes the embedding model,
then the next extraction call reloads the 27B model. Repeating this for each Context or Transition
causes avoidable model churn.

### 3. Scientific structure multiplies calls

The long irrigation paper with five Transitions took 43.86 minutes. Claim extraction is one grounded
call per Transition, and Facet extraction is one call per Context. This is intentional provenance
behavior, but runtime therefore scales with extracted scientific structure, not merely pages or
SourceBlocks.

### 4. Prompt size is not the sole bottleneck

Across all calls, prompt evaluation took 13.77 minutes, whereas LLM wall time was 182.46 minutes.
Reducing repeated registries and evidence text may improve memory use and some latency, but it will
not deliver the largest speedup unless it also reduces reasoning and generated output.

## Recommended Optimization Order

### A. Precompute evidence bundles before generative loops

For Facet extraction, generate all Context evidence bundles first while the embedding model remains
loaded, then run the Facet LLM calls consecutively. Apply the same pattern to Transition Claim
bundles after Facets are finalized.

This changes scheduling only. It preserves prompts, schemas, evidence selection, call boundaries,
and reasoning levels. This optimization was implemented after the baseline and tested on a fresh
replay of `P000006`.

### B. Run a reasoning-level ablation, not an immediate default change

On three structurally different papers, replay the exact saved requests with `thinking: false` for:

1. Claim extraction;
2. whole-paper mapping and map consolidation;
3. paper consolidation.

Compare Context hierarchy, Transition endpoints, Claims, evidence IDs, null results, reversals,
conditioning Facets, and validation warnings against this baseline. Claim extraction alone contains
about 63.85 minutes of reasoning-associated time, approximately 9.1 minutes per indexed paper.

The configured reasoning levels are normative today. They should change only after the ablation
shows no material scientific-quality regression and the specification is updated.

### C. Reduce repeated prompt material only after measuring contribution

Claim prompts repeat the Context Registry, Transition Registry, reachable Facets, and evidence
bundle for each Transition. A specification change could pass only the target Transition, its
endpoint Context ancestry, and reachable Facets. However, prompt evaluation is only 7.5% of total
LLM wall time, so this should follow the reasoning and model-switch experiments.

### D. Do not prioritize these areas

- Parquet/FAISS construction: 2.12 seconds total.
- deterministic validation: no malformed responses or retries occurred;
- State canonicalization and serialization: effectively zero runtime;
- parallel generative calls on the same 24 GB GPU: likely contention rather than speedup;
- changing schemas or merging Context/Transition calls merely to reduce call count: scientific
  provenance risk is too high without a separate design and quality evaluation.

## Reproduction

```powershell
.\.venv-climatekg\Scripts\python.exe scripts\run_indexing_benchmark.py `
  --output-root climatekg\runtime\outputs\indexing_benchmark_20260828 `
  --limit 7
```

Regenerate reports without rerunning indexing:

```powershell
.\.venv-climatekg\Scripts\python.exe scripts\run_indexing_benchmark.py `
  --output-root climatekg\runtime\outputs\indexing_benchmark_20260828 `
  --limit 7 `
  --report-only
```

The runner resumes completed papers without modifying their original timing files.

## Evidence-Bundle Scheduling Experiment

The optimized replay is stored in
`climatekg/runtime/outputs/indexing_bundle_precompute_p6_20260828`.

| Measure | Baseline | Bundle precomputation |
|---|---:|---:|
| End-to-end time | 22.01 min | 22.97 min |
| Contexts produced | 7 | 8 |
| Claims produced | 7 | 8 |
| Facet calls | 7 | 8 |
| Facet-call Qwen load time | 75.6 s | 13.5 s |
| Claim calls | 3 | 3 |
| Claim-call Qwen load time | 32.4 s | 11.3 s |
| Combined Facet/Claim Qwen load time | 108.0 s | 24.8 s |

The optimization removed 83.2 seconds of repeated Qwen model loading. Facet-call wall time fell from
3.82 to 3.04 minutes even though the replay contained one additional Facet call.

The total replay was nevertheless 58 seconds slower because Qwen generated a different paper map,
which caused an extra Context, extra Facet prompt material, an extra Claim, and longer Claim
reasoning. The baseline and replay whole-paper mapping request JSON files have the same SHA-256 hash:

```text
E28C012816DC7444B7A87CF4C0B2C5557EC31FA4174D57DF888A6EB6CAE8D8EE
```

Therefore the changed map occurred despite a byte-identical request at temperature zero. It cannot
be attributed to evidence-bundle scheduling, which begins after mapping. This replay demonstrates a
real model-load saving but does not establish an end-to-end speedup because LLM output variance is
larger than the saved time in a single run.

The scheduling change is retained because it does not alter evidence selection or prompts and has a
clear mechanical benefit. A stronger performance estimate requires either several replays or a
downstream-only benchmark starting from one fixed saved paper map.
