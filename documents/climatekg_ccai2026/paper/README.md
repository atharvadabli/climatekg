# ClimateKG CCAI 2026 Paper Source

## Files

- `climatekg_ccai2026.tex`: anonymous four-page-oriented paper draft
- `references.bib`: bibliography used by the draft
- `SUBMISSION_GAPS.md`: blocking experiments and completion checklist

The original manuscript at `E:\Atharv\lulc_suggestor_poc\19_aug_claude\doc.tex` remains unchanged. A preserved reference copy is available at `../source/original_doc.tex`.

## Official style dependency

The source intentionally requires `neurips_2026.sty` and does not modify page geometry or typography. Place the unchanged official workshop style files beside the source before compiling. The managed environment rejected downloading the official ZIP, so the style file is not vendored here.

Anonymous review mode is the default:

```tex
\usepackage{neurips_2026}
```

Do not add `final` or `preprint` for double-blind review.

## Build

With a LaTeX distribution and the official style present:

```powershell
pdflatex climatekg_ccai2026.tex
bibtex climatekg_ccai2026
pdflatex climatekg_ccai2026.tex
pdflatex climatekg_ccai2026.tex
```

No TeX compiler is currently available in this environment, so the draft has not yet been rendered or page-counted. Resolve all `\missing{...}` markers before treating it as submission-ready.
