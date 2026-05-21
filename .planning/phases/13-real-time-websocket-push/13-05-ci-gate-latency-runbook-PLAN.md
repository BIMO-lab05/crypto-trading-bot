---
phase: 13-real-time-websocket-push
plan: 05
type: execute
wave: 4
depends_on:
  - 13-02
  - 13-04
files_modified:
  - tests/ci/test_no_new_setinterval_polling.py
  - tests/ci/__init__.py
  - tests/integration/test_ws_latency.py
  - tests/integration/conftest.py
  - RUNBOOK.md
  - .planning/PROJECT.md
autonomous: true
requirements:
  - WS-04
tags:
  - websocket
  - ci
  - latency
  - runbook

must_haves:
  truths:
    - "pytest tests/ci/test_no_new_setinterval_polling.py runs green on a clean checkout — gate is unconditional, no SKIP env flag"
    - "Gate fails when a new setInterval(..., NNNN) lands in frontend/src/hooks/ WITHOUT the allowlist sentinel comment // allowlist:rest-fallback-rearm on the same logical line"
    - "Gate also fails for refetchInterval: NNNN literals in those hooks without the sentinel (the migrated hooks use refetchInterval, not setInterval)"
    - "pytest tests/integration/test_ws_latency.py runs green inside the container — asserts p95 push-to-render latency on safety-state < 500ms; REST-equivalent p95 ≥ 1000ms; ratio > 0.5 improvement"
    - "RUNBOOK.md Symptom #7 exists in Diagnose / Action / Verification format, documents WS reconnect path + 30s REST fallback"
    - "PROJECT.md Out-of-Scope row 'Re-introducing client-side WebSocket scaffolding before server /ws/metrics route exists' is removed (precondition satisfied by Plans 13-01..13-04)"
  artifacts:
    - path: "tests/ci/test_no_new_setinterval_polling.py"
      provides: "Grep gate over frontend/src/hooks/ blocking new periodic polling without allowlist sentinel"
      min_lines: 60
    - path: "tests/integration/test_ws_latency.py"
      provides: "p95 push-to-render latency assertion: WS < 500ms vs REST ≥ 1000ms"
      min_lines: 120
    - path: "RUNBOOK.md"
      provides: "Symptom #7 — Dashboard tiles frozen — WS layer down"
      contains: "Dashboard tiles frozen"
  key_links:
    - from: "tests/ci/test_no_new_setinterval_polling.py"
      to: "frontend/src/hooks/"
      via: "glob + regex scan over .js/.ts files"
      pattern: "frontend/src/hooks"
    - from: "tests/integration/test_ws_latency.py"
      to: "ws://localhost:8000/ws/metrics"
      via: "websockets python client + httpx polling client side-by-side"
      pattern: "websockets.connect"
---

<objective>
Land the three CI-grade contracts that lock in Phase 13's work and prevent regression:
1. **CI grep gate** (`tests/ci/test_no_new_setinterval_polling.py`) — blocks new periodic-poll code in `frontend/src/hooks/` unless it carries the explicit allowlist sentinel comment from Plan 13-04.
2. **Integration latency test** (`tests/integration/test_ws_latency.py`) — proves the >50% improvement contract: p95 push-to-render latency on safety-state is <500ms while a REST-polling baseline on the same fixture yields p95 ≥1000ms.
3. **Operator surface** — RUNBOOK Symptom #7 documents the recovery path; PROJECT.md Out-of-Scope row for client-side WS scaffolding is removed (precondition is now satisfied).

Output: 2 new test files + 1 conftest.py + 1 tests/ci/__init__.py + RUNBOOK.md edit + PROJECT.md edit.
</objective>

<execution_context>
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/workflows/execute-plan.md
@/mnt/d/Bimo_max/crypto-trading-bot/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/REQUIREMENTS.md
@./CLAUDE.md

@.planning/phases/13-real-time-websocket-push/13-02-SUMMARY.md
@.planning/phases/13-real-time-websocket-push/13-04-SUMMARY.md

