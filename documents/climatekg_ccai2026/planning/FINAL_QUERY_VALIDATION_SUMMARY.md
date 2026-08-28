# Final Graph-Backed Query Validation Summary

## Result

All ten validation questions have a passing final run against the Neo4j graph built from the ten finalized papers.

The final results are split across focused rerun directories. This is intentional: failed runs were preserved, each demonstrated defect was repaired, and only affected queries were rerun. The table below is the authoritative index of the latest passing artifact for each query.

The validated corpus contains:

- 10 Papers;
- 2,184 SourceBlocks;
- 101 Contexts;
- 437 Facets;
- 51 Transitions;
- 213 Claims;
- 314 per-paper canonical State records after the final alias refresh.

All 28 deterministic unit and boundary tests pass.

## Passing Query Artifacts

| Query | Type | Mode | Facets | Candidates | Paths | Blocks | Grounded items | Final run |
|---|---|---:|---:|---:|---:|---:|---:|---|
| QGEN001 | generic | global | 0 | 200 | 20 | 9 | 15 | `query-suite-20260824T153002Z` |
| QGEN002 | generic | global | 0 | 200 | 20 | 13 | 8 | `query-suite-20260824T145941Z` |
| QGEN003 | generic | global | 0 | 200 | 20 | 11 | 8 | `query-suite-20260824T153002Z` |
| QCTX001 | Context | A-to-B | 3 | 200 | 5 | 13 | 5 | `query-suite-20260824T145454Z` |
| QCTX002 | Context | A-to-B | 4 | 200 | 8 | 12 | 7 | `query-suite-20260824T145941Z` |
| QCTX003 | Context | A-to-B | 3 | 200 | 1 | 2 | 4 | `query-suite-20260824T153831Z` |
| QCTX004 | comparison | global plus Context gate | 3 | 200 | 20 | 20 | 4 | `query-suite-20260824T155834Z` |
| QCTX005 | Context | forward | 1 | 200 | 9 | 9 | 3 | `query-suite-20260824T145941Z` |
| QCTX006 | Context | A-to-B | 4 | 200 | 2 | 5 | 3 | `query-suite-20260824T153831Z` |
| QSPA001 | spatial | global plus Context gate | 2 | 111 | 20 | 11 | 3 | `query-suite-20260824T154803Z` |

`Blocks` is the number of retained evidence SourceBlocks. `Grounded items` is the number of synthesis items that passed deterministic provenance validation.

## Review Paths

The common root is:

```text
climatekg/runtime/outputs/query_validation/
```

For each query, open the listed directory and review `answer.md`, then `query_report.json`, then `stage_events.jsonl`.

| Query | Artifact directory |
|---|---|
| QGEN001 | `query-suite-20260824T153002Z/queries/QGEN001/` |
| QGEN002 | `query-suite-20260824T145941Z/queries/QGEN002/` |
| QGEN003 | `query-suite-20260824T153002Z/queries/QGEN003/` |
| QCTX001 | `query-suite-20260824T145454Z/queries/QCTX001/` |
| QCTX002 | `query-suite-20260824T145941Z/queries/QCTX002/` |
| QCTX003 | `query-suite-20260824T153831Z/queries/QCTX003/` |
| QCTX004 | `query-suite-20260824T155834Z/queries/QCTX004/` |
| QCTX005 | `query-suite-20260824T145941Z/queries/QCTX005/` |
| QCTX006 | `query-suite-20260824T153831Z/queries/QCTX006/` |
| QSPA001 | `query-suite-20260824T154803Z/queries/QSPA001/` |

Each query directory contains the parsed QuerySpec, full report, local-model request and response envelopes, selected evidence, final answer, and an ordered event log.

## Failures Found and Repaired

### Neo4j startup readiness

The first script checked only whether ports 7474 and 7687 were open. Neo4j could open those ports before the transaction endpoint accepted requests. The script now waits for an authenticated `RETURN 1` Cypher request.

### Neo4j 5.26 query syntax

Neo4j 5.26 rejected ordering on a property that was not returned after `DISTINCT`. Graph read-back now orders the returned map by `item.id`.

### Obsolete canonical States remained after re-ingestion

Paper replacement preserves shared State nodes, so State aliases changed during validation left 17 unreferenced nodes. The ingestion transaction now removes only States with no incoming Claim `FROM` or `TO` relationship. The final graph has 314 State nodes and no orphan States.

### Missing explicit query Context

The local parser sometimes omitted conditions stated in the opening phrase. A dedicated required-Facet repair request now extracts exact-span Context Facets. Invalid items are discarded individually.

### Query vectors consumed the evidence budget

Runtime 2,048-dimensional query vectors were being serialized into the synthesis package. They are now removed before budget counting and synthesis.

### Broad outcome words became false States

Words such as `reported` and `effects` were parsed as endpoint directions. These relation words now leave broad targets unspecified, allowing global semantic retrieval.

### Verified State identities were fragmented

Corpus evidence showed several true identities that were split by surface wording:

- `surface temperature` and `near-surface air temperature` now map to `surface air temperature`;
- `afternoon convective precipitation | increased likelihood of occurrence` maps to `convective precipitation | more_frequent`;
- Paper 15's location and magnitude wording is kept in Context or description while endpoints map to `surface albedo | increase` and `precipitation | decrease`.

Every State refresh backed up the previous `final_paper.json` and wrote `state_recanonicalization.json`.

### Place name duplicated as a Facet

`US Midwest` was represented both as SpatialSupport and as a `spatial_configuration` Facet. The duplicate Facet blocked the correct Paper 7 Contexts. A pure place name is now removed from Facets when the same text is already SpatialSupport.

### Comparative query lost one side

`drier or wetter` was first treated as one source State. After clearing it, exact target traversal still selected only the wetter-soil model Claim. Comparative questions now leave both endpoints open and add high-ranked, context-applicable omitted Claims through the alternative-evidence channel. QCTX004 also requires one grounded Claim from each scientific side before it can pass.

### Spatial relation became a false endpoint

`where relative to dry and wet patch edges` was treated as a target State. `Where` relations now remain spatial retrieval constraints. QSPA001 retrieves dry-patch initiation evidence but does not invent an exact edge position or cardinal direction that the evidence does not provide.

## Remaining Research Work

This is an implementation and traceability validation, not a complete scientific evaluation. Before publication, the following still matter:

- expert review of all ten final answers and their SourceBlocks;
- a manually maintained expected-invariants set for each benchmark paper;
- retrieval baselines and ablations;
- quantitative retrieval metrics over a larger query set;
- comparison with non-context-gated GraphRAG and vector-only retrieval;
- review of text encoding artifacts such as malformed scientific units in a small number of rendered answers;
- repeated-run stability measurements for the local generative stages;
- evaluation on held-out papers and questions.

The complete plain-language execution description is in `TECHNICAL_PIPELINE_WALKTHROUGH.md`. The authoritative algorithms remain the two pipeline specifications at the repository root.
