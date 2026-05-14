---
phase: 02-integration-test-suite-runbook
plan: 9
subsystem: ci
tags: [github-actions, ci, integration-test, anti-mock-guard, ml-on, tape-mode]
dependency_graph:
  requires: [02-04, 02-06]
  provides: [GitHub Actions per-push integration CI, nightly ML-on variant CI]
  affects: [all services via bootstrap.sh, tests/integration/]
tech_stack:
  added: [GitHub Actions workflows]
  patterns: [bootstrap.sh session fixture in CI, anti-mock guard via iter-fix-check-diff.sh, secrets via env: not run:]
key_files:
  created:
    - .github/workflows/integration.yml
    - .github/workflows/integration-ml-on.yml
  modified: []
decisions:
  - "Anti-mock guard gated to pull_request events only (not push); operator must configure branch protection for structural enforcement"
  - "ML-on variant runs on schedule + workflow_dispatch only (CD-05); not on push/PR"
  - "cancel-in-progress: false on ML-on workflow so manual runs are not aborted by nightly cron"
  - "timeout-minutes: 30 default, 45 ML-on (model load slower)"
  - "Secrets passed via env: not echoed in run: (T-02-09-01 mitigated; GitHub Actions auto-masks)"
metrics:
  duration: "7m 5s"
  completed_date: "2026-05-08T12:58:28Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 0
---

# Phase 02 Plan 09: GitHub Actions CI Workflows for Integration Suite Summary

GitHub Actions CI wired for Phase 2 integration suite: deterministic per-push workflow with anti-mock guard + nightly ML-on variant.

## What Was Built

Two GitHub Actions workflows created to enforce the fresh-clone proof boundary in CI:

**`.github/workflows/integration.yml`** — Per-push + PR integration suite:
- Triggers on `push: branches: ['**']` and `pull_request: branches: [main, develop]`
- Boots stack via `bash bootstrap.sh` in tape mode (D-07: same invocation as local)
- Runs `pytest tests/integration -v --tb=short` (deterministic, no `continue-on-error`)
- Anti-mock guard step (D-12): gated to `pull_request` events; pipes `git diff origin/main..HEAD -- 'tests/'` through `scripts/iter-fix-check-diff.sh` (Plan 02-06 deliverable)
- Uploads docker compose logs as artifact on failure (`integration-logs.txt`, 14-day retention)
- Tears down via `docker compose -f docker-compose.unified.yml down -v` in `if: always()` step
- Secrets: `TEST_TELEGRAM_BOT_TOKEN` and `TEST_TELEGRAM_CHAT_ID` injected via `env:` from `secrets.*` (never echoed in `run:`)
- `timeout-minutes: 30` to bound CI cost (T-02-09-05)

**`.github/workflows/integration-ml-on.yml`** — Nightly + manual ML-on variant (CD-05):
- Triggers on `schedule: cron: '0 6 * * *'` (06:00 UTC nightly) + `workflow_dispatch`
- Does NOT trigger on `push` or `pull_request` — that is the default workflow's responsibility
- Flips `ENABLE_ML_PREDICTIONS: 'true'` to enable GRU model loading during bootstrap
- Runs `pytest tests/integration -m ml_on -v --tb=short` (CD-05 marker)
- `concurrency cancel-in-progress: false` so manual runs are not aborted by next nightly cron
- `timeout-minutes: 45` (ML model load + inference requires more time than tape-only run)
- Same log artifact upload + `down -v` teardown shape as integration.yml
- Anti-mock guard NOT included (requires pull_request events which this workflow does not fire on)

## Decisions Addressed

| Decision | Resolved |
|----------|---------|
| D-07 | `bash bootstrap.sh` in CI uses same invocation as local operator |
| D-12 | Anti-mock guard wired as CI step on PR events via `iter-fix-check-diff.sh` |
| CD-01 | CI sets `NOTIFICATION_TEST_MODE=live` + injects Telegram secrets for live notification verification |
| CD-05 | ML-on variant runs nightly + manual via separate workflow; default suite runs ML-off |

## Threat Model Items Closed

| ID | Status |
|----|--------|
| T-02-09-01 | Mitigated: secrets passed via `env:`, never echoed; GitHub Actions auto-masks `secrets.*` in logs |
| T-02-09-02 | Accepted: `docker compose logs` artifact does not contain bot token (notification-service logs `bot_token_set=True` boolean, not the token itself) |
| T-02-09-03 | Partially mitigated: anti-mock guard is gated to `pull_request`; direct pushes bypass it. **Operator action required: configure GitHub branch protection** (see below) |
| T-02-09-04 | Mitigated: forked PR anti-mock guard still runs; forked-PR jobs get read-only secrets by default (Telegram notification fails gracefully, guard still enforces) |
| T-02-09-05 | Mitigated: `timeout-minutes: 30` (default) / `45` (ML-on) |
| T-02-09-06 | Accepted: GitHub Actions artifacts immutable post-upload |

## Operator Actions Required

**MUST configure GitHub branch protection before relying on anti-mock guard (Warning #1):**

The anti-mock guard step runs only on `pull_request` events. Direct pushes to `main`/`master` bypass it. To make the guard structural:

1. Navigate to GitHub repo → Settings → Branches → Branch protection rules
2. Add a rule for `main` (and `master` if used):
   - "Require a pull request before merging" — checked
   - "Require status checks to pass before merging" — checked; add `Integration Suite (Phase 2)` to required checks
   - "Do not allow bypassing the above settings" — checked
   - "Require linear history" — recommended
3. Without this configuration, an operator can push a test-muted diff directly to main and the guard never runs

**MUST configure GitHub secrets before CI can pass:**

- `secrets.TEST_TELEGRAM_BOT_TOKEN` — dedicated test Telegram bot token
- `secrets.TEST_TELEGRAM_CHAT_ID` — private test channel chat ID

These must be set in GitHub repo Settings → Secrets and variables → Actions before the workflow can complete the notification verification step.

## Commits

| Task | Commit | Files |
|------|--------|-------|
| Task 1: integration.yml | `44f83a6` | `.github/workflows/integration.yml` (created) |
| Task 2: integration-ml-on.yml | `d383683` | `.github/workflows/integration-ml-on.yml` (created) |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — both workflow files are complete and reference existing deliverables (bootstrap.sh, scripts/iter-fix-check-diff.sh) from prior plans.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes beyond those already covered in the plan's threat model.

## Self-Check: PASSED

- `[ -f .github/workflows/integration.yml ]`: FOUND
- `[ -f .github/workflows/integration-ml-on.yml ]`: FOUND  
- Commit `44f83a6` in git log: FOUND
- Commit `d383683` in git log: FOUND
