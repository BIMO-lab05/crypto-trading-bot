---
type: meta
title: "Hot Cache"
updated: 2026-07-29T18:00:00
---

# Recent Context

## Last Updated
2026-07-29. Major fix campaign complete (2026-07-28 accounting/data/frontend; 2026-07-29 security audit + notifications + portfolio-manager mirror). System reset to a clean $100 paper baseline and running.

## Key Recent Facts (2026-07-28/29)
- **Paper-engine accounting overhauled** — closes credit `margin_returned + realized_pnl − commission` for BOTH sides (a winning SHORT close previously *decreased* balance); `reduce_only` now REJECTS with no matching position instead of opening a full-size counter-trade (every stop-loss exit used to open a counter-position); `position_id` targeting; partial closes + DCA scale-in. See [[decisions/ADR-018-paper-engine-accounting-overhaul|ADR-018]].
- **Risk** — per-trade cap now CLAMPS size (10% paper per [[decisions/ADR-010-max-risk-per-trade-paper-bump|ADR-010]], hard 2% floor in LIVE); daily-loss 5% breaker auto-rolls per UTC day (was a lifetime cap); kill switch fed EQUITY not cash, loss-streak counts only on closes. [[decisions/ADR-019-kill-switch-equity-and-streak|ADR-019]].
- **Signal gate** — consensus counts only indicators voting the CHOSEN direction (HOLD no longer counts); MACD aligned to TA default 5-35-5. [[decisions/ADR-020-directional-consensus-gate|ADR-020]].
- **Data integrity** — TA fetcher: mainnet-only + candle validation (drop OHLC-invalid, >35%/bar, still-forming, raise <30 rows) + interval normalization. DB testnet pollution repaired non-destructively (`scripts/repair_testnet_pollution.sql`, 118k rows demoted; max mainnet BTC close ~$82k, was $1.76M). [[decisions/ADR-021-ta-data-integrity-gate|ADR-021]].
- **Security** — mode-gated API auth (enforced LIVE/prod, open in local paper, `REQUIRE_API_AUTH` override); real method-aware rate limiting (strict 60/min only on mutating trade actions). [[decisions/ADR-022-mode-gated-api-auth|ADR-022]]. Bybit HMAC signing fixed — was signing a differently-formatted body than sent, so every authenticated POST failed retCode 10004. [[decisions/ADR-023-bybit-request-signing-fix|ADR-023]].
- **Portfolio-manager** now MIRRORS the engine (side-aware P&L, authoritative cash/equity) — previously modeled shorts as spot longs → phantom −84% return. [[decisions/ADR-024-portfolio-manager-mirrors-engine|ADR-024]].
- **Notifications** — `NOTIFICATION_TEST_MODE` default changed `record`→`` (real Telegram delivery). It was silently writing to a file while reporting `telegram_sent=true`. [[decisions/ADR-025-notification-real-delivery-default|ADR-025]].

## Current running state
- Paper mode, clean $100 baseline (DB wiped of 43 pre-fix positions / 61 trades / negative cash), auto-trader armed, kill-switch clear.
- 8/9 services healthy; ml-prediction behind opt-in compose `ml` profile, sentiment behind `analytics` profile (neither starts by default).
- Verified live: engine and portfolio-manager agree; Telegram delivery confirmed (real api.telegram.org 200).

## Architecture correction
- **No live event bus.** Services communicate via synchronous REST only; RabbitMQ is deployed but no service wires AMQP pub/sub. Old "RabbitMQ (events)" claims were aspirational — see [[modules/Architecture-Overview]].

## Open items / next
- Frontend has no login flow yet — required before flipping to LIVE (auth is open only in paper mode).
- 9 pre-existing trading-engine test failures are test-quality debt (stale mocks / source-marker governance), not runtime bugs.
- Strategy profitability still unproven — accumulate 2–4 weeks of clean paper trades, evaluate with DSR/CPCV before any LIVE discussion.
