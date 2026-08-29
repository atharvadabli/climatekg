#!/usr/bin/env python3
"""Plain Ollama RAG over parsed markdown papers.

Build:
    python plain_rag.py build

Query:
    python plain_rag.py query "What are the climate effects of afforestation?"
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SOURCE_CSV = Path(r"E:\Atharv\lit_200\parsed_pdfs\parsed_papers.csv")
DEFAULT_KOPPEN_MANIFEST = Path(
    r"E:\Atharv\lulc_suggestor_poc\manuallly_extracting_with_agent\categorized_by_koppen\classification_manifest.csv"
)
DEFAULT_INDEX_DIR = Path("rag_index")
DEFAULT_EMBED_MODEL = "qwen3-embedding:4b"
DEFAULT_CHAT_MODEL = "qwen3.6:27b"
DEFAULT_OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
SKIP_RETRIEVAL_HEADINGS = {
    "references",
    "acknowledgements",
    "acknowledgments",
    "author contributions",
    "competing interests",
    "additional information",
    "data availability",
    "code availability",
}
KOPPEN_CATEGORY_METADATA = {
    "Af_Am_Aw_tropical": {"climate_groups": ["tropical", "monsoon"], "koppen_codes": ["Af", "Am", "Aw"]},
    "BSh_BWh_BWk_dry": {"climate_groups": ["dry", "semi_arid", "arid"], "koppen_codes": ["BSh", "BWh", "BWk"]},
    "Cfa_Cwa_Cfb_temperate": {"climate_groups": ["temperate", "humid_subtropical"], "koppen_codes": ["Cfa", "Cwa", "Cfb"]},
    "Dfa_Dfb_Dwa_continental": {"climate_groups": ["continental", "cold"], "koppen_codes": ["Dfa", "Dfb", "Dwa"]},
    "ET_Dwc_highland": {"climate_groups": ["highland", "cold"], "koppen_codes": ["ET", "Dwc"]},
    "mixed_global_multiple_koppen": {"climate_groups": ["mixed", "global"], "koppen_codes": []},
    "no_study_area_land_use_configuration": {"climate_groups": ["no_study_area"], "koppen_codes": []},
    "no_study_area_land_atmosphere_coupling": {"climate_groups": ["no_study_area"], "koppen_codes": []},
    "no_study_area_review_synthesis": {"climate_groups": ["review", "no_study_area"], "koppen_codes": []},
    "no_study_area_model_methods": {"climate_groups": ["methods", "no_study_area"], "koppen_codes": []},
}
TAG_RULES = {
    "interventions": {
        "afforestation": ["afforestation", "reforestation", "forest restoration", "tree cover", "forestation"],
        "deforestation": ["deforestation", "forest loss", "forest clearing", "forest conversion"],
        "irrigation": ["irrigation", "irrigated", "canal", "river interlinking"],
        "cropland_expansion": ["cropland expansion", "agricultural expansion", "conversion to cropland", "crop cover"],
        "cropping_practice": ["cover crop", "cropping practice", "crop rotation", "no-till", "tillage"],
        "wetland_restoration": ["wetland", "wetlands", "marsh", "sudd"],
        "reservoir_tank": ["reservoir", "tank", "lake", "oasis"],
        "solar_farm": ["solar farm", "photovoltaic", "pv power"],
        "wind_farm": ["wind farm", "wind turbine"],
        "rice_paddy": ["rice paddy", "paddy rice", "paddy field"],
        "greening": ["greening", "leaf area increase", "vegetation increase"],
        "degradation_desertification": ["desertification", "land degradation", "degraded land"],
    },
    "stressors": {
        "extreme_heat": ["extreme heat", "hot extremes", "heatwave", "heat wave", "warming", "temperature rise"],
        "agricultural_drought": ["agricultural drought", "drought", "soil moisture deficit", "water stress"],
        "rainfall_shift": ["rainfall shift", "precipitation change", "monsoon", "rainfall", "precipitation"],
        "flood_peak": ["flood", "runoff", "streamflow", "river flow", "peak flow"],
        "dust_wind": ["dust", "wind erosion", "wind speed", "surface wind"],
    },
    "mechanisms": {
        "evapotranspiration": ["evapotranspiration", "evaporation", "latent heat", "transpiration"],
        "albedo": ["albedo", "surface reflectance", "radiative"],
        "roughness": ["roughness", "surface roughness", "momentum flux"],
        "leaf_area": ["leaf area", "lai", "canopy"],
        "soil_moisture": ["soil moisture", "soil water"],
        "runoff_streamflow": ["runoff", "streamflow", "river flow"],
        "infiltration": ["infiltration", "percolation"],
        "moisture_recycling": ["moisture recycling", "precipitationshed", "atmospheric moisture"],
        "cloud_cover": ["cloud cover", "cloud formation", "cloudiness"],
        "convection": ["convection", "boundary layer", "abl", "convective"],
        "carbon": ["carbon sequestration", "co2", "biogeochemical", "biomass"],
    },
    "regions": {
        "india": ["india", "indian", "rajasthan", "gujarat", "deccan", "western ghats", "indo-gangetic"],
        "south_asia": ["south asia", "south asian", "pakistan", "bangladesh"],
        "sahel": ["sahel", "northern africa", "west africa"],
        "amazon": ["amazon", "brazil"],
        "europe": ["europe", "european"],
        "china": ["china", "north china plain", "jilin"],
        "australia": ["australia", "australian"],
        "himalaya": ["himalaya", "himalayan", "tibetan", "karakoram"],
    },
}
SECTION_INTERVENTIONS = {
    "afforestation": "afforestation",
    "cropland-expansion": "cropland_expansion",
    "cropping-practice": "cropping_practice",
    "deforestation": "deforestation",
    "degradation-desertification": "degradation_desertification",
    "greening": "greening",
    "irrigation": "irrigation",
    "plantation": "afforestation",
    "reservoir-tank": "reservoir_tank",
    "rice-paddy": "rice_paddy",
    "solar-farm": "solar_farm",
    "wetland-restoration": "wetland_restoration",
    "wind-farm": "wind_farm",
}


@dataclass(frozen=True)
class Paper:
    section: str
    paper: str
    pages: str
    markdown: Path


@dataclass(frozen=True)
class Chunk:
    heading: str
    text: str


def post_json(base_url: str, endpoint: str, payload: dict[str, Any], timeout: int = 600) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama HTTP {exc.code} at {endpoint}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Ollama at {base_url}: {exc}") from exc


def embed_texts(base_url: str, model: str, texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts, with a fallback for older Ollama APIs."""
    if not texts:
        return []

    try:
        result = post_json(base_url, "/api/embed", {"model": model, "input": texts})
        embeddings = result.get("embeddings")
        if isinstance(embeddings, list):
            return embeddings
    except RuntimeError as exc:
        if "/api/embed" not in str(exc):
            raise

    embeddings = []
    for text in texts:
        result = post_json(base_url, "/api/embeddings", {"model": model, "prompt": text})
        embedding = result.get("embedding")
        if not isinstance(embedding, list):
            raise RuntimeError(f"Ollama did not return an embedding for model {model!r}.")
        embeddings.append(embedding)
    return embeddings


