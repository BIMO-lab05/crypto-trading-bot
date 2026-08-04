---
type: module
path: ""
status: active
purpose: "30-second architectural tour of the bot"
tags: [overview, architecture]
created: 2026-05-05
updated: 2026-07-30
depends_on: []
used_by: []
---

# Architecture Overview

Async microservices, each FastAPI + Python 3.12. Communicate via **synchronous REST only** (`/api/<domain>/<resource>` through the gateway; service-to-service is direct HTTP). State in PostgreSQL; time-series in TimescaleDB; ephemeral in Redis. **There is no live RabbitMQ event bus** — `pika`/AMQP settings appear in several `config.py` files and older docs, but no service declares a publisher, consumer, or queue in `app/`. The signal/order pipeline is HTTP end-to-end (`market-data → technical-analysis → trading-engine → bybit-connector`). Treat any "event topic" reference (`trade.execute`, `trade.result`, `analysis.signal.*`, `market.data.*`) as aspirational.

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

`docs/architecture/SYSTEM_OVERVIEW.md` is the repo-facing mirror of this page (rewritten 2026-07-30). ADRs live in [[../decisions/_index|wiki/decisions/]].
