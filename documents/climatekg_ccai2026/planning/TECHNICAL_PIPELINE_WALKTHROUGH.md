# ClimateKG Technical Pipeline Walkthrough

## System goal

ClimateKG turns scientific papers into a context-aware knowledge graph and uses that graph to answer land-atmosphere questions.

The complete flow is:

```text
PDF
  -> page images
  -> NVIDIA Nemotron-Parse v1.2 output
  -> cleaned text
  -> SourceBlocks
  -> paper map
  -> Contexts, Facets, Transitions, and Claims
  -> consolidation and validation
  -> canonical States
  -> embeddings
  -> Neo4j
  -> parsed user question
  -> query Context and canonical endpoints
  -> Context and Claim ranking
  -> context-gated path search
  -> supporting SourceBlocks
  -> grounded answer with references
```

The system is designed for findings whose meaning changes with climate, season, soil moisture, atmospheric state, land-cover pattern, location, or scale. It does not treat a paper as one undifferentiated text embedding.

## Scientific objects

The graph uses six scientific objects and one evidence object.

| Object | Meaning |
|---|---|
| `Paper` | Bibliographic record and source file identity. |
| `Context` | A study setting, scenario, period, or environmental regime under which findings apply. |
| `Facet` | One part of a Context, such as climate regime, soil moisture, season, wind, terrain, or patch configuration. |
| `Transition` | A change from one Context to another, such as adding irrigation or replacing forest with open land. |
| `Claim` | A reported scientific relation between a source State and a target State. It is marked causal or associative. |
| `State` | A canonical concept and direction, such as `evapotranspiration + decrease`. |
| `SourceBlock` | The smallest stable passage used as direct evidence. It retains page and section information. |

Every Claim must point to its direct supporting SourceBlocks. The answer therefore has a trace from answer text to Claim, Paper, and exact evidence passage.

## Runtime components

| Task | Model or service |
|---|---|
| PDF parsing | `nvidia/NVIDIA-Nemotron-Parse-v1.2` only |
| Scientific extraction and synthesis | local Ollama model `qwen3.6:27b` |
| Embeddings | local Ollama model `qwen3-embedding:4b`, 2,048 dimensions |
| Graph database | Neo4j 5.26 Community |

PDFium is not a parser in this system. It renders each PDF page as an image at 200 DPI because Nemotron-Parse consumes page images. The text and layout objects used downstream come only from NVIDIA Nemotron-Parse v1.2. There is no PyMuPDF parsing fallback.

## Artifact layout

All generated data stays under `climatekg/runtime`.

```text
climatekg/runtime/
  cache/                 downloaded model files and reusable caches
  data/papers/Pxxxxxx/   all artifacts for one indexed paper
  failed_runs/           visible failed-run records
  logs/                  pipeline logs
  neo4j/                 local Neo4j data, logs, and plugins
  outputs/               query and validation results
```

Each paper has a directory similar to:

```text
P000002/
  source/paper.pdf
  manifest.json
  parse/
    page_manifest.json
    page_images/
    renderer.log
    nemotron.log
    nemotron_raw.json
    nemotron.md
  clean/
  blocks/
    blocks.jsonl
    block_embeddings.json
  extraction/
  final/
    final_paper.json
    context_retrieval_text/
    state_recanonicalization.json
    history/
```

This layout keeps the original input, intermediate objects, model requests, model responses, final data, and later repairs separate and reviewable.

# 1. Indexing

## Indexing schemas

All persistent objects are strict Pydantic models in `climatekg/models.py`. Unknown fields are rejected because each model inherits from `StrictModel` with `extra="forbid"`.

### Persistent scientific schemas

| Object | Fields |
|---|---|
| `Paper` | `id`, `title`, `source_file`, optional `doi`, optional `year` |
| `SpatialSupport` | `kind`, `name`, optional `geometry`, `resolution` |
| `Context` | `id`, `paper_id`, `parent_ids`, `label`, `aliases`, optional `spatial_support`, `evidence_block_ids`, optional retrieval embedding |
| `Facet` | `id`, `context_id`, controlled `domain`, open `notion`, open `description`, `origin`, optional derived-data source, evidence IDs, notion and content embeddings |
| `Transition` | `id`, `paper_id`, source and target Context IDs, `label`, `aliases`, `description`, evidence IDs, embedding |
| `ClaimEndpoint` | `concept`, `state` |
| `Claim` | identity and scope, `from`, `to`, causal or associative relation, description, evidence role, conditioning Facet IDs, evidence IDs, embedding |
| `State` | canonical `id`, `concept`, `state`, aliases, concept embedding |
| `SourceBlock` | identity, document order, page, section path, block type, text, source locator, hard-split flag, optional embedding |
| `FinalPaper` | all objects above, evidence links, unresolved conflicts, versions, and metadata |

The exact persistent shapes are:

```text
Paper
  id: str
  title: str
  source_file: str
  doi: str | null
  year: int | null

SpatialSupport
  kind: point | patch | watershed | region | climate_zone | global | unresolved
  name: str
  geometry: object | null
  resolution: exact | approximate | named_region | global | unresolved

Context
  id: str
  paper_id: str
  parent_ids: list[str]
  label: str
  aliases: list[str]
  spatial_support: SpatialSupport | null
  evidence_block_ids: list[str]
  retrieval_embedding: list[float] | null

Facet
  id: str
  context_id: str
  domain: spatial_configuration | land_surface | hydrology | atmosphere |
          climate | substrate_terrain | other
  notion: str
  description: str
  origin: reported | derived
  source: ProvenanceSource | null
  evidence_block_ids: list[str]
  notion_embedding: list[float] | null
  content_embedding: list[float] | null

Transition
  id: str
  paper_id: str
  from_context_id: str
  to_context_id: str
  label: str
  aliases: list[str]
  description: str
  evidence_block_ids: list[str]
  transition_embedding: list[float] | null

ClaimEndpoint
  concept: str
  state: str

Claim
  id: str
  paper_id: str
  scope_type: context | transition
  scope_id: str
  from: ClaimEndpoint
  to: ClaimEndpoint
  relation: causal | associative
  description: str
  evidence_role: OWN_RESULT | AUTHORS_INTERPRETATION_OF_OWN_RESULT |
                 CITED_BACKGROUND | HYPOTHESIS_OR_PROPOSAL
  conditioning_facet_ids: list[str]
  evidence_block_ids: list[str]
  claim_embedding: list[float] | null

State
  id: str
  concept: str
  state: str
  aliases: list[str]
  concept_embedding: list[float] | null

SourceBlock
  id: str
  paper_id: str
  order: int
  page: int | null
  section_path: list[str]
  block_type: title | abstract | heading | paragraph | list | table |
              table_caption | figure_caption | equation | footnote |
              reference | other
  text: str
  source_locator: object
  oversize_hard_split: bool
  embedding: list[float] | null

FinalPaper
  schema_version: str
  pipeline_version: str
  paper: Paper
  source_blocks: list[SourceBlock]
  contexts: list[Context]
  facets: list[Facet]
  transitions: list[Transition]
  claims: list[Claim]
  states: list[State]
  evidence_links: list[object]
  unresolved_conflicts: list[object | str]
  metadata: object
```

`ProvenanceSource` records an optional source type, ID, dataset, version, method, temporal window, and geometry hash. Reported Facets cite paper evidence. Derived Facets retain derived-data provenance.

`FinalPaper` performs cross-object validation. It rejects broken ownership, Context cycles, unreachable conditioning Facets, missing evidence, reference-only Claim evidence, invalid Transition endpoints, and invalid Claim scopes.

### Temporary LLM extraction schemas

Temporary structured outputs are defined in `climatekg/extraction_models.py`. They are validated before persistent objects are created.

| Schema | Required content | Prompt stage |
|---|---|---|
| `MapContext` | temporary ID, label, parents, optional split reason, aliases, spatial support, evidence and Facet seed IDs | paper mapping |
| `MapTransition` | temporary ID, source and target temporary Context IDs, label, description, evidence and Claim seed IDs | paper mapping |
| `PaperMap` | Contexts, Transitions, global Claim seeds, ambiguities | paper map and map consolidation |
| `ScoutMention` | name, description, Block IDs | section scouting |
| `SectionScout` | Context, location, and comparison mentions; Facet and Claim seeds; cross-references; ambiguities | section scouting |
| `FacetCandidate` | domain, notion, description, evidence IDs | Facet extraction |
| `FacetBatch` | target Context ID, Facets, unmapped Context hints, ambiguities | Facet extraction |
| `ClaimCandidate` | endpoints, relation, description, evidence role, conditioning Facets, evidence IDs | Claim extraction |
| `ClaimBatch` | scope ID, Claims, unmapped Context hints, ambiguities | Claim extraction |
| `ContextHintDecision` | hint ID, one allowed action, affected Claims, evidence, and action-specific fields | Context reconciliation |
| `ContextReconciliationBatch` | every hint decision and ambiguities | Context reconciliation |
| `ConsolidationDecision` | object type, pair IDs, decision, optional parent and child | paper consolidation |
| `ConsolidationBatch` | every candidate-pair decision and unresolved conflicts | paper consolidation |

Action validators require an existing Context for `ATTACH_TO_EXISTING_CONTEXT`; a label and evidence for any new Context; and a parent for `ADD_CHILD_CONTEXT`.

## Indexing prompts

Every versioned prompt is stored under `prompts/`. Ollama also receives the output model's generated JSON Schema through its `format` field. The standalone prompt set treats each file as an independent Qwen3.6-27B task: it defines the real-world operation, explains every input, defines internal terms before field names use them, lists fixed classifications, and specifies every output field. Most files are v2. `paper_map.txt` and `map_consolidation.txt` are v3 because their nested spatial fields received an additional plain-language definition pass after the recorded paper replay.

The table below previously listed only the seven active extraction/consolidation files. The authoritative specification defines two additional indexing-side adjudication prompts: offline State-concept adjudication and bounded conditioning-Facet adjudication. They are included here because a complete technical account must distinguish the normative prompt set from the subset currently wired into routine paper indexing.

| Prompt file | Purpose | Output schema | Temperature | Thinking |
|---|---|---|---:|---|
| Nemotron Parse page control string | request bounding boxes, classes, Markdown, and suppression of text inside pictures | model-native parse output | model-defined | model-defined |
| `paper_map.txt` | short-paper structure discovery | `PaperMap` | 0.1 | low |
| `section_scout.txt` | long-paper section scouting | `SectionScout` | 0.0 | no |
| `map_consolidation.txt` | combine scout outputs | `PaperMap` | 0.0 | low |
| `facet_extraction.txt` | extract local Context Facets | `FacetBatch` | 0.0 | no |
| `claim_extraction.txt` | extract scoped scientific relations | `ClaimBatch` | 0.0 | low |
| `context_reconciliation.txt` | decide late Context hints | `ContextReconciliationBatch` | 0.0 | medium |
| `paper_consolidation.txt` | decide bounded near-duplicate pairs | `ConsolidationBatch` | 0.0 | medium |
| `state_adjudication.txt` | conservative offline canonical-concept decision | adjudication label | 0.0 | no |
| `conditioning_facet_adjudication.txt` | decide whether a candidate condition materially changes interpretation or transfer | one of four labels | 0.0 | no |

Prompt-set audit:

| Prompt family | In authoritative specification | Active runtime status |
|---|---|---|
| Paper map, section scout, map consolidation, condition extraction, relationship extraction | yes | rewritten as standalone `.txt` tasks and wired into indexing; paper-map files are v3 and the remaining files are v2 |
| Context reconciliation | yes | rewritten as a standalone v2 decision task, with the required reversal constraints |
| Paper consolidation | yes | wired as the later Section 96 bounded pair-decision protocol, which overrides the less-specific earlier consolidation description |
| State adjudication | yes | versioned standalone v2 file for offline corpus maintenance; no per-paper LLM call is required |
| Conditioning-Facet adjudication | yes for the bounded cases defined by Section 97.2 | versioned standalone v2 file exists; the bounded runtime invocation remains an implementation-conformance gap |

