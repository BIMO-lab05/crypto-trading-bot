---
plan: 01-03-bootstrap-script
phase: 01-bootstrap-recorded-tape
status: awaiting-checkpoint
executed_by: worktree-agent-aed9e02f02e9c98e9
date: 2026-05-07
commits:
  - 6ad4533  feat(env): add MARKET_DATA_SOURCE and LIVE_TRADING_ACK to .env.example
  - 391ca7a  feat(compose): wire bybit-connector to MARKET_DATA_SOURCE + tape fixtures mount
  - 728495b  feat(bootstrap): add bootstrap.sh — fresh-clone tape boot in 6 steps
---

# Plan 01-03 Summary: Bootstrap Script

## Status: AWAITING CHECKPOINT

Tasks 1, 2, 3 completed and committed. Task 4 is a `checkpoint:human-verify` gate (blocking) — requires a Docker daemon, WSL2, and a fresh clone. Cannot be automated in this worktree. See DEFERRED-TO-OPERATOR section below.

---

## Tasks Completed

### Task 1 — `.env.example` (DONE)
**Commit:** `6ad4533`

Appended two new keys to `.env.example` (additive-only; existing keys untouched; no real credentials):

```
MARKET_DATA_SOURCE=tape
LIVE_TRADING_ACK=
```

Verification gates passed:
- `grep -q '^MARKET_DATA_SOURCE=tape' .env.example` ✓
- `grep -q '^LIVE_TRADING_ACK=' .env.example` ✓
- No real API key value added ✓

---

### Task 2 — `docker-compose.unified.yml` bybit-connector block (DONE)
**Commit:** `391ca7a`

Extended the `bybit-connector:` service block with:

**Environment additions (after `BYBIT_TESTNET`):**
```yaml
      - MARKET_DATA_SOURCE=${MARKET_DATA_SOURCE:-tape}
      - TAPE_FIXTURES_PATH=/app/tests/fixtures/tape
```

**Volume addition (after logs bind-mount):**
```yaml
      # Tape fixtures for MARKET_DATA_SOURCE=tape mode (D-15). Read-only — never mutated by the connector.
      - ./tests/fixtures/tape:/app/tests/fixtures/tape:ro
```

Verification gates passed:
- `MARKET_DATA_SOURCE=${MARKET_DATA_SOURCE:-tape}` in bybit-connector block ✓
- `TAPE_FIXTURES_PATH=/app/tests/fixtures/tape` in bybit-connector block ✓
- `tests/fixtures/tape:/app/tests/fixtures/tape:ro` volume present ✓
- `python3 -c "import yaml; yaml.safe_load(open('docker-compose.unified.yml'))"` exits 0 ✓
- No other service blocks modified ✓

---

### Task 3 — `bootstrap.sh` (DONE, mode 100755)
**Commit:** `728495b`

Created `bootstrap.sh` at repo root (executable, `chmod +x`, git mode 100755). Follows the PLAN.md skeleton exactly.

**Six-step flow:**
1. `[1/6]` Provision `.env` via `cp -n .env.example .env` (no-clobber)
2. `[2/6]` `DOCKER_BUILDKIT=0` on Linux/WSL2 (CLAUDE.md buildkit-hang gotcha)
3. `[3/6]` `touch "$REPO_ROOT/EMERGENCY_STOP"` (D-11: before compose up to prevent race)
4. `[4/6]` `docker compose -f docker-compose.unified.yml up -d [--build]`
5. `[5/6]` Health probe: 10 application services + 4 infra (postgres, timescaledb, redis, rabbitmq) + frontend (120s timeout, D-12 pattern)
6. `[6/6]` Summary: exit 0 on all healthy; on failure — last 50 log lines per failed service + exit 1, stack left up (D-13)

