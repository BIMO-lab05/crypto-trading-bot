---
type: raw-report
service: notification-service
generated: 2026-05-05
source_paths:
  - services/notification-service/app/main.py
  - services/notification-service/app/routers/alerts.py
  - services/notification-service/app/alert_manager.py
  - services/notification-service/app/channels/
  - services/notification-service/app/dlq.py
  - services/notification-service/app/config.py
  - services/notification-service/app/templates/template_engine.py
  - docker-compose.unified.yml
  - progress.md (lines 645-680)
---

# notification-service — raw agent report

Multi-channel alert/notification microservice. HTTP-only consumer (no MQ subscriber); siblings call its REST API to fan out alerts across Telegram, Email, Slack, SMS.

## Endpoints

Source: `app/main.py` + `app/routers/alerts.py`. All routes prefixed `/api/v1/...`. Skipping `/health`, `/ready`.

**Top-level (legacy + ops, in `app/main.py`):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Service info, channel flags, endpoint map |
| GET | `/metrics` | Prometheus scrape (multiprocess-aware) |
| GET | `/api/v1/config` | Echoes channel + alert toggles |
| POST | `/api/v1/notify/trade` | Trade-execution alert (legacy) |
| POST | `/api/v1/notify/pnl` | P&L alert (legacy) |
| POST | `/api/v1/notify/daily-limit` | Daily-loss-limit hit |
| POST | `/api/v1/notify/error` | Error notification |
| POST | `/api/v1/notify/startup` | Service-startup banner |
| POST | `/api/v1/notify/daily-summary` | Daily summary (Telegram-only) |
| GET | `/api/v1/dlq` | List recent failed-delivery rows from SQLite DLQ |
| POST | `/api/v1/test` | Smoke-test all enabled channels |

**Alerts router (`/api/v1/alerts`, in `app/routers/alerts.py`):**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/alerts/send` | Severity-routed multi-channel send |
| POST | `/api/v1/alerts/batch` | Batch send |
| GET | `/api/v1/alerts/history` | Paginated history (in-memory, last 1000) |
| GET | `/api/v1/alerts/active` | Unacknowledged alerts |
| GET | `/api/v1/alerts/{alert_id}` | Single alert |
| POST | `/api/v1/alerts/acknowledge/{alert_id}` | Ack to stop escalation |
| GET | `/api/v1/alerts/config` | Routing + suppression + escalation + quiet-hours config |
| PUT | `/api/v1/alerts/config` | Logs update intent (no persistence) |
| GET | `/api/v1/alerts/channels/status` | Health, sent-today, failures-today per channel |
| POST | `/api/v1/alerts/test/{channel}` | Per-channel test (`telegram\|email\|slack\|sms`) |
| GET | `/api/v1/alerts/rules` | Suppression + escalation rules |
| PUT | `/api/v1/alerts/rules` | Update rules in memory |
| GET | `/api/v1/alerts/stats` | Stats over N hours |
| POST | `/api/v1/alerts/trade` | Convenience trade alert |
| POST | `/api/v1/alerts/risk` | Convenience risk alert |
| POST | `/api/v1/alerts/system` | Convenience system alert |
| POST | `/api/v1/alerts/daily-summary` | Convenience daily summary |

**`/api/v1/test/slack` mentioned in progress.md:** does **not** exist as a literal route. Source for that line is `progress.md:670` ("live `/api/v1/test/slack` smoke … needs SLACK_BOT_TOKEN"). The actual route is **`POST /api/v1/alerts/test/{channel}`** with `channel=slack`. The `progress.md` shorthand is informal.

ADR-007 mentions "no /v1/ prefix" — notification-service ignores that ADR; every route here is `/api/v1/...`.

## Channels supported

Source: `app/channels/`.

- **Telegram** — `telegram_client.py` (legacy `telegram_notifier.py` for old endpoints). Bot API via httpx, HTML parse-mode.
- **Email** — `email_client.py` (legacy `email_notifier.py`). Stdlib `smtplib` (per requirements.txt comment "no additional packages needed").
- **Slack** — `slack_client.py`. Two paths: webhook URL (`SLACK_WEBHOOK_URL`) or Bot Token (`SLACK_BOT_TOKEN` → `chat.postMessage`). Per-severity channel routing: `#trading-critical`, `#trading-alerts`, `#bimo-performance`. Per-severity routing added 2026-04 (commits `6b79f52`, `1f53c33`, `4196fb6`).
- **SMS** — `sms_client.py`. Twilio (in `requirements.txt: twilio==8.10.0`).
- **Dashboard** — listed in `NotificationChannel` enum but stored only, not delivered (see `alert_manager.py:162` "Dashboard notifications are stored but not sent").

