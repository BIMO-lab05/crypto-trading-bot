---
phase: 08-pre-live-preflight
plan: 02
type: execute
wave: 2
depends_on:
  - 08-01
files_modified:
  - scripts/preflight_live.py
  - services/trading-engine/app/handlers/preflight.py
  - services/trading-engine/tests/test_preflight_route.py
  - services/api-gateway/app/main.py
  - services/api-gateway/tests/test_preflight_proxy.py
autonomous: true
requirements:
  - PREFLIGHT-01
tags:
  - preflight
  - cli
  - api-gateway
  - http-route

must_haves:
  truths:
    - "`python3 scripts/preflight_live.py --json` prints the schema_version=1 JSON shape to stdout and exits 0 on PASS / 1 on FAIL or UNKNOWN."
    - "`python3 scripts/preflight_live.py --check=cap` runs only the cap check (single-check mode)."
    - "`GET http://localhost:8005/api/preflight/live-readiness` on trading-engine returns 200 with the schema_version=1 body (6 checks, overall, evaluated_at)."
    - "`GET http://localhost:8000/api/preflight/live-readiness` on api-gateway proxies to trading-engine and surfaces the same body verbatim on success."
    - "When trading-engine is unreachable, the api-gateway proxy returns 200 with overall=UNKNOWN and all 6 checks UNKNOWN — never falls back to PASS."
  artifacts:
    - path: "scripts/preflight_live.py"
      provides: "CLI with --json / --text / --check / --dry-run --target flags"
      contains: "if __name__ == \"__main__\""
    - path: "services/trading-engine/app/handlers/preflight.py"
      provides: "FastAPI router exposing GET /api/preflight/live-readiness on trading-engine (port 8005)"
      contains: "APIRouter"
    - path: "services/api-gateway/app/main.py"
      provides: "proxy route adding /api/preflight/live-readiness on api-gateway (port 8000)"
      modifies: "+1 route handler near line 1166"
    - path: "services/trading-engine/tests/test_preflight_route.py"
      provides: "trading-engine route test asserting schema + 6 check names"
      contains: "schema_version"
    - path: "services/api-gateway/tests/test_preflight_proxy.py"
      provides: "gateway proxy test — happy path + unreachable-degradation"
      contains: "UNKNOWN"
  key_links:
    - from: "scripts/preflight_live.py"
      to: "services/trading-engine/app/preflight"
      via: "sys.path.insert + import"
      pattern: "sys\\.path\\.insert.*trading-engine"
    - from: "services/trading-engine/app/handlers/preflight.py"
      to: "services/trading-engine/app/preflight"
      via: "from app.preflight import run_all"
      pattern: "from app\\.preflight import run_all"
    - from: "services/api-gateway/app/main.py"
      to: "services/trading-engine/app/handlers/preflight.py"
      via: "ServiceProxy.proxy_request to trading-engine /api/preflight/live-readiness"
      pattern: "/api/preflight/live-readiness"
---

<objective>
Surface the preflight module (from 08-01) through two channels: a CLI script and an HTTP endpoint. Both share the exact same `run_all()` call; no logic duplication. The api-gateway adds a thin proxy with graceful degradation to UNKNOWN — never PASS — when trading-engine is unreachable.

Purpose: Operators run the CLI for quick checks. The dashboard (Phase 10) polls the HTTP endpoint through api-gateway every 5 seconds.

Output:
- `scripts/preflight_live.py` (CLI, ~80 lines)
- `services/trading-engine/app/handlers/preflight.py` (router, ~30 lines)
- Proxy route added to `services/api-gateway/app/main.py` (~50 lines inserted)
- 2 test files asserting schema, schema, and the load-bearing UNKNOWN safe-default

