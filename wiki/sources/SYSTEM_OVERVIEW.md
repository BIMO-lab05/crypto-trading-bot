---
type: source
source_path: "docs/architecture/SYSTEM_OVERVIEW.md"
ingested: 2026-05-05
status: stale
tags: [source, architecture]
created: 2026-05-05
updated: 2026-05-05
---

# Source: docs/architecture/SYSTEM_OVERVIEW.md

## Origin

Authored 2025-10-30 (v1.0). Documents original 6-service cohort.

## Status: STALE

Document predates the 11-service current state. Concrete divergences:

| Doc says | Reality (per repo + CLAUDE.md, 2026-05) |
|---|---|
| trading-engine on **8001** | trading-engine on **8005** |
| bybit-connector on **8002** | bybit-connector on **8001** |
| market-data-service on **8003** | market-data-service on **8002** |
| portfolio-manager on **8005** | portfolio-manager on **8003** |
| 6 services | 11 services + frontend |
| (missing) | notification, ml-prediction, sentiment, risk-metrics, ml-retraining |

## Still useful

- Microservices design philosophy (event-driven, isolation, fault-tolerance)
- Architecture diagram (logical layout still holds)
- RabbitMQ topic naming conventions (verify which still active in code; sentiment leg removed)
- Storage role split: PostgreSQL / TimescaleDB / Redis
- Performance SLOs

## Pages created/updated

- [[../modules/Architecture-Overview]] — refreshed with topic schemas
- [[../concepts/Message-Queue-Topics]] — new concept page

## Open questions

- Are all 6 listed RabbitMQ topics still alive after sentiment removal?
- Did the trading flow described match current code? Stage 1 agent run will verify.
