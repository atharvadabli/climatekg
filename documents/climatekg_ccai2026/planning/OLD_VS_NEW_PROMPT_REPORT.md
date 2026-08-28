# Old vs New Indexing Prompts: One-Paper Comparison

## Scope

This report compares two indexing runs of the same paper:

> *The Effect of Land Surface Heterogeneity and Background Wind on Shallow Cumulus Clouds and the Transition to Deeper Convection*

Both runs used the same PDF SHA-256 (`af33f2e...82616`), NVIDIA Nemotron Parse v1.2 output, `qwen3.6:27b`, embedding model, and pipeline version. This controls the document and model, but it is still only one generation per prompt version. Differences may include sampling variation as well as prompt effects.

- Old run: `climatekg/runtime/prompt_examples/atsc-jas-d-18-0196-1/papers/P000001/`
- New run: `climatekg/runtime/prompt_examples/atsc-jas-d-18-0196-1/v2/papers/P000001/`
- New exact rendered requests: `climatekg/runtime/prompt_examples/atsc-jas-d-18-0196-1/v2/actual_prompts/`

The old envelopes identify each prompt as v1 and preserve its raw response. Exact old request payloads were not captured, so old prompt-input rendering cannot be audited as precisely as v2.

## Overall Result

| Measure | Old prompts | New prompts |
|---|---:|---:|
| Pipeline status | `NEEDS_REVIEW` | `complete` |
| Contexts mapped | 8 | 9 |
| Transitions mapped | 1 | 4 |
| Global Claim seed blocks | 0 | 28 |
| Facets produced before stopping / final | 16 | 37 |
| Claims | not reached | 21 |
| Canonical States | not reached | 36 |
| LLM elapsed time | 650.5 s before failure | 1,987.9 s to completion |

**Overall observation:** the new prompts are substantially better at completing the pipeline, populating required seed fields, and representing the paper's experimental comparisons. They are not yet uniformly better at scientific scoping. The largest remaining problems are the flattened Context structure, outcome leakage into Facets, and incomplete scheduling of non-Transition Claims.

## 1. Section Scouting

**Prompts:** `section_scout_v1` versus `prompts/section_scout.txt` (`section_scout_v2`). Both runs processed the same three SourceBlock ranges.

| Raw response totals across three sections | Old | New |
|---|---:|---:|
| Context mentions | 20 | 35 |
| Location mentions | 9 | 11 |
| Comparison mentions | 14 | 14 |
| Facet seed IDs | 0 | 14 |
| Claim seed IDs | 4 | 28 |
| Cross-references | 31 | 38 |
| Ambiguities | 9 | 4 |

What improved:

- The new prompt reliably populated both seed-ID fields. All three old scout responses omitted `facet_seed_block_ids`; two also omitted `claim_seed_block_ids`. Schema defaults turned those omissions into empty lists, hiding the loss.
- New scouts identified more concrete simulation cases and retained more directly useful result passages.
- The task is more self-contained: the v2 response structure follows the prompt's real-world definitions rather than relying on pipeline terminology.

Remaining concern:

- The drop from nine to four ambiguities is not automatically an accuracy gain. Several old uncertainties, including uncertainty around the `Uc0` threshold and homogeneous control definition, disappeared rather than being resolved by new evidence.

## 2. Study-Setting Map

**Prompts:** `map_consolidation_v1` versus `prompts/map_consolidation.txt` (`map_consolidation_v2` in this recorded run).

What improved:

- The old map had one Transition that combined patch size, background wind, convection regime, moisture pooling, and an outcome. The new map separated four comparisons: heterogeneous versus homogeneous surface, zero versus nonzero wind, large versus small patches, and transition versus nontransition cases.
- The old map incorrectly treated scientific processes or analysis views as Contexts, including “Mesoscale Secondary Circulation Dynamics,” “Mesoscale vs. Turbulent Scale Contributions,” and “Subcloud Moisture Anomaly and Pooling.” The new map mostly uses experimental settings and regimes instead.
- New Transition descriptions state the comparison itself more cleanly. The old Transition description included thresholds, outcomes, and a proposed mechanism.
- The new map supplied 28 Claim seed blocks; the old map supplied none.

What became weaker:

- Every new Context is a root: all `parent_ids` are empty. The paper's orthogonal dimensions are therefore represented as independent partial settings rather than compatible combinations such as heterogeneous + large patch + zero wind + transition case.
- The base Context contains Facets covering heterogeneous and homogeneous surfaces and all wind speeds. These mutually exclusive choices should not all describe one undifferentiated base setting.
- The new map returned no ambiguities, although the evidence still contains threshold and regime uncertainty.

