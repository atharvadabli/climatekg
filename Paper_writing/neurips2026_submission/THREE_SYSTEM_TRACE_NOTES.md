# Three-System Trace Notes

These observations use the complete saved prompt, retrieval, thinking, and response files in `example_outputs/`. They cover the first two benchmark questions and should not be generalized to the full ten-query set.

## Q01: 14.4 km patches, zero wind

### PlainRAG

- Retrieved three highly relevant sections from the heterogeneity paper, but four of eight passages came from other studies.
- The answer nevertheless retained the correct comparison: heterogeneous forcing produced secondary circulations, deeper convection, and precipitation over dry patches, while the homogeneous case retained shallow clouds.
- Qwen's thinking explicitly checked each scientific sentence against an `S#` passage before answering.
- **Assessment:** workable retrieval-noise issue. Better chunk boundaries or a reranker can improve precision without changing the scientific representation.

### Community graph retrieval

- Retrieved all four expected Claims (`CL001`--`CL004`) plus one smaller-patch Claim.
- The answer correctly described deep convection over dry patches and the counterintuitive reduction in dry-wet near-surface temperature contrast.
- Qwen's thinking then introduced terrain, soil-feedback, stability, and wind-shear caveats that were not supplied as evidence records. Those caveats appeared without Claim citations in the final answer.
- **Assessment:** serious grounding flaw for a scientific system. Identifier-valid citations elsewhere do not make uncited clauses supported. The minimal remedy is structured statement-level Claim support and deterministic rejection of unsupported clauses, which ClimateKG already uses.

### ClimateKG

- Selected the four expected Claims plus four scale-related supporting Claims; no graph chain was forced because direct evidence answered the question.
- The structured synthesis used the four core Claims and the relevant threshold/variability Claims, while excluding the off-condition `0 -> 1 m/s` moisture Claim that had entered the wider candidate set.
- The answer retained zero wind, 14.4 km geometry, dry/wet patches, and the limit on spatial translation.
- **Assessment:** the broad candidate set is a ranking-precision issue, but the final gate and statement-level support prevented it from changing the answer.

## Q02: 14.4 km patches, wind increasing from 0 to 1 m/s

### PlainRAG

- Retrieved the correct paper but its top passages did not contain the precise convergence-location and cloud-advection findings.
- The answer used the available secondary-circulation and transition evidence, then explicitly stated that convergence and cloud movement were absent from the supplied passages.
- Expected-Claim retrieval/use was 2/5 under the benchmark mapping.
- **Assessment:** non-fatal and visible. The answer is incomplete but does not invent the missing relation.

### Community graph retrieval

- Retrieved four of five expected Claims: convergence shift, moisture variability, cloud advection, and retained deep-convection transition.
- The answer reconstructed the downwind-edge response, but again added real-world caveats not supported by the supplied Claim records.
- **Assessment:** retrieval is strong; generation grounding remains the important failure.

### ClimateKG

- Retrieved and used all five expected Claims (`CL013`--`CL017`).
- The answer separately preserved broken circulation symmetry, the downwind-edge convergence shift, downwind cloud advection, increased low-level moisture variability, and the retained convection transition because 1 m/s remained below the approximately 1.5 m/s potential circulation strength.
- Every answer paragraph was rendered from returned Claim IDs, with paper and page references.
- **Assessment:** successful case trace. It demonstrates the intended behavior but is not by itself evidence of corpus-wide superiority.

## Metric Limits

- Expected Claim IDs were prepared from the same indexed corpus. The benchmark tests retrieval and use of known indexed evidence, not extraction completeness.
- Citation identifier validity checks that a citation resolves to supplied evidence; it does not prove that every clause is entailed.
- Full scientific accuracy still requires independent source-level annotation and clause-level review.
