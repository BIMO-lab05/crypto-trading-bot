---
paths:
  - "docker-compose*.yml"
  - "Dockerfile*"
  - "services/*/Dockerfile"
  - "services/*/.dockerignore"
  - "infrastructure/**"
  - ".env*"
---

# Docker / environment rules

- **`docker-compose.unified.yml` is canonical** (16 services incl. DBs). `docker-compose.yml` is missing postgres/timescaledb/redis/rabbitmq — do not use it and do not "fix" it without asking.
- **WSL2 + Docker Desktop**: Docker context must be `default` (Unix socket), not `desktop-linux`. Check `docker context show`.
- **BuildKit hangs on WSL2.** Work around with `DOCKER_BUILDKIT=0 docker compose up -d --build <svc>`.
- **WSL bind-mount race**: `docker inspect` can report a `bind` mount while the in-container path is empty and root-owned. Symptom is `PermissionError` writing `/app/logs`. Fix: `docker compose up -d --force-recreate <service>`.
- **Kill switch is a dir-to-dir bind** of `./safety/` → `/app/safety/`. Do not revert to the old file-to-file `./EMERGENCY_STOP` bind; it breaks when the host file is absent.
- **sentiment-analysis-service** fails to build on PyPI read timeouts. It sits behind the compose `analytics` profile and ml-prediction behind `ml` — neither starts by default. Leave it that way.
- **ML training OOMs** at default container limits for BTC. Raise `deploy.resources.limits` before any retrain.
- `services/trading-engine/.dockerignore` currently excludes `tests/standalone/`, which deletes the accounting-harness evidence base on rebuild. Fix that before rebuilding.

## .env

Never commit `.env`. When you change a risk or capital key in `.env`, change it in `.env.example` in the same edit — the two have drifted before and `.env.example` still advertises a $10,000 account.
