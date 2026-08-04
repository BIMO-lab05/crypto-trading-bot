---
type: decision
status: accepted
date: 2026-07-29
context: "NOTIFICATION_TEST_MODE defaulted to 'record' — every alert was written to a log file inside the container while reporting telegram_sent=true; operator received nothing"
deciders: [operator]
tags: [decision, adr, notification-service, config]
created: 2026-07-29
updated: 2026-07-29
---

# ADR-025: notification real-delivery is the default (NOTIFICATION_TEST_MODE '' not 'record')

## Context

`NOTIFICATION_TEST_MODE` defaulted to `record` (WR-05, for integration tests). In record mode the notification service writes every message to `tests/.notifications.log` *inside the container* while still reporting `telegram_sent=true`. The operator therefore received **zero** Telegram messages and nothing in the logs looked wrong — a silent-failure default. Test-mode should be opt-in, not the shipping default.

## Decision

In `docker-compose.unified.yml`, the notification-service default changed to real delivery:

```yaml
- NOTIFICATION_TEST_MODE=${NOTIFICATION_TEST_MODE:-}      # '' = real POST path
- NOTIFICATION_RECORD_PATH=${NOTIFICATION_RECORD_PATH:-tests/.notifications.log}
```

An empty value selects the production POST path. `record` mode is now opt-in: export `NOTIFICATION_TEST_MODE=record` when running `pytest tests/integration` (the host conftest also sets it). `docker-compose.unified.yml:694-703`.

## Consequences

- Normal operation actually delivers Telegram/email alerts; the operator sees fills, exits, and kill-switch events.
- Integration tests must set `NOTIFICATION_TEST_MODE=record` explicitly (conftest handles it) to keep writing to the record log instead of POSTing.
- No code change — a compose default flip; existing env overrides are respected via `${...:-}`.

## Related

- `docker-compose.unified.yml:694-703`
- [[../modules/notification-service]]
- [[ADR-009-docker-compose-unified-canonical]]
