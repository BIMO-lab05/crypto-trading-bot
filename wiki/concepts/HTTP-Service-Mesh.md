---
type: concept
status: active
tags: [concept, architecture, http]
created: 2026-05-05
updated: 2026-05-05
---

# HTTP Service Mesh

The actual integration pattern, replacing the documented-but-not-built event mesh ([[Message-Queue-Topics]]).

## Pattern

All inter-service communication is **synchronous HTTP**. Every service is a FastAPI process answering REST requests. Services discover each other via `<SERVICE>_URL` env vars injected by compose.

## Real call graph

```
                          frontend (3000)
                              │
                              ▼
                       api-gateway (8000)
       ┌──────────────────────┼──────────────────────────────────┐
       │                      │                                  │
       ▼                      ▼                                  ▼
trading-engine            portfolio-manager                technical-analysis
   (8005)                    (8003)                            (8004)
   │  ▲                       │  │                                │
   │  │ POST /sync            ▼  │ HTTP                           ▼
   │  └──────────────  trading-engine                     market-data-service
   │  HTTP pull (8005)             ▲                          (8002)
   │                               │                              ▲
   ▼                               │                              │
bybit-connector              technical-analysis ──── HTTP ────────┘
   (8001)                          (8004)
   │
   ▼
Bybit REST API (mainnet — paper mode internal in paper_trading.py)

ml-prediction-service (8007)  — pulled by technical-analysis (when ENABLE_ML_PREDICTIONS=true)
risk-metrics-service (8009)   — pull-only via GET /alerts
notification-service (8006)   — pull only; nothing publishes alerts to it
sentiment-analysis-service (8008) — orphaned; gateway proxies routes for frontend reachability
ml-retraining-service (port 8009 collision) — NOT in any compose; never runs in canonical stack
```

## Key URLs (env-var-driven)

Every service has env vars like `BYBIT_CONNECTOR_URL`, `MARKET_DATA_URL`, `PORTFOLIO_MANAGER_URL`, `TRADING_ENGINE_URL`. Defaults in `app/config.py` are usually wrong (point at wrong port); production-correctness depends on compose env override.

Known stale defaults discovered:
- bybit-connector reports `bybit_connector_url=:8002` (self-loop)
- ml-prediction-service: `market_data_url=localhost:8003` (portfolio's port)
- trading-engine: `portfolio_manager_url=:8006` (notification's port)

These bugs only manifest in standalone runs.

## What this implies

- **No event-driven decoupling.** Slow consumer = back-pressure on caller. trading-engine waits on technical-analysis waits on market-data, all in serial async coroutines.
- **No replay.** Crash mid-flow loses the in-flight signal.
- **State drift possible.** portfolio-manager pulls trading-engine; if pull fails, replicas diverge silently.
- **Routing prefix mixed.** External (api-gateway) routes drop `/v1/`. Internal services use `/api/v1/`. See [[../decisions/ADR-007-no-v1-api-prefix]].

## Why we got here

Original arch doc (Oct 2025, `docs/architecture/SYSTEM_OVERVIEW.md`) prescribed RabbitMQ for everything. Implementation went HTTP, RabbitMQ env was kept "in case", topics doc kept too. Drift never reconciled.

## Related

- [[Message-Queue-Topics]]
- [[Aspirational-vs-Real]]
- [[../decisions/ADR-012-http-not-events]]
- [[../flows/Signal-Pipeline]]
- [[../flows/Order-Lifecycle]]
