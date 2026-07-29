---
type: concept
status: active
tags: [concept, flags]
created: 2026-05-05
updated: 2026-07-29
---

# Feature Flags

Compose defaults (`docker-compose.unified.yml`) as of 2026-07.

| Flag | Default | State |
|---|---|---|
| `ENABLE_ML_PREDICTIONS` | `false` | gated off — see [[ML-Status]] |
| `ENABLE_SENTIMENT_ANALYSIS` | `false` | sentiment leg removed from signal pipeline (commits `c346483`, `acae081`, `fe941cf`, `c171bb0`) |
| `AUTO_TRADING_ENABLED` | `false` (compose) / `true` (.env override) | see [[Auto-Trader]] |
| `BYBIT_TESTNET` | `false` | mainnet prices |
| `PAPER_TRADING_MODE` | `true` | simulated orders |
| `LIVE_TRADING_ACK` | unset | required to boot LIVE — see [[Trading-Mode-Flags]] |

[[../modules/sentiment-analysis-service|sentiment-analysis-service]] is now behind an opt-in `analytics` compose profile — it does **NOT** start with the core stack (`docker compose --profile analytics up -d` to enable). Likewise [[../modules/ml-prediction-service|ml-prediction-service]] is behind the opt-in `ml` profile. Neither is a `depends_on` of trading-engine; when absent, runtime fan-out calls get connection-refused and the aggregator downgrades to non-ML/non-sentiment signals.

## Corrections 2026-07-29

- Previously said the sentiment service "still runs in compose but idle." It no longer runs by default — it is gated behind the `analytics` profile (`docker-compose.unified.yml:875-876`). ml-prediction is similarly behind the `ml` profile (`:773-774`). Flag defaults themselves (`ENABLE_ML_PREDICTIONS=false`, `ENABLE_SENTIMENT_ANALYSIS=false`) verified unchanged (`:292-293`, `:620-621`).
