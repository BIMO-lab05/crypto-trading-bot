---
type: meta
title: "Operation Log"
created: 2026-05-05
updated: 2026-07-30
tags: [meta, log]
status: current
---

# Operation Log

Append-only. New entries at TOP. Never edit past entries.

## 2026-07-30 — Doc consolidation pass (merges)

- **20 redundant reference docs merged into survivors** across services (trading-engine 7, risk-metrics 3, bybit-connector/market-data/portfolio-manager/sentiment 1 each), infrastructure (helm/k8s/monitoring 7), frontend (PriceChart quartet → `frontend/PRICECHART.md`), backtesting, docs/testing. Absorbed sources archived under `docs/archive/`; every survivor carries a "Merged from … 2026-07-30" marker.
- **components/ un-stubbed**: [[components/Volume-Profile]] + [[components/Multi-Timeframe-Blender]] created from the trading-engine integration guides.
- **~25 factual errors corrected during merge**: wrong ports in six service docs (e.g. portfolio-manager "8006", bybit-connector "8000", market-data "8003"), split-compose commands → unified, missing LIVE_TRADING_ACK in LIVE-flip steps, "$10,000" paper balance → $100, DOGEUSDT in SQZMOM whitelist flagged vs validated set, k8s `replicas: 3` unsafe for the singleton engine.
- **Credentials scrubbed**: printed Grafana defaults removed from 6+ infra docs and `docs/operations/MONITORING_GUIDE.md` — default is burned, rotate it.
- T1.2 kill criterion (baseline-worse-by-0.5σ) ported into `docs/runbooks/forward-paper-test.md`.

## 2026-07-30 — Vault restructure + index resync

- **Repo docs restructured** (branch `docs/vault-restructure`): ~190 historical session/test/phase reports (Nov 2025 – May 2026) moved from repo root, `docs/`, `services/*/`, `infrastructure/`, `frontend/`, `scripts/`, `backtesting/`, `reports/` into `docs/archive/` (by theme: sessions-2025, testing-2025, strategy-2025, infrastructure-2025, audits, superseded, services/<name>, …). Living guides re-homed into `docs/{setup,operations,testing,security,deploy,reference,ml,architecture,strategy}/`. Repo root now carries 6 deliberate md files (was 73). 5 dead/broken-index files staged in `_to_delete/docs-cleanup-2026-07-30/`.
- **ADR namespace unified**: `docs/decisions/` merged into `wiki/decisions/` — docs ADR-011/012 renumbered **ADR-026/027** with provenance notes; 2026-05-15 collision policy closed. Wiki is the single ADR home (001–027).
- **Wiki resync**: `index.md` rebuilt (was frozen at 2026-05-05 listing 9 of 25 ADRs and 7 of 14 concepts); `concepts/_index` lists all 14 (orphans Aggregator-Strangler-Fig, Graphify-Shadow-Nodes now linked); `decisions/_index` adds ADR-014/017/026/027; `meta/_index.md` created; `hot.md` refreshed to 2026-07-30 (phase 20–24 re-scope, OP-14/15, `fb764d5`); module pages' lying duplicate `last_updated: 2026-05-05` removed.
- **False claims fixed**: CLAUDE.md `_archive_lstm/` claim corrected (dir doesn't exist; LSTM spans 10+ files); "Last active Jan 2026" removed; sentiment "still runs in compose" → `analytics` profile; auto-trader resume semantics corrected **against code** (`auto_trader.py`: file-halt exits loop, no auto-restart) in CLAUDE.md and [[concepts/Auto-Trader]]; [[concepts/ML-Status]] and [[modules/sentiment-analysis-service]] updated.
- **New source page**: [[sources/Archive-Distillation-2026-07-30]] — every load-bearing fact rescued from archived reports (walk-forward-tests-wrong-strategy, log growth, UPSERT failure, SOL-heavy revert check, Grafana creds, grid/ML verdicts, …).
- **Graph hygiene**: `.graphifyignore` now excludes `docs/archive/`, `_to_delete/`, `.planning/{milestones,debug}/`. `docs/architecture/SYSTEM_OVERVIEW.md` rewritten from [[modules/Architecture-Overview]] (was 2025-10-30: 6 services, wrong ports, fictional event bus).
- Lint: [[meta/lint-report-2026-07-30]] — 545/545 wikilinks resolved pre-restructure; re-verified post-edit.

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
