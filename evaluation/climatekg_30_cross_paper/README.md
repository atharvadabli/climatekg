# ClimateKG 30-question structured-reasoning evaluation

This is a diagnostic development suite for `experiment/candidate-context-rescore-v2`.
It is designed to exercise the parts of ClimateKG that passage retrieval alone does
not represent explicitly: environmental conditions, regime changes, cross-paper
agreement and disagreement, mechanism chains, spatial relations, evidence transfer,
and justified abstention.

It is **not** a held-out scientific benchmark. Expected Claims were selected from
the indexed graph, so the suite tests whether query planning, retrieval, Context
scoring, path construction, evidence allocation, and synthesis can recover and use
knowledge already present in ClimateKG. Scientific conclusions must still be checked
against the cited SourceBlocks and original PDFs.

## Composition

| Capability | Questions |
|---|---:|
| Context and regime contrasts | 6 |
| Multi-Claim mechanisms | 7 |
| Cross-paper synthesis or conflict | 9 |
| Spatial and scale reasoning | 4 |
| Transfer and evidence boundaries | 4 |
| **Total** | **30** |

Most questions require evidence from at least two papers. A few focused questions
are retained as controls for Context, scale, and wind handling.

## Run

From this worktree:

```powershell
.\evaluation\climatekg_30_cross_paper\run.ps1
```

The run uses the 115-paper patched Parquet graph and live query planning. It writes
all generated artifacts to:

```text
climatekg/runtime/outputs/climatekg_30_cross_paper_v1/
```

Each question retains the exact LLM request and response, parsed QuerySpec,
retrieval report, Context and Claim scores, paths, evidence package, citations,
stage events, answer, and timing. Re-running without `-Force` resumes completed
questions.

The completed compact reports are tracked under `results/`. Start with
`RESULTS.md`, then open `results/stage_audit/REPORT.md` and the linked question
file. The larger raw traces remain in the runtime output directory above.

## Interpretation

The expected Claims are diagnostic targets, not an instruction supplied to the
retrieval system. A valid answer may use other directly supporting Claims. Failure
analysis assigns the earliest incorrect stage among:

1. query planning;
2. candidate retrieval;
3. Context scoring or gating;
4. Claim scoring;
5. path construction;
6. evidence allocation;
7. synthesis;
8. citation rendering.

Do not use lexical answer overlap as the main conclusion. Review whether the answer
preserves conditions, distinguishes disagreement from missing information, cites
every substantive statement, and avoids location-specific recommendations that the
evidence cannot support.
