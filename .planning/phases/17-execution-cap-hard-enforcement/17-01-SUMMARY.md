---
phase: 17-execution-cap-hard-enforcement
plan: 01
subsystem: trading-engine
tags:
  - trading-engine
  - emergency-stop
  - auth
  - route-deletion
  - tdd
  - security
  - cwe-306
dependency_graph:
  requires: []
  provides:
    - "TE-CAP-02: trading-engine /api/v1/orchestrator/emergency-stop route DELETED"
    - "api-gateway /api/portfolio/emergency-stop is now sole admin-guarded kill-switch entry"
    - "Auth-note comment at handlers/orchestration.py rewritten (D-12)"
  affects:
    - services/trading-engine/app/handlers/orchestration.py
    - services/trading-engine/tests/
tech_stack:
  added: []
  patterns:
    - "TDD RED→GREEN cycle on route deletion"
    - "Negative 404 test via TestClient on freshly-mounted router (mirrors test_force_signal.py:42-52)"
key_files:
  created:
    - services/trading-engine/tests/test_orchestration_emergency_stop_removed.py
  modified:
    - services/trading-engine/app/handlers/orchestration.py
decisions:
  - "D-01 honored: route deleted outright, no auth middleware added to trading-engine"
  - "D-02 honored: clean deletion, no 410-Gone shim, no 403 stub"
  - "D-04 honored: api-gateway remains sole writer to safety/EMERGENCY_STOP"
  - "D-05 honored: ONE new negative test + existing api-gateway positive coverage confirmed green"
  - "D-12 honored: auth-note comment rewritten to name what each remaining admin router actually protects"
  - "D-03 honored: sibling admin_indicator_router and admin_force_signal_router untouched"
requirements:
  - TE-CAP-02
metrics:
  duration_minutes: 7
  completed_date: "2026-05-24"
  tasks_completed: 3
  files_created: 1
  files_modified: 1
  commits: 2
  lines_added: 90
  lines_removed: 37
---

# Phase 17 Plan 01: Trading-Engine Emergency-Stop Route Deletion (TE-CAP-02) Summary

Deleted the unauthenticated `POST /api/v1/orchestrator/emergency-stop` route from the trading-engine (CWE-306 missing-auth-on-critical-function), making the api-gateway admin-guarded route at `services/api-gateway/app/main.py:1747-1804` the sole entry for kill-switch activation. TDD-driven: 404 negative test written first (RED — observed 200 response), then route deleted (GREEN — 404 confirmed).

## Final State of handlers/orchestration.py

**Lines deleted (formerly :591-622):** 32 lines — the entire `@router.post("/emergency-stop")` decorator through the closing `raise HTTPException(status_code=500, detail=str(e))`. The `# =====...STATUS ENDPOINT...# =====` divider that previously sat below remains as the boundary marker before the `/status` route.

**Lines rewritten (formerly :725-727 auth-note comment, now ~10 lines):** Old false claim removed:

```python
# Auth note: trading-engine has no auth middleware; all admin routes are
# protected upstream at the api-gateway. We name the prefix `/admin/...` for
# routing convention, but enforce nothing at this layer.
```

Replaced with (per D-12):

```python
# Auth note: trading-engine has no auth middleware. The previously-duplicated
# `POST /api/v1/orchestrator/emergency-stop` route was DELETED in Phase 17
# (TE-CAP-02, 2026-05-24) — the api-gateway admin-guarded route at
# services/api-gateway/app/main.py:1747-1804 (Depends(get_current_admin_user))
# is now the sole entry for kill-switch activation, and it is the sole writer
# of the bind-mounted safety/EMERGENCY_STOP file (D-04). The `admin_indicator_router`
# below uses the `/admin/...` prefix for routing convention and is protected by
# its own rolling-confidence gate (see IndicatorRegistry below) — NOT by upstream
# auth. Sibling `admin_force_signal_router` (at :839) is protected by a
# `TRADING_MODE=LIVE` refusal gate. Phase 17 D-03 deliberately left these as-is.
```

**Imports retained (no orphans):**

