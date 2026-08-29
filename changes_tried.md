# Query Context Matching Experiment

Branch: `experiment/atomic-context-rerank`

Date: 2026-08-28

## Problem

A query can specify several conditions in one phrase. In the baseline parser, this phrase:

> a heterogeneous chessboard surface with 14.4 km alternating dry and wet patches

became one broad spatial condition. During Context comparison, that condition could match an
inherited facet describing the paper's complete patch-size range. As a result, the 1.2 km, 7.2 km,
and 14.4 km experiment settings received very similar scores.

The baseline ranking for the query below placed the correct 14.4 km setting fourth:

| Rank | Context | Setting | Facet score | Whole-Context score |
|---:|---|---|---:|---:|
| 1 | `P000001_C026` | 1.2 km, 0 m/s | 0.633138 | 0.672328 |
| 2 | `P000001_C019` | 7.2 km, 0 m/s | 0.632714 | 0.666576 |
| 3 | `P000001_C025` | 2.4 km, 0 m/s | 0.625609 | 0.638363 |
| 4 | `P000001_C013` | 14.4 km, 0 m/s | 0.625572 | 0.665067 |

## Changes Tried

### 1. Atomic query conditions

`prompts/query_parse.txt` now asks Qwen to emit separately matchable conditions. Wind, surface
arrangement, spatial scale, land-surface state, season, and similar conditions can therefore be
compared independently. The prompt remains standalone and defines every allowed domain in ordinary
language. It contains no example copied from the evaluation paper.

The query-parse prompt version changed from `v3` to `v4`.

### 2. Unique facet pairing within each domain

The baseline MaxSim calculation allowed one paper facet to be the best match for several query
facets. The experiment assigns each paper facet to at most one query facet within a domain. This
prevents a broad inherited facet from satisfying both patch arrangement and patch scale.

This is semantic embedding matching. It does not introduce exact string matching, a typed quantity
schema, unit-specific rules, or numeric rejection gates.

### 3. Whole-Context reranking

The persisted whole-Context embedding was previously used for ANN candidate generation and only as
a late tie-breaker. The experiment adds it to the retained-context ordering:

```text
rerank_score = 0.85 * facet_score + 0.15 * whole_context_score
```

The raw facet score, whole-Context score, and combined rerank score are all preserved in the query
report. Claim applicability continues to use the facet score, so the new retrieval signal is not
misrepresented as scientific confidence.

## Query Used

> Under zero background wind, consider a heterogeneous chessboard surface with 14.4 km alternating
> dry and wet patches and evaluate the dry-patch response. Does surface heat-flux heterogeneity with
> large patch size cause convective cloud development to transition to deep convection?

Graph: `climatekg/runtime/outputs/hierarchy_e2e_het_v10/parquet_graph`

## Results

### First experimental parse

The first prompt revision produced four independent conditions:

| Domain | Notion |
|---|---|
| `atmosphere` | zero background wind |
| `spatial_configuration` | chessboard surface arrangement |
| `spatial_configuration` | patch size scale |
| `hydrology` | alternating soil moisture states |

The correct HET14 Context matched its specific `P000001_F016` facet. This confirmed that unique
pairing prevents reuse of the broad range facet for both spatial conditions. However, the HET14
Context remained fourth.

### Second experimental parse

After defining the domains and asking Qwen to retain stated qualifiers, the parser produced:

| Domain | Notion |
|---|---|
| `atmosphere` | zero background wind |
| `spatial_configuration` | chessboard surface arrangement |
| `spatial_configuration` | 14.4 km patch size |
| `hydrology` | alternating dry and wet patches |
| `spatial_configuration` | dry-patch focus |

The resulting top Contexts were:

| Rank | Context | Setting | Rerank score | Facet score | Whole-Context score |
|---:|---|---|---:|---:|---:|
| 1 | `P000001_C025` | 2.4 km, 0 m/s | 0.587432 | 0.577734 | 0.642389 |
| 2 | `P000001_C026` | 1.2 km, 0 m/s | 0.578719 | 0.563117 | 0.667136 |
| 3 | `P000001_C019` | 7.2 km, 0 m/s | 0.576783 | 0.561930 | 0.660950 |
| 4 | `P000001_C013` | 14.4 km, 0 m/s | 0.569964 | 0.553147 | 0.665256 |

The correct Context again matched `P000001_F016`, but the embedding scores did not reliably order
14.4 km above 7.2 km, 2.4 km, and 1.2 km. The extra dry-patch condition also exposed an indexing and
query-domain inconsistency: the paper represents its prescribed dry/wet heat-flux pattern as
`land_surface`, while Qwen parsed the same wording as `hydrology`.

### End-to-end behavior

