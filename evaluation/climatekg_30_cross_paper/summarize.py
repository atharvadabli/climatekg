"""Build reproducible aggregate and per-question audits for the 30-query run."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def claim_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("claim_id") or item.get("id"))
        for item in rows
        if item.get("claim_id") or item.get("id")
    }


def path_claim_ids(report: dict[str, Any]) -> set[str]:
    return {
        str(claim_id)
        for path in report.get("paths", [])
        for claim_id in path.get("claim_ids", [])
    }


def provenance(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    value = report.get("synthesis", {}).get("provenance", {})
    return value if isinstance(value, dict) else {}


def paper_id_from_claim(claim_id: str) -> str | None:
    head = claim_id.split("_CL", 1)[0]
    return head if head.startswith("P") and head[1:].isdigit() else None


def metric_records(artifact_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(artifact_dir.rglob("*.metrics.json")):
        try:
            item = read_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        records.append(
            {
                "stage": item.get("stage", "unknown"),
                "validated": item.get("validated"),
                "elapsed_seconds": item.get("elapsed_seconds"),
                "prompt_tokens": item.get("prompt_eval_count"),
                "output_tokens": item.get("eval_count"),
                "request_path": item.get("request_path"),
                "response_path": item.get("raw_response_path"),
                "metrics_path": str(path.resolve()),
            }
        )
    return records


def flow_issues(expected: set[str], candidates: set[str], paths: set[str], cited: set[str]) -> list[str]:
    issues = []
    if expected - candidates:
        issues.append("candidate_retrieval_loss")
    if (expected & candidates) - paths:
        issues.append("path_construction_loss")
    if (expected & paths) - cited:
        issues.append("synthesis_selection_loss")
    if not issues:
        issues.append("no_expected_claim_flow_loss")
    return issues


def compact_spec(spec: dict[str, Any]) -> dict[str, Any]:
    context = spec.get("context", {})
    facets = [
        {
            "id": item.get("id"),
            "domain": item.get("domain"),
            "notion": item.get("notion"),
            "description": item.get("description"),
            "origin": item.get("origin"),
            "supporting_text_span": item.get("supporting_text_span"),
        }
        for item in context.get("facets", [])
    ]
    return {
        "mode": spec.get("mode"),
        "source": spec.get("source"),
        "target": spec.get("target"),
        "intervention_description": spec.get("intervention_description"),
        "analysis_cases": spec.get("analysis_cases", []),
        "analysis_comparison": spec.get("analysis_comparison"),
        "spatial_support": context.get("spatial_support"),
        "facets": facets,
        "ambiguities": spec.get("ambiguities", []),
    }


def build_row(case: dict[str, Any], run_root: Path) -> dict[str, Any]:
    case_id = case["id"]
    result_path = run_root / "results" / f"{case_id}.json"
    artifact_dir = run_root / "artifacts" / f"{case_id}_candidate_context_rescore_v2"
    report_path = artifact_dir / "query_report.json"
    if not result_path.exists() or not report_path.exists():
        return {
            "id": case_id,
            "category": case["category"],
            "capability": case["capability"],
            "status": "not_run",
            "question": case["question"],
            "expected_claim_ids": case.get("expected_claim_ids", []),
            "flow_issues": ["not_run"],
        }

    result = read_json(result_path)
    report = read_json(report_path)
    expected = set(case.get("expected_claim_ids", []))
    candidates = claim_ids(report.get("claim_candidates", []))
    paths = path_claim_ids(report)
    cited = set(provenance(report))
    expected_papers = {item["paper_id"] for item in case.get("source_papers", [])}
    cited_papers = {paper_id_from_claim(item) for item in cited}
    cited_papers.discard(None)
    answer = result.get("generated_answer", "")
    qualifiers = case.get("required_qualifiers", [])
    found_qualifiers = [item for item in qualifiers if item.lower() in answer.lower()]
    calls = metric_records(artifact_dir)
    llm_seconds = sum(float(item["elapsed_seconds"] or 0) for item in calls)
    prompt_tokens = sum(int(item["prompt_tokens"] or 0) for item in calls)
    output_tokens = sum(int(item["output_tokens"] or 0) for item in calls)
    specs = [compact_spec(report.get("query_spec", {}))]
    specs.extend(compact_spec(item.get("query_spec", {})) for item in report.get("subquery_reports", []))

    return {
        "id": case_id,
        "category": case["category"],
        "capability": case["capability"],
        "status": result.get("status"),
        "question": case["question"],
        "reference_answer": case["reference_answer"],
        "generated_answer": answer,
        "answerable": case["answerable"],
        "required_qualifiers": qualifiers,
        "qualifiers_found_by_exact_phrase": found_qualifiers,
        "unsupported_conclusions": case.get("unsupported_conclusions", []),
        "expected_paper_ids": sorted(expected_papers),
        "cited_paper_ids": sorted(cited_papers),
        "unexpected_cited_paper_ids": sorted(cited_papers - expected_papers),
        "expected_paper_coverage": (
            len(cited_papers & expected_papers) / len(expected_papers) if expected_papers else None
        ),
        "expected_claim_ids": sorted(expected),
        "expected_claims_in_candidates": sorted(expected & candidates),
        "expected_claims_in_paths": sorted(expected & paths),
        "expected_claims_cited": sorted(expected & cited),
        "missing_at_candidate_retrieval": sorted(expected - candidates),
        "lost_between_candidate_and_path": sorted((expected & candidates) - paths),
        "lost_between_path_and_synthesis": sorted((expected & paths) - cited),
        "flow_issues": flow_issues(expected, candidates, paths, cited),
        "candidate_claim_count": len(candidates),
        "path_count": len(report.get("paths", [])),
        "cited_claim_count": len(cited),
        "query_plan": report.get("query_plan"),
        "query_specs": specs,
        "warnings": report.get("warnings", []),
        "elapsed_seconds": result.get("metrics", {}).get("elapsed_seconds"),
        "llm_call_seconds": round(llm_seconds, 3),
        "llm_prompt_tokens": prompt_tokens,
        "llm_output_tokens": output_tokens,
        "llm_calls": calls,
        "stage_event_names": [item.get("stage") for item in result.get("events", [])],
        "result_path": str(result_path.resolve()),
        "trace_path": str(report_path.resolve()),
        "artifact_dir": str(artifact_dir.resolve()),
    }


def render_details(row: dict[str, Any], path: Path) -> None:
    calls = row.get("llm_calls", [])
    lines = [
        f"# {row['id']}: {row['capability']}",
        "",
        f"- Category: `{row['category']}`",
        f"- Status: `{row['status']}`",
        f"- Total elapsed: `{row.get('elapsed_seconds')}` seconds",
        f"- LLM call time recorded: `{row.get('llm_call_seconds')}` seconds",
        f"- Expected papers cited: `{len(set(row.get('expected_paper_ids', [])) & set(row.get('cited_paper_ids', [])))}/{len(row.get('expected_paper_ids', []))}`",
        f"- Expected Claims candidate/path/cited: `{len(row.get('expected_claims_in_candidates', []))}/{len(row.get('expected_claims_in_paths', []))}/{len(row.get('expected_claims_cited', []))}` of `{len(row.get('expected_claim_ids', []))}`",
        f"- Flow issues: `{', '.join(row.get('flow_issues', []))}`",
        "",
        "## Question",
        "",
        row.get("question", ""),
        "",
        "## Evaluation intent",
        "",
        f"Expected papers: `{', '.join(row.get('expected_paper_ids', []))}`",
        "",
        f"Expected Claims: `{', '.join(row.get('expected_claim_ids', []))}`",
        "",
        f"Required qualifiers: `{', '.join(row.get('required_qualifiers', []))}`",
        "",
        "Reference expectation:",
        "",
        row.get("reference_answer", ""),
        "",
        "Unsupported conclusions to avoid:",
        "",
        *[f"- {item}" for item in row.get("unsupported_conclusions", [])],
        "",
        "## Evidence flow",
        "",
        f"- Missing from candidates: `{', '.join(row.get('missing_at_candidate_retrieval', [])) or 'none'}`",
        f"- Lost between candidates and paths: `{', '.join(row.get('lost_between_candidate_and_path', [])) or 'none'}`",
        f"- Lost between paths and synthesis: `{', '.join(row.get('lost_between_path_and_synthesis', [])) or 'none'}`",
        f"- Expected Claims cited: `{', '.join(row.get('expected_claims_cited', [])) or 'none'}`",
        f"- Other cited papers: `{', '.join(row.get('unexpected_cited_paper_ids', [])) or 'none'}`",
        "",
        "## Parsed query",
        "",
        "```json",
        json.dumps({"query_plan": row.get("query_plan"), "query_specs": row.get("query_specs")}, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Warnings",
        "",
        *([f"- `{item}`" for item in row.get("warnings", [])] or ["- none"]),
        "",
        "## LLM calls",
        "",
        "| Stage | Valid | Seconds | Prompt tokens | Output tokens | Exact request | Exact response |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for item in calls:
        lines.append(
            f"| {item['stage']} | {item['validated']} | {float(item['elapsed_seconds'] or 0):.1f} | "
            f"{item['prompt_tokens'] or '-'} | {item['output_tokens'] or '-'} | "
            f"`{item['request_path'] or '-'}` | `{item['response_path'] or '-'}` |"
        )
    lines.extend([
        "",
        "## Generated answer",
        "",
        row.get("generated_answer", ""),
        "",
        "## Raw trace",
        "",
        f"- Query report: `{row.get('trace_path', '-')}`",
        f"- Runner result: `{row.get('result_path', '-')}`",
        f"- Artifact directory: `{row.get('artifact_dir', '-')}`",
        "",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [build_row(case, args.run_root) for case in read_json(args.dataset)]
    write_json(args.output / "responses_and_stage_audit.json", rows)
    for row in rows:
        render_details(row, args.output / "questions" / f"{row['id']}.md")

    completed = [row for row in rows if row.get("status") == "complete"]
    elapsed = [float(row["elapsed_seconds"]) for row in completed if row.get("elapsed_seconds")]
    warning_counts = Counter(w for row in completed for w in row.get("warnings", []))
    issue_counts = Counter(issue for row in completed for issue in row.get("flow_issues", []))
    category_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in completed:
        category_rows[row["category"]].append(row)

    total_expected = sum(len(row.get("expected_claim_ids", [])) for row in completed)
    total_candidate = sum(len(row.get("expected_claims_in_candidates", [])) for row in completed)
    total_path = sum(len(row.get("expected_claims_in_paths", [])) for row in completed)
    total_cited = sum(len(row.get("expected_claims_cited", [])) for row in completed)
    cross_paper_answers = sum(len(row.get("cited_paper_ids", [])) >= 2 for row in completed)

    lines = [
        "# ClimateKG 30-question structured-reasoning run",
        "",
        f"- Completed: {len(completed)} / {len(rows)}",
        f"- Total query time: {sum(elapsed):.1f} seconds",
        f"- Mean query time: {sum(elapsed) / len(elapsed):.1f} seconds" if elapsed else "- Mean query time: unavailable",
        "- Candidate branch base: `experiment/candidate-context-rescore-v2` (`c2eb632`)",
        "- Graph: 115 papers, 1,217 Contexts, 3,460 Facets, 1,729 Claims",
        "- Protocol: live decomposition and query parsing; no frozen QuerySpecs",
        "- Evaluation status: diagnostic development suite, not held-out scientific gold",
        "",
        "## Aggregate evidence flow",
        "",
        f"- Diagnostic expected Claims: {total_expected}",
        f"- Entered candidate pool: {total_candidate} ({total_candidate / total_expected:.1%})",
        f"- Reached selected paths: {total_path} ({total_path / total_expected:.1%})",
        f"- Appeared in synthesis provenance: {total_cited} ({total_cited / total_expected:.1%})",
        f"- Answers citing at least two papers: {cross_paper_answers} / {len(completed)}",
        "",
        "These are stage diagnostics, not answer-accuracy scores. An answer can be correct using an alternative Claim, and a cited expected Claim does not by itself prove a correct synthesis.",
        "",
        "## By capability group",
        "",
        "| Group | Questions | Expected Claims candidate/path/cited | Mean seconds |",
        "|---|---:|---:|---:|",
    ]
    for category, items in category_rows.items():
        expected = sum(len(item["expected_claim_ids"]) for item in items)
        candidate = sum(len(item["expected_claims_in_candidates"]) for item in items)
        paths = sum(len(item["expected_claims_in_paths"]) for item in items)
        cited = sum(len(item["expected_claims_cited"]) for item in items)
        mean = sum(float(item["elapsed_seconds"]) for item in items) / len(items)
        lines.append(f"| {category} | {len(items)} | {candidate}/{paths}/{cited} of {expected} | {mean:.1f} |")
    lines.extend([
        "",
        "## Stage-loss indicators",
        "",
        *[f"- `{name}`: {count} questions" for name, count in issue_counts.most_common()],
        "",
        "## Frequent warnings",
        "",
        *[f"- `{name}`: {count}" for name, count in warning_counts.most_common()],
        "",
        "## Question audit",
        "",
        "| ID | Capability | Seconds | Expected Claims candidate/path/cited | Papers expected/cited | Flow indicators |",
        "|---|---|---:|---:|---:|---|",
    ])
    for row in rows:
        total = len(row.get("expected_claim_ids", []))
        candidate = len(row.get("expected_claims_in_candidates", []))
        path = len(row.get("expected_claims_in_paths", []))
        cited = len(row.get("expected_claims_cited", []))
        paper_hits = len(set(row.get("expected_paper_ids", [])) & set(row.get("cited_paper_ids", [])))
        seconds = row.get("elapsed_seconds")
        seconds_text = f"{seconds:.1f}" if isinstance(seconds, (int, float)) else "-"
        detail_link = f"questions/{row['id']}.md"
        lines.append(
            f"| [{row['id']}]({detail_link}) | {row.get('capability', '')} | {seconds_text} | "
            f"{candidate}/{path}/{cited} of {total} | {paper_hits}/{len(row.get('expected_paper_ids', []))}; "
            f"{len(row.get('cited_paper_ids', []))} total | {', '.join(row.get('flow_issues', []))} |"
        )
    lines.extend([
        "",
        "## Initial findings",
        "",
        "1. Candidate retrieval is broad: most diagnostic Claims enter the candidate pool. The larger loss occurs when candidates are reduced to paths and then to the bounded synthesis evidence.",
        "2. The system does perform cross-paper synthesis, but evidence breadth is uneven. Inspect questions where expected papers are retrieved but only one paper survives into provenance.",
        "3. Context, State mapping, and grounding warnings are preserved per question. Missing Context and Context mismatch must be reviewed separately in the raw report.",
        "4. The two original execution failures came from an unavailable gazetteer. The evaluation branch now records the failure and retains unresolved spatial Context instead of aborting or inventing coordinates.",
        "5. Exact-phrase qualifier coverage and reference-token overlap remain diagnostics only; scientific correctness requires citation-level review against SourceBlocks.",
        "",
        "## Files",
        "",
        "- `responses_and_stage_audit.json`: all questions, answers, plans, parsed specs, Claim flow, warnings, timings, and raw paths.",
        "- `questions/XPGxxx.md`: readable complete audit for each question.",
        "- Runtime artifact directories: exact LLM requests/responses, query reports, and stage events.",
        "",
    ])
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