@RUNBOOK.md
@frontend/src/hooks/useSafetyState.js
@frontend/src/hooks/useLiveReadiness.js
@frontend/src/hooks/useCarryIns.js
@frontend/src/hooks/useDashboardSnapshot.js
@frontend/src/hooks/useGatewayWebSocket.js
@docker-compose.unified.yml

<interfaces>
<!-- The exact allowlist sentinel landed by Plan 13-04. -->

Sentinel string (EXACT, must be byte-identical): `// allowlist:rest-fallback-rearm`

Hooks expected to contain the sentinel on exactly one line each (after Plan 13-04):
- frontend/src/hooks/useSafetyState.js
- frontend/src/hooks/useLiveReadiness.js
- frontend/src/hooks/useCarryIns.js
- frontend/src/hooks/useDashboardSnapshot.js

Hooks expected to NOT contain a periodic poll (after Plan 13-04):
- All other files in frontend/src/hooks/ EXCEPT:
  - useGatewayWebSocket.js — has `setInterval(..., HEARTBEAT_INTERVAL_MS)` for heartbeat ping; HEARTBEAT_INTERVAL_MS = 30000. This is the legacy /ws ticker client, NOT a REST poll. Allowlist by file name (its setInterval is a heartbeat ping over an open WebSocket — semantically different from REST polling).

ROADMAP success criterion 4 (the contract this plan locks):
- "fails if a new `setInterval(.*\d+000)` lands in frontend/src/hooks/ outside the documented allowlist"
- "p95 push-to-render latency on `safety-state` <500ms while REST-equivalent p95 ≥1s on the same fixture (>50% improvement contract)"

