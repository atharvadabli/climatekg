# Extraction ground truth

One file per audited paper. Each file records the study settings and own-result
relationships that a careful reader can support from the parsed text that the
extractor actually saw, so that staged extraction recall can be measured instead
of asserted.

## Provenance

The annotations were produced by reading the exported parsed text under
`climatekg/runtime/outputs/baseline_comparison_20260830_v2/corpus/markdown/`,
which is the same SourceBlock content the extraction pipeline consumed, minus
references and page furniture. They were written by a frontier assistant model
(Claude Opus 5) working from that text alone and are checkable line by line
against the `evidence` block ids recorded in each entry. They were **not**
produced by running any extraction system, and they were not derived from the
pipeline output, so they are usable as an independent target.

`gpt-5.6-sol` was not reachable from the annotation machine and Ollama's hosted
models are subscription gated, so no larger-model annotation pass was possible.
Any published description of this ground truth must say so.

## Counting rules

These mirror `prompts/paper_map.txt` and `prompts/claim_extraction.txt` so that
the target and the system output are the same kind of object.

**Study settings.** One setting per complete combination of conditions the paper
directly analyses: study area, data source, simulation or observation branch,
control and treatment, season, time window, environmental regime, resolution,
and each individually evaluated value of an experimental variable. Settings are
separate when any applicability condition differs, even when the reported result
is the same or null. Settings belonging only to cited background work are
excluded.

**Claims.** One claim per directed relationship between two scientific endpoints
that the paper reports as its own finding. Only `OWN_RESULT` and
`AUTHORS_INTERPRETATION_OF_OWN_RESULT` count, because `climatekg/extract.py`
and `climatekg/reconcile.py` discard the other two roles. Separate, null,
opposite, conditional, seasonal, scale-dependent, threshold, and
timing-dependent findings are counted separately whenever the text distinguishes
them. A multi-step mechanism is counted as one claim per step only where the
text supports each step on its own.

## Schema

```json
{
  "paper_id": "P000006",
  "title": "...",
  "markdown": "path to the annotated text",
  "settings": [{"key": "...", "description": "...", "evidence": ["block ids"]}],
  "claims": [
    {
      "key": "short stable slug",
      "from": "source endpoint",
      "to": "target endpoint",
      "relation": "causal | associative",
      "role": "OWN_RESULT | AUTHORS_INTERPRETATION_OF_OWN_RESULT",
      "statement": "one evidence-faithful sentence",
      "evidence": ["block ids"],
      "matched_claim_id": "extracted claim id, or null when the system missed it",
      "match_note": "why the match was accepted or rejected"
    }
  ]
}
```

`matched_claim_id` is filled by reading the extracted `final_paper.json` for the
same paper and accepting a match only when the extracted record carries the same
directed relationship. Wording may differ; the endpoints and the direction may
not. `scripts/audit_extraction_recall.py` turns these files into the recall
table.