### Standalone prompt review locations

The active standalone templates are the `.txt` files in [`prompts/`](../../../prompts/). Four fully rendered v2 requests from `atsc-jas-d-18-0196.1.pdf`, each followed by the exact Pydantic JSON Schema sent to Ollama, are in:

```text
climatekg/runtime/prompt_examples/atsc-jas-d-18-0196-1/v2/actual_prompts/
```

The example run completed with 163 SourceBlocks, 9 study settings, 37 environmental or experimental condition records, 4 comparisons, 21 scientific relationship records, and 36 canonical State records.

### NVIDIA Nemotron Parse v1.2 page prompt

Before any scientific extraction prompt runs, every rendered PDF page is sent to NVIDIA Nemotron Parse v1.2 with this exact model-control string:

```text
</s><s><predict_bbox><predict_classes><output_markdown><predict_no_text_in_pic>
```

The same string is preserved in every `parse/nemotron_raw.json` under the `prompt` field. For example, `P000002` records it together with `parser: nvidia/NVIDIA-Nemotron-Parse-v1.2`, the pinned model path, page count, and page outputs. This is a parser-model prompt, not an Ollama structured scientific-extraction prompt, so it does not receive a Pydantic JSON Schema, temperature, or Qwen thinking level.

### `paper_map.txt`

This prompt performs structure discovery, not detailed Claim extraction. It defines Contexts, inheritance, and Transitions; requires the minimum paper structure and exact SourceBlock IDs; and allows only four child split reasons:

```text
separate_reported_finding
sign_or_null_reversal
misleading_parent_scope
explicit_transition_state
```

Inputs:

```text
{paper_id}
{paper_text}
```

It prohibits outside knowledge, enrichment variables, invented coordinates, and detailed mechanisms. Shared conditions belong in parents. Independent study areas remain separate. Ambiguity is retained.

### `section_scout.txt`

This prompt examines one bounded section group in a long paper. It returns mentions and evidence seeds rather than permanent graph objects.

Inputs:

```text
{paper_id}
{section_path}
{section_blocks}
```

It records Context, location, and comparison mentions; Facet and Claim seeds; cross-references; and ambiguities.

### `map_consolidation.txt`

This prompt combines validated scouts and selected original Blocks into one `PaperMap`. It can reconcile structure but cannot invent content absent from the supplied evidence.

Inputs:

```text
{paper_metadata}
{scout_outputs}
{selected_blocks}
```

### `facet_extraction.txt`

This prompt extracts only Facets owned by one target Context. It requires one coherent notion per Facet, open evidence-faithful descriptions, and exact evidence IDs.

Inputs:

```text
{paper_id}
{target_context}
{context_registry}
{parent_facets}
{existing_target_facets}
{evidence_blocks}
```

It preserves quantities, units, directions, season, layers, scale, patch and edge language, and upwind/downwind wording. It prohibits repeated inherited Facets, inferred spatial relations, invented values, and confidence scores. A distinct unregistered regime becomes an `unmapped_context_hint`.

### `claim_extraction.txt`

This prompt extracts one evidence-backed `FROM -> TO` relation per Claim for one known scope.

Inputs:

```text
{paper_id}
{context_registry}
{transitions}
{available_scope_facets}
{target_scope}
{evidence_blocks}
```

It requires causal wording only for explicit attribution or a directly supported perturbation. It preserves competing, null, opposite, conditional, seasonal, spatial, scale, magnitude, and timing findings. It prohibits invented mechanism steps, cited-background leakage, merging different response variables, and attaching every Context Facet as a condition.

### `context_reconciliation.txt`

This prompt assigns every late hint exactly one action:

```text
ATTACH_TO_EXISTING_CONTEXT
ADD_CHILD_CONTEXT
ADD_INDEPENDENT_CONTEXT
IGNORE_AS_NOT_A_CONTEXT
UNRESOLVED
```

Inputs:

```text
{context_registry}
{hints}
{hint_evidence_blocks}
```

Supported sign, null, temporal, seasonal, spatial, or scale reversals receive distinct Contexts. A scoped reversal cannot be detached into an unrelated independent Context.

### `paper_consolidation.txt`

This prompt judges only supplied candidate pairs. Every pair receives `SAME`, `DISTINCT`, `PARENT_CHILD`, or `UNCERTAIN`.

Inputs:

```text
{paper_metadata}
{candidate_pairs}
```

It is explicitly not an extraction stage. Claims can be identical only when meaning, scope, response variable, temporal scope, spatial scope, and counterfactual match. Contradictions remain distinct.

### Generated repair prompts

When JSON fails schema validation, `OllamaClient.structured` resends the original input with the exact Pydantic errors:

```text
{original_user_prompt}

Your previous output failed schema validation.
Validation errors:
{pydantic_validation_error}
Return a corrected object only. Do not add any new scientific information.
```

Referential repairs are narrower. They list only allowed Context, Facet, Claim, and SourceBlock IDs; require valid objects to remain unchanged; and prohibit unrelated evidence substitutions. Retries are bounded. The actual generated user templates are:

<details>
<summary>Paper-map SourceBlock ID repair (verbatim template)</summary>

```text
Paper: {paper_json}

Your previous output failed referential ID validation. Repair SourceBlock IDs only.
Validation error: {validation_error}
Failed output: {failed_paper_map_json}
Invalid IDs: {invalid_ids_json}
Unambiguous full-ID matches: {unique_matches_json}
Complete allowed SourceBlock IDs: {allowed_block_ids_json}
Copy every Context, Transition, hierarchy edge, label, description, alias, spatial field, ambiguity, and scientific decision exactly. Change only evidence_block_ids, facet_seed_block_ids, claim_seed_block_ids, and global_claim_seed_block_ids to allowed full IDs. Return the complete corrected object only.
```
</details>

<details>
<summary>Paper-map invalid Transition repair (verbatim template)</summary>

```text
Paper: {paper_json}

Your previous output failed referential validation.
Failed output to repair:
{failed_paper_map_json}
Validation error: {validation_error}
Allowed SourceBlock IDs: {allowed_block_ids_json}
Evidence for the invalid structure:
{rendered_source_blocks}
Every existing Context object, including its parent_temp_ids, label, spatial support, and evidence, is immutable and must be copied exactly. Preserve every already-valid Transition exactly. Every Transition must connect two distinct Context states; add only the minimum supported FROM and TO child states needed to replace an invalid Transition. Do not add new scientific facts. Return a corrected object only.
```

If that proposed repair also fails deterministic validation, the implementation appends:

```text
The repair output also failed deterministic repair validation: {repair_error}
Rejected repair output:
{rejected_repair_json}
Copy every original Context object byte-for-byte. Change only invalid Transition endpoints by adding the minimum evidence-supported child Contexts. Return a corrected object only.
```
</details>

<details>
<summary>Context-reconciliation reference repair (verbatim suffix)</summary>

```text
{original_reconciliation_request}

Your previous output failed referential validation.
Validation error: {validation_error}
Valid references by hint: {valid_references_json}
Previous object: {previous_batch_json}
Repair references only and return the complete corrected object. Do not change the scientific decisions or add information.
```
</details>

## Historical v1 runtime indexing prompt files (obsolete)

The following seven blocks are retained only to explain artifacts generated before the standalone v2 rewrite. They are not the active prompt files. Use the v2 files and captured requests linked above for current behavior.

<details>
<summary><code>paper_map.txt</code> (verbatim)</summary>

```text
SYSTEM

You map the internal scientific context and comparison structure of a land-atmosphere research paper. THIS TASK IS STRUCTURE DISCOVERY ONLY.

A Context is a physical, environmental, temporal, model, observational, or scenario state under which findings are valid. A child Context inherits its parent Context and stores only conditions that differ from or specialize the parent. A Transition is a studied comparison or perturbation from one Context to another.

Identify the minimum set of Contexts, parent-child inheritance, explicit or operational Transitions/comparisons, paper-local aliases, and SourceBlock IDs relevant to later Facet and Claim extraction.

Hard rules: use only the supplied paper; do not use outside knowledge, infer enrichment variables, invent coordinates, or extract detailed mechanism Claims. Repetition alone does not create a Context. Shared conditions belong in a parent; differences scope child Contexts. Separate independent study areas. Every object cites exact SourceBlock IDs. Child split_reason is exactly one of separate_reported_finding, sign_or_null_reversal, misleading_parent_scope, explicit_transition_state; roots use null. Preserve ambiguity. Return schema-valid JSON only.

USER

Paper ID: {paper_id}

Paper text with stable SourceBlock IDs:
{paper_text}
```
</details>

<details>
<summary><code>section_scout.txt</code> (verbatim)</summary>

```text
SYSTEM

Scout one portion of a land-atmosphere paper for a later global mapping step. Do not construct the final graph. Return only context/scenario names, locations, controls/experiments, possible comparisons, Context/Claim SourceBlock seeds, cross-references, and ambiguities. Do not infer outside facts, create Facets or Claims, merge Contexts, or invent coordinates. Every item must cite exact SourceBlock IDs. Return schema-valid JSON only.

USER

Paper ID: {paper_id}
Section: {section_path}
Blocks:
{section_blocks}
```
</details>

<details>
<summary><code>map_consolidation.txt</code> (verbatim)</summary>

```text
SYSTEM

Construct one coherent Context/Transition map from section-scout outputs. Scouts are routing hints, not scientific truth. Create the minimum hierarchy. Merge aliases only with evidence; repetition does not create Contexts; shared conditions belong to a parent; scenario differences belong to children; independent study areas remain separate. Do not extract Facets or Claims, use outside knowledge, or invent coordinates. Every map object cites original SourceBlock IDs. Preserve ambiguity. Return schema-valid JSON only.

USER

Paper: {paper_metadata}
Scout outputs: {scout_outputs}
Selected original blocks: {selected_blocks}
```
</details>

<details>
<summary><code>facet_extraction.txt</code> (verbatim)</summary>

```text
SYSTEM

Extract LOCAL Context Facets from supplied land-atmosphere paper evidence. Allowed domains: spatial_configuration, land_surface, hydrology, atmosphere, climate, substrate_terrain, other. One Facet is one coherent notion with a concise value-free notion and evidence-faithful rich description.

Use only supplied passages. Do not add outside facts, enrichment variables, coordinates, normalized units, or invented values. Extract only facets owned by the target Context and do not repeat inherited unchanged parent Facets. Preserve quantities, units, directions, seasonality, layers, scale, patch/edge and upwind/downwind language when reported. Do not infer spatial relations. A distinct unregistered regime becomes an unmapped_context_hint. Every Facet cites exact SourceBlock IDs. No confidence scores. Return schema-valid JSON only.

USER

Paper: {paper_id}
Target Context: {target_context}
Context Registry: {context_registry}
Parent effective Facets: {parent_facets}
Existing local Facets: {existing_target_facets}
Evidence bundle: {evidence_blocks}
```
</details>

<details>
<summary><code>claim_extraction.txt</code> (verbatim)</summary>

