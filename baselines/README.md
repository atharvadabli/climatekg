# Retrieval Baselines

This branch keeps three retrieval implementations together for the NeurIPS
workshop pilot. Generated indexes and model outputs are excluded from Git.

## Systems

- `../climatekg/`: ClimateKG staged and combined extraction routes, Parquet
  graph, retrieval, context gating, path search, and cited synthesis.
- `plain_rag/`: the project-owned passage RAG baseline. Only source,
  configuration, and documentation are vendored; its 86 MB generated index is
  intentionally omitted.
- `graphrag/`: Microsoft GraphRAG 3.1.1 package source, copied from upstream
  commit `14a00ad88fc33cf2b52f4f113f25807556f8e25e`. Microsoft GraphRAG is MIT
  licensed; its license is preserved in that directory. It is an external
  baseline, not a contribution of this project.

All comparisons must use the same paper text, query wording, local generation
model, embedding model where supported, and evidence budget. The paper reports
pilot behavior rather than claiming that one general-purpose retrieval method
is universally superior.
