#!/usr/bin/env python3
"""Simplify saved technical watershed answers with a fixed vocabulary and Ollama."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_INPUTS = [
    Path("query_outputs/portal_app/A01GHO56_temperature_humidity_precipitation_wind_20260721_152314.json"),
    Path("query_outputs/portal_app/B20SAR01_temperature_humidity_precipitation_wind_20260715_171839.json"),
    Path("query_outputs/portal_app/C05CAM63_temperature_humidity_precipitation_wind_20260715_171456.json"),
]
DEFAULT_VOCABULARY = Path("farmer_vocabulary.json")
DEFAULT_OUTPUT_JSON = Path("query_outputs/simplified/farmer_response_comparisons.json")
DEFAULT_OUTPUT_HTML = Path("query_outputs/simplified/farmer_response_comparisons.html")
DEFAULT_IDEAL_EXAMPLES = [
    Path("ideal_farmer_response.json"),
    Path("ideal_farmer_responses/B20SAR01.json"),
    Path("ideal_farmer_responses/C05CAM63.json"),
]
DEFAULT_MODEL = "qwen3.6:27b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_title": {"type": "string"},
        "place_summary": {"type": "string"},
        "recommendations": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "where": {"type": "string"},
                    "likely_benefit": {"type": "string"},
                    "plain_reason": {"type": "string"},
                    "main_caution": {"type": "string"},
                    "confidence": {
                        "type": "string",
                        "enum": ["High", "Medium", "Low"],
                    },
                },
                "required": [
                    "action",
                    "where",
                    "likely_benefit",
                    "plain_reason",
                    "main_caution",
                    "confidence",
                ],
            },
        },
        "do_not_expect": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["claim", "reason"],
            },
        },
        "next_checks": {
            "type": "array",
            "maxItems": 3,
            "items": {"type": "string"},
        },
        "farmer_response_markdown": {"type": "string"},
        "vocabulary_terms_used": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "summary_title",
        "place_summary",
        "recommendations",
        "do_not_expect",
        "next_checks",
        "farmer_response_markdown",
        "vocabulary_terms_used",
    ],
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def post_json(url: str, payload: dict[str, Any], timeout: int = 1800) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {url}: {exc}") from exc


def compact_vocabulary(vocabulary: dict[str, Any]) -> str:
    lines = []
    for item in vocabulary["translations"]:
        source_terms = [item["technical"], *item.get("variants", [])]
        lines.append(f"- {' / '.join(source_terms)} => {item['farmer_friendly']}")
    return "\n".join(lines)


def build_prompt(source: dict[str, Any], vocabulary: dict[str, Any]) -> str:
    answer = source.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Input JSON does not contain a non-empty 'answer' field.")

    context = {
        "watershed_id": source.get("watershed_id", "Unknown"),
        "selected_variables": source.get("selected_variables", []),
        "candidate_interventions": source.get("candidate_interventions", []),
        "verdict": source.get("verdict", []),
    }
    rules = "\n".join(f"- {rule}" for rule in vocabulary["style_rules"]["rules"])
    return f"""Convert the technical response below into decision-ready language for a local farmer.

This is a faithful rewrite task, not a new diagnosis.
- Simplify the vocabulary and sentence structure, not the amount of useful information.
- Do not summarize away recommendations, locations, mechanisms, trade-offs, warnings, confidence, or monitoring needs.
- The farmer response must include every structured recommendation, every "do not expect" item, and every next check.
- Do not add an action, location, direction, season, number, benefit, or certainty absent from the response.
- Preserve important warnings and low-confidence findings.
- A possible effect must remain possible; never turn it into a promise.
- Humidity and crop-air dryness move in opposite directions. More humidity normally means less crop-air dryness.
- Put the most useful action first.
- Use at most {vocabulary["style_rules"]["maximum_recommendations"]} recommendations.
- Prefer sentences of 18 words or fewer.
- Return only JSON matching the supplied schema.