```text
SYSTEM

Extract evidence-backed scientific relationships from supplied land-atmosphere paper passages. Each Claim is one FROM {concept,state} to TO {concept,state} relationship and is causal or associative.

Use causal only for explicit attribution or a directly supporting experimental perturbation; use associative otherwise. Use only supplied evidence. Never invent intermediate mechanisms. Split chains only when each step is supported. Preserve competing, null, opposite, conditional, seasonal, scale, spatial, magnitude and timing findings. Do not merge different outcomes such as LST and 2-m temperature. Classify evidence_role exactly as OWN_RESULT, AUTHORS_INTERPRETATION_OF_OWN_RESULT, CITED_BACKGROUND, or HYPOTHESIS_OR_PROPOSAL. Never convert cited background to the paper's finding. Scope must be known. conditioning_facet_ids include only materially conditioning reachable Facets, never all Context Facets. Every Claim cites exact SourceBlock IDs. No confidence. Return schema-valid JSON only.

USER

Paper: {paper_id}
Known Context Registry: {context_registry}
Known Transitions: {transitions}
Available effective Facets for target scope: {available_scope_facets}
Target scope: {target_scope}
Evidence bundle: {evidence_blocks}
```
</details>

<details>
<summary><code>context_reconciliation.txt</code> (verbatim)</summary>

```text
SYSTEM

You are reconciling possible missing Contexts in a scientific paper.

For each supplied hint decide exactly one:
1. ATTACH_TO_EXISTING_CONTEXT
2. ADD_CHILD_CONTEXT
3. ADD_INDEPENDENT_CONTEXT
4. IGNORE_AS_NOT_A_CONTEXT
5. UNRESOLVED

Rules:
- Do not use outside knowledge or rewrite scientific findings.
- Add a Context only for a scientifically distinct state that scopes findings or experimental conditions.
- Sign, null, temporal, seasonal, spatial, or scale reversals require distinct Contexts when the evidence supports them.
- Prefer parent-child inheritance when conditions are shared.
- Name only affected Claim IDs and evidence IDs supplied with that hint.
- For reversal hints, ATTACH_TO_EXISTING_CONTEXT and ADD_CHILD_CONTEXT must use an ID from that hint's allowed_context_ids. Do not add an independent Context for a scoped reversal.
- Preserve uncertainty and return every hint exactly once.
- Return only schema-valid JSON.

USER

Current Context Registry:
{context_registry}

Hints:
{hints}

Evidence:
{hint_evidence_blocks}
```
</details>

<details>
<summary><code>paper_consolidation.txt</code> (verbatim)</summary>

```text
SYSTEM

You consolidate candidate near-duplicate scientific objects from ONE paper.

YOU ARE NOT PERFORMING NEW SCIENTIFIC EXTRACTION.

For every supplied candidate pair, return exactly one decision:
- SAME
- DISTINCT
- PARENT_CHILD for Contexts only
- UNCERTAIN

Do not introduce, rewrite, or delete scientific facts. Do not use outside knowledge.
Claims may be SAME only when meaning, scope, response variable, temporal scope,
spatial scope, and counterfactual are the same. Retain contradictions as DISTINCT.
Contexts that differ in any scientifically relevant state are DISTINCT.
For PARENT_CHILD, identify parent_id and child_id from the supplied pair.
Return every pair exactly once and return only schema-valid JSON.

USER

Paper:
{paper_metadata}

Candidate pairs:
{candidate_pairs}
```
</details>

## Complete authoritative indexing prompt set

The blocks below reproduce the full prompt wording from `land_atmosphere_kg_indexing_pipeline.md`. These are the normative prompts the implementation must conform to. Section 96's bounded pair-decision consolidation protocol overrides the earlier, less-specific consolidation operation where the two differ.

<details>
<summary><code>paper_map.txt</code> (complete normative prompt)</summary>

```text
SYSTEM

You map the internal scientific context and comparison structure of a
land-atmosphere research paper.

THIS TASK IS STRUCTURE DISCOVERY ONLY.

Definitions:

A Context is a physical, environmental, temporal, model, observational,
or scenario state under which findings are valid.

A child Context inherits its parent Context and stores only conditions
that differ from or specialize the parent.

A Transition is a studied comparison or perturbation from one Context
to another.

Your job:
1. identify the minimum set of Contexts needed to represent the paper;
2. identify parent-child Context inheritance;
3. identify explicit or operational Transitions/comparisons;
4. collect paper-local aliases for each Context/Transition;
5. identify SourceBlock IDs likely relevant to later Context-Facet and
   Claim extraction.

Hard rules:
- Use only information supported by the supplied paper.
- Do not use outside geographic or scientific knowledge.
- Do not infer Köppen class, aridity, terrain, climatological wind, or
  other enrichment variables.
- Do not invent coordinates.
- Do not extract detailed mechanism Claims in this task.
- Do not create separate Contexts merely because the same study area is
  described repeatedly.
- When scenarios share location/climate/season/background conditions,
  create a common parent Context and child scenario Contexts.
- Create separate Contexts when differences actually scope different
  findings: e.g. land state, management state, season, experimental
  scenario, geographic study area, or physically distinct condition.
- For every child Context return `split_reason` using exactly one of:
  `separate_reported_finding`, `sign_or_null_reversal`,
  `misleading_parent_scope`, `explicit_transition_state`. Root Contexts
  use null. Follow the normative decision rule in Section 97.1.
- If a paper contains multiple independent study areas, represent them
  separately.
- Preserve uncertainty. If two structures cannot be safely merged,
  keep them separate and flag the ambiguity.
- A spatial support may be point, patch, watershed, region,
  climate_zone, global, or unresolved.
- Every Context and Transition must cite one or more SourceBlock IDs.
- Context labels should usually be concise 3–12 word noun phrases; Transition
  labels 2–10 words. Aliases should be paper-local names/IDs, not invented
  semantic synonyms.
- Transition descriptions should usually be 10–50 words and describe the
  comparison/manipulation itself, not its climatic outcome. Do not pad to meet
  these soft ranges.
- Return only JSON that conforms to the supplied schema.

USER

Paper ID:
{paper_id}

Paper text with stable SourceBlock IDs:
{paper_text}
```
</details>

<details>
<summary><code>section_scout.txt</code> (complete normative prompt)</summary>

```text
SYSTEM

You are scouting ONE portion of a scientific land-atmosphere paper to
help a later global paper-mapping step.

Do not construct the final graph.

Return only:
- context/scenario names or aliases mentioned;
- location/study-area names;
- control/experiment names;
- possible comparisons or transitions;
- SourceBlock IDs containing study-context information;
- SourceBlock IDs containing results/mechanisms;
- unresolved references to other parts of the paper.

Do not:
- infer outside facts;
- create detailed Facets;
- create causal Claims;
- merge contexts;
- invent coordinates.

Every item must cite SourceBlock IDs.

USER

Paper ID:
{paper_id}

Section:
{section_path}

Blocks:
{section_blocks}
```
</details>

<details>
<summary><code>map_consolidation.txt</code> (complete normative prompt)</summary>

```text
SYSTEM

You are constructing ONE coherent Context/Transition map for a
scientific paper from section-scout outputs.

The scout outputs are routing hints, not scientific truth.

Construct the minimum Context hierarchy needed to represent the paper.

Rules:
- Merge aliases only when evidence indicates they refer to the same
  context/scenario.
- Repeated descriptions of the same study area do not create new
  Contexts.
- Shared conditions should live in a parent Context.
- Scenario-specific differences should live in child Contexts.
- Multiple independent geographic study areas remain separate.
- Do not extract detailed Facets or mechanism Claims.
- Do not use outside knowledge.
- Do not invent coordinates.
- Every finalized map object must cite original SourceBlock IDs.
- Preserve unresolved ambiguity rather than forcing a merge.
- Return only schema-valid JSON.

USER

Paper:
{paper_metadata}

Scout outputs:
{scout_outputs}

Selected original blocks for resolving structure:
{selected_blocks}
```
</details>

<details>
<summary><code>facet_extraction.txt</code> (complete normative prompt)</summary>

```text
SYSTEM

You extract LOCAL Context Facets from land-atmosphere scientific papers.

A Facet describes one coherent aspect of the environmental/scenario
Context.

Allowed domains:
- spatial_configuration
- land_surface
- hydrology
- atmosphere
- climate
- substrate_terrain
- other

Each Facet contains:
- domain
- notion: short open-vocabulary scientific noun phrase, usually 2–8 words;
- description: faithful information-rich description, usually 20–60 words;
- evidence SourceBlock IDs.

The word ranges are soft targets. Never invent or pad information to hit them.
A shorter description is correct when the evidence is simple; a longer one is
correct when essential qualifiers make one coherent notion genuinely complex.

Important representation rule:
A Facet can remain richly descriptive. Preserve useful quantities,
ranges, units, directions, seasonality, spatial relationships, and
qualifications inside the description. Do not force a descriptive
scientific variable into one scalar.

Hard rules:
1. Use only supplied source passages.
2. Do not add outside scientific or geographic knowledge.
3. Do not infer enrichment variables such as Köppen class, aridity,
   terrain metrics, soil class, or climatological wind unless the paper
   itself reports them.
4. Do not normalize units.
5. Do not create numerical values that are not reported.
6. Extract only LOCAL facets belonging to the target Context.
7. Do not repeat facets inherited unchanged from parent Contexts.
8. If the child explicitly differs from the parent, extract the
   child-specific difference.
9. One Facet = one coherent notion, not necessarily one scalar.
10. Do not split a rich wind regime into speed/direction/moisture/season
    unless the source presents genuinely distinct regimes that need
    independent retrieval.
11. There is no separate Facet scope field. Preserve season, atmospheric
    layer, time of day, subregion, spatial scale, and similar qualifiers
    inside the description. If they define a genuinely separate Context,
    emit an unmapped_context_hint instead.
12. For spatial_configuration, preserve reported upwind/downwind,
    windward/leeward, edge/interior, patch-scale, orientation, distance,
    and source/sink relationships when present. Do not infer them.
13. Every reported Facet must cite at least one exact SourceBlock ID.
14. origin is "reported".
15. Do not assign confidence scores.
16. If the text appears to describe a Context not present in the
    registry, emit an unmapped_context_hint instead of silently
    attaching it to the target.
17. Keep `notion` concise and value-free where possible; put magnitude,
    direction, season, layer, and detailed state in `description`.
18. Aim for a 20–60 word description without padding or dropping material
    qualifiers. Split only when there are multiple coherent notions.
19. Return only schema-valid JSON.

USER

Paper:
{paper_id}

Target Context:
{target_context}

Context Registry:
{context_registry}

Parent effective Facets already known:
{parent_facets}

Existing local Facets for target:
{existing_target_facets}

Evidence bundle:
{evidence_blocks}
```
</details>

<details>
<summary><code>claim_extraction.txt</code> (complete normative prompt)</summary>