NOTE: `services/trading-engine/app/main.py` is NOT modified in this plan — that file is owned exclusively by 08-03 (router-mount + lifespan cap-check are co-located so the grep-gate scope is single-file).
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/08-pre-live-preflight/08-CONTEXT.md
@.planning/phases/08-pre-live-preflight/08-PATTERNS.md
@.planning/phases/08-pre-live-preflight/08-01-SUMMARY.md

<!-- Existing files this plan reads (analogs + targets) -->
@services/trading-engine/app/handlers/risk_budget.py
@services/api-gateway/app/main.py
@services/api-gateway/tests/test_safety_state.py
@services/api-gateway/tests/conftest.py
@scripts/audit_tiles.py
@services/trading-engine/tests/test_main.py

<interfaces>
<!-- The preflight module already exists from 08-01. -->

From services/trading-engine/app/preflight/__init__.py (08-01):
```python
def run_all(settings: Settings | None = None) -> PreflightReport: ...
# PreflightReport.to_dict() -> dict with keys: schema_version, overall, evaluated_at, checks
```

From services/api-gateway/app/main.py existing (~line 1049+):
```python
@app.get("/api/config/safety-state")
async def get_safety_state():
    proxy = get_proxy()
    resp = await proxy.proxy_request(
        service_name="trading-engine",
        path="/api/config/safety-state",
        method="GET",
    )
    # ... json.loads(resp.body.decode()) on success; safe defaults on exception
```

From services/api-gateway/tests/test_safety_state.py (analog):
```python
def _build_response(content, status_code=200):
    r = JSONResponse(content=content, status_code=status_code)
    r.body = json.dumps(content).encode()
    return r
```