Additional rules:
{rules}

Fixed vocabulary:
{compact_vocabulary(vocabulary)}

Basic record context:
{json.dumps(context, ensure_ascii=False, indent=2)}

Original technical response:
--- BEGIN ORIGINAL RESPONSE ---
{answer}
--- END ORIGINAL RESPONSE ---
"""


def simplify(
    source: dict[str, Any],
    vocabulary: dict[str, Any],
    model: str,
    ollama_url: str,
) -> dict[str, Any]:
    result = post_json(
        f"{ollama_url.rstrip('/')}/api/chat",
        {
            "model": model,
            "stream": False,
            "think": False,
            "format": OUTPUT_SCHEMA,
            "options": {"temperature": 0.1, "num_ctx": 32768},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a careful agricultural communication editor. "
                        "Preserve the technical decision while making it easy to act on."
                    ),
                },
                {"role": "user", "content": build_prompt(source, vocabulary)},
            ],
        },
    )
    content = result.get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty response.")
    try:
        simplified = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Ollama did not return valid JSON: {content[:300]}") from exc
    return simplified


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def repair_mojibake(text: str) -> str:
    """Repair common UTF-8 text that was previously decoded as Windows-1252."""
    for broken, repaired in {
        "Â°": "°",
        "Â²": "²",
        "â€“": "–",
        "â€”": "—",
        "â€™": "’",
        "â€œ": "“",
        "â€": "”",
    }.items():
        text = text.replace(broken, repaired)
    if not any(marker in text for marker in ("Â", "â€", "ðŸ")):
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


def apply_fixed_vocabulary(
    text: str,
    vocabulary: dict[str, Any],
) -> tuple[str, list[str]]:
    """Enforce fixed term translations after model generation."""
    replacements = []
    for item in vocabulary["translations"]:
        for term in [item["technical"], *item.get("variants", [])]:
            replacements.append((term, item["farmer_friendly"]))
    replacements.sort(key=lambda pair: len(pair[0]), reverse=True)

    translated = repair_mojibake(text)
    used = []
    for technical, farmer_friendly in replacements:
        pattern = re.compile(
            rf"(?<!\w){re.escape(technical)}(?!\w)",
            flags=re.IGNORECASE,
        )
        translated, count = pattern.subn(farmer_friendly, translated)
        if count:
            used.append(technical)
    translated = translated.replace(
        "wind-slowing wind resistance near the ground",
        "wind resistance near the ground",
    )
    return translated, sorted(set(used), key=str.lower)


def normalize_simplification(
    simplified: dict[str, Any],
    vocabulary: dict[str, Any],
) -> dict[str, Any]:
    applied = set(simplified.get("vocabulary_terms_used", []))

    def normalize(value: Any) -> Any:
        if isinstance(value, str):
            translated, used = apply_fixed_vocabulary(value, vocabulary)
            applied.update(used)
            return translated
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    result = {
        key: normalize(value)
        for key, value in simplified.items()
        if key != "vocabulary_terms_used"
    }
    result["vocabulary_terms_used"] = sorted(applied, key=str.lower)
    return result


def technical_terms_found(text: str, vocabulary: dict[str, Any]) -> list[str]:
    found = []
    for item in vocabulary["translations"]:
        for term in [item["technical"], *item.get("variants", [])]:
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.IGNORECASE):
                found.append(term)
    return sorted(set(found), key=str.lower)


def make_record(
    source_path: Path,
    source: dict[str, Any],
    simplified: dict[str, Any],
    vocabulary: dict[str, Any],
) -> dict[str, Any]:
    simplified = normalize_simplification(simplified, vocabulary)
    original = source["answer"]
    farmer_text = simplified["farmer_response_markdown"]
    return {
        "source_file": source_path.as_posix(),
        "watershed_id": source.get("watershed_id", "Unknown"),
        "selected_variables": source.get("selected_variables", []),
        "candidate_interventions": source.get("candidate_interventions", []),
        "original_response": original,
        "structured_simplification": {
            key: value
            for key, value in simplified.items()
            if key not in {"farmer_response_markdown", "vocabulary_terms_used"}
        },
        "simplified_response": farmer_text,
        "vocabulary_terms_used": simplified.get("vocabulary_terms_used", []),
        "quality_checks": {
            "original_word_count": word_count(original),
            "simplified_word_count": word_count(farmer_text),
            "technical_terms_remaining": technical_terms_found(farmer_text, vocabulary),
        },
    }


def markdown_to_html(text: str) -> str:
    """Render the small, trusted markdown subset produced by the local model."""
    rendered = []
    in_list = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            item = html.escape(line[2:])
            item = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", item)
            rendered.append(f"<li>{item}</li>")
            continue
        if in_list:
            rendered.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("### "):
            rendered.append(f"<h4>{html.escape(line[4:])}</h4>")
        elif line.startswith("## "):
            rendered.append(f"<h3>{html.escape(line[3:])}</h3>")
        elif line.startswith("# "):
            rendered.append(f"<h2>{html.escape(line[2:])}</h2>")
        else:
            paragraph = html.escape(line)
            paragraph = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", paragraph)
            rendered.append(f"<p>{paragraph}</p>")
    if in_list:
        rendered.append("</ul>")
    return "\n".join(rendered)


def build_html(dataset: dict[str, Any]) -> str:
    ideals = dataset.get("ideal_examples")
    if not isinstance(ideals, list):
        legacy_ideal = dataset.get("ideal_example")
        ideals = [legacy_ideal] if isinstance(legacy_ideal, dict) else []
    ideal_navigation = ""
    if ideals:
        ideal_navigation = """
    <nav class="ideal-tabs" aria-label="Choose a detailed watershed example">
      <span>Detailed examples</span>
      <div>