```text
SYSTEM

You extract evidence-backed scientific relationships from a
land-atmosphere research paper.

Each Claim represents ONE paper-supported relationship:

FROM {concept, state}
    -- relation -->
TO   {concept, state}

Endpoint `concept` should usually be a compact 1–8 word scientific noun
phrase. Endpoint `state` should usually be a compact 1–5 word directional or
categorical state. Claim `description` should usually be 15–50 words. These
are soft targets: never invent, pad, or omit material qualifiers to meet them.

Allowed relation:
- causal
- associative

Use "causal" only when:
- the paper explicitly attributes an effect/response to the source
  condition or process; OR
- the experimental perturbation directly supports that interpretation.

Use "associative" for:
- correlation;
- spatial/temporal co-occurrence;
- statistical association;
- observational preference;
- relationships where causal attribution is not established.

Hard rules:
1. Extract only relationships supported by supplied source passages.
2. Never add an intermediate mechanism merely because it is
   scientifically plausible.
3. Split a multi-step mechanism chain only if each individual step is
   supported by the supplied text.
4. Preserve competing pathways as separate Claims.
5. Preserve null effects as Claims when scientifically meaningful.
6. Preserve opposite effects rather than reconciling them.
7. Preserve qualifiers in the Claim description: season, scale,
   location, magnitude, threshold, timing, wind regime, etc.
8. Do not merge physically different outcome variables.
   Example: LST != 2-m air temperature.
9. Do not convert a cited background claim into this paper's own finding
   unless the authors explicitly adopt/test it in the study.
10. scope_id must be one known Context or Transition.
11. If the true scope is not in the Context Registry, emit an
    unmapped_context_hint.
12. Every Claim must cite exact SourceBlock IDs.
13. Do not assign confidence scores.
14. Do not decide whether the Claim is universally true.
15. Return `evidence_role` for every candidate using exactly one of:
    OWN_RESULT, AUTHORS_INTERPRETATION_OF_OWN_RESULT, CITED_BACKGROUND,
    HYPOTHESIS_OR_PROPOSAL. Only the first two are ingestible Claims.
16. `conditioning_facet_ids` may reference existing Context Facets that
    supplied evidence specifically indicates are important to this Claim's
    interpretation or transferability. Do not attach every Context Facet.
17. If no particular conditioning Facets are supported, return an empty list.
18. Keep endpoint concepts free of season/location/magnitude when possible;
    preserve such qualifiers in the Claim description or scoped Context.
19. Keep endpoint states compact. Do not create highly specific canonical-like
    states such as "increase by 3–4 C at night"; use `increase` and preserve
    the magnitude/time qualifier in `description`.
20. Aim for a 15–50 word Claim description without padding. It may be longer
    when required to preserve conditional, spatial, or non-monotonic behavior.
21. Return only schema-valid JSON.

USER

Paper:
{paper_id}

Known Context Registry:
{context_registry}

Known Transitions:
{transitions}

Available effective Facets for the target scope:
{available_scope_facets}

Target scope:
{target_scope}

Evidence bundle:
{evidence_blocks}
```
</details>

<details>
<summary><code>context_reconciliation.txt</code> (complete normative prompt plus required reversal rules)</summary>

```text
SYSTEM

You are reconciling possible missing Contexts in a scientific paper.

You are given:
- the current Context Registry;
- extracted objects;
- raw evidence for new context hints.

For each hint decide exactly one:
1. ATTACH_TO_EXISTING_CONTEXT
2. ADD_CHILD_CONTEXT
3. ADD_INDEPENDENT_CONTEXT
4. IGNORE_AS_NOT_A_CONTEXT
5. UNRESOLVED

Rules:
- Do not use outside knowledge.
- Do not rewrite scientific findings.
- Do not create a Context solely for a repeated description.
- Add a Context only when it represents a scientifically distinct state
  that scopes findings or experimental conditions.
- Prefer parent-child inheritance when conditions are shared.
- Preserve uncertainty.
- Cite SourceBlock IDs.

Return only schema-valid JSON.

USER

Current Context Registry:
{context_registry}

Hints:
{hints}

Evidence:
{hint_evidence_blocks}
```

The later normative reversal rules tighten this base prompt. The active runtime adds these requirements:

```text
- Sign, null, temporal, seasonal, spatial, or scale reversals require
  distinct Contexts when the evidence supports them.
- Name only affected Claim IDs and evidence IDs supplied with that hint.
- For reversal hints, ATTACH_TO_EXISTING_CONTEXT and ADD_CHILD_CONTEXT
  must use an ID from that hint's allowed_context_ids.
- Do not add an independent Context for a scoped reversal.
- Return every hint exactly once.
```
</details>

<details>
<summary><code>paper_consolidation.txt</code> (complete earlier-stage prompt)</summary>

```text
SYSTEM

You consolidate previously extracted scientific objects from ONE paper.

YOU ARE NOT PERFORMING NEW SCIENTIFIC EXTRACTION.

Allowed operations:
- merge duplicate Context candidates that clearly describe the same
  scientific state;
- finalize parent-child Context relationships;
- merge duplicate local Facets within the same Context;
- merge duplicate Claims with the same meaning AND same scope;
- preserve all evidence IDs from merged objects;
- repair references after merges;
- retain competing or contradictory Claims;
- flag unresolved conflicts.

Forbidden operations:
- introducing new Contexts, Facets, Claims, mechanisms, quantities, or
  scientific facts;
- using outside knowledge;
- moving a child-specific Facet to a parent unless the input evidence
  establishes that it applies to all children;
- merging Contexts that differ in a scientifically relevant state;
- merging Claims across different response variables, temporal scopes,
  spatial scopes, or counterfactuals;
- choosing one contradictory Claim and deleting another;
- assigning confidence scores;
- filling missing values;
- reconciling reported context against derived enrichment.

Inheritance rule:
A child stores LOCAL Facets only.
Effective retrieval context is computed later from ancestors + local
Facets.

Traceability rule:
Every finalized object must map to at least one candidate input object.

Return:
1. finalized Contexts
2. finalized Transitions
3. finalized Facets
4. finalized Claims
5. unresolved conflicts
6. provisional-to-final ID mapping

Return only schema-valid JSON.

USER

Paper:
{paper_metadata}

Context Registry:
{context_registry}

Candidate Facets:
{facet_candidates}

Candidate Claims:
{claim_candidates}

Candidate Transitions:
{transition_candidates}
```

The later normative Section 96.12 restricts this to precomputed candidate pairs and the labels `SAME`, `DISTINCT`, `PARENT_CHILD`, or `UNCERTAIN`. It prohibits the LLM from creating finalized scientific objects. The active runtime `paper_consolidation.txt`, reproduced earlier, implements that later rule and therefore intentionally does not use this earlier output shape.
</details>

<details>
<summary><code>state_adjudication.txt</code> (complete normative offline prompt)</summary>

```text
SYSTEM

Decide whether two scientific graph concepts should share the SAME
canonical State concept.

Allowed answers:
- SAME
- RELATED_BUT_DISTINCT
- DIFFERENT
- UNCERTAIN

SAME means the terms can be substituted without changing the scientific
variable/process being represented.

RELATED_BUT_DISTINCT means they are mechanistically connected or often
correlated but should remain separate graph nodes.

Rules:
- Be conservative.
- Do not merge a flux with a state variable.
- Do not merge a mechanism with its outcome.
- Do not merge moisture convergence with moisture recycling.
- Do not merge latent heat flux with evapotranspiration solely because
  they are closely related.
- Use supplied definitions/evidence only.
- Return schema-valid JSON.

USER

Concept A:
{concept_a}

Examples/evidence:
{examples_a}

Concept B:
{concept_b}

Examples/evidence:
{examples_b}
```

This is an offline vocabulary-maintenance call, not a mandatory per-paper stage. It must not silently alter per-paper ingest identity.
</details>

<details>
<summary>Conditioning-Facet adjudication (complete normative bounded prompt)</summary>

```text
SYSTEM
You decide whether an existing Context Facet specifically conditions the
interpretation or transferability of one already-extracted Claim.
Use only the supplied Claim, Facet, and evidence passages.
Return exactly one label: CONDITIONING, BACKGROUND_ONLY, UNRELATED, UNCERTAIN.
CONDITIONING requires evidence that the effect depends on, changes under,
is stronger/weaker under, is located/oriented by, or is experimentally
defined by the Facet. Mere coexistence in the study Context is BACKGROUND_ONLY.
When uncertain, return UNCERTAIN.

USER
Claim: {claim}
Candidate Facet: {facet}
Claim evidence: {claim_evidence}
Facet evidence: {facet_evidence}
```

The specification requires `thinking=no`. The pass is mandatory when deterministic candidate generation finds one or more candidate Facets and the Claim is used for spatial transfer or the paper reports conditional or reversing effects. Otherwise it may be skipped.
</details>

## Indexing LLM envelopes

Every structured call saves an envelope containing:

```text
call_id
paper_id
stage
model
prompt_version
thinking_level
input_block_ids
raw_response_path
validated
retry_number
elapsed_seconds
validation_errors or transport/HTTP error path when applicable
```

This connects each model decision to the prompt stage, prompt version, model, evidence IDs, raw response, validation result, and retry. The current envelope does **not** store the rendered system message, rendered user message, or the JSON Schema body. A request can be reconstructed from the versioned template, schema model, saved input Block IDs, and stage artifacts, but the absence of a byte-for-byte rendered request in the envelope is a reproducibility gap.

## Step-by-step indexing pipeline

### Step 1: Register the paper

Entry point: `climatekg.pdf.register_pdf`.

The pipeline computes a SHA-256 hash, assigns a stable Paper ID, copies the PDF into the paper directory, and creates `manifest.json`. Duplicate source files are detected by hash. The manifest records status changes and model versions.

### Step 2: Render pages

Entry point: `climatekg.pdf.parse_pdf` and worker `climatekg/workers/pdfium_render.py`.

PDFium renders every page to an image. It also writes a page manifest. Rendering fails visibly when no page is produced. This isolated environment exists only because page rendering and Nemotron inference need different Python packages.

### Step 3: Parse with NVIDIA Nemotron-Parse v1.2

Worker: `climatekg/workers/nemotron_parse.py`.

Nemotron-Parse reads the page images and returns page-level text and layout elements. The pipeline verifies that:

- the parser identity is exactly `nvidia/NVIDIA-Nemotron-Parse-v1.2`;
- at least one page was parsed;
- rendered and parsed page numbers match exactly;
- parsed text is not empty.

The raw JSON, reconstructed Markdown, worker command, standard output, and errors are saved. A failed parse does not switch to another parser.

### Step 4: Clean parsed text

Entry point: `climatekg.pdf.clean_parse`.

Python performs deterministic cleaning:

- Unicode normalization;
- repeated page-header and footer removal;
- conservative repair of line-wrap hyphenation;
- whitespace normalization;
- reference-section marking;
- preservation of in-text citations, tables, and relevant scientific text.

Cleaning does not use an LLM.

### Step 5: Build stable SourceBlocks

Entry point: `climatekg.pdf.build_source_blocks`.

The cleaner output is divided at section, paragraph, list, figure-caption, and table boundaries. Each SourceBlock receives:

- stable ID;
- Paper ID;
- document order;
- page number when available;
- section path;
- block type;
- text;
- source locator;
- an oversize-split flag.

Blocks are limited to 1,500 tokens. Oversized text is split near 1,100 tokens using deterministic boundaries. The result is saved as `blocks.jsonl`.

### Step 6: Embed SourceBlocks

When block embeddings are enabled, `qwen3-embedding:4b` creates a 2,048-dimensional vector for each SourceBlock. The cache is reused only when it contains the exact expected Block IDs and vector dimensions.

These embeddings help select focused evidence bundles later. They do not replace provenance: extracted objects still cite exact Block IDs.

### Step 7: Map the paper

Entry points: `climatekg.extract.map_paper` and `permanent_map`.

Short papers are mapped in one request. Long papers are divided into section groups, mapped by section scouts, and then consolidated. The local generative model identifies proposed Contexts, Transitions, important results, and evidence locations.

Python validates the structured response, assigns permanent IDs, and saves the request and response envelopes. The model cannot create arbitrary graph nodes outside the defined schemas.

### Step 8: Build Context evidence bundles

Python combines map evidence, lexical retrieval, semantic block retrieval, and adjacent blocks. Candidate blocks are ordered and trimmed to the configured input budget. This gives the extraction model focused evidence without losing the SourceBlock IDs.

### Step 9: Extract Facets

Entry point: `climatekg.extract.extract_facets`.

The local model extracts typed Facets for each Context. `Facet.domain` uses the controlled set:

```text
spatial_configuration
land_surface
hydrology
atmosphere
climate
substrate_terrain
other
```

The notion and description remain open scientific text. This avoids forcing all studies into a small set of rigid columns. Each Facet keeps only the smallest sufficient evidence set.

### Step 10: Extract Claims

Entry point: `climatekg.extract.extract_claims`.