JSON shape this plan produces (locked from 08-CONTEXT.md):
```json
{
  "schema_version": 1,
  "overall": "PASS|FAIL|UNKNOWN",
  "evaluated_at": "2026-05-16T14:32:01Z",
  "checks": [
    {"check": "cap", "status": "PASS", "detail": "..."},
    {"check": "paper_mode", "status": "PASS", "detail": "..."},
    {"check": "trading_mode", "status": "PASS", "detail": "..."},
    {"check": "ack", "status": "PASS", "detail": "..."},
    {"check": "emergency_stop", "status": "PASS", "detail": "..."},
    {"check": "dsr_evidence", "status": "UNKNOWN", "detail": "..."}
  ]
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: CLI entry point `scripts/preflight_live.py`</name>
  <files>scripts/preflight_live.py</files>
  <read_first>
    - scripts/audit_tiles.py (lines 1-29 — docstring + shebang analog; lines 233-309 — argparse + main() + exit pattern)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 305-373 — copy-ready CLI pattern with sys.path insert)
    - .planning/phases/08-pre-live-preflight/08-CONTEXT.md (lines 77-87 — CLI flag spec)
  </read_first>
  <behavior>
    - `python3 scripts/preflight_live.py` (no flags) prints human-readable text: one line per check (`  STATUS    name    detail`) plus a final `OVERALL: <status>` line. Exit 0 on PASS, 1 on FAIL/UNKNOWN.
    - `python3 scripts/preflight_live.py --json` prints valid JSON parseable by `json.loads`, schema_version=1, 6 checks. Exit code same as text mode.
    - `python3 scripts/preflight_live.py --check=cap` runs only the named check. JSON or text output filtered to that one check.
    - `python3 scripts/preflight_live.py --check=bogus_name` exits 2 with a stderr error (bad arg semantics from audit_tiles.py).
    - `python3 scripts/preflight_live.py --dry-run --target=HEAD` reads `.env.example` from the git ref via `git show HEAD:.env.example`, parses key=value lines, overlays onto a fresh Settings instance (does NOT read process env), runs `run_all` against that, prints JSON, exits 0/1 per overall.
  </behavior>
  <action>
    1. Create `scripts/preflight_live.py` with shebang `#!/usr/bin/env python3` and module docstring per 08-PATTERNS.md lines 311-326.

    2. Add the sys.path insert per 08-PATTERNS.md lines 340-342:
       ```python
       _REPO_ROOT = Path(__file__).resolve().parent.parent
       sys.path.insert(0, str(_REPO_ROOT / "services" / "trading-engine"))
       from app.preflight import run_all  # noqa: E402
       ```

    3. Build the argparse parser per 08-PATTERNS.md lines 346-354. Flags: `--json` (store_true), `--text` (default behavior — no flag needed, but accept it for symmetry), `--check=<name>` (str, default None), `--dry-run` (store_true), `--target=<ref>` (str, default None).

    4. Implement `main(argv: list[str] | None = None) -> int`:
       - If `args.dry_run`: require `args.target`; run `subprocess.run(["git", "show", f"{args.target}:.env.example"], capture_output=True, text=True, check=True)`; parse the stdout as dotenv (each non-comment `KEY=VALUE` line); construct a fresh `Settings(**parsed)` instance; pass to `run_all(settings=...)`. If `git show` fails, exit code 2 with stderr message.
       - Else: call `report = run_all()` (uses default settings from process env).
       - If `args.check`: filter `report.checks` to the one matching; if no match, exit 2 with stderr `"unknown check: ..."`.
       - If `args.json`: print `json.dumps({"schema_version":1, "overall":..., "evaluated_at":..., "checks":[...]}, indent=2)` (build from filtered report).
       - Else: human-readable per 08-PATTERNS.md line 364 — `print(f"  {c.status:8s}  {c.check:18s}  {c.detail}")` for each, then `print(f"\nOVERALL: {report.overall}")`.
       - Return `0 if report.overall == "PASS" else 1`.

    5. `if __name__ == "__main__": sys.exit(main())`.

    6. Make executable: `chmod +x scripts/preflight_live.py` (note in done criteria).
  </action>
  <verify>
    <automated>python3 scripts/preflight_live.py --json &gt; /tmp/preflight_out.json; EC=$?; python3 -c "import json,sys; d=json.load(open('/tmp/preflight_out.json')); assert d['schema_version']==1; assert d['overall'] in ('PASS','FAIL','UNKNOWN'); assert len(d['checks'])==6 or '$EC'=='2'; print('CLI OK (exit=$EC, overall='+d['overall']+')')"</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c 'if __name__ == "__main__"' scripts/preflight_live.py` returns 1.
    - Source assertion: `grep -c "from app.preflight import run_all" scripts/preflight_live.py` returns 1.
    - Source assertion: `grep -cE "argparse|ArgumentParser" scripts/preflight_live.py` returns ≥1.
    - Source assertion: `grep -cE "(--dry-run|dry_run)" scripts/preflight_live.py` returns ≥1.
    - Behavior assertion: `python3 scripts/preflight_live.py --json` exits with code 0 or 1 (NOT 2 — meaning the CLI ran cleanly); `jq -e '.schema_version == 1 and (.checks | length) == 6' /tmp/preflight_out.json` exits 0. (If `jq` not available, the inline python assertion in `<verify>` substitutes.)
    - Behavior assertion: `python3 scripts/preflight_live.py --check=bogus` exits 2.
    - Behavior assertion: `python3 scripts/preflight_live.py --check=cap --json` returns valid JSON containing one check named "cap".
  </acceptance_criteria>
  <done>scripts/preflight_live.py exists, executable, prints schema_version=1 JSON when --json, prints human-readable lines + OVERALL when no flag, supports --check filter and --dry-run --target git-ref read.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: trading-engine HTTP route + tests</name>
  <files>services/trading-engine/app/handlers/preflight.py, services/trading-engine/tests/test_preflight_route.py</files>
  <read_first>
    - services/trading-engine/app/handlers/risk_budget.py (lines 18-37 — imports + APIRouter pattern; lines 378-415 — GET handler + try/except)
    - services/trading-engine/tests/test_main.py (lines 27-31 — TestClient(app) pattern)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 252-291 — router copy-ready code; lines 651-685 — route test pattern)
  </read_first>
  <behavior>
    - GET `/api/preflight/live-readiness` returns 200 with body matching the schema_version=1 shape (overall in {PASS,FAIL,UNKNOWN}, checks list length 6, every check has keys {check, status, detail}, every status in {PASS,FAIL,UNKNOWN}).
    - The set of check names equals `{"cap","paper_mode","trading_mode","ack","emergency_stop","dsr_evidence"}` exactly.
    - On unexpected exception inside `run_all()`, returns 500 with the error in the detail (NOT silently PASS — let the api-gateway proxy translate to UNKNOWN-everywhere via its own try/except).
  </behavior>
  <action>
    1. Create `services/trading-engine/app/handlers/preflight.py` per 08-PATTERNS.md lines 258-291. Imports: `logging`, `from fastapi import APIRouter, HTTPException`, `from app.preflight import run_all`. Router: `APIRouter(prefix="/api/preflight", tags=["preflight"])`. Handler:
       ```python
       @router.get("/live-readiness")
       async def get_live_readiness() -> dict:
           try:
               report = run_all()
               return report.to_dict()
           except Exception as e:
               logger.error(f"Preflight live-readiness check failed: {e}", exc_info=True)
               raise HTTPException(status_code=500, detail=f"Preflight check internal error: {e}")
       ```
       Note: NO authentication dependency on this route (D-09 pattern: unauthenticated read-only). Do NOT add `Depends(get_current_admin_user)`.

    2. Create `services/trading-engine/tests/test_preflight_route.py` per 08-PATTERNS.md lines 651-685. Use `TestClient(app)`, NOT `admin_client`. Tests:
       - `test_route_returns_schema_v1`: GET `/api/preflight/live-readiness` → status_code 200; body['schema_version']==1; body['overall'] in {PASS,FAIL,UNKNOWN}; len(body['checks'])==6; set of check names matches exact 6; every check has status in {PASS,FAIL,UNKNOWN} and keys {check,status,detail}.
       - `test_route_no_auth_required`: GET WITHOUT any auth header still returns 200 (asserts D-09 unauthenticated decision). If the route is accidentally re-protected later, this test fails loudly.
       - `test_route_500_on_internal_error` (monkeypatch `app.preflight.run_all` to raise): GET → 500 (asserts the route surfaces failures rather than silently returning PASS — proxy layer handles UNKNOWN-degradation).

    3. NOTE: this plan does NOT mount the router on `app` — that mount is owned by 08-03 in `services/trading-engine/app/main.py`. **The test file MUST import & include the router manually in a test app fixture** so tests can pass before 08-03 lands:
       ```python
       @pytest.fixture
       def client():
           from fastapi import FastAPI
           from app.handlers.preflight import router
           test_app = FastAPI()
           test_app.include_router(router)
           return TestClient(test_app)
       ```
       Document this fixture choice in a comment referencing 08-03 (final mount).
  </action>
  <verify>
    <automated>cd services/trading-engine &amp;&amp; pytest tests/test_preflight_route.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "APIRouter(prefix=\"/api/preflight\"" services/trading-engine/app/handlers/preflight.py` returns 1.
    - Source assertion: `grep -c "from app.preflight import run_all" services/trading-engine/app/handlers/preflight.py` returns 1.
    - Source assertion: `grep -c "admin" services/trading-engine/app/handlers/preflight.py` returns 0 (no auth dep — D-09).
    - Source assertion: `grep -c "test_route_no_auth_required" services/trading-engine/tests/test_preflight_route.py` returns 1 (the auth-leak guard test exists).
    - Behavior assertion: `pytest services/trading-engine/tests/test_preflight_route.py -v` exits 0; at least 3 tests pass.
    - Behavior assertion (post-08-03 integration smoke, optional in this plan): once 08-03 mounts the router, `curl -s http://localhost:8005/api/preflight/live-readiness | jq -e '.schema_version == 1 and (.checks | length) == 6'` exits 0 — record this in SUMMARY as a forward-reference check, but do NOT block 08-02 acceptance on a running container.
  </acceptance_criteria>
  <done>preflight router exists, returns schema_version=1 with 6 checks, no auth dependency, ≥3 route tests pass against a standalone test_app fixture.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: api-gateway proxy route + tests</name>
  <files>services/api-gateway/app/main.py, services/api-gateway/tests/test_preflight_proxy.py</files>
  <read_first>
    - services/api-gateway/app/main.py (lines 1049-1165 — `/api/config/safety-state` fan-out — copy this shape exactly; lines 1155, 1209 — autoflake-survival local imports pattern)
    - services/api-gateway/tests/test_safety_state.py (lines 32-101 — JSONResponse mock + side_effect dispatcher; lines 104-end — test_client + proxy mocking)
    - services/api-gateway/tests/conftest.py (lines 61-64 — plain `test_client` fixture, NO auth override)
    - .planning/phases/08-pre-live-preflight/08-PATTERNS.md (lines 824-875 — copy-ready proxy code; lines 695-765 — copy-ready proxy test)
  </read_first>
  <behavior>
    - GET `/api/preflight/live-readiness` on api-gateway (port 8000) returns 200 with the trading-engine response body verbatim on success (preserving schema_version=1, overall, evaluated_at, all 6 checks).
    - When the proxy_request raises (trading-engine unreachable / 500 / timeout), the gateway returns 200 with a graceful-degradation body: schema_version=1, overall=UNKNOWN, evaluated_at=now, all 6 checks with status=UNKNOWN and detail="trading-engine unreachable".
    - **CRITICAL: never falls back to PASS on failure** — UNKNOWN is the safe default per 08-CONTEXT.md Open Question close. A test asserts this explicitly.
    - No authentication required (D-09 — same as safety-state).
  </behavior>
  <action>
    1. Locate `services/api-gateway/app/main.py` line 1166 (immediately after `get_safety_state` return; before the next route block). Insert the proxy handler per 08-PATTERNS.md lines 831-875. Use `@app.get("/api/preflight/live-readiness")`. The handler:
       - Uses local imports `from datetime import datetime, timezone as _tz` + `import json` inside the function (autoflake-survival per project memory `feedback_main_imports_autoflake.md`; mirror existing lines 1155, 1209).
       - Calls `proxy = get_proxy()`; `resp = await proxy.proxy_request(service_name="trading-engine", path="/api/preflight/live-readiness", method="GET")`.
       - On success (status 200): `return json.loads(resp.body.decode())`. (Use `.body.decode()` NOT `.json()` — `proxy.proxy_request` returns `JSONResponse`, see safety-state F-03 fix at line 1080.)
       - On any exception (including non-200): log warning, return the graceful-degradation dict with all 6 checks UNKNOWN, overall=UNKNOWN, schema_version=1, evaluated_at=now().
       - Docstring should reference D-09 (unauthenticated) and the CONTEXT.md Open Question close (never PASS on failure).

    2. Create `services/api-gateway/tests/test_preflight_proxy.py` per 08-PATTERNS.md lines 695-765. Use plain `test_client` fixture from conftest.py (NOT `admin_client` — would mask a future auth-dep regression). Tests:
       - `test_proxy_passes_through_preflight_report`: mock proxy_request to return a JSONResponse with the 6-check payload; assert response body['overall']=='PASS', etc.
       - `test_proxy_returns_unknown_when_trading_engine_unreachable`: mock proxy_request to raise `Exception("connection refused")`; assert status_code 200 (NOT 5xx), body['overall']=='UNKNOWN', all 6 checks have status=='UNKNOWN'. This is the load-bearing test for the "never fall back to PASS" decision.
       - `test_proxy_no_auth_required`: hit without auth header → 200 (asserts D-09 stays unauthenticated; auth-dep regression guard).
       - `test_proxy_returns_unknown_when_trading_engine_returns_non_200`: mock proxy_request to return JSONResponse(status_code=500, content={"error":"boom"}); response body['overall']=='UNKNOWN'.

    3. Use the `_build_response` helper from test_safety_state.py:32-40 — JSONResponse with explicit `.body = json.dumps(content).encode()` — because the handler decodes via `json.loads(resp.body.decode())`.
  </action>
  <verify>
    <automated>cd services/api-gateway &amp;&amp; docker exec crypto-bot-api-gateway pytest tests/test_preflight_proxy.py -v --tb=short 2&gt;/dev/null || pytest services/api-gateway/tests/test_preflight_proxy.py -v --tb=short</automated>
  </verify>
  <acceptance_criteria>
    - Source assertion: `grep -c "/api/preflight/live-readiness" services/api-gateway/app/main.py` returns ≥1.
    - Source assertion: `grep -c "trading-engine unreachable" services/api-gateway/app/main.py` returns ≥1 (the graceful-degradation detail string).
    - Source assertion: `grep -c "PASS" services/api-gateway/app/main.py | xargs -I{} test {} -gt 0` — well, looser check: `grep -B2 -A20 'def get_preflight_live_readiness' services/api-gateway/app/main.py | grep -c "PASS"` returns 0 — proxy MUST NOT fall back to PASS on failure. (Or assert directly: `grep -A15 'def get_preflight_live_readiness' services/api-gateway/app/main.py | grep -E "overall.*PASS"` returns 0.)
    - Source assertion: `grep -c "test_proxy_returns_unknown_when_trading_engine_unreachable" services/api-gateway/tests/test_preflight_proxy.py` returns 1.
    - Behavior assertion: `pytest services/api-gateway/tests/test_preflight_proxy.py -v` exits 0; ≥4 tests pass.
    - Behavior assertion (run-time, optional if container available): `curl -s http://localhost:8000/api/preflight/live-readiness | jq -e '.schema_version == 1 and (.checks | length) == 6'` exits 0. If api-gateway not running, record manual curl step in SUMMARY post-deploy.

    Note on api-gateway test environment (CLAUDE.md gotcha): run inside container (`docker exec crypto-bot-api-gateway pytest ...`) — host pip has fastapi 0.136 (HTTPBearer→401), container pins fastapi 0.109 (→403). Host test runs may show spurious 401-vs-403 failures on unrelated tests. The fallback in `<verify>` runs on host if the container isn't up — both should pass for these tests since the route is unauthenticated.
  </acceptance_criteria>
  <done>Proxy route added to api-gateway/app/main.py near line 1166, falls back to overall=UNKNOWN (never PASS) on trading-engine failure, ≥4 proxy tests pass with the load-bearing UNKNOWN-degradation assertion present.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| operator shell → CLI script | local trust domain; CLI reads process env or git refs only |
