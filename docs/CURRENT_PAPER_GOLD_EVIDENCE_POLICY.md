# Gold evidence policy

## Required provenance

Every answerable benchmark question must be supported by a result, observation, simulation, analysis, null result, or limitation produced by the indexed paper itself.

A passage is not valid gold evidence when it only:

- summarizes a finding from another named study;
- reports a result followed by a citation where the result belongs to that citation;
- appears in a literature review without a new analysis by the indexed paper; or
- states general scientific background.

Review papers can be included only for findings produced by the review itself, such as a systematic synthesis, meta-analysis, or new quantitative comparison. The question and answer must describe that synthesis rather than silently transferring a cited study's finding to the review paper.

## Construction procedure

1. Select candidate passages from the original SourceBlocks, independently of generated answers.
2. Determine who produced the stated finding: the indexed paper or cited literature.
3. Draft the question and reference answer only when the indexed paper produced the finding.
4. Record the smallest sufficient SourceBlocks, paper ID, page, and required conditions.
5. Check the passage against the original PDF before setting `human_verified`.

Extracted `OWN_RESULT` Claims may be used to locate candidate passages and catch provenance mistakes. They are not themselves gold evidence, and their absence does not prove that a passage is invalid.

## Corrected ten-case dataset

The first architecture benchmark used four invalid review passages. Dataset v2 replaces them while preserving their IDs and `context_conditional` category:

| Case | Replacement evidence |
|---|---|
| `CKGQ0003` | P000019 current simulations of weakened synoptic wind, deforestation-induced circulation, clouds, and rainfall |
| `CKGQ0005` | P000007 current analysis of drought effects on irrigated versus rainfed cooling |
| `CKGQ0008` | P000014 current observations of seasonal, wind, and forest-size dependence of cloud enhancement |
| `CKGQ0009` | P000004 current simulations of asymmetric daytime/nighttime irrigation effects and heat-wave duration |

The generated dataset is located at:

`evaluation/output/climatekg_benchmark/dataset_v2_current_findings_10/cases.json`

Its status remains `model_checked_requires_human_verification` until every replacement is checked against the corresponding PDF.
