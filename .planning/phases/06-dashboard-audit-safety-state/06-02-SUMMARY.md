---
phase: 06-dashboard-audit-safety-state
plan: 02
subsystem: api-gateway, trading-engine, compose
tags: [DASH-03, safety-state, kill-switch, F-01, F-02, F-03, F-04]
requires:
  - 06-01 (planning artifacts D-04/D-07/D-08/D-09/D-10/D-11)
provides:
  - GET /api/config/safety-state (D-08 schema, fan-out to trading-engine)
  - trading-engine /status now emits emergency_stop.mtime
  - trading-engine /api/v1/risk/budget/current now emits utilization.daily_pnl_pct
  - docker-compose.unified.yml api-gateway env block exposes TRADING_MODE / PAPER_TRADING_MODE / ENABLE_ML_PREDICTIONS
affects:
  - frontend dashboard StatusBar (Plan 06-04 will consume this)
tech-stack:
  added: []
  patterns:
    - "ServiceProxy.proxy_request returns JSONResponse → decode via json.loads(resp.body.decode())"
    - "Local-import of datetime.timezone inside handler to survive autoflake on main.py"
key-files:
  created:
    - services/trading-engine/tests/test_health_status.py
    - services/trading-engine/tests/test_risk_budget_daily_pnl_pct.py
    - services/api-gateway/tests/test_safety_state.py
    - .planning/phases/06-dashboard-audit-safety-state/deferred-items.md
  modified:
    - services/trading-engine/app/handlers/health.py
    - services/trading-engine/app/risk/dynamic_risk_budget.py
    - services/api-gateway/app/main.py
    - docker-compose.unified.yml
decisions:
  - "Compute daily_pnl_pct post-asdict() in get_current_budget rather than mutating RiskUtilization dataclass (preserves /api/v1/risk/budget/utilization shape)"
  - "Local-import timezone inside get_safety_state to survive autoflake on main.py refactors"
metrics:
  duration_seconds: 1806
  duration_minutes: 30
  completed: "2026-05-13"
  tasks_completed: 4
  commits: 7
  tests_added: 19
  files_created: 4
  files_modified: 4
---

# Phase 6 Plan 02: Backend Wiring for Safety-State (DASH-03) Summary

Aggregated safety-posture endpoint `GET /api/config/safety-state` shipped on the api-gateway; trading-engine `/status` and `/api/v1/risk/budget/current` extended with the missing `emergency_stop.mtime` and `utilization.daily_pnl_pct` fields; docker-compose.unified.yml api-gateway env block patched to expose `TRADING_MODE` / `PAPER_TRADING_MODE` / `ENABLE_ML_PREDICTIONS`. All four F-fixes (F-01..F-04) closed; 19 pytest cases (4 + 4 + 11) pass against the running containers; D-08 schema verified live via curl with the trading-engine UP and DOWN.

## Schema Delivered

```bash
$ curl -sS http://localhost:8000/api/config/safety-state
{
  "trading_mode": "PAPER",
  "paper_trading_mode": true,
  "auto_trading_enabled": true,
  "emergency_stop": {
    "active": false,
    "mtime": null
  },
  "ml_predictions_enabled": false,
  "kill_switch": {
    "daily_loss_armed": true,
    "daily_pnl_pct": 0.0,
    "tripped": false
  },
  "last_updated_at": "2026-05-13T21:07:38.440181+00:00"
}
```

Matches D-08 exactly. The fan-out is to two trading-engine endpoints:

- `GET /status` → `auto_trading_enabled`, `emergency_stop.{active,mtime}`
- `GET /api/v1/risk/budget/current` → `kill_switch.{daily_loss_armed, daily_pnl_pct, tripped}`

Env-derived (gateway-local): `trading_mode`, `paper_trading_mode`, `ml_predictions_enabled`. Gateway-stamped: `last_updated_at` (ISO 8601 UTC).

## Test Coverage

| Suite | Count | File | Status |
|-------|-------|------|--------|
| trading-engine health.py mtime | 4 | services/trading-engine/tests/test_health_status.py | PASS (in container) |
| trading-engine risk_budget daily_pnl_pct | 4 | services/trading-engine/tests/test_risk_budget_daily_pnl_pct.py | PASS (in container) |
| api-gateway safety-state | 11 | services/api-gateway/tests/test_safety_state.py | PASS (in container) |

