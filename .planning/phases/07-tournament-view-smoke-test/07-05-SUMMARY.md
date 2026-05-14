---
phase: 07-tournament-view-smoke-test
plan: 05
subsystem: testing
tags:
  - smoke-test
  - playwright
  - audit-driven
  - tournament
  - dashboard
requires:
  - 06-TILE-AUDIT.json (data_testid wired on every non-REMOVED row by Plan 03)
  - forceStale wrapped on all 5 LABELED_STALE tile component_files (Phase 6 Plan 06-05)
  - bootstrap_stack + tape_reset fixtures (Phase 2 conftest)
  - api-gateway RO bind-mount of services/tournament-harness/data/snapshots/ -> /app/snapshots (Phase 7 D-01)
provides:
  - committed deterministic tournament snapshot (primary + 2 Phase 4 sidecars)
  - tournament_snapshot_seeded pytest fixture (function-scope, 3-file seed + 3-file teardown)
  - audit-driven Playwright smoke test (single test, walks every TILE-AUDIT row)
affects:
  - Plan 06 will install pytest-playwright + Chromium and invoke `pytest tests/integration/test_dashboard_smoke.py -v --tb=short`
tech-stack:
  added:
    - pytest-playwright (deferred to Plan 06 install)
  patterns:
    - audit-as-source-of-truth (smoke loads 06-TILE-AUDIT.json at runtime; no inlined tile list)
    - hard-gate-no-escape-hatch (data_testid coverage gate fails fast on missing rows)
    - fixture-trio seed/teardown (primary + ensemble + significance staged into RO bind-mount)
key-files:
  created:
    - tests/fixtures/tournament/smoke-fixture.json
    - tests/fixtures/tournament/smoke-fixture.ensemble.json
    - tests/fixtures/tournament/smoke-fixture.significance.json
    - tests/integration/test_dashboard_smoke.py
    - .planning/phases/07-tournament-view-smoke-test/07-05-SUMMARY.md
  modified:
    - tests/integration/conftest.py (added tournament_snapshot_seeded fixture)
decisions:
  - "D-08 (smoke fixture path + tournament_snapshot_seeded pytest fixture) implemented"
  - "D-15 (full audit-driven coverage — smoke iterates every row in 06-TILE-AUDIT.json) implemented"
  - "D-17 (StatusBar D-17 substrings asserted explicitly: PAPER / ARMED / OFF / INACTIVE / idle|live) implemented"
  - "D-19 (reuse Phase 2 bootstrap_stack + tape_reset fixtures) implemented"
  - "D-21 (local invocation via plain pytest) implemented"
  - "D-22 (failure artifacts handled by pytest-playwright CLI flags, wired in Plan 06)"
  - "W-3 Path A: Phase 4 sidecars committed so smoke exercises BOTH significance-badge-pass AND significance-badge-none paths in one run"
  - "BL-1 page-aware navigation: PAGE_LEVEL_ROUTE_OVERRIDE map + PAGE_ROUTES table drive page.goto per audit row"
metrics:
  tasks_completed: 2
  files_created: 5
  files_modified: 1
  duration: "approx. 25 min"
  completed: "2026-05-14"
---

# Phase 07 Plan 05: Audit-Driven Dashboard Smoke Test Summary

**One-liner.** Authored the audit-driven Playwright dashboard smoke (Phase 7 DASH-06): a single pytest-playwright test reads `06-TILE-AUDIT.json` at runtime, hard-asserts every non-REMOVED row carries a `data_testid`, walks every audit row asserting verdict-specific visibility against the gateway origin (`http://localhost:8000`), and exercises both Phase 4 significance paths via committed sidecars. Five files: primary fixture JSON, 2 Phase 4 sidecar JSONs, conftest extension, and the new test file.

## What this plan ships

### Three-file fixture layout (committed, deterministic)

| File | Purpose |
|------|---------|
| `tests/fixtures/tournament/smoke-fixture.json` | Primary snapshot mirroring `export_snapshot()` (`services/tournament-harness/app/leaderboard/snapshot.py`). 7 rows across {SOL, BNB, ADA} × {GRU, LSTM}, exactly 1 row with `status="failed"` (`BNB/LSTM`, `failure_reason="nan_loss"`), every row sets `train_window_includes_contaminated=false`, only `SOL/GRU` row has `dsr >= 1.0` (=1.142). `summary.n_rows=7`, `n_success=6`, `n_failed=1`. |
| `tests/fixtures/tournament/smoke-fixture.ensemble.json` | Single ensemble for symbol SOL whose `members[0].run_id` / `hp_hash` / `dsr` are byte-identical to the SOL/GRU success row in the primary fixture (the frontend joins on `run_id`, so byte equality is load-bearing). |
| `tests/fixtures/tournament/smoke-fixture.significance.json` | `per_symbol.SOL.win_gate_passed=true`; `per_symbol.BNB.win_gate_passed=false`; `per_symbol.ADA.win_gate_passed=false`. Drives the smoke to assert BOTH `significance-badge-pass` (SOL/GRU only) AND `significance-badge-none` (the other 5 success rows + 1 failed row). |

