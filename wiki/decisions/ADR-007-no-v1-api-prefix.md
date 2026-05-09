---
type: decision
status: accepted
date: 2026-04
context: "API path simplification"
deciders: []
tags: [decision, adr, api]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-007: drop /v1/ prefix from gateway routes

## Context

Older docs (incl. `docs/architecture/SERVICE_CONTRACTS.md`) showed `/api/v1/...`. Repo never reached a v2; the prefix added noise without versioning value. Internal services use direct paths anyway.

## Decision

Gateway routes: `/api/<domain>/<resource>`.

Domains: `portfolio`, `trading`, `risk`, `market`, `analysis`, `ml`, `sentiment`, `dashboard`, `performance`.

Live OpenAPI: `http://localhost:8000/openapi.json`.

## Consequences

- `docs/architecture/SERVICE_CONTRACTS.md` references `/api/v1/...` — STALE; live OpenAPI is authoritative
- `docs/api/openapi.yaml` snapshot deleted 2026-04-26 (drifted)

## Related

- [[../sources/SERVICE_CONTRACTS]]
- [[../modules/api-gateway]]
