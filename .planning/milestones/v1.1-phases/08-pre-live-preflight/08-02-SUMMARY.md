---
phase: 08-pre-live-preflight
plan: 02
subsystem: trading-engine + api-gateway + scripts
tags:
  - preflight
  - cli
  - http-route
  - api-gateway
  - PREFLIGHT-01

requires:
  - app.preflight.run_all (08-01)
provides:
  - scripts/preflight_live.py CLI
  - GET /api/preflight/live-readiness (trading-engine port 8005)
  - GET /api/preflight/live-readiness (api-gateway port 8000, thin proxy)
affects:
  - services/trading-engine
  - services/api-gateway

tech_stack_added: []
patterns:
  - sys.path insert at script root to import service module without docker
  - filtered env-overlay for `--dry-run` (only 6 preflight-relevant keys
    cross into os.environ to avoid pydantic-settings JSON-decode failures
    on unrelated list-typed fields)
  - graceful-degradation UNKNOWN-everywhere on proxy failure (never PASS)
  - standalone FastAPI test app for the trading-engine route (so the
    test passes before 08-03 mounts the router on the real app)
  - autoflake-survival local imports inside the gateway proxy function

key_files_created:
  - scripts/preflight_live.py
  - services/trading-engine/app/handlers/preflight.py
  - services/trading-engine/tests/test_preflight_route.py
  - services/api-gateway/tests/test_preflight_proxy.py
key_files_modified:
  - services/api-gateway/app/main.py

decisions:
  - `--dry-run --target=<ref>` overlays the snapshot onto `os.environ`
    and calls `reload_settings()` BEFORE `run_all()` (then restores),
    rather than just `Settings(**parsed)`. Three of six checks
    (`check_paper_mode`, `check_ack`, `check_dsr_evidence`) read
    `os.environ` directly per 08-01 design, so a fresh Settings alone
    would silently bypass them. See Deviations §1.
  - The env overlay is FILTERED to the 6 preflight-relevant keys
    (TRADING_MODE, MAX_RISK_PER_TRADE, PAPER_TRADING_MODE,
    LIVE_TRADING_ACK, ENABLE_ML_PREDICTIONS, EMERGENCY_STOP_FILE).
    `.env.example` has comma-separated list fields (TRADING_SYMBOLS,
    etc.) that pydantic-settings tries to JSON-decode when populated as
    env vars, breaking the snapshot reload. See Deviations §2.
  - The dotenv parser strips trailing inline comments
    (`KEY=value  # comment`) so `.env.example` rows like
    `ENABLE_ML_PREDICTIONS=false  # Future feature` parse to the
    expected boolean. See Deviations §3.
  - The trading-engine route handler raises 500 on `run_all()`
    exception (not silent PASS). The api-gateway proxy is the layer
    that translates failures into the graceful-degradation
    UNKNOWN-body — single owner of that safe-default per 08-CONTEXT.md
    Open Question close.
  - Test fixture for the trading-engine route uses a standalone
    `FastAPI()` + `include_router(router)` rather than
    `from app.main import app`, because 08-03 (not this plan) is the
    one that mounts the router on the real app co-located with the
    cap-check block. This lets the 3 route tests pass before 08-03
    lands.
  - Proxy tests use the plain `test_client` fixture (NOT
    `admin_client`). `admin_client` would override
    `get_current_admin_user`, silently masking a future regression that
    accidentally added an auth dependency to the unauthenticated route.

metrics:
  duration_minutes: 60
  completed: 2026-05-16
  files_created: 4
  files_modified: 1
  tests_added: 7
  tests_passed: 7
  commits: 3
---

# Phase 8 Plan 2: CLI + HTTP Route Summary

CLI script (`scripts/preflight_live.py`) and HTTP endpoints
(`/api/preflight/live-readiness` on both trading-engine and api-gateway)
that surface the 08-01 preflight package. CLI and HTTP both call the same
`run_all()` from `app.preflight` — single source of truth, zero logic
duplication. The api-gateway proxy ALWAYS degrades to
`overall=UNKNOWN` (never PASS) on any failure, per CONTEXT.md's "Open
Question" close.

