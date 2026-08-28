# ClimateKG Paper: Acceptance-Critical Gaps

This file tracks every visible `\missing{...}` marker in `climatekg_ccai2026.tex`. Do not remove a marker by replacing it with an estimate, aspiration, or manually invented number. Each result must be generated from frozen artifacts.

## Blocking experiments

- [ ] Start Neo4j and complete the ten-paper graph ingestion round trip.
- [ ] Verify node, relationship, and vector-index counts against the saved final-paper JSON.
- [ ] Save at least one complete question-to-grounded-answer query report before freezing the benchmark.
- [ ] Define 18-24 representative queries and a gold annotation schema.
- [ ] Record annotator expertise, independent-review subset, agreement, and adjudication.
- [ ] Run BM25, dense RAG, ungated graph, and full ClimateKG on identical inputs.
- [ ] Run whole-Context-only and no-conditioning-Facet ablations.
- [ ] Generate Claim, path, citation, answer-support, latency, token, and memory metrics deterministically.
- [ ] Add uncertainty intervals suitable for the benchmark size.
- [ ] Freeze all result JSON/CSV before copying numbers into the paper.

## Required paper inserts

- [ ] Abstract: benchmark size and measured headline result.
- [ ] Introduction: one sentence stating the measured contribution.
- [ ] Evaluation: exact benchmark split and annotation protocol.
- [ ] Table 2: replace every placeholder with generated results.
- [ ] Results: add one compact ungated-versus-gated trace with exact SourceBlock citations.
- [ ] Impact: add a land-atmosphere expert review and identify the actual intended user.
- [ ] Limitations: measured failure categories, external-validity boundary, and compute/energy use.
- [ ] Conclusion: measured result without implying scientific truth or intervention effectiveness.

## Scientific review

- [ ] Verify every bibliography entry against the published source.
- [ ] Check that cited background is never described as a finding of the indexed paper.
- [ ] Audit at least 20-25% of benchmark labels independently.
- [ ] Confirm that contradictory, conditional, scale-dependent, seasonal, and sign-reversing cases appear in the evaluation.
- [ ] Confirm that Context gating precedes path search in every evaluated run.
- [ ] Confirm that every answer proposition resolves to retained Claims and SourceBlocks.
- [ ] Check causal versus associative wording in all qualitative examples.
- [ ] Remove any local recommendation unsupported by both local data and transferable evidence.

## Submission compliance

- [ ] Obtain the official workshop style archive and keep its files unchanged.
- [ ] Compile `climatekg_ccai2026.tex` with the official `neurips_2026.sty` in anonymous mode.
- [ ] Confirm the main text is at most four pages; references may follow.
- [ ] Keep essential method and result material out of discretionary appendices.
- [ ] Remove all red `MISSING` markers.
- [ ] Remove author names, affiliations, acknowledgments, identifying repository URLs, filenames, and PDF metadata.
- [ ] Run an anonymization and page-limit check on the rendered PDF.
- [ ] Have all human authors independently verify the current official requirements and approve the final wording.
- [ ] Add the required LLM-use disclosure in the appropriate submission field or manuscript location after author review.
- [ ] Check whether the author team triggers reciprocal-reviewer nomination.
- [ ] Confirm all OpenReview accounts and author ordering before submission.

## Track gate

Use the Papers track only when the graph/query round trip, common benchmark, comparative results, and grounded-answer audit are complete. If these remain incomplete, this source must be converted to a three-page Proposal and must describe unrun experiments as future work.
