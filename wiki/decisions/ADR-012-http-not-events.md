---
type: decision
status: accepted
date: 2026-05-06
context: "Service-to-service communication topology"
deciders: []
tags: [decision, adr, architecture, rabbitmq, http]
created: 2026-05-06
updated: 2026-05-06
---

# ADR-012: HTTP service mesh, not RabbitMQ event bus

## Context

Older architecture docs (`docs/architecture/SERVICE_CONTRACTS.md`, Oct 2025; `docs/architecture/SYSTEM_OVERVIEW.md`) describe an event-driven design with RabbitMQ topics:

| Topic | Claimed publisher | Claimed consumer |
|---|---|---|
| `market.data.{symbol}` | market-data-service | technical-analysis |
| `analysis.signal.{symbol}` | technical-analysis | trading-engine |
| `trade.execute` | trading-engine | bybit-connector |
| `trade.result` | bybit-connector | portfolio-manager |
| `portfolio.update` | portfolio-manager | notification-service |
| `alert.critical` | various | notification-service |

Stage 1 code-mapping audit (2026-05-05) verified empirically: **0 of 11 services use RabbitMQ at orchestration level.** Every container ships `RABBITMQ_HOST` / `RABBITMQ_URL` env vars and most have full pydantic `Settings` blocks for RabbitMQ host/port/url-builders, but **no service imports `aio_pika` or `pika` for actual message publishing or consumption.**

Only live RabbitMQ touchpoint: a single optional `aio_pika` health probe in `services/trading-engine/core/health.py:406`. `services/technical-analysis/app/config.py:105-115` carries an audit comment admitting RabbitMQ is configured but unused.

## Decision

The service mesh is **synchronous HTTP end-to-end**. Treat RabbitMQ env vars and pydantic Settings as legacy scaffolding to be removed (see consequences).

Real call topology:

- bybit-connector → market-data-service: REST polled candle ingest
- technical-analysis → market-data-service: HTTP `GET /api/candles/...`
- trading-engine → technical-analysis: HTTP via `signal_aggregator` (in-process polling of TA + GRU outputs in trading-engine, not cross-service events)
- trading-engine → bybit-connector: HTTP order placement (LIVE only); paper orders simulated internally in `paper_trading.py`
- portfolio-manager → trading-engine: HTTP **pull** via `POST /api/sync` (direction inverted from the old event story)
- risk-metrics-service: pull-only `GET /alerts`; **notification-service never receives them**

## Consequences

- No DLQ semantics, no replay, no fan-out
- Slow consumer = HTTP back-pressure on caller, not queue buildup
- Restart loses everything in flight (no message persistence)
- Orchestration via async timers + `signal_aggregator` polling, not events
- Documented topics in old arch docs are **fiction**; do not trust as integration contract
- RabbitMQ env vars in `docker-compose.unified.yml` are dead config; safe to remove (pending audit per action queue)
- `services/technical-analysis/app/config.py:105-115` inert RabbitMQ Settings block can be deleted

## Alternatives considered

- **Wire RabbitMQ as originally documented.** Rejected for now: HTTP mesh works, paper-trading mode does not need fan-out semantics, retraining cron + admin endpoints handle batch + control-plane needs. Re-evaluate when reaching multi-region or multi-instance trading-engine deployment where in-process aggregator becomes a bottleneck.
- **Move to lightweight pub/sub (Redis Streams).** Deferred — same migration cost as RabbitMQ adoption, but lower DLQ guarantees.

## Related

- [[../concepts/HTTP-Service-Mesh]]
- [[../concepts/Message-Queue-Topics]]
- [[../concepts/Aspirational-vs-Real]]
- [[ADR-007-no-v1-api-prefix]]
- [[../sources/SERVICE_CONTRACTS]]
- [[../sources/SYSTEM_OVERVIEW]]
