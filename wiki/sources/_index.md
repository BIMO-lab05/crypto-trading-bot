---
type: meta
title: "Sources Index"
status: current
created: 2026-05-05
updated: 2026-07-30
tags: [index, sources]
---

# Sources

One summary page per ingested document. Page records origin, current status (live/stale), key claims, and links into the wiki where material was filed.

## Ingested

- [[Archive-Distillation-2026-07-30]] — load-bearing facts rescued from ~190 reports archived to `docs/archive/` during the 2026-07-30 vault restructure
- [[SYSTEM_OVERVIEW]] — `docs/architecture/SYSTEM_OVERVIEW.md` *(source was stale; the doc was rewritten from [[../modules/Architecture-Overview|Architecture-Overview]] on 2026-07-30)*
- [[SERVICE_CONTRACTS]] — original now at `docs/archive/superseded/SERVICE_CONTRACTS.md` (stale; live OpenAPI at `:8000/openapi.json` is authoritative)
- [[progress]] — `progress.md` (running log; summary current to 2026-05-05 — refresh due)

## Completed (previously "pending")

- Stage 1 per-service ingest — done (see `.raw/agent-reports/` + [[../modules/_index|module pages]], rebuilt 2026-07-29)
- `docs/REVIVAL_PLAN_2026-05-02.md` — archived; surviving facts in [[Archive-Distillation-2026-07-30]]
- `docs/PHASE3_ML_AI_ROADMAP.md` — archived (superseded by V0 findings + RESEARCH_PLAN_2026-04-29)
- `docs/SECURITY_AUDIT_REPORT.md` — archived to `docs/archive/audits/`; open findings tracked in [[Archive-Distillation-2026-07-30]]

## Pending

- `FIXES_2026-07-28_COMPREHENSIVE.md` + `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` (repo root) — key decisions already filed as ADR-018..025; full source-page ingest pending. **Keep at repo root until GSD OP-07 triage closes** (`.planning/STATE.md` references them there); then move to `docs/audits/`.
- `docs/operations/MONITORING_GUIDE.md` — living guide, ingest summary pending
- `frontend/src/` — Stage 2

## Skipped intentionally

- Root legacy session/test reports — moved to `docs/archive/` on 2026-07-30 (were: 69+ files at repo root). Excluded from the Graphify graph.
- `CLAUDE.md` (project root) — NOT ingested as a wiki page; authoritative project rule file. Wiki concepts derive from it.