**All verification gates passed:**
- `bash -n bootstrap.sh` exits 0 ✓
- `grep -q 'docker-compose.unified.yml' bootstrap.sh` ✓
- `grep -q 'cp -n' bootstrap.sh` ✓
- `grep -q 'EMERGENCY_STOP' bootstrap.sh` ✓
- `! grep -q 'git clean' bootstrap.sh` ✓
- `! grep -E 'echo.*\$BYBIT_(API_KEY|API_SECRET)' bootstrap.sh` ✓
- `! grep -E 'docker compose.*down' bootstrap.sh` ✓
- `grep -q 'declare -A SERVICES' bootstrap.sh` ✓
- `[ -x bootstrap.sh ]` ✓ (git mode 100755)
- `grep -q 'DOCKER_BUILDKIT=0' bootstrap.sh` ✓

---

## Task 4 — DEFERRED-TO-OPERATOR

**Task:** Operator verifies bootstrap-against-fresh-clone (must-have: 15 services healthy + idempotent re-run)

**Reason for deferral:** This is a `checkpoint:human-verify` gate (blocking). It requires:
- Docker daemon running (Docker Desktop on WSL2)
- Fresh clone in a tmp directory
- Manual inspection of container logs and curl responses

Automated syntax + grep gates and YAML validity were verified above. End-to-end runtime verification requires the operator to run the following 8-step procedure.

---

### DEFERRED-TO-OPERATOR: 8-Step Verification Block

*Copied verbatim from 01-03-bootstrap-script-PLAN.md Task 4 `<how-to-verify>` section.*

On the operator's WSL2 box with Docker Desktop running.

**Timing:** `bootstrap.sh` self-terminates at the health-probe deadline (~120s) — if it has not returned by then, treat it as a FAILURE (not a hang). Per D-13 the script never auto-retries; on timeout, exit non-zero with last 50 log lines per failed service and leave the stack up for `docker logs` post-mortem.


1. Make a fresh tmp clone (per PROJECT.md Constraints — bootstrap-tests run against fresh clone, not working tree):
   ```
   cd /tmp && rm -rf crypto-bot-bootstrap-test && \
     git clone /mnt/d/Bimo_max/crypto-trading-bot crypto-bot-bootstrap-test && \
     cd crypto-bot-bootstrap-test
   ```

2. Run bootstrap.sh against an EMPTY .env (test the fresh-clone path):
   ```
   rm -f .env  # ensure no .env from working tree carried over
   bash bootstrap.sh 2>&1 | tee bootstrap-run-1.log
   echo "Exit: $?"
   ```
   EXPECT: exit 0; log shows `[6/6] Bootstrap complete — all services healthy.`; .env created (with MARKET_DATA_SOURCE=tape); EMERGENCY_STOP file present at repo root.

3. Run a SECOND time WITHOUT teardown (idempotent check — must-have):
   ```
   bash bootstrap.sh 2>&1 | tee bootstrap-run-2.log
   echo "Exit: $?"
   ```
   EXPECT: exit 0; log shows `[1/6] .env already exists — preserving operator edits`.

4. Verify tape mode is actually active (no live API call) by grepping the bybit-connector startup log:
   ```
   docker compose -f docker-compose.unified.yml logs bybit-connector | grep BYBIT_PRICE_SOURCE
   ```
   EXPECT: at least one line `BYBIT_PRICE_SOURCE: mode=tape source_dir=/app/tests/fixtures/tape tape_version=1`. NO `mode=live` line.

5. Confirm a SOLUSDT ticker request via the connector returns tape data:
   ```
   curl -s 'http://localhost:8001/api/v1/market/kline?category=linear&symbol=SOLUSDT&interval=5&limit=5' | head -c 500
   ```
   EXPECT: JSON with `"success": true` and a non-empty `data` array.

6. Confirm an UNKNOWN-symbol request (XRPUSDT — not in v1 tape) does NOT 500:
   ```
   curl -s -o /dev/null -w '%{http_code}\n' 'http://localhost:8001/api/v1/market/kline?category=linear&symbol=XRPUSDT&interval=5&limit=5'
   ```
   EXPECT: 200 (with empty/short data), NOT 500.

