---
type: module
path: ""
status: active
purpose: "30-second architectural tour of the bot"
tags: [overview, architecture]
created: 2026-05-05
updated: 2026-05-05
depends_on: []
used_by: []
---

# Architecture Overview

Async microservices, each FastAPI + Python 3.12. Communicate via REST (`/api/<domain>/<resource>` through gateway) and event bus (RabbitMQ). State in PostgreSQL; time-series in TimescaleDB; ephemeral in Redis.

## Layered view

1. **Edge** — `frontend/` (React) ↔ [[api-gateway]] (auth, routing)
2. **Domain services** — [[portfolio-manager]], [[trading-engine]], [[risk-metrics-service]], [[notification-service]]
3. **Signal services** — [[technical-analysis]], [[ml-prediction-service]], [[sentiment-analysis-service]]
4. **Data services** — [[market-data-service]], [[bybit-connector]]
5. **Background** — [[ml-retraining-service]] (cron)
6. **Observability** — Prometheus :9090, Grafana :3001

## Key flows

- [[../flows/Signal-Pipeline|Signal Pipeline]]
- [[../flows/Order-Lifecycle|Order Lifecycle]]
- [[../flows/Emergency-Stop|Emergency Stop]]

## Reference docs

Authoritative source: `docs/architecture/SYSTEM_OVERVIEW.md`. ADRs in `docs/architecture/DECISIONS.md`.
