from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import OUTPUT_ROOT, ROOT
from .graph import Neo4jHttp
from .parquet_graph import ParquetGraph
from .query import run_query
from .utils import write_json


class QueryCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_id: str
    category: Literal["generic", "context_dependent", "spatial"]
    question: str
    expected_mode: Literal["forward", "backward", "a_to_b", "global"] | None = None
    expect_context_facets: bool
    scientific_purpose: str
    required_claim_groups: list[list[str]] = Field(default_factory=list)


def load_query_suite(path: Path | None = None) -> list[QueryCase]:
    suite_path = path or ROOT / "config" / "validation_queries.json"
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    return [QueryCase.model_validate(item) for item in data["queries"]]


def verify_query_report(case: QueryCase, report: dict[str, Any]) -> list[dict[str, Any]]:
    spec = report.get("query_spec", {})
    paths = report.get("paths", [])
    candidates = {row["claim_id"] for row in report.get("claim_candidates", [])}
    path_claims = {claim_id for path in paths for claim_id in path.get("claim_ids", [])}
    blocks = report.get("source_blocks", {})
    synthesis = report.get("synthesis", {})
    provenance = synthesis.get("provenance", {})
    state_mapping = report.get("state_mapping", {})
    checks = [
        _check("query_id", report.get("query_id") == case.query_id, f"expected={case.query_id} actual={report.get('query_id')}"),
        _check("query_mode", case.expected_mode is None or spec.get("mode") == case.expected_mode, f"expected={case.expected_mode} actual={spec.get('mode')}"),
        _check("query_context", bool(spec.get("context", {}).get("facets")) == case.expect_context_facets, f"expected_facets={case.expect_context_facets} count={len(spec.get('context', {}).get('facets', []))}"),
        _check("source_state_mapping", not spec.get("source") or bool(state_mapping.get("source_seeds")), f"source={spec.get('source')} seeds={state_mapping.get('source_seeds', [])}"),
        _check("target_state_mapping", not spec.get("target") or bool(state_mapping.get("target_seeds")), f"target={spec.get('target')} seeds={state_mapping.get('target_seeds', [])}"),
        _check("claim_candidates", bool(candidates), f"count={len(candidates)}"),
        _check("paths", bool(paths), f"count={len(paths)}"),
        _check("paths_use_ranked_claims", path_claims <= candidates, f"unranked={sorted(path_claims - candidates)}"),
        _check("selected_evidence", bool(blocks), f"objects={len(blocks)} blocks={sum(len(items) for items in blocks.values())}"),
        _check("grounded_synthesis", bool(synthesis.get("items")) and bool(provenance), f"items={len(synthesis.get('items', []))} provenance={len(provenance)}"),
        _check("answer", bool(report.get("answer", "").strip()), f"characters={len(report.get('answer', ''))}"),
        _check("grounding_warning_absent", "FINAL_GROUNDING_VALIDATION_FAILED" not in report.get("warnings", []), f"warnings={report.get('warnings', [])}"),
    ]
    if case.expect_context_facets:
        checks.append(_check("context_gate_enabled", report.get("context_gate_disabled_reason") is None, f"disabled_reason={report.get('context_gate_disabled_reason')}"))
        applicable_paths = [path for path in paths if path.get("A_path") is not None]
        checks.append(_check("known_path_applicability", bool(applicable_paths), f"known={len(applicable_paths)} total={len(paths)}"))
    for index, group in enumerate(case.required_claim_groups, 1):
        supported = sorted(set(group) & set(provenance))
        checks.append(_check(f"required_claim_group_{index}", bool(supported), f"expected_any={group} grounded={supported}"))
    return checks


