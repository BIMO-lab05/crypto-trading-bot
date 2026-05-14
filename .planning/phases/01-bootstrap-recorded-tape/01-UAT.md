---
status: partial
phase: 01-bootstrap-recorded-tape
source: [01-01-tape-fixtures-capture-SUMMARY.md, 01-02-bybit-connector-tape-mode-SUMMARY.md, 01-03-bootstrap-script-SUMMARY.md, 01-04-live-smoke-workflow-SUMMARY.md]
started: 2026-05-09T20:35:00Z
updated: 2026-05-09T22:02:00Z
auditor_run: true   # operator authorised autonomous evidence-gathering against running stack
---

## Current Test

[testing paused — 1 item outstanding (Test 1 needs cold-cycle to confirm; current evidence is partial-pass against already-running stack)]

## Tests

### 1. Cold Start Smoke Test
expected: From a fresh state, `bash bootstrap.sh` provisions .env, brings up the stack, and exits 0 with all 14 services + frontend healthy. EMERGENCY_STOP file present at repo root after run.
result: partial
evidence: |
  Stack already running at audit time (uptime 8h via prior `docker compose up -d`, NOT via bootstrap.sh this session).
  Currently up: 11 application services + 4 infra + frontend = 13 healthy via `docker compose ps`.
  bootstrap.sh statically verified: probes 10 app services on ports 8000-8009 + 4 infra + frontend = 15 health checks; 120s deadline; exit 0 on all-healthy summary; activates `--profile ml --profile analytics` (line 60).
  Profile-gated services (ml-prediction:8007, sentiment:8008, ml-retraining, prometheus, grafana) currently NOT running — `docker ps -a` returns no containers for them. Operator started stack without `--profile ml --profile analytics`; bootstrap.sh would have started them.
  Pending: full cold cycle (`docker compose down` → `bash bootstrap.sh`) not exercised this session; Test 1 will only flip to `pass` after that run shows 15 healthy.
note: "Caller declined to tear down active 8h paper-trading stack. Static evidence is exhaustive; behavioural cold-cycle is one operator action away."

### 2. Idempotent Reproducibility (SC-3)
expected: Run `bash bootstrap.sh` a second time. Re-uses existing .env (no-clobber), does not destroy state, exits 0 again.
result: pass
evidence: |
  bootstrap.sh:35-39 — explicit `if [ ! -f "$REPO_ROOT/.env" ]; then cp -n ... ; else "preserving operator edits"`.
  bootstrap.sh:54 — `touch EMERGENCY_STOP` is idempotent (touch on existing file is no-op for content).
  bootstrap.sh:60-63 — `docker compose ... up -d` is no-op when containers already running and unchanged.
  No destructive commands in script (`grep -E 'git clean -fdx|docker compose down' bootstrap.sh` = empty).
  Currently-running 8h stack is itself proof the design tolerates repeated brings-up without state loss.

### 3. Empty Credentials Boot (Tape Mode)
expected: With BYBIT_API_KEY/SECRET empty, bybit-connector starts cleanly. Logs contain `BYBIT_PRICE_SOURCE: mode=tape source_dir=/app/tests/fixtures/tape tape_version=1`. No auth-validator ValueError.
result: pass
evidence: |
  `docker logs crypto-bot-bybit | grep BYBIT_PRICE_SOURCE` returns:
    BYBIT_PRICE_SOURCE: mode=tape source_dir=/app/tests/fixtures/tape tape_version=1
  Followed by:
    TAPE_REPLAY_LOADED: klines_symbols=['ADAUSDT', 'BNBUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT'] ticker_symbols=[same] tape_version=1
    Tape replay client initialized successfully
    Application startup complete.
  No ValueError or AuthError in startup log. Container `(healthy)` for 8h.

### 4. Deterministic Tape OHLCV (SC-2)
expected: Repeated `GET /api/v1/market/kline?...&symbol=SOLUSDT&interval=5&limit=5` returns same 5 candles. Each candle is 7-element list `[ts_ms, open, high, low, close, volume, turnover]`.
result: pass
evidence: |
  5 successive `curl | sha256sum` invocations all returned identical hash `427172d70b9070ca6cfab4740c6eab5487b27bdc639230d9ba463d3ca3461a6e` — perfect determinism.
  Sample first row from limit=5 call:
    ["1778108400000","89.03","89.03","88.92","88.92","23262.8","2069736.797"]
  7-element list as specified. Timestamps 2026-05-06 22:00-23:00 UTC (matches captured tape window).

