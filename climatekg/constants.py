"""Single tuning surface for ClimateKG indexing and querying.

Change pipeline models, reasoning levels, thresholds, limits, weights, and
budgets here.  Algorithmic identities (for example, cosine arithmetic), schema
enumerations, and serialization format versions remain beside their code.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .environment import environment_value


# ``validated`` is the smallest profile that retained the required structures
# in the three-paper cross-check. ``baseline`` preserves the original levels;
# ``no`` remains available only for controlled ablations.
REASONING_PROFILE = "validated"
ALLOWED_REASONING_LEVELS = {"no", "low", "medium", "high"}

GENERATION_MODEL = "qwen3.6:27b"
EMBEDDING_MODEL = "qwen3-embedding:4b"
EMBEDDING_DIMENSION = 2048
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_REQUEST_TIMEOUT_SECONDS = 1800
OLLAMA_CONTEXT_TOKENS = 32768
OLLAMA_RETRIES = 2
OLLAMA_RETRY_BACKOFF_BASE_SECONDS = 2
TOKEN_ESTIMATE_CHARACTERS_PER_TOKEN = 3.5
ROUTING_TOKENIZER_ENCODING = "o200k_base"
FILE_HASH_CHUNK_BYTES = 1024 * 1024

PROMPT_VERSIONS = {
    "small_paper_extraction": "v4.3",
    "paper_map": "v13",
    "map_consolidation": "v13",
    "paper_map_candidate": "v13",
    "map_consolidation_candidate": "v13",
    "section_scout": "v4",
    "query_parse": "v3",
    "final_synthesis": "v4",
}

BASELINE_INDEXING_REASONING = {
    "small_paper_extraction": "low",
    "paper_map": "low",
    "section_scout": "no",
    "map_consolidation": "low",
    "paper_map_reference_id_repair": "no",
    "paper_map_reference_repair": "low",
    "facet_extraction": "no",
    "facet_reference_repair": "no",
    "claim_extraction": "low",
    "claim_reference_repair": "low",
    "context_reconciliation": "medium",
    "context_reconciliation_reference_repair": "medium",
    "paper_consolidation": "medium",
    "state_adjudication": "low",
}

BASELINE_QUERY_REASONING = {
    "query_parse": "no",
    "query_parse_context_repair": "no",
    "final_synthesis": "low",
    "final_synthesis_complex": "medium",
}

VALIDATED_INDEXING_REASONING = {
    "small_paper_extraction": "no",
    "paper_map": "medium",
    "section_scout": "no",
    "map_consolidation": "medium",
    "paper_map_reference_id_repair": "no",
    "paper_map_reference_repair": "medium",
    "facet_extraction": "no",
    "facet_reference_repair": "no",
    "claim_extraction": "no",
    "claim_reference_repair": "no",
    "context_reconciliation": "no",
    "context_reconciliation_reference_repair": "no",
    "paper_consolidation": "no",
    "state_adjudication": "no",
}

VALIDATED_QUERY_REASONING = BASELINE_QUERY_REASONING


def _reasoning(stage: str, baseline: dict[str, str], validated: dict[str, str]) -> str:
    if REASONING_PROFILE == "no":
        return "no"
    if REASONING_PROFILE == "baseline":
        value = baseline[stage]
    elif REASONING_PROFILE == "validated":
        value = validated[stage]
    else:
        raise ValueError(f"Unknown REASONING_PROFILE: {REASONING_PROFILE}")
    if value not in ALLOWED_REASONING_LEVELS:
        raise ValueError(f"Invalid reasoning level for {stage}: {value}")
    return value


def _stage(
    stage: str,
    temperature: float,
    baseline: dict[str, str],
    validated: dict[str, str],
    retries: int = OLLAMA_RETRIES,
) -> dict[str, Any]:
    return {
        "temperature": temperature,
        "thinking": _reasoning(stage, baseline, validated),
        "retries": retries,
    }


def _stages(
    baseline: dict[str, str],
    validated: dict[str, str],
    temperatures: dict[str, float],
    retry_overrides: dict[str, int],
) -> dict[str, dict[str, Any]]:
    return {
        name: _stage(
            name,
            temperatures.get(name, 0.0),
            baseline,
            validated,
            retry_overrides.get(name, OLLAMA_RETRIES),
        )
        for name in baseline
    }


INDEXING_PIPELINE: dict[str, Any] = {
    "parsing": {
        "model": "nvidia/NVIDIA-Nemotron-Parse-v1.2",
        "model_path": "climatekg/runtime/cache/nemotron_parse_v1_2",
        "nemotron_python": "E:/Atharv/lulc_suggestor_poc/hipporag copy 3/.venv-nemotron/Scripts/python.exe",
        "pdfium_python": "C:/Users/DELL/.codex/venvs/mineru_py313/Scripts/python.exe",
        "render_dpi": 200,
        "render_timeout_seconds": 1800,
        "parse_timeout_seconds": 7200,
        "page_top_fraction": 0.12,
        "page_bottom_fraction": 0.88,
        "minimum_parsed_characters": 100,
    },
    "paper_mapping": {
        "combined_extraction_enabled": False,
        # 8K is the preferred size for the combined experiment, not a hard
        # eligibility boundary. The safety limit reserves at least half of the
        # 32K window for instructions, schema, reasoning, and generated JSON.
        "combined_extraction_target_tokens": 8000,
        "combined_extraction_max_cleaned_tokens": 16000,
        "whole_paper_threshold_tokens": 15000,
        "map_consolidation_source_budget_tokens": 9000,
        "evidence_input_budget_tokens": 18000,
        "hard_llm_input_budget_tokens": 24000,
    },
    "ollama": {
        "model": GENERATION_MODEL,
        "base_url": OLLAMA_BASE_URL,
        "request_timeout_seconds": OLLAMA_REQUEST_TIMEOUT_SECONDS,
        "context_tokens": OLLAMA_CONTEXT_TOKENS,
        "retries": OLLAMA_RETRIES,
        "retry_backoff_base_seconds": OLLAMA_RETRY_BACKOFF_BASE_SECONDS,
        "final_repair_retries": 0,
        "structured_output": True,
        "reasoning_profile": REASONING_PROFILE,
        "stages": _stages(
            BASELINE_INDEXING_REASONING,
            VALIDATED_INDEXING_REASONING,
            temperatures={"paper_map": 0.1},
            retry_overrides={
                "paper_map_reference_id_repair": 0,
                "paper_map_reference_repair": 1,
                "facet_reference_repair": 1,
                "claim_reference_repair": 1,
            },
        ),
    },
    "embeddings": {
        "model": EMBEDDING_MODEL,
        "dimension": EMBEDDING_DIMENSION,
        "normalize": True,
        "block_embeddings": True,
    },
    "blocks": {
        "max_block_tokens": 1500,
        "target_split_tokens": 1100,
    },
    "source_cleaning": {
        "repeated_margin_min_pages": 2,
        "repeated_margin_page_fraction": 0.60,
        "margin_line_min_characters": 2,
        "margin_line_max_characters": 150,
        "heading_font_size_factor": 1.15,
        "heading_max_lines": 2,
        "heading_max_words": 14,
        "body_font_sample_min_characters": 80,
        "fallback_body_font_size": 10.0,
    },
    "paper_metadata": {
        "title_max_characters": 500,
        "sample_source_blocks": 30,
    },
    "section_scout": {
        "target_tokens": 6500,
        "min_tokens": 3500,
        "max_tokens": 8000,
    },
    "evidence_retrieval": {
        "lexical_top_k": 10,
        "semantic_top_k": 10,
        "neighbor_blocks_each_side": 1,
        "max_context_bundle_blocks": 80,
        "bm25_k1": 1.5,
        "bm25_b": 0.75,
    },
    "consolidation": {
        "facet_notion_candidate_cosine": 0.82,
        "facet_content_candidate_cosine": 0.88,
        "claim_endpoint_candidate_cosine": 0.88,
        "max_context_reconciliation_rounds": 2,
    },
    "enrichment": {
        "backend": "earth_engine",
        "algorithm_version": "spatial_enrichment_v2",
        "earth_engine_project": environment_value("EARTH_ENGINE_PROJECT"),
        "watershed_registry_path": environment_value("CLIMATEKG_WATERSHED_REGISTRY")
        or "E:/Atharv/lulc_suggestor_poc/13jul/assets/watershed_pan_india_simplified.geojson",
        "geocoding": {
            "provider": "nominatim",
            "endpoint": environment_value("CLIMATEKG_GEOCODER_URL") or "https://nominatim.openstreetmap.org",
            "user_agent": environment_value("CLIMATEKG_GEOCODER_USER_AGENT")
            or "ClimateKG/0.1 (https://github.com/atharvadabli)",
            "cache_path": "climatekg/runtime/cache/geocoding/nominatim.json",
            "minimum_interval_seconds": 1.1,
            "result_limit": 10,
            "timeout_seconds": 30,
        },
        "min_valid_polygon_coverage": 0.80,
        "max_local_enrichment_area_sqkm": 1_000_000,
        "max_native_land_cover_pixels": 250_000_000,
        "max_native_terrain_pixels": 500_000_000,
        "wind_directional_persistence_threshold": 0.55,
        "reference_period": {"start": "1991-01-01", "end": "2021-01-01", "label": "1991-2020"},
        "datasets": {
            "climate_regime": {
                "id": "Global_1986-2010_KG_5m.kmz.zip",
                "version": "Kottek et al. (2006), updated 1986-2010 normals (2017 release)",
                "scale_m": 9276.6,
                "temporal_window": "1986-2010",
                "source_path": environment_value("KOPPEN_GEIGER_SOURCE")
                or "E:/Atharv/lulc_suggestor_poc/13jul/assets/Global_1986-2010_KG_5m.kmz.zip",
            },
            "aridity": {"id": "IDAHO_EPSCOR/TERRACLIMATE", "version": "Earth Engine catalog", "scale_m": 4638.3},
            "wind": {"id": "ECMWF/ERA5_LAND/MONTHLY_AGGR", "version": "Earth Engine monthly aggregates", "scale_m": 11132},
            "terrain": {"id": "USGS/SRTMGL1_003", "version": "SRTM V3", "scale_m": 30},
            "land_cover": {"id": "ESA/WorldCover/v200", "version": "2021 v200", "scale_m": 10},
        },
        "seasons": {"DJF": [12, 1, 2], "MAM": [3, 4, 5], "JJA": [6, 7, 8], "SON": [9, 10, 11]},
    },
    "graph": {
        "neo4j_uri": "bolt://localhost:7687",
        "neo4j_http_uri": "http://localhost:7474",
        "database": "neo4j",
        "user": "neo4j",
        "password_env": "NEO4J_PASSWORD",
        "http_timeout_seconds": 300,
        "ann": {
            "backend": "faiss_hnsw",
            "connectivity": 32,
            "ef_construction": 200,
            "ef_search": 128,
        },
    },
    "canonicalization": {
        "state_embedding_top_k": 5,
        "auto_merge_cosine_threshold": None,
    },
}


QUERY_PIPELINE: dict[str, Any] = {
    "ollama": {
        "model": GENERATION_MODEL,
        "base_url": OLLAMA_BASE_URL,
        "request_timeout_seconds": OLLAMA_REQUEST_TIMEOUT_SECONDS,
        "context_tokens": OLLAMA_CONTEXT_TOKENS,
        "retries": OLLAMA_RETRIES,
        "retry_backoff_base_seconds": OLLAMA_RETRY_BACKOFF_BASE_SECONDS,
        "final_repair_retries": 0,
        "structured_output": True,
        "reasoning_profile": REASONING_PROFILE,
        "stages": _stages(
            BASELINE_QUERY_REASONING,
            VALIDATED_QUERY_REASONING,
            temperatures={},
            retry_overrides={"query_parse_context_repair": 1},
        ),
    },
    "embeddings": {
        "model": EMBEDDING_MODEL,
        "dimension": EMBEDDING_DIMENSION,
        "normalize": True,
    },
    "state_mapping": {
        "top_k": 5,
        "seed_top_k": 5,
        "candidate_margin": 0.05,
        "exact_fallback_pool_multiplier": 10,
        "exact_fallback_pool_minimum": 50,
    },
    "context_retrieval": {
        "ann_top_k": 100,
        "rerank_top_k": 30,
        "notion_weight_alpha": 0.35,
        "missing_coverage_penalty_lambda": 0.25,
        "domain_weights": {
            "spatial_configuration": 1.0,
            "land_surface": 1.0,
            "hydrology": 1.0,
            "atmosphere": 1.0,
            "climate": 1.0,
            "substrate_terrain": 1.0,
            "other": 0.5,
        },
        "min_context_score": None,
    },
    "conditioning": {"weight_beta": 0.25, "min_known_conditioning_score": None},
    "mechanism_retrieval": {
        "claim_semantic_top_k": 100,
        "transition_top_k": 50,
        "candidate_claim_top_k": 200,
    },
    "claim_ranking": {
        "weights": {"context": 0.45, "mechanism": 0.20, "intervention": 0.15, "endpoint": 0.20}
    },
    "path_search": {
        "max_path_length": 4,
        "beam_width": 40,
        "max_paths": 20,
        "cross_edge_context_threshold": None,
        "path_length_penalty": 0.08,
        "tie_margin": 0.02,
    },
    "synthesis": {
        "top_paths": 8,
        "max_claims": 24,
        "max_source_blocks_per_claim": 2,
        "evidence_input_budget_tokens": 16000,
        "hard_llm_input_budget_tokens": 20000,
        "complex_min_paths": 4,
        "complex_min_outcome_states": 2,
    },
    "spatial": {
        "directional_persistence_threshold": 0.55,
        "spatial_transfer_min_score": None,
        "sector_quantile": 0.33,
        "terrain_barrier_relief_m": 300,
        "terrain_barrier_search_km": 50,
        "terrain_barrier_min_fraction": 0.5,
        "relation_text_lookbehind_characters": 25,
        "relation_text_lookahead_characters": 15,
    },
    "contradictions": {"per_focal_claim_top_k": 3},
    "evidence_selection": {
        "direct_weight": 0.7,
        "query_weight": 0.3,
        "results_section_bonus": 0.05,
        "discussion_section_bonus": 0.02,
        "section_priority": {"results": 5, "analysis": 5, "discussion": 4, "conclusion": 3, "methods": 2},
    },
    "reporting": {
        "top_contexts": 5,
        "top_claims": 10,
        "top_paths": 5,
    },
}


def indexing_config() -> dict[str, Any]:
    return deepcopy(INDEXING_PIPELINE)


def query_config() -> dict[str, Any]:
    return deepcopy(QUERY_PIPELINE)