""" + "\n".join(
            (
                f'        <a class="ideal-tab{" active" if index == 0 else ""}" '
                f'href="#ideal-card-{index}" '
                f'data-ideal-target="ideal-card-{index}" '
                f'aria-selected="{"true" if index == 0 else "false"}">'
                f'{html.escape(ideal["watershed_id"])}</a>'
            )
            for index, ideal in enumerate(ideals)
        ) + """
      </div>
    </nav>
"""
    ideal_sections = []
    for ideal_index, ideal in enumerate(ideals):
        ideal_sections.append(f"""
    <section id="ideal-card-{ideal_index}" class="ideal-card{" active" if ideal_index == 0 else ""}">
      <div class="ideal-intro">
        <span class="eyebrow">Featured ideal {ideal_index + 1} of {len(ideals)}</span>
        <h2>{html.escape(ideal['title'])}</h2>
        <p>{html.escape(ideal['subtitle'])}</p>
        <div class="ideal-meta">
          <span>Example watershed</span>
          <strong>{html.escape(ideal['watershed_id'])}</strong>
        </div>
      </div>
      <div class="ideal-response">
        <div class="panel-heading">
          <div><span class="panel-number">00</span><h3>Ideal farmer-facing response</h3></div>
          <button class="copy-button" data-copy="ideal-response-{ideal_index}">Copy</button>
        </div>
        <div id="ideal-response-{ideal_index}" class="farmer-copy">
          {markdown_to_html(ideal['response_markdown'])}
        </div>
      </div>
    </section>