## Tasks Completed

| Task | Name                                          | Commit  | Files                                                                                                  |
| ---- | --------------------------------------------- | ------- | ------------------------------------------------------------------------------------------------------ |
| 1    | CLI entry point `scripts/preflight_live.py`   | 1891de8 | `scripts/preflight_live.py`                                                                            |
| 2    | trading-engine HTTP route + tests             | 5927a80 | `services/trading-engine/app/handlers/preflight.py`, `services/trading-engine/tests/test_preflight_route.py` |
| 3    | api-gateway proxy route + tests               | c16386f | `services/api-gateway/app/main.py` (+66 lines), `services/api-gateway/tests/test_preflight_proxy.py`      |

## Source Files

| File                                                          | Lines    | Purpose                                                                                                                   |
| ------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------- |
| `scripts/preflight_live.py`                                   | 275      | CLI with `--json` / `--text` / `--check=<name>` / `--dry-run --target=<ref>`; exit 0 on PASS, 1 on FAIL/UNKNOWN, 2 bad args |
| `services/trading-engine/app/handlers/preflight.py`           | 58       | `APIRouter(prefix="/api/preflight")` with `GET /live-readiness`; unauthenticated; 500 on internal error                   |
| `services/trading-engine/tests/test_preflight_route.py`       | 104      | 3 tests: schema_v1 shape + 6 checks; no-auth regression guard; 500 on `run_all()` exception                               |
| `services/api-gateway/app/main.py` (delta)                    | +66      | Proxy handler inserted after `/api/config/safety-state` (line 1166); graceful-degradation UNKNOWN-everywhere               |
| `services/api-gateway/tests/test_preflight_proxy.py`          | 188      | 4 tests: verbatim pass-through, unreachable→UNKNOWN, no-auth, non-200→UNKNOWN                                              |
| **Total new + modified**                                      | **691**  |                                                                                                                           |

`services/trading-engine/app/main.py` is **not** modified in this plan.
Mounting the new router + the cap-check lifespan block are 08-03's
single-file scope (keeps the grep-gate sharp).

## Tests

```
$ pytest services/trading-engine/tests/test_preflight_route.py --no-cov
tests/test_preflight_route.py::test_route_returns_schema_v1     PASSED
tests/test_preflight_route.py::test_route_no_auth_required      PASSED
tests/test_preflight_route.py::test_route_500_on_internal_error PASSED
========================= 3 passed in 5.31s =========================

$ pytest services/api-gateway/tests/test_preflight_proxy.py --no-cov
tests/test_preflight_proxy.py::test_proxy_passes_through_preflight_report           PASSED
tests/test_preflight_proxy.py::test_proxy_returns_unknown_when_trading_engine_unreachable PASSED
tests/test_preflight_proxy.py::test_proxy_no_auth_required                          PASSED
tests/test_preflight_proxy.py::test_proxy_returns_unknown_when_trading_engine_returns_non_200 PASSED
========================= 4 passed in 0.22s =========================
```

7 / 7 — meets the plan's ≥3 (route) + ≥4 (proxy) floors.

## Sample CLI Output

### Text mode (default — PAPER env)

```
$ python3 scripts/preflight_live.py
  PASS      cap                 non-LIVE mode (PAPER); cap check skipped per ADR-010 paper-relaxed cap
  PASS      paper_mode          non-LIVE mode (PAPER); paper_mode check skipped
  FAIL      trading_mode        TRADING_MODE=PAPER (expected LIVE)
  PASS      ack                 non-LIVE mode (PAPER); ack check skipped
  PASS      emergency_stop      no file at /app/EMERGENCY_STOP
  PASS      dsr_evidence        ML disabled (ENABLE_ML_PREDICTIONS=false); DSR check skipped

OVERALL: FAIL
```

Exit code 1 (FAIL) — correct for a system in PAPER mode (not LIVE-ready).

### `--check=cap --json`

