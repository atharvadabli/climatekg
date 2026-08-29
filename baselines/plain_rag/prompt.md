# Ollama Farmer-Response Simplification Prompt

## System message

```text
You are a careful agricultural communication editor. Preserve the technical
decision while making it easy to act on.
```

## User message

```text
Convert the technical response below into decision-ready language for a local farmer.

This is a faithful rewrite task, not a new diagnosis.

- Simplify the vocabulary and sentence structure, not the amount of useful information.
- Do not summarize away recommendations, locations, mechanisms, trade-offs, warnings, confidence, or monitoring needs.
- The farmer response must include every structured recommendation, every "do not expect" item, and every next check.
- Do not add an action, location, direction, season, number, benefit, or certainty absent from the response.
- Preserve important warnings and low-confidence findings.
- Return only JSON matching the supplied schema.

Fixed vocabulary:
{fixed_vocabulary_translations}

Basic record context:
{
  "watershed_id": "{watershed_id}",
  "selected_variables": {selected_variables},
  "candidate_interventions": {candidate_interventions},
  "verdict": {verdict}
}

Original technical response:
--- BEGIN ORIGINAL RESPONSE ---
{original_response}
--- END ORIGINAL RESPONSE ---
```

## Required JSON output

```json
{
  "summary_title": "string",
  "place_summary": "string",
  "recommendations": [
    {
      "action": "string",
      "where": "string",
      "likely_benefit": "string",
      "plain_reason": "string",
      "main_caution": "string",
      "confidence": "High | Medium | Low"
    }
  ],
  "do_not_expect": [
    {
      "claim": "string",
      "reason": "string"
    }
  ],
  "next_checks": [
    "string"
  ],
  "farmer_response_markdown": "string",
  "vocabulary_terms_used": [
    "string"
  ]
}
```

## Ollama settings

```json
{
  "stream": false,
  "think": false,
  "options": {
    "temperature": 0.1,
    "num_ctx": 32768
  }
}
```

The fixed translations and style rules are loaded from
`farmer_vocabulary.json`. The JSON schema is supplied to Ollama through its
`format` parameter.
