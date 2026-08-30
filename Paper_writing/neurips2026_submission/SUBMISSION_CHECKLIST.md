# Submission Checklist

## Complete

- Anonymous official workshop style.
- Four-page main body; references begin on page 5.
- Appendix includes schemas, staged extraction traces, query trace, and a
  documented retrieval failure.
- All reported counts and timings trace to saved benchmark JSON.
- Compiled PDF page count checked: main body ends on page 4 and references begin on page 5.
- Repository tests: 89 existing tests plus 3 benchmark-evaluation tests.
- Custom ClimateKG, plain RAG, and Microsoft GraphRAG code are present on the
  paper branch; generated indexes and caches remain ignored.

## Before Upload

- Replace `Anonymous Author(s)` only if the submission site requests a
  non-anonymous version; otherwise preserve double-blind formatting.
- Confirm title, author order, affiliations, acknowledgements, and conflicts in
  the submission form.
- Re-read the four-page body for scientific claims and author-approved wording.
- Upload `climatekg_tccml_neurips2026.pdf` and verify the portal preview.
- Do not describe the Rajasthan example as a recommendation or the retrieval
  score as scientific confidence.

## Results Worth Adding Only If Finished and Audited

- Out-of-corpus Rajasthan query result and trace.
- Remaining equal-corpus PlainRAG, community-graph, and ClimateKG answers.
- Expert citation/path audit.

Do not delay the submission for incomplete baselines. The current manuscript
states that these results are unfinished and does not claim system superiority.
