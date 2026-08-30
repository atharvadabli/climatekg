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
# Small-paper combined extraction experiment (2026-08-29)

- Added an experimental one-call Context/Facet/Transition/Claim route for
  cleaned papers at or below 8000 estimated tokens.
- Benchmarked Qwen `no`, `low`, and `medium` thinking on P000006 and preserved
  exact prompts, raw responses, thinking, converted objects, and metrics.
- Traced v1 failures to deliberate regime compression and same-endpoint
  Transitions in model reasoning; v2 fixed the generic structural rule.
- Added a v3 evidence-ledger procedure. It improved the selected `low` run to 7
  Contexts, 3 Transitions, and 8 Claims in 460 seconds.
- The combined run still omitted a material resolution-sensitivity experiment.
  Automatic routing is therefore disabled by default; see
  `docs/SMALL_PAPER_COMBINED_EXTRACTION_EXPERIMENT.md`.
- Repeated v3 with fresh `low`, `medium`, and `high` requests. All three
  thinking traces and JSON responses were byte-identical, with approximately
  469 seconds runtime each. On local Ollama 0.32.9, these three non-false levels
  did not produce different reasoning effort for this model/request.

# Constrained combined extraction v4.1 (2026-08-29)

- Replaced full SourceBlock IDs in the one-call prompt with request-local
  handles and enumerated the allowed handles in the request JSON Schema.
- Nested Facets and Context Claims inside Contexts and comparison Claims inside
  Transitions, then deterministically flattened them into the unchanged final
  ClimateKG schemas.
- Rewrote the standalone Qwen prompt around complete experimental settings and
  clarified that reported responses belong in Claims rather than Facets.
- Replayed previously failing `P000010` with thinking disabled. It completed
  through embeddings and Parquet/FAISS indexing in 242.6 seconds with 9
  Contexts, 12 Facets, 5 Transitions, 17 Claims, and valid evidence round trips.
- The 30% solar-efficiency Claim is now scoped to its own 30% Context instead of
  the unrelated 15%-to-45% Transition.
- Automatic combined routing remains disabled. This is a one-paper structural
  result; crossed-factor `P000007` and a broader corpus remain to be tested.

# Constrained v4.1 heterogeneous patch-size test (2026-08-29)

- Ran `atsc-jas-d-18-0196.1.pdf` with the no-thinking one-call route through
  embeddings and Parquet/FAISS indexing in 254.4 seconds.
- Evidence handles, nested Claim scopes, deterministic flattening, and graph
  integrity all passed.
- Scientific setting coverage did not pass: HET5/HET7/HET14 zero-wind cases,
  multiple strong-wind cases, and homogeneous controls were compressed into
  broad Contexts; HET7U0.5, HET14U2, HOMU0_DRY/WET, and detailed Ax2 cases were
  not preserved as separate settings despite being present in cleaned blocks.
- A low-thinking replay hit the 32K limit with 32,411 prompt tokens, only 357
  generated tokens, and `done_reason: length`; its JSON was truncated.
- Conclusion: v4.1 improves referential integrity but does not make a one-call
  route adequate for crossed-factor papers. This paper requires the proposed
  compact two-call Context/Facet then Transition/Claim route or staged extraction.
# 2026-08-29: Merge-ready integration branch

- Created `integration/indexing-v11-combined-v41` from the completed extraction
  experiments.
- Replaced the accidental full-no-reasoning default with the selected validated
  profile: mapping `medium`, Claims `no`, reconciliation/consolidation `no`, and
  query synthesis at its original `low`/`medium` levels.
- Added a deterministic derivation fingerprint covering extraction route,
  prompts, models, reasoning levels, cleaning, retrieval, consolidation, and
  canonicalization settings. Cached final artifacts are rejected when this
  fingerprint changes.
- Removed the unfinished atomic query-Facet assignment and whole-Context rerank
  experiment. Context comparison again uses the specified domain-wise MaxSim;
  ANN whole-Context similarity remains candidate-generation/tie-break data.
