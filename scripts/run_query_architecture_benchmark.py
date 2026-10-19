"""Run one retrieval system on a frozen benchmark dataset."""

from __future__ import annotations

import argparse
import inspect
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


def frozen_spec(
    case: dict[str, Any],
    project_root: Path,
    query_module: Any,
    models: Any,
    extraction_models: Any,
    spec_dir: Path | None = None,
) -> Any:
    case_id = case["id"]
    if spec_dir is not None:
        path = spec_dir / f"{case_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Prepared QuerySpec not found: {path}")
        return models.QuerySpec.model_validate(read_json(path))
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
    parser.add_argument("--system", choices=("plain_rag", "graphrag", "climatekg"), default="climatekg")
    parser.add_argument("--plain-index", type=Path)
    parser.add_argument("--graphrag-index", type=Path)
    parser.add_argument("--spec-dir", type=Path)
    parser.add_argument("--case", action="append")
    parser.add_argument("--limit", type=int)
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
    import evaluation.plain_backend as plain_backend
    import webapp.answer_systems as answer_systems
    from webapp.server import ClimateKGEngine

    historical_read_prompt = query_module._read_prompt

    def read_benchmark_prompt(name: str) -> str:
        if name in {"webapp_process_rag_answer.txt", "webapp_land_use_rag_answer.txt"}:
            shared = project_root / "prompts" / name
            if not shared.exists():
                raise FileNotFoundError(f"Shared benchmark answer prompt not found: {shared}")
            return shared.read_text(encoding="utf-8")
        return historical_read_prompt(name)

    query_module._read_prompt = read_benchmark_prompt

    if len(inspect.signature(plain_backend._plain_rag_prompt).parameters) == 2:
        historical_plain_prompt = plain_backend._plain_rag_prompt
        plain_backend._plain_rag_prompt = (
            lambda question, sources, unused_mode: historical_plain_prompt(question, sources)
        )
    PlainPassageRAG = plain_backend.PlainPassageRAG

    if args.graphrag_index is not None:
        answer_systems.GRAPHRAG_INDEX = args.graphrag_index.resolve()

    cases = read_json(args.dataset)
    if args.limit is not None:
        cases = cases[: args.limit]
    if args.case:
        requested = set(args.case)
        cases = [case for case in cases if case["id"] in requested]
    output = args.output.resolve() / args.variant
    artifact_root = output / "artifacts"
    engine = ClimateKGEngine(graph_root=args.graph_root, output_root=artifact_root)
    plain = None
    if args.system == "plain_rag":
        if args.plain_index is None:
            raise ValueError("--plain-index is required for plain_rag")
        plain = PlainPassageRAG(args.plain_index, engine.ollama_url, engine.embedding_model, engine.model)

    write_json(
        output / "run_manifest.json",
        {
            "variant": args.variant,
            "code_root": str(code_root),
            "graph_root": str(args.graph_root.resolve()),
            "dataset": str(args.dataset.resolve()),
            "case_ids": [case["id"] for case in cases],
            "system": args.system,
            "query_protocol": (
                f"prepared QuerySpec loaded from {args.spec_dir.resolve()}"
                if args.system == "climatekg" and args.spec_dir is not None
                else "question text passed directly; no ClimateKG QuerySpec used"
            ),
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
        spec = None
        if args.system == "climatekg":
            spec = frozen_spec(
                case, project_root, query_module, models, extraction_models, args.spec_dir
            )
            frozen_path = output / "frozen_query_specs" / f"{case['id']}.json"
            write_json(frozen_path, spec.model_dump(by_alias=True, exclude_none=False))
            query_module.parse_query = lambda *unused_args, _spec=spec, **unused_kwargs: (
                _spec.model_copy(deep=True),
                ["QUERY_PARSE_REUSED_FOR_ARCHITECTURE_BENCHMARK"],
            )
        events: list[dict[str, Any]] = []
        started = time.perf_counter()
        try:
            if args.system == "plain_rag":
                result = plain.run(case["question"], top_k=5)
            else:
                result = engine.run(
                    case["question"],
                    f"{case['id']}_{args.variant}",
                    args.system,
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