7. Confirm EMERGENCY_STOP is in place (D-11):
   ```
   ls -la EMERGENCY_STOP
   ```
   EXPECT: file exists.

8. Tear down for cleanup:
   ```
   docker compose -f docker-compose.unified.yml down -v
   cd /tmp && rm -rf crypto-bot-bootstrap-test
   ```

**Resume signal:** Type "approved" if all 8 checks pass, or paste the specific failed step + log excerpt.

---

## Verification Gates Summary (All Passed)

| Gate | Status |
|------|--------|
| `bash -n bootstrap.sh` | PASS |
| `grep -q 'docker-compose.unified.yml' bootstrap.sh` | PASS |
| `grep -q 'cp -n' bootstrap.sh` | PASS |
| `grep -q 'EMERGENCY_STOP' bootstrap.sh` | PASS |
| `! grep -q 'git clean' bootstrap.sh` | PASS |
| `! grep -E 'echo.*\$BYBIT_(API_KEY\|API_SECRET)' bootstrap.sh` | PASS |
| `! grep -E 'docker compose.*down' bootstrap.sh` | PASS |
| `python3 -c "import yaml; yaml.safe_load(open('docker-compose.unified.yml'))"` | PASS |
| `grep -q 'MARKET_DATA_SOURCE=tape' .env.example` | PASS |
| `grep -q 'LIVE_TRADING_ACK=' .env.example` | PASS |
| `grep -q 'tests/fixtures/tape:/app/tests/fixtures/tape:ro' docker-compose.unified.yml` | PASS |
| `[ -x bootstrap.sh ]` (git mode 100755) | PASS |

---

## Files Modified

| File | Change | Commit |
|------|--------|--------|
| `.env.example` | Appended `MARKET_DATA_SOURCE=tape` + `LIVE_TRADING_ACK=` | 6ad4533 |
| `docker-compose.unified.yml` | Extended bybit-connector: env + RO tape volume | 391ca7a |
| `bootstrap.sh` | NEW — 6-step operator entrypoint (mode 100755) | 728495b |

## Requirements Addressed

- **INFRA-02 (partial):** bootstrap.sh provisions `.env` from `.env.example`, brings up stack, health-probes — runtime verification pending Task 4 operator checkpoint.
- **INFRA-03 (tape half, partial):** `MARKET_DATA_SOURCE=tape` default wired into compose + `.env.example` — runtime verification pending Task 4.
- **D-09:** 15-service health probe with 120s timeout implemented.
- **D-10:** `.env.example` provides correct flag defaults (`PAPER_TRADING_MODE=true`, `TRADING_MODE=PAPER`, `ENABLE_ML_PREDICTIONS=false`, etc.).
- **D-11:** EMERGENCY_STOP touched at step [3/6] before compose up (race prevention).
- **D-12:** Reuses health_check.sh service port table pattern.
- **D-13:** Fail-loud-leave-stack-up on probe failure; no auto-teardown, no retry.
- **D-14:** `MARKET_DATA_SOURCE=tape` default in compose env.
- **D-17:** Empty creds accepted in tape mode (compose already defaults to `${BYBIT_API_KEY:-}`).

## Notes for Operator

- Steps 4-6 in the verification block (BYBIT_PRICE_SOURCE grep, SOLUSDT kline, XRPUSDT 200) depend on plans 01-01 (tape fixtures) and 01-02 (bybit-connector tape-mode branch) being deployed. Ensure those commits are present in the fresh clone before running bootstrap.
- The `BYBIT_PRICE_SOURCE: mode=tape` log line (step 4) is emitted by the bybit-connector tape-mode lifespan branch from plan 01-02.
- Sentiment-analysis-service image may fail to build on first run (PyPI timeout, landmine §9). If it does: re-run `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis` then re-run `bash bootstrap.sh`. Per D-13, bootstrap does not auto-retry.
