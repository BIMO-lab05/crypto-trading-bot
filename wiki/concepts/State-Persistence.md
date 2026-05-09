---
type: concept
status: active
tags: [concept, persistence, state]
created: 2026-05-05
updated: 2026-05-05
---

# State Persistence — What Survives Restart

Restart-safety map per service. RAM-only state = data loss on container recycle.

## Survives restart (durable)

| Service | What | Where |
|---|---|---|
| market-data-service | candles, tickers | TimescaleDB (`klines`, `tickers`). DB is the cache. |
| portfolio-manager | daily snapshots | PostgreSQL `portfolio.performance_history` |
| notification-service | failed alerts (DLQ) | SQLite at `/app/data/dlq.sqlite3` |
| ml-prediction-service | models | `.keras` files mounted from disk |

## RAM-only (wipes on restart)

| Service | What | Note |
|---|---|---|
| api-gateway | user store | In-process `dict`; restart wipes all logins |
| portfolio-manager | positions, balances, transaction history | Migration `003_portfolios_orm_align.sql` exists, not used at runtime |
| risk-metrics-service | `historical_returns` | Never populated → all risk metrics use insufficient-data fallback |
| risk-metrics-service | circuit-breaker state | Dual with trading-engine; restart resets state machine |
| trading-engine | in-flight signal queue | Crash mid-flow loses signal (no event bus replay) |

## Hidden caveats

- TimescaleDB has **mixed testnet/mainnet history** before 2026-04-25 mid-day. `is_mainnet` defaults to `true` for old rows → mainnet filter does NOT protect pre-flip pollution. Manual `DELETE` required for clean backtests.
- portfolio-manager pulls trading-engine via `POST /api/v1/sync`. If pull fails, copies drift; no two-way reconciliation.

## Related

- [[../flows/Order-Lifecycle]]
- [[../decisions/ADR-006-mainnet-prices-paper-orders]]
