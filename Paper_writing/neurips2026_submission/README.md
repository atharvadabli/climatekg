# NeurIPS 2026 Workshop Submission

Main manuscript: `main.tex`

Compiled submission: `climatekg_tccml_neurips2026.pdf`

Supporting files:

- `appendix.tex`: staged/combined extraction objects and complete query traces.
- `references.bib`: verified bibliographic records used by the manuscript.
- `evaluation_queries.json`: ten frozen questions, expected Claims, and conditions.
- `gold_answers.json`: author-prepared reference propositions; independent review pending.
- `example_outputs/`: verbatim prompt/retrieval/thinking/response traces for completed examples.
- `THREE_SYSTEM_TRACE_NOTES.md`: source-grounded comparison of the first two traces.
- `PAPER_REVISION_NOTES.md`: outline, claim-evidence map, and adversarial self-review.
- `evaluation/extraction_audit/`: ten paper-level review sheets and deterministic reference audit.
- `RESULTS_LEDGER.md`: records which numbers are measured, manually reviewed,
  planned, or unavailable.
- `tackling_climate_workshop_style.sty`: official anonymous workshop style.

Build from this directory:

```powershell
..\..\climatekg\runtime\tools\tectonic-0.17.0\tectonic.exe main.tex
Copy-Item main.pdf climatekg_tccml_neurips2026.pdf -Force
```

Standard `pdflatex`/`bibtex` also works. The portable Tectonic binary is cached
under the ignored `climatekg/runtime/tools` directory and is not committed.

The main text must end by page 4. References and appendices follow and do not
count toward that limit. The PDF remains anonymous for double-blind review.