""")
    ideal_section = "\n".join(ideal_sections)

    cards = []
    for index, record in enumerate(dataset["comparisons"]):
        simplified_html = markdown_to_html(record["simplified_response"])
        original = html.escape(record["original_response"])
        variables = ", ".join(record["selected_variables"])
        checks = record["quality_checks"]
        remaining = checks["technical_terms_remaining"]
        term_note = "None" if not remaining else ", ".join(remaining)
        cards.append(
            f"""
            <article class="case-card" data-search="{html.escape((record['watershed_id'] + ' ' + variables).lower())}">
              <header class="case-header">
                <div>
                  <span class="eyebrow">Comparison {index + 1}</span>
                  <h2>{html.escape(record['watershed_id'])}</h2>
                  <p>{html.escape(variables)}</p>
                </div>
                <div class="reduction">
                  <strong>{checks['simplified_word_count']}</strong>
                  <span>words, down from {checks['original_word_count']}</span>
                </div>
              </header>
              <div class="comparison-grid">
                <section class="response-panel technical">
                  <div class="panel-heading">
                    <div><span class="panel-number">01</span><h3>Original technical response</h3></div>
                    <button class="copy-button" data-copy="original-{index}">Copy</button>
                  </div>
                  <pre id="original-{index}">{original}</pre>
                </section>
                <section class="response-panel farmer">
                  <div class="panel-heading">
                    <div><span class="panel-number">02</span><h3>Simplified farmer response</h3></div>
                    <button class="copy-button" data-copy="simple-{index}">Copy</button>
                  </div>
                  <div id="simple-{index}" class="farmer-copy">{simplified_html}</div>
                  <div class="quality-row">
                    <span class="check {'pass' if not remaining else 'warn'}">
                      Fixed-vocabulary terms remaining: {html.escape(term_note)}
                    </span>
                  </div>
                </section>
              </div>
            </article>
            """
        )

    generated = html.escape(dataset["generated_at"])
    model = html.escape(dataset["model"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>From climate evidence to field action</title>
  <style>
    :root {{
      --ink: #17211b;
      --muted: #647068;
      --paper: #f5f1e7;
      --card: #fffdf7;
      --line: #d8d1c2;
      --green: #245c3b;
      --green-soft: #e2eee5;
      --ochre: #b96b2d;
      --technical: #ece8df;
      --shadow: 0 16px 50px rgba(44, 52, 44, .09);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        linear-gradient(rgba(36, 92, 59, .035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(36, 92, 59, .035) 1px, transparent 1px),
        var(--paper);
      background-size: 32px 32px;
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }}
    .page-shell {{ width: min(1500px, calc(100% - 32px)); margin: 0 auto; }}
    .hero {{
      padding: 72px 0 44px;
      display: grid;
      grid-template-columns: 1.4fr .6fr;
      gap: 48px;
      align-items: end;
      border-bottom: 1px solid var(--line);
    }}
    .kicker, .eyebrow {{
      color: var(--ochre);
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .14em;
      font-size: .72rem;
    }}
    h1 {{
      max-width: 820px;
      margin: 12px 0 18px;
      font-family: Georgia, "Times New Roman", serif;
      font-size: clamp(2.7rem, 6vw, 5.9rem);
      font-weight: 500;
      line-height: .96;
      letter-spacing: -.045em;
    }}
    .hero p {{ max-width: 720px; color: var(--muted); font-size: 1.05rem; line-height: 1.7; }}
    .hero-note {{
      padding: 20px 0 4px 24px;
      border-left: 3px solid var(--green);
      color: var(--muted);
      line-height: 1.65;
    }}
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
      padding: 24px 0;
    }}
    .ideal-card {{
      display: grid;
      grid-template-columns: minmax(240px, .38fr) minmax(0, 1fr);
      margin: 34px 0 42px;
      background: var(--green);
      color: #f8f3e7;
      border-radius: 24px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .js-enabled .ideal-card:not(.active) {{ display: none; }}
    .ideal-tabs {{
      position: sticky;
      top: 12px;
      z-index: 20;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      margin: 28px 0 18px;
      padding: 12px 14px 12px 18px;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 253, 247, .94);
      box-shadow: 0 8px 30px rgba(44, 52, 44, .10);
      backdrop-filter: blur(12px);
    }}
    .ideal-tabs > span {{
      color: var(--muted);
      font-size: .8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .1em;
    }}
    .ideal-tabs > div {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .ideal-tab {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 9px 15px;
      background: transparent;
      color: var(--ink);
      font: inherit;
      font-size: .84rem;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
    }}
    .ideal-tab.active {{
      border-color: var(--green);
      background: var(--green);
      color: white;
    }}
    .ideal-intro {{ padding: 38px 34px; border-right: 1px solid rgba(255,255,255,.18); }}
    .ideal-intro .eyebrow {{ color: #efb57c; }}
    .ideal-intro h2 {{
      margin: 12px 0;
      font: 500 clamp(2rem, 4vw, 3.4rem)/1.02 Georgia, serif;
      letter-spacing: -.03em;
    }}
    .ideal-intro p {{ color: rgba(255,255,255,.72); line-height: 1.6; }}
    .ideal-meta {{
      margin-top: 34px;
      padding-top: 18px;
      border-top: 1px solid rgba(255,255,255,.18);
    }}
    .ideal-meta span {{ display: block; color: rgba(255,255,255,.62); font-size: .76rem; }}
    .ideal-meta strong {{ display: block; margin-top: 4px; font: 500 1.5rem Georgia, serif; }}
    .ideal-response {{ padding: 34px 38px 40px; background: #fffdf7; color: var(--ink); }}
    .ideal-response .farmer-copy {{ max-width: 820px; }}
    .toolbar input {{
      width: min(420px, 100%);
      padding: 13px 16px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255,255,255,.62);
      color: var(--ink);
      font: inherit;
    }}
    .toolbar small {{ color: var(--muted); }}
    .case-card {{
      margin: 0 0 36px;
      background: rgba(255,253,247,.82);
      border: 1px solid var(--line);
      border-radius: 22px;
      overflow: hidden;
      box-shadow: var(--shadow);
    }}
    .case-header {{
      padding: 26px 30px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
      align-items: end;
      border-bottom: 1px solid var(--line);
    }}
    .case-header h2 {{ margin: 4px 0; font-family: Georgia, serif; font-size: 2rem; }}
    .case-header p {{ margin: 0; color: var(--muted); }}
    .reduction {{ text-align: right; }}
    .reduction strong {{ display: block; color: var(--green); font: 600 2rem Georgia, serif; }}
    .reduction span {{ color: var(--muted); font-size: .84rem; }}
    .comparison-grid {{ display: grid; grid-template-columns: 1fr 1fr; }}
    .response-panel {{ min-width: 0; padding: 28px 30px 32px; }}
    .response-panel + .response-panel {{ border-left: 1px solid var(--line); }}
    .technical {{ background: var(--technical); }}
    .farmer {{ background: var(--card); }}
    .panel-heading {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 20px;
    }}
    .panel-heading > div {{ display: flex; align-items: center; gap: 10px; }}
    .panel-heading h3 {{ margin: 0; font-size: 1rem; }}
    .panel-number {{ color: var(--ochre); font: 700 .72rem monospace; }}
    .copy-button {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 12px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }}
    pre {{
      margin: 0;
      max-height: 520px;
      overflow: auto;
      white-space: pre-wrap;
      font: .86rem/1.65 ui-monospace, SFMono-Regular, Consolas, monospace;
      color: #4f5851;
    }}
    .farmer-copy {{ font-size: 1rem; line-height: 1.65; }}
    .farmer-copy h2, .farmer-copy h3, .farmer-copy h4 {{
      margin: 1.15em 0 .35em;
      color: var(--green);
      font-family: Georgia, serif;
      line-height: 1.15;
    }}
    .farmer-copy h2:first-child, .farmer-copy h3:first-child {{ margin-top: 0; }}
    .farmer-copy p {{ margin: .45em 0; }}
    .farmer-copy ul {{ padding-left: 1.25rem; }}
    .farmer-copy li {{ margin: .5em 0; }}
    .quality-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }}
    .check {{ padding: 7px 10px; border-radius: 999px; font-size: .75rem; }}
    .pass {{ color: var(--green); background: var(--green-soft); }}
    .warn {{ color: #7c421b; background: #f5dfcb; }}
    footer {{
      margin-top: 64px;
      padding: 28px 0 46px;
      display: flex;
      justify-content: space-between;
      gap: 24px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: .82rem;
    }}
    @media (max-width: 850px) {{
      .hero, .comparison-grid, .ideal-card {{ grid-template-columns: 1fr; }}
      .hero {{ padding-top: 48px; gap: 18px; }}
      .ideal-intro {{ border-right: 0; border-bottom: 1px solid rgba(255,255,255,.18); }}
      .response-panel + .response-panel {{ border-left: 0; border-top: 1px solid var(--line); }}
      .case-header, .toolbar, footer, .ideal-tabs {{ align-items: flex-start; flex-direction: column; }}
      .reduction {{ text-align: left; }}
    }}
  </style>
</head>
<body>
  <script>document.documentElement.classList.add("js-enabled");</script>
  <main class="page-shell">
    <section class="hero">
      <div>
        <span class="kicker">Farmer communication prototype</span>
        <h1>From climate evidence to field action.</h1>
        <p>Side-by-side comparisons show how a fixed vocabulary and structured rewrite make technical watershed advice easier to follow.</p>
      </div>
      <div class="hero-note">
        The left side preserves the saved model response. The right side keeps its decision and warnings, but removes the scientific audit trail.
      </div>
    </section>
    {ideal_navigation}
    {ideal_section}
    <div class="toolbar">
      <input id="search" type="search" placeholder="Filter by watershed or variable…">
      <small>{len(dataset['comparisons'])} examples · generated with {model}</small>
    </div>
    <section id="cases">
      {''.join(cards)}
    </section>
    <footer>
      <span>Vocabulary version {html.escape(dataset['vocabulary_version'])}</span>
      <span>Generated {generated}</span>
    </footer>
  </main>
  <script>
    const search = document.getElementById("search");
    search.addEventListener("input", () => {{
      const query = search.value.trim().toLowerCase();
      document.querySelectorAll(".case-card").forEach(card => {{
        card.hidden = query && !card.dataset.search.includes(query);
      }});
    }});
    document.querySelectorAll(".ideal-tab").forEach(button => {{
      button.addEventListener("click", event => {{
        event.preventDefault();
        document.querySelectorAll(".ideal-tab").forEach(tab => {{
          const selected = tab === button;
          tab.classList.toggle("active", selected);
          tab.setAttribute("aria-selected", selected ? "true" : "false");
        }});
        document.querySelectorAll(".ideal-card").forEach(card => {{
          const selected = card.id === button.dataset.idealTarget;
          card.classList.toggle("active", selected);
        }});
        history.replaceState(null, "", "#" + button.dataset.idealTarget);
        document.getElementById(button.dataset.idealTarget).scrollIntoView({{
          behavior: "auto",
          block: "start"
        }});
      }});
    }});
    const requestedCard = location.hash.slice(1);
    const requestedTab = document.querySelector(`[data-ideal-target="${{requestedCard}}"]`);
    if (requestedTab) requestedTab.click();
    document.querySelectorAll(".copy-button").forEach(button => {{
      button.addEventListener("click", async () => {{
        const target = document.getElementById(button.dataset.copy);
        await navigator.clipboard.writeText(target.innerText);
        const previous = button.textContent;
        button.textContent = "Copied";
        setTimeout(() => button.textContent = previous, 1200);
      }});
    }});
  </script>
</body>
</html>
"""


