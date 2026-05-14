---
type: meta
title: "Decisions Index"
created: 2026-05-05
updated: 2026-05-05
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

- [[ADR-010-max-risk-per-trade-paper-bump]] — `max_risk_per_trade` 0.02 → 0.10 in paper mode for $100 balance min-notional clearance; LIVE remains ≤ 2%
- [[ADR-011-paper-deterministic-execution]] — paper-trading fills with zero slippage / zero latency / always-filled; do not trust paper P&L for edge

## Architecture (cont.)

- [[ADR-012-http-not-events]] — service mesh is synchronous HTTP end-to-end; documented RabbitMQ topics are fiction

## Strategy

- [[ADR-013-strategy-rebuild-plan]] — phased rebuild grounded in 2026 crypto-bot research; kill 22 of 25 strategy files; honest walk-forward harness; sqzmom + ADX + volume + 4h-alignment as the one canonical strategy

## Sizing

- [[ADR-015-ensemble-sizing-cascade]] — bind ensemble sizing to `settings.max_risk_per_trade` + expose floor/multiplier; defaults push trades to 5-10 % to honor ADR-010 intent