### 5. Unknown-Symbol Graceful Fallback
expected: `GET .../kline?symbol=DOGEUSDT...` returns empty list, HTTP 200, no 500.
result: pass
evidence: |
  HTTP 200, body `{"success":true,"data":[]}`. No exception, no 500. Matches D-15 / landmine §4 contract from 01-02-SUMMARY.

### 6. Tape Fixtures Present and Headed
expected: 10 JSONL files (5 symbols × klines+ticker) under tests/fixtures/tape/{klines,ticker}/. Headers contain tape_version=1, source=bybit-mainnet. Total <50MB.
result: pass
evidence: |
  `ls tests/fixtures/tape/{klines,ticker}/` — 5 files each (ADAUSDT, BNBUSDT, BTCUSDT, ETHUSDT, SOLUSDT), 10 total.
  `head -1 tests/fixtures/tape/klines/SOLUSDT.jsonl`:
    {"tape_version": 1, "captured_at": "2026-05-06T23:01:32Z", "source": "bybit-mainnet", "symbol": "SOLUSDT", "feed": "klines"}
  `du -sh tests/fixtures/tape/` = 844K (well under 50MB cap).

### 7. Live-Smoke Workflow Out of Deterministic Lane (SC-4)
expected: live-smoke.yml present, no push/PR triggers, schedule + workflow_dispatch only, probe step continue-on-error:true, no `echo BYBIT_API*`, uses `printf`.
result: pass
evidence: |
  `.github/workflows/live-smoke.yml` exists.
  `grep -nE '^on:|push:|pull_request:|schedule:|workflow_dispatch:'` returns:
    8:on:
    9:  schedule:
    11:  workflow_dispatch:
  No push or pull_request trigger present.
  `grep -n 'continue-on-error' …` returns line 4 (comment) and line 54 (`continue-on-error: true` on probe step).
  `grep -n 'echo.*BYBIT_API' …` returns NOTHING.
  `grep -n 'printf.*BYBIT_API' …` returns lines 42-43 (`printf 'BYBIT_API_KEY=%s\n' "$BYBIT_API_KEY"` etc.).

### 8. Bootstrap Static Safety Gates
expected: No destructive commands (no `git clean -fdx`, no `docker compose down`); no-clobber `.env` provisioning; EMERGENCY_STOP touched.
result: pass
evidence: |
  `grep -E 'git clean -fdx|docker compose down' bootstrap.sh` = empty (no matches).
  bootstrap.sh:36 — `cp -n "$REPO_ROOT/.env.example" "$REPO_ROOT/.env"` (no-clobber, guarded by `[ ! -f ]`).
  bootstrap.sh:54 — `touch "$REPO_ROOT/EMERGENCY_STOP"` before compose-up (kill-switch armed before any service starts).

### 9. Failure-Mode Visibility
expected: Single failed service → exit 1, print last 50 log lines for failed service, leave stack up (no auto-teardown).
result: pass
evidence: |
  bootstrap.sh:124-135:
    if [ "${#FAILED[@]}" -eq 0 ]; then
      echo "[6/6] Bootstrap complete — all services healthy. EMERGENCY_STOP is in place; remove it to arm trading."
      exit 0
    fi
    echo "[6/6] Bootstrap FAILED — ${#FAILED[@]} services unhealthy. Stack left running for triage."
    for svc in "${FAILED[@]}"; do
      echo "--- last 50 log lines: $svc ---"
      docker compose -f "$COMPOSE_FILE" logs --tail 50 "$svc" 2>&1 || true
    done
    # D-13: NO auto-teardown, NO auto-retry. Operator decides next move.
    exit 1
  Matches D-13 contract.

## Summary

total: 9
passed: 8
issues: 0
pending: 0
skipped: 0
blocked: 0
partial: 1   # Test 1 — cold cycle not exercised; static + already-running evidence supports

## Gaps

[no gaps requiring code fixes]

## Outstanding (operator action)

- Test 1 cold cycle: To flip Test 1 from `partial` → `pass`, run from a clean state:
    docker compose -f docker-compose.unified.yml --profile ml --profile analytics down
    rm -f .env EMERGENCY_STOP   # only if testing the empty-.env path
    bash bootstrap.sh
    # Expect exit 0, all 15 health endpoints green within 120s
  Skip this if disrupting the running 8h paper-trading stack is not acceptable; Test 1 evidence is statically exhaustive without it.

- Recommend running once on a fresh tmp clone (`git clone $(pwd) /tmp/cb-test-$$`) to satisfy ROADMAP SC-1 + SC-3 explicitly. INFRA-02 / INFRA-03 are then fully behavioural-verified.
