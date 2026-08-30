# Query retrieval redesign experiment

Branch: `experiment/query-evidence-path-redesign`

The experiment changes retrieval in three bounded steps. Each step is tested before the next is applied. The frozen evaluation queries are Q1 heterogeneous patches, Q2 Rondonia season/wind response, and Q3 Rajasthan transfer.

## Baseline

For Q2, Context and Claim retrieval succeeded: all 33 `P000019` Claims entered the 200-Claim candidate set. Exact forward traversal nevertheless started only from `state::deforestation::land_cover_change`. The relevant Claims used generated endpoints such as `land cover pattern [observed deforestation]`, so none were reachable. Four generic `P000002` paths became the complete synthesis package.

Baseline Q2 synthesis evidence:

```text
P000002_CL005
P000002_CL004
P000002_CL006
P000002_CL004 -> P000002_CL007
```

The final Qwen response correctly reported that the supplied evidence did not contain the requested seasons or synoptic-wind comparison.

## Change 1: direct evidence and graph paths are separate lanes

Design:

- Claim ANN and transition retrieval define query-focused direct evidence.
- When the query supplies Context, a direct Claim must have known Context applicability.
- The highest-ranked eight direct Claims are retained as single-Claim paths.
- Up to four State-connected graph paths are retained separately.
- Exact State traversal can organize or extend evidence, but cannot erase a relevant Claim solely because its generated endpoint wording differs.

This follows the useful part of HippoRAG's retrieval design: query-relevant facts seed retrieval, while graph structure propagates from them. It does not adopt iterative LLM search or trial-and-error fallbacks.

Results:

- Deterministic tests: `40 passed` in 1.17 seconds.
- Full Q2 run: `Q2_CHANGE1`, saved under
  `climatekg/runtime/outputs/query_evidence_path_redesign/change_1/`.
- Query parsing: 19.87 seconds, 863 prompt tokens, 273 output tokens.
- Final synthesis: 269.74 seconds, 21,630 model-reported prompt tokens, 1,443 output tokens.
- The eight direct slots contained only `P000019` Claims:
  `CL009`, `CL012`, `CL011`, `CL008`, `CL001`, `CL014`, `CL002`, and
  `CL019`.
- These Claims cover rainy-season original and weakened wind cases, the break
  period, and the second and third dry-season days. The answer therefore
  addressed all three periods and the role of synoptic wind with exact paper,
  page, Claim, and SourceBlock provenance.
- The alternative-evidence stage also surfaced `P000019_CL018`, preserving the
  first-dry-season-afternoon result that differs from later dry-season days.

Assessment: successful at preventing evidence loss. The generic `P000002`
State-seeded paths still occupied all four graph slots. They were no longer able
to replace direct evidence, but graph search itself remained query-insensitive.
That remaining failure is the target of Change 2.

Observed warning: `UNSUPPORTED_SYNTHESIS_ITEM`. The structured synthesis
validator removed one item whose cited support was not present in the supplied
evidence. This did not remove any of the supported seasonal findings.