def build_technical_simple_html(dataset: dict[str, Any]) -> str:
    """Build a focused page containing only technical and simplified responses."""
    comparisons = {
        item["watershed_id"]: item
        for item in dataset.get("comparisons", [])
    }
    ideals = dataset.get("ideal_examples", [])
    pairs = [
        (comparisons[ideal["watershed_id"]], ideal)
        for ideal in ideals
        if ideal["watershed_id"] in comparisons
    ]
    tabs = "\n".join(
        (
            f'<a class="tab{" active" if index == 0 else ""}" '
            f'href="#case-{index}" data-target="case-{index}">'
            f'{html.escape(ideal["watershed_id"])}</a>'
        )
        for index, (_, ideal) in enumerate(pairs)
    )
    cases = []
    for index, (technical, ideal) in enumerate(pairs):
        technical_html = markdown_to_html(repair_mojibake(technical["original_response"]))
        simple_html = markdown_to_html(ideal["response_markdown"])
        cases.append(
            f"""
    <section id="case-{index}" class="response-case{" active" if index == 0 else ""}">
      <header class="case-title">
        <span>Watershed</span>
        <h2>{html.escape(ideal["watershed_id"])}</h2>
      </header>
      <div class="pair-grid">
        <article class="panel technical-panel">
          <div class="panel-title">
            <h3>Technical response</h3>
            <button class="copy" data-copy="technical-{index}">Copy</button>
          </div>
          <div id="technical-{index}" class="response-content">{technical_html}</div>
        </article>
        <article class="panel simple-panel">
          <div class="panel-title">
            <h3>Simplified response</h3>
            <button class="copy" data-copy="simple-{index}">Copy</button>
          </div>
          <div id="simple-{index}" class="response-content">{simple_html}</div>
        </article>
      </div>
    </section>
"""
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Technical and simplified watershed responses</title>
  <style>
    :root {{
      --ink: #17211b;
      --muted: #69736c;
      --paper: #f5f1e7;
      --card: #fffdf8;
      --technical: #ece8df;
      --line: #d8d1c2;
      --green: #245c3b;
      --orange: #b96b2d;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: var(--paper);
      font-family: Inter, "Segoe UI", Arial, sans-serif;
    }}
    .shell {{ width: min(1580px, calc(100% - 32px)); margin: 0 auto; }}
    .topbar {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 28px;
      padding: 30px 0 20px;
      border-bottom: 1px solid var(--line);
    }}
    .topbar p {{
      margin: 0 0 5px;
      color: var(--orange);
      font-size: .72rem;
      font-weight: 800;
      letter-spacing: .14em;
      text-transform: uppercase;
    }}
    h1 {{ margin: 0; font: 500 clamp(2rem, 4vw, 3.6rem)/1 Georgia, serif; }}
    .tabs {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .tab {{
      padding: 9px 15px;
      border: 1px solid var(--line);
      border-radius: 999px;
      color: var(--ink);
      font-size: .84rem;
      font-weight: 700;
      text-decoration: none;
    }}
    .tab.active {{ border-color: var(--green); color: white; background: var(--green); }}
    .response-case {{ margin: 24px 0 36px; }}
    .js-enabled .response-case:not(.active) {{ display: none; }}
    .case-title {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }}
    .case-title span {{ color: var(--muted); font-size: .75rem; text-transform: uppercase; letter-spacing: .1em; }}
    .case-title h2 {{ margin: 0; font: 500 1.7rem Georgia, serif; }}
    .pair-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      border: 1px solid var(--line);
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 15px 45px rgba(44, 52, 44, .08);
    }}
    .panel {{ min-width: 0; }}
    .technical-panel {{ background: var(--technical); }}
    .simple-panel {{ background: var(--card); border-left: 1px solid var(--line); }}
    .panel-title {{
      position: sticky;
      top: 0;
      z-index: 2;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
      background: inherit;
    }}
    .panel-title h3 {{ margin: 0; font-size: .98rem; }}
    .copy {{
      padding: 7px 12px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
    }}
    .response-content {{
      height: calc(100vh - 210px);
      min-height: 560px;
      overflow: auto;
      padding: 24px 28px 42px;
      font-size: .94rem;
      line-height: 1.68;
    }}
    .response-content h2, .response-content h3, .response-content h4 {{
      margin: 1.35em 0 .45em;
      color: var(--green);
      font-family: Georgia, serif;
      line-height: 1.18;
    }}
    .response-content h2:first-child, .response-content h3:first-child {{ margin-top: 0; }}
    .response-content p {{ margin: .65em 0; }}
    .response-content ul {{ padding-left: 1.3rem; }}
    .response-content li {{ margin: .5em 0; }}
    @media (max-width: 860px) {{
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      .pair-grid {{ grid-template-columns: 1fr; }}
      .simple-panel {{ border-left: 0; border-top: 1px solid var(--line); }}
      .response-content {{ height: auto; min-height: 0; max-height: none; }}
    }}
  </style>
