# Combined Extraction Failure RCA

## Scope

This report explains why `P000005`, `P000007`, and `P000010` were rejected in the ten-paper combined-extraction run. The staged run was stopped before any paper completed.

Original run:

`climatekg/runtime/outputs/combined_vs_staged_10_20260829/combined/`

Low-thinking replay:

`climatekg/runtime/outputs/combined_failure_rca_low_20260829/combined/`

The replay used the same Nemotron parse, cleaned text, SourceBlocks, and combined prompt. It changed only Ollama `think` from `false` to `low` and did not overwrite the original outputs.

## Where Rejection Happens

Ollama first returns JSON that is validated against the Pydantic output schema in `climatekg/ollama.py:94`. All three original responses passed that schema validation.

The combined extractor then runs graph- and provenance-aware checks in `climatekg/small_paper.py:28`. Existing SourceBlock membership is checked at lines 65, 70, 76, and 88. Conditioning-facet reachability is checked at line 87. The validated-schema artifact is written at line 148, and the stricter check runs at line 149.

Therefore, `attempt0.metrics.json` says `validated: true` because the JSON schema passed. The paper can still be rejected by the subsequent scientific-object consistency checks. This status label should eventually be made less ambiguous.

## Context Window and Thinking

None of the original calls hit the context limit. Every response has `done: true` and `done_reason: stop`.

| Paper | Prompt tokens | Generated tokens | Sum | Context window | Thinking chars |
|---|---:|---:|---:|---:|---:|
| `P000005` | 19,685 | 3,526 | 23,211 | 32,768 | 0 |
| `P000007` | 13,720 | 4,159 | 17,879 | 32,768 | 0 |
| `P000010` | 8,820 | 5,386 | 14,206 | 32,768 | 0 |

The original requests used `think: false`, so no hidden reasoning text exists for them.

## P000005

### Exact rejection

`Context C4 has missing or invalid evidence SourceBlock IDs`

The response emitted:

- `C4`: `P000005:S02:P0012` and valid `P000005:S05:P0066`
- `F1`: `P000005:S02:P0013`

Neither section-2 ID exists. The paper contains ordinals `P0012` and `P0013`, but their full IDs are `P000005:S01:P0012` and `P000005:S01:P0013`; both are author-affiliation footnotes and do not support these objects. The actual section-2 IDs in the prompt run from `P0022` to `P0032`. The model retained small paragraph ordinals while inventing the section prefix.

This is not a fuzzy semantic-match failure. SourceBlock IDs are exact database keys, and accepting a nonexistent key would break provenance.

Original raw response:

`climatekg/runtime/outputs/combined_vs_staged_10_20260829/combined/data/P000005/extraction/small_paper/28f6b843-7808-4f78-8711-35d994d50c43.attempt0.json`

### Low-thinking replay

The replay passed. Its thinking explicitly performed a final evidence-ID and conditioning-facet check. It took 352.4 seconds for the combined LLM call and produced 19,876 thinking characters. Its reported prompt plus generated tokens were 29,097, still followed by `done_reason: stop`.

Replay raw response:

`climatekg/runtime/outputs/combined_failure_rca_low_20260829/combined/data/P000005/extraction/small_paper/32ef1aa5-b854-4551-b2e6-f338a52feadf.attempt0.json`

## P000007

### Exact rejection

`Context C1 has missing or invalid evidence SourceBlock IDs`

The response emitted `P000007:S08:P0114`. That full ID does not exist. The actual paragraph ordinal exists as `P000007:S14:P0114`, a Methods block. Section 8 in the prompt contains only `P0038` to `P0040`. The context already cited directly relevant valid blocks `P0006` and `P0007`.

Again, the model transposed one component of an opaque composite ID. This occurred below the preferred 8,000-token target, so paper length alone does not explain the error.

Original raw response:

`climatekg/runtime/outputs/combined_vs_staged_10_20260829/combined/data/P000007/extraction/small_paper/9d5f9ba1-bc11-4955-beb8-3173ddb1808e.attempt0.json`