For each Context or Transition, Python prepares an evidence bundle and the local model extracts Claims. A Claim contains:

- source concept and state;
- target concept and state;
- causal or associative relation;
- plain scientific description;
- evidence role;
- only the Facets that materially condition applicability;
- exact supporting SourceBlock IDs.

The evidence role prevents cited background literature from being presented as a new result of the indexed paper. Null, conditional, contradictory, seasonal, and sign-reversing results are preserved.

### Step 11: Reconcile late Context information

Entry point: `climatekg.reconcile.reconcile_contexts`.

Facet or Claim extraction can reveal that the initial paper map combined two scientifically different regimes. The reconciliation stage can split or repair Context ownership within a bounded number of rounds. It preserves unresolved conflicts instead of hiding them.

### Step 12: Deterministic cleanup and consolidation

Entry point: `climatekg.consolidate.consolidate_paper`.

Python first removes exact duplicates and validates IDs and references. The local model is used only for bounded semantic consolidation where scientific judgment is needed. Similarity proposes candidates; it does not force uncertain merges.

### Step 13: Canonicalize States

Entry point: `climatekg.canonicalize.canonicalize_claim_states`.

Concept text and state direction are normalized deterministically. Only verified entries in `config/state_aliases.yaml` are treated as exact identities. Unknown scientific wording is retained as a new canonical concept rather than being over-normalized.

For example, the demonstrated query failure established that `surface temperature`, `surface air temperature`, and `near-surface air temperature` needed one verified concept identity. They now map to `surface air temperature`. `land surface temperature` is deliberately not included because it is a distinct physical measurement.

When an alias changes after indexing, `python -m climatekg.cli recanonicalize-states` rebuilds only Claim endpoints, States, and their embeddings. It backs up the old `final_paper.json` and writes an endpoint-change audit.

### Step 14: Create retrieval embeddings

Entry point: `climatekg.embeddings.embed_paper`.

The system creates separate vectors for:

- Facet notion;
- Facet full content;
- effective Context text, including inherited Facets;
- Claim text;
- Transition text;
- State concept;
- SourceBlock text when enabled.

The separate Facet vectors allow the query pipeline to compare both the kind of condition and its detailed meaning.

### Step 15: Validate and save `final_paper.json`

The centralized Pydantic models reject extra fields and broken references. Validation checks Context hierarchy, Claim scopes, State endpoints, evidence IDs, conditioning Facets, and Paper ownership. Malformed objects are not silently accepted.

`final_paper.json` is the complete, versioned graph package for one paper.

### Step 16: Ingest into Neo4j

Entry point: `climatekg.graph.Neo4jHttp.ingest`.

Neo4j contains unique constraints, full-text indexes, and cosine vector indexes. Ingestion replaces one paper atomically:

1. Delete the old paper-owned nodes and relationships.
2. Keep shared canonical State nodes.
3. Create the Paper and SourceBlocks.
4. Create Contexts and parent-child links.
5. Create Facets and attach them to Contexts.
6. Create Transitions and their source/target Context links.
7. Merge canonical States.
8. Create Claims and connect their source and target States.
9. Add Claim scope, conditioning, and evidence relationships.
10. Verify the paper counts before accepting the ingestion.

The current ten-paper graph contains 10 Papers, 2,184 SourceBlocks, 101 Contexts, 437 Facets, 51 Transitions, 213 Claims, and 314 active canonical State nodes.

## Three real indexing traces

These are not invented examples. They are shortened views of saved production artifacts. Long text and 2,048-number embedding arrays are abbreviated here, but the named JSON files contain the complete values. The three traces continue through querying in the next main section.

### Trace A: tropical deforestation paper (`P000002`)

**PDF, parse, clean, and block creation.** The registered source is `41467_2024_Article_51783.pdf`, with SHA-256 `927b0c681612f3526f8a40462a7b3ce456fcd606c8a6ef252cf7aeae4d666098`. Its saved manifest reports:

```json
{
  "paper_id": "P000002",
  "status": "complete",
  "parser": "nemotron-parse-v1.2",
  "extractor_model": "qwen3.6:27b",
  "embedding_model": "qwen3-embedding:4b",
  "counts": {
    "source_blocks": 148,
    "contexts": 15,
    "facets": 46,
    "transitions": 5,
    "claims": 59,
    "states": 63
  }
}
```

The exact files for the early stages are:

```text
climatekg/runtime/data/papers/P000002/source/paper.pdf
climatekg/runtime/data/papers/P000002/parse/nemotron_raw.json
climatekg/runtime/data/papers/P000002/parse/nemotron.md
climatekg/runtime/data/papers/P000002/clean/cleaned.md
climatekg/runtime/data/papers/P000002/blocks/blocks.jsonl
```

One generated SourceBlock used by the final answer is:

```json
{
  "id": "P000002:S03:P0025",
  "page": 3,
  "section_path": ["Discussion of physical mechanisms of forest-cloud impacts"],
  "block_type": "paragraph",
  "text_excerpt": "...shifting from forests to open land induces surface warming in tropical regions... primarily due to the prevailing impact of ET... In contrast... deforestation leads to surface cooling in the boreal zone..."
}
```

This single Block preserves the reported climate-zone sign reversal instead of flattening it into one global result.

**Map, Facet, Claim, and State output.** `extraction/map/paper_map.json` contains 15 Contexts, 5 Transitions, 3 global Claim seed Blocks, and no unresolved map ambiguity. The relevant mapped Context and extracted Facet include:

```json
{
  "context": {
    "id": "P000002_C004",
    "parent_ids": ["P000002_C001"],
    "label": "Tropical climate zone focus",
    "evidence_block_ids": [
      "P000002:S02:P0019",
      "P000002:S03:P0025",
      "P000002:S03:P0026",
      "P000002:S10:P0046"
    ]
  },
  "facet": {
    "id": "P000002_F004",
    "context_id": "P000002_C001",
    "domain": "hydrology",
    "notion": "Tropical latent heat flux reduction mechanism",
    "evidence_block_ids": ["P000002:S03:P0026", "P000002:S03:P0027"]
  }
}
```

Two separately preserved Claims point to the same canonical endpoint while retaining different relation types:

```json
[
  {
    "id": "P000002_CL041",
    "scope_type": "context",
    "scope_id": "P000002_C004",
    "from": {"concept": "deforestation", "state": "occurrence"},
    "to": {"concept": "surface air temperature", "state": "increase"},
    "relation": "causal",
    "evidence_role": "OWN_RESULT",
    "evidence_block_ids": ["P000002:S03:P0025"]
  },
  {
    "id": "P000002_CL018",
    "scope_type": "context",
    "scope_id": "P000002_C004",
    "from": {"concept": "deforestation", "state": "occurrence"},
    "to": {"concept": "surface air temperature", "state": "increase"},
    "relation": "associative",
    "conditioning_facet_ids": ["P000002_F004"],
    "evidence_block_ids": ["P000002:S03:P0025"]
  }
]
```

Canonicalization connects these endpoints to `state::deforestation::occurrence` and `state::surface_air_temperature::increase`. The complete paper object, including all embedding vectors and evidence links, is `climatekg/runtime/data/papers/P000002/final/final_paper.json`.

### Trace B: dry-versus-wet soil rainfall paper (`P000006`)

**PDF through SourceBlocks.** The registered source is `nature11377.pdf`, SHA-256 `fe1352c41f7918c1afc21255a795543e2378ba324736ab41d3868cbca99604d4`. Nemotron Parse v1.2 produced the Markdown used to generate 64 stable Blocks. The completed manifest contains 9 Contexts, 42 Facets, 4 Transitions, 15 Claims, and 29 paper-level State records.

The decisive observational Block is:

```json
{
  "id": "P000006:S00:P0020",
  "page": 3,
  "block_type": "paragraph",
  "text_excerpt": "The most negative values occur during daytime, in particular between 12:00 and 15:00. By contrast, between 21:00 and 3:00 the opposite signal emerges; that is, events are more likely to be found over wetter soils."
}
```

The mapping stage represented that reversal explicitly:

```json
{
  "id": "P000006_T002",
  "from_context_id": "P000006_C004",
  "to_context_id": "P000006_C005",
  "label": "Diurnal Lag Time Comparison",
  "description": "Comparison across diurnal lag times, revealing a sign reversal from dry-soil preference in early afternoon to wet-soil preference at night.",
  "evidence_block_ids": ["P000006:S00:P0020"]
}
```

The observational and model results remain distinct Claims:

```json
[
  {
    "id": "P000006_CL007",
    "scope_type": "transition",
    "scope_id": "P000006_T002",
    "from": {"concept": "afternoon time window 12 00-15 00", "state": "null"},
    "to": {
      "concept": "negative soil moisture-precipitation feedback",
      "state": "preference for precipitation over drier soils"
    },
    "relation": "associative",
    "evidence_role": "OWN_RESULT",
    "evidence_block_ids": ["P000006:S00:P0020"]
  },
  {
    "id": "P000006_CL001",
    "scope_type": "transition",
    "scope_id": "P000006_T001",
    "from": {"concept": "simulated soil moisture state", "state": "wetter than surrounding area"},
    "to": {"concept": "convective precipitation", "state": "more_frequent"},
    "relation": "associative",
    "conditioning_facet_ids": ["P000006_F017"],
    "evidence_block_ids": ["P000006:S00:P0021", "P000006:S00:P0023"]
  }
]
```

This paper is a useful trace because consolidation did not merge the observational dry-soil result with the contrasting simulated wet-soil result. The complete objects are in `climatekg/runtime/data/papers/P000006/final/final_paper.json`.

### Trace C: Sahel albedo perturbation paper (`P000015`)

**PDF through SourceBlocks.** The registered source is the 1975 Charney paper, SHA-256 `50216f34da1821a3f75c03ffad56d68d730591bdbe85ced6c4fd55b4b2acbc4d`. Its complete manifest reports 69 SourceBlocks, 8 Contexts, 36 Facets, 4 Transitions, 10 Claims, and 16 paper-level State records.

The central parsed and cleaned evidence became this Block:

```json
{
  "id": "P000015:S06:P0059",
  "page": 9,
  "section_path": ["APPENDIX I: GENERAL CIRCULATION MODEL SIMULATIONS"],
  "block_type": "paragraph",
  "text_excerpt": "The albedo north of 18 degrees N was then increased to 0.35... From the first week on a drop in precipitation of about 40% occurred... and persisted... for the entire six-week period."
}
```

The map and Facet stages retained the experiment geometry and timing:

```json
{
  "transition": {
    "id": "P000015_T002",
    "from_context_id": "P000015_C006",
    "to_context_id": "P000015_C007",
    "label": "GCM Control to High Albedo Perturbation (North of 18 degrees N)",
    "evidence_block_ids": ["P000015:S06:P0059"]
  },
  "facets": [
    {
      "id": "P000015_F031",
      "domain": "land_surface",
      "notion": "High Albedo Perturbation Configuration North of 18 degrees N"
    },
    {
      "id": "P000015_F034",
      "domain": "spatial_configuration",
      "notion": "Simulation Temporal Window and Geographic Domain"
    }
  ]
}
```

The two directly relevant causal Claims are:

```json
[
  {
    "id": "P000015_CL009",
    "scope_type": "transition",
    "scope_id": "P000015_T004",
    "from": {"concept": "surface albedo", "state": "increase"},
    "to": {"concept": "precipitation", "state": "decrease"},
    "relation": "causal",
    "conditioning_facet_ids": ["P000015_F031", "P000015_F034"],
    "evidence_block_ids": ["P000015:S01:P0010", "P000015:S06:P0059"]
  },
  {
    "id": "P000015_CL004",
    "scope_type": "transition",
    "scope_id": "P000015_T002",
    "from": {"concept": "surface albedo", "state": "increase"},
    "to": {"concept": "precipitation", "state": "decrease"},
    "relation": "causal",
    "conditioning_facet_ids": ["P000015_F018"],
    "evidence_block_ids": ["P000015:S06:P0059"]
  }
]
```

