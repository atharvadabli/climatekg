# Atomic Claims and Evidence Subgraphs

## Status

This document defines an experimental extension. It does not replace the
authoritative indexing or query specifications until the ten-paper gate in
`evaluation/atomic_evidence_subgraph/README.md` passes.

## Scientific constraints

- A Claim remains the only object that can assert a causal or associative
  scientific relationship.
- Embedding similarity may retrieve candidate Claims or candidate State links;
  it cannot establish scientific causality.
- State semantic links express vocabulary identity or hierarchy only:
  `equivalent_to`, `narrower_than`, or `broader_than`.
- Original endpoint text, Context, evidence role, and SourceBlock provenance are
  retained even when an endpoint receives a semantic link.
- Context gating is applied before Claims from different papers are assembled.
- Disconnected but relevant Claims may be supplied as evidence. Synthesis must
  state when the literature does not support the connection between them.

## Indexing extension

Claim extraction should emit one Claim for each directly supported relationship.
If a passage explicitly states `A causes B, which causes C`, it may emit `A -> B`
and `B -> C`, both citing that passage. If `B -> C` is merely plausible, it must
not be emitted.

After ordinary conservative State canonicalization, a separate maintenance step
may propose semantic links among retained States. Exact aliases are deterministic.
Embedding retrieval generates candidates. Ambiguous candidates require explicit
adjudication and remain unlinked when uncertain.

## Query extension

Ordinary exact paths remain available. In parallel, the query system builds a
bounded evidence subgraph from Context-compatible candidate Claims. Selection
maximizes coverage of independently parsed query requirements while penalizing
redundancy. Exact paths and verified semantic links improve organization, but
lack of a path does not by itself remove a directly relevant Claim.

The report must distinguish:

- exact scientific Claim edges;
- vocabulary/hierarchy links;
- connected mechanism chains;
- relevant disconnected evidence;
- requested requirements for which no evidence was selected.
# Status

The completed 10-paper gate and the decision not to expand are documented in `evaluation/atomic_evidence_subgraph/BENCHMARK.md`.

