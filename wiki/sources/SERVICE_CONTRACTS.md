---
type: source
source_path: "docs/architecture/SERVICE_CONTRACTS.md"
ingested: 2026-05-05
status: stale
tags: [source, api-contracts]
created: 2026-05-05
updated: 2026-05-05
---

# Source: docs/architecture/SERVICE_CONTRACTS.md

## Origin

Authored 2025-10-30 (v1.0). API contract spec for the original 6-service cohort.

## Status: STALE — diverges from live OpenAPI

Live contracts: `http://localhost:8000/openapi.json` (api-gateway).

Concrete divergences vs CLAUDE.md:

| Doc says | Reality |
|---|---|
| `/api/v1/...` prefix | `/api/<domain>/<resource>` (no `v1` prefix) |
| Ports per service per old assignment | Current ports per [[../overview]] |
| 6 services documented | 11 services in repo |

`docs/api/openapi.yaml` snapshot was deleted on 2026-04-26 because it drifted. Live OpenAPI is authoritative.

## Still useful

- **Standard response envelope** `{success, data, error, timestamp}` — appears reusable
- **Health endpoints** `/health`, `/ready` on every service (still true)
- **RabbitMQ topic schemas**: payload shapes for `market.data.*`, `analysis.signal.*`, `trade.execute`, `trade.result` (verify still match)
- **Sample resource schemas** — Trade, Position, Order, Candle, Signal — likely close to current shape

## Pages created/updated

- [[../concepts/Message-Queue-Topics]] — uses topic schemas as starting point
- [[../modules/_index]] — module pages will be enriched by Stage 1 agents reading live FastAPI routes

## Open questions

- Has the response envelope shape held? (Stage 1 agents will check)
- Are topic payloads still as documented? (verify in market-data + technical-analysis publishers)