- Kept combined v4.1 extraction disabled by default and retained staged v11 as
  the production indexing route.

# 2026-08-29: Earth Engine-only enrichment

- Created `feature/earth-engine-enrichment` from the clean integration branch.
- Added exact GeoJSON, labeled-coordinate, and pan-India watershed-ID spatial
  resolution.
- Added one shared deterministic enrichment implementation for indexing and
  querying, using Earth Engine TerraClimate, ERA5-Land, SRTM V3, and ESA
  WorldCover.
- Added dataset/version/time-window/geometry-hash/algorithm provenance to every
  derived Facet and preserved raw Earth Engine statistics in trace artifacts.
- Added a direct `enrich-area` smoke command and explicit warnings for the
  unavailable Köppen family and unimplemented land-cover patch metrics.
- No local raster fallback is present. Earth Engine failures are recorded and
  no substitute values are generated.

# 2026-08-30: Shared-corpus RAG and GraphRAG baseline audit

- Traced the Rondonia and Rajasthan query failures through saved parse requests,
  query reports, synthesis prompts, final responses, and Qwen thinking.
- Confirmed that the final model recognized missing or non-transferable evidence;
  the failures originated in query representation, State seeding, path selection,
  and evidence packaging.
- Added a reproducible topology audit. The 17-paper mechanism projection has
  261 Claims, 367 canonical States, 118 weak components, 16 exact two-Claim
  paths, and 12 exact three-Claim paths.
- Exported one deduplicated 18-paper SourceBlock corpus for both baselines.
- Plain RAG uses only cleaned paper passages. The GraphRAG adapter uses canonical
  States as entities, Claims as relationships, and Microsoft GraphRAG 3.1.1's
  hierarchical Leiden implementation for thematic communities.
- Preserved Claim type, Context/Facet metadata, Paper identity, and exact
  SourceBlock provenance in the adapted GraphRAG tables.
- Kept GraphRAG communities distinct from ClimateKG's scientific Context gating;
  community co-membership is not treated as proof that Claims can form a valid
  mechanism chain.
- Completed all three queries. Plain RAG took 27.63-40.30 seconds per query;
  GraphRAG took 38.34-55.94 seconds. The adapted index formed 134 level-0
  communities from 399 States and 279 Claim relationships.
- For Rondonia, GraphRAG selected 18 Claims from the correct `P000019` paper.
  This confirms that the existing ClimateKG failure occurred after successful
  Claim retrieval, when State-seeded path selection replaced the relevant
  evidence with generic deforestation paths.

# 2026-08-30: Query evidence/path redesign

- Created `experiment/query-evidence-path-redesign` from the completed baseline
  audit branch.
- Froze Q1/Q2/Q3 and the Q2 failure trace before modifying retrieval.
- Change 1 reserves separate bounded evidence lanes for query-focused,
  Context-gated direct Claims and State-connected graph paths. Graph traversal
  no longer has sole authority to admit Claims to synthesis.
- Change 1 Q2 result: the direct lane retained eight `P000019` Claims spanning
  rainy, break, and dry periods; the generated answer now addressed the requested
  seasonal and wind-conditioned findings. The four graph slots remained generic
  `P000002` paths, confirming that path seeding is the next independent issue.
- Change 1 tests: `40 passed`. Full-run LLM time was 19.87 seconds for parsing
  and 269.74 seconds for synthesis.
- Change 2 seeds graph expansion from context-gated semantic Claim candidates
  for forward, backward, and global questions. Explicit A-to-B traversal remains
  strict. Only two-or-more-Claim chains qualify for the graph lane.
- Change 2 Q2 result: 20 relevant anchors produced zero exact State-connected
  chains, which is reported directly. No generic `P000002` paths entered the
  evidence package. The supported answer was retained while synthesis input fell
  from 21,630 to 18,166 model-reported tokens and synthesis time fell from 269.74
  to 228.91 seconds.
- Change 2 tests: `86 passed`.