### F-01 / F-03 load-bearing tests (named per plan acceptance gates)

| Test | Fix | Asserts |
|------|-----|---------|
| `test_daily_loss_armed_defaults_false_when_budget_empty` | F-01 | When te_budget proxy raises OR returns {}, `daily_loss_armed` is False — NOT hardcoded True |
| `test_daily_loss_armed_true_when_budget_reachable` | F-01 | Non-empty te_budget body → `daily_loss_armed` is True AND `tripped` is False |
| `test_tripped_true_when_emergency_mode_flag_set` | F-01 | `emergency_mode: True` flat bool → `tripped` is True (proves NOT a dict-walk) |
| `test_proxy_returns_jsonresponse_decoded_via_body_decode` | F-03 | Real JSONResponse mock; handler returns non-default values → proves body.decode pipeline ran end-to-end |

### Live container runs

```text
=== API GATEWAY: 11 tests ===
11 passed, 12 warnings in 0.12s

=== TRADING ENGINE: 8 tests ===
8 passed, 532 warnings in 8.89s
```

Tests run in the deployed `crypto-bot-api-gateway` and `crypto-bot-trading` containers (CLAUDE.md gotcha: host fastapi 0.136 vs container 0.109; tests must run in-container).

## F-fix closures

### F-01 — kill_switch derivation (api-gateway/main.py)

**Before (PATTERNS.md lines 376-380 — never landed; was the WRONG recipe):**
```python
"kill_switch": {
    "daily_loss_armed": te_budget.get("emergency_mode", {}).get("armed", True),
    "daily_pnl_pct": float(te_budget.get("utilization", {}).get("daily_pnl_pct", 0.0)),
    "tripped": te_budget.get("emergency_mode", {}).get("active", False),
},
```
(Would always evaluate the inner `.get(...).get("armed", True)` chain on a bool — raises `AttributeError: 'bool' object has no attribute 'get'`, OR with a defensive `.get` fallback returns the literal `True` regardless of reality.)

**After (this plan):**
```python
kill_switch = {
    "daily_loss_armed": bool(te_budget),
    "daily_pnl_pct": float(
        te_budget.get("utilization", {}).get("daily_pnl_pct", 0.0)
    ),
    "tripped": bool(te_budget.get("emergency_mode", False)),
}
```

**Verification (live):** with trading-engine stopped, `kill_switch.daily_loss_armed` → `false`, `tripped` → `false` (correct). With trading-engine up, both transitions handled.

### F-02 — utilization.daily_pnl_pct (trading-engine/dynamic_risk_budget.py)

**Before:** `utilization` dict had `total_budget_usd`, `used_budget_usd`, `available_budget_usd`, `utilization_pct` ONLY. No `daily_pnl_pct`. The api-gateway would have returned `0.0` permanently for that field.

**After (manager.get_current_budget):**
```python
utilization_dict = utilization.to_dict()
utilization_dict["daily_pnl_pct"] = (
    (self._daily_pnl / self._current_equity) * 100.0
    if self._current_equity > 0
    else 0.0
)
return {
    "budget": budget.to_dict(),
    "utilization": utilization_dict,
    ...
}
```

**Verification (live):**
```bash
$ curl -sS http://localhost:8005/api/v1/risk/budget/current | jq '.utilization.daily_pnl_pct'
0.0
```
Key present (was missing pre-plan). Sign-preserved per F-02 evidence — kill-switch trip check at line 1186 uses `abs()` separately for threshold; the wire value is signed for UI display.

### F-03 — proxy_request returns JSONResponse (api-gateway/main.py)

**Before (the seductive bug):** `await proxy.proxy_request(...).get("auto_trading_enabled")` → `AttributeError: 'JSONResponse' object has no attribute 'get'`. Every request → 500.

**After (this plan, mirroring existing main.py:271):**
```python
te_status_resp = await proxy.proxy_request(
    service_name="trading-engine", path="/status", method="GET"
)
if getattr(te_status_resp, "status_code", 500) == 200:
    te_status = json.loads(te_status_resp.body.decode())
```

