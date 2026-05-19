---
phase: 10-path-to-live-dashboard
plan: 01
subsystem: api-gateway
tags:
  - api-gateway
  - preflight
  - state-file
  - phase-10
  - dashlive

dependency_graph:
  requires:
    - 08-02: /api/preflight/live-readiness (trading-engine endpoint this plan proxies)
  provides:
    - GET /api/preflight/carry-ins (D-10-04 response shape with joined live_readiness)
    - .planning/state/carry_ins.json (D-10-02 seed, atomic RW by api-gateway)
    - services/api-gateway/app/routes/ package (first route sub-package in api-gateway)
  affects:
    - docker-compose.unified.yml (api-gateway bind-mount + two env vars)
    - services/api-gateway/app/main.py (first include_router call)

tech_stack:
  added:
    - tempfile.mkstemp + os.fdopen + os.fsync + os.replace atomic write pattern (new to api-gateway)
  patterns:
    - FastAPI APIRouter module under services/api-gateway/app/routes/
    - Proxy fan-out to trading-engine with graceful UNKNOWN degradation (existing main.py pattern)
    - Local datetime import inside handler for autoflake survival (project memory feedback_main_imports_autoflake.md)

key_files:
  created:
    - .planning/state/carry_ins.json
    - services/api-gateway/app/routes/__init__.py
    - services/api-gateway/app/routes/preflight_carry_ins.py
  modified:
    - docker-compose.unified.yml
    - services/api-gateway/app/main.py

decisions:
  - Lazy import of get_proxy() inside handler body to avoid circular import (preflight_carry_ins.py imported by main.py after app construction)
  - _atomic_write_json accepts Path (not str); caller wraps os.environ.get result with Path()
  - _DEFAULT_STATE module constant defined but handler uses inline dict literals to keep the fallback explicit and easy to audit in-context
  - len(checks) >= 6 guard on all_pass computation defends against truncated proxy payloads (D-10-11 defense-in-depth)

metrics:
  duration: ~12 minutes
  completed_at: "2026-05-17T19:21:07Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 2
---

# Phase 10 Plan 01: Carry-ins API Endpoint and State Machine Summary

**One-liner:** File-backed carry-ins endpoint (`GET /api/preflight/carry-ins`) with atomic `_state` writes, 24h continuous-PASS window logic (D-10-07), and graceful degradation to `DO_NOT_FLIP` when trading-engine is unreachable.

## What Was Built

Three tasks shipped the full backend slice for the Phase 10 carry-ins dashboard surface:

**Task 1 — Seed state file + compose changes**

- `.planning/state/carry_ins.json` created with D-10-02 schema: `schema_version=1`, 5 open carry-ins (OP-01..04, INFRA-02), zeroed `_state` object.
- `docker-compose.unified.yml` api-gateway block: added `./.planning/state:/app/planning_state:rw` bind-mount of the parent directory (per CLAUDE.md WSL bind-mount-race gotcha) and two env vars with `${VAR:-default}` syntax: `PREFLIGHT_CARRY_INS_PATH` and `PREFLIGHT_CONTINUOUS_PASS_REQUIRED_SECONDS`.

**Task 2 — Router module**

- `services/api-gateway/app/routes/__init__.py` (package marker — first sub-package under api-gateway/app/).
- `services/api-gateway/app/routes/preflight_carry_ins.py`: 250 lines.
  - `_atomic_write_json(path, payload)` uses `tempfile.mkstemp` + `os.fdopen` + `os.fsync` + `os.replace`. On exception, unlinks tmp_name (best-effort) then re-raises. The bare `.write_text()` idiom from `ml.py:195` was explicitly NOT copied (PATTERNS.md falsifies the CONTEXT.md analog claim).
  - `@router.get("/carry-ins")` handler: fans out to trading-engine via `get_proxy().proxy_request(...)` (lazy import to avoid circular), reads state file, applies D-10-07 reset rule, computes `overall` (DO_NOT_FLIP / ALMOST / READY), writes `_state` atomically, returns D-10-04 shape with joined `live_readiness`.
  - All failure paths (proxy unreachable, file read/write error) logged as warnings; handler returns 200 with `overall="DO_NOT_FLIP"` — never raises.

**Task 3 — Router registration**

- `services/api-gateway/app/main.py`: inserted 3 lines immediately after the existing `/api/preflight/live-readiness` inline handler (line 1234 area):
  ```python
  # Phase 10 DASHLIVE-02 — carry-ins endpoint (state file + 24h window).
  from app.routes.preflight_carry_ins import router as preflight_carry_ins_router  # noqa: E402
  app.include_router(preflight_carry_ins_router)
  ```
  This is the first `include_router` call in api-gateway main.py. The `# noqa: E402` guards against autoflake stripping (T-10-01-06 mitigation).

## Verification Results

- `carry_ins.json` parses, schema_version=1, 5 carry-ins all `state="open"`, `_state` zeroed.
- `preflight_carry_ins.py` AST-parses; `_atomic_write_json` uses all canonical idioms; router has `prefix="/api/preflight"`; `@router.get("/carry-ins")` present; no `.write_text()` as state writer; no `Depends()` auth.
- `main.py` AST-parses; exactly 2 references to `preflight_carry_ins_router` (import + include_router); positioned after live-readiness handler (line 1235 > line 1168).
- `docker compose -f docker-compose.unified.yml config` exits 0.
- Volumes-block-scoped awk gate: 0 occurrences of single-file path in volumes block (env-var default does not false-positive).

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Notes

- PATTERNS.md "No Analog Found" for atomic write was confirmed correct: `ml.py:195` is a bare `write_text`, not an atomic temp+rename. The plan's explicit warning was followed; canonical Python idiom used from scratch.
- Formatter (post-write hook) added a blank line between the import and `app.include_router(...)` in main.py. Functionally identical; verified 2 references still present.

## Threat Flags

No new security surface beyond what the plan's threat model already covers (T-10-01-01 through T-10-01-06).

## Known Stubs

None — all five carry-ins have real descriptions from D-10-02; `_state` is intentionally zeroed as the correct seed state.

## Self-Check: PASSED

Files confirmed present:
- `.planning/state/carry_ins.json` — EXISTS
- `services/api-gateway/app/routes/__init__.py` — EXISTS
- `services/api-gateway/app/routes/preflight_carry_ins.py` — EXISTS

Commits confirmed:
- `12d5261` — Task 1 (carry_ins.json + compose)
- `c66f15c` — Task 2 (routes package + preflight_carry_ins.py)
- `2e5eed5` — Task 3 (main.py router registration)