| Symbol | Occurrences after deletion | Note |
|---|---|---|
| `get_risk_coordinator` | 3 | still used by `/risk/utilization` and `/status` |
| `get_strategy_orchestrator` | 15 | used by many routes throughout file |
| `HTTPException` | 24 | used by every route |
| `Query` | (in fastapi import) | still used by other Query()-defaulted parameters |

No `# noqa: F401` markers were needed.

## Task Execution & Test Results

### Task 1: RED test (commit `17ed2d3`)

**Action:** Created `services/trading-engine/tests/test_orchestration_emergency_stop_removed.py` with two tests:
- `test_emergency_stop_route_deleted_returns_404`
- `test_emergency_stop_route_deleted_returns_404_with_reason_query`

**Pre-deletion run (RED proof):** Both tests failed exactly as the TDD anchor required:

```
FAILED tests/test_orchestration_emergency_stop_removed.py::test_emergency_stop_route_deleted_returns_404
  AssertionError: Expected 404 after route deletion, got 200:
  {"success":true,"message":"Emergency stop activated","reason":"Manual emergency stop", ...}
  assert 200 == 404
FAILED tests/test_orchestration_emergency_stop_removed.py::test_emergency_stop_route_deleted_returns_404_with_reason_query
  AssertionError: Expected 404 after route deletion (with reason= query param), got 200:
  {"success":true,"message":"Already in emergency stop","reason":"Manual emergency stop", ...}
  assert 200 == 404
============================== 2 failed in 54.62s ==============================
```

The 200 response body confirmed the route still existed and was actively calling `coordinator.emergency_stop()` + `orchestrator.pause_all()`.

**Commit:** `17ed2d3 test(trading-engine): add RED 404 test for emergency-stop route removal (TE-CAP-02)`

### Task 2: GREEN deletion (commit `f2aaa77`)

**Action:** Deleted the 32-line `@router.post("/emergency-stop")` block and rewrote the auth-note comment per D-12.

**All 6 verification gates passed:**

| Gate | Check | Result |
|---|---|---|
| 1 | `grep -c '@router.post("/emergency-stop"' handlers/orchestration.py` | `0` ✓ |
| 2 | `grep -cE '^async def emergency_stop\b' handlers/orchestration.py` | `0` ✓ |
| 3a | `grep -c 'all admin routes are' handlers/orchestration.py` | `0` ✓ (old false claim removed) |
| 3b | `grep -c 'DELETED in Phase 17' handlers/orchestration.py` | `1` ✓ (D-12 new comment present) |
| 4 | Every retained import has ≥2 occurrences | `get_risk_coordinator=3, get_strategy_orchestrator=15, HTTPException=24` ✓ |
| 5 | `pytest tests/test_orchestration_emergency_stop_removed.py` | **2 passed** (RED→GREEN) ✓ |
| 6 | `pytest tests/test_force_signal.py tests/test_handler_endpoints.py` | **28 passed, 1 skipped** (no regression) ✓ |

**Commit:** `f2aaa77 fix(trading-engine): delete unauthenticated emergency-stop route and update auth-note comment (TE-CAP-02)`

### Task 3: In-container api-gateway verification (no commit)

**Step A (api-gateway container):** Confirmed `crypto-bot-api-gateway` is `Up 13 hours (healthy)`.

**Step A.5 (trading-engine rebuild) + Step C (live curl):** **DEFERRED to orchestrator post-merge.** Rationale documented under "Known Caveats" below — the worktree branch's source change is not yet on `main`, and a worktree-spawned `docker compose up --build` would create a parallel docker project alongside the running `crypto-bot-*` stack (different namespace, port conflict on `:8005`). The orchestrator merges the worktree branch into main, then performs the post-merge rebuild + 404 curl proof.

**Step B (in-container api-gateway emergency-stop tests):**

Container does not ship test files in the image. Tests copied in via `docker cp /mnt/d/Bimo_max/crypto-trading-bot/services/api-gateway/tests crypto-bot-api-gateway:/app/tests` then executed in-container:

