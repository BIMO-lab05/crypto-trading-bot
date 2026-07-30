---
type: meta
title: "Decisions Index"
status: current
created: 2026-05-05
updated: 2026-07-30
tags: [index, decisions]
---

# Decisions

ADRs and design choices. **Single canonical ADR home since 2026-07-30** — the former `docs/decisions/` side-channel was merged in (its ADR-011/012 renumbered to [[ADR-026-monitoring-disposition|ADR-026]] / [[ADR-027-extended-backtest-disposition|ADR-027]]), resolving the namespace collision flagged 2026-05-15. Complete set: ADR-001 – ADR-027 (ADR-012 intentionally absent — renumbered to ADR-016 on 2026-05-15).

## Architecture

- [[ADR-001-LSTM-removed]] — LSTM god-class deleted; GRU is sole price predictor *(purge incomplete — see [[../concepts/ML-Status|ML-Status]])*
- [[ADR-002-trading-engine-lifespan-refactor]] — `lifespan()` split into composed `@asynccontextmanager`s
- [[ADR-003-bcrypt-sha256-prehash]] — switch to `bcrypt_sha256` for >72-byte password resilience
- [[ADR-016-http-not-events]] — service mesh is synchronous HTTP end-to-end; documented RabbitMQ topics are fiction *(renumbered from ADR-012 on 2026-05-15)*

## Operations

- [[ADR-004-paper-trading-default]] — paper-trading mode is repo default; LIVE requires 4-flag alignment
- [[ADR-005-emergency-stop-file-flag]] — `EMERGENCY_STOP` file gate alongside admin endpoint
- [[ADR-006-mainnet-prices-paper-orders]] — current dual-mode contract: real prices, simulated orders
- [[ADR-007-no-v1-api-prefix]] — gateway routes drop `/v1/` prefix
- [[ADR-026-monitoring-disposition]] — keep Tier-1 cron monitor, delete autonomous Tier-2; no unattended LLM ops *(merged from docs/decisions ADR-011, 2026-07-30)*

## Tooling

- [[ADR-008-conventional-commits]] — `feat(service): ...`, `fix(service): ...`
- [[ADR-009-docker-compose-unified-canonical]] — `docker-compose.unified.yml` is canonical, plain `docker-compose.yml` is incomplete
- [[ADR-027-extended-backtest-disposition]] — `run_extended_backtest.py` diverges from live aggregator; regime characterisation only, never edge measurement *(merged from docs/decisions ADR-012, 2026-07-30)*

## Risk

- [[ADR-010-max-risk-per-trade-paper-bump]] — `max_risk_per_trade` 0.02 → 0.10 in paper mode; cap now CLAMPS (not rejects) + hard 2% floor in LIVE (`min(cap,0.02)`)
- [[ADR-011-paper-deterministic-execution]] — paper-trading fills with zero slippage / zero latency / always-filled; do not trust paper P&L for edge (accounting overhauled — see ADR-018)
- [[ADR-019-kill-switch-equity-and-streak]] — kill switch fed equity not cash; consecutive-loss streak only on closes; daily-loss breaker auto-rolls per UTC day
- [[ADR-017-risk-metrics-paper-mode-alignment]] — risk-metrics-service aligned to paper-mode semantics (2026-05-19)

## Strategy & sizing

- [[ADR-013-strategy-rebuild-plan]] — phased rebuild grounded in 2026 crypto-bot research; kill 22 of 25 strategy files; honest walk-forward harness; sqzmom + ADX + volume + 4h-alignment as the one canonical strategy
- [[ADR-014-multi-tf-blender-threshold-mismatch]] — multi-timeframe blender threshold mismatch resolution
- [[ADR-015-ensemble-sizing-cascade]] — bind ensemble sizing to `settings.max_risk_per_trade` + expose floor/multiplier; defaults push trades to 5-10 % to honor ADR-010 intent

## Trading engine (2026-07-28/29 fix campaign)

- [[ADR-018-paper-engine-accounting-overhaul]] — side-aware close accounting, `reduce_only` rejects instead of flipping, `position_id` targeting, partial close + DCA scale-in
- [[ADR-020-directional-consensus-gate]] — consensus counts only indicators voting the chosen direction; agreement-based confidence; MACD aligned to TA 5-35-5
- [[ADR-021-ta-data-integrity-gate]] — mainnet-only + candle validation + drop still-forming + interval normalization; testnet-pollution DB repair
- [[ADR-023-bybit-request-signing-fix]] — sign the exact compact bytes transmitted (fixes retCode 10004 on every authenticated POST)
- [[ADR-024-portfolio-manager-mirrors-engine]] — mirror the engine's authoritative cash/equity, side-aware P&L, no spot-buy reconstruction

## Platform / security

- [[ADR-022-mode-gated-api-auth]] — control-endpoint auth enforced in LIVE/prod, open in local paper, `REQUIRE_API_AUTH` override; real method-aware rate-limit enforcement
- [[ADR-025-notification-real-delivery-default]] — `NOTIFICATION_TEST_MODE` default flipped from `record` to `''` (real delivery)

> **Namespace policy (2026-05-15, closed 2026-07-30):** wiki `decisions/` is now the ONLY ADR namespace. `docs/decisions/` no longer exists; its two ADRs were renumbered into this sequence as ADR-026/027 with `renumbered_from` provenance notes. New ADRs take the next free number here — no side-channels.
