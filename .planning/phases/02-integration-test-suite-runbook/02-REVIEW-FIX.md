---
phase: 02-integration-test-suite-runbook
fixed: 2026-05-08T00:00:00Z
review_path: .planning/phases/02-integration-test-suite-runbook/02-REVIEW.md
fix_scope: critical_warning
applied: 4
deferred: 9
total_findings: 13
status: partial
---

# Code Review Fix Report — Phase 02

## Summary

Source: `02-REVIEW.md` (4 BLOCKER + 9 WARNING = 13 findings).

The auto-fixer agent (gsd-code-fixer) hit a token-quota limit before producing a fix
report. Orchestrator applied the 4 BLOCKER findings manually as atomic commits;
9 WARNING findings remain deferred to a gap-closure phase or follow-up cleanup.

## Applied (BLOCKERs — 4 of 4)

| ID | Commit | File | Fix |
|----|--------|------|-----|
| BL-01 | `c102a44` | `tests/integration/test_fresh_clone_round_trip.py` | Renamed `/api/v1/market/tickers` (plural) → `/api/v1/market/ticker` (singular) at lines 44 and 141 to match the route declared in `services/bybit-connector/app/main.py:741`. Headline e2e test no longer 404s on the ticker fetch. |
| BL-02 | `884ca4d` | `bootstrap.sh` | Added `--profile ml --profile analytics` to both `docker compose up` invocations. ml-prediction:8007 and sentiment-analysis-service:8008 are profile-gated in `docker-compose.unified.yml:710-711,757-758` and were skipped without the flags, causing the health probe to exit 1. |
| BL-03 | `63a39c2` | `docker-compose.unified.yml` | Renamed compose's `TELEGRAM_TEST_BOT_TOKEN`/`TELEGRAM_TEST_CHAT_ID` (lines 641-642) to `TEST_TELEGRAM_BOT_TOKEN`/`TEST_TELEGRAM_CHAT_ID` to align with the workflow contract in `.github/workflows/integration*.yml` and `tests/integration/conftest.py:250`. CI Telegram secrets now reach the notification-service container. |
| BL-04 | `3bd8d55` | `services/bybit-connector/app/{config.py,main.py}` | Replaced `allow_origins=["*"]` with `allow_credentials=True` (spec-violating) by introducing `cors_origins` + `internal_service_origins` fields and `all_cors_origins` property in `Settings` (mirrors trading-engine pattern in `services/trading-engine/app/config.py:587-613,667-670`). Middleware now uses `settings_instance.all_cors_origins`. |

## Deferred (WARNINGs — 9 of 9)

The 9 WARNING findings remain in `02-REVIEW.md` with severity-tagged entries
(`### WR-01` through `### WR-09`). They are non-blocking for phase-02 verification:

- **WR-01** anti-mock guard threshold-lowering regex is one-sided — `iter-fix-check-diff.sh`
- **WR-02** `[DEBUGGER:...]` print-style logger calls in production telegram_notifier.py
- **WR-03** file-handle leak in `tests/integration/test_notification_delivery.py:49`
- **WR-04** dead `try: pass except: pass` in bybit-connector `/metrics`
- **WR-05** `notification_test_mode` host fixture default mismatch with container default
- **WR-06** `force_signal` integration test sends lowercase `"buy"` while unit test uses `"BUY"`
- **WR-07** `_load_model` falsy-return on success-without-metadata in gru_predictor — `_reload_if_stale` reports "no reload" on a successful reload
- **WR-08** `notification_test_mode` accepts arbitrary strings; case-sensitive equality silently breaks `RECORD`/`Record`
- **WR-09** `bootstrap.sh` creates `EMERGENCY_STOP`, integration suite never removes it — undocumented coupling

Recommended path: roll WR-01..WR-09 into a gap-closure phase (e.g. 02.1) or address
during the next quality pass. None block the phase-02 acceptance criteria; all
involve tests, infrastructure ergonomics, or auditing-friendly cleanups.

## Notes

- The auto-fixer agent (`gsd-code-fixer`) terminated at the per-account token quota
  limit (resets ~17:30 Africa/Algiers) after 110 tool invocations without producing
  any commits. Manual BL-* application was the recovery path.
- All 4 BL commits passed Python/YAML/bash syntax validation before commit.
- Cross-plan integration: BL-01 + BL-02 + BL-03 jointly unblock the headline
  `test_fresh_clone_round_trip` test (INFRA-01). BL-04 closes a credential-leak
  surface independent of phase-02 requirements but is in scope per the review.