**Assessment:** the new prompt produced much better comparison coverage, but the resulting Context hierarchy is not yet adequate for context compatibility and transfer gating.

## 3. Facet Extraction

**Prompts:** `facet_extraction_v1` versus `prompts/facet_extraction.txt` (`facet_extraction_v2`). The old run also called `facet_reference_repair_v1`.

What improved:

- New setup Facets are more granular and directly traceable: domain size, horizontal/vertical resolution, time step, roughness, heat-flux contrast, background wind, droplet concentration, and diurnal case basis.
- Evidence sets are generally smaller. Many new Facets use one directly supporting SourceBlock, while old Facets often combined distant passages about setup, results, and mechanisms.
- The old run failed at Context `P000001_C004`. Both its initial and repair responses cited `P000001:S05:P0030` and `P000001:S11:P0100`, which were outside the 40 allowed evidence blocks. The repair repeated the same invalid IDs. New `P000001_C004` used the allowed block `P000001:S05:P0031` and passed reference validation.

Remaining scientific problems:

- Several new Facets are findings or mechanisms rather than environmental or experimental conditions. Examples include “Cloud development and convection transition,” “Moisture pool formation at PBL top,” “Subcloud thermal organization,” and “Planetary boundary layer mixing.” These belong in Claims unless they are used only to define an explicit reported regime.
- Some descriptions mix the defining condition with its outcome. For example, the large-patch Facet says the threshold induces circulation, moisture transport, and convection transition.
- Because all Contexts are roots, shared setup Facets are not inherited. This encourages duplication and makes each partial Context scientifically incomplete.

**Assessment:** v2 is clearly better for evidence validity and setup granularity, but Facet purity is still insufficient.

## 4. Claim Extraction

**Prompts:** the old run never reached Claim extraction; the completed run used `prompts/claim_extraction.txt` (`claim_extraction_v2`) for four Transition scopes.

New output:

- 21 Claims: 18 causal and 3 associative.
- Evidence roles: 19 `OWN_RESULT`, 2 `AUTHORS_INTERPRETATION_OF_OWN_RESULT`, and no cited-background leakage.
- Eight Claims use conditioning Facets.
- Every Claim has valid supporting SourceBlock IDs.

Positive observations:

- The extracted relationships preserve major scale and wind regimes, including the 5 km patch threshold, wind suppression, moisture pooling, PBL mixing, and transition versus nontransition outcomes.
- The prompt successfully separated associative statements from explicitly causal or controlled-perturbation relationships in several cases.
- Evidence roles distinguish authors' interpretation for the moisture-pool mechanism and cold-pool triggering.

Concerns:

- All 21 Claims are scoped to Transitions; none are scoped directly to a Context. Yet the map supplied 28 global Claim seed blocks. This appears primarily to be an extraction-scheduling issue rather than a wording issue in the Claim prompt.
- Eighteen of 21 Claims are causal. Some, such as precipitation occurrence leading to lower cloud-water path, need manual review to ensure temporal co-occurrence was not promoted to causation.
- Several Claim endpoints are verbose composite phrases. They are traceable, but may reduce canonical State connectivity across papers.

There is no valid old-versus-new Claim quality comparison because the old pipeline stopped before this stage.

## 5. Reconciliation, Consolidation, and Finalization

**Prompts:** the old run did not reach these stages. The new run made no Context-reconciliation LLM call and used `paper_consolidation_v2` once.

- The only consolidation candidate was `P000001_F001` versus `P000001_F002`; the model correctly classified horizontal and vertical domain resolution as `DISTINCT`.
- No unresolved conflicts were recorded.
- State canonicalization produced 36 States from 42 Claim endpoints.
- Final reference validation passed for all Context, Facet, Transition, Claim, State, and SourceBlock links.

One consolidation decision is too little evidence to judge whether the new consolidation prompt is better.

## Severity Definitions

The word **fatal** below does not mean difficult or irreparable. All observed flaws are technically repairable.

- **Fatal if left unfixed:** violates a scientific invariant or can make context gating, provenance, causal interpretation, or evidence completeness materially wrong. It is acceptance-blocking for claims that the system performs context-safe scientific reasoning.
- **Serious but doable:** can reduce recall, precision, or graph connectivity, but does not by itself invalidate every answer.
- **Minor/doable:** affects clarity, efficiency, or maintainability more than scientific validity.
- **Improvement:** new behavior is observably better on this run. It still needs replication on more papers.

