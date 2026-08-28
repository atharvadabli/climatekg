# Map Pipeline Redesign: Three-Paper Corpus Report

## Goal

Represent each paper as a compact tree of complete study settings. Preserve named study units and experimental combinations without adding a semantic repair call or expensive fuzzy validation.

## Corpus

| Case | Structure exercised | Source artifact |
|---|---|---|
| Surface heterogeneity and background wind | Factorial named simulations with patch size, wind, amplitude, and controls | `climatekg/runtime/prompt_examples/atsc-jas-d-18-0196-1/v2/papers/P000001` |
| Global irrigation | Coupled control/treatment runs plus offline sensitivity runs | `climatekg/runtime/data/papers/P000003` |
| Forestry climate forcing | Multiple regions, vegetation contrasts, and management comparisons | `climatekg/runtime/data/papers/P000011` |

Production prompts contain no names or identifiers from these papers.

## Root Cause Confirmed

The v4 prompt described inheritance, but the generated JSON Schema required only `temp_id`, `label`, and `evidence_block_ids` for a Context. Qwen inferred branch-like labels and IDs but omitted `parent_temp_ids`, `split_reason`, and `aliases`. Pydantic then supplied empty defaults, making every Context a root.

The fix makes every existing map field required in constrained generation. Fields whose scientific value is absent still use `[]` or `null`. No new scientific field was added.

## Input Reduction

Map consolidation now receives:

1. one direct block for every scout setting, comparison, and location mention;
2. title and abstract;
3. additional mention evidence while space remains;
4. setting-detail and result blocks while space remains.

It no longer adds global keyword matches or automatic neighboring blocks. Original-source text has a 9,000 estimated-token cap. Scout notes are rendered as a compact readable ledger rather than verbose JSON.

| Case | Earlier evaluated prompt | v5 evaluated prompt | Selected source blocks |
|---|---:|---:|---:|
| Heterogeneity | 30,365 | 21,558 | 40 |
| Irrigation | 28,226 | 18,682 | 41 |
| Forestry | 23,867 | 18,129 | 32 |

The local token estimator is intentionally conservative and differs from Ollama's tokenizer. Ollama's `prompt_eval_count` above is the measured value.

## v5 Map Results

| Case | Contexts | Roots | Aliases | Transitions | Time |
|---|---:|---:|---:|---:|---:|
| Heterogeneity | 18 | 1 | 29 | 6 | 452 s |
| Irrigation | 9 | 1 | 6 | 4 | 306 s |
| Forestry | 18 | 1 | 0 | 7 | 424 s |

Forestry has zero aliases because its paper-local names were used directly as labels. Empty aliases are valid in that case.

## Structural Observations

### Heterogeneity

The result has one common LES root, heterogeneous and homogeneous family branches, and complete named run leaves. Patch size and wind are no longer disconnected root Contexts.

The old scout collapsed doubled-amplitude cases. A targeted `section_scout_v3` call preserved `HET14U1_Ax2`, `HET14U2_Ax2`, and `HET7U1_Ax2` separately. A fresh production index will use these improved notes.

One map comparison used heterogeneous as `from` and homogeneous control as `to`. This is reviewable but should be monitored because a clearly identified control should normally be the `from` endpoint. No deterministic reversal is applied because baseline identity is a semantic judgment.

### Irrigation

The result has a common CAM-CLM root, coupled and offline branches, and named control, irrigation, soil-column, midnight, and noon leaves. Comparisons hold the modeling branch fixed.

### Forestry

The result has one analysis root, regional parents, site or regime children, and comparisons within each region. It does not flatten all sites into independent roots.

## Runtime Validation

Map validation remains limited to cheap internal invariants:

- JSON Schema validity;
- unique generated IDs;
- valid parent, endpoint, and SourceBlock references;
- acyclic parent structure;
- root/child consistency of `split_reason`.

There is no runtime exact or fuzzy matching between generated labels and scout text. Semantic behavior is checked offline with this corpus and the saved text trees.

## Review Artifacts

All exact LLM requests, JSON Schemas, raw responses, validated maps, input reports, and text trees are under:

`climatekg/runtime/outputs/map_prompt_corpus_v5/`

The main files for each case are:

- `map_input_report.json`
- `llm_call/*.attempt0.request.json`
- `llm_call/*.attempt0.json`
- `paper_map.json`
- `paper_map.tree.txt`

The targeted scout regression is in `map_prompt_corpus_v5/scout_v3_heterogeneity/`.
