---
phase: 10-path-to-live-dashboard
reviewed: 2026-05-17T22:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - .planning/state/carry_ins.json
  - services/api-gateway/app/routes/__init__.py
  - services/api-gateway/app/routes/preflight_carry_ins.py
  - services/api-gateway/app/main.py
  - docker-compose.unified.yml
  - frontend/src/hooks/useLiveReadiness.js
  - frontend/src/hooks/useCarryIns.js
  - frontend/src/components/PathToLiveTile.jsx
  - frontend/src/components/Dashboard.jsx
  - tests/e2e/conftest.py
  - tests/e2e/fixtures/test-live-trading.override.yml
  - tests/e2e/test_path_to_live_smoke.py
  - tests/integration/test_dashlive_grep_gates.py
  - .github/workflows/dashboard-smoke.yml
findings:
  critical: 1
  warning: 2
  info: 4
  total: 7
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-17T22:00:00Z
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 10 ships the Path-to-LIVE Dashboard tile (backend carry-ins endpoint, React tile,
and verification surface). The backend slice (`preflight_carry_ins.py`) and the frontend
slice (`PathToLiveTile.jsx`, hooks, Dashboard wiring) are correctly implemented. The
atomic write pattern, WSL bind-mount, and workflow injection surface are clean.

One blocker was found in the test fixtures (Wave 2, Plan 03): the `leaderboard_dsr_seeded`
fixture's Step 3 — which must flip `ENABLE_ML_PREDICTIONS=true` on the running
trading-engine container — uses two subprocess calls that silently fail due to incorrect
CLI usage. The first spawns a transient one-off container that immediately exits. The
second passes `-e VAR=val` to `docker compose up`, which does not accept that flag.
Neither returncode is checked. As a result, trading-engine keeps running with
`ENABLE_ML_PREDICTIONS=false`, the DSR check short-circuits to UNKNOWN, and D-10-18
assertions #6 (DSR row PASS) and #7 (window reaches READY) are unreachable in CI.

Two warnings cover: the same fixture's setup subprocess calls lacking timeouts, and the
`all_preflight_checks_passing` fixture using `check=True` without capturing output on
failure.

---

## Critical Issues

### CR-01: `leaderboard_dsr_seeded` Step 3 silently fails to inject `ENABLE_ML_PREDICTIONS=true` — D-10-18 #6 and #7 are unreachable

**File:** `tests/e2e/conftest.py:506-541`

**Issue:** The fixture must restart trading-engine with `ENABLE_ML_PREDICTIONS=true` so
the DSR check reads the seeded leaderboard row instead of short-circuiting to UNKNOWN.
Two subprocess calls attempt this, both are broken:

1. **Lines 506-516 — `compose run --rm` spawns a one-off container:** `-e` is valid for
   `docker compose run`, but `run --rm --no-deps trading-engine true` starts a fresh
   container that runs `true` and immediately exits. The *long-running* `trading-engine`
   service is untouched. Its env is unchanged.

2. **Lines 522-541 — `compose up -e VAR=val` is invalid CLI:** `docker compose up` has no
   `-e`/`--env` flag (verified against installed compose v2). The call is rejected by
   compose and the actual `up --force-recreate` step never executes.

Both calls use `capture_output=True`; neither returncode is checked after execution.
Failures are invisible. The health-poll that follows (lines 543-555) succeeds because
trading-engine was *already running* under the base compose (ENABLE_ML_PREDICTIONS=false).
The `healthy` guard passes and the fixture yields — silently broken.

Consequence: when D-10-18 #6 (`test_dsr_row_schema_passes_after_seed`) runs, the
preflight DSR check sees `ENABLE_ML_PREDICTIONS=false`, short-circuits to UNKNOWN,
and the assertion `dsr_check.get("status") == "PASS"` fails. When D-10-18 #7
(`test_24h_window_reaches_ready_with_fast_forward`) runs, the all_pass condition is never
met, `first_all_pass_at` is never set, and `overall` stays `DO_NOT_FLIP`. Both CI
assertions fail.

**Fix:** Add `ENABLE_ML_PREDICTIONS: 'true'` to the override file, drop both broken
subprocess calls, and rely on the same override-file `force-recreate` pattern that
`all_preflight_checks_passing` correctly uses:

```yaml
# tests/e2e/fixtures/test-live-trading.override.yml
services:
  trading-engine:
    environment:
      - PAPER_TRADING_MODE=false
      - TRADING_MODE=LIVE
      - LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY
      - MAX_POSITION_RISK_PCT=2
      - ENABLE_ML_PREDICTIONS=true   # add this line
```

Then in `leaderboard_dsr_seeded`, replace all of lines 500-541 with:

```python
# Step 3: Force-recreate trading-engine with LIVE-mode + ML enabled
ml_override_file = (
    REPO_ROOT / "tests" / "e2e" / "fixtures" / "test-live-trading.override.yml"
)
recreate_result = subprocess.run(
    [
        "docker", "compose",
        "-f", str(REPO_ROOT / "docker-compose.unified.yml"),
        "-f", str(ml_override_file),
        "up", "-d", "--force-recreate", "--no-deps", "trading-engine",
    ],
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
    timeout=120,
)
if recreate_result.returncode != 0:
    pytest.fail(
        f"leaderboard_dsr_seeded: trading-engine force-recreate failed "
        f"(rc={recreate_result.returncode}): {recreate_result.stderr}"
    )
```