| Finding | Severity if left unfixed | Main correction owner |
|---|---|---|
| Old invalid evidence IDs and failed repair | Fatal to that run; fixed in new run | repair prompt + deterministic validation |
| Missing scout seed fields | Serious/doable | response schema + completeness validation |
| Better separation of four experimental comparisons | Improvement | retain new mapping behavior |
| All new Contexts are independent roots | Fatal for context-safe retrieval | map prompt + structural failure audit + bounded repair |
| Mutually exclusive alternatives on the base Context | Fatal for applicability scoring | Context/Facet ownership reconciliation |
| Outcomes and mechanisms stored as Facets | Fatal when used for matching or conditioning | Facet prompt + semantic role validation |
| Context/global Claim scopes skipped when Transitions exist | Fatal for evidence completeness | extraction scheduler implementation |
| High causal proportion | Serious review risk; fatal only where a label is wrong | causal QA warning + bounded semantic review |
| Scout ambiguities disappear without evidence | Serious/doable | consolidation validation |
| Highly specific State wording | Serious/doable connectivity risk | conservative State adjudication |
| One consolidation decision | Evidence gap | reviewed consolidation evaluation set |
| Longer completed runtime | Minor/doable | measurement and optimization after correctness |

## Detailed Examples and Corrective Actions

### A. Exact evidence references now pass

**Classification:** Improvement. The old behavior was fatal for that indexing run; the defect is doable and is already avoided in the new run.

**Example:** Old Context `P000001_C004` was “Persistent Shallow Cumulus Regime.” Its Facet response cited `P000001:S05:P0030` and `P000001:S11:P0100`. Neither ID was in the 40 SourceBlocks supplied to that call. The reference-repair prompt returned the same two invalid IDs, and indexing stopped with `FAILED_REFERENCE_VALIDATION`.

The new `P000001_C004` is “Simulations with zero background wind speed.” Its Facet “Background wind speed” cites `P000001:S05:P0031`, which was supplied to the call and explicitly states the 0, 1, 2, 3, and 10 m/s simulations.

**Do differently:**

1. Keep saving the exact allowed ID list with every request.
2. Reject a repaired response when it repeats any invalid ID, as the current validator does.
3. For repair prompts, present the invalid IDs and complete allowed set, and require evidence IDs to be copied rather than generated.
4. Do not silently remove invalid evidence because that could leave an unsupported object looking valid.

### B. New scouting preserves downstream seed passages

**Classification:** Improvement. Missing seed fields are serious but doable because they cause silent recall loss rather than false provenance.

**Example:** Across the old scouts, `facet_seed_block_ids` was omitted in all three responses and became an empty list through schema defaults. Two scouts also omitted Claim seeds. The new scouts returned 14 Facet seeds and 28 Claim seeds. This is why blocks such as `P000001:S12:P0120`, which describes moisture pooling and deeper-convection transition, remained available downstream.

**Do differently:**

1. Make all response fields structurally required in the temporary LLM response schema, even when the valid value is an empty list.
2. Validate the raw JSON keys before Pydantic supplies defaults.
3. Record a visible completeness warning when a results-heavy section returns no Claim seeds or a methods-heavy section returns no Facet seeds.
4. Treat that warning as a bounded repair condition, not as permission to invent seed IDs.

### C. Experimental comparisons are separated more faithfully

**Classification:** Improvement.

**Example:** The old map created only “Convection Regime Shift.” Its description combined patch size above 5 km, wind below `Uc0`, moisture pooling, vertical transport, and transition to deep convection. Those are multiple interventions, conditions, mechanisms, and outcomes in one comparison.

The new map separately represents:

- homogeneous → heterogeneous surface;
- zero → nonzero background wind;
- small → large patches;
- nontransition → transition cases.

This matches the paper's experimental axes. For example, `P000001:S05:P0030` defines homogeneous controls, `P000001:S05:P0031` defines wind experiments, and `P000001:S06:P0033` compares patch sizes and wind responses.

**Do differently:** keep the v2 positive definition of a comparison, but add a validation question: “Does this Transition change one interpretable experimental axis or compare two explicitly named regimes?” Send a Transition that combines intervention, mechanism, and outcome to bounded map repair.

### D. The new Context graph is flat

**Classification:** **Fatal if left unfixed** for context-conditioned retrieval. Doable with map validation and bounded repair.

**Example:** All nine new Contexts have empty `parent_ids`. “Zero background wind,” “large patches,” “heterogeneous chessboard surface,” and “transition cases” are therefore unrelated roots. In the actual experiment these conditions coexist in cases such as `HET14U0`.

A query asking about large heterogeneous patches under zero wind needs Claims supported by that combination. With independent roots, the graph cannot prove that the large-patch, heterogeneous, and zero-wind Facets describe one compatible supporting regime.

