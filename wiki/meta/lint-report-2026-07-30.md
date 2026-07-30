---
type: meta
title: "Lint Report 2026-07-30"
status: current
created: 2026-07-30
updated: 2026-07-30
tags: [meta, lint]
---

# Wiki Lint — 2026-07-30 (vault restructure)

Run as part of the full vault restructure (branch `docs/vault-restructure`). Method: extract all `[[wikilinks]]` outside code blocks, resolve Obsidian-style (path form, relative form, bare basename, case-insensitive, alias/heading stripped).

## Before restructure

- 87 pages · 545 wikilinks · **0 broken**
- Orphans: 3 real (`concepts/Aggregator-Strangler-Fig`, `concepts/Graphify-Shadow-Nodes`, `meta/lint-report-2026-05-06`) + 2 structural (`index.md`, `CLAUDE.md`)
- `index.md` frozen at 2026-05-05: listed 9 of 25 ADRs, 7 of 14 concepts
- `decisions/_index` omitted ADR-014/017; `concepts/_index` listed 8 of 14
- 13 pages missing `status` frontmatter; 12 module pages carried a lying duplicate `last_updated: 2026-05-05`
- ADR-011 wiki-vs-docs numbering collision open since 2026-05-15

## After restructure

- 92 pages · ~600 wikilinks · **0 broken**
- Orphans: only structural (`index.md`, `CLAUDE.md`) — all content pages reachable
- All `_index` pages complete and current; `meta/_index.md` created
- ADR namespace unified: wiki/decisions is the single home, ADR-001–027 (docs ADR-011/012 → ADR-026/027 with `renumbered_from` provenance)
- `status` added to all nav/meta pages; duplicate `last_updated` fields removed

## Still open (deliberate, tracked in hot.md / action plan)

- `components/`, `dependencies/`, `questions/` remain stubs (candidates: endpoint tables split out of the 3 oversized module pages; infra dependency pages for postgres/timescale/redis/rabbitmq)
- Atomicity: `modules/trading-engine.md` (~2.2k words), `modules/api-gateway.md` (~2.0k), `modules/bybit-connector.md` (~1.6k), `ADR-013` (plan-in-an-ADR)
- Stale content pages not yet rewritten: `modules/frontend.md`, `modules/risk-metrics-service.md`, `modules/ml-retraining-service.md`, `concepts/Validated-Symbols.md`, `concepts/Trading-Mode-Flags.md`, `sources/progress.md` (summary current to 2026-05-05)
