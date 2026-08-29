# Combined Extraction v4.1: Heterogeneous Patch-Size Paper

## Scope

Paper:

`E:\Atharv\literature\literature_to_read\rule_types\Land_use\Heterogenous\atsc-jas-d-18-0196.1.pdf`

Title: *The Effect of Land Surface Heterogeneity and Background Wind on Shallow Cumulus Clouds and the Transition to Deeper Convection*

Cleaned non-reference input: 13,408 `o200k_base` tokens.

No-thinking output:

`climatekg/runtime/outputs/combined_v41_heterogeneous_patch_20260829/combined/`

Low-thinking replay:

`climatekg/runtime/outputs/combined_v41_heterogeneous_patch_low_20260829/combined/`

## No-Thinking Run

The v4.1 no-thinking run completed through final embeddings and Parquet/FAISS indexing in 254.4 seconds.

- Contexts: 9
- Facets: 13
- Transitions: 4
- Claims: 14
- States: 23
- SourceBlocks: 163
- Parquet relationships: 352
- Prompt tokens: 19,015
- Generated tokens: 6,044
- Completion: `done_reason: stop`

Exact request:

`data/P000001/extraction/small_paper/5003f9ed-8ba3-4c9b-aabe-aa7794453bf8.attempt0.request.json`

Raw response:

`data/P000001/extraction/small_paper/5003f9ed-8ba3-4c9b-aabe-aa7794453bf8.attempt0.json`

## What Worked

The technical v4.1 changes worked:

- every evidence handle was drawn from the request-local enum;
- every handle mapped deterministically to one permanent SourceBlock;
- Context and Transition Claim scopes were assigned from nesting;
- conditioning-Facet reachability passed;
- nested, flattened, final, and indexed object counts agreed;
- the response did not hit the context limit.

The output also preserved the broad scientific mechanism:

- large patches and weak wind support a mesoscale secondary circulation;
- vertical moisture transport creates a moisture pool over DRY patches;
- small patches do not produce the same convection transition;
- 1 m/s wind shifts but does not eliminate the HET14 circulation;
- wind at or above 2 m/s suppresses the secondary circulation;
- doubled heterogeneity amplitude increases circulation strength.

## Scientific Structure Lost

The Context hierarchy is too coarse for context-conditioned retrieval.

The model returned:

- one Context combining `HET5U0`, `HET7U0`, and `HET14U0`;
- one Context combining `HET1U0` and `HET2U0`;
- one Context combining all `U2`, `U3`, and `U10` cases;
- one homogeneous Context containing only `HOMU0`;
- one general doubled-amplitude Context.

It incorrectly put several distinct runs together in `aliases`, even though the prompt defines aliases as names for the same complete setting.

The output omitted separate Contexts for material reported cases including:

- `HET14U0`, `HET14U1`, and `HET14U2`;
- `HET7U0` and `HET7U0.5`;
- `HET5U0` as its own setting;
- `HOMU0_DRY` and `HOMU0_WET`;
- the separate `HET14_Ax2` and `HET7_Ax2` wind cases;
- several individually simulated patch-size and wind-speed combinations.

This information is present in the cleaned input:

- `P0028`: patch sizes 1.2, 2.4, 4.8, 7.2, and 14.4 km;
- `P0030`: `HOM`, `HOMU0_DRY`, and `HOMU0_WET`;
- `P0031`: wind values 0, 1, 2, 3, and 10 m/s;
- `P0036`: named transition cases `HET14U0`, `HET14U1`, `HET7U0`, and `HET5U0`;
- `P0042`: direct HET14 U0/U1/U2 comparison;
- `P0102`: the separately reported `HET7U0.5` result;
- `P0103`: HET14/HET7 doubled-amplitude sensitivity cases.

Therefore, the omission is not caused by Nemotron parsing, cleaning, evidence selection, or context-window truncation. The no-thinking model compressed settings that shared a broad outcome despite explicit complete-combination instructions.

This is a material failure for query applicability. A query about 14.4 km patches at 1 m/s versus 2 m/s cannot be gated against the output at the required granularity.

## Low-Thinking Replay

The low-thinking replay did not produce usable JSON.

Attempt 0 metrics:

- elapsed time: 535.0 seconds;
- prompt tokens: 32,411;
- generated tokens: 357;
- thinking characters: 44,282;
- final content characters: 1,212;
- completion: `done_reason: length`;
- validation error: JSON ended during the first Context.

Exact request:

`data/P000001/extraction/small_paper/a84f0dea-757e-4d63-98d7-b5c5a7779480.attempt0.request.json`

Raw response and thinking:

`data/P000001/extraction/small_paper/a84f0dea-757e-4d63-98d7-b5c5a7779480.attempt0.json`

The automatic schema-repair request was larger than the already truncated request and therefore had no possible output budget in the same 32K window. It was stopped rather than allowed to repeat a guaranteed truncation.

## Conclusion

The constrained v4.1 contract fixes invalid evidence IDs and arbitrary Claim scope references, but a single no-thinking call is not scientifically complete for this paper. Enabling thinking is not viable at this input size under the 32K context window.

This paper should not use the one-call route. It directly motivates the compact two-call route:

1. extract and validate only the complete experimental-setting hierarchy and setting-owned Facets;
2. extract Transitions and Claims using the validated Context/Facet registry and dynamically constrained scope choices.

That is not an open-ended repair call. It separates two dependent tasks so the second call can only use settings established by the first. Until that route is implemented and tested, structurally complex crossed-factor papers should use staged extraction.
