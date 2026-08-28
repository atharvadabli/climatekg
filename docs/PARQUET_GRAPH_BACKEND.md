# Parquet Graph Backend

## What Microsoft GraphRAG Does

Microsoft GraphRAG writes its indexed knowledge model as Parquet tables. Its
`relationships.parquet` file is the graph edge list. At query time it loads the
required tables into dataframes, uses vector lookup to find entry points, and
performs relationship expansion and ranking in application code.

Parquet is durable columnar storage. It is not itself a graph database and does
not provide Cypher, indexes, transactions, or traversal operators.

## ClimateKG Design

ClimateKG now follows the same storage pattern without adopting Microsoft
GraphRAG's entity/community schema or retrieval algorithm. The authoritative
ClimateKG scientific objects remain unchanged:

- `papers.parquet`
- `source_blocks.parquet`
- `contexts.parquet`
- `facets.parquet`
- `transitions.parquet`
- `claims.parquet`
- `states.parquet`
- `evidence_links.parquet`
- `relationships.parquet`

`relationships.parquet` is derived from the object references and uses the same
relationship directions as the Neo4j ingestion code. Examples are
`HAS_CONTEXT`, `PARENT_OF`, `HAS_FACET`, `FROM`, `TO`, `SCOPED_TO`,
`CONDITIONED_BY`, and `SUPPORTED_BY`.

The query pipeline loads the tables, reconstructs `FinalPaper`, validates all
schema references with Pydantic, and then creates the existing in-memory
`Corpus`. Context similarity, Claim gating, path search, evidence selection,
and grounded answer synthesis are therefore unchanged.

Embeddings remain list columns on their owning Context, Facet, Transition,
Claim, State, or SourceBlock rows. Building the Parquet graph also creates
persisted FAISS HNSW indexes under `ann/` for Contexts, Claims, States, and
Transitions. ANN supplies candidate IDs only. ClimateKG recomputes cosine
scores for those candidates and performs the existing exact, domain-aware
Facet MaxSim after Context shortlisting.

## Commands

Build the local graph from indexed paper folders:

```powershell
python -m climatekg.cli build-parquet `
  --data-root climatekg/runtime/data/papers `
  --output climatekg/runtime/outputs/parquet_graph
```

Validate the files and display counts:

```powershell
python -m climatekg.cli inspect-parquet `
  --graph-root climatekg/runtime/outputs/parquet_graph
```

Run a query without Neo4j or Docker:

```powershell
python -m climatekg.cli query "How does forest cover affect local temperature?" `
  --graph-root climatekg/runtime/outputs/parquet_graph
```

Run the query validation suite against Parquet:

```powershell
python -m climatekg.cli validate-queries `
  --storage parquet `
  --graph-root climatekg/runtime/outputs/parquet_graph
```

Neo4j remains available by passing `--storage neo4j`. It is useful when Cypher,
Neo4j Browser, or an externally shared graph server is needed. It is no longer
required for the normal local query path.

## Verified Example

The hierarchy extraction at
`climatekg/runtime/outputs/hierarchy_e2e_het_v10` was exported and read back
without any object differences. The Parquet graph contains:

| Table | Rows |
|---|---:|
| papers | 1 |
| source_blocks | 163 |
| contexts | 26 |
| facets | 59 |
| transitions | 4 |
| claims | 18 |
| states | 32 |
| evidence_links | 144 |
| relationships | 505 |

The complete dataset is about 6.4 MB and is stored under the runtime output
folder, not alongside source code.
