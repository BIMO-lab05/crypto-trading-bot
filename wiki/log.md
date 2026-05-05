---
type: meta
title: "Operation Log"
created: 2026-05-05
updated: 2026-05-05
tags: [meta, log]
---

# Operation Log

Append-only. New entries at TOP. Never edit past entries.

## 2026-05-05 — Stage 0 ingest

- Repo CLAUDE.md updated with Wiki Knowledge Base block (path, lookup order, lint reminder)
- Flagged stale CLAUDE.md reference to `docs/architecture/DECISIONS.md` (file doesn't exist; ADRs now in `wiki/decisions/`)
- Ingested: `docs/architecture/SYSTEM_OVERVIEW.md` (stale, flagged), `docs/architecture/SERVICE_CONTRACTS.md` (stale, flagged), `progress.md` (running log)
- ADRs filed: ADR-001 (LSTM removed), ADR-002 (lifespan refactor), ADR-003 (bcrypt_sha256), ADR-004 (paper-trading default), ADR-005 (EMERGENCY_STOP file flag), ADR-006 (mainnet+paper dual mode), ADR-007 (no /v1/ prefix), ADR-008 (conventional commits), ADR-009 (unified compose)
- Concept pages added: `Message-Queue-Topics` (verify in code), `Test-Setup-Gotchas`
- Source summaries: SYSTEM_OVERVIEW, SERVICE_CONTRACTS, progress
- Concepts/decisions indexes updated
- Stage 1 (per-service agents) pending in next operation

## 2026-05-05 — Vault scaffolded

- Mode B (Repository) + concepts/ from Mode E
- Wiki placed under `wiki/` to avoid polluting code repo
- Created: `index.md`, `log.md`, `hot.md`, `overview.md`, `CLAUDE.md`
- Folders: modules, components, decisions, dependencies, flows, concepts, sources, questions, meta, .raw, _templates
- Module stubs: 12 (11 backend services + frontend)
- Concept seeds: Trading-Mode-Flags, Risk-Model, ML-Status, Validated-Symbols, Auto-Trader, Feature-Flags
- Flow seeds: Signal-Pipeline, Order-Lifecycle, Emergency-Stop
- CSS snippet: `.obsidian/snippets/vault-colors.css`
- Templates for module / decision / flow / concept / source
- MCP verified live (Local REST API @ 27123 reachable from WSL)
- No ingests yet