Note: adding `ENABLE_ML_PREDICTIONS=true` to the override file also makes the override
self-consistent for D-10-18 #7 (`all_preflight_checks_passing` already applies the same
file); no separate ML flag injection is needed.

---

## Warnings

### WR-01: Setup subprocess calls in `leaderboard_dsr_seeded` have no `timeout=` — CI budget exhaustible on hang

**File:** `tests/e2e/conftest.py:469,483,506,522`

**Issue:** The four `subprocess.run` calls in the setup path (lines 469, 483, 506, 522)
have no `timeout=` argument. A hung `docker compose` or `sqlite3` call blocks indefinitely,
consuming the workflow's entire 30-minute budget silently. The teardown call at line 566
correctly passes `timeout=120`; the setup calls should match.

**Fix:**
```python
seed_result = subprocess.run(
    EXEC_CMD + ["sqlite3", "/data/tournament.db", seed_sql],
    cwd=REPO_ROOT, capture_output=True, text=True,
    timeout=60,   # add this
)
# Apply timeout=60 to marker_result (line 483) and recreate_result (after CR-01 fix).
```

### WR-02: `all_preflight_checks_passing` uses `check=True` with no captured output — failure message is opaque

**File:** `tests/e2e/conftest.py:611-627`

**Issue:** The `subprocess.run(..., check=True, cwd=REPO_ROOT)` call on lines 611-627 has
no `capture_output=True`. When compose fails (image pull error, port conflict, etc.) the
call raises `subprocess.CalledProcessError` with no stdout/stderr captured, so the test
error message contains no compose output. The teardown call at lines 652-665 correctly
uses `capture_output=True` without `check=True`.

**Fix:** Switch to the same pattern as teardown — capture output, check returncode
manually, and report compose stderr:

```python
result = subprocess.run(
    [
        "docker", "compose",
        "-f", str(REPO_ROOT / "docker-compose.unified.yml"),
        "-f", OVERRIDE,
        "up", "-d", "--force-recreate", "trading-engine",
    ],
    cwd=REPO_ROOT,
    capture_output=True,
    text=True,
    timeout=120,
)
if result.returncode != 0:
    pytest.fail(
        f"all_preflight_checks_passing: force-recreate failed "
        f"(rc={result.returncode}): {result.stderr}"
    )
```

---

## Info

### IN-01: `test_path_to_live_smoke.py:248` docstring misstates where `PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1` is configured

**File:** `tests/e2e/test_path_to_live_smoke.py:248`

**Issue:** The test docstring says `"PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1
(compose default + CI override)"`. The compose default is 86400 (see
`docker-compose.unified.yml:305`: `${PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS:-86400}`).
Only CI (and the bootstrap boot step) sets it to 1. A developer running the smoke locally
against a stack booted without the override will see the test fail after the 2s wait
because `required_seconds=86400`, not because the code is broken.

**Fix:** Correct the docstring:
```python
# With PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS=1 (CI override set by
# dashboard-smoke.yml Boot step; compose default is 86400 — local runs must
# set this manually or boot with the CI env block):
```

### IN-02: `_atomic_write_json` does not fsync the parent directory after `os.replace`

**File:** `services/api-gateway/app/routes/preflight_carry_ins.py:51-78`

**Issue:** The implementation correctly orders flush → fsync → close → os.replace.
However, on some Linux filesystems the directory entry for the new inode is not
guaranteed durable until the parent directory fd is also fsynced. For a state file
written every 5 seconds on a well-configured ext4/xfs host this rarely causes a problem
in practice (the next write will self-heal). Raised as Info given the operational context
(single-process api-gateway, 5s rewrite cadence, short outage tolerance).

**Fix (optional, belt-and-braces):**
```python
    os.replace(tmp_name, path)
    # Fsync the parent dir so the directory entry is also durable.
    parent_fd = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
```

### IN-03: CI workflow pip installs are unpinned — supply-chain drift risk

**File:** `.github/workflows/dashboard-smoke.yml:47,72`

**Issue:** Two pip install steps use bare (unpinned) package names:
- Line 47: `pip install playwright httpx`
- Line 72: `pip install pytest-playwright`

A new major release of any of these could silently break the smoke. Phase 8/9 CI
workflows (`preflight-live-readiness.yml`, `live-smoke.yml`) follow the same pattern, so
this is a project-wide convention rather than a Phase 10 regression, but worth flagging.

**Fix:** Pin to known-good versions matching the local dev environment, e.g.:
```yaml
pip install "playwright==1.44.0" "httpx==0.27.0" "pytest-playwright==0.5.0"
```

### IN-04: `all_preflight_checks_passing` compose calls omit `--no-deps` — minor isolation gap

**File:** `tests/e2e/conftest.py:611-627,652-665`

**Issue:** The `compose up` calls in both setup (lines 611-627) and teardown (lines
652-665) of `all_preflight_checks_passing` do not pass `--no-deps`. With compose v2,
omitting `--no-deps` from a named-service `up` does NOT cascade-restart already-running
healthy dependency containers — compose v2 only starts stopped deps, it does not restart
running ones. So the harm scenario (postgres/redis/rabbitmq restart mid-smoke) does not
materialize in practice. However, adding `--no-deps` is cleaner: it makes intent explicit,
avoids compose resolving the dependency graph at all, and slightly reduces startup latency.

**Fix:** Add `--no-deps` to both calls:
```python
"up", "-d", "--force-recreate", "--no-deps", "trading-engine",
```

---

_Reviewed: 2026-05-17T22:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