### Low-thinking replay

Thinking corrected the SourceBlock-ID error but produced a different structural error:

`Claim CL9 references an unreachable conditioning Facet`

The model created four sibling contexts under `C1`:

- `C9`: rainfed, drought
- `C10`: rainfed, non-drought
- `C11`: irrigated, drought
- `C12`: irrigated, non-drought

It attached drought facets `F12` and `F13` to the rainfed siblings `C9` and `C10`, then used those facets on transition `T4`, whose endpoints are the irrigated siblings `C12` and `C11`. Those facets are not ancestors of either endpoint and are therefore unreachable.

The thinking trace says “all looks consistent” and lists the facets for `CL9`, but never performs a reachability calculation. The validator correctly rejects this graph. The issue is hierarchy factorization and facet placement, not string matching.

Replay raw response:

`climatekg/runtime/outputs/combined_failure_rca_low_20260829/combined/data/P000007/extraction/small_paper/8dfabfbe-bd2f-49d5-8841-312bf6cd4dc1.attempt0.json`

## P000010

### Exact rejection

`Claim CL8 references an unreachable conditioning Facet`

The response correctly created:

- `C8`: 45% solar-panel efficiency
- `C9`: 30% solar-panel efficiency
- `F5`: the 30% condition attached to `C9`

But `CL8`, which describes the 30% result and uses `F5`, was scoped to `T3`. `T3` compares `C4` (15%) with `C8` (45%). Context `C9` is not an endpoint or ancestor of that transition, so its facet cannot condition `CL8` there.

This is a wrong cross-object reference. The scientific content and evidence IDs are present, but the claim points to the wrong transition.

Original raw response:

`climatekg/runtime/outputs/combined_vs_staged_10_20260829/combined/data/P000010/extraction/small_paper/ff692629-4e65-43db-be0e-7c8a397cc4e1.attempt0.json`

### Low-thinking replay

The replay passed by creating `T4` from the 15% context `C6` to the 30% context `C8`, attaching the 30% facet `F7` to `C8`, and scoping the 30% claim to `T4`.

This call took 776.7 seconds and produced 49,000 thinking characters. Reported prompt plus generated tokens were 30,949 of 32,768. It still ended with `done_reason: stop`, but the small remaining headroom shows why enabled thinking is risky for larger combined inputs.

Replay raw response:

`climatekg/runtime/outputs/combined_failure_rca_low_20260829/combined/data/P000010/extraction/small_paper/1ff81de2-10e2-47c6-9562-6b5c6cc906de.attempt0.json`

## Root Cause

The validator is behaving correctly. The combined prompt asks one generation to create a hierarchy and many mutually referential objects while copying opaque composite evidence IDs. JSON Schema can validate field shapes and enumerations, but cannot enforce that:

1. every evidence ID occurs in the supplied paper;
2. every conditioning facet is reachable through the chosen context hierarchy;
3. a claim about one experimental setting is attached to the transition containing that setting.

No-thinking generation failed twice on ID transcription and once on graph linkage. Enabled thinking fixed two papers but still failed the most contextually combinatorial paper, while increasing runtime from about 2.5-3.4 minutes to 6-13 minutes per paper.

The failures should not be bypassed by weakening exact ID checks. They protect traceability. The design problem is that the model must reproduce and join too many opaque IDs correctly in one large output.

## Next Decision

Do not add another generic “improve this output” call. The smallest principled options to test are:

1. replace long composite SourceBlock IDs in the LLM input with short call-local evidence handles and deterministically map them back afterward;
2. generate the context hierarchy first, then deterministically constrain valid facet and claim scope choices in the combined response;
3. represent crossed factors such as water source by drought regime as explicit combination contexts, so conditioning facets belong to the actual claim scope;
4. make post-schema consistency failure a visible typed result and, only if desired, retry the same task with the exact failed constraint rather than an open-ended improvement prompt.

These are pipeline-contract changes and should be evaluated separately. No such repair was applied in this RCA.
