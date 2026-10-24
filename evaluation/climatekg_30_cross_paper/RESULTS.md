# Results: 30 structured-reasoning questions

## Run identity

- Architecture: `experiment/candidate-context-rescore-v2`
- Evaluation branch: `evaluation/climatekg-30-cross-paper-v1`
- Base commit: `c2eb632`
- Graph: 115 papers, 1,217 Contexts, 3,460 Facets, and 1,729 Claims
- Query protocol: live query planning and parsing; no frozen QuerySpecs
- Questions completed: 30 / 30
- Sum of per-query latency: 3,931.2 seconds
- Mean per-query latency: 131.0 seconds

This is a diagnostic development suite. Its expected Claims were selected from the
indexed graph, so the results locate pipeline losses but are not a held-out scientific
accuracy estimate.

## Evidence flow

The 30 questions identified 167 diagnostic Claims that could contribute to complete
answers.

| Stage | Expected Claims retained | Recall |
|---|---:|---:|
| Candidate retrieval | 150 / 167 | 89.8% |
| Selected paths | 65 / 167 | 38.9% |
| Synthesis provenance | 49 / 167 | 29.3% |

Twenty-seven of 30 answers cited at least two papers. ClimateKG therefore does combine
papers, but it uses only a small part of the relevant structured evidence it retrieves.
The main loss occurs after candidate retrieval, especially during path selection. These
numbers are diagnostic: an alternative Claim can support a correct answer, and retaining
an expected Claim does not guarantee correct synthesis.

## Supplemental answer review

Qwen3.6-27B compared each answer with the reference expectation in six batches. The
judge used no hidden project context and did not verify citations against PDFs.

| Verdict | Questions |
|---|---:|
| Correct | 14 |
| Mostly correct | 7 |
| Partly correct | 6 |
| Incorrect | 3 |

Treat this as a triage signal for human review, not an independent evaluation. Exact
scores and explanations are in `results/judge/REPORT.md`.

## What worked

- `XPG002`, `XPG003`, `XPG004`, and `XPG014` handled irrigation cooling, moist-heat,
  drought, evaporative-fraction, and regional rainfall qualifications.
- `XPG018`, `XPG023`, `XPG024`, and `XPG025` preserved non-monotonic patch scale,
  wind-displaced convergence, forest edge effects, and the distinction between a scale
  threshold and an optimum.
- `XPG012` connected external land-use change, atmospheric moisture transport, and
  basin flow, including a sign reversal after terrestrial recycling was included.
- `XPG021` kept local patch responses separate from basin-scale deforestation thresholds.
- `XPG022` distinguished observational association from interventions and modeled causal
  pathways.
- `XPG029` and `XPG030` refused unsupported exact placement or universal irrigation
  recommendations.

## What failed

- `XPG009` retrieved four of six expected heterogeneity Claims, but none reached a path.
  The answer then said that the wet-to-dry moisture-pooling mechanism was unavailable.
- `XPG015` retrieved all eight expected forest-cloud Claims, but only two reached paths
  and one reached synthesis. The answer became a fragmented list rather than a
  cross-method synthesis.
- `XPG027` retrieved five of six expected Claims but recommended irrigation expansion in
  a limited-groundwater setting. The answer did not preserve the planning constraint or
  moist-heat risk.
- `XPG005`, `XPG006`, `XPG013`, `XPG016`, `XPG019`, and `XPG028` were judged partly
  correct because complementary mechanisms, regions, methods, diurnal distinctions, or
  transfer limitations were lost.

## Main bottlenecks

1. **Candidate-to-path loss.** Twenty-seven questions lost at least one diagnostic Claim
   between candidate retrieval and path construction. This is much larger than the
   initial retrieval loss.
2. **Ambiguous State mapping.** `STATE_MAPPING_AMBIGUOUS` appeared in 26 questions.
   Relevant direct Claims can be retrieved semantically but excluded when their generated
   endpoints do not connect to the selected canonical State seeds.
3. **Bounded evidence allocation.** Twelve questions lost expected Claims between paths
   and final synthesis. Cross-paper questions need complementary evidence, not only the
   highest-scoring interchangeable Claims.
4. **Constraint preservation.** The failed semi-arid planning answer shows that retrieval
   relevance alone is insufficient. User constraints such as limited water must remain a
   hard synthesis condition.
5. **Broad unresolved places.** Two questions initially aborted when the external
   gazetteer was unavailable. The evaluation branch now records the failure and retains
   unresolved spatial Context without inventing coordinates.

## Recommended next investigations

1. Trace `XPG009`, `XPG015`, and `XPG027` first. They isolate mechanism-path loss,
   cross-paper evidence allocation, and constraint violation respectively.
2. For each lost expected Claim, record its semantic rank, Context applicability,
   canonical endpoints, rejection rule, and the Claim that replaced it.
3. Test a minimal evidence selector that allocates slots by requested subquestion or
   mechanism role before score-based filling. Do not add another LLM repair call.
4. Separate a valid direct Claim from a graph path: a retrieved, applicable Claim should
   remain eligible evidence even when no multi-edge State path can be constructed.
5. Add a deterministic final constraint check for planning queries before the answer is
   accepted.

## Where to inspect

- Overall stage audit: `results/stage_audit/REPORT.md`
- Complete structured output: `results/stage_audit/responses_and_stage_audit.json`
- One readable trace per question: `results/stage_audit/questions/XPGxxx.md`
- Supplemental judge: `results/judge/REPORT.md`
- Raw prompts, responses, scores, and evidence:
  `climatekg/runtime/outputs/climatekg_30_cross_paper_v1/`