**Do differently:**

1. Add a deterministic structural audit after map consolidation: flag a map when multiple partial experimental dimensions are all roots and evidence names combined cases.
2. Send only the failed map and directly supporting SourceBlocks to the specified bounded map-repair procedure.
3. Require a shared LES/CASS parent, then child settings or explicit case-group Contexts that inherit its setup.
4. For this paper, a candidate structure to verify against evidence is: shared CASS LES setup → heterogeneous/homogeneous surface → wind/patch case groups → transition/nontransition regimes. This is a review target, not a structure to impose without evidence.
5. Reject the repaired map if it creates inheritance unsupported by SourceBlocks.

### E. Mutually exclusive conditions are attached to the base Context

**Classification:** **Fatal if left unfixed** because it can make Context similarity and Claim applicability circular or contradictory. Doable.

**Example:** Base Context `P000001_C001`, “Idealized LES of CASS case over ARM SGP site,” contains:

- Facet `F005`: chessboard WET/DRY heat-flux heterogeneity;
- Facet `F006`: homogeneous surface properties;
- Facet `F008`: all background wind settings from 0 to 10 m/s.

Some surface properties are genuinely homogeneous in the heterogeneous experiments, as `P000001:S05:P0028` explains. However, heterogeneous heat-flux forcing versus homogeneous domain-mean forcing is an experimental choice, and 0 versus nonzero wind is another choice. Those alternatives should not all be interpreted as one base environmental state.

**Do differently:**

1. Keep only conditions common to every child experiment on the shared parent: domain, resolution, roughness, microphysics, and common case basis.
2. Assign chessboard heat-flux forcing to heterogeneous children, uniform domain-mean forcing to homogeneous controls, and individual wind regimes to their relevant children.
3. Add an ownership audit that flags categorical alternatives such as zero/nonzero, dry/wet, control/treatment, or homogeneous/heterogeneous on the same Context unless the description explicitly says the field enumerates an experiment family.
4. Use LLM reconciliation for semantic ownership; do not attempt to resolve scientific exclusivity with string matching alone.

### F. Findings and mechanisms leak into Facets

**Classification:** **Fatal if these Facets participate in query matching or Claim conditioning.** Doable through prompt clarification plus semantic validation.

**Examples:**

- `F030` begins with the valid condition “patch sizes greater than or equal to 5 km” but continues that this induces circulation, moisture transport, and convection transition.
- `F031` is “Cloud development and convection transition,” an outcome.
- `F032` is “Moisture pool formation at PBL top,” a mechanism/result supported by `P000001:S12:P0120`.
- `F037` is “Planetary boundary layer mixing,” another reported mechanism/result.

If a user asks about moisture pooling, matching the query to `F032` and then retrieving a Claim about moisture pooling would use the answer as its own applicability condition.

**Do differently:**

1. Add a plain-language acceptance test to the Facet prompt: “Could this information be known before observing the reported atmospheric outcome?” Patch size and prescribed wind pass; resulting moisture pooling and convection transition do not.
2. Ask the model to return finding-like passages as `unmapped_context_hints` only when they imply a distinct regime; otherwise leave them for Claim extraction.
3. After extraction, run the specification's bounded semantic judgment on Facets that contain response language such as caused, promoted, prevented, increased, transitioned, or formed. These words are candidate signals, not automatic rejection rules.
4. Move supported relationships into Claims with the same SourceBlock provenance; do not merely delete them.

### G. Global and Context-scoped Claims are skipped

**Classification:** **Fatal if left unfixed** for evidence completeness. This is an implementation flaw, not mainly a prompt flaw, and it is directly doable.

**Example:** The new map returned 28 `global_claim_seed_block_ids`, but the final graph contains zero Context-scoped Claims and 21 Transition-scoped Claims. In `extract_claims()`, Context scopes are added only inside `if not scopes`. Any paper with at least one Transition therefore skips Context/global Claim scheduling entirely.

This can omit findings that describe the paper's overall LES regime or one setting without an explicit comparison.

**Do differently:**

1. Implement the indexing specification's Context/global Claim scheduling even when Transitions exist; remove the mutually exclusive scheduling behavior.
2. Keep Transition seed blocks assigned to their Transition scopes.
3. Process global seeds against the evidence-supported Context scopes required by the specification, then use normal consolidation to merge true duplicates.
4. Add an integration test where one paper contains both a Transition result and an independent Context result. The test must require both scope types in the final graph.
5. Record which global seed IDs were consumed, rejected, or left unresolved.