Both Claims connect `state::surface_albedo::increase` to `state::precipitation::decrease`. Their Context, Facet, Transition, Claim, State, evidence-link, and embedding records are in `climatekg/runtime/data/papers/P000015/final/final_paper.json`.

**Embedding and graph completion for all three traces.** SourceBlock, Facet notion, Facet content, effective Context, Claim, Transition, and State-concept texts were embedded with `qwen3-embedding:4b`; stored vectors have 2,048 dimensions. Neo4j ingestion then created the paper-owned nodes and evidence/scope/endpoint relationships described above. The current graph-wide integrity check reports zero unsupported Claims, zero unscoped Claims, zero endpoint-less Claims, and zero orphan canonical States.

# 2. Querying

## Query schemas

### Persistent query schemas

```text
QueryFacet
  id: str
  domain: the same seven-domain vocabulary used by indexed Facets
  notion: str
  description: str
  origin: user | provided_dataset | derived
  source: ProvenanceSource | null
  supporting_text_span: str | null
  notion_embedding: list[float] | null
  content_embedding: list[float] | null

QueryContext
  spatial_support: SpatialSupport | null
  facets: list[QueryFacet]

QuerySpec
  query_id: str
  mode: forward | backward | a_to_b | global
  context: QueryContext
  source: ClaimEndpoint | null
  target: ClaimEndpoint | null
  intervention_description: str | null
  user_question: str
  ambiguities: list[str]
```

The Query Context uses the same Facet language as indexed Contexts. This is what makes direct Context comparison possible.

### Query-parser output schemas

| Schema | Fields |
|---|---|
| `ParsedEndpoint` | concept, state, exact supporting text span |
| `ParsedQueryFacet` | domain, notion, description, exact supporting text span |
| `ParsedQueryFacetBatch` | required list of explicit Context Facets for repair |
| `SpatialReference` | exact user location text and optional kind hint |
| `ParsedQuery` | optional endpoints, intervention description, explicit Facets, optional spatial reference, global flag, ambiguities |

Exact-span validation is deterministic. Unsupported items are removed individually. Reporting words such as `effects` and `reported`, spatial `where relative to` phrases, duplicate place Facets, and comparative `X or Y` phrases are handled by explicit rules rather than being forced into false States.

### Final synthesis schema

```text
SynthesisItem
  text: str
  support_claim_ids: list[str]
  support_query_facet_ids: list[str]
  kind: direct_finding | transfer_inference | mechanism |
        spatial_guidance | limitation

SynthesisOutput
  direct_answer: list[SynthesisItem]
  mechanisms: list[SynthesisItem]
  spatial_guidance: list[SynthesisItem]
  conditions_and_limitations: list[SynthesisItem]
  contradictory_evidence: list[SynthesisItem]
```

All five output lists and both support-ID lists are required. This prevents fluent text from bypassing structured provenance. `models.py` also contains the simpler `AnswerItem` and `Answer` public models, but the implemented synthesis call uses the stricter `SynthesisOutput` contract above.

### Deterministic intermediate report schemas

These records are created by Python rather than by the LLM. They are saved in `query_report.json` so every retrieval decision can be reproduced.

```text
Context report
  context_id
  paper_id
  coarse_ann_score
  context_similarity
    semantic_similarity
    coverage
    overall_score
    alpha
    missing_coverage_penalty_lambda
    domain_scores
      <domain>
        score
        status
    facet_matches
      query_facet_id
      candidate_facet_id
      domain
      notion_similarity
      content_similarity
      pair_score
    missing_query_facets

Claim candidate
  claim_id
  channels
  R_claim
  A_claim
  applicability_known
  context_coverage
  S_claim_semantic
  S_transition
  S_endpoint
  conditioning_match
    score
    known_coverage
    matches
  scope_context_id

Path report
  claim_ids
  state_ids
  A_path
  C_path
  M_path
  length_factor
  R_path
  context_unknown
  coherence_unknown

Spatial transfer report
  families
  allowed
  method
  matched_phrases
  parsed_scales
  blocking_reasons
```

The complete `query_report.json` contains:

```text
query_id
query_pipeline_version
query_spec
context_gate_disabled_reason
context_candidates
state_mapping
claim_candidates
paths
contradictions_and_alternatives
synthesis_package
source_blocks
synthesis
answer
prompt_versions
models
state_alias_registry_version
effective_parameters
warnings
```

`A_claim` and `A_path` may be null. Null means that applicability is unknown; it is not converted to a mismatch or a truth probability.

## Query prompts

| Prompt | Purpose | Output schema | Temperature | Thinking |
|---|---|---|---:|---|
| `query_parse.txt` | parse the question into a retrieval request | `ParsedQuery` | 0.0 | no |
| generated Context repair prompt | recover explicit omitted Context Facets | `ParsedQueryFacetBatch` | 0.0 | no |
| `final_synthesis.txt` | answer only from the selected evidence package | `SynthesisOutput` | 0.0 | low or medium |

The verbatim query templates are [`query_parse.txt`](../../../prompts/query_parse.txt) and [`final_synthesis.txt`](../../../prompts/final_synthesis.txt). The Context repair prompt is generated in `parse_query` and is reproduced below.

### `query_parse.txt`

This prompt extracts only information stated by the user. It identifies optional endpoints, an intervention description, explicit Context Facets, a location reference, ambiguity, and whether a global synthesis was explicitly requested.

Input:

```text
{user_question}
```

Its main rules are:

- do not add geographic, climate, soil, terrain, wind, or land-cover facts from model knowledge;
- every endpoint and explicit Facet must include an exact copied supporting span;
- environmental phrases introduced by `in`, `under`, `during`, or `with` become Facets when appropriate;
- a pure place name is SpatialSupport rather than a duplicate Facet;
- broad relation words are not State directions;
- `where` relations remain spatial retrieval information;
- alternatives such as `drier or wetter` remain comparisons rather than one State;
- `global_requested` is true only for explicit global, corpus-wide, or across-literature wording;
- no answer, mechanism, coordinates, or confidence score is generated here.

### Generated query Context repair prompt

When an environmental opening phrase is present but the first parse omits Facets, a second request extracts only explicitly stated Context Facets. It copies exact supporting spans and cannot infer facts. The required `ParsedQueryFacetBatch` schema prevents omission of the Facet list.

The actual generated system and user messages are:

```text
SYSTEM

Extract only environmental Context Facets explicitly stated in the user
question. Do not infer facts. Each Facet must contain an exact
supporting_text_span copied from the question. Return schema-valid JSON only.

USER

USER QUESTION
{question}

The opening environmental preamble was omitted previously. Represent its stated climate, season, land surface, hydrology, atmosphere, terrain, and spatial-configuration information as explicit_context_facets.
```

### `final_synthesis.txt`

This prompt produces the answer only from the final evidence package.

Inputs:

```text
{question}
{query_spec}
{query_context}
{selected_paths}
{contradictions}
{source_blocks}
```

Its central instructions are:

```text
Every substantive scientific statement cites supporting Claim IDs.
Every query-area fact cites Query Facet IDs.
Combine Claims only along supplied paths.
Do not invent mechanisms, locations, magnitudes, directions, or distances.
Distinguish direct findings, transfer inference, uncertainty, mismatch,
missing information, and contradictions.
Scores are retrieval scores, not confidence.
Spatial translation is allowed only when the supplied package says so.
```

Thinking is selected deterministically. It is medium when alternatives exist, at least four paths are selected, spatial translation is allowed, or multiple target states are present. Otherwise it is low.

## Historical v1 query prompt templates (obsolete)

These blocks document the pre-v2 query prompts used by older validation artifacts. The active standalone v2 templates are `prompts/query_parse.txt` and `prompts/final_synthesis.txt`.

<details>
<summary><code>query_parse.txt</code> (verbatim)</summary>

```text
SYSTEM

Parse a land-atmosphere user question into a minimal retrieval request.

Return only information stated by the user. Do not add environmental,
geographic, climatic, hydrologic, terrain, wind, soil, or land-cover
facts from your own knowledge.

Tasks:
1. identify an optional source State {concept, state};
2. identify an optional target State {concept, state};
3. preserve a rich intervention description when the question specifies
   magnitude, replacement type, spatial arrangement, direction, timing, or
   location of a land-use change; usually keep this to 10-60 words, but never
   omit user-supplied detail or pad a simple intervention;
4. extract explicit environmental/context statements as rich Facets;
5. record the user's location text or supplied spatial identifier without
   inferring environmental properties;
6. for every extracted endpoint and explicit Context Facet, return an exact
   supporting_text_span copied from the user question;
7. detect whether a global/non-location-conditioned synthesis is requested.

Facet domains:
- spatial_configuration
- land_surface
- hydrology
- atmosphere
- climate
- substrate_terrain
- other

Rules:
- global_requested is true only when the user explicitly requests a global,
  corpus-wide, or non-location-conditioned synthesis;
- a question about a stated environment is not global_requested;
- environmental phrases introduced by words such as "in", "under", "during",
  or "with" must be represented as explicit Context Facets when they describe
  climate, season, land surface, hydrology, atmosphere, terrain, or spatial
  configuration;
- recording a location as spatial_reference does not replace extraction of the
  other explicit environmental phrases in the same question;
- do not also emit a pure place name as a spatial_configuration Facet when the
  same text is already recorded as spatial_reference;
- no confidence scores;
- no invented mechanisms;
- no invented coordinates;
- no scientific answer yet;
- use compact endpoint concepts (usually 1-8 words) and compact
  directional/categorical states (usually 1-5 words);
- words that only describe the question relation, such as "effects",
  "reported", "affect", or "impact", are not scientific endpoint states;
  leave a broad outcome target unspecified rather than inventing one State;
- for a "where" question, keep patch-edge or directional wording as spatial
  query information; do not turn "location relative to ..." into a State;
- a comparison such as "drier or wetter" contains alternatives, not one
  endpoint State; preserve the full comparison in intervention_description
  and leave both endpoints unspecified so both sides can be retrieved;
- use short Facet notions (usually 2-8 words) and evidence-faithful Facet
  descriptions; 20-60 words is a soft target for rich Facets, never a reason
  to invent or pad information;
- preserve important intervention detail in intervention_description;
- return schema-valid JSON only.

Example: for "In a snow-covered boreal forest during winter, could
deforestation decrease surface temperature?", extract the stated snow cover,
boreal forest setting, and winter period as Facets; use deforestation as the
source, surface temperature decrease as the target, and set global_requested
to false. Do not add any unstated property of boreal forests.

USER

{user_question}
```
</details>

<details>
<summary><code>final_synthesis.txt</code> (verbatim)</summary>

```text
SYSTEM

Answer using ONLY the supplied Query Context, selected graph Claims, paths, and SourceBlocks. Every substantive scientific statement cites supporting Claim IDs. Every query-area fact cites Query Facet IDs. Combine Claims only along supplied paths. Do not invent mechanisms, steps, locations, magnitudes, directions, or distances. Distinguish direct findings, transfer inference, query-area derived facts, uncertainty, mismatch, missing information, and contradictions. Scores are retrieval scores, not confidence. Spatial translation is allowed only when the supplied package says so. Return schema-valid JSON only.

USER QUESTION
{question}

QUERY SPEC
{query_spec}

QUERY CONTEXT
{query_context}

SELECTED PATHS AND CLAIMS
{selected_paths}

CONTRADICTORY / ALTERNATIVE EVIDENCE
{contradictions}

SOURCE BLOCKS
{source_blocks}
```
</details>

## Query LLM envelopes

