---
phase: 07-tournament-view-smoke-test
plan: 06
subsystem: ci
tags:
  - ci
  - playwright
  - integration
  - workflow
requires:
  - tests/integration/test_dashboard_smoke.py (Plan 05)
  - tests/fixtures/tournament/smoke-fixture{,.ensemble,.significance}.json (Plan 05)
  - tournament_snapshot_seeded fixture in tests/integration/conftest.py (Plan 05)
provides:
  - pytest-playwright pinned in tests/integration/requirements.txt
  - playwright install --with-deps chromium step in both CI workflows
  - failure-only screenshot/HAR/trace artifact upload in both CI workflows
  - single `pytest tests/integration` invocation now collects the dashboard smoke
affects:
  - .github/workflows/integration.yml (push/PR gate — blocks merge on smoke failure)
  - .github/workflows/integration-ml-on.yml (nightly + manual ML-on variant)
tech-stack:
  added:
    - pytest-playwright>=0.5,<1.0 (PyPI; Microsoft-maintained Playwright Python plugin)
  patterns:
    - single dep file is the source of truth for the integration suite (no inline
      pip install drift between workflow and file)
    - failure-only artifact upload (if: failure()) with if-no-files-found: ignore
      so the step is green when the smoke didn't run
    - separate artifact name per workflow (`playwright-artifacts` vs
      `playwright-artifacts-ml-on`) to avoid GitHub Actions name collisions
key-files:
  created:
    - tests/integration/requirements.txt
    - .planning/phases/07-tournament-view-smoke-test/07-06-SUMMARY.md
  modified:
    - .github/workflows/integration.yml
    - .github/workflows/integration-ml-on.yml
decisions:
  - "D-18 implemented: pytest-playwright>=0.5 in tests/integration/requirements.txt + `playwright install --with-deps chromium` in both CI workflows (Chromium only, Firefox/WebKit deferred to v2)."
  - "D-20 implemented: smoke runs inside the existing `pytest tests/integration` step (NOT a parallel job, NOT an `npx playwright test` shim). Failures block PR merge via the same gate."
  - "D-22 implemented: pytest-playwright capture flags appended to the pytest invocation (`--screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure`) + failure-only artifact upload step (`actions/upload-artifact@v4`, retention-days: 14, if-no-files-found: ignore)."
metrics:
  tasks_completed: 2
  files_created: 2
  files_modified: 2
  duration: "approx. 10 min"
  completed: "2026-05-14"
---

# Phase 07 Plan 06: CI Wiring for Dashboard Smoke Summary

**One-liner.** Wired the Plan 05 audit-driven Playwright smoke into both CI workflows: pinned `pytest-playwright>=0.5,<1.0` in a new `tests/integration/requirements.txt`, added a `playwright install --with-deps chromium` step before stack boot, appended pytest-playwright capture flags to the existing `pytest tests/integration` invocation, and added a failure-only `upload-artifact@v4` step. Single CI command stays single (D-18); failures now block PR merge via the same gate that already blocks on backend regressions (D-20); failure artifacts (screenshot + video + trace) ship to the operator for triage (D-22).

## Files changed

### Created

| File | Purpose |
|------|---------|
| `tests/integration/requirements.txt` | Source of truth for the integration suite's Python deps. Lists Phase 2 baseline (`httpx`, `asyncpg`, `pytest`, `pytest-asyncio`) plus the new `pytest-playwright>=0.5,<1.0`. The workflow now installs via `pip install -r tests/integration/requirements.txt`, eliminating drift between the workflow's inline list and a dep file. |

### Modified

| File | Edits |
|------|-------|
| `.github/workflows/integration.yml` | 4 surgical edits: (1) `Install pytest dependencies` step now reads the dep file; (2) NEW `Install Playwright browsers (Chromium only, D-18)` step before `Boot stack`; (3) `Run integration suite` step appends `--screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure` to its `pytest` invocation; (4) NEW `Upload Playwright failure artifacts` step (`if: failure()`) between `Upload logs` and `Tear down`, artifact name `playwright-artifacts`, retention 14 days. |
| `.github/workflows/integration-ml-on.yml` | Same 4 edits applied symmetrically (PATTERNS.md line 535 mandate). Artifact name is `playwright-artifacts-ml-on` to prevent any future GitHub Actions name collision should both workflows ever post to the same artifact namespace; the substring `playwright-artifacts` is still present, satisfying the plan's "or equivalent" allowance for the canonical name. |

