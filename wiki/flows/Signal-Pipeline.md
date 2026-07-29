---
type: flow
status: active
tags: [flow, signal]
created: 2026-05-05
updated: 2026-07-29
---

# Signal Pipeline

End-to-end signal generation flow.

```
[[../modules/bybit-connector|bybit-connector]] (WS)
    ↓ candles
[[../modules/market-data-service|market-data-service]]
    ↓ TimescaleDB write
    ↓ event
[[../modules/technical-analysis|technical-analysis]]
    ├── data-integrity gate (see [[../decisions/ADR-021-ta-data-integrity-gate]]):
    │     mainnet-only reads · interval normalization (1440→D) · drop invalid /
    │     >35%-jump candles · drop still-forming last candle · refuse if <30 valid rows
    ├── TA indicators (SQZMOM, MACD 5-35-5, RSI, ...)
    └── GRU inference (when [[../concepts/ML-Status|enabled]])
    ↓ aggregator (CoreAggregator)
    │   ├── weighted vote → action (sign of weighted score)
    │   ├── consensus = count of indicators voting the CHOSEN direction ≥ min_consensus(3)
    │   │     (HOLD votes no longer count toward a directional trade)
    │   ├── confidence = agreement strength (Σ weight·conf of agreeing / Σ weight) ≥ 0.30
    │   └── category diversity + trend/regime blocks
    │   see [[../decisions/ADR-020-directional-consensus-gate]]
    ↓ unified signal
[[../modules/trading-engine|trading-engine]]
    └── strategy + [[../concepts/Risk-Model|risk]] gate → order decision
```

## Notes

- Sentiment leg removed (see [[../concepts/Feature-Flags|Feature Flags]])
- ML leg gated OFF; aggregator falls back to TA-only
- MACD parameters are sourced from the TA service defaults (Kang-2021 5-35-5), not local overrides (ADR-020)
- Cache: market-data caches in **TimescaleDB itself**, not Redis (Redis empty in testing)
- Stuck prices? `POST /api/v1/collect/ticker/{symbol}` on port 8002 to force refresh

## TimescaleDB caveat

Mixed testnet/mainnet history before 2026-04-25 mid-day was **repaired 2026-07-28** via `scripts/repair_testnet_pollution.sql` (demotes pre-cutoff + >5×-outlier rows to `is_mainnet=false`), and TA now reads mainnet-only with candle validation. See [[../decisions/ADR-021-ta-data-integrity-gate]]. Historical analysis no longer requires wiping `klines` / `tickers`.
