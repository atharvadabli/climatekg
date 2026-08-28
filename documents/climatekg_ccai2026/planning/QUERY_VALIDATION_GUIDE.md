# Graph-Backed Query Validation

## Query suite

The versioned suite is stored at `config/validation_queries.json` and contains:

- three generic/global literature questions;
- six context-dependent questions covering tropical/boreal reversal, irrigation and heat, soil-moisture feedback, atmospheric stability, and Sahel albedo;
- one spatial patch-edge question that must fail closed when local geometry is insufficient.

The questions were selected from the Contexts and Claims present in the ten finalized paper artifacts. They are not generic demonstrations disconnected from the indexed corpus.

## One-command run

From a normal PowerShell session with Docker Desktop access:

```powershell
.\scripts\run_graph_query_validation.ps1
```

The script uses the pinned official `neo4j:5.26-community` container, stores its data under `climatekg/runtime/neo4j`, initializes the graph schema, ingests and verifies all finalized papers, and runs the query suite with the configured local Ollama models.

## Per-query stages

Every query records these events in `stage_events.jsonl`:

1. corpus loaded from Neo4j;
2. query parsed by local `qwen3.6:27b`;
3. query embedded by `qwen3-embedding:4b`;
4. Context candidates retrieved and Facet-reranked;
5. source and target States mapped;
6. Claims ranked with applicability components;
7. context-gated mechanism paths searched;
8. contradictions and alternatives retrieved;
9. SourceBlocks selected;
10. evidence package trimmed;
11. grounded answer synthesized and validated;
12. final artifacts written.

The stage log includes IDs, scores, coverage, warnings, counts, and artifact paths. LLM request/response envelopes remain in the query's `parse` and `synthesis` directories.

## Outputs

```text
climatekg/runtime/outputs/query_validation/<run-id>/
|-- suite_progress.json
|-- suite_report.json
|-- suite_report.md
`-- queries/
    `-- <query-id>/
        |-- stage_events.jsonl
        |-- query_spec.json
        |-- query_report.json
        |-- answer.md
        |-- parse/
        `-- synthesis/
```

The first managed-session preflight is preserved at `climatekg/runtime/outputs/query_validation/preflight-20260824`. It records that all ten queries were blocked before execution because Neo4j port 7474 refused the connection. No in-memory graph fallback was used.
