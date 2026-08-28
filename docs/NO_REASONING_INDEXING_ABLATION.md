# No-Reasoning Indexing Ablation

Date: 2026-08-28

## Change

`climatekg/constants.py` is now the runtime source for indexing and query models,
reasoning levels, temperatures, retries, token budgets, `top_k` values,
thresholds, ranking weights, parser settings, timeouts, and ANN settings.

The experiment set:

```python
REASONING_PROFILE = "no"
```

This forced every indexing and query LLM stage, including repair paths, to send
`"think": false`. The former stage-specific levels remain in
`BASELINE_INDEXING_REASONING` and `BASELINE_QUERY_REASONING` and can be restored
with `REASONING_PROFILE = "baseline"`.

## Runtime Result

Three papers were freshly indexed from PDF through Parquet and FAISS. No parse,
mapping, extraction, or embedding cache from the baseline was reused.

| Paper | Baseline | No reasoning | Reduction | Speedup |
|---|---:|---:|---:|---:|
| `P000001` wind farms | 29.88 min | 16.24 min | 45.7% | 1.84x |
| `P000003` global irrigation | 43.86 min | 21.59 min | 50.8% | 2.03x |
| `P000006` soil moisture and rain | 22.01 min | 11.36 min | 48.4% | 1.94x |

Total generative LLM time fell from 81.58 to 37.22 minutes. Claim extraction
fell from 35.64 to 9.71 minutes even though the new run made 13 Claim calls
instead of 10 and returned more Claims. All 65 exact new requests used
`think: false`.

## Integrity Result

- All three final papers completed.
- Parquet graph and FAISS indexes completed in 1.06 seconds.
- No Claim, Context, Facet, or Transition contains an unknown evidence ID.
- No Claim has an unknown scope or conditioning Facet.
- No Transition has an unknown Context endpoint.
- The full deterministic test suite passes: 49 tests.

Embedding alignment shows that most baseline content remains represented. For
baseline-to-new matching, median maximum Claim cosine was 0.936, 0.907, and
0.896 for the three papers. These are diagnostic similarities, not scientific
truth scores or acceptance checks.

## Scientific Review

Full no-reasoning is materially faster, but it is not equivalent to the
baseline mapping behavior.

### `P000001`

The baseline represented two comparisons. The new map added a third comparison
between the standard wind-farm simulation and rotor-TKE sensitivity runs. This
is supported by the paper and may be a useful correction. The new run also
split several response curves into separate Claims, increasing Claims from 7
to 18. Some additions concern turbine productivity rather than local climate,
so downstream relevance becomes less focused.

### `P000003`

The main irrigation hierarchy was retained with 11 Contexts. The new run added
an offline irrigation-versus-control comparison, which is scientifically
useful. It also added `TR_06`, described as irrigated versus non-irrigated grid
cells, but assigned the same coupled control and irrigation endpoints already
used by `TR_01`. Claims under this duplicate Transition repeat effects already
represented as causal irrigation Claims. This is a map-granularity error.

The new run separately retained warming over non-irrigated grid cells and
cooling over irrigated cells. That is a useful sign-dependent result, although
its Context/spatial conditioning needs clearer representation.

### `P000006`

The new map split every individual model into its own Context but did not retain
the baseline's explicit dry-mean-soil-moisture and wet-mean-soil-moisture regime
Contexts. Those regimes materially condition the feedback and are more useful
for contextual retrieval than model-name Contexts. A nocturnal mechanism Claim
also states an attribution more strongly than the paper's cautious language
that organized systems "may" favour the positive feedback.

## Decision

The speed improvement is real, but full no-reasoning should not become the
scientific default yet. The observed problems are doable mapping and
granularity flaws, not failures of schemas, provenance, or graph construction.

The next experiment should use a hybrid profile:

- paper map and map consolidation: `low`;
- section scouts and Facets: `no`;
- Claim extraction: `no`;
- paper consolidation: `no`;
- Context reconciliation: initially `low`, then evaluate whether `no` is safe;
- query parsing: `no`;
- final synthesis: retain `low` and `medium` until separately evaluated.

This preserves the baseline hierarchy stage while targeting the Claim reasoning
that consumed the most time. A reasonable expected runtime is roughly 18-24
minutes per paper, depending on paper structure and parsing time.

## Artifacts

- Exact benchmark: `climatekg/runtime/outputs/indexing_no_reasoning_3paper_20260828/`
- Generated comparison: `NO_REASONING_COMPARISON.md` and `.json` in that folder
- Exact requests/responses: each paper's `extraction/**` directories
- Reusable comparison script: `scripts/compare_indexing_ablation.py`
