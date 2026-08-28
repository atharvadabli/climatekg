# Review of the Existing `doc.tex`

## Source and status

- Reviewed source: `E:\Atharv\lulc_suggestor_poc\19_aug_claude\doc.tex`
- Reviewed on: 2026-08-24
- Size: 597 lines, 53,585 characters
- Current form: a detailed methods and research-plan manuscript, not a results-complete workshop paper
- Original file was not edited.

The document is useful source material. Its scientific motivation, provenance argument, and explanation of context-conditioned retrieval align with the implemented system. It should not be submitted in its current form because the Results and Discussion sections are placeholders, the comparison is described in the future tense, and the custom LaTeX layout is not the official submission template.

## Recommended positioning

Use the existing document as a source for a new, much shorter paper centered on one testable thesis:

> Topical relevance is insufficient for land-atmosphere evidence synthesis because the applicability and even direction of an effect can depend on hydroclimate, season, atmospheric regime, spatial configuration, and intervention geometry. ClimateKG gates claims by supporting environmental context before constructing mechanism paths and retains exact evidence provenance.

The current title is accurate but too long and gives unimplemented WRF work undue prominence. Prefer:

**ClimateKG: Context-Gated Scientific GraphRAG for Auditable Land-Atmosphere Evidence Synthesis**

Treat raster generation and WRF as an impact pathway or future validation step. They should occupy a few sentences, not two main sections.

## What to retain

- The core motivation in the abstract and Introduction: land-atmosphere responses are conditional and may reverse by regime.
- The concrete scientific examples of hydroclimate, background flow, patch scale, advection, and moisture recycling, after every citation is independently checked.
- The distinction among `Paper`, `SourceBlock`, `Context`, `Facet`, `Transition`, `Claim`, and canonical `State`.
- The principle that a Claim retains exact supporting SourceBlocks and remains scoped to its supporting Context or Transition.
- The directional MaxSim equation, explicit coverage reporting, pre-path Claim gating, bottleneck path applicability, and separation of relevance signals.
- The warning that missing context is different from contextual mismatch.
- The relation-specific spatial reasoning families.
- The traceability chain from an answer statement to Claims, Papers, and SourceBlocks.

## Required corrections

### 1. Update the schema vocabulary

The manuscript uses the older term `ContextVariable` throughout. The authoritative specifications and implementation use `Facet` with:

- controlled `Facet.domain`;
- open `Facet.notion` and `Facet.description`;
- `Claim.conditioning_facet_ids` for only the materially conditioning Facets.

Replace `ContextVariable` with `Facet`, `name` with `notion`, `conditioning_context_variable_ids` with `conditioning_facet_ids`, and `HAS_CONTEXT_VARIABLE` with the specified Facet relationship. Do this as a semantic edit, not a blind global substitution, because some surrounding sentences and equations also need adjustment.

### 2. Match the implemented configuration

State exact model identifiers where relevant:

- parser: `nvidia/NVIDIA-Nemotron-Parse-v1.2` only;
- extraction model: `qwen3.6:27b` through Ollama;
- embedding model: `qwen3-embedding:4b`, 2,048 dimensions.

Avoid describing optional or planned components as active pipeline stages unless the frozen experiment configuration actually uses them.

### 3. Replace proposal language with measured evidence

The current Results section explicitly says results "will" be reported. Before a Papers-track submission, replace all future-tense evaluation claims with generated tables and saved artifact references. At minimum report:

- corpus processing: 10 successful papers and 5 visible `NEEDS_REVIEW` failures;
- object counts: 2,184 SourceBlocks, 101 Contexts, 437 Facets, 51 Transitions, 213 Claims, and 322 States;
- benchmark definition and annotation procedure;
- baseline and ablation results on the same queries;
- citation/source accuracy;
- context applicability and incompatible-evidence rejection;
- mechanism-path validity;
- failure analysis.

Indexing counts demonstrate pipeline execution, not retrieval quality. They must not be presented as evidence that ClimateKG outperforms a baseline.

### 4. Narrow the baseline claim

The manuscript promises Plain RAG, Microsoft GraphRAG, and the custom system. Keep Microsoft GraphRAG only if it can be installed, configured, run on the same ten PDFs, and evaluated on the identical frozen benchmark before results freeze. Otherwise use feasible, informative comparisons:

- lexical/BM25 passage retrieval;
- dense passage retrieval;
- ungated graph retrieval;
- full context-gated ClimateKG.

This comparison isolates the actual contribution more directly. Never imply the Microsoft GraphRAG experiment occurred if it did not.

### 5. Remove unsupported completion language

The abstract says "we developed" a three-system comparison, while the Results section is empty and the Neo4j query round trip is not yet complete. Until that is fixed, distinguish carefully among:

- implemented and unit-tested indexing/query logic;
- successfully generated pilot indexing artifacts;
- blocked Neo4j integration;
- planned benchmark comparisons;
- future WRF evaluation.

### 6. Use the official anonymous template

The source uses `article`, custom geometry, custom definition boxes, and a named affiliation. Move content into the official four-page, double-blind workshop template. Remove `ICTD, IIT Delhi` and identifying PDF metadata from the review version. Definition boxes are too expensive for a four-page paper; represent the schema once in the architecture figure.

## Four-page content map

### Page 1: problem and contribution

- Short context-dependence motivation with one sign-reversal example.
- Failure mode: semantically relevant evidence can be environmentally inapplicable.
- Three contributions: provenance-preserving scientific representation, context gating before path construction, and an auditable benchmark/evaluation.
- Compact architecture figure.

### Page 2: method

- One-line indexing flow.
- Schema and provenance invariants.
- Facet similarity equation plus coverage.
- Claim gating and mechanism-path scoring.
- One sentence on relation-specific spatial handling.

### Page 3: evaluation and results

- Corpus and benchmark protocol.
- Main table comparing BM25, dense, ungated graph, and full system.
- One ablation table or compact plot.
- One traceable success/failure example.

### Page 4: interpretation and climate relevance

- What gating changes and where it fails.
- Limitations: small corpus, annotation scale, extraction errors, local-model dependence, incomplete spatial enrichment, and no demonstrated management outcome.
- Pathway to climate impact: evidence triage and hypothesis generation before expensive regional modelling.
- Conclusion.

## Material to compress or remove

- Compress the 88-line Definitions section into one figure and a short paragraph.
- Reduce the broad scientific-basis review to only the facts needed to motivate context gating.
- Remove the standalone raster-scenario and WRF sections; retain a short impact-pathway paragraph.
- Remove implementation narration that is already evident from the pipeline diagram.
- Remove all placeholder Results/Discussion prose.
- Avoid the claim that the system proposes reliable local interventions. It retrieves transferable evidence candidates subject to explicit gaps and constraints.

## Immediate manuscript sequence

1. Finish the Neo4j round trip and save one end-to-end grounded query report.
2. Freeze 18-24 representative queries and gold judgments.
3. Run the feasible baselines and gating ablations on exactly that benchmark.
4. Generate all reported values from saved JSON with deterministic scripts.
5. Create the official anonymous four-page source using measured results only.
6. Independently verify citations, workshop requirements, and final wording against the official call before submission.

## Track decision

The existing `doc.tex` is closer to a strong Proposal-track foundation than a Papers-track submission because it presents a complete methodology but no retrieval results. It becomes a credible Papers-track manuscript only after the end-to-end query path, common benchmark, quantitative comparisons, and grounded-answer audit are complete.