## Workflow step layout after this plan

### `.github/workflows/integration.yml` (push/PR gate)

| # | Step | Source | Notes |
|---|------|--------|-------|
| 1 | Checkout | unchanged | `fetch-depth: 0` (anti-mock guard) |
| 2 | Set up Python | unchanged | 3.12 |
| 3 | Install pytest dependencies | **EDITED** | now `pip install -r tests/integration/requirements.txt` |
| 4 | Install Playwright browsers (Chromium only, D-18) | **NEW** | `playwright install --with-deps chromium` |
| 5 | Boot stack via bootstrap.sh in tape mode | unchanged | Phase 2 |
| 6 | Run integration suite | **EDITED** | appends `--screenshot --video --tracing` flags |
| 7 | Anti-mock guard (D-12) | unchanged | Phase 2 invariant preserved |
| 8 | Collect docker logs | unchanged | `if: always()` |
| 9 | Upload logs | unchanged | `actions/upload-artifact@v4` |
| 10 | Upload Playwright failure artifacts | **NEW** | `if: failure()` |
| 11 | Tear down | unchanged | `if: always()`, `docker compose down -v` |

### `.github/workflows/integration-ml-on.yml` (nightly + manual ML-on variant)

Same shape; no Anti-mock guard step in this variant (it never had one — PR-only behavior).

## Artifact upload details (D-22)

```yaml
- name: Upload Playwright failure artifacts
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: playwright-artifacts            # ml-on variant uses playwright-artifacts-ml-on
    path: |
      test-results/                       # pytest-playwright trace/video output (newer plugin versions)
      playwright-report/                  # pytest-playwright HTML report
      tests/integration/.playwright/      # CONTEXT.md D-22 local destination
    if-no-files-found: ignore             # keep the step green when the smoke didn't run
    retention-days: 14
```

The three candidate paths cover every output destination pytest-playwright might write to, depending on plugin version and project layout. `if-no-files-found: ignore` keeps the step green when a failure happened upstream of the smoke (e.g. stack boot failed) and there are no Playwright outputs to upload.

## Pytest invocation (after Edit 3)

`integration.yml`:
```
pytest tests/integration -v --tb=short --screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure
```

`integration-ml-on.yml`:
```
pytest tests/integration -m ml_on -v --tb=short --screenshot=only-on-failure --video=retain-on-failure --tracing=retain-on-failure
```

These pytest-playwright plugin flags activate full capture only when a Playwright test (i.e. `test_dashboard_smoke.py`) actually fails; they are no-ops for the existing non-Playwright tests. Single command, no second invocation.

## Single-command CI invariant (D-18 / D-20)

`grep -nE 'npx playwright' .github/workflows/integration.yml .github/workflows/integration-ml-on.yml` returns **0 matches** — no Node shim, no parallel job. The smoke is collected by the same `pytest tests/integration` invocation the existing Phase 2 suite uses. That keeps the CI surface single: one command, one log, one set of failure modes.

## Verification (this plan)

| Check | Command | Result |
|-------|---------|--------|
| Dep file exists | `test -f tests/integration/requirements.txt` | PASSED |
| pytest-playwright pinned | `grep -nE 'pytest-playwright' tests/integration/requirements.txt` | 2 lines (comment + pin) |
| Phase 2 baseline preserved | `grep -cE '(pytest\|pytest-asyncio\|asyncpg\|httpx)' tests/integration/requirements.txt` | 6 |
| YAML parses (both) | `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/integration.yml')); yaml.safe_load(open('.github/workflows/integration-ml-on.yml'))"` | OK |
| playwright install in both | `grep -nE 'playwright install --with-deps chromium' .github/workflows/integration*.yml` | 2 matches |
| screenshot flag in both | `grep -nE '\-\-screenshot=only-on-failure' .github/workflows/integration*.yml` | 2 matches |
| artifact upload step in both | `grep -nE 'Upload Playwright failure artifacts' .github/workflows/integration*.yml` | 2 matches |
| `name: playwright-artifacts*` in both | `grep -nE 'name: playwright-artifacts' .github/workflows/integration*.yml` | 2 matches |
| teardown preserved in both | `grep -cE 'docker compose .* down -v' .github/workflows/integration*.yml` | 2 |
| anti-mock guard preserved | `grep -nE 'iter-fix-check-diff.sh' .github/workflows/integration.yml` | 1 |
| no `npx playwright` shim | `grep -nE 'npx playwright' .github/workflows/integration*.yml` | 0 |