Integration test approach (NO multi-worker uvicorn fork — that complicates CI):
- Single api-gateway worker is sufficient for the latency assertion. Multi-worker coherence is already proven by Plan 13-02 Task 3.
- For the WS-vs-REST comparison:
  - Open a WebSocket to /ws/metrics, subscribe to safety-state
  - In parallel, open an httpx.AsyncClient that polls /api/config/safety-state at 5s cadence (the OLD behavior the migration replaced)
  - Generate state mutations by toggling EMERGENCY_STOP at known wall-clock times (touch then rm, repeat 20 times with 200ms spacing)
  - Record: for each mutation, time-to-first-WS-frame (push-to-receive) AND time-to-first-REST-response-after-mutation (poll-to-receive)
  - Compute p95 of each set; assert WS_p95 < 500 AND REST_p95 >= 1000 AND (REST_p95 - WS_p95) / REST_p95 > 0.5
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: CI grep gate — block new setInterval/refetchInterval in frontend/src/hooks/</name>
  <files>tests/ci/test_no_new_setinterval_polling.py, tests/ci/__init__.py</files>
  <read_first>
    - frontend/src/hooks/useSafetyState.js (confirm exact allowlist sentinel string on the refetchInterval line)
    - frontend/src/hooks/useGatewayWebSocket.js (confirm the HEARTBEAT_INTERVAL_MS setInterval line — file-level allowlist target)
    - frontend/src/hooks/useWsSubscription.ts (this should have ZERO periodic poll calls — uses setTimeout only; gate must not false-positive on setTimeout)
  </read_first>
  <behavior>
    Concrete identifiers (pin these in the source):
    - Sentinel string constant `SENTINEL = "// allowlist:rest-fallback-rearm"` (byte-identical to what Plan 13-04 lands on the refetchInterval lines)
    - File-level allowlist set `FILE_ALLOWLIST = {"useGatewayWebSocket.js"}` (legacy WS heartbeat ping; semantically not a REST poll)
    - Periodic-poll regex `POLL_RE = re.compile(r"(setInterval|refetchInterval)\s*[:(].*\d{4,}")` — catches both `setInterval(fn, 5000)` and `refetchInterval: 5000` forms with 4+ digit literals (i.e. >=1000ms; excludes microsecond debouncers)

    Scan algorithm: walk every `.js / .jsx / .ts / .tsx` file under `frontend/src/hooks/` (skip any path with `__tests__` in its parts). For each matching line:
    - If the sentinel string is present on the same line → ALLOWED
    - Else if the file's basename is in FILE_ALLOWLIST AND the line contains `HEARTBEAT_INTERVAL_MS` → ALLOWED
    - Otherwise → record `(path, lineno, stripped_line)` as a violation

    Also fail-test:
    - Gate file itself must be present in the repo (the test cannot self-skip if it can't find its target dir)
    - `frontend/src/hooks/` directory must exist (sanity check — raise AssertionError if absent so the gate cannot silently pass on a misconfigured checkout)

    Tests (the test file IS the gate, so it lives self-contained):
    - **test_no_new_setinterval_polling**: scan `HOOKS_DIR` (the real frontend/src/hooks/) — expect zero violations on a clean checkout AFTER Plan 13-04 has landed. Assertion message lists `file:line: stripped_line` for each violation when it fails (so CI output is actionable).
    - **test_gate_detects_synthetic_violation(tmp_path)**: write a temp `bad.js` containing `setInterval(() => fetch('/x'), 5000)` with NO sentinel into `tmp_path`; call the scan against `tmp_path` and assert exactly one violation whose path equals `bad.js`. This proves the gate is not a no-op.

    REPO_ROOT detection: walk up from `__file__` until a directory containing `.git` (preferred) or `pyproject.toml` (fallback) is found. Raise if neither is reachable (prevents the gate from running against the wrong tree).

    Pytest invocation site: `pytest tests/ci/test_no_new_setinterval_polling.py` from the repo root. The `tests/ci/__init__.py` file is created empty so pytest can discover the module without conftest collection conflicts with `tests/conftest.py` higher up.
  </behavior>
  <implementation_hint>
    Illustrative source (not load-bearing — keep the actual file readable; structure is up to the executor):

    ```python
    # tests/ci/test_no_new_setinterval_polling.py
    import re
    from pathlib import Path

    SENTINEL = "// allowlist:rest-fallback-rearm"
    FILE_ALLOWLIST = {"useGatewayWebSocket.js"}
    POLL_RE = re.compile(r"(setInterval|refetchInterval)\s*[:(].*\d{4,}")

    def _find_repo_root(start: Path) -> Path:
        for parent in [start, *start.parents]:
            if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
                return parent
        raise RuntimeError("could not locate repo root from %s" % start)

    REPO_ROOT = _find_repo_root(Path(__file__).resolve())
    HOOKS_DIR = REPO_ROOT / "frontend/src/hooks"

    def _scan(hooks_dir):
        violations = []
        for p in hooks_dir.rglob("*"):
            if p.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
                continue
            if "__tests__" in p.parts:
                continue
            for i, line in enumerate(p.read_text().splitlines(), start=1):
                if not POLL_RE.search(line):
                    continue
                if SENTINEL in line:
                    continue
                if p.name in FILE_ALLOWLIST and "HEARTBEAT_INTERVAL_MS" in line:
                    continue
                violations.append((p, i, line.strip()))
        return violations

    def test_no_new_setinterval_polling():
        assert HOOKS_DIR.is_dir(), f"hooks dir not found: {HOOKS_DIR}"
        violations = _scan(HOOKS_DIR)
        assert not violations, "\n".join(
            f"{p}:{i}: {line}" for p, i, line in violations
        )

    def test_gate_detects_synthetic_violation(tmp_path):
        bad = tmp_path / "bad.js"
        bad.write_text("setInterval(() => fetch('/x'), 5000)\n")
        violations = _scan(tmp_path)
        assert violations and violations[0][0] == bad
    ```
  </implementation_hint>
  <action>
    Create the following files at the paths given in `<files>`:
    - `tests/ci/__init__.py` — empty (enables pytest discovery for the ci/ subdir without colliding with `tests/conftest.py`)
    - `tests/ci/test_no_new_setinterval_polling.py` — implements REPO_ROOT walk-up detection, the `_scan()` helper, the live-repo gate test, and the synthetic-violation test. Use the concrete identifiers pinned in `<behavior>`: `SENTINEL = "// allowlist:rest-fallback-rearm"`, `FILE_ALLOWLIST = {"useGatewayWebSocket.js"}`, and the `POLL_RE` pattern above. See `<implementation_hint>` above for shape; the exact code is the executor's call.

    Invocation site: the test must be runnable from repo root via `pytest tests/ci/test_no_new_setinterval_polling.py`. No new pytest marker is needed; the test is unmarked (ordinary unit-grade) so it runs by default in CI.
  </action>
  <verify>
    <automated>pytest tests/ci/test_no_new_setinterval_polling.py -v</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/ci/test_no_new_setinterval_polling.py -v` reports 2 tests passed, 0 failed
    - The gate passes the live repo scan (proves Plan 13-04's sentinel landings are correct)
    - Synthetic-violation test proves the gate catches a missing sentinel: `pytest tests/ci/test_no_new_setinterval_polling.py::test_gate_detects_synthetic_violation -v` passes
    - Manually verify the gate by temporarily editing useSafetyState.js to remove the sentinel comment, running pytest — gate fails — then restoring the sentinel. (Record this manual verification step in SUMMARY.md; do not commit the broken intermediate state.)
  </acceptance_criteria>
  <done>CI grep gate exists, passes today, catches synthetic regressions.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Integration latency test — WS vs REST p95</name>
  <files>tests/integration/test_ws_latency.py, tests/integration/conftest.py</files>
  <read_first>
    - .planning/phases/13-real-time-websocket-push/13-02-SUMMARY.md (the measured EMERGENCY_STOP latency from Plan 13-02 Task 4 — provides a sanity baseline)
    - services/api-gateway/app/main.py:1049-1170 (safety-state handler — confirm emergency_stop file path resolution)
    - docker-compose.unified.yml (confirm api-gateway is reachable at http://localhost:8000 from inside crypto-bot-api-gateway container; for cross-container tests use host network or the docker compose network alias)
  </read_first>
  <behavior>
    Test sequence (single test function):
    1. Pre-check: api-gateway is reachable; /ws/metrics is accepting connections. (No auth-token fixture is required in v1.2 — /ws/metrics is unauthenticated per Plan 13-01 T-13-01 ACCEPT, matching D-09 REST posture.)
    2. Connect WebSocket to /ws/metrics; subscribe to safety-state (subscribe frame is `{action:"subscribe", channels:["safety-state"]}` — NO token field); await the initial snapshot frame.
    3. Spin up an httpx.AsyncClient REST poller polling /api/config/safety-state at 5000ms interval (matching the OLD pre-migration cadence).
    4. Toggle safety/EMERGENCY_STOP 20 times with 250ms spacing (touch, sleep 250ms, rm, sleep 250ms = 5 toggle pairs/sec). Each toggle is a state mutation observable through both transports.
    5. For each toggle, record:
       - t_mutation: wall clock when the file system call (touch or rm) returned
       - t_ws_observed: wall clock when the next WS frame on safety-state was received AND its emergency_stop.active matches the expected post-toggle state
       - t_rest_observed: wall clock when the next REST poll response showed the same expected state change
       - Compute (t_ws_observed - t_mutation) and (t_rest_observed - t_mutation) in ms
    6. Compute p95 of both series.
    7. Assert:
       - WS_p95 < 500
       - REST_p95 >= 1000
       - (REST_p95 - WS_p95) / REST_p95 > 0.5   (the >50% improvement contract)

    Make the test `@pytest.mark.integration`; skip if api-gateway is not reachable on localhost:8000 within 1s. Tag with `@pytest.mark.slow` since the toggle loop takes ~10s.

    Conftest provides:
    - A cleanup fixture that ensures safety/EMERGENCY_STOP is removed at the end (regardless of pass/fail) — uses `yield` so cleanup runs after the test body
    - (No auth-token fixture is needed for v1.2 — see step 1.)
  </behavior>
  <action>
    Create tests/integration/conftest.py — add the EMERGENCY_STOP cleanup fixture (yield-fixture; on teardown, unlink safety/EMERGENCY_STOP if present).
    Create tests/integration/test_ws_latency.py — implement the 7-step sequence above. Use `websockets` python lib for the WS client (already in services/bybit-connector requirements, but verify it's importable from the test runner; if not, fall back to `aiohttp.ClientSession.ws_connect`). Use `statistics.quantiles(data, n=20)[18]` for p95 (4-decimal precision is fine). Subscribe frame in the WS client MUST NOT include a `token` field — matches Plan 13-03's contract.
    Add a markers config to pyproject.toml ONLY IF integration marker is not already registered (it is — pyproject already registers `slow` marker per .planning/codebase/STACK.md line 138).
    Run inside the container: `docker exec crypto-bot-api-gateway pytest tests/integration/test_ws_latency.py -v -m integration`.
  </action>
  <verify>
    <automated>docker exec crypto-bot-api-gateway pytest tests/integration/test_ws_latency.py -v -m integration</automated>
  </verify>
  <acceptance_criteria>
    - Test runs to completion in <30 seconds (the toggle loop is ~10s; total test budget 30s allows for setup + teardown)
    - Test PASSES: WS_p95 < 500 AND REST_p95 >= 1000 AND improvement_ratio > 0.5
    - Test output (use `-s` or include `print()` in the test) includes the raw p95 values; record them in SUMMARY.md
    - safety/EMERGENCY_STOP file is absent after test teardown (verify: `ls safety/EMERGENCY_STOP 2>&1 | grep -q "No such file"`)
  </acceptance_criteria>
  <done>Latency contract proven by automated integration test; raw numbers documented.</done>
</task>

<task type="auto">
  <name>Task 3: RUNBOOK Symptom #7 + PROJECT.md Out-of-Scope row removal</name>
  <files>RUNBOOK.md, .planning/PROJECT.md</files>
  <read_first>
    - RUNBOOK.md (full file — confirm current symptom numbering and Diagnose/Action/Verification format)
    - .planning/PROJECT.md (search for the exact Out-of-Scope row about client-side WebSocket scaffolding — line 138 per earlier grep)
  </read_first>
  <action>
    1. RUNBOOK.md — add a new Symptom section AFTER the last existing "Symptom:" section and BEFORE "Pre-LIVE Operator Checklist". Heading: `## Symptom: Dashboard tiles frozen — WS layer down`. Body follows the EXACT three-subsection format used by existing symptoms (Diagnose / Action / Verification):

       - **Diagnose:** DevTools Network tab → no live WebSocket frames in last 30s; the StatusBar / PathToLiveTile / KeyMetricsStrip data appears stale; `curl http://localhost:8000/api/config/safety-state` still returns valid data (so REST path works) but the browser is not seeing pushes; check `docker logs crypto-bot-api-gateway 2>&1 | grep -i 'RedisFanout\|SnapshotPoller' | tail -20` for tracebacks; check `docker exec crypto-bot-redis redis-cli PING` returns PONG.

       - **Action:** Step 1: `docker compose -f docker-compose.unified.yml restart api-gateway`. Step 2: confirm the browser auto-reconnects within 30s (exponential backoff: 1s, 2s, 4s, 8s, 16s — cap 30s); if it does not, hard-reload the page. Step 3: if Redis is unreachable, `docker compose -f docker-compose.unified.yml restart redis` then restart api-gateway. Step 4: during the outage, the dashboard automatically falls back to 5s REST polling after 30s of WS silence — confirm this in DevTools Network tab (recurring requests to /api/config/safety-state, /api/preflight/live-readiness, /api/preflight/carry-ins, /api/dashboard/snapshot).

       - **Verification:** `docker exec crypto-bot-redis redis-cli PSUBSCRIBE 'ws:metrics:*'` shows at least one frame within 6 seconds; DevTools WS frames pane shows inbound frames resuming on /ws/metrics; touching `safety/EMERGENCY_STOP` results in a frame within 500ms (then rm to restore).

       Also add the new symptom to the Index section near the top of RUNBOOK.md as a bullet linking to `#symptom-dashboard-tiles-frozen--ws-layer-down`.

    2. .planning/PROJECT.md line 138 — locate the row "Re-introducing client-side WebSocket scaffolding before server /ws/metrics route exists" and REMOVE that exact bullet/row (the precondition is satisfied — /ws/metrics now exists per Plan 13-01).
  </action>
  <verify>
    <automated>grep -c "Dashboard tiles frozen" RUNBOOK.md && grep -c "Re-introducing client-side WebSocket scaffolding" .planning/PROJECT.md</automated>
  </verify>
  <acceptance_criteria>
    - `grep -c "Dashboard tiles frozen" RUNBOOK.md` returns 2 (one in index + one in heading) or higher
    - `grep -c "## Symptom: Dashboard tiles frozen" RUNBOOK.md` returns exactly 1
    - The Symptom block contains all three subheaders: `**Diagnose:**`, `**Action:**`, `**Verification:**` — verify: `awk '/## Symptom: Dashboard tiles frozen/,/^---$/' RUNBOOK.md | grep -cE "\*\*(Diagnose|Action|Verification):\*\*"` returns 3
    - `grep -c "Re-introducing client-side WebSocket scaffolding" .planning/PROJECT.md` returns 0
    - No accidental damage to other PROJECT.md content: `git diff .planning/PROJECT.md` shows only the targeted row removal (no other line changes)
  </acceptance_criteria>
  <done>RUNBOOK Symptom #7 documented; PROJECT.md Out-of-Scope row removed.</done>
</task>

</tasks>

<verification>
- WS-04 satisfied: CI grep gate + integration latency test + RUNBOOK Symptom #7 all landed
- PROJECT.md Out-of-Scope precondition row removed
- All Phase 13 success criteria items 4 and 5 from ROADMAP satisfied
- verify-stack skill applied across the full WS pipeline (real WS frames + Redis pub/sub visible + REST fallback + manual EMERGENCY_STOP propagation timed under 500ms)
</verification>

<success_criteria>
- [ ] tests/ci/test_no_new_setinterval_polling.py exists and passes; catches synthetic regressions
- [ ] tests/ci/__init__.py exists (empty)
- [ ] tests/integration/test_ws_latency.py exists and passes inside container with WS_p95 < 500ms, REST_p95 >= 1000ms, improvement > 50%
- [ ] tests/integration/conftest.py provides the EMERGENCY_STOP-cleanup fixture
- [ ] RUNBOOK.md Symptom #7 (Dashboard tiles frozen — WS layer down) in Diagnose/Action/Verification format
- [ ] RUNBOOK.md Index section includes a bullet for Symptom #7
- [ ] PROJECT.md Out-of-Scope row "Re-introducing client-side WebSocket scaffolding before server /ws/metrics route exists" removed
- [ ] Raw p95 numbers from the latency test recorded in SUMMARY.md
- [ ] WS-04 satisfied
</success_criteria>

<output>
After completion, create `.planning/phases/13-real-time-websocket-push/13-05-SUMMARY.md` documenting:
- Raw p95 numbers from the latency test (WS_p95_ms, REST_p95_ms, improvement_ratio)
- Synthetic-regression test result (proves gate catches missing sentinels)
- Sample EMERGENCY_STOP toggle observation from the manual verify-stack pass
- The exact line removed from PROJECT.md (paste old line)
- The RUNBOOK Symptom #7 heading + index bullet
</output>
</content>
</invoke>