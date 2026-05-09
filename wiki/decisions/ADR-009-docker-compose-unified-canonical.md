---
type: decision
status: accepted
date: 2026
context: "two compose files in repo, only one complete"
deciders: []
tags: [decision, adr, docker]
created: 2026-05-05
updated: 2026-05-05
---

# ADR-009: docker-compose.unified.yml is canonical

## Context

Repo has two compose files. `docker-compose.yml` is incomplete (missing postgres / timescaledb / redis / rabbitmq). `docker-compose.unified.yml` has all 16 services including DBs.

## Decision

Use `docker-compose.unified.yml` for all dev / test / paper-trading deploy.

```bash
docker compose -f docker-compose.unified.yml up -d
```

## Consequences

- Single source of truth for stack composition
- Plain `docker-compose.yml` should eventually be deleted or marked deprecated
- WSL2: BuildKit hangs common — `DOCKER_BUILDKIT=0 docker compose ... up -d --build <svc>` works around stalls
- sentiment-analysis-service image historically fails to build (PyPI timeouts); skip with `--no-deps` if needed

## Related

- `CLAUDE.md` § Environment / Gotchas