```
docker exec crypto-bot-api-gateway pytest /app/tests/test_gateway_80_coverage.py -k emergency_stop -v
  tests/test_gateway_80_coverage.py::TestErrorHandling::test_emergency_stop_endpoint PASSED       [ 50%]
  tests/test_gateway_80_coverage.py::TestErrorHandling::test_emergency_stop_file_write_error PASSED [100%]
  =============== 2 passed, 59 deselected, 3944 warnings in 0.13s ================

docker exec crypto-bot-api-gateway pytest /app/tests/test_main.py -k emergency_stop -v
  tests/test_main.py::TestEmergencyStop::test_emergency_stop_creates_file PASSED                 [ 50%]
  tests/test_main.py::TestEmergencyStop::test_emergency_stop_handles_error PASSED                [100%]
  =============== 2 passed, 26 deselected, 1788 warnings in 0.10s ================
```

**Gate 2 verdict:** PASS — 4/4 emergency-stop tests green in-container (using `fastapi 0.109` per the CLAUDE.md gotcha, so the existing 403-asserting positive paths work as authored).

## Verification (end-of-plan checklist from PLAN.md `<verification>`)

| # | Command | Expected | Actual |
|---|---|---|---|
| 1a | `grep -c '@router.post("/emergency-stop"' …orchestration.py` | `0` | `0` ✓ |
| 1b | `grep -c 'DELETED in Phase 17' …orchestration.py` | `1` | `1` ✓ |
| 2 | `pytest tests/test_orchestration_emergency_stop_removed.py -v` | exit 0 | exit 0 (2 passed) ✓ |
| 3 | `pytest tests/test_force_signal.py tests/test_handler_endpoints.py -q` | exit 0 | exit 0 (28 passed, 1 pre-existing skip) ✓ |
| 4 | `docker exec crypto-bot-api-gateway pytest …test_gateway_80_coverage.py -k emergency_stop` | pass | 2 passed ✓ |
| 4 | `docker exec crypto-bot-api-gateway pytest …test_main.py -k emergency_stop` | pass | 2 passed ✓ |
| 5 | `curl -X POST http://localhost:8005/api/v1/orchestrator/emergency-stop` | `404` | **DEFERRED** — currently returns `200` on the unrebuilt container (image predates worktree commit `f2aaa77`); see Known Caveats |

## Deviations from Plan

### Deferred / environmental

**1. [Environmental] Live curl on `:8005` deferred to orchestrator post-merge.** PLAN Task 3 Step A.5 + Step C call for `docker compose ... up -d --build trading-engine` from the worktree, then `curl -X POST http://localhost:8005/api/v1/orchestrator/emergency-stop` to confirm 404. Both deferred because (a) docker compose run from the worktree directory uses a different project namespace (`agent-ab5cae320b99699f2`) from the running `crypto-bot-*` stack, would spawn a parallel container, and would conflict on host port `:8005`; (b) the running `crypto-bot-trading` container is built from `/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine` (main repo), not the worktree, so a same-namespace rebuild requires the worktree branch to first land on `main`. Orchestrator owns this step post-merge.

**2. [Environmental] api-gateway test files copied in via `docker cp` rather than pre-shipped in image.** The deployed `crypto-bot-api-gateway` image does not ship test files; `docker exec crypto-bot-api-gateway pytest services/api-gateway/tests/...` (the literal command from PLAN Task 3 Step B) returns "file or directory not found". Worked around by copying the main-repo tests directory into the running container with `docker cp` before invoking pytest. This is a CI-hygiene concern for the api-gateway image, not a Phase 17 defect — pre-existing. Tests then ran successfully under the container's pinned `fastapi 0.109` runtime, satisfying the D-05 obligation.

### Auto-fixed

None — plan executed exactly as written; no Rule 1/2/3 deviations triggered.

## Auth Gates

None — no authentication interaction during execution.

## Threat-Model Mitigation Status