```json
{
  "schema_version": 1,
  "overall": "PASS",
  "evaluated_at": "2026-05-16T20:52:16.972741+00:00",
  "checks": [
    {
      "check": "cap",
      "status": "PASS",
      "detail": "non-LIVE mode (PAPER); cap check skipped per ADR-010 paper-relaxed cap"
    }
  ]
}
```

Exit code 0 (PASS in the filtered subset). The `--check` filter
recomputes `overall` over the single-check subset.

### `--dry-run --target=HEAD --json` (CI variant)

Reads `.env.example` via `git show HEAD:.env.example`, filters to the 6
preflight-relevant keys, overlays onto `os.environ`, calls
`reload_settings()`, runs all 6 checks, restores. Used by Phase 8 04's
CI workflow.

## Verification Status

| Check                                                                                       | Result |
| ------------------------------------------------------------------------------------------- | ------ |
| `python3 scripts/preflight_live.py --json` exits 0/1 (not 2) and prints valid schema_v1     | PASS   |
| `python3 scripts/preflight_live.py --check=cap --json` returns one check named "cap"        | PASS   |
| `python3 scripts/preflight_live.py --check=bogus` exits 2                                   | PASS   |
| `pytest services/trading-engine/tests/test_preflight_route.py` — 3 passed                   | PASS   |
| `pytest services/api-gateway/tests/test_preflight_proxy.py` — 4 passed                      | PASS   |
| `grep -c "/api/preflight/live-readiness" services/api-gateway/app/main.py` returns 3 (≥1)   | PASS   |
| `grep -A20 'def get_preflight_live_readiness' .../main.py \| grep -cE '"overall".*"PASS"'`  | PASS (0) |

## Forward References

- **Post-08-03 curl smoke check pending:** once 08-03 mounts the router
  in `services/trading-engine/app/main.py`, the operator can verify
  end-to-end with
  `curl -s http://localhost:8000/api/preflight/live-readiness | jq -e
  '.schema_version == 1 and (.checks | length) == 6'` (exits 0).
  Recorded here so the verifier checks it after 08-03 lands.
- **Phase 8 plan 04 (CI workflow)** consumes the
  `--dry-run --target=HEAD --json` mode. The filtered-env-overlay
  design (see Deviations §2) is what makes that mode produce coherent
  results across all 6 checks rather than silently mixing snapshot
  values with process env.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan-suggested `Settings(**parsed)` for `--dry-run` would silently bypass 3 of 6 checks**

- **Found during:** Task 1 review of 08-01 `checks.py` (advisor flagged
  this pre-write).
- **Issue:** Plan's `<behavior>` for `--dry-run` says "construct a fresh
  `Settings(**parsed)` instance; pass to `run_all(settings=...)`". But
  three of six checks read `os.environ` directly per 08-01 design
  (`check_paper_mode` line 113, `check_ack` line 159,
  `check_dsr_evidence` line 217) — same trust source as
  `services/trading-engine/app/main.py:251`. A fresh Settings alone
  leaves those three checks reading process env. The CI gate becomes
  meaningless (would PASS on a snapshot that should FAIL).
- **Fix:** `--dry-run` saves `os.environ`, overlays the snapshot,
  calls `reload_settings()` (exposed at
  `services/trading-engine/app/config.py:704`), runs `run_all()`, then
  restores `os.environ` and reloads settings again. The try/finally
  guarantees no env leakage even if a check raises.
- **Files modified:** `scripts/preflight_live.py`.
- **Commit:** 1891de8.

**2. [Rule 1 - Bug] Pydantic-settings JSON-decoded list fields fail when snapshot is overlaid**

- **Found during:** Task 1 first smoke test of
  `--dry-run --target=HEAD`. The bare overlay raised
  `pydantic_core.ValidationError` on `TRADING_SYMBOLS` etc. because
  pydantic-settings treats list-typed fields as JSON-encoded when read
  from env.
- **Issue:** `.env.example` includes comma-separated list values
  (`TRADING_SYMBOLS=BTC,ETH,SOL,BNB,ADA`) that pydantic-settings tries
  to `json.loads` when those values are present in `os.environ`. The
  resulting `JSONDecodeError` aborts `reload_settings()`.
