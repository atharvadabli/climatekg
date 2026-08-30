# Shared-corpus retrieval baselines

This adapter compares plain passage RAG and an entity-adapted GraphRAG index on exactly the same finalized papers.

Install the baseline-only dependencies:

```powershell
py -3.13 -m pip install -e ".[baselines]"
```

Run the frozen three-query comparison:

```powershell
py -3.13 -m baselines.climatekg_comparison.run `
  --staged-root climatekg/runtime/outputs/indexing_50_medium_map_20260829 `
  --heterogeneity-root climatekg/runtime/outputs/hierarchy_e2e_het_v10 `
  --queries Paper_writing/neurips2026_submission/evaluation_queries.json `
  --output climatekg/runtime/outputs/baseline_comparison_20260830_v2
```

Plain RAG indexes cleaned SourceBlock text. The GraphRAG adapter uses canonical States as entities, Claims as relationships, and Microsoft GraphRAG 3.1.1 hierarchical Leiden for communities. It preserves paper, context, facet, and SourceBlock provenance in relationship and text-unit tables.

The adapter does not treat a thematic community as a scientifically valid mechanism path. ClimateKG's Context gating is a distinct operation.
