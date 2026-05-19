---
type: concept
status: in-progress
tags: [trading-engine, refactor, strangler-fig]
created: 2026-05-06
updated: 2026-05-06
---

# Signal Aggregator Strangler-Fig — Actual State

> Audit (2026-05-06) corrected an earlier optimistic claim. The strangler is **partial**, not 80% complete.

## What lives where

`services/trading-engine/app/signal_aggregator.py` (**1262 lines**)
- Holds the canonical `SignalAggregator` class (25 methods)
- 14 of those are `fetch_<indicator>` methods that call the technical-analysis HTTP API directly: RSI, MACD, BB, SMA, EMA, ATR, Stochastic, Trend Filter, Volume Confirmation, RSI Divergence, Ichimoku Cloud, Enhanced SQZMOM, plus orchestration
- Composes a `CoreAggregator` instance for the *aggregation* step only (line 47)
- Module-level `get_aggregator()` / `close_aggregator()` singleton accessors at lines 1262 and 1270

`services/trading-engine/app/aggregation/aggregator_core.py` (621 lines)
- `CoreAggregator` class — 9 methods, all about combining already-fetched indicators into a final signal
- Knows nothing about HTTP fetching; consumes `IndicatorSignal` objects produced upstream
- Does *not* expose a singleton

`services/trading-engine/app/aggregation/__init__.py`
- Re-exports `CoreAggregator`, `EnhancedAggregator`, `MultiTimeframeAnalyzer`, `MarketRegimeDetector`, `TrendGatekeeper`, `VolumeValidator`, `SignalVoter`

## What's been extracted

| Concern | Old location | Strangler home |
|---|---|---|
| Final-step vote weighting | `SignalAggregator.aggregate(...)` | `aggregation/voter.py:SignalVoter` |
| Gatekeeper (counter-trend block) | embedded in monolith | `aggregation/gatekeeper.py:TrendGatekeeper` |
| Volume validator | embedded | `aggregation/validator.py:VolumeValidator` |
| ADX market-regime detection | n/a (new) | `aggregation/market_regime.py` |
| Multi-timeframe alignment | n/a (new) | `aggregation/multi_timeframe.py` |
| Cache + signal staleness | embedded | `aggregation/signal_cache.py` |

## What is NOT yet extracted

- All 14 `fetch_<indicator>` methods (HTTP-side I/O bound to `httpx.AsyncClient`)
- The singleton accessors (`get_aggregator`, `close_aggregator`)
- The `health_check()` for upstream technical-analysis service

## Caller footprint (2026-05-06 grep)

- 14 imports of `app.signal_aggregator` (auto_trader, multi_symbol_trader, monitor_signals, main.py, tests)
- 23 imports of `app.aggregation` (mostly internal cross-references inside the aggregation package itself)

The 23-vs-14 number was misleading: most of the 23 are intra-package imports between aggregator_core ↔ voter ↔ gatekeeper, not new external consumers of the strangler.

## Retirement is multi-hour, not 1-hour

Realistic plan:

1. **Move the 14 `fetch_<indicator>` methods** out of `SignalAggregator` into per-indicator modules under `app/aggregation/fetchers/` (split by category: trend, momentum, volume, advanced).
2. **Promote `aggregation` to own the singleton.** Add `get_aggregator()` to `aggregation/__init__.py` constructing a slim orchestrator that composes Fetchers + CoreAggregator.
3. **Codemod 14 callers**: `from app.signal_aggregator import` → `from app.aggregation import`.
4. **Adjust tests** (5 callers under tests/ + verify_system.py path-string).
5. **Delete `signal_aggregator.py`** only after pytest passes inside the trading-engine container (host pip versions diverge; see `feedback_api_gateway_test_env.md` memory).

Estimate: 3–4 hours including container test cycles. Not a single-pass refactor.

## Decision (2026-05-06)

Hold the retirement until a dedicated session that has the docker stack running. Until then:

- **Do not** add new code to `signal_aggregator.py` — every new fetcher goes into `aggregation/fetchers/`
- **New callers** must import from `app.aggregation`, not `app.signal_aggregator`
- The 14 existing callers stay as-is; codemod happens in the dedicated retirement session

## Related

- [[../decisions/ADR-016-http-not-events]] (this whole pipeline is the HTTP mesh in question)
- [[../flows/Signal-Pipeline]]
- [[../modules/trading-engine]]