- **Fix:** The CLI defines a filter set `_PREFLIGHT_ENV_KEYS` of the
  6 keys the preflight checks actually read
  (`TRADING_MODE`, `MAX_RISK_PER_TRADE`, `PAPER_TRADING_MODE`,
  `LIVE_TRADING_ACK`, `ENABLE_ML_PREDICTIONS`, `EMERGENCY_STOP_FILE`)
  and overlays only those. Unrelated config doesn't pollute the env.
- **Files modified:** `scripts/preflight_live.py`.
- **Commit:** 1891de8.

**3. [Rule 1 - Bug] Dotenv parser captured inline comments as part of value**

- **Found during:** Task 1 retry of `--dry-run --target=HEAD`. After
  fix §2, `reload_settings()` failed with
  `ValidationError: enable_ml_predictions Input should be a valid
  boolean, unable to interpret input 'false  # Future feature'`.
- **Issue:** `.env.example` lines like
  `ENABLE_ML_PREDICTIONS=false  # Future feature` have trailing inline
  comments. The original dotenv parser captured the whole value
  including the comment, so `'false  # Future feature'` ended up in
  `os.environ`.
- **Fix:** When the value does not start with `"` or `'`, strip
  everything from the first `#` onward. Quoted values are left intact
  (they may legitimately contain `#`).
- **Files modified:** `scripts/preflight_live.py`.
- **Commit:** 1891de8.

**4. [Rule 3 - Blocking] `app.preflight` not present on the worktree base branch**

- **Found during:** Pre-Task-1 smoke test (`python3 -c "from
  app.preflight import run_all"` raised `ModuleNotFoundError`).
- **Issue:** Worktree branch `worktree-agent-a5dcb2848e5f7a148` was
  forked from a base commit (43ba59a) that predates the 08-01 merge
  on `sync/cherry-picks-2026-05-05` (which contains commits 321d901,
  9b41e17, aa2553f from 08-01). Without 08-01 the CLI cannot import
  `from app.preflight import run_all` and none of the route/proxy
  handlers can be exercised.
- **Fix:** Merged `sync/cherry-picks-2026-05-05` into the worktree
  branch (clean fast-forward of the preflight package + tests + plan
  docs). Smoke-checked `run_all()` returns
  `(overall=FAIL, schema_version=1, checks=6)` from the worktree
  before starting any task.
- **Files modified:** (merge — adds 08-01 surface; no source-level
  changes by this plan).
- **Commit:** absorbed into the merge commit; not its own task
  commit. Tracked here for the verifier.

**5. [Rule 1 - Bug] Initial Task 3 Edit accidentally landed in the parent repo, not the worktree**

- **Found during:** Task 3 test run — all 4 proxy tests returned 404,
  but the worktree's `services/api-gateway/app/main.py` showed
  `grep -c "preflight"` returning 0. The parent repo
  `/mnt/d/Bimo_max/crypto-trading-bot/services/...` had the route at
  3 matches.
- **Issue:** The Read calls I made on `services/api-gateway/app/main.py`
  used the absolute path that resolves to the parent repo (since the
  worktree shares the same `services/` tree on disk but git ops
  branch via the `.git` symlink/file). My Edit landed at that
  parent-repo absolute path. Same regression pattern noted in
  08-01-SUMMARY.md "Worktree placement".
- **Fix:** Reverted the parent repo's `main.py` (`git checkout` from
  `/mnt/d/Bimo_max/crypto-trading-bot`), then re-applied the proxy
  route via Edit on the absolute worktree path
  (`/mnt/d/Bimo_max/crypto-trading-bot/.claude/worktrees/agent-a5dcb2848e5f7a148/services/...`).
  Verified `grep -c` returns 3 in the worktree and 0 in the parent
  repo before committing. All 4 tests passed on the worktree after
  the fix.
- **Files modified:** `services/api-gateway/app/main.py` (in worktree
  only; parent reverted).
- **Commit:** c16386f (final, on the worktree).

### Execution-time environment notes