Both experimental runs found one mechanism path containing `P000001_CL002` and generated a grounded
answer. The answer correctly states that patch sizes larger than 5 km under zero background wind can
transition from shallow cumulus to deep precipitating convection over dry patches. The answer cites
the paper, page, and Claim ID.

Local detailed artifacts are preserved at:

- `climatekg/runtime/outputs/atomic_context_rerank/EXP_ATOMIC_Q1`
- `climatekg/runtime/outputs/atomic_context_rerank/EXP_ATOMIC_Q2`

Runtime artifacts are intentionally excluded from Git because they include model requests,
responses, embeddings, and larger generated files. This document preserves the comparison needed
for repository review.

## Conclusion

This is a **partial improvement**, not a completed fix.

- Improved: compound Context wording is decomposed; a broad facet cannot be reused for multiple
  query conditions; the correct case-specific HET14 facet is selected; final retrieval remains
  grounded.
- Not improved: the correct HET14 Context is still fourth. Independent sentence embeddings do not
  reliably distinguish nearby numerical conditions, and prompt-only domain classification remains
  imperfect.
- Not attempted: exact string checks, hard numeric gates, typed quantity fields, unit-specific
  schemas, or an additional LLM repair/reranking call.

The branch should be evaluated on the planned multi-paper query set before merging. A next
experiment should test a semantic reranker trained or prompted to compare a query condition and a
candidate condition jointly. That would address the observed pairwise discrimination problem
without requiring users to type a schema or requiring exact generated strings.

## Verification

```powershell
$env:PYTHONPATH = (Resolve-Path '.\.venv-climatekg\Lib\site-packages').Path
py -3.13 -m pytest -q -p no:cacheprovider
```

Result: `46 passed`.
# 2026-08-28: Central constants and no-reasoning indexing ablation

- Added `climatekg/constants.py` as the runtime tuning surface for both indexing
  and querying.
- Removed hard-coded reasoning, temperature, and retry settings from map
  consolidation, repair calls, query repair, and final synthesis.
- Set `REASONING_PROFILE = "no"` for an experimental three-paper run.
- Runtime fell by 45.7-50.8%, from a 31.92-minute matching baseline mean to a
  16.39-minute mean.
- All references remained valid and Parquet/FAISS construction completed.
- Full no-reasoning changed scientific map granularity: one duplicate
  comparison appeared and important dry/wet regimes were replaced by
  model-specific Contexts in one paper.
- Decision: keep the result as an experiment; test a hybrid profile with low
  reasoning for mapping and no reasoning for Claims/consolidation next.

# 2026-08-29: Factorial reasoning benchmark and medium-map cross-check

- Added a cache-safe eight-profile runner covering all `low`/`no` combinations
  for mapping, Claim extraction, and downstream reconciliation/consolidation.
- Added per-profile `BENCHMARK.md` and `benchmark.json` reports plus a combined
  matrix report.
- All four `map=no` profiles failed because they generated a duplicated
  irrigation comparison. All four `map=low` profiles passed the screening-paper
  structural gate.
- Claim reasoning at `low` cost substantially more without changing the Claim
  count when the same paper map and Facets were held fixed.
- A fresh `map-low_claim-no_down-no` cross-check omitted the wet/high-soil-
  moisture regime and its comparison in `P000006`.
- A targeted `map-medium_claim-no_down-no` cross-check preserved the important
  structures in `P000001`, `P000003`, and `P000006`, averaging 18.88 minutes per
  paper.
- Selected `map-medium_claim-no_down-no` for the stratified 50-paper run. At the
  measured mean, projected serial runtime is 15.73 hours.
- Added a deterministic 50-paper corpus builder and resumable profile benchmark
  runner. Scientific extraction behavior was not changed.

# 2026-08-29: Complete-setting prompt v11

- Compared full Qwen thinking for two byte-identical P000006 map requests.
  Both recognized dry/wet and day/night regimes; v10 sometimes removed them as
  sensitivity analyses because its regime rules conflicted.
- Rewrote paper-map and long-paper consolidation prompts using the standalone
  Qwen3.6-27B prompt-writing skill.
- Defined Context identity from directly analyzed combinations of location,
  setup, time, season, regime, treatment, and variable values, independently of
  whether results differ.
- Required an evaluated list/range/sweep to be represented as a family parent
  with value-specific children, without inventing unobserved cross-products.
- Controlled replays passed on P000006 (7 Contexts/3 Transitions), P000001
  (16/4), and P000003 (13/6).
- Promoted both prompts to v11 and aligned the normative indexing specification.
- Stopped the v10 large-corpus run after 20 attempts to avoid mixing prompt
  versions; its partial benchmark artifacts remain preserved.
