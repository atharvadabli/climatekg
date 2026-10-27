# Atomic Evidence-Subgraph Experiment

## Decision

The 10-paper experiment improved Claim flow and eight of ten answers, but it did not pass the frozen acceptance gate. The experiment was therefore not expanded to 30 papers.

## Corpus and outputs

The frozen corpus contains P000002, P000014, P000018, P000037, P000039, P000040, P000068, P000071, P000082, and P000100.

Main runtime artifacts:

- initial atomic graph: `climatekg/runtime/outputs/atomic_evidence_subgraph_v1/atomic_10_graph`
- labelled hybrid graph: `climatekg/runtime/outputs/atomic_evidence_subgraph_v1/hybrid_10_graph_v6`
- final retrieval run: `climatekg/runtime/outputs/atomic_evidence_subgraph_v1/queries_10_final_v6`
- final score-ordered recomposition: `climatekg/runtime/outputs/atomic_evidence_subgraph_v1/queries_10_final_v7`
- replacement-aware flow report: `queries_10_final_v7/replacement_aware_claim_flow.json`

The hybrid graph replaces only P000100 with the previously verified focused-result-scope artifact. This is declared in its `experiment_manifest.json`. It is not presented as a clean run of one indexing implementation.

## Changes tested

1. Extract one direct scientific relation per Claim and preserve old Claims while adding atomic replacements.
2. Add explicitly adjudicated State semantic links without treating them as causal edges.
3. Select evidence with relevance seeds, one opportunity per requested part, and bounded same-paper expansion. Paper novelty no longer displaces related mechanism steps.
4. Treat zero comparable Context coverage as unknown applicability instead of a mismatch.
5. Order accepted evidence by scientific relevance while reporting Context applicability separately.
6. Pack compound-query evidence fairly across subqueries and cap the combined package at 24 Claims.
7. Limit combined synthesis to eight non-repeated answer items.

## Quantitative result

The replacement-aware audit uses an accepted atomic replacement when it has exact normalized text, embedding cosine at least 0.84, or shared evidence and cosine at least 0.68. The full mapping is saved for review.

| Measure | Result | Gate |
|---|---:|---:|
| Expected findings represented in graph | 59/59 (100.0%) | at least 90% |
| Expected findings reaching candidates | 59/59 (100.0%) | diagnostic |
| Expected findings reaching selected evidence | 48/59 (81.4%) | at least 75% |
| Correct or mostly correct answers | 8/10 (80.0%) | at least 80% |
| Invalid accepted State links | 0 observed | 0 |
| Unsupported bridge/generalization | 1 observed | 0 |

The first three numerical thresholds pass. The overall gate fails because the final two requirements are conjunctive.

## Per-query review

| Query | Judgment | Main result |
|---|---|---|
| XPG007 | correct | Complete deforestation, turbulent-flux, cloud, and radiative-offset chain. |
| XPG008 | correct | Recovers 7% mean contribution, stress reduction, seasonal minimum, dry-year maximum, and IGP >20%. |
| XPG009 | correct | Recovers wet-to-dry transport, moisture pooling, deep convection, and precipitation. |
| XPG012 | correct | Recovers external-basin transport, return precipitation, compensation, and sign reversal. |
| XPG013 | correct | Separates local cooling from remote rainfall and temperature effects. |
| XPG023 | correct | Recovers symmetry loss, displaced convergence, cloud advection, and the 14.4 km condition. |
| XPG025 | correct | Distinguishes the approximately 5 km threshold from the 12.8 km optimum. |
| XPG026 | partly correct | Distinguishes the spatial families, but changes `mesoscale` to `microscale` and overgeneralizes a stated wind comparison. |
| AES009 | partly correct | Omits requested wind, instability, and radiation branches despite indexed evidence. |
| AES010 | correct | Separates dry-temperature cooling from increased extreme wet-bulb temperature. |

The full manual rationales are in `answer_review_v7.json`.

## Root causes found

### Diversity displaced mechanism steps

The first selector rewarded new papers after covering a requirement once. For XPG009 it selected one P000018 Claim and filled remaining slots with diverse papers, while the correct wet-to-dry transport and moisture-pool Claims ranked near the top but were omitted. Relevance seeds plus bounded same-paper expansion fixed this case.

### Compound evidence was unbounded

Each child query could contribute up to 20 paths. An eight-part question could therefore send more than one hundred Claim records to final synthesis. Balanced packing now reserves evidence for each subquery, adds paths round-robin, and caps the package.

### Missing Context was scored as mismatch

When no candidate Facet shared a query Facet's domain, Context coverage was zero. The old ranker assigned `A_claim = 0.0`, although no contradiction existed. The corrected ranker records applicability as unknown and retains mechanism relevance.

### Applicability was applied twice

Claims first passed Context gating and were then ordered by `R_path = M_path * A_path`. This moved a directly relevant remote-basin Claim from first in Claim ranking to eleventh in evidence order. Accepted evidence is now ordered by `M_path`; `A_path` remains visible and still controls incompatibility and graph coherence.

### Focused atomic replay cannot recover unseen result blocks

P000100's dry-year result occurs in SourceBlocks `P000100:S12:P0061` and `P000100:S12:P0063`. The additive atomic replay only revisited evidence near existing Claims, so it never received these blocks. The focused-result-scope artifact did receive them and extracted the required dry/wet comparison. This indexing coverage problem must be solved without collapsing the existing Context and Transition structure before a 30-paper run is justified.

## Runtime

- additive atomic extraction over 10 papers: 2,044 seconds (34.1 minutes)
- initial 10-query run: 1,489 seconds (24.8 minutes)
- final 10-query run after query fixes: approximately 1,015 seconds (16.9 minutes)
- cached compound-only recomposition: approximately 284 seconds (4.7 minutes)

LLM requests, responses, thinking output, and metrics are retained below each query and extraction artifact directory.

Focused deterministic and prompt tests pass. The full suite collected 137 tests; 130 ran without an assertion failure and seven could not set up because Windows denied pytest access to `C:\Users\DELL\AppData\Local\Temp\pytest-of-DELL`. A separate `-x` run confirmed the first error occurs inside pytest's `tmp_path` fixture before the test body.

## Next required work

1. Integrate result-block coverage with the stable paper hierarchy: every scouted result block must reach one focused Claim task without rebuilding or collapsing valid Contexts and Transitions.
2. Add a general synthesis validation for preserved scientific scale and bounded numerical comparisons. It should reject a changed term such as mesoscale to microscale rather than silently rewriting the answer.
3. Rework large enumerate questions so all requested mechanism branches survive query planning and evidence packing; AES009 currently creates eight searches and loses later outcome-mechanism combinations.
4. Rerun this frozen 10-query gate. Expand to 30 papers only after every conjunctive condition passes.
