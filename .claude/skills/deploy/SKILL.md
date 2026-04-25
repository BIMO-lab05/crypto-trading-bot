---
name: deploy
description: Rebuild and recreate a single docker service in this project. Forces image rebuild from source, recreates the container, waits for healthcheck, then prints status and recent logs. Use when source has changed or a service is misbehaving and a clean restart is the right move. Pass the service name as the only argument — must match a service in docker-compose.unified.yml.
disable-model-invocation: true
---

# Deploy a single service

Goal: rebuild and restart **one** docker service cleanly, with health verification. This is the playbook I (the user) was repeatedly running by hand.

## Inputs

- **service name** (required): one of `api-gateway`, `bybit-connector`, `market-data`, `portfolio-manager`, `technical-analysis`, `trading-engine`, `notification-service`, `ml-prediction`, `sentiment-analysis`, `risk-metrics`, `frontend`. Match exactly the service key in `docker-compose.unified.yml`. The container name is `crypto-bot-<short>` (e.g. `trading-engine` → `crypto-bot-trading`, `technical-analysis` → `crypto-bot-ta`).

## Playbook

1. **Confirm the service exists** in `docker-compose.unified.yml`:
   ```bash
   docker compose -f docker-compose.unified.yml config --services | grep -x <service>
   ```
   If empty, stop and tell the user.

2. **Rebuild + force-recreate** with no upstream dep churn:
   ```bash
   docker compose -f docker-compose.unified.yml up -d --build --no-deps --force-recreate <service>
   ```
   This is one of the few cases where `--force-recreate` is correct — we explicitly want a clean container.

3. **Wait for healthy** (poll `docker inspect`):
   ```bash
   until [ "$(docker inspect -f '{{.State.Health.Status}}' crypto-bot-<short> 2>/dev/null)" != "starting" ]; do sleep 2; done
   ```
   Cap at ~120 s; if still starting, treat as failure.

4. **Report final state**:
   ```bash
   docker ps --format 'table {{.Names}}\t{{.Status}}' | grep crypto-bot-<short>
   docker logs --tail 25 crypto-bot-<short> 2>&1
   ```

5. **If status is `Restarting` or `unhealthy`**: dump the last 80 log lines and tell the user the failure reason. Common patterns from history: missing import in `app/main.py`, missing dep in `requirements.txt`, port collision, env-var mismatch (e.g. `TELEGRAM_ENABLED` not passed by compose).

## Service → container-name mapping (asymmetric naming)

| Compose service | Container name |
|---|---|
| api-gateway | crypto-bot-api-gateway |
| bybit-connector | crypto-bot-bybit |
| market-data | crypto-bot-market-data |
| portfolio-manager | crypto-bot-portfolio |
| technical-analysis | crypto-bot-ta |
| trading-engine | crypto-bot-trading |
| notification-service | crypto-bot-notification |
| ml-prediction | crypto-bot-ml-prediction |
| sentiment-analysis | crypto-bot-sentiment |
| risk-metrics | crypto-bot-risk-metrics |
| frontend | crypto-bot-frontend |

## Anti-cases (don't run /deploy)

- For DBs (`postgres`, `redis`, `rabbitmq`, `timescaledb`): a force-recreate **wipes data** if no named volume protects it. Verify volume mounts before running. Better: just `docker compose ... restart <db>`.
- If the issue is config-only (env var typo): edit + `docker compose ... up -d <service>` is enough — no rebuild needed.
- For a multi-service change (gateway routes + downstream contract): use `docker compose ... up -d --build` without `--no-deps` so downstream services restart in the right order.

## Notes

- Always use `docker-compose.unified.yml`, never the bare `docker-compose.yml` (the latter is missing DBs).
- `--build` rebuilds the image. If only env-vars changed, drop `--build` to skip rebuild.
- `--force-recreate` ensures the container is replaced even if compose thinks it's already in the desired state (useful after `.env` changes).
