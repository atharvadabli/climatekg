# ClimateKG capability evaluation strategy

## Evaluation claim

ClimateKG should not be presented as a replacement for passage retrieval on
simple fact lookup. Its intended advantage is preserving the environmental
conditions, spatial relations, comparisons, causal status, and evidence chains
needed to transfer land-atmosphere findings or combine them safely.

The evaluation must therefore include both ordinary RAG questions and tasks
that require those structures.

## Two evaluation tracks

### Track A: common grounded question answering

Use the same papers, questions, answer model, retrieval limit, and citation
requirements for Plain RAG, Microsoft GraphRAG, and ClimateKG.

Report three headline metrics:

1. **Evidence Recall@10**: fraction of independently annotated SourceBlocks
   found among the first ten delivered evidence units.
2. **Atomic answer correctness**: fraction of gold scientific facts stated
   correctly, with partial credit recorded separately.
3. **Citation faithfulness**: fraction of substantive answer statements
   supported by their cited SourceBlocks.

This track measures general competence and prevents a specialized evaluation
from hiding weak basic retrieval.

### Track B: structured land-atmosphere reasoning

Use questions for which the system's explicit representation should matter.

| Capability | Test design | Success criterion |
|---|---|---|
| Context discrimination | Paired questions differ in one condition such as season, soil moisture, wind, patch size, or climate regime. | Both answers preserve the changed condition and select the appropriate evidence. |
| Sign or regime reversal | Evidence reports opposite, null, or scale-dependent responses. | The answer states each regime separately rather than averaging them. |
| Mechanism chains | The answer requires at least two independently supported Claims connected through canonical States. | Every edge is cited, State continuity is valid, and supporting Contexts are compatible. |
| Cross-paper synthesis | Several papers provide compatible, conflicting, or complementary results. | The answer groups evidence by Context and exposes contradictions. |
| Out-of-corpus transfer | A new place is described by measured environmental Facets. | Evidence is ranked by applicability; missing and mismatching Context are distinguished. |
| Spatial planning | Evidence and local geometry jointly permit or block a placement recommendation. | Placement is made only for a supported spatial relation family and includes limitations. |
| Unsupported request | Required evidence is absent or incompatible. | The system abstains from the unsupported conclusion and identifies the evidence gap. |

## Dataset design

Build a new locked 36-question set from papers and locations not used to tune
the query pipeline:

| Group | Questions |
|---|---:|
| Direct single-paper findings | 8 |
| Context-contrast questions, arranged as six pairs | 12 |
| Multi-Claim mechanism questions | 6 |
| Cross-paper conflict or synthesis questions | 4 |
| Out-of-corpus transfer or spatial-planning questions | 4 |
| Deliberately unsupported questions | 2 |

The current 30-question model-checked set becomes a development and regression
set. It must not be called a final held-out test because it has already guided
several implementation changes.

## Gold annotation

Gold data must come from the original PDFs and SourceBlocks, never from
ClimateKG Claims or a system answer. Each question records:

- atomic facts and their smallest sufficient SourceBlock sets;
- required Context conditions, analysis cases, scale, season, and direction;
- acceptable evidence alternatives when a paper repeats a result;
- required mechanism edges for chain questions;
- known contradictions and null findings;
- conclusions that are unsupported;
- for transfer questions, applicable, incompatible, and unknown conditions;
- human verifier and verification date.

For out-of-corpus locations there may be no single gold recommendation. Use an
expert-reviewed admissibility rubric: evidence selection, applicability,
constraint compliance, spatial support, and abstention are scored separately.

## Stage-level diagnostics

The three headline metrics are not enough for root-cause analysis. Preserve
the following diagnostics without combining them into one score:

- structured query-plan accuracy;
- source, target, analysis-case, location, and Facet recall;
- indexed-finding coverage before retrieval;
- candidate Claim and SourceBlock recall;
- Context applicability and known coverage;
- delivered evidence recall after budgeting;
- valid multi-Claim path rate;
- requested-outcome coverage;
- contradiction retrieval;
- cited-evidence recall;
- latency and token cost by stage.

Every failure is assigned to the earliest incorrect stage: annotation,
indexing, query planning, candidate retrieval, Context scoring, evidence
allocation, path construction, synthesis, or citation rendering.

## Ablations

Run the same locked cases through:

1. full ClimateKG;
2. ClimateKG without Context scoring;
3. ClimateKG without canonical-State path construction;
4. ClimateKG without contradictions and alternatives;
5. ClimateKG without geographic/environmental enrichment for transfer cases.

These ablations establish whether a measured gain comes from the Knowledge
Graph structure rather than the answer prompt or a larger evidence package.

## Fair baseline controls

- All systems receive the same PDF snapshot.
- Use the same generation model and decoding settings.
- Enforce the same delivered evidence and token budget.
- Let each system use its native retrieval representation.
- Require citations to canonical SourceBlocks for all systems.
- Hide system identity during answer review.
- Report results by capability group, not only as one macro average.
- Use paired bootstrap confidence intervals over questions.

## Claims that the evaluation can support

If successful, the evaluation can support statements such as:

- ClimateKG preserves Context qualifiers or supported mechanism chains more
  often than the baselines on the locked structured-reasoning suite.
- ClimateKG makes evidence applicability and evidence gaps more traceable.
- ClimateKG can produce literature-grounded candidate land-use scenarios for
  later expert or numerical-model testing.

It cannot by itself establish that a recommended land-use scenario is optimal
or that it will change local climate as predicted. That claim requires an
external validation stage such as expert assessment, observational comparison,
or WRF scenario experiments.

## Execution order

1. Human-verify the current 30-question regression set.
2. Complete the six missing indexing findings identified by the stage audit,
   using the ordinary extraction design rather than query-specific patches.
3. Build and freeze the 36-question capability set.
4. Run the three systems and ClimateKG ablations without mid-run tuning.
5. Perform blinded scientific review and stage-level root-cause analysis.
6. Report headline metrics, capability-stratified results, confidence
   intervals, latency, and all failures.

