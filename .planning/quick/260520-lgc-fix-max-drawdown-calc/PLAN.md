---
status: in-progress
slug: fix-max-drawdown-calc
created: 2026-05-20
---

# Fix Max Drawdown Calculation Bug

## Problem
Frontend Performance page displayed `Max Drawdown 211.67%` — impossible (drawdown is bounded 0–100% by definition).

## Root cause (two related bugs)

1. **`calculatePerformanceMetrics()` in `frontend/src/services/analyticsApi.js`** computes drawdown from cumulative-P&L deltas (`cumulativePnL`) with `peak = 0` initial. When trade history starts with one winner (e.g. +$0.10) followed by losses pushing cumulative to −$0.30:
   - peak = +$0.10
   - cumulativePnL = −$0.30
   - drawdown = peak − cum = $0.40
   - maxDrawdownPercent = $0.40 / $0.10 × 100 = **400%**
   The denominator should be the running peak of *equity* at the trough, not the final peak of cumulative P&L. Also drawdown should be computed against equity (initial + cumulative), not cumulative alone.

2. **`usePerformanceMetrics` hook** reads `portfolioData?.total_equity || portfolioData?.balance?.total || 10000`. The portfolio-manager API returns `cash_balance` and `total_value`; neither `total_equity` nor `balance.total` exist. Result: `initialBalance` falls back to `$10000` when the real paper-trading balance is `$100`, miscalibrating the equity curve and drawdown chart axes.

## Fix
1. `analyticsApi.js::calculatePerformanceMetrics(trades, initialBalance = 100)` — track equity = initial + cumulativePnL, peak = running max of equity, drawdown = (peak − equity), drawdownPercent = drawdown / peak × 100. Return both `maxDrawdown` (dollars, positive) and `maxDrawdownPercent` (bounded 0–100).
2. `usePerformanceMetrics.js` — read `total_value` / `cash_balance` before falling back; default fallback drops from 10000 → 100 (project's paper default).
3. Pass `initialBalance` through to `calculatePerformanceMetrics(trades, initialBalance)`.
4. Add unit test asserting `maxDrawdownPercent <= 100` and matching equity-curve drawdown.

## Verify
- `pnpm --filter frontend run test -- performance.test.jsx`
- Rebuild frontend container; reload `/performance` page; observe Max DD between 0–100% and consistent with the drawdown chart.
