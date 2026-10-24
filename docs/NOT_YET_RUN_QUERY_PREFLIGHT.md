# Not-yet-run query preflight

Date: 2026-10-24

This preflight covers the 12 questions in the current 30-question development
dataset that did not have a completed report in `atomic_plan_v3_20`. These are
useful regression cases, but they are not a new held-out test because the
dataset has already informed development.

Before running retrieval, each independently annotated central SourceBlock was
first checked against the evidence IDs of all indexed Claims. A subsequent
semantic audit checked whether the same finding had been extracted from a
different passage in the paper. Exact SourceBlock coverage alone is not a valid
measure of scientific finding coverage because papers often repeat findings.

| Case | Capability | Exact gold blocks | Semantic finding coverage |
|---|---|---:|---|
| `CKGQ0005` | Context conditional | 1/1 | Complete |
| `CKGQ0015` | Context conditional | 0/1 | Partial: seasonal contrast present; full spatial qualifier absent |
| `CKGQ0036` | Direct finding | 1/1 | Complete |
| `CKGQ0041` | Mechanism pathway | 2/3 | Complete through an equivalent passage and `P000088_CL010` |
| `CKGQ0042` | Mechanism pathway | 1/3 | Complete through adjacent passages and `P000036_CL003/013/015` |
| `CKGQ0043` | Mechanism pathway | 0/2 | Complete through `P000086_CL008/013` |
| `CKGQ0044` | Mechanism pathway | 1/2 | Complete through `P000111_CL091/092/096` |
| `CKGQ0046` | Mechanism pathway | 0/1 | Missing |
| `CKGQ0047` | Mechanism pathway | 1/1 | Complete |
| `CKGQ0050` | Spatial | 1/1 | Complete |
| `CKGQ0051` | Spatial | 1/1 | Complete |
| `CKGQ0054` | Spatial | 1/1 | Complete |

Summary:

- 10 questions have complete semantic finding coverage.
- `CKGQ0015` has partial coverage. The monsoon/non-monsoon contrast is present,
  but the complete country-wide and Indo-Gangetic Plain qualifier from
  `P000100:S12:P0068` was not extracted as one Claim.
- `CKGQ0046` is the one genuine full extraction miss.

## Why exact SourceBlock coverage was misleading

Four apparent failures were actually equivalent-evidence cases:

- `P000088:S17:P0180` was not cited by a Claim, but its moisture-convergence
  finding appears in `P000088_CL010` using repeated evidence elsewhere.
- The West African divergence mechanism from `P000036:S16:P0144` is represented
  by `P000036_CL003/013/015` using adjacent and summary passages.
- The Jambi evaporative-cooling mechanism is represented by
  `P000086_CL008/013` using the discussion rather than the annotated abstract
  and conclusion blocks.
- The Amazon evapotranspiration mechanism in `P000111:S03:P0046` is represented
  by `P000111_CL091/092`, with the circulation consequence in `P000111_CL096`.

The remaining true miss, `CKGQ0046`, arose earlier. The paper map created one
Transition focused on comparing sparse and extensive land-cover-change schemes.
Its Claim call received 85 blocks, including `P000084:S09:P0057`, but returned
only five Claims about that comparison. The humid-tropics latent-heat and
evapotranspiration-efficiency mechanism was present in the input and absent from
the raw model output. Validation did not remove it. This is a paper-map and
Claim-task coverage failure: the sole extraction scope was narrower than the
paper's findings, while the input remained unnecessarily broad.

## Attempted live run

`CKGQ0036` was selected as the first fully represented case. The run failed
before query parsing because the configured local model could not start:

```text
OLLAMA_HTTP_ERROR query_parse: 500
cudaMalloc failed: out of memory
failed to allocate CUDA0 buffer of size 15507660800
```

The machine had approximately 22.7 GiB of free GPU memory. The local
`qwen3.6:27b` model is about 17 GiB and this Ollama build additionally requested
about 15.5 GiB for a model working buffer. The failure was reproduced at an 8K
context and with CPU-only loading, so it is a model-runtime allocation problem,
not a query result. No substitute model was used, and the case is not scored as
incorrect.

The complete failed-run artifact is under:

`climatekg/runtime/outputs/candidate_context_rescore_v2/new_query_run/`

## Correct next run

After the Qwen runtime can load, run the ten semantically complete cases first:

```text
CKGQ0005 CKGQ0036 CKGQ0041 CKGQ0042 CKGQ0043 CKGQ0044
CKGQ0047 CKGQ0050 CKGQ0051 CKGQ0054
```

For each case, report candidate, delivered, and cited SourceBlock recall and
then assign any failure to query planning, retrieval, Context scoring, evidence
allocation, path construction, synthesis, or citation rendering. `CKGQ0015`
must be scored with its known partial indexing ceiling, and `CKGQ0046` should be
re-indexed before it is used to compare query architectures.
