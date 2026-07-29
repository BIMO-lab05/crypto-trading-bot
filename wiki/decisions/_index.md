---
type: meta
title: "Decisions Index"
created: 2026-05-05
updated: 2026-07-29
tags: [index, decisions]
---

# Decisions

ADRs and design choices, captured from progress.md, CLAUDE.md, and code archaeology.

## Architecture

- [[ADR-001-LSTM-removed]] — LSTM god-class deleted; GRU is sole price predictor
- [[ADR-002-trading-engine-lifespan-refactor]] — `lifespan()` split into composed `@asynccontextmanager`s
- [[ADR-003-bcrypt-sha256-prehash]] — switch to `bcrypt_sha256` for >72-byte password resilience

## Operations

- [[ADR-004-paper-trading-default]] — paper-trading mode is repo default; LIVE requires 4-flag alignment
- [[ADR-005-emergency-stop-file-flag]] — `EMERGENCY_STOP` file gate alongside admin endpoint
- [[ADR-006-mainnet-prices-paper-orders]] — current dual-mode contract: real prices, simulated orders
- [[ADR-007-no-v1-api-prefix]] — gateway routes drop `/v1/` prefix

## Tooling

- [[ADR-008-conventional-commits]] — `feat(service): ...`, `fix(service): ...`
- [[ADR-009-docker-compose-unified-canonical]] — `docker-compose.unified.yml` is canonical, plain `docker-compose.yml` is incomplete

## Risk

- [[ADR-010-max-risk-per-trade-paper-bump]] — `max_risk_per_trade` 0.02 → 0.10 in paper mode; cap now CLAMPS (not rejects) + hard 2% floor in LIVE (`min(cap,0.02)`)
- [[ADR-011-paper-deterministic-execution]] — paper-trading fills with zero slippage / zero latency / always-filled; do not trust paper P&L for edge (accounting overhauled — see ADR-018)
- [[ADR-019-kill-switch-equity-and-streak]] — kill switch fed equity not cash; consecutive-loss streak only on closes; daily-loss breaker auto-rolls per UTC day

## Trading engine (2026-07-28/29 fix campaign)

- [[ADR-018-paper-engine-accounting-overhaul]] — side-aware close accounting, `reduce_only` rejects instead of flipping, `position_id` targeting, partial close + DCA scale-in
- [[ADR-020-directional-consensus-gate]] — consensus counts only indicators voting the chosen direction; agreement-based confidence; MACD aligned to TA 5-35-5
- [[ADR-021-ta-data-integrity-gate]] — mainnet-only + candle validation + drop still-forming + interval normalization; testnet-pollution DB repair
- [[ADR-023-bybit-request-signing-fix]] — sign the exact compact bytes transmitted (fixes retCode 10004 on every authenticated POST)
- [[ADR-024-portfolio-manager-mirrors-engine]] — mirror the engine's authoritative cash/equity, side-aware P&L, no spot-buy reconstruction

## Platform / security

- [[ADR-022-mode-gated-api-auth]] — control-endpoint auth enforced in LIVE/prod, open in local paper, `REQUIRE_API_AUTH` override; real method-aware rate-limit enforcement
- [[ADR-025-notification-real-delivery-default]] — `NOTIFICATION_TEST_MODE` default flipped from `record` to `''` (real delivery)

## Architecture (cont.)

- [[ADR-016-http-not-events]] — service mesh is synchronous HTTP end-to-end; documented RabbitMQ topics are fiction *(renumbered from ADR-012 on 2026-05-15 — collision with `docs/decisions/ADR-012-extended-backtest-disposition.md`; see v1.0 audit INT-01)*

> **Namespace policy (added 2026-05-15):** `wiki/decisions/ADR-NNN.md` is a separate namespace from `docs/decisions/ADR-NNN.md`. To avoid xref ambiguity, **wiki ADR numbers must not duplicate any docs/decisions/ADR number**. When a new docs ADR lands, check this index for collisions and renumber if needed. Latent collision still open: wiki `ADR-011-paper-deterministic-execution` vs `docs/decisions/ADR-011-monitoring-disposition` — flagged but not yet renumbered (more xrefs to update; will fix in v1.1 cleanup).

## Strategy

- [[ADR-013-strategy-rebuild-plan]] — phased rebuild grounded in 2026 crypto-bot research; kill 22 of 25 strategy files; honest walk-forward harness; sqzmom + ADX + volume + 4h-alignment as the one canonical strategy

## Sizing

- [[ADR-015-ensemble-sizing-cascade]] — bind ensemble sizing to `settings.max_risk_per_trade` + expose floor/multiplier; defaults push trades to 5-10 % to honor ADR-010 intent
