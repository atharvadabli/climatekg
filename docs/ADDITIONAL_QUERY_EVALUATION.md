# Additional query evaluation

Branch: `experiment/candidate-context-rescore-v2`

## What was evaluated

The audit used the latest completed atomic-query-plan run, not the older
single-query architecture. It contains 18 completed questions from the
model-checked 30-question dataset. Two attempted questions failed for runtime
reasons and are not counted.

Gold evidence is defined by independently audited SourceBlock IDs. ClimateKG
Claims were used only to determine whether that evidence was represented and
whether it reached the answer.

Three retrieval stages were measured separately:

1. **Candidate evidence**: evidence attached to retrieved Claim candidates.
2. **Delivered evidence**: evidence included in the final synthesis package.
3. **Cited evidence**: evidence attached to Claims cited by the generated answer.

## Stage results

| Measure | Result |
|---|---:|
| Completed questions | 18 |
| Expected paper present among candidates | 18/18 |
| Expected paper present in delivered evidence | 18/18 |
| Expected paper cited in the answer | 18/18 |
| Mean candidate SourceBlock Recall@10 | 0.509 |
| Mean delivered SourceBlock recall | 0.704 |
| Mean cited SourceBlock recall | 0.676 |

Candidate Recall@10 is lower than delivered recall because compound questions
have several atomic searches. A single global top-ten candidate list is not an
adequate description of the evidence delivered across those searches.

## Earliest failure stage

Five questions had incomplete delivered evidence.

| Case | Earliest failure | Finding |
|---|---|---|
| `CKGQ0002` | Indexing | Neither gold SourceBlock supports an indexed Claim. |
| `CKGQ0004` | Indexing | The gold SourceBlock supports no indexed Claim. |
| `CKGQ0006` | Indexing | The gold SourceBlock supports no indexed Claim. |
| `CKGQ0028` | Indexing | One of two gold SourceBlocks is unrepresented; the represented block is delivered and cited. |
| `CKGQ0030` | Evidence allocation | All three gold blocks are represented and retrieved, but the energy-flux block is omitted from the bounded synthesis package. |
| `CKGQ0031` | Indexing | The gold SourceBlock supports no indexed Claim. |
| `CKGQ0033` | Indexing | One of two gold blocks is unrepresented; the represented block is delivered and cited. |

These are not all query-pipeline failures. In six of the seven incomplete cases,
at least one required finding is absent from the indexed Claims. Changing
retrieval thresholds cannot recover those findings.

## Evidence-allocation experiment

`CKGQ0030` asks for a within-paper mechanism connecting reduced
evapotranspiration to surface energy fluxes and temperature over central India.
The correct Claims and `P000068:S18:P0089` occur in the candidate set. A later
dependent atomic query receives only two reserved positions from the paper
established by its preceding query, so related but incomplete Claims consume
those positions.

The dependency-paper quota was varied while preserving the total direct
evidence budget of eight Claims. Reserving five positions for the dependency
paper recovered all three gold SourceBlocks. The other three positions are
selected independently by SourceBlock, Claim-semantic, and endpoint similarity
and remain open to ordinary cross-paper retrieval.

Across the 18 completed cases:

| Configuration | Mean delivered SourceBlock recall | Regressed cases |
|---|---:|---:|
| Two dependency-paper positions | 0.704 | - |
| Five dependency-paper positions | 0.722 | 0 |

On the ten available development cases, mean delivered recall increased from
`0.667` to `0.700`, again with no case-level regression. This is a small sample;
the setting remains experimental until evaluated on a new locked set.

## Important correction to the earlier experiment

The first candidate-Context-rescoring worktree started from an older query
architecture and replayed compound questions as single queries. Its comparison
mixed unrelated code changes and did not represent the current execution flow.

The current atomic-query-plan implementation already:

- scores a candidate Claim's supporting Context on demand when Context ANN did
  not retain it;
- removes method-only Context Facets such as `simulation study`;
- decomposes compound questions into structured atomic searches;
- balances direct evidence across retrieval signals.

The new stage audit and dependency-quota experiment therefore use commit
`84010da` as their baseline.

## Artifacts

- Scorer: `scripts/evaluate_saved_climatekg_run.py`
- Detailed local results:
  `climatekg/runtime/outputs/candidate_context_rescore_v2/apv1_20_evidence_stage_scores.json`
