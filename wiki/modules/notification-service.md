---
type: module
path: "services/notification-service/"
status: active
language: python
port: 8006
purpose: "Multi-channel alert fan-out: Telegram, Email, Slack, SMS"
maintainer: ""
last_updated: 2026-05-05
linked_issues: []
depends_on: [redis, postgres, slack-api, telegram-api, smtp, twilio]
used_by: [trading-engine, ml-retraining-service, api-gateway]
tags: [module, service, notification, alerting]
created: 2026-05-05
updated: 2026-07-29
---

# notification-service

**Port:** `8006` (code default in `app/config.py` is `8007` — compose `SERVICE_PORT=8006` overrides; compose authoritative)
**Path:** `services/notification-service/`
**Purpose:** Multi-channel alert fan-out with severity routing, suppression, escalation, and a SQLite DLQ for failed deliveries.

## Overview

HTTP-only FastAPI service. Sibling services POST alerts; this service routes to Telegram / Email / Slack / SMS based on severity and per-severity rules. Despite `RABBITMQ_HOST=rabbitmq` in compose, the service has **no AMQP consumer** — it does not subscribe to events from the message bus. All alerts are pull-fanout from REST callers.

See raw report: `wiki/.raw/agent-reports/notification-service.md`.

## Endpoints

Two surfaces — both `/api/v1/...`. The "no v1 prefix" convention applies to gateway external routes, not internal services.

**Legacy + ops (`app/main.py`):**

- `GET /` — service info
- `GET /metrics` — Prometheus
- `GET /api/v1/config` — channel + alert toggles
- `POST /api/v1/notify/{trade,pnl,daily-limit,error,startup,daily-summary}` — legacy fixed-shape endpoints (Telegram + Email)
- `GET /api/v1/dlq` — list recent failed-delivery rows
- `POST /api/v1/test` — smoke-test all enabled channels

**Alerts router (`app/routers/alerts.py`, `/api/v1/alerts/...`):**

- `POST /send`, `POST /batch` — generic severity-routed sends
- `GET /history`, `GET /active`, `GET /{alert_id}` — read alerts
- `POST /acknowledge/{alert_id}` — ack to stop escalation
- `GET|PUT /config`, `GET|PUT /rules` — runtime config (PUT is in-memory only, not persisted)
- `GET /channels/status` — health per channel
- `POST /test/{channel}` — per-channel test (`telegram|email|slack|sms`); the `/api/v1/test/slack` shorthand in `progress.md` refers here
- `POST /trade`, `/risk`, `/system`, `/daily-summary` — convenience helpers
- `GET /stats` — N-hour aggregates

Total ~30 routes (skipping `/health`, `/ready`).

## Channels

| Channel | Client | Transport | Notes |
|---|---|---|---|
| Telegram | `app/channels/telegram_client.py` + legacy `app/telegram_notifier.py` | httpx → `api.telegram.org` | HTML parse-mode, `rate_limit=20/min`, 3 retries |
| Email | `app/channels/email_client.py` + legacy `app/email_notifier.py` | stdlib `smtplib` | Default `smtp.gmail.com:587`, HTML templates from `app/templates/template_engine.py`. **SMTP now uses `timeout=30`** (`email_notifier.py:73`) — blocking `smtplib.SMTP()` with no timeout could hang the event loop indefinitely. |
| Slack | `app/channels/slack_client.py` | httpx | Webhook URL **OR** Bot Token (`chat.postMessage`); per-severity routing to `#trading-critical`, `#trading-alerts`, `#bimo-performance` (added 2026-04, commits `6b79f52`, `1f53c33`, `4196fb6`) |
| SMS | `app/channels/sms_client.py` | Twilio SDK | `twilio==8.10.0` |
| Dashboard | (enum only) | — | Stored, never delivered (`alert_manager.py:162`) |

[[../concepts/Message-Queue-Topics]] — irrelevant here: this service does not consume any topic. Stays in HTTP land.

## Severity routing

From `app/config.py` and `alerts.py:32-46`:

- `CRITICAL` → Telegram + Email + Slack (`#trading-critical`) immediate
- `HIGH` → Telegram + Email within 1 min
- `MEDIUM` → Telegram OR Email by preference
- `LOW` → Email batched (interval `email_batch_interval=300s`)
- `INFO` → dashboard only

## Templates

`app/templates/template_engine.py` — `string.Template`-based. Includes `CRITICAL_ALERT_HTML` (red gradient banner). Telegram + Slack messages built inline in the channel clients (HTML parse-mode for Telegram, Block Kit for Slack).

## Internal dependencies