| Threat ID | Disposition | Resolution |
|---|---|---|
| T-17-01 (CWE-306 unauthenticated emergency-stop on :8005) | **mitigate** | RESOLVED — route deleted in commit `f2aaa77`; FastAPI default 404 handler now returns visible failure. ASVS V4.2.1 satisfied: api-gateway route with `Depends(get_current_admin_user)` is now the only remaining entry. |
| T-17-02 (false documentation claim about admin route protection) | **mitigate** | RESOLVED — auth-note comment rewritten in commit `f2aaa77` to drop the "all admin routes protected upstream" claim and name each remaining admin router's actual protection model. |
| T-17-03 (DoS — silent failure if 404 hit during real emergency) | **accept** | Per D-01: zero non-doc callers exist; operator runbooks point at api-gateway route. 404 is the desired failure mode per CLAUDE.md "no backwards-compat hacks". Residual risk mitigated by the new comment flagging the deletion. |
| T-17-04 (sibling admin routes still on :8005) | **accept** (out of scope per D-03) | UNCHANGED — `admin_indicator_router` (rolling-confidence gate) and `admin_force_signal_router` (`TRADING_MODE=LIVE` refusal gate) preserve their own inline protection models. Deferred to future security phase. |

## Known Stubs

None. The two pre-existing `TODO` markers in `handlers/orchestration.py` (`:727` indicator master switch reference, `:760` indicator master switch lookup) belong to the indicator-gate code path which Phase 17 D-03 deliberately leaves out of scope.

## Known Caveats

- **Live `curl :8005 → 404` proof requires post-merge rebuild.** The currently-running `crypto-bot-trading` container was built before commit `f2aaa77` landed and bind-mounts only `logs/` and `safety/`, not application source. After the orchestrator merges this wave to `main`, the verification step is:
  ```bash
  docker compose -f docker-compose.unified.yml up -d --build trading-engine
  # wait for container to reach (healthy)
  curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8005/api/v1/orchestrator/emergency-stop
  # expected: 404
  ```
- **api-gateway image does not ship test files.** Future hygiene work could add `COPY tests/ /app/tests/` to the api-gateway Dockerfile so `docker exec ... pytest` works without a `docker cp` step.

## Commits

| Task | Commit | Type | Message |
|---|---|---|---|
| 1 (RED) | `17ed2d3` | `test(trading-engine):` | add RED 404 test for emergency-stop route removal (TE-CAP-02) |
| 2 (GREEN) | `f2aaa77` | `fix(trading-engine):` | delete unauthenticated emergency-stop route and update auth-note comment (TE-CAP-02) |
| 3 (verify) | — | — | (verification task; no commit) |

## TDD Gate Compliance

- ✅ RED gate: commit `17ed2d3` is a `test(...)` commit; both tests asserted to fail with `assert 200 == 404` against pre-deletion code (failure evidence captured above).
- ✅ GREEN gate: commit `f2aaa77` is a `fix(...)` commit following the RED commit; both tests now pass.
- (no REFACTOR phase needed — the deletion + comment rewrite is the implementation).

## Self-Check

```
[ -f services/trading-engine/tests/test_orchestration_emergency_stop_removed.py ] → FOUND
[ -f services/trading-engine/app/handlers/orchestration.py ]                      → FOUND
git log --all | grep 17ed2d3                                                      → FOUND
git log --all | grep f2aaa77                                                      → FOUND
grep -c '@router.post("/emergency-stop"' services/trading-engine/app/handlers/orchestration.py → 0
grep -c 'DELETED in Phase 17' services/trading-engine/app/handlers/orchestration.py            → 1
pytest tests/test_orchestration_emergency_stop_removed.py                         → 2 passed
docker exec crypto-bot-api-gateway pytest /app/tests/test_gateway_80_coverage.py -k emergency_stop → 2 passed
docker exec crypto-bot-api-gateway pytest /app/tests/test_main.py -k emergency_stop                → 2 passed
```

## Self-Check: PASSED

Phase 17 D-05 obligation discharged: api-gateway remains the sole admin-guarded emergency-stop entry; its existing positive-path tests stay green in-container; trading-engine returns 404 on the deleted route at the unit-test level. Live HTTP curl proof on `:8005` deferred to post-merge orchestrator action (environmental, not code).
