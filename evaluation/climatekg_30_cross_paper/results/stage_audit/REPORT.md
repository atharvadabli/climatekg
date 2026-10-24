# ClimateKG 30-question structured-reasoning run

- Completed: 30 / 30
- Total query time: 3931.2 seconds
- Mean query time: 131.0 seconds
- Candidate branch base: `experiment/candidate-context-rescore-v2` (`c2eb632`)
- Graph: 115 papers, 1,217 Contexts, 3,460 Facets, 1,729 Claims
- Protocol: live decomposition and query parsing; no frozen QuerySpecs
- Evaluation status: diagnostic development suite, not held-out scientific gold

## Aggregate evidence flow

- Diagnostic expected Claims: 167
- Entered candidate pool: 150 (89.8%)
- Reached selected paths: 65 (38.9%)
- Appeared in synthesis provenance: 49 (29.3%)
- Answers citing at least two papers: 27 / 30

These are stage diagnostics, not answer-accuracy scores. An answer can be correct using an alternative Claim, and a cited expected Claim does not by itself prove a correct synthesis.

## By capability group

| Group | Questions | Expected Claims candidate/path/cited | Mean seconds |
|---|---:|---:|---:|
| context_contrast | 6 | 34/18/13 of 37 | 157.1 |
| mechanism_chain | 7 | 34/17/15 of 37 | 140.5 |
| cross_paper_synthesis | 9 | 51/16/9 of 56 | 116.7 |
| spatial_scale | 4 | 15/12/9 of 16 | 72.7 |
| transfer | 2 | 7/1/2 of 11 | 200.8 |
| evidence_boundary | 2 | 9/1/1 of 10 | 131.3 |

## Stage-loss indicators

- `path_construction_loss`: 27 questions
- `synthesis_selection_loss`: 12 questions
- `candidate_retrieval_loss`: 11 questions
- `no_expected_claim_flow_loss`: 1 questions

## Frequent warnings

- `STATE_MAPPING_AMBIGUOUS`: 26
- `QUERY_UNSUPPORTED_TARGET_STATE_CLEARED`: 13
- `QUERY_ENRICHMENT_SKIPPED_UNRESOLVED_SPATIAL_SUPPORT`: 10
- `QUERY_COMPARATIVE_ENDPOINTS_DISCARDED`: 8
- `SPATIAL_REFERENCE_AMBIGUOUS`: 7
- `CONTEXT_GATE_DISABLED_EMPTY_QUERY_CONTEXT`: 7
- `QUERY_UNSUPPORTED_SOURCE_STATE_CLEARED`: 7
- `QUERY_GLOBAL_FLAG_NORMALIZED`: 5
- `QUERY_UNSPECIFIED_TARGET_STATE_DISCARDED`: 3
- `QUERY_METHOD_FACET_DISCARDED`: 2
- `QUERY_UNSUPPORTED_PARSED_ITEM_DISCARDED`: 2
- `SPATIAL_GAZETTEER_FAILED:URLError: <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>`: 2
- `UNSUPPORTED_RECOMPOSED_ITEM`: 1
- `QUERY_SPATIAL_RELATION_TARGET_DISCARDED`: 1
- `UNSUPPORTED_SYNTHESIS_ITEM`: 1

## Question audit