</head>
<body>
  <script>document.documentElement.classList.add("js-enabled");</script>
  <main class="shell">
    <header class="topbar">
      <div>
        <p>Response comparison</p>
        <h1>Technical and simplified</h1>
      </div>
      <nav class="tabs" aria-label="Choose watershed">
        {tabs}
      </nav>
    </header>
    {''.join(cases)}
  </main>
  <script>
    document.querySelectorAll(".tab").forEach(tab => {{
      tab.addEventListener("click", event => {{
        event.preventDefault();
        document.querySelectorAll(".tab").forEach(item => {{
          item.classList.toggle("active", item === tab);
        }});
        document.querySelectorAll(".response-case").forEach(item => {{
          item.classList.toggle("active", item.id === tab.dataset.target);
        }});
        history.replaceState(null, "", "#" + tab.dataset.target);
      }});
    }});
    const requested = document.querySelector(`[data-target="${{location.hash.slice(1)}}"]`);
    if (requested) requested.click();
    document.querySelectorAll(".copy").forEach(button => {{
      button.addEventListener("click", async () => {{
        await navigator.clipboard.writeText(document.getElementById(button.dataset.copy).innerText);
        button.textContent = "Copied";
        setTimeout(() => button.textContent = "Copy", 1200);
      }});
    }});
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="*", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--vocabulary", type=Path, default=DEFAULT_VOCABULARY)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--output-html", type=Path, default=DEFAULT_OUTPUT_HTML)
    parser.add_argument(
        "--ideal-examples",
        nargs="+",
        type=Path,
        default=DEFAULT_IDEAL_EXAMPLES,
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Add the ideal example and rebuild HTML from the existing output JSON without calling Ollama.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.render_only:
        dataset = read_json(args.output_json)
        dataset.pop("ideal_example", None)
        dataset["ideal_examples"] = [read_json(path) for path in args.ideal_examples]
        with args.output_json.open("w", encoding="utf-8") as handle:
            json.dump(dataset, handle, ensure_ascii=False, indent=2)
        args.output_html.write_text(build_technical_simple_html(dataset), encoding="utf-8")
        print(f"Updated {args.output_json}")
        print(f"Updated {args.output_html}")
        return

    vocabulary = read_json(args.vocabulary)
    comparisons = []
    for path in args.inputs:
        print(f"Simplifying {path}...", flush=True)
        source = read_json(path)
        simplified = simplify(source, vocabulary, args.model, args.ollama_url)
        comparisons.append(make_record(path, source, simplified, vocabulary))

    dataset = {
        "schema_version": "1.0",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "model": args.model,
        "vocabulary_file": args.vocabulary.as_posix(),
        "vocabulary_version": vocabulary["version"],
        "ideal_examples": [read_json(path) for path in args.ideal_examples],
        "comparisons": comparisons,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, indent=2)
    args.output_html.write_text(build_technical_simple_html(dataset), encoding="utf-8")
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_html}")


if __name__ == "__main__":
    main()
