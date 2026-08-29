#!/usr/bin/env python3
"""Run portal-style watershed screening and RAG retrieval.

This script reads the 13jul watershed assets, derives simple stressor/intervention
screening signals, and attaches RAG evidence for fully sampled watersheds.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import plain_rag


PORTAL_ROOT = Path(r"E:\Atharv\lulc_suggestor_poc\13jul")
WATERSHED_FILE = PORTAL_ROOT / "assets" / "watershed_pan_india_simplified.geojson"
METRIC_ROOT = PORTAL_ROOT / "assets" / "coupling_metrics"
OUT_DIR = Path("query_outputs") / "watershed_runs"


def load_csv_by_id(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["wsconc"]: row for row in csv.DictReader(handle)}


def as_float(row: dict[str, str] | None, key: str, default: float = 0.0) -> float:
    if not row:
        return default
    try:
        value = row.get(key, "")
        return float(value) if value != "" else default
    except ValueError:
        return default


def leverage_rank(label: str) -> int:
    if "High" in label or "Strong" in label:
        return 2
    if "Medium" in label or "Moderate" in label:
        return 1
    return 0


def rank_label(rank: int) -> str:
    return ["Low", "Medium", "High"][max(0, min(2, rank))]


def climate_from_aridity(ai: float, regime: str) -> dict[str, list[str] | str]:
    regime_l = regime.lower()
    if ai < 0.2 or "arid" in regime_l and "semi" not in regime_l:
        return {"climate_group": ["dry", "arid"], "koppen_code": ["BWh"]}
    if ai < 0.5 or "semi" in regime_l:
        return {"climate_group": ["dry", "semi_arid"], "koppen_code": ["BSh"]}
    if ai < 0.65 or "sub-humid" in regime_l:
        return {"climate_group": ["dry", "semi_arid"], "koppen_code": ["BSh"]}
    return {"climate_group": ["monsoon", "tropical"], "koppen_code": ["Aw"]}


def possible_changes(
    aridity: dict[str, str] | None,
    ef_proxy: dict[str, str] | None,
    tci_proxy: dict[str, str] | None,
    dtr: dict[str, str] | None,
    true_coupling: dict[str, str] | None,
    ctphi: dict[str, str] | None,
    lulc: dict[str, str] | None,
) -> dict[str, str]:
    ai_rank = leverage_rank(aridity.get("ai_leverage_gate", "")) if aridity else 0
    ef_rank = leverage_rank(ef_proxy.get("ef_proxy_leverage", "")) if ef_proxy else 0
    tci_rank = leverage_rank(tci_proxy.get("tci_proxy_leverage", "")) if tci_proxy else 0
    dtr_rank = leverage_rank(dtr.get("temperature_leverage", "")) if dtr else 0
    if true_coupling:
        true_tci = as_float(true_coupling, "true_tci")
        true_rank = 2 if true_tci >= 25 else 1 if true_tci >= 10 else 0
        tci_rank = max(tci_rank, true_rank)

    temperature = rank_label(round((ai_rank + ef_rank + tci_rank + dtr_rank) / 4))
    humidity = rank_label(round((ef_rank + tci_rank) / 2))

    precip_rank = 0
    if ctphi:
        trigger = as_float(ctphi, "monsoon_triggerable_pct")
        precip_rank = 2 if trigger >= 40 else 1 if trigger >= 20 else 0
        precip_rank = min(precip_rank, max(ai_rank, tci_rank))
    wind_rank = leverage_rank(lulc.get("roughness_change_potential", "")) if lulc else 0

    return {
        "Temperature/LST": temperature,
        "Humidity/VPD": humidity,
        "Precipitation": rank_label(precip_rank),
        "Wind": rank_label(wind_rank),
    }


def classify_stressors(levers: dict[str, str]) -> list[str]:
    stressors = []
    if levers.get("Temperature/LST") in {"Medium", "High"}:
        stressors.append("extreme_heat")
    if levers.get("Humidity/VPD") in {"Medium", "High"}:
        stressors.append("agricultural_drought")
    if levers.get("Precipitation") in {"Medium", "High"}:
        stressors.append("rainfall_shift")
    if levers.get("Wind") in {"Medium", "High"}:
        stressors.append("dust_wind")
    return stressors or ["extreme_heat"]


def candidate_interventions(metrics: dict[str, Any], stressors: list[str]) -> list[str]:
    interventions: list[str] = []
    lulc = metrics.get("lulc")
    aridity = metrics.get("aridity")
    ef_proxy = metrics.get("ef_proxy")
    tci_proxy = metrics.get("tci_proxy")
    ai = as_float(aridity, "aridity_index")
    tree = as_float(lulc, "tree_cover_pct") if lulc else 0.0
    crop = as_float(lulc, "cropland_pct") if lulc else 0.0
    transition = as_float(lulc, "transitionable_pct") if lulc else 0.0
    ef = as_float(ef_proxy, "ef_proxy")
    tci = as_float(tci_proxy, "tci_proxy")

    if "extreme_heat" in stressors:
        if tree < 25 and transition >= 25:
            interventions.append("afforestation")
        if ef < 0.65 and tci >= 15:
            interventions.append("irrigation")
        if crop >= 20:
            interventions.append("cropping_practice")
    if "agricultural_drought" in stressors:
        if crop >= 20:
            interventions.append("cropping_practice")
        if ai >= 0.35 and ef < 0.7:
            interventions.append("irrigation")
        if tree < 20 and transition >= 25:
            interventions.append("afforestation")
    if "rainfall_shift" in stressors:
        interventions.extend(["afforestation", "irrigation"])
    if "dust_wind" in stressors:
        interventions.extend(["afforestation", "cropping_practice"])
    return sorted(set(interventions))


def build_question(ws_id: str, context: dict[str, Any]) -> str:
    stressors = ", ".join(context["stressors"])
    interventions = ", ".join(context["candidate_interventions"])
    climate = ", ".join(context["climate_group"])
    return (
        f"For Indian watershed {ws_id}, climate regime {climate}, aridity regime "
        f"{context['aridity_regime']}, and priority stressors {stressors}, rank candidate "
        f"land-use interventions ({interventions}). For each, give expected direction, "
        "mechanism, caveat, confidence, and source citations."
    )


def ranked_recommendations(context: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = context["metrics"]
    lulc = metrics.get("lulc")
    aridity = metrics.get("aridity")
    ef_proxy = metrics.get("ef_proxy")
    tci_proxy = metrics.get("tci_proxy")
    ctphi = metrics.get("ctphi")
    levers = context["levers"]
    stressors = set(context["stressors"])

    ai = as_float(aridity, "aridity_index")
    ef = as_float(ef_proxy, "ef_proxy")
    tci = as_float(tci_proxy, "tci_proxy")
    tree = as_float(lulc, "tree_cover_pct") if lulc else 0.0
    shrub = as_float(lulc, "shrubland_pct") if lulc else 0.0
    grass = as_float(lulc, "grassland_pct") if lulc else 0.0
    crop = as_float(lulc, "cropland_pct") if lulc else 0.0
    bare = as_float(lulc, "bare_sparse_pct") if lulc else 0.0
    transition = as_float(lulc, "transitionable_pct") if lulc else 0.0
    roughness = lulc.get("roughness_change_potential", "") if lulc else ""
    monsoon_trigger = as_float(ctphi, "monsoon_triggerable_pct")

    rows: list[dict[str, Any]] = []

    if "afforestation" in context["candidate_interventions"]:
        score = 0
        score += 2 if levers["Temperature/LST"] == "High" else 1 if levers["Temperature/LST"] == "Medium" else 0
        score += 2 if levers["Wind"] == "High" else 1 if levers["Wind"] == "Medium" else 0
        score += 1 if monsoon_trigger >= 40 else 0
        score += 1 if tree < 20 else 0
        score += 1 if transition >= 50 else 0
        caveat = "Water-limited setting: avoid dense plantations where ET would reduce blue water; prioritize native/open-canopy agroforestry and shelterbelts."
        if ai >= 0.65:
            caveat = "Humid/monsoon setting: tree cover is more plausible for cooling, but species choice and rainfall/downwind effects still need local validation."
        rows.append(
            {
                "intervention": "afforestation / agroforestry / shelterbelts",
                "rank_score": score,
                "where": f"Transitionable LULC {transition:.0f}%; prioritize low-tree areas, field boundaries, degraded shrub/grass/bare patches, and wind-exposed edges.",
                "expected_effect": "Cooling through shade, roughness, ET, and possible cloud/rainfall feedback; wind/dust reduction where roughness potential is high.",
                "mechanisms": "evapotranspiration; roughness; leaf_area; cloud_cover; albedo caveat",
                "confidence": "Medium" if score >= 4 else "Low-Medium",
                "caveat": caveat,
            }
        )

    if "irrigation" in context["candidate_interventions"]:
        score = 0
        score += 2 if levers["Temperature/LST"] == "High" else 1 if levers["Temperature/LST"] == "Medium" else 0
        score += 2 if levers["Humidity/VPD"] == "High" else 1 if levers["Humidity/VPD"] == "Medium" else 0
        score += 1 if ef < 0.65 else 0
        score += 1 if tci >= 15 else 0
        score += 1 if crop >= 20 else 0
        caveat = "Requires water budget check; can cool daytime heat but may increase humid heat stress or alter monsoon gradients."
        if ai < 0.35:
            caveat = "Strong water constraint: use only water-saving irrigation, farm ponds, recharge, or deficit irrigation after groundwater screening."
        rows.append(
            {
                "intervention": "irrigation efficiency / water spreading / supplemental irrigation",
                "rank_score": score,
                "where": f"Cropland {crop:.0f}%; prioritize existing cropland with high heat/VPD exposure and feasible water storage or recharge.",
                "expected_effect": "Hot-extreme cooling via higher latent heat flux and soil moisture; possible support for rainfed crops through moisture recycling.",
                "mechanisms": "evapotranspiration; soil_moisture; latent_heat; moisture_recycling",
                "confidence": "Medium-High" if score >= 5 else "Medium",
                "caveat": caveat,
            }
        )

    if "cropping_practice" in context["candidate_interventions"]:
        score = 0
        score += 2 if crop >= 30 else 1 if crop >= 15 else 0
        score += 2 if levers["Humidity/VPD"] in {"Medium", "High"} else 0
        score += 1 if levers["Temperature/LST"] in {"Medium", "High"} else 0
        score += 1 if levers["Wind"] in {"Medium", "High"} else 0
        rows.append(
            {
                "intervention": "cropping practice change / cover crops / residue / reduced tillage",
                "rank_score": score,
                "where": f"Cropland {crop:.0f}%; target exposed cropland and erosion-prone fields, especially where shrub+grass+bare is {shrub + grass + bare:.0f}%.",
                "expected_effect": "Improves soil cover and soil moisture buffering; can reduce surface heating and wind erosion where cover is currently low.",
                "mechanisms": "soil_moisture; albedo/cover; roughness; evapotranspiration",
                "confidence": "Medium" if score >= 4 else "Low-Medium",
                "caveat": "Current corpus has less direct local evidence for specific practices than for irrigation/forest-cover effects; crop calendar and farmer constraints matter.",
            }
        )

    rows.sort(key=lambda row: row["rank_score"], reverse=True)
    return rows


def source_summary(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": round(float(source.get("score", 0.0)), 4),
        "vector_score": round(float(source.get("vector_score", 0.0)), 4),
        "metadata_boost": round(float(source.get("metadata_boost", 0.0)), 4),
        "section": source.get("section"),
        "paper": source.get("paper"),
        "heading": source.get("heading"),
        "chunk_index": source.get("chunk_index"),
        "path": source.get("markdown"),
        "koppen_category": source.get("koppen_category"),
        "evidence_role": source.get("evidence_role"),
        "metadata_reasons": source.get("metadata_reasons", []),
    }


def retrieval_args(base: argparse.Namespace, context: dict[str, Any], question: str) -> argparse.Namespace:
    return argparse.Namespace(
        index_dir=base.index_dir,
        ollama_url=base.ollama_url,
        embed_model=base.embed_model,
        top_k=base.top_k,
        intervention=context["candidate_interventions"],
        stressor=context["stressors"],
        mechanism=[],
        region=["india"],
        climate_group=context["climate_group"],
        climate_category=[],
        koppen_code=context["koppen_code"],
        strict_intervention=False,
        strict_stressor=False,
        strict_mechanism=False,
        strict_region=False,
        strict_climate=False,
        exclude_cold=True,
        question=[question],
    )


def make_context(ws_id: str, props: dict[str, Any], metrics: dict[str, dict[str, str] | None]) -> dict[str, Any]:
    aridity = metrics["aridity"]
    levers = possible_changes(
        aridity,
        metrics["ef_proxy"],
        metrics["tci_proxy"],
        metrics["dtr"],
        metrics["true_coupling"],
        metrics["ctphi"],
        metrics["lulc"],
    )
    stressors = classify_stressors(levers)
    ai = as_float(aridity, "aridity_index")
    climate = climate_from_aridity(ai, aridity.get("aridity_regime", "") if aridity else "")
    context = {
        "watershed_id": ws_id,
        "area_sqkm": props.get("area_sqkm"),
        "bacode": props.get("bacode"),
        "sbcode": props.get("sbcode"),
        "aridity_index": ai,
        "aridity_regime": aridity.get("aridity_regime", "") if aridity else "",
        "climate_group": climate["climate_group"],
        "koppen_code": climate["koppen_code"],
        "levers": levers,
        "stressors": stressors,
        "metrics": metrics,
    }
    context["candidate_interventions"] = candidate_interventions(metrics, stressors)
    return context


def write_all_screening(features: list[dict[str, Any]], metric_maps: dict[str, dict[str, dict[str, str]]], out_dir: Path) -> Path:
    out_path = out_dir / "all_india_watershed_screening.csv"
    fieldnames = [
        "wsconc",
        "area_sqkm",
        "bacode",
        "sbcode",
        "aridity_index",
        "aridity_regime",
        "climate_group",
        "koppen_code",
        "temperature_lever",
        "humidity_lever",
        "precipitation_lever",
        "wind_lever",
        "stressors",
        "candidate_interventions",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for feature in features:
            props = feature["properties"]
            ws_id = props["wsconc"]
            metrics = {name: metric_maps[name].get(ws_id) for name in metric_maps}
            context = make_context(ws_id, props, metrics)
            writer.writerow(
                {
                    "wsconc": ws_id,
                    "area_sqkm": props.get("area_sqkm"),
                    "bacode": props.get("bacode"),
                    "sbcode": props.get("sbcode"),
                    "aridity_index": f"{context['aridity_index']:.4f}",
                    "aridity_regime": context["aridity_regime"],
                    "climate_group": ";".join(context["climate_group"]),
                    "koppen_code": ";".join(context["koppen_code"]),
                    "temperature_lever": context["levers"]["Temperature/LST"],
                    "humidity_lever": context["levers"]["Humidity/VPD"],
                    "precipitation_lever": context["levers"]["Precipitation"],
                    "wind_lever": context["levers"]["Wind"],
                    "stressors": ";".join(context["stressors"]),
                    "candidate_interventions": ";".join(context["candidate_interventions"]),
                }
            )
    return out_path


def run_selected_rag(
    base_args: argparse.Namespace,
    features_by_id: dict[str, dict[str, Any]],
    metric_maps: dict[str, dict[str, dict[str, str]]],
    out_dir: Path,
) -> tuple[Path, Path]:
    selected_ids = sorted(
        set(metric_maps["ctphi"])
        | set(metric_maps["lulc"])
        | set(metric_maps["true_coupling"])
    )
    selected_ids = [ws_id for ws_id in selected_ids if ws_id in features_by_id]
    results = []
    for ws_id in selected_ids:
        props = features_by_id[ws_id]["properties"]
        metrics = {name: metric_maps[name].get(ws_id) for name in metric_maps}
        context = make_context(ws_id, props, metrics)
        question = build_question(ws_id, context)
        args = retrieval_args(base_args, context, question)
        sources = plain_rag.retrieve(args, question)
        results.append(
            {
                "watershed_id": ws_id,
                "context": {
                    key: value
                    for key, value in context.items()
                    if key != "metrics"
                },
                "query": question,
                "recommendations": ranked_recommendations(context),
                "retrieved_sources": [source_summary(source) for source in sources],
            }
        )

    json_path = out_dir / "selected_watershed_rag_retrieval.json"
    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    md_path = out_dir / "selected_watershed_rag_retrieval.md"
    lines = ["# Selected Watershed RAG Retrieval", ""]
    for item in results:
        context = item["context"]
        lines.append(f"## {item['watershed_id']}")
        lines.append("")
        lines.append(f"- Area: {context['area_sqkm']:.1f} sq km")
        lines.append(f"- Basin/sub-basin: {context['bacode']}/{context['sbcode']}")
        lines.append(f"- Aridity: {context['aridity_index']:.3f} ({context['aridity_regime']})")
        lines.append(f"- Climate filters: {', '.join(context['climate_group'])}; {', '.join(context['koppen_code'])}")
        lines.append(f"- Levers: {json.dumps(context['levers'])}")
        lines.append(f"- Stressors: {', '.join(context['stressors'])}")
        lines.append(f"- Candidate interventions: {', '.join(context['candidate_interventions'])}")
        lines.append("")
        lines.append("Query:")
        lines.append("")
        lines.append(f"```text\n{item['query']}\n```")
        lines.append("")
        lines.append("Retrieved evidence:")
        lines.append("")
        for idx, source in enumerate(item["retrieved_sources"], start=1):
            lines.append(
                f"{idx}. score={source['score']} {source['section']}/{source['paper']} "
                f"heading={source['heading']} koppen={source['koppen_category']} role={source['evidence_role']}"
            )
            lines.append(f"   path={source['path']}")
            if source["metadata_reasons"]:
                lines.append(f"   metadata={', '.join(source['metadata_reasons'])}")
        lines.append("")
        lines.append("Screening recommendations:")
        lines.append("")
        for idx, rec in enumerate(item["recommendations"], start=1):
            lines.append(f"{idx}. **{rec['intervention']}** (score {rec['rank_score']}, confidence {rec['confidence']})")
            lines.append(f"   - Where: {rec['where']}")
            lines.append(f"   - Expected effect: {rec['expected_effect']}")
            lines.append(f"   - Mechanisms: {rec['mechanisms']}")
            lines.append(f"   - Caveat: {rec['caveat']}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    csv_path = out_dir / "selected_watershed_recommendations.csv"
    fieldnames = [
        "watershed_id",
        "rank",
        "intervention",
        "rank_score",
        "confidence",
        "where",
        "expected_effect",
        "mechanisms",
        "caveat",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            for idx, rec in enumerate(item["recommendations"], start=1):
                writer.writerow({"watershed_id": item["watershed_id"], "rank": idx, **rec})
    return json_path, md_path, csv_path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run watershed screening and RAG retrieval for the 13jul portal assets.")
    parser.add_argument("--portal-root", default=str(PORTAL_ROOT))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--index-dir", default=str(plain_rag.DEFAULT_INDEX_DIR))
    parser.add_argument("--ollama-url", default=plain_rag.DEFAULT_OLLAMA_URL)
    parser.add_argument("--embed-model", default=plain_rag.DEFAULT_EMBED_MODEL)
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    portal_root = Path(args.portal_root)
    watershed_file = portal_root / "assets" / "watershed_pan_india_simplified.geojson"
    metric_root = portal_root / "assets" / "coupling_metrics"
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    data = json.loads(watershed_file.read_text(encoding="utf-8"))
    features = data.get("features", [])
    features_by_id = {feature["properties"]["wsconc"]: feature for feature in features}
    metric_maps = {
        "aridity": load_csv_by_id(metric_root / "aridity_by_watershed.csv"),
        "ef_proxy": load_csv_by_id(metric_root / "ef_proxy_by_watershed.csv"),
        "tci_proxy": load_csv_by_id(metric_root / "tci_proxy_by_watershed.csv"),
        "dtr": load_csv_by_id(metric_root / "dtr_by_watershed.csv"),
        "ctphi": load_csv_by_id(metric_root / "ctphi_triggerability_samples.csv"),
        "lulc": load_csv_by_id(metric_root / "lulc_terrain_samples.csv"),
        "true_coupling": load_csv_by_id(metric_root / "gldas_true_coupling_samples.csv"),
    }

    screening_path = write_all_screening(features, metric_maps, out_dir)
    json_path, md_path, rec_csv_path = run_selected_rag(args, features_by_id, metric_maps, out_dir)
    print(f"wrote {screening_path}")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"wrote {rec_csv_path}")


if __name__ == "__main__":
    main()
