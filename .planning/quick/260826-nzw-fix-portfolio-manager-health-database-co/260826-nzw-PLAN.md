---
phase: quick-260826-nzw
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - services/portfolio-manager/app/handlers/health.py
  - services/portfolio-manager/tests/test_health_db_probe.py
autonomous: true
requirements: [QUICK-260826-NZW]

must_haves:
  truths:
    - "In-container /health reports database_connection=true when the service's live asyncpg pool answers SELECT 1"
    - "/ready reports database: ok via a live-pool probe when use_database is true and the pool exists; probe failure returns 503"
    - "use_database=False behavior is byte-identical to today (health: false, readiness: skipped)"
    - "A failing or hanging probe degrades to false/503 within ~2s, never an unhandled exception in the endpoint"
  artifacts:
    - path: "services/portfolio-manager/app/handlers/health.py"
      provides: "Live asyncpg pool probe with legacy shared.database fallback"
      contains: "_probe_db_pool"
    - path: "services/portfolio-manager/tests/test_health_db_probe.py"
      provides: "Regression coverage for pool-probe, fallback, and disabled-DB paths"
  key_links:
    - from: "services/portfolio-manager/app/handlers/health.py"
      to: "app.main db_pool global"
      via: "function-level import (same pattern as get_portfolio_manager)"
      pattern: "from app\\.main import db_pool"
    - from: "_probe_db_pool"
      to: "asyncpg pool"
      via: "SELECT 1 fetchval under asyncio.wait_for"
      pattern: "asyncio\\.wait_for"
---

<objective>
Fix the portfolio-manager `/health` `database_connection` false-negative (and the identical false-negative shape in `/ready`).

Root cause (verified live 2026-08-26): `app/handlers/health.py:48` and `:87` do `from shared.database.connection import db_manager`. In-container this ALWAYS raises ImportError — the Dockerfile creates an empty `./shared` dir (documented as a **dead import** in `.claude/rules/money.md`) — so `/health` reports `database_connection: false` while the service's real asyncpg pool (`app/main.py:140`, `db_pool`) is healthy and logging "Database connection pool created".

Purpose: honest health/readiness signals — monitoring currently cannot distinguish a dead DB from this dead import.
Output: `health.py` probing the live pool with a legacy fallback, plus host-run regression tests. No container rebuild/restart in this task — deploy is handled separately by the orchestrator.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@./CLAUDE.md
@.claude/rules/money.md
@.claude/rules/testing.md
@services/portfolio-manager/app/handlers/health.py
@services/portfolio-manager/app/main.py

<interfaces>
From services/portfolio-manager/app/main.py (module globals, line 134-140):

```python
portfolio_manager: Optional[PortfolioManager] = None
db_pool: Optional[asyncpg.Pool] = None   # created in lifespan when settings.use_database
```

From services/portfolio-manager/app/handlers/health.py (existing pattern to mirror, line 19-25):

```python
def get_portfolio_manager() -> PortfolioManager:
    from app.main import portfolio_manager   # function-level import against globals
    ...
```

From services/portfolio-manager/app/config.py:

```python
use_database: bool = Field(default=False, ...)   # line 104
```

From services/portfolio-manager/tests/test_health_handler.py (patch patterns to reuse — note the whole file is `pytest.mark.skip`-ed as stale; do NOT un-skip it):

