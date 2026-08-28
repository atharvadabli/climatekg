# Climate Change AI at NeurIPS 2026: Submission Strategy for ClimateKG

> Existing manuscript source assessed separately in [`DOC_TEX_SUBMISSION_REVIEW.md`](DOC_TEX_SUBMISSION_REVIEW.md). The original `E:\Atharv\lulc_suggestor_poc\19_aug_claude\doc.tex` remains unchanged.

> Anonymous paper source: [`../paper/climatekg_ccai2026.tex`](../paper/climatekg_ccai2026.tex). Acceptance-critical placeholders and experiment gates are tracked in [`../paper/SUBMISSION_GAPS.md`](../paper/SUBMISSION_GAPS.md).

## Purpose and compliance note

This is an internal research and execution plan, not submission-ready manuscript text. The authors must independently read the [official workshop page](https://www.climatechange.ai/events/neurips2026), verify every requirement, and write and approve the final paper. Do not copy this document verbatim into the submission.

The workshop page includes a specific restriction concerning sharing CCAI website material with LLMs during paper preparation. The final authors are responsible for compliance. The NeurIPS author policy also makes authors responsible for the correctness, originality, references, figures, and disclosures in their submission. See the [NeurIPS 2026 handbook](https://neurips.cc/Conferences/2026/MainTrackHandbook).

## Immediate submission facts

- Target: Climate Change AI workshop at NeurIPS 2026.
- Recommended track: **Papers**, conditional on completing the query evaluation below within 24 hours.
- Fallback track: **Proposal** if the graph/query evaluation cannot be completed reliably. Do not submit an under-evaluated system as a finished paper.
- Workshop contribution deadline: **August 29, 2026, 23:59 Anywhere on Earth**.
- Equivalent deadline in India: approximately **August 30, 2026, 17:29 IST**. Verify this independently.
- Internal deadline: **August 28, 2026, 20:00 IST**, leaving time for OpenReview and formatting failures.
- Paper limit: four main-text pages for the Papers track; references are outside that limit. Verify the current template rules on the official page.
- Review is double-blind. The PDF, supplementary material, code links, filenames, repository history, and acknowledgements must not reveal author identities.
- Confirm that every author has an active, complete OpenReview profile immediately. New account moderation can be slow.
- Check whether any author triggers the reciprocal-reviewer requirement.
- This is a non-archival workshop, so the work can later be expanded for an archival venue.

## Recommended positioning

### Working title

**ClimateKG: Context-Gated Scientific GraphRAG for Auditable Land-Atmosphere Evidence Synthesis**

Alternatives:

- **Preventing Context-Incompatible Reasoning in Land-Atmosphere GraphRAG**
- **From Literature Claims to Context-Coherent Climate Mechanisms**
- **A Provenance-Preserving Knowledge Graph for Context-Dependent Land-Climate Evidence**

Do not use “first” or “novel” in the title or abstract until the related-work search supports it.

### One-sentence research claim

ClimateKG represents the environmental and experimental conditions of land-atmosphere findings explicitly and gates scientific claims by context before constructing mechanism paths, reducing unsupported or environmentally incompatible evidence composition while retaining exact source provenance.

### The problem to lead with

Land-use and land-cover effects on heat, moisture, clouds, circulation, and precipitation are not transferable from one study to another based only on matching intervention and outcome terms. Effects can reverse with season, stability, hydroclimate, spatial scale, baseline land cover, or local geometry. Conventional search and flat retrieval can return relevant-looking evidence without testing whether its supporting environmental regime applies to the question.

The paper should therefore focus on this failure mode:

> **Scientific retrieval can be topically relevant yet environmentally inapplicable, and graph path search can compound the error by joining claims from incompatible contexts.**

This is sharper and more defensible than positioning the work as a general climate knowledge graph or a land-management recommendation system.

### Method contribution

Frame ClimateKG as a hybrid, domain-constrained ML system with five candidate contributions:

1. A scientific representation separating `Context`, open-vocabulary `Facet`, `Transition`, atomic `Claim`, canonical `State`, and exact `SourceBlock` provenance.
2. Context and Facet applicability scoring that distinguishes missing query information from actual contextual mismatch.
3. Claim gating before graph path construction, preventing mechanism chains assembled from environmentally incompatible supporting studies.
4. Fail-closed extraction and reconciliation that preserves sign reversals, null findings, contradictory regimes, and malformed-output audit trails.
5. A resource-conscious hybrid pipeline: deterministic algorithms for validation/ranking and local language models only for semantic extraction or synthesis.

These are **candidate contribution claims**, not established novelty claims. Confirm them against related work before submission.

### Climate pathway to impact

The credible pathway is decision support for expert evidence assessment, not automated intervention recommendation:

1. Scientific papers contain distributed, conditional evidence about land-climate mechanisms.
2. ClimateKG makes the evidence and its applicability conditions searchable and auditable.
3. Researchers, adaptation analysts, forestry/agriculture specialists, and land-use planners can identify transferable mechanisms, contradictions, and missing local information faster.
4. Experts combine that evidence with local observations, numerical models, stakeholder knowledge, and policy constraints.
5. Better evidence triage can reduce inappropriate transfer of findings between regions and improve the design of detailed assessment or simulation.

Do not claim that the system directly proves an intervention will work, predicts climate, replaces a regional model, or produces deployment-ready spatial recommendations.

## What is already verified

As of August 24, 2026:

- 10 representative PDFs completed the indexing pipeline through validated `FinalPaper` artifacts.
- 5 additional papers were retained as `NEEDS_REVIEW`; malformed scientific objects were not silently accepted.
- Successful artifacts contain, in aggregate:
  - 2,184 SourceBlocks;
  - 101 Contexts;
  - 437 Facets;
  - 51 Transitions;
  - 213 Claims;
  - 322 canonical States.
- Every successful `FinalPaper` passes deterministic reference validation.
- 17 deterministic tests pass.
- Parsing used NVIDIA Nemotron Parse v1.2 only.
- Intermediate parse, extraction, reconciliation, consolidation, and failure artifacts are preserved under `climatekg/runtime`.

These numbers demonstrate implementation scale and traceability. They do **not** yet demonstrate retrieval quality, scientific correctness, or answer quality.

Primary audit report:

`climatekg/runtime/output/validation/e2e_validation_report.md`

## Critical missing evidence

The paper is not experimentally ready yet. The following are blocking:

1. Neo4j has not been started; no graph ingestion result exists.
2. No end-to-end query has completed against a Neo4j round trip.
3. No manually annotated query benchmark exists.
4. No retrieval baseline or ablation has been run.
5. No quantitative Context-gating result exists.
6. No grounded-answer or citation-faithfulness evaluation exists.
7. No domain expert has reviewed a sample of extracted Claims and Contexts.
8. The related-work and novelty analysis is incomplete.

The submission must not imply these are complete.

## Minimum viable evaluation

### Evaluation questions

- **RQ1: Extraction validity.** Do extracted Contexts, Claims, and evidence links agree with the papers?
- **RQ2: Applicability retrieval.** Does Context gating improve retrieval of environmentally applicable Claims over topical retrieval alone?
- **RQ3: Path coherence.** Does gating reduce mechanism paths that combine incompatible environmental regimes?
- **RQ4: Grounding.** Are answer statements supported by the cited Claims and exact SourceBlocks?
- **RQ5: Abstention.** Does the pipeline reject malformed extraction and unsupported queries rather than fabricate an answer?

### Benchmark to build today

Create 18-24 queries across the ten successful papers:

- 5-6 direct intervention-to-outcome questions;
- 5-6 mechanism-chain questions;
- 4 transferability questions with a matching or mismatching Context;
- 3 sign-reversal, null-result, or contradiction questions;
- 2-3 spatial questions where translation should be allowed or explicitly disallowed.

For every query, manually annotate:

- relevant Paper IDs;
- relevant Context IDs;
- relevant Claim IDs;
- minimum supporting SourceBlock IDs;
- expected outcome direction or “insufficient evidence”;
- whether transfer is supported, mismatched, or under-specified;
- whether spatial translation is allowed.

Keep the benchmark JSON under `climatekg/runtime/output/benchmark`, but prepare an anonymized, license-safe version for supplementary release. Do not redistribute copyrighted PDFs or long extracted passages.

### Required systems

Run at least these four variants on the identical query set:

| Variant | Purpose |
|---|---|
| BM25 over SourceBlocks | Lexical retrieval baseline |
| Dense retrieval over SourceBlocks/Claims | Flat semantic RAG baseline |
| Graph retrieval without Context gating | Tests whether graph structure alone is sufficient |
| Full ClimateKG | Context retrieval, Claim gating, coherent path search, evidence synthesis |

High-value ablations if time permits:

- remove conditioning Facets;
- replace Facet matching with whole-Context cosine only;
- disable Context-path coherence;
- disable contradiction retrieval.

### Metrics

Report deterministic metrics before subjective ratings:

- relevant Claim Recall@5 and Recall@10;
- applicable Claim Precision@5;
- Context mismatch rate among retained Claims;
- evidence citation precision;
- evidence citation recall against the smallest gold evidence set;
- incompatible-path rate;
- supported-answer-item rate;
- correct abstention rate;
- query latency and number of generative calls.

For extraction, manually audit a stratified sample, for example:

- 30 Contexts;
- 50 Claims;
- 50 Claim-to-SourceBlock links;
- every sign-reversal split;
- all five `NEEDS_REVIEW` failures.

Report precision with raw numerators and denominators. Do not use an LLM judge as the only evaluator. A second human reviewer on even 20-25% of the sample is substantially better than a single unverified annotation pass.

### Results table that must exist

The main paper needs one compact table with rows for the four systems and columns for:

- applicable Precision@5;
- Claim Recall@10;
- citation precision;
- incompatible-path rate;
- abstention accuracy.

Do not spend main-page space on object counts if retrieval results are absent. Put detailed indexing counts and failure taxonomy in the appendix.

## Paper structure for four pages

### Page 1: Problem, gap, and contribution

- Context-dependent land-atmosphere evidence and the risk of false transfer.
- One concrete motivating reversal or mismatch example from the indexed corpus.
- Why flat search/RAG and ungated graph traversal are insufficient.
- Three concise contributions, supported by results rather than implementation inventory.

### Page 2: Method

- One architecture figure: PDF -> scientific objects -> Context gating -> coherent paths -> cited answer.
- Minimal schema diagram.
- Context/Facet matching and the missing-versus-mismatch distinction.
- Claim gating before path construction.
- Provenance and fail-closed validation.

### Page 3: Evaluation

- Corpus and benchmark definition.
- Baselines and ablations.
- Main quantitative table.
- One error-analysis sentence covering rejected papers.

### Page 4: Example, climate impact, and limitations

- One compact query trace: query Facets -> retained/rejected Contexts -> path -> SourceBlocks.
- Pathway to expert decision support.
- Limitations and safeguards.
- Conclusion with a narrow, evidenced claim.

References and optional appendices can contain schemas, prompts, thresholds, additional traces, failure cases, compute details, and annotation instructions.

## Figures to create

Only create figures after results are stable.

1. **System figure:** Context-aware indexing and query flow. Show Context gating before path search visually.
2. **Failure example:** The same intervention has different outcomes under distinct temporal or environmental Contexts; ungated retrieval mixes them, ClimateKG separates them.
3. **Optional audit trace:** Answer statement -> Claim -> Context/Facet -> Paper -> SourceBlock.

Use vector diagrams generated from repository data or manually authored. Do not use decorative graphics.

## Related-work search

Search and organize prior work into four groups:

1. Scientific knowledge graphs and scholarly information extraction.
2. GraphRAG, knowledge-graph retrieval, and path-based question answering.
3. Context-aware retrieval, metadata-conditioned retrieval, and applicability/transfer reasoning.
4. Climate and Earth-science NLP, literature synthesis, and land-atmosphere evidence systems.

For every paper, record the exact capability difference:

- Does it model scientific findings or only entities?
- Does it preserve exact textual evidence?
- Does it represent environmental applicability?
- Does it gate before path construction?
- Does it distinguish missing information from mismatch?
- Does it preserve contradictions and regime reversals?

Do not manufacture citations. Every citation must be opened and verified by an author.

## Limitations and risks to state plainly

- The current corpus is small and selected for mechanisms, not representative of all climates, regions, interventions, or publication venues.
- LLM extraction can fail; the five fail-closed papers demonstrate this rather than eliminate it.
- Evidence retrieval scores are applicability/ranking signals, not probabilities of scientific truth.
- Extracted literature may inherit publication, geographic, language, and methodological bias.
- Causal and associative findings remain distinct, but literature evidence alone cannot establish local causal validity.
- Location-specific guidance requires trusted local environmental and geometric data; cardinal directions must not be invented from prose.
- The system does not replace regional climate models, field studies, stakeholder consultation, or indigenous/local knowledge.
- Local generative inference has computational and energy costs; report hardware, model, total run time, and approximate energy if measurable.
- PDF and extracted-text licensing constrains release of the evaluation corpus.

## Reproducibility package

Before submission, prepare:

- anonymized code snapshot;
- environment lock file, not only broad dependency ranges;
- configuration and threshold files;
- prompt versions;
- selected-paper metadata and hashes, without redistributing restricted PDFs;
- benchmark queries and gold IDs where licensing permits;
- commands for indexing, Neo4j ingestion, and query evaluation;
- aggregate metrics and raw per-query reports;
- hardware, models, inference settings, run time, and failure logs;
- license and intended-use statement.

The current `pyproject.toml` lists only `pydantic`; it is not a complete reproducibility environment. Fix this before code release.

## Three-to-four-day critical path

### August 24: unblock and freeze

- Create or verify OpenReview profiles for every author.
- Download the official workshop LaTeX template manually and create an anonymized paper repository.
- Start Docker Desktop/Neo4j manually or explicitly authorize the required system action.
- Ingest the ten successful papers and verify node/relationship/vector-index counts.
- Freeze the method. Do not add optional enrichment or redesign schemas now.
- Define the benchmark JSON schema and write all queries.
- Assign one author to scientific annotation and one to implementation/results.

**Go/no-go gate:** if Neo4j ingestion and one grounded query do not work by the end of the day, target the Proposal track or withdraw this deadline.

### August 25: experiments

- Complete gold annotations.
- Run BM25, dense, ungated-graph, and full-system variants.
- Run the no-gating and whole-Context-only ablations.
- Save all per-query reports.
- Compute metrics with deterministic scripts.
- Audit failed and contradictory cases.
- Freeze the result CSV/JSON by evening.

### August 26: analysis and figures

- Independent spot-check of at least 20-25% of annotations.
- Resolve metric bugs; do not tune on the final test queries without disclosing it.
- Create the main result table and architecture figure.
- Perform related-work search and citation verification.
- Draft method and evaluation sections from the frozen artifacts.

### August 27: full paper

- Draft introduction, climate-impact pathway, limitations, and conclusion.
- Fit the four-page limit without shrinking typography or moving essential results to the appendix.
- Add reproducibility and LLM-use disclosures.
- Anonymize PDF, metadata, code links, filenames, and supplementary material.
- Ask a climate-domain reader and an ML reader for one rapid review each.

### August 28: submission candidate

- Incorporate only high-impact corrections.
- Re-run every number in the paper from saved artifacts.
- Check every citation, figure label, claim, and page limit.
- Complete the required checklist and OpenReview metadata.
- Upload and inspect the rendered PDF by 20:00 IST.

### August 29: buffer only

- Use only for submission-system or critical correctness problems.
- Do not start new experiments or broaden claims.

## Decision rule for track selection

Submit to the **Papers track** only if all are true:

- Neo4j round trip succeeds;
- at least 18 annotated queries exist;
- all four primary variants run on the same benchmark;
- Context gating has at least one quantitative result;
- grounded citation evaluation is complete;
- results and limitations fit legibly in four pages.

Otherwise submit a carefully scoped **Proposal** or defer. A proposal should present the system design, fail-closed pilot indexing, benchmark plan, and climate-impact pathway as work to be completed; it must not present unrun query experiments as results.

## Claims that are safe now versus unsafe now

### Currently defensible

- The system implements a context-conditioned scientific KG/GraphRAG architecture.
- Ten heterogeneous papers produced validated indexed artifacts with exact provenance.
- Five additional papers were rejected visibly under strict validation.
- The representation preserves Context hierarchy, Facets, Transitions, Claims, States, and SourceBlocks.
- Deterministic tests cover key normalization, hierarchy, provenance, reconciliation, graph-property, and evidence-budget behavior.

### Not yet defensible

- ClimateKG improves retrieval accuracy over RAG.
- Context gating reduces incompatible paths by a measured amount.
- Answers are more scientifically correct than baselines.
- The system generalizes across the land-atmosphere literature.
- The system provides reliable local land-management recommendations.
- The approach is the first context-aware climate GraphRAG.

The experiments, not the desired narrative, determine which of these claims can enter the final paper.

## Immediate owner checklist

- [ ] OpenReview accounts verified for all authors.
- [ ] Author list frozen and reciprocal-review requirement checked.
- [ ] Official template obtained and anonymized repository created.
- [ ] Neo4j started and ten papers ingested.
- [ ] Graph counts verified.
- [ ] Benchmark query/gold schema committed.
- [ ] 18-24 queries annotated.
- [ ] Four primary variants run.
- [ ] Metrics generated from a script.
- [ ] Main table frozen.
- [ ] Architecture and failure-example figures created.
- [ ] Related work verified by authors.
- [ ] Climate pathway and limitations reviewed by a domain expert.
- [ ] Environment lock file and reproducibility commands prepared.
- [ ] PDF/code/supplement anonymized.
- [ ] LLM-use and compute disclosures checked.
- [ ] Final PDF uploaded before the internal deadline.