| ID | Capability | Seconds | Expected Claims candidate/path/cited | Papers expected/cited | Flow indicators |
|---|---|---:|---:|---:|---|
| [XPG001](questions/XPG001.md) | seasonal_and_synoptic_conditioning | 383.8 | 3/1/1 of 6 | 1/3; 2 total | candidate_retrieval_loss, path_construction_loss |
| [XPG002](questions/XPG002.md) | dry_heat_moist_heat_tradeoff | 90.4 | 6/3/3 of 6 | 3/4; 4 total | path_construction_loss |
| [XPG003](questions/XPG003.md) | drought_conditioning | 84.6 | 6/5/3 of 6 | 2/2; 3 total | path_construction_loss, synthesis_selection_loss |
| [XPG004](questions/XPG004.md) | precipitation_sign_by_region | 59.4 | 5/2/1 of 5 | 1/4; 3 total | path_construction_loss, synthesis_selection_loss |
| [XPG005](questions/XPG005.md) | afforestation_sign_reversal | 108.6 | 8/4/2 of 8 | 1/3; 4 total | path_construction_loss, synthesis_selection_loss |
| [XPG006](questions/XPG006.md) | interannual_conditioning | 215.9 | 6/3/3 of 6 | 1/3; 2 total | path_construction_loss |
| [XPG007](questions/XPG007.md) | deforestation_cloud_radiative_chain | 139.9 | 5/4/2 of 5 | 1/2; 10 total | path_construction_loss, synthesis_selection_loss |
| [XPG008](questions/XPG008.md) | irrigation_rainfed_recycling_chain | 148.9 | 6/4/4 of 6 | 1/2; 6 total | path_construction_loss, synthesis_selection_loss |
| [XPG009](questions/XPG009.md) | heterogeneity_convection_chain | 249.7 | 4/0/0 of 6 | 2/2; 2 total | candidate_retrieval_loss, path_construction_loss |
| [XPG010](questions/XPG010.md) | forest_cloud_chain | 195.8 | 7/3/3 of 7 | 1/2; 2 total | path_construction_loss |
| [XPG011](questions/XPG011.md) | amazon_energy_moisture_chain | 105.6 | 3/0/0 of 3 | 1/3; 3 total | path_construction_loss |
| [XPG012](questions/XPG012.md) | remote_hydrology_chain | 76.1 | 4/2/2 of 5 | 1/2; 1 total | candidate_retrieval_loss, path_construction_loss |
| [XPG013](questions/XPG013.md) | irrigation_circulation_chain | 67.7 | 5/4/4 of 5 | 2/3; 2 total | path_construction_loss |
| [XPG014](questions/XPG014.md) | irrigation_temperature_agreement | 78.1 | 7/2/1 of 7 | 5/5; 6 total | path_construction_loss, synthesis_selection_loss |
| [XPG015](questions/XPG015.md) | forest_cloud_evidence_convergence | 129.9 | 8/2/1 of 8 | 1/3; 5 total | path_construction_loss, synthesis_selection_loss |
| [XPG016](questions/XPG016.md) | deforestation_temperature_latitude | 132.8 | 6/2/0 of 6 | 2/5; 3 total | path_construction_loss, synthesis_selection_loss |
| [XPG017](questions/XPG017.md) | soil_moisture_convection_conflict | 140.3 | 6/2/2 of 6 | 2/3; 6 total | path_construction_loss |
| [XPG018](questions/XPG018.md) | patch_scale_nonmonotonicity | 273.9 | 7/3/4 of 8 | 2/3; 2 total | candidate_retrieval_loss, path_construction_loss |
| [XPG019](questions/XPG019.md) | forest_temperature_diurnal_tradeoff | 95.5 | 7/3/0 of 7 | 0/2; 3 total | path_construction_loss, synthesis_selection_loss |
| [XPG020](questions/XPG020.md) | moisture_recycling_scale | 66.5 | 4/1/1 of 5 | 1/4; 5 total | candidate_retrieval_loss, path_construction_loss |
| [XPG021](questions/XPG021.md) | deforestation_thresholds | 67.2 | 2/1/0 of 4 | 0/3; 5 total | candidate_retrieval_loss, path_construction_loss, synthesis_selection_loss |
| [XPG022](questions/XPG022.md) | causal_associative_distinction | 65.7 | 4/0/0 of 5 | 1/4; 5 total | candidate_retrieval_loss, path_construction_loss |
| [XPG023](questions/XPG023.md) | wind_displaced_convergence | 84.3 | 5/5/4 of 5 | 1/1; 1 total | synthesis_selection_loss |
| [XPG024](questions/XPG024.md) | forest_edge_wind_size | 59.4 | 2/2/2 of 2 | 1/1; 1 total | no_expected_claim_flow_loss |
| [XPG025](questions/XPG025.md) | patch_threshold_vs_optimum | 61.2 | 5/5/3 of 5 | 2/2; 2 total | synthesis_selection_loss |
| [XPG026](questions/XPG026.md) | local_vs_remote_relation_family | 85.8 | 3/0/0 of 4 | 1/4; 6 total | candidate_retrieval_loss, path_construction_loss |
| [XPG027](questions/XPG027.md) | semiarid_planning_tradeoff | 260.8 | 5/1/2 of 6 | 2/4; 3 total | candidate_retrieval_loss, path_construction_loss |
| [XPG028](questions/XPG028.md) | humid_forest_transfer | 140.9 | 2/0/0 of 5 | 2/5; 8 total | candidate_retrieval_loss, path_construction_loss |
| [XPG029](questions/XPG029.md) | unsupported_cardinal_placement | 68.0 | 3/0/0 of 3 | 0/3; 5 total | path_construction_loss |
| [XPG030](questions/XPG030.md) | recommendation_under_conflict | 194.5 | 6/1/1 of 7 | 1/5; 3 total | candidate_retrieval_loss, path_construction_loss |

## Initial findings

1. Candidate retrieval is broad: most diagnostic Claims enter the candidate pool. The larger loss occurs when candidates are reduced to paths and then to the bounded synthesis evidence.
2. The system does perform cross-paper synthesis, but evidence breadth is uneven. Inspect questions where expected papers are retrieved but only one paper survives into provenance.
3. Context, State mapping, and grounding warnings are preserved per question. Missing Context and Context mismatch must be reviewed separately in the raw report.
4. The two original execution failures came from an unavailable gazetteer. The evaluation branch now records the failure and retains unresolved spatial Context instead of aborting or inventing coordinates.
5. Exact-phrase qualifier coverage and reference-token overlap remain diagnostics only; scientific correctness requires citation-level review against SourceBlocks.

## Files

- `responses_and_stage_audit.json`: all questions, answers, plans, parsed specs, Claim flow, warnings, timings, and raw paths.
- `questions/XPGxxx.md`: readable complete audit for each question.
- Runtime artifact directories: exact LLM requests/responses, query reports, and stage events.