All acceptance criteria from Plan 06 Task 2 satisfied.

## Step ordering verified

`integration.yml` step order: Checkout → Set up Python → Install pytest dependencies → **Install Playwright browsers** → Boot stack → Run integration suite → Anti-mock guard → Collect docker logs → Upload logs → **Upload Playwright failure artifacts** → Tear down.

`integration-ml-on.yml` step order: Checkout → Set up Python → Install pytest dependencies → **Install Playwright browsers** → Boot stack with ML enabled → Run ML-on suite → Collect docker logs → Upload logs → **Upload Playwright failure artifacts** → Tear down.

Both: Playwright install lands BEFORE stack boot (so the `playwright` CLI is on PATH for the pytest run), and the failure-artifact upload lands BEFORE Tear down (so the test-results directory still exists at upload time — `docker compose down -v` only tears down the stack, but the runner workdir is wiped after the job ends).

## Deviations from Plan

None — plan executed exactly as written. Two minor judgment calls noted, neither requiring a deviation rule:

1. **ML-on artifact name `playwright-artifacts-ml-on`** instead of `playwright-artifacts`. The plan explicitly allows "or equivalent" for the artifact name; using a per-workflow name prevents `actions/upload-artifact@v4` from rejecting a duplicate name should both workflows ever post in the same context. The substring `playwright-artifacts` is still present in both files (acceptance grep passes).

2. **Removed the explicit `pip install pytest-playwright>=0.5` line from the install step** — PATTERNS.md line 532 showed it as a separate inline install. Because Task 1 created `tests/integration/requirements.txt` with the pin and Edit 1 now installs from that file, the inline install would be a duplicate. The plan's Path B explicitly anticipated this consolidation ("the workflow edit in Task 2 then becomes `pip install -r tests/integration/requirements.txt` (replacing the inline list)" — Plan Task 1 action body).

## Deferred Issues

1. **Live CI run not yet performed.** Plan verification step 6 ("Push the branch and confirm the PR's `Integration Suite (Phase 2)` check turns green with the new install step visible in the job log") is an operator action; CONTEXT.md and STATE.md note that workflow billing must be unblocked first. Until then, the green-run signal is unavailable. The static verification above (YAML parse + grep coverage) is the strongest signal this worktree can produce.

2. **Plan 05 Deferred Issue 1 (pytest-playwright async-fixture compatibility) still latent.** Plan 05's summary flagged that `tape_reset` is `async def` and may need `pytest-asyncio` mode `auto` (or a sync wrapper) to compose with pytest-playwright's sync `page` fixture. This plan installs pytest-playwright but does NOT exercise it — the first green CI run is what will surface (or rule out) this issue. If the first run fails on it, the fix lives in Plan 06's executor's hands per Plan 05's note OR a follow-up plan; no preemptive change made here.

## Self-Check

Files exist:
- `tests/integration/requirements.txt` → FOUND
- `.github/workflows/integration.yml` (modified) → FOUND
- `.github/workflows/integration-ml-on.yml` (modified) → FOUND
- `.planning/phases/07-tournament-view-smoke-test/07-06-SUMMARY.md` → FOUND (this file)

Commits exist (`git log --oneline`):
- `b9bd623 chore(07-06): add pytest-playwright to integration test deps` → FOUND
- `3b5bbb4 ci(07-06): wire Playwright into integration workflows` → FOUND

## Self-Check: PASSED
