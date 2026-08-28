CLIMATEKG CCAI 2026 DOCUMENT INDEX
==================================

Purpose
-------
This folder contains the publication and manuscript documents for the
ClimateKG submission effort. Implementation specifications remain at the
repository root because they are authoritative engineering documents used by
the codebase.


FOLDER: paper
-------------

paper/climatekg_ccai2026.tex
    The current anonymous LaTeX paper draft. It is written for a four-page
    Papers-track submission and uses the NeurIPS 2026 style. Red MISSING
    markers identify results or reviews that must be completed before
    submission. This is the main manuscript to edit.

paper/references.bib
    BibTeX bibliography used by climatekg_ccai2026.tex. Every entry must be
    checked against the original publication before submission.

paper/SUBMISSION_GAPS.md
    Acceptance-critical experiment, scientific-review, anonymization, and
    submission checklist. A MISSING marker should not be removed until its
    supporting artifact or review exists.

paper/README.md
    Build instructions, official-style dependency, and current rendering
    limitations for the LaTeX paper.


FOLDER: planning
----------------

planning/NEURIPS2026_CCAI_SUBMISSION_STRATEGY.md
    Overall positioning, contribution framing, evaluation design, schedule,
    track decision, and submission checklist.

planning/DOC_TEX_SUBMISSION_REVIEW.md
    Assessment of the earlier manuscript. It records which material is useful,
    what terminology is outdated, what claims are unsupported, and how the
    material maps into a four-page paper.

planning/QUERY_VALIDATION_GUIDE.md
    Query-suite contents, graph-backed execution command, verbose stage list,
    artifact layout, and the recorded Neo4j preflight blocker.

planning/TECHNICAL_PIPELINE_WALKTHROUGH.md
    Plain-language technical reference organized into Indexing and Querying.
    It includes persistent and temporary schemas, the standalone prompt
    design and review locations, the complete authoritative indexing prompt
    set, the NVIDIA parser control prompt, historical v1 prompts clearly
    marked obsolete, and a prompt-conformance audit. It also
    explains generated repairs and the current envelope reproducibility gap,
    followed by step-by-step graph construction, retrieval, grounding,
    artifacts, and failure signals. It follows three real
    saved examples from PDF parsing through indexed objects, graph retrieval,
    intermediate scores and paths, evidence Blocks, and cited final answers.

planning/FINAL_QUERY_VALIDATION_SUMMARY.md
    Final ten-query pass summary, result counts, authoritative artifact path
    for every answer, repaired failure analysis, and remaining research work.

planning/OLD_VS_NEW_PROMPT_REPORT.md
    Stage-by-stage comparison of the old and standalone indexing prompts on
    the same surface-heterogeneity paper. It records output counts, the old
    reference failure, improvements, scientific regressions, and limits of
    the one-run comparison.


FOLDER: source
--------------

source/original_doc.tex
    Preserved copy of the earlier 597-line manuscript from:
    E:\Atharv\lulc_suggestor_poc\19_aug_claude\doc.tex

    This is reference material, not the submission manuscript. The original
    external file was not modified.


AUTHORITATIVE DOCUMENTS OUTSIDE THIS FOLDER
-------------------------------------------

../../land_atmosphere_kg_indexing_pipeline.md
    Authoritative indexing implementation specification. It overrides older
    manuscript descriptions and implementation choices.

../../land_atmosphere_kg_query_pipeline.md
    Authoritative query, gating, path-search, and grounded-answer specification.

../../land_atmosphere_kg_problem_statement.md
    Project purpose, scientific problem, and intended system behavior.

../../land_atmosphere_kg_project_summary.md
    Supporting architectural context.

../../AGENTS.md
    Repository implementation and validation rules.


VALIDATION EVIDENCE OUTSIDE THIS FOLDER
---------------------------------------

../../climatekg/runtime/output/validation/e2e_validation_report.md
    Human-readable pilot validation report.

../../climatekg/runtime/output/validation/e2e_validation_report.json
    Machine-readable source for reported paper counts and pipeline status.

The runtime validation files remain in climatekg/runtime so generated evidence
is not duplicated or allowed to drift away from the pipeline output.


RECOMMENDED READING ORDER
-------------------------

1. planning/NEURIPS2026_CCAI_SUBMISSION_STRATEGY.md
2. paper/SUBMISSION_GAPS.md
3. paper/climatekg_ccai2026.tex
4. planning/DOC_TEX_SUBMISSION_REVIEW.md
5. source/original_doc.tex, only when recovering useful earlier prose


CURRENT LIMITATIONS
-------------------

- The official workshop style archive is not present because its download was
  rejected by the managed environment.
- No TeX compiler is installed, so the manuscript has not been rendered or
  page-counted.
- Neo4j ingestion is complete for the ten finalized papers.
- All ten generic, Context-dependent, comparison, and spatial validation
  queries have a passing final graph-backed run.
- Comparative retrieval metrics and broader scientific expert review remain
  necessary before a Papers-track submission.
