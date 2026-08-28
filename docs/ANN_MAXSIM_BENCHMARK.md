# ANN and Exact MaxSim Benchmark

## Query

The end-to-end comparison used:

> Under zero background wind over a heterogeneous chessboard surface with
> 14.4 km dry and wet patches, how does surface heat-flux heterogeneity affect
> local cloud development and precipitation?

Qwen extracted three Context Facets and a forward source endpoint. Both runs
used the same 1-paper corpus: 26 Contexts, 59 Facets, 18 Claims, 32 States, and
4 Transitions.

## Retrieval Design

```text
query Context vector
  -> FAISS HNSW top 100 Context IDs
  -> exact cosine for the shortlist
  -> exact domain-wise Facet MaxSim
  -> top 30 Contexts
  -> Context-scoped Claim candidates

query Claim / endpoint / intervention vectors
  -> corresponding HNSW shortlists
  -> exact cosine and existing Claim ranking
  -> Context gating
  -> path search
```

HNSW uses cosine-equivalent inner product over normalized vectors with
`M=32`, `efConstruction=200`, and `efSearch=128`. Index creation is offline
when the Parquet graph is built.

## One-Paper End-to-End Result

| Stage | Full scan | ANN | Observation |
|---|---:|---:|---|
| Context retrieval + exact MaxSim | 0.065 s | 0.075 s | ANN overhead at 26 Contexts |
| State mapping | 0.233 s | 0.188 s | Mostly endpoint embedding latency |
| Claim ranking | 0.006 s | 0.007 s | Effectively equal |
| Path search | 0.001 s | 0.001 s | Unchanged |

The two retrieval modes produced the same ordered Contexts, exact Context
MaxSim scores, State IDs, ordered Claims, `A_claim` values, paths, and selected
evidence objects. Total wall time is not a useful ANN comparison because local
Qwen loading, parsing, embedding, and synthesis dominate it.

## Scaling Benchmark

The benchmark replicated the real 2048-dimensional Context-vector
distribution with small deterministic noise. Recall was measured against exact
top-100 inner-product search.

| Context vectors | Approx. papers | Current Python scan | HNSW query | Speedup | Recall@100 | HNSW build |
|---:|---:|---:|---:|---:|---:|---:|
| 26 | 1 | 0.0025 s | 0.000012 s | 213x | 1.00 | 0.0002 s |
| 260 | 10 | 0.0271 s | 0.000125 s | 216x | 1.00 | 0.0150 s |
| 2,600 | 100 | 0.3224 s | 0.000363 s | 889x | 1.00 | 0.2121 s |
| 26,000 | 1,000 | 3.0018 s | 0.000568 s | 5,284x | 1.00 | 5.3491 s |

The HNSW query timings cover candidate generation only. Exact Facet MaxSim is
then applied to at most 100 Contexts, so its cost is bounded by configuration
rather than total corpus size.

## Interpretation

At the present corpus size, ANN is unnecessary for speed and slightly increases
end-to-end Context retrieval time. It becomes useful as the number of Contexts
reaches the thousands. The synthetic benchmark demonstrates computational
scaling, not scientific retrieval quality across a varied literature corpus.
Recall and ranking quality must be re-evaluated when substantially more real
papers are indexed.

Artifacts:

- `climatekg/runtime/outputs/ann_benchmark/scaling_comparison.json`
- `climatekg/runtime/outputs/ann_benchmark/baseline/QCTX_BASELINE/`
- `climatekg/runtime/outputs/ann_benchmark/ann/QCTX_ANN/`
- `climatekg/runtime/outputs/ann_benchmark/real_query_equivalence.json`
