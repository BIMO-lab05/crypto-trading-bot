---
type: meta
title: "Lint Report 2026-05-06"
created: 2026-05-06
updated: 2026-05-06
tags: [meta, lint]
status: developing
---

# Lint Report: 2026-05-06

Run after ADR-011 + ADR-012 additions and graphify wiki extraction.

## Summary
- Pages scanned: 61 (excluding `.raw/` and `_templates/`)
- Issues found: 3
- Auto-fixed: 0
- Needs review: 3

## Dead Links
- `wiki/CLAUDE.md` → `[[Note Name]]` — placeholder in cross-project hint example block; intentional doc artifact, not a real broken link. **Action: leave or rewrite as fenced code-only.**

## Orphan Pages
- `concepts/State-Persistence.md` — no inbound wikilinks. Page describes how each service persists state (DB/Redis/in-mem). **Action: link from `modules/_index.md` cross-cutting list and from at least one module page that exemplifies the gotcha (likely `trading-engine` or `portfolio-manager`).**

## Frontmatter Gaps
- `wiki/CLAUDE.md` — no YAML frontmatter. Skill-doc not subject to wiki schema; **leave**.

## Stale Claims
- None new since previous ingest. Pre-existing STALE flags on `sources/SYSTEM_OVERVIEW.md`, `sources/SERVICE_CONTRACTS.md`, and `sources/progress.md` (stale Oct 2025 / Apr 2026 — flagged at ingest, not regressions).

## Cross-Reference Gaps
- ADR-012 (`HTTP-not-events`) is now linked by 3 concept pages and `decisions/_index.md`. No dangling refs remain.
- ADR-011 (`paper-deterministic-execution`) is linked by `concepts/Paper-Trading-Internals.md` and `decisions/_index.md`.

## Resolved this run
- `[[../decisions/ADR-012-http-not-events]]` — file was missing in 3 concept pages; **created** at `wiki/decisions/ADR-012-http-not-events.md`
- `[[../decisions/ADR-010-paper-deterministic-execution]]` — wikilink pointed to non-existent slug; **renamed in concept page to** `[[../decisions/ADR-011-paper-deterministic-execution]]` and **filed** ADR-011

## Address Validation
Skipped — DragonScale tooling not present (`scripts/allocate-address.sh` not found).

## Semantic Tiling
Skipped — `scripts/tiling-check.py` not present.

## Recommended next actions
1. Link `concepts/State-Persistence.md` from `modules/trading-engine.md` and `modules/portfolio-manager.md` (both have in-process state worth flagging there)
2. Re-run `/graphify --update wiki` to fold ADR-011 + ADR-012 into the knowledge graph and verify component bridge across the architecture-truths ↔ trading-engine-hub split
