# Complete-Setting Prompt v11

## Purpose

This candidate removes an ambiguity found by comparing two medium-thinking Qwen3.6-27B runs on
the same paper-map request. One run preserved condition-specific regimes and one acknowledged them
but removed them as sensitivity analyses.

The candidate defines a study setting from the complete combination of conditions directly
analyzed by the paper. Result direction is not part of the setting-identity decision.

## Decision Rule

- Preserve every directly analyzed combination of area, setup, time, season, treatment, forcing,
  and environmental regime.
- Use parents for conditions shared by multiple analyzed combinations.
- Keep combinations separate even when their results are equal, similar, or null.
- Always preserve supported sign reversals, effect/null changes, thresholds, and material
  applicability changes as separate condition branches.
- Do not invent combinations that the paper did not analyze.
- Treat a sweep/range/list as a family parent when its stated values are evaluated individually;
  preserve each evaluated value as a complete child.
- Do not turn a group defined only by its observed outcome into a setting unless the paper then
  analyzes that group under additional conditions.

## Status

Candidate only. The active 50-paper v10 benchmark reads the production prompt at each paper, so
these files remain separate to avoid mixing prompt versions. Promote both candidate files and bump
their prompt versions only after replaying P000006 and at least two unrelated paper structures.
