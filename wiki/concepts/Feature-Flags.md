---
type: concept
status: active
tags: [concept, flags]
created: 2026-05-05
updated: 2026-05-05
---

# Feature Flags

Compose defaults as of 2026-05.

| Flag | Default | State |
|---|---|---|
| `ENABLE_ML_PREDICTIONS` | `false` | gated off — see [[ML-Status]] |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`) |
| `AUTO_TRADING_ENABLED` | `false` (compose) / `true` (.env override) | see [[Auto-Trader]] |
| `BYBIT_TESTNET` | `false` | mainnet prices |
| `PAPER_TRADING_MODE` | `true` | simulated orders |
| `LIVE_TRADING_ACK` | unset | required to boot LIVE — see [[Trading-Mode-Flags]] |

[[../modules/sentiment-analysis-service|sentiment-analysis-service]] still runs in compose but idle.
