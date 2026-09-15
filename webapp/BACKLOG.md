# Deferred Work

The next corpus task is to run the finalized indexing configuration on more papers, record per-stage and per-LLM-call timing, and rebuild the Parquet graph used by this application. It is intentionally deferred while the working webapp prototype is being developed.

Before treating land-use planning output as a recommendation, add and evaluate:

- explicit candidate intervention generation and constraint handling;
- comparison of proposed changes against the watershed's current land-cover composition;
- feasibility, trade-off, and adverse-effect checks;
- expert review and calibrated abstention tests on out-of-corpus watersheds;
- a larger, versioned literature corpus.

The current planning workflow returns transferable literature evidence and limitations. It is a decision-support prototype, not an automatic prescription system.
