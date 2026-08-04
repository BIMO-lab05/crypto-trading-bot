---
type: meta
title: "Wiki Index"
status: current
created: 2026-05-05
updated: 2026-07-30
tags: [meta, index]
---

# Crypto Trading Bot — Wiki Index

Master catalog. Updated on every ingest.

## Folders

- [[modules/_index|Modules]] — per-service pages (11 microservices + frontend)
- [[components/_index|Components]] — reusable engine sub-systems (Volume-Profile, Multi-Timeframe-Blender)
- [[decisions/_index|Decisions]] — ADRs 001–027 (single canonical ADR home since 2026-07-30)
- [[dependencies/_index|Dependencies]] — external packages, models, infra *(stub — unpopulated)*
- [[flows/_index|Flows]] — request paths, signal pipeline, order lifecycle
- [[concepts/_index|Concepts]] — strategy patterns, ML lifecycle, risk model (14 pages)
- [[sources/_index|Sources]] — summaries of ingested raw documents
- [[questions/_index|Questions]] — filed Q&A from sessions *(stub — unpopulated)*
- [[meta/_index|Meta]] — lint reports, dashboards

## Top-level pages

- [[overview|Overview]] — executive summary
- [[hot|Hot Cache]] — most recent context (~500 words)
- [[log|Log]] — append-only operation log

## Quick links

### Architecture
- [[modules/Architecture-Overview|Architecture Overview]]
- [[flows/Signal-Pipeline|Signal Pipeline]]
- [[flows/Order-Lifecycle|Order Lifecycle]]
- [[flows/Emergency-Stop|Emergency Stop]]

### Concepts (all 14)
- [[concepts/Trading-Mode-Flags|Trading Mode Flags]]
- [[concepts/Risk-Model|Risk Model]]
- [[concepts/ML-Status|ML Status]]
- [[concepts/Auto-Trader|Auto-Trader]]
- [[concepts/Feature-Flags|Feature Flags]]
- [[concepts/Validated-Symbols|Validated Symbols]]
- [[concepts/Paper-Trading-Internals|Paper Trading Internals]]
- [[concepts/State-Persistence|State Persistence]]
- [[concepts/HTTP-Service-Mesh|HTTP Service Mesh]]
- [[concepts/Message-Queue-Topics|Message Queue Topics]]
- [[concepts/Aspirational-vs-Real|Aspirational vs Real]]
- [[concepts/Aggregator-Strangler-Fig|Aggregator Strangler Fig]]
- [[concepts/Graphify-Shadow-Nodes|Graphify Shadow Nodes]]
- [[concepts/Test-Setup-Gotchas|Test Setup Gotchas]]

### Decisions (ADRs 001–027)

Founding set (2026-05-05):
- [[decisions/ADR-001-LSTM-removed|ADR-001 LSTM removed]] · [[decisions/ADR-002-trading-engine-lifespan-refactor|ADR-002 lifespan refactor]] · [[decisions/ADR-003-bcrypt-sha256-prehash|ADR-003 bcrypt_sha256]] · [[decisions/ADR-004-paper-trading-default|ADR-004 paper default]] · [[decisions/ADR-005-emergency-stop-file-flag|ADR-005 EMERGENCY_STOP flag]] · [[decisions/ADR-006-mainnet-prices-paper-orders|ADR-006 mainnet+paper]] · [[decisions/ADR-007-no-v1-api-prefix|ADR-007 no /v1/]] · [[decisions/ADR-008-conventional-commits|ADR-008 conventional commits]] · [[decisions/ADR-009-docker-compose-unified-canonical|ADR-009 unified compose]]

May 2026 (strategy rebuild era):
- [[decisions/ADR-010-max-risk-per-trade-paper-bump|ADR-010 paper risk-cap bump]] · [[decisions/ADR-011-paper-deterministic-execution|ADR-011 deterministic paper fills]] · [[decisions/ADR-013-strategy-rebuild-plan|ADR-013 strategy rebuild plan]] · [[decisions/ADR-014-multi-tf-blender-threshold-mismatch|ADR-014 multi-TF threshold]] · [[decisions/ADR-015-ensemble-sizing-cascade|ADR-015 ensemble sizing]] · [[decisions/ADR-016-http-not-events|ADR-016 HTTP not events]] · [[decisions/ADR-017-risk-metrics-paper-mode-alignment|ADR-017 risk-metrics paper alignment]]

July 2026 fix campaign:
- [[decisions/ADR-018-paper-engine-accounting-overhaul|ADR-018 accounting overhaul]] · [[decisions/ADR-019-kill-switch-equity-and-streak|ADR-019 kill-switch equity+streak]] · [[decisions/ADR-020-directional-consensus-gate|ADR-020 consensus gate]] · [[decisions/ADR-021-ta-data-integrity-gate|ADR-021 data-integrity gate]] · [[decisions/ADR-022-mode-gated-api-auth|ADR-022 mode-gated auth]] · [[decisions/ADR-023-bybit-request-signing-fix|ADR-023 Bybit signing fix]] · [[decisions/ADR-024-portfolio-manager-mirrors-engine|ADR-024 PM mirrors engine]] · [[decisions/ADR-025-notification-real-delivery-default|ADR-025 real notifications]]

Merged from docs/decisions (2026-07-30):
- [[decisions/ADR-026-monitoring-disposition|ADR-026 monitoring disposition]] · [[decisions/ADR-027-extended-backtest-disposition|ADR-027 extended-backtest disposition]]

### Sources
- [[sources/Archive-Distillation-2026-07-30|Archive Distillation 2026-07-30]] — load-bearing facts rescued from archived reports
- [[sources/progress|progress.md summary]] · [[sources/SYSTEM_OVERVIEW|SYSTEM_OVERVIEW (stale source)]] · [[sources/SERVICE_CONTRACTS|SERVICE_CONTRACTS (stale source)]]

### Meta
- [[meta/lint-report-2026-07-30|Lint report 2026-07-30]] (latest) · [[meta/lint-report-2026-05-06|Lint report 2026-05-06]]

## Where things live (repo map)

- Living how-to/reference docs: `docs/` (setup, operations, testing, security, deploy, strategy, reference, ml, architecture)
- Historical reports (Nov 2025 – May 2026): `docs/archive/` — excluded from the Graphify graph
- Planning state (GSD-managed, machine-consumed): `.planning/` — do not hand-edit
- Scheduled-task outputs: `reports/{edge-audits,premarket,runtime-checks,walk-forward,circuit-breaker}/`
