---
type: meta
title: "Hot Cache"
updated: 2026-05-05T14:00:00
---

# Recent Context

## Last Updated
2026-05-05. Wiki Stage 0 ingest complete. Stage 1 parallel agent dispatch for service modules in flight.

## Key Recent Facts
- Vault scaffolded under `wiki/` of crypto-trading-bot repo (Mode B + concepts/)
- Repo CLAUDE.md updated with wiki reference block + flagged stale `DECISIONS.md` mention
- Ingested `docs/architecture/SYSTEM_OVERVIEW.md` and `SERVICE_CONTRACTS.md` — both flagged STALE (Oct 2025; wrong ports, /v1/ prefix, only 6 of 11 services)
- Ingested `progress.md` — extracted ADRs and gotchas
- 9 ADRs filed (ADR-001 through ADR-009) covering: LSTM removal, lifespan refactor, bcrypt_sha256, paper-trading default, EMERGENCY_STOP file flag, mainnet+paper dual mode, no-/v1/ prefix, conventional commits, unified compose
- 2 new concepts: Message-Queue-Topics (verify in code), Test-Setup-Gotchas

## Recent Changes
- Created sources/SYSTEM_OVERVIEW, sources/SERVICE_CONTRACTS, sources/progress
- Created 9 decisions/ADR-*.md
- Created concepts/Message-Queue-Topics, concepts/Test-Setup-Gotchas
- Updated repo `CLAUDE.md` with Wiki Knowledge Base section
- Module pages still stub-state — Stage 1 agents will populate

## Active Threads
- Stage 1: parallel agents reading each `services/<name>/` to extract real endpoints, deps, env vars, RabbitMQ pub/sub, gotchas → write into `wiki/modules/<name>.md`
- Verification needed: which RabbitMQ topics from `Message-Queue-Topics` are still alive post-sentiment-removal
- Stage 2 deferred: `frontend/src/` component map
- Stage 3 deferred: synthesize cross-cutting flows with real function names from Stage 1 outputs

## Open Contradictions
- `docs/architecture/SERVICE_CONTRACTS.md` says `/api/v1/...`; current API uses `/api/<domain>/<resource>` (ADR-007)
- `SYSTEM_OVERVIEW.md` ports differ from current — see [[sources/SYSTEM_OVERVIEW]] table
- CLAUDE.md previously referenced `docs/architecture/DECISIONS.md` — file does not exist (now fixed in CLAUDE.md)
