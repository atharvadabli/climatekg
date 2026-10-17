"""Run one ClimateKG query architecture on the frozen ten-query benchmark."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def report_spec(case_id: str, project_root: Path) -> dict[str, Any] | None:
    for run_name in ("cross_domain_v7_first10", "analysis_cases_v2_first10", "v1"):
        path = (
            project_root
            / "evaluation/output/climatekg_benchmark/runs"
            / run_name
            / "artifacts"
            / f"{case_id}_climatekg"
            / "query_report.json"
        )
        if path.exists():
            return read_json(path)["query_spec"]
    return None


def raw_parsed_query(case_id: str, project_root: Path) -> dict[str, Any]:
    parse_dir = (
        project_root
        / "evaluation/output/climatekg_benchmark/runs/analysis_cases_v2_first10/artifacts"
        / f"{case_id}_climatekg/parse"
    )
    attempts = sorted(parse_dir.glob("*.attempt0.json"))
    if not attempts:
        raise FileNotFoundError(f"No saved parse response for {case_id}: {parse_dir}")
    envelope = read_json(attempts[-1])
    return json.loads(envelope["message"]["content"])


def frozen_spec(case: dict[str, Any], project_root: Path, query_module: Any, models: Any, extraction_models: Any) -> Any:
    case_id = case["id"]
    saved = report_spec(case_id, project_root)
    if saved is not None:
        return models.QuerySpec.model_validate(saved)

    parsed = extraction_models.ParsedQuery.model_validate(raw_parsed_query(case_id, project_root))
    question = unicodedata.normalize("NFC", case["question"])
    exact = lambda value: unicodedata.normalize("NFC", value) in question
    facets = [
        models.QueryFacet(
            id=f"{case_id}_climatekg_F{index:03d}",
            domain=item.domain,
            notion=item.notion,
            description=item.description,
            origin="user",
            supporting_text_span=item.supporting_text_span,
        )
        for index, item in enumerate(parsed.explicit_context_facets, start=1)
        if exact(item.supporting_text_span)
    ]
    cases = [
        models.QueryAnalysisCase(
            id=f"{case_id}_climatekg_AC{index:03d}",
            label=item.label,
            supporting_text_span=item.supporting_text_span,
        )
        for index, item in enumerate(parsed.analysis_cases, start=1)
        if exact(item.supporting_text_span)
    ]
    support = None
    if parsed.spatial_reference:
        support = models.SpatialSupport(
            kind=parsed.spatial_reference.kind_hint or "unresolved",
            name=parsed.spatial_reference.text,
            geometry=None,
            enrichable_study_location_name=parsed.spatial_reference.text,
            resolution="unresolved",
        )
    endpoint = lambda item: models.ClaimEndpoint(concept=item.concept, state=item.state) if item else None
    return models.QuerySpec(
        query_id=f"{case_id}_climatekg",
        mode=query_module._query_mode(parsed, "global"),
        context=models.QueryContext(spatial_support=support, facets=facets),
        source=endpoint(parsed.source),
        target=endpoint(parsed.target),
        intervention_description=parsed.intervention_description,
        analysis_cases=cases,
        analysis_comparison=parsed.analysis_comparison,
        user_question=case["question"],
        ambiguities=parsed.ambiguities,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--graph-root", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    project_root = args.project_root.resolve()
    code_root = args.code_root.resolve()
    os.environ.setdefault(
        "TIKTOKEN_CACHE_DIR",
        str(project_root / "climatekg/runtime/cache/tiktoken"),
    )
    sys.path.insert(0, str(code_root))
    sys.path.insert(1, str(project_root))

    import climatekg.extraction_models as extraction_models
    import climatekg.models as models
    import climatekg.query as query_module
    from evaluation.metrics import score_result
    from webapp.server import ClimateKGEngine

    cases = read_json(args.dataset)[:10]
    if args.case:
        requested = set(args.case)
        cases = [case for case in cases if case["id"] in requested]
    output = args.output.resolve() / args.variant
    artifact_root = output / "artifacts"
    engine = ClimateKGEngine(graph_root=args.graph_root, output_root=artifact_root)

    write_json(
        output / "run_manifest.json",
        {
            "variant": args.variant,
            "code_root": str(code_root),
            "graph_root": str(args.graph_root.resolve()),
            "dataset": str(args.dataset.resolve()),
            "case_ids": [case["id"] for case in cases],
            "query_protocol": "frozen saved QuerySpec; query parsing and enrichment are not rerun",
        },
    )

    for index, case in enumerate(cases, start=1):
        target = output / "results" / f"{case['id']}.json"
        if target.exists() and not args.force:
            existing = read_json(target)
            if existing.get("status") == "complete":
                print(f"[{index}/{len(cases)}] {case['id']}: reused", flush=True)
                continue
        print(f"[{index}/{len(cases)}] {case['id']}: running", flush=True)
        spec = frozen_spec(case, project_root, query_module, models, extraction_models)
        frozen_path = output / "frozen_query_specs" / f"{case['id']}.json"
        write_json(frozen_path, spec.model_dump(by_alias=True, exclude_none=False))
        query_module.parse_query = lambda *unused_args, _spec=spec, **unused_kwargs: (
            _spec.model_copy(deep=True),
            ["QUERY_PARSE_REUSED_FOR_ARCHITECTURE_BENCHMARK"],
        )
        events: list[dict[str, Any]] = []
        started = time.perf_counter()
        try:
            result = engine.run(
                case["question"],
                f"{case['id']}_{args.variant}",
                "climatekg",
                lambda stage, data: events.append({"stage": stage, "data": data}),
            )
            elapsed = time.perf_counter() - started
            expected = {
                **case,
                "expected_paper_ids": [item["paper_id"] for item in case["source_papers"]],
                "expected_terms": case["required_qualifiers"],
            }
            payload = {
                "status": "complete",
                "variant": args.variant,
                "case_id": case["id"],
                "question": case["question"],
                "gold_answer": case["reference_answer"],
                "generated_answer": result["answer"],
                "metrics": score_result(expected, result, elapsed),
                "events": events,
                "result": result,
            }
        except Exception as exc:
            payload = {
                "status": "failed",
                "variant": args.variant,
                "case_id": case["id"],
                "question": case["question"],
                "gold_answer": case["reference_answer"],
                "generated_answer": "",
                "error": {"type": type(exc).__name__, "message": str(exc)},
                "events": events,
            }
        write_json(target, payload)
        print(f"[{index}/{len(cases)}] {case['id']}: {payload['status']}", flush=True)


if __name__ == "__main__":
    main()