### `tournament_snapshot_seeded` fixture (`tests/integration/conftest.py`)

Function-scope. Copies the three committed fixtures into `services/tournament-harness/data/snapshots/smoke-tape-fixture{,.ensemble,.significance}.json` (the source path of the `/app/snapshots:ro` bind mount declared in `docker-compose.unified.yml` for `api-gateway`). On teardown, unlinks all three files. Uses `pathlib.Path.read_text` / `write_text` to bypass the `builtins.open` mocking trap (per project memory `feedback_pathlib_mocking.md`).

Reuses the existing `_repo_root()` helper (`tests/integration/conftest.py` lines 53-60); no new helper added.

### Audit-driven smoke (`tests/integration/test_dashboard_smoke.py`)

Single test: `test_every_audited_tile_renders_per_verdict`.

Decorators / fixtures:

- `@pytest.mark.usefixtures("bootstrap_stack", "tape_reset", "tournament_snapshot_seeded")`
- Session-scope `tile_audit` fixture reads `06-TILE-AUDIT.json` at runtime (NOT inlined into the test source) — any Plan 03 audit edit is picked up automatically.
- Session-scope `browser_context_args` override pins viewport to 1440x900 (matches the audit's capture size).

Selector contract (one line per data-testid asserted):

| data-testid | Asserted by step | Expectation |
|-------------|------------------|-------------|
| `statusbar` | Step 2 (initial wait) + Step 5 (D-17 substrings) | visible after `/` loads under `networkidle` |
| `<row.data_testid>` for FIXED rows | Step 3 (per-row verdict loop) | visible AND `inner_text().strip() != ""` |
| `<row.data_testid> [data-testid="tile-stale-badge"]` for LABELED_STALE rows | Step 3 | visible (relies on Phase 6 Plan 06-05 wiring `forceStale={true}`) |
| `tournament-leaderboard` | Step 4 | visible on `/tournament` |
| `tournament-row-*` | Step 4 | count >= 6 (fixture has 7 rows) |
| `tournament-selector` | Step 4 | visible AND `inner_text` contains `'smoke-tape-fixture'` |
| `tournament-filter-status` | Step 4 | visible |
| `tournament-refresh` | Step 4 | visible |
| `tournament-footer` | Step 4 | visible AND `inner_text` mentions `'exported'` (case-insensitive) |
| `contaminated-warning` | Step 4 | count == 0 (every fixture row has `train_window_includes_contaminated=false`) |
| `significance-badge-pass` | Step 4 (W-3 Path A) | count >= 1 (SOL/GRU is ensemble member AND SOL win_gate_passed=true) |
| `significance-badge-none` | Step 4 (W-3 Path A) | count >= 5 (other 5 success rows render em-dash; failed row also renders em-dash) |
| `statusbar-mode` | Step 5 | `inner_text` contains `'PAPER'` |
| `statusbar-kill-switch` | Step 5 | `inner_text` contains `'ARMED'` |
| `statusbar-ml` | Step 5 | `inner_text` contains `'OFF'` |
| `statusbar-emergency-stop` | Step 5 | `inner_text` contains `'INACTIVE'` |
| `statusbar-trading-state` | Step 5 | `inner_text.lower()` contains `'idle'` OR `'live'` (NOT `'halted'`) |

### Hard data_testid gate (B-1 fix) — NO escape hatch

Runs **before** any navigation:

```python
rows_needing_testid = [r for r in tile_audit["tiles"] if r["verdict"] != "REMOVED"]
missing = [r for r in rows_needing_testid if not r.get("data_testid")]
assert not missing, (
    f"audit-driven smoke contract broken: {len(missing)} non-REMOVED "
    f"tile(s) missing data_testid: {[r['tile'] for r in missing]}. "
    "Plan 03 must wire data-testid on every production tile."
)
```

No `skip with a clear message` branch; no `may not have one` fallback. If Plan 03 forgot a row, the smoke fails at construction time, NOT silently. (Acceptance grep `grep -nE 'skip with a clear message|may not have one' tests/integration/test_dashboard_smoke.py` returns 0 matches.)

### BL-1 page-aware navigation

Three audit rows are PAGE-LEVEL composites that live on their own routes (NOT on `/`):

| Tile | Route | Source |
|------|-------|--------|
| `Phase1Dashboard` | `/phase1` | `PAGE_LEVEL_ROUTE_OVERRIDE` |
| `Phase3Dashboard` | `/phase3` | `PAGE_LEVEL_ROUTE_OVERRIDE` |
| `Portfolio` (page-level, verdict=LABELED_STALE) | `/portfolio` | `PAGE_LEVEL_ROUTE_OVERRIDE` |

Component-level tiles fall back to `PAGE_ROUTES` keyed by the audit `page` field (`Performance`/`Portfolio`/`Phase1` -> `/`; `Phase3` -> `/phase3`; `Tournament` -> `/tournament`). `page.goto` runs at the top of every loop iteration; there is no mid-loop hard-coded Tournament navigation.

## Gateway-origin choice

The smoke targets `http://localhost:8000` (the api-gateway) — NOT `http://localhost:3000` (the vite dev origin). This exercises the same ingress path the production frontend traverses. Acceptance grep `grep -nE 'http://localhost:3000' tests/integration/test_dashboard_smoke.py` returns 0 matches.

## Tile audit current state (Plan 03 contract)

| Total tiles | FIXED | LABELED_STALE | REMOVED | Missing data_testid |
|-------------|-------|----------------|---------|---------------------|
| 16          | 11    | 5              | 0       | 0                   |

Pages covered: `Performance`, `Portfolio`, `Phase1`, `Phase3`, `Tournament`. All 5 `LABELED_STALE` `component_file` references already contain `forceStale` (Phase 6 Plan 06-05 precondition holds — verified at smoke-construction time).

## Verification (this plan)

| Check | Result |
|-------|--------|
| `python3 -c "import json; d = json.load(open('tests/fixtures/tournament/smoke-fixture.json')); assert len(d['rows']) == 7"` | passes |
| `python3 -c "import json; e = json.load(open('tests/fixtures/tournament/smoke-fixture.ensemble.json')); assert e['ensembles'][0]['symbol']=='SOL'"` | passes |
| `python3 -c "import json; s = json.load(open('tests/fixtures/tournament/smoke-fixture.significance.json')); assert s['per_symbol']['SOL']['win_gate_passed'] is True"` | passes |
| `grep -nE 'def tournament_snapshot_seeded' tests/integration/conftest.py | wc -l` == 1 | passes |
| `python3 -c "import ast; ast.parse(open('tests/integration/test_dashboard_smoke.py').read())"` | passes |
| `grep -nE 'skip with a clear message|may not have one' tests/integration/test_dashboard_smoke.py` returns 0 matches | passes |
| `forceStale` present in all 5 LABELED_STALE `component_file` paths | passes |
| All 24 acceptance grep checks in Plan 05 Task 2 | passes (test fn=1, :8000=2, :3000=0, B-1 gate=3, audit json=4, usefixtures=1, bootstrap_stack=2, tournament_snapshot_seeded=1, tournament-leaderboard=1, tournament-selector=2, tournament-refresh=1, tournament-footer=2, contaminated-warning=2, sig-pass=2, sig-none=2, "PAPER"=1, "ARMED"=1, "OFF"=1, "INACTIVE"=1, D-17 cells=5, page-level override=6, page.goto:8000=4) |

Functional execution (running the smoke against a healthy stack) is deferred to Plan 06 — pytest-playwright is not yet installed in this worktree, and the project rule forbids declaring "working end-to-end" without live evidence. Plan 06 owns the CI install + first green run.

## Deviations from Plan

None — plan executed as written.

## Deferred Issues

1. **pytest-playwright async-fixture compatibility.** The `tape_reset` fixture is `async def`; the `page` fixture from pytest-playwright is sync. Running a sync test that depends on `tape_reset` via `usefixtures` requires `pytest-asyncio` `mode = auto` (or an explicit anyio plugin). Plan 06 installs pytest-playwright; if the first green run fails on this, Plan 06's executor must either:
   - flip pytest-asyncio mode to `auto` (already the case if `pytest.ini` / `pyproject.toml` set `asyncio_mode = "auto"`), OR
   - replace `tape_reset` in the `usefixtures` list with a sync wrapper that drives `tape_reset` via `asyncio.run` at the top of the test body.

   This is NOT a Plan 05 fix; flagging here so Plan 06 picks it up.

2. **Phase 4 sidecar schema simplification.** The sidecars committed here follow the simpler schema in the plan's `<interfaces>` block (no `schema_version`, `git_sha`, `created_at`, `aggregation`, `baseline` top-level fields the production `write_ensemble()` / `write_significance()` writers emit). The frontend only reads `ensembles[].members[].run_id` and `per_symbol[sym].win_gate_passed`, so both schemas satisfy the UI contract. If a future plan demands schema parity with production writers, regenerate the sidecars via the writers and re-commit.

## Self-Check

Verified files exist:

- `tests/fixtures/tournament/smoke-fixture.json` -> FOUND
- `tests/fixtures/tournament/smoke-fixture.ensemble.json` -> FOUND
- `tests/fixtures/tournament/smoke-fixture.significance.json` -> FOUND
- `tests/integration/test_dashboard_smoke.py` -> FOUND
- `tests/integration/conftest.py` -> MODIFIED (tournament_snapshot_seeded present)

Verified commits exist (`git log --oneline`):

- `13c3f4a test(07-05): add tournament smoke fixture trio and snapshot seeder` -> FOUND
- `310a315 test(07-05): add audit-driven Playwright dashboard smoke` -> FOUND

## Self-Check: PASSED