| network → api-gateway HTTP route | public-internet exposure (paper-mode dashboard); unauthenticated by design (D-09) |
| api-gateway → trading-engine | internal docker network; ServiceProxy uses configured base URL |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-08-02-01 | I (Info disclosure) | unauthenticated GET on api-gateway proxy route | accept | D-09 carryforward from `/api/config/safety-state`: discloses only configuration shape (PASS/FAIL/UNKNOWN + detail strings); no secrets, no balances, no positions. Same disclosure surface as safety-state, which already accepts this in production. Detail strings include env values (e.g. `max_risk_per_trade=0.03`) which are configuration, not secrets. |
| T-08-02-02 | T (Tampering) | trading-engine response surfaced verbatim by api-gateway | mitigate | Graceful-degradation path returns `overall=UNKNOWN`, never PASS, on any failure (timeout, 5xx, network error). The single most load-bearing line in the proxy — falling back to PASS would defeat the entire phase. Test `test_proxy_returns_unknown_when_trading_engine_unreachable` asserts this. Body is `json.loads(resp.body.decode())` — JSON parse rejects malformed bytes. |
| T-08-02-03 | S (Spoofing) / R (Repudiation) | unauthenticated read-only GET | accept | No state change, no logged-in user concept on this route. CSRF/XSS irrelevant on JSON-only GET. Same posture as safety-state. |
| T-08-02-04 | I (Info disclosure) | UNKNOWN-leak — operator sees that ML evidence is missing | accept | UNKNOWN-leak is by design — dashboard MUST distinguish "evidence missing" from "evidence present, gate failed" so operator knows whether Phase 9 is the blocker. Detail strings mention "Phase 9 not landed" — internal milestone naming, not a secret. |
| T-08-02-05 | I (Info disclosure) | CLI `--dry-run --target=<ref>` reads `.env.example` from arbitrary git refs | accept | `.env.example` is committed and shipped; not a secret. Operator-side use only (not exposed over HTTP). `git show` errors fail-soft to exit 2. |
| T-08-02-06 | E (Elevation) | CLI runs as the invoking user; no privileged escalation | accept | CLI is a read-only script; doesn't write to disk except stdout. |

