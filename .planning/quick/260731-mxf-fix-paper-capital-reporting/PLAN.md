---
id: 260731-mxf
slug: fix-paper-capital-reporting
date: 2026-07-31
status: complete-uncommitted
---

# Fix paper-capital reporting defects ($10,000 → $100)

Derived from `.planning/audits/2026-07-31-full-system-diagnostic.md`.

## Why

Backend *config* already sets the paper account to $100 everywhere
(`config.py:557`, all three compose files, both k8s configmaps, and the live
container env). But three reporting surfaces still measure against $10,000,
so every returns/drawdown/exposure figure the operator sees is wrong by up to
100×.

## Scope — changes that need NO trading-engine restart and NO risk-cap change

### Task 1 — `PerformanceTracker` is always built at $10,000 (D-3, HIGH)

`get_performance_tracker()` is called with **no argument** at every production
site (`auto_trader.py:2955`, `:3703`, `handlers/orchestration.py:454,500,610`),
so the lazy singleton always takes the
`balance = initial_balance or Decimal("10000")` branch at
`performance_tracker.py:561`.

- `performance_tracker.py:561` — default to `settings.paper_initial_balance`.
- `performance_tracker.py:128` — same for the `__init__` default.
- `repositories.py:358` — same for the `create`/`get_or_create` default.

Use `Decimal(str(settings.paper_initial_balance))`, not a new literal, so this
never drifts from config again.

### Task 2 — equity-curve baseline uses a *current* value (F-1, CRITICAL)

`frontend/src/hooks/usePerformanceMetrics.js:119-128` seeds the equity curve
from `portfolioData.total_value` — a value that changes on every 30 s poll — so
the curve's origin translates vertically while the user watches, and
`peakEquity` (`analyticsApi.js:417`) inflates the `maxDrawdownPercent`
denominator. Read the served `metrics.initial_balance` instead.

### Task 3 — contradictory `|| 10000` / `|| 100` fallbacks (F-2, HIGH)

- `PortfolioCard.jsx:43` `|| 10000` vs `KeyMetricsStrip.jsx:195` `|| 100` — same
  field (`metrics.current_balance`), same query, 100× apart. Reconcile.
- `PortfolioCard.jsx:44` is a **divisor** for `exposurePercentage` (`:64`); a
  wrong fallback makes a $100 position read as 1.0%.
- Replace `|| N` with `Number.isFinite` guards so a legitimate `0` survives
  instead of rendering as $10,000.

### Task 4 — `analyticsApi.js:203` (F-3, HIGH)

Default `initialBalance = 10000` → `100`, matching `:358` in the same file.

## Explicitly OUT of scope

- `risk-metrics-service/app/backtest_models.py:16`, `backtesting.py:126` —
  backtest `initial_capital` is a **research parameter**. Forcing it to $100
  pushes backtests under Bybit min-notional and yields garbage.
- The stale `portfolios` row (`initial_balance=10000`) — pending the data-layer
  finding on whether anything reads it at runtime. An `UPDATE` is either
  cosmetic or a behavior change; don't guess.
- **T-2 / T-3 / T-7** (LIVE-mode risk-cap and execution-routing CRITICALs).
  These require a risk-cap change on a running engine and have a hard fix
  ordering (T-2 before T-3). Found, documented, deliberately not patched here.
- Dead-code deletion (F-8, 25 frontend files) — separate change, separate review.

## Verification

- Backend: `pytest services/trading-engine/tests/` — baseline is
  **36 failed, 1449 passed, 842 skipped**. Must not regress.
- Frontend: `npm test` in `frontend/`, then rebuild the frontend container only
  (`docker compose -f docker-compose.unified.yml up -d --build frontend`) —
  independent of the trading engine, which must **not** be restarted.
- No trading-engine restart: a restart would itself corrupt the measured book
  (T-9 rebases balance and discards realized P&L; T-8 resets max-hold clocks).