def chat(base_url: str, model: str, prompt: str) -> str:
    result = post_json(
        base_url,
        "/api/chat",
        {
            "model": model,
            "stream": False,
            "think": False,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You answer questions using only the provided source excerpts. "
                        "Cite sources as [S1], [S2], etc. If the excerpts do not contain "
                        "enough evidence, say what is missing."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=1200,
    )
    message = result.get("message", {})
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Ollama chat response did not contain message.content.")
    if not content.strip():
        raise RuntimeError("Ollama returned an empty answer. Try lowering --top-k or reducing --chunk-words.")
    return content.strip()


def load_papers(source_csv: Path) -> list[Paper]:
    with source_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    papers = []
    for row in rows:
        markdown = Path(row["markdown"])
        if markdown.exists():
            papers.append(
                Paper(
                    section=row.get("section", ""),
                    paper=row.get("paper", markdown.parent.name),
                    pages=row.get("pages", ""),
                    markdown=markdown,
                )
            )
    return papers


def normalize_token(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def load_koppen_manifest(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    if not path.exists():
        return {}

    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            category = row.get("category", "")
            extra = KOPPEN_CATEGORY_METADATA.get(category, {"climate_groups": [], "koppen_codes": []})
            metadata = {
                "koppen_category": category,
                "koppen_confidence": row.get("confidence", ""),
                "koppen_rationale": row.get("rationale", ""),
                "climate_groups": extra["climate_groups"],
                "koppen_codes": extra["koppen_codes"],
            }
            by_key[(row.get("section", ""), row.get("paper", ""))] = metadata
            source_markdown = row.get("source_markdown", "")
            if source_markdown:
                by_key[("markdown", str(Path(source_markdown)).lower())] = metadata
    return by_key


def koppen_for_paper(paper: Paper, manifest: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    return manifest.get(
        (paper.section, paper.paper),
        manifest.get(
            ("markdown", str(paper.markdown).lower()),
            {
                "koppen_category": "",
                "koppen_confidence": "",
                "koppen_rationale": "",
                "climate_groups": [],
                "koppen_codes": [],
            },
        ),
    )


def tag_text(text: str, section: str = "") -> dict[str, list[str]]:
    lowered = text.lower()
    tags: dict[str, list[str]] = {}
    for field, rules in TAG_RULES.items():
        matched = []
        for tag, terms in rules.items():
            if any(term in lowered for term in terms):
                matched.append(tag)
        tags[field] = sorted(set(matched))

    section_intervention = SECTION_INTERVENTIONS.get(section)
    if section_intervention:
        tags["interventions"] = sorted(set(tags["interventions"] + [section_intervention]))
    return tags


def evidence_role(record: dict[str, Any]) -> str:
    category = str(record.get("koppen_category", ""))
    heading = str(record.get("heading", "")).strip().lower()
    paper = str(record.get("paper", "")).lower()
    try:
        pages = int(str(record.get("pages", "0")).strip() or "0")
    except ValueError:
        pages = 0

    if category == "no_study_area_review_synthesis" or "review" in paper:
        return "review_synthesis"
    if category == "no_study_area_model_methods":
        return "methods"
    if category.startswith("no_study_area"):
        return "background_framework"
    if pages >= 60 or "state_of_" in paper or heading in {"contents", "preface"}:
        return "report_or_book"
    return "direct_study"


def enrich_record(record: dict[str, Any], manifest: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    metadata = manifest.get(
        (record.get("section", ""), record.get("paper", "")),
        manifest.get(("markdown", str(record.get("markdown", "")).lower()), {}),
    )
    if metadata:
        record.update(metadata)
    else:
        record.setdefault("koppen_category", "")
        record.setdefault("koppen_confidence", "")
        record.setdefault("koppen_rationale", "")
        record.setdefault("climate_groups", [])
        record.setdefault("koppen_codes", [])

    combined_text = " ".join(
        [
            str(record.get("section", "")),
            str(record.get("paper", "")),
            str(record.get("heading", "")),
            str(record.get("text", "")),
        ]
    )
    for field, values in tag_text(combined_text, str(record.get("section", ""))).items():
        record[field] = values
    record["evidence_role"] = evidence_role(record)
    return record


def clean_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<!--\s*page\s+(\d+)\s*-->", r"\n\n[page \1]\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\u00a0", " ")
    text = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^(#{1,4})\s+(.+?)\s*$", text))
    if not matches:
        return [("Document", text)]

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            sections.append(("Preface", preface))

    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        heading = match.group(2).strip()
        body = text[start:end].strip()
        if body:
            sections.append((heading, body))
    return sections


def chunk_text(text: str, chunk_words: int, overlap_words: int, min_chunk_words: int) -> list[Chunk]:
    section_chunks: list[Chunk] = []
    for heading, section_text in split_markdown_sections(text):
        for chunk in chunk_section(section_text, chunk_words, overlap_words):
            if len(chunk.split()) < min_chunk_words:
                continue
            section_chunks.append(Chunk(heading=heading, text=chunk))
    return section_chunks


def chunk_section(text: str, chunk_words: int, overlap_words: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []

    for paragraph in paragraphs:
        words = paragraph.split()
        if len(words) > chunk_words:
            if current:
                chunks.append(" ".join(current))
                current = []
            step = max(1, chunk_words - overlap_words)
            for start in range(0, len(words), step):
                window = words[start : start + chunk_words]
                if len(window) >= 80:
                    chunks.append(" ".join(window))
            continue

        if len(current) + len(words) > chunk_words and current:
            chunks.append(" ".join(current))
            current = current[-overlap_words:] if overlap_words else []
        current.extend(words)

    if current:
        chunks.append(" ".join(current))
    return chunks


def batched(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def vector_norm(vector: list[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def cosine(query: list[float], query_norm: float, doc: list[float], doc_norm: float) -> float:
    if query_norm == 0 or doc_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(query, doc)) / (query_norm * doc_norm)


def values_from_args(values: list[str] | None) -> set[str]:
    output: set[str] = set()
    for value in values or []:
        for part in re.split(r"[,;]", value):
            if part.strip():
                output.add(normalize_token(part))
    return output


def query_metadata(args: argparse.Namespace, question: str) -> dict[str, set[str]]:
    inferred = tag_text(question)
    metadata = {
        "interventions": set(inferred["interventions"]) | values_from_args(getattr(args, "intervention", None)),
        "stressors": set(inferred["stressors"]) | values_from_args(getattr(args, "stressor", None)),
        "mechanisms": set(inferred["mechanisms"]) | values_from_args(getattr(args, "mechanism", None)),
        "regions": set(inferred["regions"]) | values_from_args(getattr(args, "region", None)),
        "climate_groups": values_from_args(getattr(args, "climate_group", None)),
        "koppen_categories": set(getattr(args, "climate_category", None) or []),
        "koppen_codes": values_from_args(getattr(args, "koppen_code", None)),
    }
    return metadata


def has_any(record: dict[str, Any], field: str, wanted: set[str]) -> bool:
    if not wanted:
        return True
    existing = {normalize_token(str(value)) for value in record.get(field, [])}
    return bool(existing & wanted)


def metadata_adjustment(record: dict[str, Any], wanted: dict[str, set[str]]) -> tuple[float, list[str]]:
    boost = 0.0
    reasons: list[str] = []

    weighted_fields = [
        ("interventions", 0.10),
        ("stressors", 0.10),
        ("mechanisms", 0.08),
        ("regions", 0.07),
        ("climate_groups", 0.12),
        ("koppen_codes", 0.12),
    ]
    for field, weight in weighted_fields:
        if wanted[field] and has_any(record, field, wanted[field]):
            boost += weight
            reasons.append(f"{field}+{weight:.2f}")

    if wanted["koppen_categories"] and record.get("koppen_category") in wanted["koppen_categories"]:
        boost += 0.12
        reasons.append("koppen_category+0.12")

    category = str(record.get("koppen_category", ""))
    confidence = str(record.get("koppen_confidence", "")).lower()
    climate_groups = {normalize_token(str(value)) for value in record.get("climate_groups", [])}
    if category == "mixed_global_multiple_koppen":
        boost += 0.03
        reasons.append("mixed_global+0.03")
    if "review" in climate_groups or category.startswith("no_study_area"):
        boost -= 0.08
        reasons.append("no_study_area_or_review-0.08")
    if confidence == "low":
        boost -= 0.04
        reasons.append("low_confidence-0.04")
    if (
        ("india" in wanted["regions"] or "south_asia" in wanted["regions"])
        and climate_groups & {"cold", "continental", "highland"}
        and "himalaya" not in wanted["regions"]
    ):
        boost -= 0.20
        reasons.append("cold_or_highland_india_mismatch-0.20")
    if wanted["regions"]:
        record_regions = {normalize_token(str(value)) for value in record.get("regions", [])}
        if record_regions and not (record_regions & wanted["regions"]):
            boost -= 0.08
            reasons.append("region_mismatch-0.08")

    role = str(record.get("evidence_role", ""))
    if role == "direct_study":
        boost += 0.04
        reasons.append("direct_study+0.04")
    elif role == "report_or_book":
        boost -= 0.12
        reasons.append("report_or_book-0.12")
    elif role in {"review_synthesis", "methods", "background_framework"}:
        boost -= 0.08
        reasons.append(f"{role}-0.08")
    return boost, reasons


def passes_strict_filters(record: dict[str, Any], wanted: dict[str, set[str]], args: argparse.Namespace) -> bool:
    for arg_name, field in [
        ("strict_intervention", "interventions"),
        ("strict_stressor", "stressors"),
        ("strict_mechanism", "mechanisms"),
        ("strict_region", "regions"),
        ("strict_climate", "climate_groups"),
    ]:
        if getattr(args, arg_name, False) and not has_any(record, field, wanted[field]):
            return False

    if getattr(args, "exclude_cold", False):
        climate_groups = {normalize_token(str(value)) for value in record.get("climate_groups", [])}
        if climate_groups & {"cold", "continental", "highland"}:
            return False
    return True


def build_index(args: argparse.Namespace) -> None:
    source_csv = Path(args.source_csv)
    koppen_manifest = load_koppen_manifest(Path(args.koppen_manifest))
    index_dir = Path(args.index_dir)
    chunks_path = index_dir / "chunks.jsonl"
    meta_path = index_dir / "meta.json"

    papers = load_papers(source_csv)
    if not papers:
        raise SystemExit(f"No readable markdown files found from {source_csv}")

    records: list[dict[str, Any]] = []
    for paper in papers:
        paper_koppen = koppen_for_paper(paper, koppen_manifest)
        raw_text = paper.markdown.read_text(encoding="utf-8", errors="replace")
        text = clean_markdown(raw_text)
        for idx, chunk in enumerate(chunk_text(text, args.chunk_words, args.overlap_words, args.min_chunk_words), start=1):
            record = {
                "id": f"{paper.section}/{paper.paper}#{idx}",
                "section": paper.section,
                "paper": paper.paper,
                "heading": chunk.heading,
                "pages": paper.pages,
                "markdown": str(paper.markdown),
                "chunk_index": idx,
                "text": chunk.text,
                **paper_koppen,
            }
            records.append(enrich_record(record, koppen_manifest))

    index_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    embedded = 0
    with chunks_path.open("w", encoding="utf-8") as handle:
        for batch in batched(records, args.batch_size):
            vectors = embed_texts(args.ollama_url, args.embed_model, [record["text"] for record in batch])
            for record, vector in zip(batch, vectors):
                record["embedding"] = vector
                record["norm"] = vector_norm(vector)
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            embedded += len(batch)
            print(f"embedded {embedded}/{len(records)} chunks", flush=True)

    meta = {
        "source_csv": str(source_csv),
        "paper_count": len(papers),
        "chunk_count": len(records),
        "embed_model": args.embed_model,
        "chunk_words": args.chunk_words,
        "overlap_words": args.overlap_words,
        "min_chunk_words": args.min_chunk_words,
        "koppen_manifest": str(Path(args.koppen_manifest)),
        "created_at_epoch": int(time.time()),
        "seconds": round(time.time() - started, 2),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {chunks_path}")
    print(f"wrote {meta_path}")


def enrich_index(args: argparse.Namespace) -> None:
    index_dir = Path(args.index_dir)
    chunks_path = index_dir / "chunks.jsonl"
    tmp_path = index_dir / "chunks.enriched.tmp.jsonl"
    meta_path = index_dir / "meta.json"
    if not chunks_path.exists():
        raise SystemExit(f"Index not found at {chunks_path}. Run: python plain_rag.py build")

    manifest = load_koppen_manifest(Path(args.koppen_manifest))
    updated = 0
    with chunks_path.open("r", encoding="utf-8") as source, tmp_path.open("w", encoding="utf-8") as dest:
        for line in source:
            if not line.strip():
                continue
            record = enrich_record(json.loads(line), manifest)
            dest.write(json.dumps(record, ensure_ascii=False) + "\n")
            updated += 1
    tmp_path.replace(chunks_path)

    meta = {}
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["koppen_manifest"] = str(Path(args.koppen_manifest))
    meta["metadata_enriched_at_epoch"] = int(time.time())
    meta["metadata_enriched_chunk_count"] = updated
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"enriched {updated} chunks in {chunks_path}")
    print(f"updated {meta_path}")


def load_index(index_dir: Path) -> list[dict[str, Any]]:
    chunks_path = index_dir / "chunks.jsonl"
    if not chunks_path.exists():
        raise SystemExit(f"Index not found at {chunks_path}. Run: python plain_rag.py build")
    with chunks_path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def retrieve(args: argparse.Namespace, question: str) -> list[dict[str, Any]]:
    records = load_index(Path(args.index_dir))
    wanted = query_metadata(args, question)
    query_vector = embed_texts(args.ollama_url, args.embed_model, [question])[0]
    query_norm = vector_norm(query_vector)
    scored = []
    for record in records:
        heading = str(record.get("heading", "")).strip().lower()
        if (
            heading in SKIP_RETRIEVAL_HEADINGS
            or re.match(r"^\d+\.\s+", heading)
            or " doi" in heading
            or " et al" in heading
        ):
            continue
        if not passes_strict_filters(record, wanted, args):
            continue
        vector_score = cosine(query_vector, query_norm, record["embedding"], record.get("norm", 0.0))
        metadata_boost, metadata_reasons = metadata_adjustment(record, wanted)
        score = vector_score + metadata_boost
        scored.append((score, vector_score, metadata_boost, metadata_reasons, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, vector_score, metadata_boost, metadata_reasons, record in scored[: args.top_k]:
        result = dict(record)
        result["score"] = score
        result["vector_score"] = vector_score
        result["metadata_boost"] = metadata_boost
        result["metadata_reasons"] = metadata_reasons
        result.pop("embedding", None)
        results.append(result)
    return results


def print_sources(sources: list[dict[str, Any]]) -> None:
    print("\nSources:")
    for idx, source in enumerate(sources, start=1):
        print(
            f"[S{idx}] score={source['score']:.4f} vector={source.get('vector_score', 0.0):.4f} "
            f"meta={source.get('metadata_boost', 0.0):+.2f} "
            f"section={source['section']} paper={source['paper']} "
            f"koppen={source.get('koppen_category', '')}/{source.get('koppen_confidence', '')} "
            f"role={source.get('evidence_role', '')} "
            f"heading={source.get('heading', 'Document')} "
            f"chunk={source['chunk_index']} path={source['markdown']}"
        )
        reasons = source.get("metadata_reasons") or []
        if reasons:
            print(f"     metadata_reasons={', '.join(reasons)}")
        tags = {
            "interventions": source.get("interventions", []),
            "stressors": source.get("stressors", []),
            "mechanisms": source.get("mechanisms", []),
            "regions": source.get("regions", []),
            "climate_groups": source.get("climate_groups", []),
            "koppen_codes": source.get("koppen_codes", []),
        }
        print("     tags=" + json.dumps(tags, ensure_ascii=False))


def search_index(args: argparse.Namespace) -> None:
    question = " ".join(args.question).strip()
    if not question:
        raise SystemExit("Provide a question.")

    sources = retrieve(args, question)
    print_sources(sources)


def query_index(args: argparse.Namespace) -> None:
    question = " ".join(args.question).strip()
    if not question:
        raise SystemExit("Provide a question.")

    sources = retrieve(args, question)
    context_blocks = []
    for idx, source in enumerate(sources, start=1):
        context_blocks.append(
            "\n".join(
                [
                    (
                        f"[S{idx}] category={source['section']} paper={source['paper']} "
                        f"koppen={source.get('koppen_category', '')} "
                        f"heading={source.get('heading', 'Document')} chunk={source['chunk_index']}"
                    ),
                    source["text"],
                ]
            )
        )

    prompt = (
        f"Question: {question}\n\n"
        "Source excerpts:\n\n"
        + "\n\n".join(context_blocks)
        + "\n\nAnswer with concise synthesis and source citations."
    )
    answer = chat(args.ollama_url, args.chat_model, prompt)
    print(answer)
    print_sources(sources)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plain local RAG over parsed paper markdown files.")
    parser.add_argument("--source-csv", default=str(DEFAULT_SOURCE_CSV))
    parser.add_argument("--koppen-manifest", default=str(DEFAULT_KOPPEN_MANIFEST))
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL)
    parser.add_argument("--chat-model", default=DEFAULT_CHAT_MODEL)

    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Chunk markdown papers and embed them into a local JSONL index.")
    build.add_argument("--chunk-words", type=int, default=750)
    build.add_argument("--overlap-words", type=int, default=120)
    build.add_argument("--min-chunk-words", type=int, default=80)
    build.add_argument("--batch-size", type=int, default=8)
    build.set_defaults(func=build_index)

    enrich = subparsers.add_parser("enrich-index", help="Add metadata tags to an existing index without re-embedding.")
    enrich.set_defaults(func=enrich_index)

    def add_retrieval_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("question", nargs=argparse.REMAINDER)
        command.add_argument("--top-k", type=int, default=3)
        command.add_argument("--intervention", action="append", help="Boost/filter intervention tags, e.g. afforestation.")
        command.add_argument("--stressor", action="append", help="Boost/filter stressor tags, e.g. extreme_heat.")
        command.add_argument("--mechanism", action="append", help="Boost/filter mechanism tags, e.g. evapotranspiration.")
        command.add_argument("--region", action="append", help="Boost/filter region tags, e.g. india or sahel.")
        command.add_argument("--climate-group", action="append", help="Boost/filter climate groups, e.g. dry or monsoon.")
        command.add_argument("--climate-category", action="append", help="Boost exact manifest category, e.g. BSh_BWh_BWk_dry.")
        command.add_argument("--koppen-code", action="append", help="Boost/filter Koppen codes, e.g. BSh.")
        command.add_argument("--strict-intervention", action="store_true")
        command.add_argument("--strict-stressor", action="store_true")
        command.add_argument("--strict-mechanism", action="store_true")
        command.add_argument("--strict-region", action="store_true")
        command.add_argument("--strict-climate", action="store_true")
        command.add_argument("--exclude-cold", action="store_true", help="Hard-exclude cold/continental/highland papers.")

    search = subparsers.add_parser("search", help="Retrieve and print ranked chunks without generating an answer.")
    add_retrieval_options(search)
    search.set_defaults(func=search_index)

    query = subparsers.add_parser("query", help="Retrieve relevant chunks and answer a question.")
    add_retrieval_options(query)
    query.set_defaults(func=query_index)

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    args.func(args)


if __name__ == "__main__":
    main()