Query parsing and synthesis use the same envelope structure as indexing. Parse records are saved under `parse/`, and synthesis records under `synthesis/`. Each envelope records the prompt-stage version, model, thinking level, retry number, elapsed time, raw response, schema result, and selected input Block IDs.

## Step-by-step query pipeline

### Step 1: Load the graph corpus

Entry point: `climatekg.graph.Neo4jHttp.read_corpus`.

The query command reads Papers and their graph objects back from Neo4j. This verifies that the answer is using the graph, not bypassing it by reading extraction files directly.

### Step 2: Parse the question

Entry point: `climatekg.query.parse_query`.

The local generative model returns a structured Query object with:

- mode: forward, backward, A-to-B, or global;
- source endpoint when stated;
- target endpoint when stated;
- intervention description;
- sparse Context Facets copied from the user's words;
- spatial information when present.

Python validates exact text spans and schema references. Invalid items are discarded individually. A dedicated repair request is used when explicit Context details were omitted. The parser does not infer environmental facts from a place name.

### Step 3: Determine query mode

- **Forward:** starting from an intervention or source State, find reported outcomes.
- **Backward:** starting from a desired outcome, find reported causes or interventions.
- **A-to-B:** test how one stated State could connect to another.
- **Global:** summarize across the indexed literature without a Context gate.

Global mode is used only when the wording explicitly asks for corpus-wide or global evidence.

### Step 4: Embed the query

Entry point: `climatekg.query.embed_query`.

The embedding model creates vectors for the whole Claim-like question, the query Context, the intervention, and each query Facet. Runtime vectors are not copied into the synthesis prompt because they consume tokens without helping the language model.

### Step 5: Retrieve candidate Contexts

Entry point: `climatekg.query.retrieve_contexts`.

The Context vector supplies a coarse candidate set. The pipeline reconstructs each candidate's effective Context, including inherited parent Facets, before detailed comparison.

### Step 6: Compare query and indexed Facets

Entry points: `facet_pair` and `context_similarity`.

Facet comparisons are grouped by domain. For every query Facet, the best compatible indexed Facet is found. The report keeps separate values for:

- semantic similarity;
- coverage of the stated query conditions;
- intervention similarity;
- spatial relevance;
- mechanism relevance.

Missing information is not treated as a contradiction. Coverage records what was actually matched. Retrieval scores rank evidence; they are not probabilities that a Claim is scientifically true.

### Step 7: Map query endpoints to canonical States

Entry point: `climatekg.query.map_endpoint`.

Exact canonical aliases are tried first. Embedding candidates are considered next. State direction must be compatible. An unspecified query direction can match any indexed direction; an explicit incompatible direction cannot.

### Step 8: Generate and rank Claim candidates

Entry point: `climatekg.query.rank_claims`.

Candidates are collected from five channels:

- Claims scoped to retained Contexts;
- source endpoint matches;
- target endpoint matches;
- semantic Claim retrieval;
- Transition retrieval.

Each report records the channels that produced the Claim. Ranking combines semantic relevance, endpoint relevance, Context applicability, conditioning-Facet match, and Transition similarity according to the query specification.

`A_claim` is an applicability ranking signal. A null value means applicability is unknown, not that the Context mismatches and not that the Claim is false.

### Step 9: Apply the Context gate

Context and conditioning checks are computed before mechanism paths are built. Claims from incompatible Contexts must not be joined into one path. Context-unknown evidence may remain visible as an alternative, but its unknown status must be preserved.

For validation, a context-dependent query must now contain at least one final path with a non-null `A_path`. This prevents a fluent answer from passing when every path lacks an applicability assessment.

### Step 10: Search mechanism paths

Entry point: `climatekg.query.search_paths`.

The search follows Claim source and target States. It uses the requested query mode, prevents invalid cycles, limits path length, and checks Context coherence between adjacent Claims. The path report includes:

- Claim IDs in order;
- retrieval score `R_path`;
- applicability `A_path`;
- cross-edge coherence `C_path`;
- `context_unknown` flag;
- `coherence_unknown` flag.

The system also retrieves contradictory or alternative evidence rather than forcing one direction into a single conclusion.

### Step 11: Handle spatial evidence

Entry points: `spatial_report` and `parse_spatial_scales`.

Spatial relations remain distinct: local advection, patch-edge effects, distance decay, windward/leeward effects, moisture recycling, and remote teleconnections are not collapsed into generic downwind wording.

A literature relation is translated to a real map direction only when both local geometry or environmental data and transferable literature evidence are present. Otherwise, the answer states the literature relation without inventing a cardinal direction.

### Step 12: Select exact evidence

Entry point: `climatekg.query.select_source_blocks`.

For selected path Claims and alternatives, the pipeline retrieves their directly linked SourceBlocks. Block embeddings only help order directly supporting evidence. They cannot introduce a new Claim or replace the stored support links.

### Step 13: Trim the evidence package

Entry point: `climatekg.query.trim_evidence_package`.

Python applies the final token budget while preserving the most useful paths, alternatives, Facets, and SourceBlocks. It records any trimming warning. Query embedding arrays are removed before counting this budget.

### Step 14: Synthesize the answer

Entry point: `climatekg.query.synthesize`.

The local `qwen3.6:27b` model receives only the structured query, selected paths, alternatives, Claims, Context reports, and SourceBlocks. It must return structured answer items with supporting Claim IDs and query-Facet IDs.

The model is instructed to:

- separate causal and associative findings;
- preserve conditions and uncertainty;
- distinguish context-known from context-unknown evidence;
- mention alternatives and contradictions;
- avoid unsupported mechanisms;
- avoid translating spatial relations when local inputs are missing.

### Step 15: Validate grounding and render references

Python checks every substantive synthesis item. A cited Claim must exist in the selected evidence package, and its supporting SourceBlocks must be present. Unsupported items are removed and recorded as `UNSUPPORTED_SYNTHESIS_ITEM`. If no valid substantive item remains, final grounding fails visibly.

The rendered answer cites the Paper and Claim and is backed by exact SourceBlock provenance in `query_report.json`.

## Query artifacts and review order

Validation output is stored at:

```text
climatekg/runtime/outputs/query_validation/<run-id>/
  suite_progress.json
  suite_report.json
  suite_report.md
  queries/<query-id>/
    stage_events.jsonl
    query_spec.json
    query_report.json
    answer.md
    llm/
```

Review one query in this order:

1. Open `answer.md` for the human-readable result.
2. Open `stage_events.jsonl` to see the exact stage sequence and counts.
3. Check `query_spec.json` for parsed endpoints and explicit query Facets.
4. In `query_report.json`, check retained Contexts and their coverage.
5. Check State seeds and warnings.
6. Check top Claims, candidate channels, `A_claim`, and rejection reasons.
7. Check paths, `A_path`, `C_path`, and unknown flags.
8. Check selected SourceBlocks and page information.
9. Check synthesis items and provenance.
10. Open the saved LLM envelopes when a structured extraction or synthesis decision needs review.

For `QCTX001`, the corrected focused run is:

```text
climatekg/runtime/outputs/query_validation/query-suite-20260824T145454Z/
```

It parsed three query Facets, mapped the target to `state::surface_air_temperature::increase`, ranked the two applicable tropical deforestation Claims first, found two direct context-known paths with `A_path = 0.4864`, retained 13 evidence blocks, and produced five grounded answer items. Two unsupported synthesis items were discarded and logged.

## Three real query traces, continued

Each trace below starts with the actual question and follows the saved stage events through parsing, enrichment, embeddings, Context comparison, State mapping, Claim gating, path search, evidence selection, synthesis, and citation rendering. Decimal scores are shown as ranking diagnostics, not probabilities of scientific truth.

### Trace A continued: `QCTX001`, humid tropical deforestation

**Question and parsed output.**

```text
In a humid tropical forest during daytime, could deforestation increase surface temperature?
```

```json
{
  "query_id": "QCTX001",
  "mode": "a_to_b",
  "context": {
    "spatial_support": null,
    "facets": [
      {"id": "QCTX001_F001", "domain": "climate", "notion": "humid tropical", "supporting_text_span": "humid tropical"},
      {"id": "QCTX001_F002", "domain": "land_surface", "notion": "forest", "supporting_text_span": "forest"},
      {"id": "QCTX001_F003", "domain": "atmosphere", "notion": "daytime", "supporting_text_span": "during daytime"}
    ]
  },
  "source": {"concept": "deforestation", "state": ""},
  "target": {"concept": "surface temperature", "state": "increase"},
  "intervention_description": "deforestation"
}
```

The parse recorded `QUERY_CONTEXT_FACET_REPAIR` because the repair pass recovered explicit Context detail, and `QUERY_UNSUPPORTED_SOURCE_STATE_CLEARED` because the empty/unsupported source direction was cleared instead of invented.

**Embeddings, similarity, gating, and paths.** All three query embeddings had 2,048 dimensions. Context retrieval returned 30 candidates with full three-Facet coverage for its leading records. Endpoint mapping included `state::deforestation::occurrence` as a source seed and exactly mapped the target to `state::surface_air_temperature::increase`.

```json
{
  "top_claims": [
    {
      "claim_id": "P000002_CL041",
      "channels": ["claim_ann", "context_scope", "source_endpoint", "target_endpoint"],
      "R_claim": 0.6867838213,
      "A_claim": 0.4864336400,
      "context_coverage": 1.0
    },
    {
      "claim_id": "P000002_CL018",
      "channels": ["claim_ann", "context_scope", "source_endpoint", "target_endpoint"],
      "R_claim": 0.6795722108,
      "A_claim": 0.4864336400,
      "context_coverage": 1.0
    }
  ],
  "direct_context_known_paths": [
    {"claim_ids": ["P000002_CL041"], "A_path": 0.4864336400, "C_path": 1.0, "context_unknown": false},
    {"claim_ids": ["P000002_CL018"], "A_path": 0.4864336400, "C_path": 1.0, "context_unknown": false}
  ]
}
```

The search also retained three mechanism paths marked `context_unknown: true`; that flag remains visible rather than being treated as a match. Six supporting or opposite alternatives were collected, including boreal cooling Claims `P000002_CL042` and `P000002_CL019`. Evidence selection found 14 Blocks and deterministic trimming retained 13.

**Grounded synthesis and rendered answer.** The LLM returned seven candidate synthesis items. Grounding validation discarded two unsupported items and retained five items with nine Claim-provenance entries. The rendered result begins:

```text
Yes, deforestation could increase surface temperature in a humid tropical
forest. [Decreased cloud cover partially offsets the cooling effects of
surface albedo change due to deforestation (2024), p. 3,
Claims P000002_CL041 and P000002_CL018]

Lower evapotranspiration diminishes latent cooling, leading to surface
warming. [same paper, pp. 1,3, Claims P000002_CL017,
P000002_CL038 and P000002_CL004]

In boreal regions, deforestation leads to surface cooling because increased
surface albedo becomes the predominant factor over diminished
evapotranspiration. [same paper, p. 3, Claims P000002_CL042 and
P000002_CL019]
```

The full saved report is [QCTX001 query_report.json](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T145454Z/queries/QCTX001/query_report.json), and the exact rendered response is [answer.md](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T145454Z/queries/QCTX001/answer.md). This run recorded 317 State nodes; later alias consolidation reduced the current graph to 314 without changing the Claims used here.

### Trace B continued: `QCTX004`, drier versus wetter soil patches

**Question and parsed output.**

```text
In an afternoon dry-soil convective regime, is convective rainfall reported
as more likely over drier or wetter soil patches?
```

