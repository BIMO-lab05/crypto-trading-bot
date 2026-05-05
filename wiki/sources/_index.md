---
type: meta
title: "Sources Index"
created: 2026-05-05
updated: 2026-05-05
tags: [index, sources]
---

# Sources

One summary page per ingested document. Page records origin, current status (live/stale), key claims, and links into the wiki where material was filed.

## Ingested

- [[SYSTEM_OVERVIEW]] — `docs/architecture/SYSTEM_OVERVIEW.md` (stale)
- [[SERVICE_CONTRACTS]] — `docs/architecture/SERVICE_CONTRACTS.md` (stale)
- [[progress]] — `progress.md` (running log)

## Pending

- `CLAUDE.md` (project root) — explicitly NOT ingested as a wiki page; treated as authoritative project rule file. Wiki concepts derive from it.
- `docs/REVIVAL_PLAN_2026-05-02.md`
- `docs/PHASE3_ML_AI_ROADMAP.md`
- `docs/MONITORING_GUIDE.md`
- `docs/SECURITY_AUDIT_REPORT.md`
- `services/<each>/` — handled by Stage 1 parallel agents
- `frontend/src/` — Stage 2

## Skipped intentionally

- 69 root `*.md` legacy session/test reports — too granular, low signal-to-noise. Leave in repo, not surfaced via wiki. Filter Obsidian search by `tag:` if needed.
