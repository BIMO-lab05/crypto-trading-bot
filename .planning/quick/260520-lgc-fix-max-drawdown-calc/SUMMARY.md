---
status: complete
slug: fix-max-drawdown-calc
completed: 2026-05-20
---

# Fix Max Drawdown Calculation Bug — Summary

## Outcome
`/performance` → **MAX DRAWDOWN: 0.77%** (was 211.67%). Matches the manual replay of the same 36-trade history against an equity curve seeded at the paper-trading $100 balance.

## Changes

### `frontend/src/services/analyticsApi.js`
- `calculatePerformanceMetrics(trades)` → `calculatePerformanceMetrics(trades, initialBalance = 100)`.
- Drawdown now tracks **equity** (`initialBalance + cumulativePnL`), not raw cumulative P&L. Initial peak seeded to `initialBalance`. Both the dollar drawdown and the percent drawdown are tracked through the loop and the worst of each is returned. The old `(maxDrawdown / final_peak) * 100` formula could exceed 100% whenever losses dwarfed pre-loss winnings; the new running per-step percent is bounded 0–100 by construction.

### `frontend/src/hooks/usePerformanceMetrics.js`
- `initialBalance` now reads `total_value` / `cash_balance` (the actual fields the portfolio-manager API returns) before falling back to the legacy `total_equity` / `balance.total` shapes; defaults to `$100` instead of `$10000` so the equity-curve axes match the paper baseline.
- Coerces the value through `parseFloat` (the API returns numeric strings) and guards against non-finite / non-positive results.
- Passes `initialBalance` through to `calculatePerformanceMetrics`.

### `frontend/src/__tests__/performance.test.jsx`
- Adds two unit tests:
  - `keeps maxDrawdownPercent bounded to 0–100 even when losses exceed peak gains` — the win-then-cascading-losses sequence that broke the old code.
  - `matches calculateDrawdownSeries when using the same initialBalance` — cross-checks that `calculatePerformanceMetrics` and `calculateDrawdownSeries` agree.

## Verification
- `vitest run src/__tests__/performance.test.jsx -t "calculatePerformanceMetrics"` → 4/4 pass.
- Rebuilt `frontend/dist`, rebuilt the `crypto-trading-bot-frontend` image, recreated the container.
- Hard-loaded `/performance?nocache=1` in Playwright (the original tab was running an even older cached bundle, masking the fix).
- Server-served bundle now contains the new return shape (`maxDrawdownPercent,` shorthand) and the old `peak>0?(maxDrawdown/peak)*100:0` formula is no longer in the JS at all.

## Out of scope (kept as separate follow-ups)
- Pre-existing assertion mismatch in `calculateDrawdownSeries > calculates drawdown from equity curve` (test expected `0.0196` against a function that returns percent form `1.96`). Not part of this fix.
- 9 `ResizeObserver is not defined` chart-component test failures — recharts + jsdom env issue, unrelated.
- Portfolio page `STALE` badge + `N/A`-dated trades — separate data-quality ticket.
