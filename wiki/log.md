---
type: meta
title: "Operation Log"
created: 2026-05-05
updated: 2026-08-19
tags: [meta, log]
status: current
---

# Operation Log

Append-only. New entries at TOP. Never edit past entries.

## 2026-08-19 — Doc resync against August data (batteries, cost model, risk caps)

- **Edge results propagated into the docs.** CLAUDE.md §2 split into 2a (legacy indicator strategies) and 2b (pre-registered kill-test batteries); README gains a `Strategy status` section. Headline now stated once and consistently: **twelve strategy families, zero survivors** — 7 legacy + 5 pre-registered, plus the chance-level GRU ensemble. (`progress.md`'s "nine families" is family-*runs* across the two batteries, 4 + 5; only 5 distinct candidates were tested. Counted explicitly so the headline stops drifting.) Battery #1 (2026-08-17, 8 variants) rejected xs_momentum / vol_breakout / funding_carry / lf_trend; battery #2 (2026-08-18, 17 variants) re-ran those four with more variants, added pairs_statarb, and rejected all five.
- **Gate semantics written down** so a Gate 1 number is never quoted as a result: Gate 1 is a cost hurdle (gross edge ≥ 2× taker cost), Gate 2 is statistical (DSR ≥ 0.95 **and** ≥ 0.7 of CPCV paths positive). `lf_trend` cleared Gate 1 on 4/5 variants at `ratio_taker` up to 15.511 and still died on Gate 2 — outlier trades, not a distribution.
- **Trials floor documented as a ratchet**: `backtesting/edge_lab/trial_ledger.json` is append-only, DSR deflates at `max(effective_floor, n_paths)`, floor went 16 → 21 (battery #2 ran floor 21 against 45 CPCV paths, so the path count bound), ledger now 30 rows. Recorded in CLAUDE.md, README, [[hot]], [[overview]] as "must not be reset".
- **Risk caps corrected in README** — the table still read 2% per-trade / 5% daily / 10% drawdown-halt / 5 concurrent positions / 1× leverage. Actual `trading-engine/app/config.py`: `max_risk_per_trade` **0.10** fraction (2% hard in LIVE), `max_daily_loss_pct` **12.0**, `max_position_size_pct` **10.0**, `max_total_exposure_pct` **80.0**. There is no drawdown-halt setting and no concurrent-position count cap — concurrency is bounded by total exposure; the tiered drawdown triggers (5/10/15/20%) live in `kill_switch.py`. Two figures that were simply wrong for months.
- **`DEFAULT_LEVERAGE` 10.0 → 1.0 recorded** ([[concepts/Risk-Model]] said 10.0). Dropped 2026-08-04 per AUDIT §6.4/H1 — at 10× the notional formula multiplied the 10% per-trade cap back to ~100% of balance per trade.
- **Cost-model timeline pinned to commits** because "gross of slippage" had become wrong: slippage `fb45efe` (2026-08-03), correct fee accounting from the clean-data epoch 2026-08-12T13:47:20Z, perp funding on closes `b9fadc0` (2026-08-18, `paper_funding_enabled` default **true**). A P&L figure is only net of what had shipped when it was measured.
- **`_archive_lstm/` flip-flop resolved at the root cause.** The 2026-07-30 entry below recorded "dir doesn't exist"; CLAUDE.md was corrected on 2026-08-03 to "does exist". Both were half-right: `.gitignore:248` excludes `services/ml-prediction-service/**/_archive_lstm/`, so it exists in the operator's working copy (27 files, 41 MB) and is absent from every fresh clone, container, and CI run. Past entries left intact per append-only rule; the correction is filed here, in [[hot]], and in [[concepts/ML-Status]]. Also fixed the path everyone had been copying: the LSTM import is at `app/models/ensemble_model.py:15`, not `app/ensemble_model.py:15` (line number was always right).
- **Smaller corrections**: emergency-stop path in README was "repo root" → actually `safety/EMERGENCY_STOP` with a two-step resume; notification-service channel list 3 → 5 (telegram/email/slack/sms/dashboard) in CLAUDE.md, README, [[overview]]; symbol universes separated into traded 5 / ingested 14 / research-pinned 30; GRU staleness ~5 months → ~8; ADR range 001–027 → 001–028 in [[index]] with ADR-012's renumbering to ADR-016 noted; the archived `RESEARCH_PLAN_2026-04-29.md` link replaced; `backtesting/edge_lab/`, `shared/account.py` and `safety/` added to the README layout and the index repo map.
- **Known contradiction now stated rather than repeated**: README's testing gotcha told readers to run api-gateway tests in-container, but that image ships no `tests/` (RES-10). Neither documented path works today; targeted host runs are the only one that does.

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
