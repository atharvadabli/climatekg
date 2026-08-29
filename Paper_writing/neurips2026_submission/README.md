# NeurIPS 2026 Workshop Submission

Main manuscript: `main.tex`

Compiled submission: `climatekg_tccml_neurips2026.pdf`

Supporting files:

- `appendix.tex`: staged/combined extraction objects and complete query traces.
- `references.bib`: verified bibliographic records used by the manuscript.
- `evaluation_queries.json`: frozen pilot questions and expected conditions.
- `query_audit.json`: manual outcome and failure audit for the three frozen
  diagnostic questions.
- `example_outputs/`: verbatim generated answers for those questions.
- `RESULTS_LEDGER.md`: records which numbers are measured, manually reviewed,
  planned, or unavailable.
- `tackling_climate_workshop_style.sty`: official anonymous workshop style.

Build from this directory:

```powershell
..\..\climatekg\runtime\tools\tectonic\tectonic.exe -X compile main.tex --outdir build
Copy-Item build\main.pdf climatekg_tccml_neurips2026.pdf -Force
```

Standard `pdflatex`/`bibtex` also works. The portable Tectonic binary is cached
under the ignored `climatekg/runtime/tools` directory and is not committed.

The main text must end by page 4. References and appendices follow and do not
count toward that limit. The PDF remains anonymous for double-blind review.