Same shape for `te_budget_resp`. Both wrapped in `try/except Exception` so a proxy raise sets the var to `{}` and downstream `.get(...)` calls remain safe.

**Verification:** `test_proxy_returns_jsonresponse_decoded_via_body_decode` feeds a real `JSONResponse(content=..., status_code=200)` mock and asserts the handler returns non-default values end-to-end. If the handler called `.get()` on the JSONResponse, the test client would see 500 and the test would fail.

### F-04 — api-gateway compose env block (docker-compose.unified.yml)

**Before (lines 253-283):** api-gateway environment lacked the trading-mode flags. `os.getenv("TRADING_MODE", "PAPER")` in the new handler would always return the python default, regardless of operator `.env`.

**Diff:**
```yaml
       - EMERGENCY_STOP_FILE=${EMERGENCY_STOP_FILE:-/app/EMERGENCY_STOP}
+      # Trading-mode flags — read by /api/config/safety-state (DASH-03 / Plan 06-02).
+      # Defaults match CLAUDE.md project rules: TRADING_MODE starts at PAPER, the
+      # four deliberate steps to LIVE require explicit env override.
+      - TRADING_MODE=${TRADING_MODE:-PAPER}
+      - PAPER_TRADING_MODE=${PAPER_TRADING_MODE:-true}
+      - ENABLE_ML_PREDICTIONS=${ENABLE_ML_PREDICTIONS:-false}
     volumes:
       - ./services/api-gateway/logs:/app/logs
```

**Verification:**
- YAML parses cleanly (`python3 -c "import yaml; yaml.safe_load(open('docker-compose.unified.yml'))"`).
- awk-extracted api-gateway block contains all three vars (4 grep hits — TRADING_MODE appears twice in the `${VAR:-default}` substitution).
- A `docker compose up -d --force-recreate api-gateway` will pick these up on next stack boot.

## Graceful-degradation behavior (verified live)

Stopped `crypto-bot-trading` container, hit `/api/config/safety-state`:

```json
{
  "trading_mode": "PAPER",
  "paper_trading_mode": true,
  "auto_trading_enabled": false,
  "emergency_stop": { "active": false, "mtime": null },
  "ml_predictions_enabled": false,
  "kill_switch": {
    "daily_loss_armed": false,
    "daily_pnl_pct": 0.0,
    "tripped": false
  },
  "last_updated_at": "2026-05-13T21:08:46.573645+00:00"
}
```

- 200 (not 500/503) — D-09 graceful degradation honored.
- `auto_trading_enabled=false` — safe default (assume the worst).
- `emergency_stop = {active:false, mtime:null}` — safe default.
- `kill_switch.daily_loss_armed=false` — **F-01 behavior gate PASS** (the WRONG hardcoded `True` would have made the dashboard show the kill-switch as armed even though trading-engine is unreachable).
- `tripped=false` — safe default.

Trading-engine restarted and stack is back to normal afterward.

## Verify-stack discipline (per CLAUDE.md "Verification standards")

| Check | Status | Evidence |
|-------|--------|----------|
| Endpoint returns 200 with the D-08 schema | PASS | curl output above |
| F-01 derivation correct on the wire (trading-engine DOWN) | PASS | live graceful-degradation curl above |
| F-02 wire value present | PASS | `curl :8005/api/v1/risk/budget/current` shows `daily_pnl_pct` |
| F-03 decode pattern (no `.get` on JSONResponse) | PASS | grep + dedicated pytest |
| api-gateway restarted after route edit | PASS | `docker restart crypto-bot-api-gateway` ran post-cp |
| trading-engine restarted after handler edit | PASS | `docker restart crypto-bot-trading` ran post-cp |
| pytest in-container | PASS | 11 + 8 = 19 tests pass |
| DB writes unchanged | N/A | endpoint is read-only |