(No HIGH-severity threats; phase ASVS L1 disposition is accept-with-mitigation per D-09 carryforward.)
</threat_model>

<verification>
- `python3 scripts/preflight_live.py --json | jq -e '.schema_version == 1 and (.checks | length) == 6'` exits 0.
- `pytest services/trading-engine/tests/test_preflight_route.py -v` — ≥3 passing tests.
- `pytest services/api-gateway/tests/test_preflight_proxy.py -v` — ≥4 passing tests (including the UNKNOWN-degradation guard).
- `grep -c "/api/preflight/live-readiness" services/api-gateway/app/main.py` returns ≥1.
- Source negative-grep: `grep -A20 'def get_preflight_live_readiness' services/api-gateway/app/main.py | grep -cE '"overall".*"PASS"'` returns 0 (proxy never falls back to PASS).
- Post-deploy (record in SUMMARY): `curl -s http://localhost:8000/api/preflight/live-readiness | jq -e '.schema_version == 1'` exits 0 once 08-03 mounts the trading-engine router.
</verification>

<success_criteria>
- CLI exits 0 on PASS, 1 on FAIL/UNKNOWN, 2 on bad args.
- CLI `--json` emits valid JSON parseable by `json.loads` and `jq`.
- CLI `--check=<name>` filter works (cap, paper_mode, etc.).
- CLI `--dry-run --target=HEAD` reads `.env.example` from git ref (uses `git show`).
- trading-engine route returns schema_version=1 with 6 checks; no auth required.
- api-gateway proxy returns trading-engine body verbatim on success; **returns overall=UNKNOWN (never PASS) on failure**.
- Both route test files use `test_client` not `admin_client` (D-09 — auth-leak guard).
- Verification post-08-03: end-to-end curl through api-gateway returns the schema.

NOTE: this plan does NOT modify `services/trading-engine/app/main.py`. The router-mount + `from app.preflight import run_all` import live in 08-03 along with the cap-check block, so the grep-gate scope stays single-file.
</success_criteria>

<output>
After completion, create `.planning/phases/08-pre-live-preflight/08-02-SUMMARY.md` capturing:
- File list + line counts.
- CLI sample output (`python3 scripts/preflight_live.py --json` redacted/snippet).
- Test counts (passed) for both `test_preflight_route.py` and `test_preflight_proxy.py`.
- Note that `services/trading-engine/app/main.py` is untouched in this plan (08-03 owns it).
- Flag any execution-time deviation from the patterns (e.g. if the gateway test had to run on host vs container, document which).
- Forward-reference: a 1-line note "curl smoke check pending 08-03 router-mount".
</output>