### H. The causal proportion needs scientific audit

**Classification:** Serious review risk. **Fatal for any individual Claim that is incorrectly labeled causal**, but the 18/21 count alone does not prove misclassification.

**Examples:**

- `CL005`, background wind shifting and destroying secondary circulation, is supported by controlled wind perturbations and explicit paper language; causal is plausible.
- `CL015`, surface precipitation occurrence → cloud-water-path decrease, is supported by `P000001:S07:P0040`, which says the reduction represents removal of cloud water by precipitation; causal may also be justified.
- `CL001`, large patches → deep-convection transition, is based on controlled simulations but combines the patch threshold with a complex response. It needs review for whether background wind should be explicit conditioning rather than implicit scope.

**Do differently:**

1. Keep the current rule that controlled perturbations and explicit author attribution can support causal Claims.
2. Add a review flag when a causal Claim lacks either a controlled intervention in its scope or explicit causal language in its smallest evidence set.
3. For flagged cases only, use a bounded semantic correction/review with the specification's exact causal-versus-associative rules and the smallest supporting evidence set.
4. Preserve the original Claim and mark the case unresolved if evidence is insufficient; do not silently downgrade or upgrade it.

### I. Uncertainty is being lost during consolidation

**Classification:** Serious but doable. It becomes fatal only when the lost uncertainty changes gating or the final scientific answer.

**Example:** Old scouting noted that exact `Uc0` values by patch size were not supplied and that the homogeneous-control forcing definition was incomplete. The new map returned zero ambiguities without citing evidence that resolved those issues.

**Do differently:**

1. Pass scout ambiguities into consolidation as items that must each be resolved with cited evidence or preserved.
2. Require a resolution record: ambiguity text, action (`resolved` or `preserved`), and supporting SourceBlock IDs when resolved.
3. Reject consolidation that drops an ambiguity without evidence.
4. Surface preserved ambiguity in final artifacts and query limitations.

### J. State labels may reduce cross-paper connectivity

**Classification:** Serious but doable; not fatal to single-paper provenance.

**Example:** Claims create highly specific endpoints such as “sensitivity of sensible and latent heat fluxes to soil moisture” or “surface heterogeneity patch size / greater than or equal to 5 km.” Specificity preserves meaning, but overly composite concepts can fail to connect to another paper using a simpler term such as “patch size” or “surface heterogeneity scale.”

**Do differently:**

1. Keep evidence-faithful Claim endpoints unchanged in the Claim record.
2. Improve canonical State adjudication separately, using embeddings only to propose candidates and the specified conservative semantic decision for merges.
3. Preserve aliases and `RELATED_BUT_DISTINCT` outcomes rather than forcing connectivity.
4. Evaluate cross-paper State recall with a reviewed set of equivalent and non-equivalent concept pairs.

### K. Consolidation quality is not yet measurable

**Classification:** Evidence gap, not a demonstrated flaw.

**Example:** The new consolidation prompt saw only `F001` horizontal resolution versus `F002` vertical resolution and correctly returned `DISTINCT`. One obvious pair cannot establish consolidation precision or recall.

**Do differently:** create a reviewed candidate set containing true duplicates, close-but-distinct Facets, parent-child Contexts, contradictory Claims, and conditionally different Claims. Report precision, recall, and unresolved rate instead of citing this single successful decision.

### L. The new run is slower

**Classification:** Minor/doable relative to scientific correctness.

**Example:** Old prompts used 650.5 LLM seconds before failure. The new completed run used 1,987.9 seconds, including 1,003.7 seconds for Claim extraction. This is not a fair end-to-end speed comparison because the old run never performed Claims, consolidation, States, or embeddings.

**Do differently:** measure per-stage latency on completed matched runs, retain deterministic caching, avoid resending irrelevant blocks, and optimize only after scientific validation. Do not remove required evidence or collapse scopes merely to reduce runtime.

## Conclusion

The new prompts are **better overall for executable extraction**: they prevent the observed reference failure, populate seed fields, separate experimental comparisons, preserve provenance, and produce a complete graph-ready paper.

They are **not yet demonstrably better in every scientific dimension**. Before treating v2/v3 as the accepted prompt set, the next validation should focus on:

1. requiring scientifically meaningful Context inheritance or explicit composite regimes;
2. preventing outcomes and mechanisms from being stored as Facets;
3. investigating why global Claim seeds did not produce Context-scoped Claims;
4. manually auditing causal versus associative labels;
5. repeating the comparison on several papers and multiple generations per version.

Query parsing and answer-synthesis prompts were not compared here because there is no matched old/new query run over the same finalized graph.