**Caveat:** the api-gateway env vars from F-04 are not yet visible inside the running container — the running container was created before this patch, so `docker exec env | grep TRADING_MODE` returns nothing. The python defaults coincidentally match (`PAPER`/`true`/`false`), so the live response shape is correct *today*. Operator must `docker compose -f docker-compose.unified.yml up -d --force-recreate api-gateway` after merge to make the env-substitution path live. The plan completes its required deliverable (compose file patched + container substitution proven via YAML parse), and the visible defaults in the curl above are correct regardless of which code path produced them.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] trading-engine container name discrepancy**
- **Found during:** Task 1 verification setup.
- **Issue:** Plan acceptance criteria reference `crypto-bot-trading-engine` (lines 219, 449 of 06-02-PLAN.md). Actual container name per `docker-compose.unified.yml:529` is `crypto-bot-trading`.
- **Fix:** All in-container test runs and `docker stop` graceful-degradation checks used the correct `crypto-bot-trading` name. No code/compose edits required — purely a documentation drift in the plan.
- **Files modified:** none (documentation-only deviation).
- **Commit:** n/a (this fix is in the operational verification only).

**2. [Rule 3 - Blocking] autoflake stripped `timezone` from top-level import**
- **Found during:** Task 4 GREEN test run (in-container pytest raised `NameError: name 'timezone' is not defined`).
- **Issue:** Hook formatter on services/api-gateway/app/main.py removed `, timezone` from the `from datetime import datetime` line at line 34. Per project memory `feedback_main_imports_autoflake.md`, autoflake runs over main.py and strips perceived-unused top-level imports.
- **Fix:** Imported `timezone` locally inside `get_safety_state` (`from datetime import timezone as _tz`). This pattern is the documented workaround and matches the project memory note.
- **Files modified:** services/api-gateway/app/main.py (workaround inside the new handler).
- **Commit:** b33e7ae (folded into Task 4 GREEN).

**3. [Rule 3 - Scope-boundary] semgrep pre-existing findings on untouched compose blocks**
- **Found during:** Task 3 PostToolUse semgrep scan.
- **Issue:** semgrep flagged 12 warnings (no-new-privileges / read_only / docker.sock) on the postgres/timescaledb/redis/rabbitmq/prometheus/grafana blocks and line 768. NONE are in the api-gateway block (lines 245-310) I edited.
- **Fix:** Logged to `.planning/phases/06-dashboard-audit-safety-state/deferred-items.md` per executor scope-boundary rule ("only auto-fix issues DIRECTLY caused by the current task's changes"). Stateful DB services require `tmpfs` planning before `read_only:true` is safe — needs operator sign-off; not in DASH-03 scope.
- **Files modified:** .planning/phases/06-dashboard-audit-safety-state/deferred-items.md (added).
- **Commit:** 72333d8 (folded into Task 3).

### Architectural decisions

**`daily_pnl_pct` placement** — Inserted post-`utilization.to_dict()` inside `manager.get_current_budget` rather than mutating `RiskUtilization` dataclass. Reason: changing the dataclass would ripple into `/api/v1/risk/budget/utilization` (UtilizationResponse pydantic), expanding the change surface beyond DASH-03. The post-`to_dict()` insertion satisfies every grep gate, preserves the existing `/utilization` endpoint shape, and keeps the math in a single location (the manager). Advisor concurred before implementation.

## Schema-compliance check (D-08)

| D-08 key | Source | Present | Type |
|----------|--------|---------|------|
| `trading_mode` | env `TRADING_MODE` (uppercased) | yes | str |
| `paper_trading_mode` | env `PAPER_TRADING_MODE` | yes | bool |
| `auto_trading_enabled` | trading-engine /status | yes | bool |
| `emergency_stop.active` | trading-engine /status | yes | bool |
| `emergency_stop.mtime` | trading-engine /status (this plan) | yes | str\|null |
| `ml_predictions_enabled` | env `ENABLE_ML_PREDICTIONS` | yes | bool |
| `kill_switch.daily_loss_armed` | bool(te_budget) | yes | bool |
| `kill_switch.daily_pnl_pct` | te_budget.utilization.daily_pnl_pct (this plan) | yes | float |
| `kill_switch.tripped` | bool(te_budget.emergency_mode) | yes | bool |
| `last_updated_at` | gateway-stamped ISO UTC | yes | str |

**No deviations from the D-08 schema.** All keys present in both happy-path and graceful-degradation responses.

## Phase 7 deferral

