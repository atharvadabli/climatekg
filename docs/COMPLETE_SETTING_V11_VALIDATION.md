# Complete-Setting Prompt v11 Validation

## Reason For The Change

Two medium-thinking Qwen3.6-27B calls received byte-identical P000006 paper-map requests. Both
recognized dry/wet soil-moisture regimes and the daytime/nighttime reversal. One produced seven
Contexts; the other deliberately reduced the map to three Contexts because it treated the regimes
as sensitivity analyses rather than study settings.

The v10 prompt contained competing rules: preserve separately analyzed regimes, but create a
regime setting only when it supports multiple findings. That made setting identity depend partly on
the number or difference of results rather than on the conditions defining applicability.

## V11 Rule

A complete study setting is one combination of conditions directly analyzed by the paper.

- Shared conditions belong in parents.
- Every directly analyzed site, setup, period, season, regime, treatment, named run, and variable
  value combination is preserved as a complete leaf.
- Similar, equal, or null results do not merge settings.
- A list, range, sweep, or ensemble is a family parent when its values are evaluated individually.
- Only combinations analyzed by the paper are created; no Cartesian product is invented.
- Groups named only by their observed outcome remain results unless the paper then analyzes those
  groups under additional conditions.

The production prompts are standalone Qwen3.6-27B prompts and contain no benchmark-paper names or
identifiers.

## Controlled Replays

Each replay reused the exact original user message, evidence, JSON Schema, model, temperature 0,
and medium thinking. Only the system prompt changed.

| Paper | Structure tested | Result | Runtime |
|---|---|---:|---:|
| `P000006` | condition-defined dry/wet and day/night regimes | 7 Contexts, 3 Transitions | 323.86 s |
| `P000001` | simulation sensitivity values under a shared RAMS setup | 16 Contexts, 4 Transitions | 536.95 s |
| `P000003` | coupled/offline, irrigation, soil-column, and timing combinations | 13 Contexts, 6 Transitions | 384.00 s |

### P000006

The tree contains an observational parent with dry, wet, daytime, and nighttime children, plus a
model branch. The thinking explicitly says these are stratification conditions and rejects an
unobserved cross-product.

### P000001

The first candidate wording still collapsed the seven rotor-TKE values into one sensitivity leaf,
despite listing every value in its thinking. The prompt was tightened so a list/range of
individually evaluated values is a family parent. The second replay produced children for 0, 0.5,
1, 2, 5, 10, and 15 m2/s2 under the shared sensitivity parent.

### P000003

The long-paper consolidation produced shared parents for separate versus single soil-column
configurations and complete leaves for all named coupled/offline control, irrigation, and timing
runs. It resolved the full scout inventory and added the supported offline irrigation-versus-control
comparison without inventing experiment combinations.

## Artifacts

- `climatekg/runtime/outputs/p000006_map_v11_replay_20260829`
- `climatekg/runtime/outputs/p000001_map_v11b_replay_20260829`
- `climatekg/runtime/outputs/p000003_map_v11_replay_20260829`

Each directory contains the exact request, full Qwen thinking, raw response, validated JSON, and
rendered setting tree.

## Benchmark Boundary

The v10 50-paper run was stopped after 20 attempted papers so prompt versions would not be mixed in
one benchmark. Its artifacts remain unchanged under
`climatekg/runtime/outputs/indexing_50_medium_map_20260829`. A new v11 corpus run must use a new
output directory.
