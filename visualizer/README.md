# ClimateKG Visualizer

Local web application for inspecting indexed papers and saved query traces.

## Run

From the repository root:

```powershell
python .\visualizer\server.py --port 8765
```

Open <http://127.0.0.1:8765>.

The server reads finalized paper artifacts from `climatekg/runtime/data/papers`, finalized paper-specific prompt replays from `climatekg/runtime/prompt_examples`, and query reports from `climatekg/runtime/outputs`. It does not modify those artifacts. Embedding arrays are removed from browser responses to keep the interface responsive.

## Views

- **Graph** shows claims as source-state to outcome-state relationships. Select a node or claim to inspect its scope, conditioning Facets, and SourceBlocks.
- **Entities** provides searchable tables for Claims, Contexts, Facets, Transitions, States, and SourceBlocks.
- **Query traces** shows the structured question, Context similarity, Claim gating scores, selected paths, grounded synthesis, warnings, and cited evidence.

Every displayed ClimateKG ID is interactive when its referenced object is available.
