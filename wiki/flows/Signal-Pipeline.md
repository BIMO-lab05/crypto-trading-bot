---
type: flow
status: active
tags: [flow, signal]
created: 2026-05-05
updated: 2026-05-05
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
    ├── TA indicators (SQZMOM, MACD, RSI, ...)
    └── GRU inference (when [[../concepts/ML-Status|enabled]])
    ↓ aggregator
    ↓ unified signal
[[../modules/trading-engine|trading-engine]]
    └── strategy + [[../concepts/Risk-Model|risk]] gate → order decision
```

## Notes

- Sentiment leg removed (see [[../concepts/Feature-Flags|Feature Flags]])
- ML leg gated OFF; aggregator falls back to TA-only
- Cache: market-data caches in **TimescaleDB itself**, not Redis (Redis empty in testing)
- Stuck prices? `POST /api/v1/collect/ticker/{symbol}` on port 8002 to force refresh

## TimescaleDB caveat

Mixed testnet/mainnet history before 2026-04-25 mid-day. Wipe `klines` / `tickers` if running historical analysis.