- `TestClient(app)` without context manager → lifespan does NOT run, `app.main` globals stay None unless patched
- `patch('app.handlers.health.check_service_health', AsyncMock(return_value=True))`
- `patch('app.handlers.health.settings')` with `mock_settings.use_database = ...`
- `patch('app.main.portfolio_manager', mock_manager)`
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Probe the live asyncpg pool in health_check and readiness_check (test-first)</name>
  <files>services/portfolio-manager/tests/test_health_db_probe.py, services/portfolio-manager/app/handlers/health.py</files>
  <behavior>
    New host-run test file `tests/test_health_db_probe.py` (do NOT touch the skip-marked `test_health_handler.py`), all via `TestClient(app)` with `check_service_health` and `settings` patched as in the existing patterns above:
    - Test 1 (health, pool ok): `use_database=True`, `patch('app.main.db_pool', fake_pool)` where fake_pool probes clean → GET /health returns 200 with `database_connection: true`, and the fake connection's `fetchval` was awaited with "SELECT 1".
    - Test 2 (health, probe raises): same but the fake connection's `fetchval` has `side_effect=Exception("connection lost")` → 200 with `database_connection: false` (no 500).
    - Test 3 (health, pool None + import fails): `patch('app.main.db_pool', None)` and force the legacy import to fail deterministically via `patch.dict('sys.modules', {'shared': None, 'shared.database': None, 'shared.database.connection': None})` → 200 with `database_connection: false`.
    - Test 4 (health, use_database False): `patch('app.main.db_pool', fake_pool)` but `use_database=False` → `database_connection: false` and `fake_pool.acquire` never called (current behavior preserved exactly).
    - Test 5 (readiness, pool ok): `patch('app.main.portfolio_manager', Mock())`, `use_database=True`, healthy fake pool → GET /ready returns 200 with `database: "ok"`.
    - Test 6 (readiness, probe fails): same but probe raises → 503.
    - Test 7 (readiness, use_database False): → 200 with `database: "skipped"`.
    Fake-pool construction (prose, mirrors asyncpg's acquire-as-async-CM): build a MagicMock pool whose `acquire()` return value implements `__aenter__`/`__aexit__` as AsyncMocks, `__aenter__` yielding a connection object whose `fetchval` is an AsyncMock returning 1. No balance literals anywhere in fixtures (testing.md rule).
  </behavior>
  <action>
    Write the failing tests first, run them to confirm RED, then modify `app/handlers/health.py`:

    1. Add `import asyncio` at module top. Add a module-private helper `async def _probe_db_pool(pool) -> bool` that wraps the whole acquire-and-query in `asyncio.wait_for(..., timeout=2.0)`: acquire a connection via `async with pool.acquire() as conn` and `await conn.fetchval("SELECT 1")`; return True on success; on ANY exception (including `asyncio.TimeoutError`) log at warning ("Database pool probe failed: {e}") and return False. The timeout covers acquire too, since an exhausted pool blocks there.
    2. In `health_check()`: when `settings.use_database` is true, do a function-level `from app.main import db_pool` (same pattern as `get_portfolio_manager()` — MUST stay inside the function body so tests can patch `app.main.db_pool` and so module import order stays safe). If `db_pool is not None` → `database_healthy = await _probe_db_pool(db_pool)`. If `db_pool is None` → fall back to the EXISTING `from shared.database.connection import db_manager` block unchanged (preserves host-run/test behavior; in-container it stays a dead import but is now only reached when the real pool is absent). `use_database` False path: untouched.
    3. In `readiness_check()`: same shape. When `use_database` is true and `db_pool is not None`: probe via `_probe_db_pool`; True → `db_status = "ok"`, False → `raise HTTPException(status_code=503, detail="Database unavailable")`. When `db_pool is None`: keep the existing legacy block exactly as-is (ImportError → "unavailable", etc.).
    4. Run the new tests to GREEN. Cautions: the repo's format hook runs ruff at 88 cols and autoflake has previously stripped function-level imports — after editing, diff-check that `from app.main import db_pool` and the shared fallback import survived; re-add with `# noqa: F401`-style guard only if a tool strips them (they are used, so this should not trigger). Do not add any account-size literal; do not restart or rebuild the container.
  </action>
  <verify>
    <automated>cd services/portfolio-manager && python3 -m pytest tests/test_health_db_probe.py --no-cov -q</automated>
  </verify>
  <done>All 7 new tests pass on host; `_probe_db_pool` exists with a 2s `asyncio.wait_for` guard; `use_database=False` responses are unchanged from current behavior; legacy `shared.database.connection` fallback still present but only reachable when `db_pool is None`.</done>
</task>

<task type="auto">
  <name>Task 2: Full portfolio-manager suite regression</name>
  <files>services/portfolio-manager/tests/test_health_db_probe.py</files>
  <action>
    Run the full portfolio-manager host suite per testing.md (`--no-cov` mandatory) and compare against the pre-change baseline: capture baseline BEFORE Task 1's edits if not already done (`git stash`-free option: baseline is derivable by running the suite on HEAD first — Task 1 executor should run the full suite once before editing and record pass/fail counts). Requirement: zero NEW failures attributable to the health.py change. The stale `test_health_handler.py` remains skip-marked and must stay untouched (its skip predates this task and names its own reason; rewriting it is tracked follow-up work, out of scope here — do not "fix" it to make counts prettier, per testing.md's no-cosmetic-skip rule).
  </action>
  <verify>
    <automated>cd services/portfolio-manager && python3 -m pytest tests/ --no-cov -q</automated>
  </verify>
  <done>Full suite pass/fail counts match the pre-change baseline plus 7 new passing tests; no regressions in other handlers.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| monitoring→/health, /ready | unauthenticated internal probe endpoints; response content feeds alerting decisions |
| health handler→postgres | new SELECT 1 round-trip on every health poll |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | DoS | _probe_db_pool | mitigate | asyncio.wait_for 2.0s hard timeout wrapping acquire+query; any exception → false/503, endpoint never hangs or 500s |
| T-quick-02 | DoS | asyncpg pool exhaustion via health polling | accept | probe uses one pooled conn for <2s per poll against a min 2 / max 10 pool; poll cadence is minutes-scale |
| T-quick-03 | Info disclosure | readiness 503 detail strings | accept | pre-existing behavior, internal-only service port, no secrets in asyncpg error text; unchanged by this task |
| T-quick-SC | Tampering | package installs | n/a | zero new dependencies — asyncio is stdlib, asyncpg already imported by main.py |
</threat_model>

<verification>
- `cd services/portfolio-manager && python3 -m pytest tests/test_health_db_probe.py --no-cov -q` → 7/7 pass
- `cd services/portfolio-manager && python3 -m pytest tests/ --no-cov -q` → no new failures vs baseline
- `grep -n "from app.main import db_pool" services/portfolio-manager/app/handlers/health.py` → present, inside function bodies only
- `grep -c "asyncio.wait_for" services/portfolio-manager/app/handlers/health.py` → ≥ 1
- In-container proof (`docker exec` curl of `/health` showing `database_connection: true`) is deliberately DEFERRED to the orchestrator's deploy step — this plan does not restart/rebuild the container
</verification>

<success_criteria>
- `/health` derives `database_connection` from a live `SELECT 1` against `app.main.db_pool` when the pool exists; the dead `shared.database` import is demoted to a pool-is-None fallback
- `/ready` gets the same probe; failing probe → 503, healthy probe → `database: "ok"`
- `use_database=False` responses byte-identical to current behavior
- 7 new host tests green; full suite shows zero regressions
- No container restart performed by this plan
</success_criteria>

<output>
Create `.planning/quick/260826-nzw-fix-portfolio-manager-health-database-co/260826-nzw-SUMMARY.md` when done.
</output>