So **4 delivery channels + 1 store-only**. `health_check()` reports flags for `email`, `telegram`, `slack`, `sms` only.

## Templates / formatting

`app/templates/template_engine.py` — `string.Template` based. Includes:
- `CRITICAL_ALERT_HTML` — full HTML email template with red gradient banner, alert box, action-required block.
- Telegram messages built directly in `telegram_notifier.py` / `telegram_client.py` with HTML parse-mode.
- Slack messages use rich Block-Kit blocks built in `slack_client.py`.

## Internal deps

- **External APIs called:**
  - Telegram Bot API (`https://api.telegram.org`)
  - SMTP (configurable host; default `smtp.gmail.com:587`)
  - Slack incoming webhook OR `https://slack.com/api/chat.postMessage`
  - Twilio API (when SMS enabled)
- **Internal deps:**
  - **Redis** — declared in compose (`REDIS_HOST=redis`) and `redis==5.0.1` in requirements; intended for rate limiting / dedup. Currently rate-limit + dedup live in `alert_rules_engine` in-memory; Redis hookup is opt-in.
  - **PostgreSQL** — `database_url` field in config, `asyncpg` + `sqlalchemy[asyncio]` in requirements. **No live SQL writes** in current code (see DB tables section).
  - **SQLite** — `app/dlq.py` uses stdlib `sqlite3` against `/app/data/dlq.sqlite3` for the dead-letter queue.
- **No RabbitMQ / no AMQP / no aio_pika** — not in requirements, not imported anywhere in `app/`. Service is purely a REST sink, despite `RABBITMQ_HOST=rabbitmq` env var injected by docker-compose (unused).
- **prometheus-client** — `/metrics` endpoint, multiprocess-aware via `PROMETHEUS_MULTIPROC_DIR` tmpdir created in lifespan.

## Used by

Direct HTTP callers (port 8006, var name `NOTIFICATION_SERVICE_URL` or `NOTIFICATION_URL`):

- **trading-engine** — `services/trading-engine/app/services/notification_client.py` wraps it; `auto_trader.py` calls `notify_trade_open`, `notify_trade_close`, `send_notification` on every entry/exit/partial-exit + critical events (lines 1824, 2345, 2535, 2599, 2614, 2659, 2729, 2991, 3345). 25+ call sites.
- **ml-retraining-service** — `services/ml-retraining-service/app/config/settings.py:32` declares `notification_service_url` (presumably to alert when retrain finishes/fails).
- **api-gateway** — env var `NOTIFICATION_URL=http://notification-service:8006` (compose line 280), used for proxying alert routes.
- **portfolio-manager / risk-metrics-service** — searched, no direct HTTP calls found. risk-metrics has its **own** internal `/api/v1/alerts/active` route (different surface, same path coincidence).

## RabbitMQ

**None.** No AMQP consumer or publisher. The CLAUDE.md / brief assumed there'd be one (consumes `alert.critical`, `portfolio.update`, …) — not implemented. All alerts arrive via direct HTTP POST. Compose injects `RABBITMQ_HOST=rabbitmq` but the service does not connect.

## DB tables

- **`failed_alerts`** (SQLite, `app/dlq.py`):
  - Path: `/app/data/dlq.sqlite3` (overridable via `DLQ_DB_PATH`).
  - Columns: `id`, `created_at`, `endpoint`, `failed_channels`, `payload_json`, `response_json`. Index on `created_at DESC`.
  - Purpose: any 502/503 from `_build_delivery_response` in `main.py` enqueues here for replay/audit.
- **`notifications` table (PostgreSQL)** — referenced in `progress.md:671` ("`notifications` row inserted") but **NOT FOUND** in the notification-service code. `database_url` is declared but unused in the alert path. No `CREATE TABLE notifications` and no `INSERT INTO notifications` anywhere under `services/notification-service/app/`. progress.md aspiration vs. code reality.

## Key files

