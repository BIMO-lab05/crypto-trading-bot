---
type: meta
title: "Operation Log"
created: 2026-05-05
updated: 2026-07-29
tags: [meta, log]
---

# Operation Log

Append-only. New entries at TOP. Never edit past entries.

## 2026-07-29 — Fix campaign + wiki resync

- **Code**: two-day fix campaign landed. 2026-07-28: paper-engine accounting overhaul, TA data-integrity + indicator confidence fixes, DB testnet-pollution repair, frontend API/UX fixes, directional-consensus gate, mean-reversion R/R. 2026-07-29: security audit (mode-gated auth, real rate limiting, Bybit signing fix), portfolio/risk/notification/data-pipeline hardening, portfolio-manager engine-mirror, notification real-delivery default. Commits `882f4d0`..`7de6803`.
- **Ops**: paper book reset to clean $100 (wiped 43 pre-fix positions / 61 trades / negative cash), engine restarted, auto-trader armed, kill-switch clear. Telegram delivery verified live.
- **Wiki**: concepts/ (Paper-Trading-Internals, Risk-Model, Feature-Flags, Aggregator-Strangler-Fig), all changed service modules, Architecture-Overview (RabbitMQ→REST-only correction), flows (Order-Lifecycle, Signal-Pipeline, Emergency-Stop), and ADR-010/011/006 updated against current code. New ADR-018..025 filed for the campaign's decisions. hot.md + overview.md refreshed.
- **Reports**: `FIXES_2026-07-28_COMPREHENSIVE.md`, `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` at repo root.

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
