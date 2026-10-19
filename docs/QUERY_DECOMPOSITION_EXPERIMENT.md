# Query Decomposition Experiment

## Purpose

The 30-query benchmark showed that ClimateKG sometimes lost one part of a multi-part question when all
requested findings shared one query representation and one bounded evidence package. This experiment
tests whether separately retrieving independently answerable parts improves the grounded answer.

Branch: `experiment/query-decomposition-v1`

## Architecture

The query planner returns one operation:

```text
retrieve | enumerate | compare | join | aggregate | select
```

It produces standalone subqueries only when multiple evidence searches are required. Each subquery
runs through the unchanged ClimateKG parse, embedding, Context retrieval, Claim ranking, Context gate,
path search, evidence selection, and grounded synthesis stages. A final Qwen call recomposes only the
validated answer items and Claim IDs from those runs.

For dependent `join` questions, later retrieval reserves three direct-evidence positions for Claims
from the paper supporting the earlier primary direct finding. This is not a paper-only filter; the
remaining evidence positions still use full-corpus retrieval.

## Decomposition Audit

Qwen classified the 30 benchmark questions in 110.5 seconds, averaging 3.64 seconds per question:

| Operation | Questions |
|---|---:|
| Retrieve | 14 |
| Enumerate | 6 |
| Compare | 9 |
| Join | 1 |

Sixteen questions contained more than one independently retrievable part. Manual inspection found the
plans scientifically reasonable. One comparison containing two regimes and two outcomes exposed the
need for atomic case-outcome combinations; decomposition prompt version 2 introduced that rule.
Version 3 makes the exact standalone JSON response shape explicit without changing the decision rule.

## Five-Query Result

The test set contains a regime comparison, a three-outcome mechanism question, two multi-outcome
direct-finding questions, and one dependent join. A blinded Qwen review compared old and decomposed
answers against the existing reference answers.

| Case | Pattern | Baseline correctness | Decomposed correctness | Result |
|---|---|---:|---:|---|
| CKGQ0001 | wet versus dry years | 0/4 | 1/4 | Still limited by missing indexed dry-year evidence |
| CKGQ0003 | circulation, clouds, rainfall | 4/4 | 4/4 | No regression; decomposed answer was more concise |
| CKGQ0009 | daytime, nighttime, heat-wave duration | 1/4 | 4/4 | Recovered all three requested findings |
| CKGQ0029 | humidity and precipitation | 2/4 | 4/4 | Recovered the quantified precipitation finding |
| CKGQ0032 | evaporation regions joined to Himalayan rainfall | 1/4 | 4/4 | Recovered both Claims and the supported link |

Mean blinded scores:

| System | Correctness /4 | Completeness /4 | Directness /2 |
|---|---:|---:|---:|
| Previous ClimateKG | 1.6 | 1.6 | 0.6 |
| Decomposed ClimateKG | 3.4 | 3.4 | 1.8 |

The median latency increased from 171.6 seconds to 551.5 seconds, about 3.2 times slower. The current
implementation executes subqueries sequentially and performs a complete synthesis for every subquery
before recomposition. The quality result justifies keeping the architecture experiment, but this
execution strategy is not efficient enough for production.

## Failure Analysis

`CKGQ0001` did not become correct. Decomposition produced valid wet-year and dry-year searches, but the
indexed graph used by this benchmark does not contain the required dry-year finding. The wet-year run
also admitted unrelated Amazon wet-period evidence. Query decomposition cannot recover scientific
content absent from the index. The correct next action is to rebuild and audit the relevant paper with
the newer analysis-case extraction, then retest; adding more query-prompt wording would hide the root
cause.

The original `CKGQ0032` run retrieved `P000082_CL005` with high semantic similarity but placed it ninth,
outside the eight direct-evidence positions. Using every citation from the preceding subquery as a
dependency was also too broad. Restricting dependency propagation to the paper supporting the first
grounded direct finding placed `P000082_CL005` first while preserving cross-corpus candidates.

## Artifacts

Generated artifacts are outside Git:

```text
evaluation/output/query_decomposition_v1/planning_30/
evaluation/output/query_decomposition_v1/variants/decomp_eval4/
evaluation/output/query_decomposition_v1/variants/decomp_v2/
evaluation/output/query_decomposition_v1/blinded_judge_5/
```

Every compound query contains the decomposition request/response, one complete query report per
subquery, the recomposition request/response, and the final combined report.

## Decision

Keep decomposition as an experimental architecture because it substantially improves multi-part
retrieval completeness. Do not treat it as the default production path until:

1. the analysis-case index is rebuilt and `CKGQ0001` is retested;
2. subquery retrieval is parallelized;
3. intermediate per-subquery generation is removed so one final grounded synthesis call is sufficient;
4. the full 30-query benchmark confirms no atomic-query regression.