```json
{
  "query_id": "QCTX004",
  "mode": "global",
  "context": {
    "facets": [
      {"id": "QCTX004_F001", "domain": "atmosphere", "notion": "convective regime"},
      {"id": "QCTX004_F002", "domain": "land_surface", "notion": "soil moisture condition"},
      {"id": "QCTX004_F003", "domain": "atmosphere", "notion": "time of day"}
    ]
  },
  "source": null,
  "target": null,
  "intervention_description": "comparison of drier versus wetter soil patches"
}
```

The comparison does not invent a single endpoint. `QUERY_COMPARATIVE_ENDPOINTS_DISCARDED` records that deterministic correction. The `global` mode describes the endpoint-free comparison search; it does not remove the three explicit Context Facets or disable Context gating.

**Similarity, Claim gating, and alternatives.** The leading Context was `P000006_C006` with overall similarity `0.6217319457` and coverage `1.0`; `P000006_C007` followed at `0.6015907498`, also with coverage `1.0`. No endpoint State seeds were created because both sides of the comparison had to remain available.

```json
{
  "ranked_claims": [
    {"claim_id": "P000006_CL012", "R_claim": 0.6229705088, "A_claim": 0.6263636851, "context_coverage": 1.0},
    {"claim_id": "P000006_CL010", "R_claim": 0.6226703606, "A_claim": 0.6080318232, "context_coverage": 1.0},
    {"claim_id": "P000006_CL007", "R_claim": 0.5907863000, "A_claim": 0.5559819931, "context_coverage": 1.0},
    {"claim_id": "P000006_CL001", "R_claim": 0.5715049063, "A_claim": 0.5124069524, "context_coverage": 1.0}
  ],
  "top_path": {
    "claim_ids": ["P000006_CL012"],
    "R_path": 0.3902061036,
    "A_path": 0.6263636851,
    "C_path": 1.0,
    "context_unknown": false
  },
  "alternative_claim_ids": ["P000006_CL003", "P000006_CL001", "P000006_CL008"]
}
```

The path search produced 20 candidates and trimming kept 8 paths, 3 alternatives, and 20 exact SourceBlocks. This preserved both the observational dry-soil result and the contrasting model wet-soil result.

**Grounded synthesis and rendered answer.** Four synthesis items passed grounding and cited six Claims. One unsupported candidate item was visibly rejected. The saved answer reports:

```text
In an afternoon dry-soil convective regime, observational analysis reports
that convective rainfall is more likely over drier soil patches
[P000006_CL007]. This preference is strongest under the driest mean soil
moisture conditions [P000006_CL010]. The result is consistent with a negative
soil-moisture feedback [P000006_CL012].

The negative feedback signal loses statistical significance at the 95% level
when mean soil moisture exceeds 0.20 cubic metres per cubic metre
[P000006_CL011]. Climate models often show the contrasting preference for
wetter soils because of overly sensitive daytime convective triggering
[P000006_CL001].
```

The complete result is [QCTX004 query_report.json](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T155834Z/queries/QCTX004/query_report.json), with the unshortened cited prose in [answer.md](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T155834Z/queries/QCTX004/answer.md).

### Trace C continued: `QCTX006`, Sahel albedo and precipitation

**Question and parsed output.**

```text
In the Sahel north of 18 degrees north during summer, could increasing
surface albedo from 0.14 to 0.35 reduce precipitation?
```

```json
{
  "query_id": "QCTX006",
  "mode": "a_to_b",
  "context": {
    "spatial_support": {
      "kind": "region",
      "name": "Sahel north of 18 degrees north",
      "geometry": null,
      "resolution": "unresolved"
    },
    "facets": [
      {"id": "QCTX006_F001", "domain": "spatial_configuration", "notion": "region"},
      {"id": "QCTX006_F002", "domain": "climate", "notion": "season"},
      {"id": "QCTX006_F003", "domain": "land_surface", "notion": "surface_albedo_initial"},
      {"id": "QCTX006_F004", "domain": "land_surface", "notion": "surface_albedo_final"}
    ]
  },
  "source": {"concept": "surface albedo", "state": ""},
  "target": {"concept": "precipitation", "state": "reduce"},
  "intervention_description": "increasing surface albedo from 0.14 to 0.35"
}
```

Because the named region had no supplied geometry, enrichment logged `QUERY_ENRICHMENT_SKIPPED_UNRESOLVED_SPATIAL_SUPPORT`; it did not invent coordinates. The explicit region still remained a query Facet and was compared against reported literature geometry.

**Similarity, gating, and direct paths.** Four leading `P000015` Contexts each scored `0.5815389227` with coverage `1.0`. The target mapped to `state::precipitation::decrease`; the source candidate set included `state::surface_albedo::increase`.

```json
{
  "claims": [
    {
      "claim_id": "P000015_CL009",
      "channels": ["claim_ann", "context_scope", "source_endpoint", "target_endpoint", "transition_ann"],
      "R_claim": 0.7360997527,
      "A_claim": 0.5784873829,
      "context_coverage": 1.0
    },
    {
      "claim_id": "P000015_CL004",
      "channels": ["claim_ann", "context_scope", "source_endpoint", "target_endpoint", "transition_ann"],
      "R_claim": 0.7286311349,
      "A_claim": 0.5647623439,
      "context_coverage": 1.0
    }
  ],
  "paths": [
    {"claim_ids": ["P000015_CL009"], "R_path": 0.4258244195, "A_path": 0.5784873829, "C_path": 1.0},
    {"claim_ids": ["P000015_CL004"], "R_path": 0.4115034276, "A_path": 0.5647623439, "C_path": 1.0}
  ]
}
```

Evidence selection found the two Claims and conditioning Facets `P000015_F018`, `P000015_F031`, and `P000015_F034`. Trimming retained five SourceBlocks. No grounding warning was produced.

**Grounded synthesis and exact answer.** Three items passed validation with two Claim-provenance records:

```text
Yes [Check for updates (1975), pp. 1,9, Claim P000015_CL009;
Check for updates (1975), p. 9, Claim P000015_CL004]

The supplied evidence explicitly covers the Sahel/north of 18 degrees N
region [QCTX006_F001] and does not require spatial translation. [same Claims]

The precipitation reduction of approximately 40% was observed during a
six-week summer simulation period (late June to mid-August) [QCTX006_F002]
following an albedo increase from 0.14 [QCTX006_F003] to 0.35
[QCTX006_F004]. [same Claims]
```

The full trace is [QCTX006 query_report.json](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T153831Z/queries/QCTX006/query_report.json), and the rendered response is [answer.md](E:/Atharv/lulc_suggestor_poc/19_aug_final/climatekg/runtime/outputs/query_validation/query-suite-20260824T153831Z/queries/QCTX006/answer.md).

For all three examples, `stage_events.jsonl` beside the report is the simplest start-to-finish execution log. It records timestamps, corpus counts, dimensions, candidate counts, top IDs and scores, evidence counts, synthesis counts, warnings, and final artifact paths. The LLM `attempt*.json` and `envelope.json` files in each query folder preserve the actual parser and synthesis requests and responses.

## Validation suite

The configured suite contains ten questions:

- three generic corpus-wide questions;
- six Context-dependent questions;
- one patch-edge spatial question.

They cover irrigation, deforestation, boundary-layer changes, tropical and boreal sign reversal, soil-moisture regimes, wind-turbine mixing, Sahel albedo change, and patch-edge convection.

The suite checks query mode, explicit Context extraction, State mapping, Claim candidates, path construction, ranked-Claim membership, selected evidence, structured grounding, answer presence, and grounding warnings. Context cases also require an enabled gate and at least one path with known applicability.

Run it with:

```powershell
.\scripts\run_graph_query_validation.ps1
```

The script starts Neo4j, waits for a real authenticated Cypher transaction, ingests and verifies the ten papers, runs every query, and prints the output directory.

## Visible failure behavior

The pipeline fails or warns explicitly for important problems:

| Signal | Meaning |
|---|---|
| `FAILED_PARSE` | Nemotron parsing or page-coverage validation failed. No parser fallback is used. |
| `NEEDS_REVIEW` | A later indexing stage produced an object that could not be safely accepted. |
| `QUERY_CONTEXT_FACET_REPAIR` | The first query parse omitted explicit conditions; a required-Facet repair request was used. |
| `QUERY_UNSUPPORTED_*_STATE_CLEARED` | A query endpoint state was not supported by the user's wording and was cleared. |
| `UNSUPPORTED_SYNTHESIS_ITEM` | A generated answer statement lacked valid selected support and was removed. |
| `FINAL_GROUNDING_VALIDATION_FAILED` | No safe grounded final answer could be rendered. |
| `context_unknown: true` | The path may be relevant, but its environmental transfer could not be assessed. |
| `coherence_unknown: true` | Adjacent Claims did not provide enough Context information for a complete coherence check. |

Retries are bounded. Malformed structured model output is validated, repaired according to the specified procedure, or saved as a visible failure. The system does not silently accept malformed scientific objects.

## Reproducibility checklist

To reproduce an answer, retain:

- the source PDF hash;
- parser and model versions;
- prompt versions;
- `final_paper.json` for every indexed paper;
- alias registry and pipeline configuration;
- Neo4j version;
- query text and query ID;
- query report and stage events;
- all local-model request and response envelopes;
- final answer and provenance map.

The main deterministic tests run with:

```powershell
python -m pytest -q -p no:cacheprovider
```

At the time this document was updated, all 28 deterministic tests passed. All ten query cases also have a passing graph-backed final run. `FINAL_QUERY_VALIDATION_SUMMARY.md` is the authoritative index because failure-driven focused reruns were preserved in separate directories.

## Interpretation rules

1. A high retrieval score means an item ranks well for the question. It does not mean the Claim is certainly true.
2. Missing Context data is different from a measured mismatch.
3. An associative Claim must not be rewritten as causal.
4. Cited background must not be presented as the indexed paper's own finding.
5. Contradictions and sign changes are scientific results, not extraction errors.
6. A mechanism path is valid only when its supporting Claims can coexist under compatible Contexts.
7. A local spatial recommendation needs local geometry or environmental inputs as well as transferable literature evidence.
8. Every substantive answer statement must be traceable to selected Claims and exact SourceBlocks.

## Implementation map

| File | Responsibility |
|---|---|
| `climatekg/models.py` | Central scientific and final-paper schemas. |
| `climatekg/extraction_models.py` | Structured local-model output schemas. |
| `climatekg/pdf.py` | Registration, Nemotron-only parse orchestration, cleaning, and SourceBlocks. |
| `climatekg/extract.py` | Mapping, Facet extraction, and Claim extraction. |
| `climatekg/reconcile.py` | Late Context reconciliation. |
| `climatekg/consolidate.py` | Exact cleanup and bounded scientific consolidation. |
| `climatekg/canonicalize.py` | State concept and direction normalization. |
| `climatekg/state_maintenance.py` | Audited State recanonicalization after an alias correction. |
| `climatekg/embeddings.py` | Text construction and embedding generation. |
| `climatekg/graph.py` | Neo4j schema, ingestion, verification, and graph read-back. |
| `climatekg/query.py` | Query parsing, ranking, gating, paths, evidence, and synthesis. |
| `climatekg/query_validation.py` | Ten-query runner, checks, progress, and reports. |
| `climatekg/cli.py` | Command-line entry points. |
| `config/pipeline.yaml` | Models, budgets, paths, and indexing parameters. |
| `config/query_pipeline.yaml` | Query ranking, search, and evidence parameters. |
| `config/state_aliases.yaml` | Verified concept and direction identities. |
| `config/validation_queries.json` | Generic, Context-dependent, and spatial test questions. |
| `prompts/` | Versioned extraction and synthesis instructions. |

The authoritative behavior remains defined by `land_atmosphere_kg_indexing_pipeline.md` and `land_atmosphere_kg_query_pipeline.md`. This walkthrough explains the implemented execution in simpler language; it does not replace those specifications.