def run_validation_suite(
    suite_path: Path | None = None,
    output_root: Path | None = None,
    query_ids: list[str] | None = None,
    storage: Literal["parquet", "neo4j"] = "parquet",
    graph_root: Path | None = None,
) -> dict[str, Any]:
    cases = load_query_suite(suite_path)
    if query_ids:
        selected = set(query_ids)
        cases = [case for case in cases if case.query_id in selected]
        missing = selected - {case.query_id for case in cases}
        if missing:
            raise ValueError(f"unknown query IDs: {sorted(missing)}")
    run_id = datetime.now(timezone.utc).strftime("query-suite-%Y%m%dT%H%M%SZ")
    root = output_root or OUTPUT_ROOT / "query_validation" / run_id
    root.mkdir(parents=True, exist_ok=True)
    try:
        if storage == "parquet":
            graph = ParquetGraph(graph_root or OUTPUT_ROOT / "parquet_graph")
            papers, indexes = graph.read_corpus(), graph.read_indexes()
        else:
            papers, indexes = Neo4jHttp().read_corpus(), None
    except Exception as exc:
        blocker = f"{type(exc).__name__}: {exc}"
        summary = {"run_id": run_id, "generated_at": datetime.now(timezone.utc).isoformat(), "storage": storage, "corpus_papers": 0, "query_count": len(cases), "passed": 0, "failed": 0, "errors": len(cases), "blocked": True, "blocker": blocker, "results": []}
        write_json(root / "suite_report.json", summary)
        (root / "suite_report.md").write_text(_markdown(summary), encoding="utf-8")
        print(json.dumps({"stage": "graph_preflight_failed", "storage": storage, "error": blocker}, ensure_ascii=False), flush=True)
        return summary
    results = []
    for index, case in enumerate(cases, 1):
        case_root = root / "queries"
        events_path = case_root / case.query_id / "stage_events.jsonl"
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text("", encoding="utf-8")

        def record(stage: str, details: dict[str, Any]) -> None:
            event = {"timestamp": datetime.now(timezone.utc).isoformat(), "query_id": case.query_id, "stage": stage, "details": details}
            with events_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            print(json.dumps(event, ensure_ascii=False), flush=True)

        started = time.time()
        record("query_started", {"position": index, "total": len(cases), "category": case.category, "question": case.question, "scientific_purpose": case.scientific_purpose})
        try:
            report = run_query(case.question, case.query_id, papers, case_root, stage_callback=record, indexes=indexes)
            checks = verify_query_report(case, report)
            status = "passed" if all(item["passed"] for item in checks) else "failed"
            error = None
        except Exception as exc:
            checks, status, error = [], "error", f"{type(exc).__name__}: {exc}"
            record("query_failed", {"error": error})
        result = {"query_id": case.query_id, "category": case.category, "question": case.question, "status": status, "elapsed_seconds": time.time() - started, "checks": checks, "error": error, "artifact_dir": str(case_root / case.query_id)}
        results.append(result)
        write_json(root / "suite_progress.json", {"run_id": run_id, "results": results})
    summary = {"run_id": run_id, "generated_at": datetime.now(timezone.utc).isoformat(), "storage": storage, "corpus_papers": len(papers), "query_count": len(cases), "passed": sum(item["status"] == "passed" for item in results), "failed": sum(item["status"] == "failed" for item in results), "errors": sum(item["status"] == "error" for item in results), "blocked": False, "blocker": None, "results": results}
    write_json(root / "suite_report.json", summary)
    (root / "suite_report.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def _check(name: str, passed: bool, details: str) -> dict[str, Any]:
    return {"name": name, "passed": passed, "details": details}


def _markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# ClimateKG Query Validation",
        "",
        f"- Run: `{summary['run_id']}`",
        f"- Graph storage: {summary.get('storage', 'neo4j')}",
        f"- Corpus papers loaded: {summary['corpus_papers']}",
        f"- Queries: {summary['query_count']}",
        f"- Passed / failed / errors: {summary['passed']} / {summary['failed']} / {summary['errors']}",
        f"- Blocked: {summary.get('blocked', False)}",
        f"- Blocker: {summary.get('blocker') or 'none'}",
        "",
        "| Query | Category | Status | Seconds | Failed checks / error |",
        "|---|---|---:|---:|---|",
    ]
    for result in summary["results"]:
        failed = [item["name"] for item in result["checks"] if not item["passed"]]
        details = result["error"] or ", ".join(failed)
        lines.append(f"| {result['query_id']} | {result['category']} | {result['status']} | {result['elapsed_seconds']:.1f} | {details} |")
    lines.extend(["", "Each query directory contains `stage_events.jsonl`, LLM request/response envelopes, `query_spec.json`, `query_report.json`, and `answer.md` when the run reaches those stages.", ""])
    return "\n".join(lines)