- **Redis** (`REDIS_URL`) — declared but rate-limit + dedup currently in-memory in `alert_rules_engine`.
- **PostgreSQL** (`DATABASE_URL`) — declared in config; **no live SQL writes** in current code despite `asyncpg` + `sqlalchemy[asyncio]` in `requirements.txt`. The `notifications` PG table referenced in `progress.md:671` is aspirational.
- **SQLite DLQ** — `/app/data/dlq.sqlite3`, table `failed_alerts`, written by `app/dlq.py` whenever `_build_delivery_response` raises 502/503. The only persistent store this service actually uses.
- **Prometheus** — `/metrics`, multiprocess via `PROMETHEUS_MULTIPROC_DIR` tmpdir set in lifespan.

## External dependencies

- Telegram Bot API
- SMTP server (default Gmail)
- Slack incoming webhook + `chat.postMessage`
- Twilio API (when `sms_enabled=true`)

## Used by

- [[trading-engine]] — heaviest caller. `app/services/notification_client.py` wraps it; `auto_trader.py` posts on every entry/exit/partial-exit and on critical events (~25 call sites).
- [[../flows/Order-Lifecycle]] — every state transition that emits a notification flows through this service.
- `ml-retraining-service` — declares `notification_service_url` in settings (retrain success/failure alerts).
- [[api-gateway]] — exports `NOTIFICATION_URL=http://notification-service:8006` for proxied admin routes.
- [[portfolio-manager]] — no direct calls found.
- [[risk-metrics-service]] — no direct calls; it has its own internal `/api/v1/alerts/active` route (path coincidence, different surface).

## Gotchas

- **No AMQP.** Despite `RABBITMQ_HOST=rabbitmq` in compose, no consumer code exists. Pure HTTP sink.
- **Port mismatch:** `app/config.py` defaults `port=8007`; compose binds `8006:8006`. Compose wins via env override.
- **False-success killed.** Legacy `/notify/*` endpoints used to always return `{"success": true}` regardless of channel-level failure. `_build_delivery_response` in `app/main.py` now raises 502 when any enabled channel fails, 503 when none are configured. Callers must inspect `failed_channels` in error detail and treat 502 as "delivery did not happen."
- **In-memory state.** Alert history (last 1000), suppression dedup, throttle counters all reset on restart. Only the SQLite DLQ persists.
- **DLQ never auto-replays.** `GET /api/v1/dlq` is read-only; replay endpoint is "follow-up" per code comment.
- **`PUT /api/v1/alerts/config` is a no-op** — logs intent, returns current config.
- **Daily summary is Telegram-only** by design.
- **Secrets:** `.env` under `services/notification-service/.env` holds real `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_WEBHOOK_URL`, `SMTP_PASSWORD`. Token redaction is installed at logger setup (`install_token_redaction()`).
- **`app/main.py.bak`** still in tree — pre-DLQ snapshot, unused.
- **`NOTIFICATION_TEST_MODE` default was silently swallowing every message (fixed 2026-07-29).** The compose default was `record`, which made `telegram_notifier.py` write each message to `tests/.notifications.log` and **`return True` (`telegram_sent=true`) without ever POSTing to Telegram** (`telegram_notifier.py:64–85`) — the operator got no alerts while the API reported success. Default is now empty (`docker-compose.unified.yml:702` `NOTIFICATION_TEST_MODE=${NOTIFICATION_TEST_MODE:-}`); `record` is opt-in. Real delivery is the default again.

## Contradictions vs project CLAUDE.md

- CLAUDE.md describes purpose as "Telegram + email alerts" — service actually supports **four** delivery channels (Telegram, Email, Slack, SMS) plus dashboard storage. Slack + SMS missing from the one-liner.
- Brief expected RabbitMQ consumption of `alert.critical` / `portfolio.update`. Not implemented; service is HTTP-only.
- Brief expected a `notifications` Postgres table. Doesn't exist; only the SQLite `failed_alerts` DLQ table is real.

## Related

- [[trading-engine]] — primary caller
- [[portfolio-manager]] — sibling service (does not call this one directly)
- [[risk-metrics-service]] — sibling; its `/api/v1/alerts/active` is unrelated
- [[api-gateway]] — proxies admin/notification routes
- [[../concepts/Message-Queue-Topics]] — context for why MQ does not appear here
- [[../flows/Order-Lifecycle]] — every notification fires from a step in this flow

## Corrections 2026-07-29

Reflects the 2026-07-29 production audit (verified in source):

- **`NOTIFICATION_TEST_MODE` default changed `record` → '' (real delivery)** (`docker-compose.unified.yml:702`). The old `record` default diverted every Telegram message to `tests/.notifications.log` while reporting `telegram_sent=true` (`telegram_notifier.py:64–85`) — operators never received alerts.
- **SMTP timeout added** (`email_notifier.py:73`, `timeout=30`) — blocking send with no timeout could hang the event loop.

## Source

Raw report: `wiki/.raw/agent-reports/notification-service.md`