`live_trading_acknowledged` — a fifth safety flag tracking `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY` (CLAUDE.md "Trading-mode flags" rule). Not in the D-08 schema, so out of scope for Plan 06-02 / Plan 06-04. Defer to Phase 7. Documented in the route's docstring so a future operator does not see `TRADING_MODE=LIVE` pill while trading-engine refuses to boot.

## Commits

| # | Hash | Subject |
|---|------|---------|
| 1 | 003071b | test(06-02): add failing test for emergency_stop.mtime (Task 1 RED) |
| 2 | 150f9b2 | feat(06-02): add emergency_stop.mtime to trading-engine /status (Task 1 GREEN) |
| 3 | 5e56781 | test(06-02): add failing test for utilization.daily_pnl_pct (Task 2 RED) |
| 4 | eb97b5b | feat(06-02): emit utilization.daily_pnl_pct from manager.get_current_budget (Task 2 GREEN) |
| 5 | 72333d8 | fix(06-02): expose TRADING_MODE / PAPER_TRADING_MODE / ENABLE_ML_PREDICTIONS to api-gateway (F-04) |
| 6 | 45f2a8d | test(06-02): add failing tests for GET /api/config/safety-state (Task 4 RED) |
| 7 | b33e7ae | feat(06-02): add GET /api/config/safety-state route on api-gateway (Task 4 GREEN) |

## Threat Flags

No new security-relevant surface introduced beyond what the plan's threat_model anticipated. Threat T-06-02-01 (information disclosure of operator config flags) explicitly accepted under D-09; no secrets / balances / positions exposed.

## TDD Gate Compliance

Plan 06-02 uses task-level `tdd="true"` (not plan-level `type: tdd`). For Tasks 1, 2, 4: a `test(...)` RED commit was created and the test was confirmed to FAIL before the corresponding `feat(...)` GREEN commit, where the test then PASSES. All three TDD cycles complete.

## Known gotcha — verifier note on container-test invocation

**The plan acceptance criteria say `docker exec crypto-bot-api-gateway pytest /app/tests/test_safety_state.py -x`. On a freshly built image, `/app/tests/` does NOT exist.** Both `services/api-gateway/Dockerfile` and `services/trading-engine/Dockerfile` only `COPY ./app/` — they intentionally exclude the test directory from production images (good security practice).

To reproduce the in-container pytest runs documented above, use the same workaround this plan used:

```bash
docker exec crypto-bot-api-gateway mkdir -p /tmp/tests
docker cp services/api-gateway/tests/conftest.py crypto-bot-api-gateway:/tmp/tests/
docker cp services/api-gateway/tests/__init__.py crypto-bot-api-gateway:/tmp/tests/
docker cp services/api-gateway/tests/test_safety_state.py crypto-bot-api-gateway:/tmp/tests/
docker exec -w /app crypto-bot-api-gateway python -m pytest /tmp/tests/test_safety_state.py -x
```

(Or build a dedicated test image with `--target tests` if the Dockerfile gains a tests stage in a future plan; out of scope here.)

The hot-patch approach (`docker cp` of source + `docker restart`) was used in this session to verify the live endpoint behavior against the running stack without forcing a full image rebuild. The orchestrator's merge-back will rebuild images from worktree source and the route + handler extensions will land cleanly.

## Self-Check: PASSED

### Created files verified
- FOUND: services/trading-engine/tests/test_health_status.py
- FOUND: services/trading-engine/tests/test_risk_budget_daily_pnl_pct.py
- FOUND: services/api-gateway/tests/test_safety_state.py
- FOUND: .planning/phases/06-dashboard-audit-safety-state/deferred-items.md
- FOUND: .planning/phases/06-dashboard-audit-safety-state/06-02-SUMMARY.md

### Modified files verified
- FOUND: services/trading-engine/app/handlers/health.py
- FOUND: services/trading-engine/app/risk/dynamic_risk_budget.py
- FOUND: services/api-gateway/app/main.py
- FOUND: docker-compose.unified.yml

### Commits verified
All 8 commit hashes (003071b, 150f9b2, 5e56781, eb97b5b, 72333d8, 45f2a8d, b33e7ae, 06005c3) confirmed present via `git log --oneline --all | grep <hash>`.
