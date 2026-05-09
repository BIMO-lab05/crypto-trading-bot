---
type: concept
status: not-implemented
tags: [concept, rabbitmq, events, fiction]
created: 2026-05-05
updated: 2026-05-05
---

# Message Queue Topics — DOCUMENTED BUT NOT WIRED

> ⚠️ **Status: 0/11 services use RabbitMQ.** Old arch docs (`docs/architecture/SERVICE_CONTRACTS.md`, Oct 2025) describe an event-driven design that **was never built**. Verified empirically by Stage 1 code-mapping agents (2026-05-05).

## Reality

The service mesh is **synchronous HTTP** end-to-end. See [[HTTP-Service-Mesh]].

- Every service ships RabbitMQ env vars (`RABBITMQ_HOST`, `RABBITMQ_URL`) injected by compose.
- Some services have full pydantic `Settings` blocks for RabbitMQ host/port/url-builders.
- One service (technical-analysis) has an audit comment in `app/config.py:105-115` admitting RabbitMQ is configured but unused.
- **Zero services import `aio_pika` or `pika` at orchestration level.** trading-engine has one optional `aio_pika` health probe in `core/health.py:406` — that's it.

## What old docs claimed (do not trust)

| Topic | Claimed publisher | Claimed consumer | Real status |
|---|---|---|---|
| `market.data.{symbol}` | market-data-service | technical-analysis | not implemented |
| `analysis.signal.{symbol}` | technical-analysis | trading-engine | not implemented |
| `trade.execute` | trading-engine | bybit-connector | not implemented |
| `trade.result` | bybit-connector | portfolio-manager | not implemented |
| `portfolio.update` | portfolio-manager | notification-service | not implemented |
| `alert.critical` | various | notification-service | not implemented |

## Real flow (HTTP)

- market-data-service ← bybit-connector (REST)
- technical-analysis → market-data-service (HTTP `GET /api/v1/candles/...`)
- trading-engine → technical-analysis (HTTP via `signal_aggregator`)
- trading-engine → bybit-connector (HTTP order placement; LIVE only — paper internal in `paper_trading.py`)
- portfolio-manager → trading-engine (HTTP **pull** via `POST /api/v1/sync` — direction inverted from event story)
- risk-metrics-service: pull-only `GET /alerts`; **notification-service never receives them**

## Implications

- No DLQ semantics, no replay, no fan-out
- Slow consumer = back-pressure on caller (HTTP), not queue buildup
- Restart loses everything in flight (no message persistence)
- Orchestration via async timers + `signal_aggregator` polling, not events

## Related

- [[HTTP-Service-Mesh]]
- [[Aspirational-vs-Real]]
- [[../decisions/ADR-012-http-not-events]]
- [[../sources/SERVICE_CONTRACTS]]
