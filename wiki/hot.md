---
type: meta
title: "Hot Cache"
status: current
created: 2026-05-05
updated: 2026-08-25
tags: [meta, hot]
---

# Recent Context

## Last Updated
2026-08-25. Account re-scaled to **$10,000 paper research scale** per [[decisions/ADR-029-account-size-10k-research-scale|ADR-029]] (operator-approved). Risk knobs UNCHANGED: 10%/trade (now $1,000), 12% daily breaker (now $1,200), 5% ensemble floor (now $500), LIVE 2% cap untouched ($200). Min-notional distortion gone — BTC/ETH mechanically tradeable again. Fees are bps-of-notional, so the flip creates NO edge. LIVE is no longer arithmetically blocked; the four deliberate flags are the only barrier — never cite arithmetic as the LIVE safety argument. DB reset + redeploy deferred until after the 2026-08-27 isolation harvest. Earlier: 2026-07-30 WIP settled (`fb764d5`); v1.3 phases re-scoped; wiki is the single ADR home.

## State (v1.3 "TA + Engine Correctness", executing, 3/9 phases)
- Paper mode, **$10,000 declared baseline (ADR-029, 2026-08-25; was $100)**, auto-trader armed, kill-switch clear. 8/9 services healthy; ml-prediction behind compose `ml` profile, sentiment behind `analytics` profile (neither starts by default).
- Phases 16–18 complete (validated-set re-audit; execution-cap enforcement; Bybit adapter contract fix). Next: Phase 19 (order reconciliation + idempotency).
- **2026-07-30 re-scope of phases 20–24**: 20 shrinks (SL/TP trigger eval existed since `0d0271c`), 21 shrinks (MACD/BB value drift already gone), 22 GROWS (22 price-domain `round(...,2)` sites across 7 files — `support_resistance_detector.py` was missed), 23 GROWS (LSTM footprint 10+ files; `_archive_lstm/` does not exist; third R² consumer in `scripts/check_ml_training_status.py`), 24 shrinks (3 of 4 premises dead).
- Operator backlog OP-01..OP-15. New: **OP-14** trading-engine image lacks PyJWT + `/app/shared` empty → in-container pytest collects zero tests; **OP-15** new `.dockerignore` would delete the 28-check accounting harness from the container on next rebuild.

## Key July facts (details: ADR-018..025 + [[log]])
- Paper accounting overhauled (side-aware closes; `reduce_only` rejects). Kill switch fed equity; daily-loss breaker rolls per UTC day. Consensus gate directional-only. TA mainnet-only + candle validation; DB testnet pollution repaired (118k rows demoted). Mode-gated API auth + real rate limiting; Bybit HMAC signing fixed. Portfolio-manager mirrors engine. Notifications deliver for real.

## Architecture correction
- **No live event bus.** Synchronous REST only; RabbitMQ deployed but nothing wires AMQP — see [[modules/Architecture-Overview]] and ADR-016.

## Open items / next
- Frontend has no login flow — blocks LIVE (auth open only in paper mode).
- Strategy profitability unproven — accumulate 2–4 weeks clean paper trades, evaluate DSR/CPCV before any LIVE talk. Walk-forward harness still tests `phase1_strategy_prod`, NOT the deployed ensemble (see [[sources/Archive-Distillation-2026-07-30]]).
- 9 trading-engine test failures = test-quality debt, not runtime bugs. Single-process rate limiter needs Redis backing before multi-replica.
- Unrotated service logs (api-gateway 834 MB, portfolio-manager 941 MB as of 2026-05-20) — no rotation configured.