1. `services/notification-service/app/main.py` — FastAPI app, legacy notify endpoints, lifespan, Prometheus middleware, DLQ-aware delivery helper (804 lines).
2. `services/notification-service/app/routers/alerts.py` — full `/api/v1/alerts/...` router (464 lines).
3. `services/notification-service/app/alert_manager.py` — orchestration, per-severity routing, in-memory history (last 1000), batch queue, escalation. `alert_manager` singleton.
4. `services/notification-service/app/alert_rules.py` — suppression + escalation rule engine (`alert_rules_engine` singleton).
5. `services/notification-service/app/channels/{base,telegram_client,email_client,slack_client,sms_client}.py` — channel implementations sharing `BaseChannel` (rate limit + retry + result type).
6. `services/notification-service/app/dlq.py` — SQLite DLQ for failed deliveries.
7. `services/notification-service/app/config.py` — `NotificationConfig` + `AlertSeverity` / `AlertType` / `NotificationChannel` enums.
8. `services/notification-service/app/models.py` — Pydantic models for the alerts router.
9. `services/notification-service/app/templates/template_engine.py` — HTML email templates.
10. `services/notification-service/tests/test_slack_client.py` — 4 new tests added 2026-04 to cover bot-token branch (per `progress.md:653`).

Misc: `app/main.py.bak` lingers next to `main.py` — pre-DLQ snapshot, not imported. Should be deleted.

## Gotchas

- **Service code says `port=8007`** (`app/config.py:47`), but compose maps `8006:8006` and exports `SERVICE_PORT=8006`. Compose env wins (pydantic-settings reads `SERVICE_PORT`), but the default in source is wrong/misleading.
- **Secrets via `.env` (gitignored).** `.env` for this service holds real `TELEGRAM_BOT_TOKEN`, `SLACK_BOT_TOKEN`, `SLACK_WEBHOOK_URL`, `SMTP_PASSWORD`. Compose does `env_file: ./services/notification-service/.env` (line 629), then overlays a small `environment:` block. Token redaction installed at startup (`install_token_redaction()` in `main.py:54`) so they don't leak to logs.
- **False-success eradication (commit not noted in progress.md):** `_build_delivery_response` in `main.py` raises HTTP 502 when *any* enabled channel fails delivery, and 503 when no channels are configured. Previously every legacy `/notify/*` returned `{"success": True}` regardless of `email_sent` / `telegram_sent`. Callers must now expect non-2xx and inspect `failed_channels` in the response detail.
- **Dedup / throttle live in `alert_rules_engine` (in-memory).** Restart loses dedup state; first alert post-restart can resend something the user already saw 30s before the restart.
- **In-memory alert history (last 1000).** Restart loses everything visible at `/api/v1/alerts/history`. The DLQ is the only persistent store, and it only holds *failures*.
- **`PUT /api/v1/alerts/config` is a no-op** — logs the request, does not persist (router comment says so).
- **Retry logic per channel is per-message.** `BaseChannel` rate_limit/retry_attempts/retry_delay used by Telegram (`rate_limit=20/min`, `retry_attempts=3`), Slack (`rate_limit=60/min`), Email, SMS. No exponential backoff scheduler across the service.
- **DLQ never replayed automatically.** `/api/v1/dlq` is read-only. Replay endpoint is "a separate follow-up" per code comment in `main.py:711`.
- **Daily summary endpoint is Telegram-only by design** (line 661–698). Email/Slack get nothing on daily summaries.

## Contradictions vs CLAUDE.md

- **CLAUDE.md says: "Telegram + email alerts."** Service actually supports **Telegram, Email, Slack, SMS**, plus dashboard storage. CLAUDE.md is two channels behind.
- **Brief assumed RabbitMQ consumer** (`alert.critical`, `portfolio.update` topics). **Not implemented.** Service is HTTP-only. CLAUDE.md does not contradict this directly, but the wider system docs imply event-driven alerting that doesn't exist on this side.
- **Brief assumed `notifications` table in Postgres.** Not present in code. Only `failed_alerts` in SQLite DLQ exists. `progress.md` reference (line 671) is aspirational.
- **`/api/v1/test/slack` (progress.md:670)** does not exist literally. Real route is `POST /api/v1/alerts/test/slack`.
- **ADR-007 ("no /v1/ prefix on gateway routes")** does not apply here — every notification-service route uses `/api/v1/`. This is on-purpose: the ADR is about the API gateway's external surface, not internal service surfaces. No real contradiction, but worth noting for anyone proxying these through the gateway.
- **Port discrepancy:** code default `8007`, compose `8006`. Compose authoritative.
