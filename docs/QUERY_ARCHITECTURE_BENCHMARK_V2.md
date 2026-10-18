# Corrected-gold query architecture benchmark

## Evidence policy

This rerun uses ten questions whose gold evidence is restricted to findings produced, observed, simulated, or analyzed by the indexed paper. Review passages that only summarize cited studies are excluded. Four invalid v1 questions were replaced: `CKGQ0003`, `CKGQ0005`, `CKGQ0008`, and `CKGQ0009`.

Each corrected question was parsed once. The saved `QuerySpec` was then reused by all four ClimateKG architectures. PlainRAG and Microsoft GraphRAG received the same question text. All systems used the same 115-paper corpus and local Qwen generation model.

## Automated results

| System | Complete | Expected paper hit | Mean token F1 | Mean qualifier coverage | Median latency (s) |
|---|---:|---:|---:|---:|---:|
| PlainRAG | 10/10 | 10/10 | 0.3535 | 0.3333 | 26.0 |
| Microsoft GraphRAG | 10/10 | 10/10 | 0.2693 | 0.3183 | 41.0 |
| ClimateKG baseline | 10/10 | 8/10 | 0.1695 | 0.1550 | 180.0 |
| ClimateKG evidence union | 10/10 | 9/10 | 0.2768 | 0.2800 | 201.9 |
| ClimateKG soft context | 10/10 | 9/10 | 0.2843 | 0.2350 | 210.3 |
| ClimateKG graph expansion | 10/10 | 9/10 | 0.2892 | 0.2350 | 214.1 |

These are diagnostic metrics, not proof of scientific correctness. Expected-paper hit only shows that evidence from the gold paper reached the answer package. Token F1 rewards lexical overlap. Qualifier coverage currently uses phrase matching and assigns zero to some valid paraphrases; for example, the answers to `CKGQ0005` describe persistent irrigated cooling and lost rainfed cooling during drought even though the recorded coverage is zero.

## Replacement-case audit

| Case | Finding | Result |
|---|---|---|
| `CKGQ0003` | Weaker synoptic wind, Amazon circulation, clouds, and rainfall | PlainRAG and GraphRAG hit P000019. ClimateKG baseline retrieved the paper but abstained. All three evidence-union descendants produced a grounded answer from P000019. |
| `CKGQ0005` | Drought response of irrigated versus rainfed cooling | All systems hit P000007. ClimateKG baseline abstained; the three experimental variants recovered the requested contrast. |
| `CKGQ0008` | Season, wind speed, forest size, and cloud location | All systems hit P000014. All ClimateKG variants returned the seasonal and downwind-edge result. |
| `CKGQ0009` | Irrigation effects on daytime maximum, nighttime minimum, and heat-wave duration | PlainRAG and GraphRAG hit P000004. Every ClimateKG architecture missed P000004 and returned only partial evidence from other irrigation papers. |

## Remaining ClimateKG miss

`CKGQ0009` fails before graph expansion can help:

1. Query parsing identifies irrigation as the source but leaves the target empty.
2. The three requested outcomes are placed inside `intervention_description` instead of represented as targets or analysis items.
3. The leading Contexts come from P000100, P000091, and P000003; P000004 is absent.
4. The leading Claims come primarily from P000037 and P000091; no P000004 Claim enters the assembled evidence.
5. Path search produces zero paths, so graph expansion has no relevant P000004 seed to expand from.

This is a query-representation and retrieval-coverage failure, not a synthesis failure. The answer correctly states that the supplied evidence lacks nighttime-temperature and heat-wave-duration findings.

The baseline also misses P000040 for `CKGQ0007`. Evidence union recovers P000040 Claims and raises the expected-paper result from 8/10 to 9/10.

## Architecture decision

Evidence union is the smallest experimental architecture that recovers the additional expected paper and answers the corrected Amazon and drought cases. Soft Context matching and graph expansion do not add another expected-paper hit in this benchmark. Graph expansion is also the slowest variant and does not repair `CKGQ0009`, so the corrected run still does not justify adopting it.

Final architecture selection should wait for human scientific review of all ten answers. The automated results support evidence union as the current minimal candidate, not as a proven winner over PlainRAG or GraphRAG.

## Artifacts

- Corrected dataset: `evaluation/output/climatekg_benchmark/dataset_v2_current_findings_10/cases.json`
- Saved query parses and raw LLM calls: `evaluation/output/query_architecture_benchmark_v2/query_parse/`
- Per-system results and traces: `evaluation/output/query_architecture_benchmark_v2/variants/`
- Complete comparison: `evaluation/output/query_architecture_benchmark_v2/comparison.json`
- Generated summary: `evaluation/output/query_architecture_benchmark_v2/summary.md`
- Run logs: `evaluation/output/query_architecture_benchmark_v2/logs/`
