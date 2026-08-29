# Small-paper combined extraction experiment

## Question

Can a short paper be indexed with one Qwen3.6-27B call that returns Contexts,
Facets, Transitions, and Claims, instead of separate mapping, per-Context Facet,
and per-scope Claim calls?

## Implementation

Branch: `experiment/small-paper-single-call`

The experimental route:

1. accepts only cleaned, non-empty, non-reference SourceBlocks;
2. routes only papers at or below the configurable `8000` estimated-token limit;
3. sends one standalone prompt and one structured JSON Schema;
4. validates temporary IDs, Context acyclicity, Transition endpoints, Claim
   scopes, reachable conditioning Facets, and evidence SourceBlock IDs;
5. converts the response to the existing permanent Context, Facet, Transition,
   and Claim schemas;
6. continues through the existing reconciliation, consolidation, State,
   embedding, and graph stages.

There is no silent fallback to staged extraction after a combined-call failure.

The exact prompt is `prompts/small_paper_extraction.txt`. The benchmark-selected
thinking level is `low`; choose the existing `baseline` reasoning profile for a
full experimental index run. The Ollama context remains `32768`; all runs stayed on
the GPU without CPU spill.

## Test paper

`P000006`, *Afternoon rain more likely over drier soils*, was selected because:

- it has only `6299` cleaned estimated tokens in 34 non-reference SourceBlocks;
- it contains observational and model settings;
- it contains dry/wet and daytime/nighttime regimes;
- it contains sign reversal, threshold, mechanism, and resolution-sensitivity
  findings.

This is a short but scientifically dense paper, so it is a useful stress test.

## v1 reasoning matrix

| Thinking | Seconds | Contexts | Facets | Transitions | Claims | Result |
|---|---:|---:|---:|---:|---:|---|
| no | 244.22 | 6 | 10 | 2 | 7 | Valid, but incomplete comparison structure |
| low | 443.06 | 3 | 10 | 1 | 5 | Regimes compressed into Claim prose |
| medium | 339.56 | 3 | 5 | 3 | 6 | Failed: `T2` used the same endpoint twice |

Root cause from the saved thinking:

- `low` recognized dry/wet and daytime/nighttime, then classified them as
  analytical splits rather than study settings.
- `medium` considered child Contexts, then explicitly decided that the shared
  observational parent was acceptable as both Transition endpoints.

The failure was a structural decision error. It was not missing evidence,
context truncation, schema parsing, model loading, or CPU spill.

Artifacts:

`climatekg/runtime/outputs/small_paper_combined_p000006_20260829/`

## v2 reasoning matrix

v2 added a generic setting-coverage table: every separately analyzed value must
receive a Context, shared data/setup belongs in a parent, and every comparison
must connect two different value-specific Contexts.

| Thinking | Seconds | Contexts | Facets | Transitions | Claims | Result |
|---|---:|---:|---:|---:|---:|---|
| no | 128.41 | 6 | 8 | 2 | 6 | Regime Contexts present; dry/wet Transition absent |
| low | 617.71 | 7 | 14 | 3 | 5 | Expected regime structure |
| medium | 352.04 | 5 | 7 | 1 | 5 | Dry/wet regimes omitted |

The `medium` trace recognized the mean-soil-moisture sensitivity but kept it
inside an afternoon Context rather than creating threshold/regime children.
Only `low` followed the complete structural procedure.

Artifacts:

`climatekg/runtime/outputs/small_paper_combined_v2_p000006_20260829/`

## v3 low replay

v3 added an internal evidence ledger covering every current-paper finding,
null result, threshold, sensitivity/robustness result, and authors'
interpretation. It also made brief resolution checks and threshold sides
explicitly eligible as settings.

| Thinking | Seconds | Request tokens | Contexts | Facets | Transitions | Claims |
|---|---:|---:|---:|---:|---:|---:|
| low | 460.46 | 12176 estimated | 7 | 8 | 3 | 8 |

