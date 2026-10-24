# Not-yet-run query preflight

Date: 2026-10-24

This preflight covers the 12 questions in the current 30-question development
dataset that did not have a completed report in `atomic_plan_v3_20`. These are
useful regression cases, but they are not a new held-out test because the
dataset has already informed development.

Before running retrieval, each independently annotated central SourceBlock was
checked against the evidence IDs of all indexed Claims. This determines whether
the query pipeline can possibly recover the complete annotated answer.

| Case | Capability | Indexed central evidence | Status |
|---|---|---:|---|
| `CKGQ0005` | Context conditional | 1/1 | Fully represented |
| `CKGQ0015` | Context conditional | 0/1 | Indexing-limited |
| `CKGQ0036` | Direct finding | 1/1 | Fully represented |
| `CKGQ0041` | Mechanism pathway | 2/3 | Partly indexing-limited |
| `CKGQ0042` | Mechanism pathway | 1/3 | Partly indexing-limited |
| `CKGQ0043` | Mechanism pathway | 0/2 | Indexing-limited |
| `CKGQ0044` | Mechanism pathway | 1/2 | Partly indexing-limited |
| `CKGQ0046` | Mechanism pathway | 0/1 | Indexing-limited |
| `CKGQ0047` | Mechanism pathway | 1/1 | Fully represented |
| `CKGQ0050` | Spatial | 1/1 | Fully represented |
| `CKGQ0051` | Spatial | 1/1 | Fully represented |
| `CKGQ0054` | Spatial | 1/1 | Fully represented |

Summary:

- 6 questions are fully represented and can fairly test query retrieval,
  Context handling, path construction, and synthesis.
- 3 questions are partly represented. Retrieval can recover only part of the
  annotated answer.
- 3 questions have no indexed Claim attached to their central evidence. A
  query-pipeline change cannot make them complete.

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

After the Qwen runtime can load, run the six fully represented cases first:

```text
CKGQ0005 CKGQ0036 CKGQ0047 CKGQ0050 CKGQ0051 CKGQ0054
```

For each case, report candidate, delivered, and cited SourceBlock recall and
then assign any failure to query planning, retrieval, Context scoring, evidence
allocation, path construction, synthesis, or citation rendering. The other six
cases should be re-indexed before they are used to compare query architectures.