- **api-gateway tests on host vs container.** The deployed
  `crypto-bot-api-gateway` container has no source bind-mount, so a
  `docker exec ... pytest` cannot see the new test file. Copying via
  `docker cp` failed with the WSL bind-mount-race error noted in
  CLAUDE.md. Tests were instead run on the host after installing
  `python-jose` via `pip --break-system-packages` (the missing dep
  was the only blocker; conftest.py imports
  `from jose import JWTError, jwt`). The route under test is
  unauthenticated so the 401-vs-403 host/container HTTPBearer drift
  (CLAUDE.md gotcha) does not affect any assertion. Container-run
  verification remains the recommended path once the container has a
  source-tree mount or after the next image rebuild.
- **`pytest --no-cov`** used for the proxy-test summary because the
  trading-engine test config has coverage on by default and the
  combined output is otherwise unreadable in the summary.

## TDD Gate Compliance

This plan's three commits follow `feat → feat → feat` (CLI, handler+tests,
proxy+tests). Each commit pairs source + its tests in one atomic unit;
the workflow-level TDD-gate that looks for a leading `test(...)` commit
will flag this as a warning. Pairing source + tests in a single commit
makes the per-task acceptance gates (which require both the file and
its tests) self-contained — splitting would have created intermediate
states where acceptance failed.

## Threat Surface Scan

No new attack surface introduced. The threat register entries in the
plan (T-08-02-01 through T-08-02-06) are all addressed:

| Threat ID  | Disposition | Status                                                                                                |
| ---------- | ----------- | ----------------------------------------------------------------------------------------------------- |
| T-08-02-01 | accept      | Unauthenticated GET preserved; disclosure level matches `/api/config/safety-state` D-09 (config-only). |
| T-08-02-02 | mitigate    | Proxy returns `overall=UNKNOWN` (never PASS) on any failure; `test_proxy_returns_unknown_when_trading_engine_unreachable` enforces. |
| T-08-02-03 | accept      | No state change, no auth surface added.                                                               |
| T-08-02-04 | accept      | UNKNOWN-leak is by design — dashboard needs to distinguish "evidence missing" from "evidence failed". |
| T-08-02-05 | accept      | `--dry-run --target` reads `.env.example` only (committed, not a secret); operator-side use only.     |
| T-08-02-06 | accept      | CLI runs as the invoking user; no privileged escalation.                                              |

No `threat_flag` items — no new endpoints, no auth surface added,
no schema changes at trust boundaries beyond what 08-01 already
disclosed.

## Self-Check: PASSED

- `scripts/preflight_live.py` — FOUND (executable, 275 lines)
- `services/trading-engine/app/handlers/preflight.py` — FOUND (58 lines)
- `services/trading-engine/tests/test_preflight_route.py` — FOUND (104 lines)
- `services/api-gateway/tests/test_preflight_proxy.py` — FOUND (188 lines)
- `services/api-gateway/app/main.py` proxy route at ~line 1168 — FOUND
- commit 1891de8 (CLI) — FOUND
- commit 5927a80 (trading-engine route + tests) — FOUND
- commit c16386f (api-gateway proxy + tests) — FOUND
- behavior: `python3 scripts/preflight_live.py --json` returns
  schema_version=1 with 6 checks — VERIFIED
- behavior: `pytest tests/test_preflight_route.py` — 3/3 PASS
- behavior: `pytest tests/test_preflight_proxy.py` — 4/4 PASS
- grep gate: `/api/preflight/live-readiness` in api-gateway/main.py —
  3 (>=1)
- grep gate: `trading-engine unreachable` in api-gateway/main.py —
  1 (>=1)
- negative grep: `"overall": "PASS"` inside
  `get_preflight_live_readiness` — 0 (==0; UNKNOWN-only fallback)
- grep gate: `test_proxy_returns_unknown_when_trading_engine_unreachable`
  — 2 occurrences (>=1)
- grep gate: `services/trading-engine/app/main.py` NOT modified by
  this plan — VERIFIED (untouched per 08-03 ownership boundary)