The resulting hierarchy correctly contained:

- observational and model branches;
- dry and wet children;
- daytime and nighttime children;
- observation/model, dry/wet, and daytime/nighttime Transitions.

Claim coverage improved from 5 to 8. It recovered the principal observational
finding, dry-surface mechanism, moisture threshold, diurnal reversal, model
opposite sign, model triggering explanation, and drought-persistence
interpretation.

Artifacts:

`climatekg/runtime/outputs/small_paper_combined_v3_p000006_20260829/`

## Remaining failure and root cause

v3 still omitted the paper's `0.25 degree` to `1.0 degree` resolution-
degradation experiment and its two reported results: reduced event count and
persistence of the dry-soil preference.

The v3 thinking mentions the observational resolution and cites the supporting
block, but the resolution experiment never enters its evidence ledger. This is
an attention/coverage omission inside the single large semantic task. ID and
schema validation cannot detect a scientific relationship that the model never
emitted.

This omission is scientifically material because it removes scale-dependent
transfer evidence. It is not safe to call the combined result equivalent to the
staged result.

## Timing conclusion

The v3 combined extraction call alone took `7.67 minutes`. The previous staged
P000006 benchmark took `9.29 minutes` end to end, although that particular
staged run also had an incomplete Context map. The combined route would still
need reconciliation, consolidation, State canonicalization, embeddings, and
graph output, so a meaningful end-to-end speed advantage was not demonstrated.

Higher context was unnecessary. The v3 request was about `12.2k` estimated
tokens and Ollama used the configured `32768` context entirely on GPU.

## Decision

The implementation remains available for research, but automatic combined
extraction is disabled by default through
`paper_mapping.combined_extraction_enabled`.

The failures have different severity:

- Self-Transition: doable; generic prompt rule plus deterministic validation
  fixed it.
- Regime compression: doable for this paper under `low`; the setting-coverage
  procedure fixed it.
- Missing non-headline scientific findings: fatal for treating one-call
  extraction as a faithful replacement at the tested threshold. Detecting this
  reliably requires an explicit auditable coverage object or focused evidence
  calls, which reduces the simplicity and speed benefit of the one-call design.

The staged extractor remains authoritative. A future experiment should use
genuinely simple papers, likely below `4000` cleaned tokens, and compare
relationship-level recall rather than object counts before enabling this route.

## Fresh v3 low/medium/high replay

A fresh three-call replay used the exact v3 prompt and the same 34 cleaned
non-reference SourceBlocks.

| Thinking request | Seconds | Contexts | Facets | Transitions | Claims | Thinking characters |
|---|---:|---:|---:|---:|---:|---:|
| low | 469.15 | 7 | 8 | 3 | 8 | 31498 |
| medium | 468.77 | 7 | 8 | 3 | 8 | 31498 |
| high | 468.81 | 7 | 8 | 3 | 8 | 31498 |

The request files are different and contain the requested `think` value:
`low`, `medium`, or `high`. However, all three raw responses have the same
thinking hash and content hash:

```text
thinking SHA-256 f656d244f9328095d63bd199d2216b0f0f2d8315bec1edb2a935970b3b9ad990
content  SHA-256 bfbf7a4a9fcb798e1ffe2d698b7c536bdc0102a6e99c31919b092b629e4f7de7
```

The local runtime was Ollama `0.32.9`; the model reports the `qwen3.5`
renderer/parser and the generic `thinking` capability. Empirically, this model
and runtime treated all three non-false levels identically for this request.
The experiment therefore does not demonstrate distinct low, medium, and high
reasoning intensities.

Because the structured output is byte-identical, all three levels retain the
same scientific strengths and the same omission: none recovers the
resolution-degradation experiment. `medium` and `high` provide no quality or
runtime advantage over `low` here.

Fresh replay artifacts:

`climatekg/runtime/outputs/small_paper_combined_v3_lmh_p000006_20260829/`
