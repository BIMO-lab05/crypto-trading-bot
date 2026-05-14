---
type: concept
status: proposal
tags: [tooling, graphify, knowledge-graph]
created: 2026-05-06
updated: 2026-05-06
---

# Graphify Shadow Nodes (Wikilink Resolution Gap)

> Proposal / known-gap note for the `/graphify` wiki extraction. Not implemented.

## Symptom

After running `/graphify wiki/`, the resulting graph splits into many disconnected components even though Obsidian renders all wikilinks as resolved. As of 2026-05-06: 24 communities, 19 connected components on 264 nodes.

Cross-cluster paths that *should* exist do not. Example:

```
Aspirational vs Real  -- (no path) -->  module_trading_engine
```

even though `wiki/concepts/Aspirational-vs-Real.md` contains `[[../modules/trading-engine]]` and the module page exists.

## Why

The graphify subagent prompt asks for node IDs of the form `{stem}_{entity}`. When a concept page contains a wikilink `[[trading-engine]]`, the subagent processing that concept page emits an edge to a *new* node with id `aspirational_trading_engine_ref` (label `trading-engine (ref)`) — scoped to its own source file. The canonical module node `module_trading_engine` is emitted by a *different* subagent processing `wiki/modules/trading-engine.md`.

Result: every wikilink to a page outside the current chunk creates a **shadow node** instead of pointing at the canonical one. Concept pages link only to shadows; module pages live in their own connected component.

This is a wiki-extraction artifact; in code-extraction (AST mode) the issue does not occur because import resolution gives canonical IDs.

## Cost

- `god_nodes` over-weights canonical module pages (still ranked correctly, but graph diameter is misleading)
- `shortest_path` queries between concept and module fail spuriously
- Community detection inflates community count (16 → 24 across runs)
- "Surprising connections" misses the most useful cross-cluster bridges

## Possible fixes

1. **Post-extraction merge pass.** After all subagents complete, deduplicate nodes by normalized label match. Any node whose label matches a canonical module/ADR/flow exactly (modulo `(ref)` suffix and `(referenced)` suffix) merges into the canonical node, redirecting all incident edges.
2. **Pre-extraction wikilink target table.** Before dispatching subagents, scan all pages once to build a `wikilink_target → canonical_node_id` map; pass it to every subagent so they emit canonical IDs directly.
3. **Manual canonical hint in subagent prompt.** Already partially done in our chunk 3 prompt ("use `module_trading_engine`"). Hard to keep in sync as wiki grows.

Option 1 is cheapest; option 2 produces the highest-fidelity graph.

## Decision

Defer. Documented here so future graphify runs do not waste time treating disconnected components as a structural finding.

## Related

- [[../decisions/ADR-012-http-not-events]] (was the trigger that surfaced the gap)
- `graphify-out/GRAPH_REPORT.md` — components count
