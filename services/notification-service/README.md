# notification-service

Alert delivery service (FastAPI, port **8006**): Telegram + email, with alert rules, a scheduler, and a dead-letter queue for failed sends.

**Real delivery is the default** since 2026-07-29 (ADR-025): `NOTIFICATION_TEST_MODE` default changed from `record` to empty. In `record` mode the service wrote notifications to a file while still reporting `telegram_sent=true` — the project's canonical false-pass example. If alerts seem silent, check this flag first, then the DLQ.

## Endpoints (prefix `/api/v1`, service-internal — the gateway drops `/v1`)

- `POST /notify/trade`, `/notify/pnl`, `/notify/daily-limit`, `/notify/error`, `/notify/startup`, `/notify/daily-summary` — typed notifications
- `POST /test` — send a test notification (use this for end-to-end delivery proof: a real Telegram message arriving, not a 200)
- `GET /dlq` — inspect failed deliveries
- `GET /config`, `GET /health`, `GET /ready`, `GET /metrics`

## Layout

`app/telegram_notifier.py`, `app/email_notifier.py`, `channels/`, `alert_manager.py` + `alert_rules.py`, `scheduler/`, `dlq.py`, `templates/`.

## Configuration

Telegram bot token + chat id and SMTP credentials via env (never committed — see `docs/setup/TELEGRAM_NOTIFICATIONS_SETUP.md`). Verification standard: a feature that "sends notifications" is only proven by a message arriving on a real channel (`/verify-stack`).

## Known gaps

- No integration with risk-metrics-service: `RiskAlert` objects with `CRITICAL` level are only surfaced if something polls that service's `GET /alerts` — nothing pushes them here.

More: `wiki/modules/notification-service.md`. Old coverage reports: `docs/archive/services/notification-service/`.
