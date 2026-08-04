# RUNBOOK — Failure Triage

Symptom-indexed recovery procedures for the crypto-trading-bot stack.

- For nominal operations (deploys, backups, monitoring): see [`docs/operations/RUNBOOK.md`](docs/operations/RUNBOOK.md).
- For first-time setup: see [`docs/development/SETUP.md`](docs/development/SETUP.md).
- This file: "the stack just broke — what now?"

## Index

- [Symptom: BuildKit hang on `docker compose up --build`](#symptom-buildkit-hang-on-docker-compose-up---build)
- [Symptom: Docker context misconfig (WSL2 named-pipe error)](#symptom-docker-context-misconfig-wsl2-named-pipe-error)
- [Symptom: Bind-mount race — service has empty /app/logs or /app/tests/fixtures](#symptom-bind-mount-race--service-has-empty-applogs-or-apptestsfixtures)
- [Symptom: Stale in-memory ML model after retrain](#symptom-stale-in-memory-ml-model-after-retrain)
- [Symptom: bootstrap.sh fails with one or more UNHEALTHY services](#symptom-bootstrapsh-fails-with-one-or-more-unhealthy-services)
- [Symptom: EMERGENCY_STOP recovery — auto-trader will not arm after stop](#symptom-emergency_stop-recovery--auto-trader-will-not-arm-after-stop)
- [Symptom: Market-data stale or missing — bybit-connector chain broken](#symptom-market-data-stale-or-missing--bybit-connector-chain-broken)
- [Pre-LIVE Operator Checklist](#pre-live-operator-checklist)
- [Tournament harness — first-time setup](#tournament-harness--first-time-setup)

---

## Symptom: BuildKit hang on `docker compose up --build`

`docker compose up --build` stalls indefinitely on a single image (often `sentiment-analysis`, `ml-prediction-service`, or `technical-analysis`). No progress bar advance, no error.

**Diagnose:**
- `docker context show` — reports the active context. Must be `default` (Unix socket); `desktop-linux` is the WSL2 named-pipe context that hangs builds.
- `cat /proc/version | grep -i microsoft` — confirms WSL2 kernel; the BuildKit-on-WSL2 issue is environmental.
- `docker compose -f docker-compose.unified.yml build <svc>` — repro; if it stalls past 2 minutes on one service with no log output, this is the case.

**Action:**
```bash
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build <svc>
# or use the convenience target (Plan 02-10):
make build-no-buildkit SVC=<svc>
```

**Verification:**
- `docker compose -f docker-compose.unified.yml ps` — service shows `Up (healthy)` after re-run.
- Build log shows progressive `Step N/M` output (no stage stalls).
- `bash bootstrap.sh` reaches `[6/6] Bootstrap complete` without re-hanging.

---

## Symptom: Docker context misconfig (WSL2 named-pipe error)

Any `docker` invocation errors with `error during connect: ... npipe:////./pipe/docker_engine: ...` or `Cannot connect to the Docker daemon`. Stack will not even start.

**Diagnose:**
- `docker context show` — returns `desktop-linux` instead of expected `default`.
- `docker context ls` — confirms multiple contexts available; `default` should exist.
- `docker info` — fails with the same `npipe` connection error.

**Action:**
```bash
docker context use default
docker context show  # must now print: default
```

**Verification:**
- `docker info` returns server version + storage driver (no error).
- `docker ps` lists containers without error.
- Re-run `bash bootstrap.sh`; stack reaches healthy idle.

---

## Symptom: Bind-mount race — service has empty /app/logs or /app/tests/fixtures

A service errors with `PermissionError: /app/logs` or `FileNotFoundError: tests/fixtures/tape/...` despite `docker inspect` showing the bind mount as `bind`. This is a known WSL2 + Docker Desktop race where the bind silently fails at container-create time; the path inside the container is empty + root-owned.

**Diagnose:**
- `docker exec <svc> ls -la /app/logs` — returns root-owned empty dir (mount silently failed).
- `docker inspect <svc> --format '{{json .Mounts}}'` — shows `Type: bind` for the path that's empty (mount looks correct on the host side but didn't take inside the container).
- Service logs show `PermissionError` writing to `/app/logs/service.log` or `FileNotFoundError` reading tape fixtures.

**Action:**
```bash
docker compose -f docker-compose.unified.yml up -d --force-recreate <svc>
```

**Verification:**
- `docker exec <svc> ls -la /app/logs` — shows the host-mounted contents (non-empty + matching host UID, not root).
- Service `/health` returns 200; logs show no `PermissionError` / `FileNotFoundError`.
- For tape-mode services: `docker exec <svc> ls /app/tests/fixtures/tape/klines` lists JSONL files for the 5 validated symbols.

---

## Symptom: Stale in-memory ML model after retrain

`ml-retraining-service` ran a successful retrain (new model file present in `models/`), but `ml-prediction-service` continues to return predictions matching the pre-retrain model. The service has not picked up the new artifact.

**Diagnose:**
- `docker logs ml-prediction-service | grep -i "model loaded"` — last line shows the OLD model file path (not the just-retrained one).
- `ls -la models/<symbol>/` on the host — newest file is more recent than the timestamp in the `model loaded` log line.
- `curl http://localhost:8007/api/v1/predictions/SOLUSDT` — returns predictions identical to pre-retrain values (compare against a saved sample).

**Action:**
```bash
docker compose -f docker-compose.unified.yml restart ml-prediction-service
```

**Verification:**
- `docker logs ml-prediction-service --tail 20 | grep -i "model loaded"` — shows the new model file path / mtime matching the retrain output.
- `curl http://localhost:8007/api/v1/predictions/SOLUSDT` — returns predictions differing from the pre-restart values.
- Cross-link: For long-term fix (mtime-watching reload hook so a manual restart is not required), see Phase 2 Plan 02-08 (INFRA-06 deferred-bug triage).

---

## Symptom: bootstrap.sh fails with one or more UNHEALTHY services

`bash bootstrap.sh` exits non-zero with one or more `[5/6] UNHEALTHY <svc>:<port>` lines. Stack is partially up; some service `/health` endpoints never returned 200 inside the 120s deadline.

**Diagnose:**
- Read the exact lines printed by `bootstrap.sh` step `[5/6]`; each `UNHEALTHY <svc>:<port>` names a failing service.
- `docker compose -f docker-compose.unified.yml logs --tail 100 <svc>` — service-specific failure cause.
- `docker compose -f docker-compose.unified.yml ps` — confirm container is `Up` vs `Exited` vs `Restarting`.

**Action:** triage by service:
```bash
# sentiment-analysis: PyPI read timeout during pip install (CLAUDE.md gotcha)
DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build sentiment-analysis
docker compose -f docker-compose.unified.yml up -d sentiment-analysis

# postgres / timescaledb: container started but Postgres not ready yet
docker exec crypto-bot-postgres pg_isready -U postgres
docker exec crypto-bot-timescaledb pg_isready -U postgres
# if not ready, give it 30s then re-probe

# bind-mount race symptoms (PermissionError /app/logs): see "Bind-mount race" symptom above
docker compose -f docker-compose.unified.yml up -d --force-recreate <svc>
```

**Verification:**
- Re-run `bash bootstrap.sh`; expect `[6/6] Bootstrap complete` without `UNHEALTHY` lines.
- If still red after one round, do NOT loop manually — run `bash scripts/iter-fix.sh` (Plan 02-06) for checkpointed iteration on the integration suite. Per project rule (D-13): no auto-retry inside `bootstrap.sh`.

---

## Symptom: EMERGENCY_STOP recovery — auto-trader will not arm after stop

After an emergency stop (file present at repo root or API-triggered), the trading-engine refuses to fire signals — auto-trader loop holds at STEP-0. Operator wants to resume trading; clearing the file alone has not re-armed the engine.

**Diagnose:**
- `ls -la EMERGENCY_STOP` — file present? Should be ABSENT after recovery.
- `docker logs trading-engine --tail 50 | grep -i "emergency\|step-0\|hold"` — engine reports it is in STEP-0 hold.
- `curl http://localhost:8000/api/portfolio/emergency-stop/status` — returns `active: true` if API-side flag is also set.
- `docker inspect trading-engine --format '{{json .Mounts}}' | grep EMERGENCY_STOP` — confirms RO bind-mount of the file at `/app/EMERGENCY_STOP`.

**Action:**
```bash
# 1. Remove the file at repo root (RO bind-mount means the engine sees it disappear)
rm -f EMERGENCY_STOP

# 2. Clear the API-side flag if /api/portfolio/emergency-stop/status was active
curl -X POST http://localhost:8000/api/portfolio/emergency-stop/clear

# 3. If the engine still holds (file change not picked up), restart it
docker compose -f docker-compose.unified.yml restart trading-engine
```

**Verification:**
- `ls -la EMERGENCY_STOP` — file absent.
- `curl http://localhost:8000/api/portfolio/emergency-stop/status` — returns `active: false`.
- `docker logs trading-engine --tail 20 | grep -iE "auto.?trader.armed|loop running"` — engine reports armed and looping.
- Stack reaches healthy idle (re-run `bash bootstrap.sh` if needed; expect `[6/6] Bootstrap complete`).

---

## Symptom: Market-data stale or missing — bybit-connector chain broken

Post-Phase-13 (2026-05-22), every consumer of Bybit market data — scripts, ml-prediction-service handlers, backtesting fetcher, infra rotate-secrets ping, market-data-service ingest — routes through `bybit-connector:8001` REST. When that single chokepoint breaks, every downstream consumer reports stale prices, empty kline backfills, or hard failures. Triage the four sub-causes below in order.

**Diagnose:**

Sub-cause A — bybit-connector container down or unhealthy:
- `docker ps --filter name=bybit-connector` — empty result or `Exited` / `Restarting` status. A healthy entry shows `Up <duration> (healthy)`.
- `docker logs crypto-bot-bybit-connector --tail 30` — last lines show a Python traceback, `OOMKilled`, or `received SIGTERM` shutdown.
- `curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8001/health` — non-200 (or connection refused) confirms the connector is not serving.

Sub-cause B — `BYBIT_CONNECTOR_URL` environment misconfigured (host vs compose hostname):
- `docker exec crypto-bot-market-data env | grep BYBIT_CONNECTOR_URL` — must read `http://bybit-connector:8001` inside the compose network. If it reads `http://localhost:8001`, the consumer is trying to dial out of its container to the host loopback (will fail).
- For host-side operator scripts (`python scripts/collect_*.py` on the host, not in compose), the inverse holds: `echo $BYBIT_CONNECTOR_URL` must read `http://localhost:8001`, not the compose hostname.
- Mismatched value triggers `httpx.ConnectError: All connection attempts failed` in the consumer's logs.

Sub-cause C — bybit-connector hitting Bybit-side ratelimit (HTTP 429 / rate.limit headers):
- `docker logs crypto-bot-bybit-connector --tail 100 | grep -iE 'ratelimit|rate.limit|HTTP 429|Too Many'` — non-empty result confirms Bybit is throttling.
- Bybit's REST rate limits are documented at `https://bybit-exchange.github.io/docs/v5/rate-limit` — burst-mode is 600 req/5s for unauthenticated requests on most endpoints; if multiple backfill scripts run in parallel they can exhaust the budget for the whole stack.

Sub-cause D — `MARKET_DATA_SOURCE=tape` accidentally enabled in production:
- `docker exec crypto-bot-bybit-connector env | grep MARKET_DATA_SOURCE` — value reads `tape` instead of `live`. Production must always be `live`; `tape` replays JSONL fixtures from `tests/fixtures/tape/` and returns deterministic-but-stale data with a 30s+ "now" lag.
- `docker logs crypto-bot-bybit-connector --tail 100 | grep -i 'tape mode\|MARKET_DATA_SOURCE=tape'` — a startup log line confirms tape mode is active.
- Cross-link: tape mode is the default for `tests/integration/` runs and `docker-compose.test.yml`; if those compose overrides leak into a production deploy, this is the symptom.

**Action:**

For sub-cause A (connector down):
```bash
docker compose -f docker-compose.unified.yml up -d bybit-connector
# Watch for healthy status (~30s):
docker compose -f docker-compose.unified.yml ps bybit-connector
```

For sub-cause B (URL misconfig):
```bash
# Compose-network consumer (inside container) — should be the compose hostname
docker exec <consumer-service> env | grep BYBIT_CONNECTOR_URL
# Fix by editing docker-compose.unified.yml service environment block, then:
docker compose -f docker-compose.unified.yml up -d --force-recreate <consumer-service>

# Host-side operator script — should be localhost
export BYBIT_CONNECTOR_URL=http://localhost:8001
```

For sub-cause C (ratelimit):
- Identify which consumer is hot: `docker logs crypto-bot-bybit-connector --tail 200 | grep -oE 'X-Bapi-Limit-Status: [0-9]+' | sort | uniq -c`.
- Stop any parallel backfill scripts; ratelimit clears within 60s typically.
- If recurring, throttle the consumer by adding `asyncio.sleep` between batched calls or reducing concurrent worker count.

For sub-cause D (tape leaked into prod):
```bash
# Identify the override (most often docker-compose.override.yml or stale .env entry)
grep -rE 'MARKET_DATA_SOURCE=tape' docker-compose*.yml .env 2>/dev/null
# Remove the override / set MARKET_DATA_SOURCE=live, then force-recreate
docker compose -f docker-compose.unified.yml up -d --force-recreate bybit-connector
```

**Verification:**

Hit the connector directly and confirm a live Bybit ticker response:

```bash
curl http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear
# From host (outside compose network):
curl http://localhost:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear
```

Expected: 200 response within 2s, JSON body shaped `{"success": true, "data": {"category": "linear", "list": [{"symbol": "BTCUSDT", "lastPrice": "<float>", "indexPrice": "...", "markPrice": "...", ...}]}}`. The `lastPrice` field must be a non-zero float, and the timestamp implicit in `data.list[0]` must match real-time Bybit data (cross-check against `https://www.bybit.com/trade/usdt/BTCUSDT` in a browser if uncertain).

Failure indicators that mean the chain is still broken — recurse to Diagnose:
- `{"success": false, ...}` body → connector reached Bybit but Bybit rejected (likely sub-cause C ratelimit, or auth misconfig).
- HTTP 5xx → connector itself is unhealthy (sub-cause A).
- `Connection refused` or `Could not resolve host: bybit-connector` → URL/networking misconfig (sub-cause B).
- `lastPrice` reads `"0"` or matches a known tape fixture → tape mode leaked (sub-cause D).

Then confirm at least one downstream consumer can read the chain. A quick health probe:
```bash
docker exec crypto-bot-market-data curl -s http://bybit-connector:8001/api/v1/market/ticker?symbol=BTCUSDT&category=linear | head -c 200
```

If that returns a populated `lastPrice`, the chain is restored.

---

## Pre-LIVE Operator Checklist

Before flipping `TRADING_MODE=LIVE`, work through each of the 6 preconditions below.
Each pairs with a `preflight_live.py` check ID; the dashboard tile (Phase 10
DASHLIVE-01, not yet shipped) will render the same 6 rows.

Run `python3 scripts/preflight_live.py --json` for a snapshot of all 6 at once.
The CLI exits 0 on PASS, 1 on any FAIL or UNKNOWN. The HTTP endpoint
`GET /api/preflight/live-readiness` (proxied through api-gateway, served by
trading-engine) returns the same JSON. The four-flag friction documented in
CLAUDE.md "Trading-mode flags" is enforced — these checks verify each flag is
in the LIVE-correct state, they do not replace the deliberate flip.

### Precondition 1: Per-trade cap <= 2% (LIVE-strict)

**Diagnose:**
- `python3 scripts/preflight_live.py --check=cap --json` — reports `"status": "FAIL"` when `MAX_RISK_PER_TRADE > 0.02` in the current env.
- `grep MAX_RISK_PER_TRADE .env` — shows the current setting (default 0.10 per ADR-010 paper-relaxed).
- `docker logs trading-engine | grep "LIVE_PREFLIGHT_REJECTED reason=cap_too_high"` — if the container failed to start, this line names the cause.

**Action:**
```bash
# Restore LIVE-strict cap in .env (paper-relaxed 10% per ADR-010 must be lowered before flipping LIVE)
sed -i 's/^MAX_RISK_PER_TRADE=.*/MAX_RISK_PER_TRADE=0.02/' .env
grep MAX_RISK_PER_TRADE .env   # expect: MAX_RISK_PER_TRADE=0.02

# Restart trading-engine so the new cap is read at lifespan
docker compose -f docker-compose.unified.yml restart trading-engine
```

**Verification:**
- `python3 scripts/preflight_live.py --check=cap` exits 0.
- `docker compose -f docker-compose.unified.yml up trading-engine` reaches log line `LIVE preflight cap check passed: max_risk_per_trade=0.02 <= 0.02`.
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `cap` row's `status` field is `"PASS"`.

---

### Precondition 2: PAPER_TRADING_MODE=false

**Diagnose:**
- `python3 scripts/preflight_live.py --check=paper_mode --json` — reports `"status": "FAIL"` when `PAPER_TRADING_MODE=true` in `.env`.
- `grep PAPER_TRADING_MODE .env` — shows the current setting (default `true`).

**Action:**
```bash
sed -i 's/^PAPER_TRADING_MODE=.*/PAPER_TRADING_MODE=false/' .env
grep PAPER_TRADING_MODE .env   # expect: PAPER_TRADING_MODE=false

# Restart trading-engine so the new mode is picked up at lifespan
docker compose -f docker-compose.unified.yml restart trading-engine
```

**Verification:**
- `python3 scripts/preflight_live.py --check=paper_mode` exits 0.
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `paper_mode` row's `status` field is `"PASS"`.

---

### Precondition 3: TRADING_MODE=LIVE

**Diagnose:**
- `python3 scripts/preflight_live.py --check=trading_mode --json` — reports the detected value in `detail`.
- `grep TRADING_MODE .env` — shows the current setting (default unset / `PAPER`).

**Action:**
```bash
sed -i 's/^TRADING_MODE=.*/TRADING_MODE=LIVE/' .env
grep TRADING_MODE .env   # expect: TRADING_MODE=LIVE

# Restart trading-engine so the new mode is read at lifespan (cap + ack checks fire here)
docker compose -f docker-compose.unified.yml restart trading-engine
```

**Verification:**
- `python3 scripts/preflight_live.py --check=trading_mode` exits 0.
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `trading_mode` row's `status` field is `"PASS"`.

---

### Precondition 4: LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY

**Diagnose:**
- `python3 scripts/preflight_live.py --check=ack --json` — reports `"status": "FAIL"` when the ACK is absent or wrong.
- `grep LIVE_TRADING_ACK .env` — shows the current setting (default absent).
- This sentinel is the deliberate-friction gate from CLAUDE.md "Trading-mode flags". Do NOT shortcut it; the literal value is checked exactly by `services/trading-engine/app/main.py` at lifespan.

**Action:**
```bash
# Add the literal sentinel exactly — no variation is accepted by the ACK check
echo 'LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY' >> .env
grep LIVE_TRADING_ACK .env   # expect: LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY

# Restart trading-engine so the ACK is verified at lifespan boot
docker compose -f docker-compose.unified.yml restart trading-engine
```

**Verification:**
- `python3 scripts/preflight_live.py --check=ack` exits 0.
- On startup, trading-engine logs `LIVE trading mode acknowledged via LIVE_TRADING_ACK`.
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `ack` row's `status` field is `"PASS"`.

---

### Precondition 5: EMERGENCY_STOP file absent

**Diagnose:**
- `python3 scripts/preflight_live.py --check=emergency_stop --json` — reports `"status": "FAIL"` if a regular file is present at the configured path (`Path.is_file()` check, matching trading-engine's existing handling).
- `ls -la EMERGENCY_STOP` — run from repo root.

**Action:**
```bash
rm -f EMERGENCY_STOP
ls -la EMERGENCY_STOP   # expect: No such file or directory
```

Note (CLAUDE.md gotcha): a *directory* at the path also reads as absent for the
preflight check, because `Path.is_file()` returns `False` for directories. If
you encounter an empty directory there (WSL bind-mount race), clean it up with
`rmdir EMERGENCY_STOP`. See the existing `## Symptom: EMERGENCY_STOP recovery`
section above for the full recovery flow including clearing the API-side flag.

**Verification:**
- `python3 scripts/preflight_live.py --check=emergency_stop` exits 0.
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `emergency_stop` row's `status` field is `"PASS"`.

---

### Precondition 6: DSR > 0.95 evidence row (only when ML enabled)

**Diagnose:**
- `python3 scripts/preflight_live.py --check=dsr_evidence --json` — reports `"status": "UNKNOWN"` when `ENABLE_ML_PREDICTIONS=true` but Phase 9's auto-flip marker `/run/mlgate_auto_flip.json` is absent.
- With `ENABLE_ML_PREDICTIONS=false` (the default), this check short-circuits to `"PASS"` — ML is disabled by default, so the gate does not apply.
- Query the leaderboard directly for the latest DSR row:
  ```bash
  docker exec crypto-bot-tournament-harness sqlite3 /data/tournament.db \
      "SELECT dsr FROM leaderboard ORDER BY tournament_start_ts DESC LIMIT 1"
  ```

**Action:**
- LIVE without ML: leave `ENABLE_ML_PREDICTIONS=false` and the check passes automatically. No further action required for this precondition.
- LIVE with ML on: Phase 9 (MLGATE-01/02) must land first; it owns the 7-day evidence accrual + auto-flip marker. As of 2026-05-16, Phase 9 has not shipped — `dsr_evidence` returns `UNKNOWN` whenever ML is enabled, and the CLI exits non-zero.

**Verification:**
- `python3 scripts/preflight_live.py --check=dsr_evidence` exits 0 (ML disabled path) or remains pending Phase 9 (ML enabled path).
- `curl -s http://localhost:8000/api/preflight/live-readiness | python3 -m json.tool` — the `dsr_evidence` row's `status` is `"PASS"` (ML off) or `"UNKNOWN"` (ML on, Phase 9 pending).

---

## INFRA-06 Bug Triage Outcomes (Phase 2)

Logged 2026-05-08 per Phase 2 INFRA-06 / CD-02. All three bugs from the INFRA-06 defect register have been addressed.

| Bug | Status | Reference |
|-----|--------|-----------|
| 1. Stale in-memory ML model after retrain | FIXED — `_reload_if_stale()` added to `gru_predictor.py` (mirrors existing `gru_model.py:140-166`); log format aligned to `MODEL_RELOAD: path=` in both predictors; regression tests in `services/ml-prediction-service/tests/test_model_reload.py` and `tests/integration/test_pre_existing_bug_regressions.py::test_stale_ml_model_reload` | `services/ml-prediction-service/app/ml_models/gru_predictor.py` |
| 2. Hardcoded confidence=0 still emitting signals | FIXED — explicit `confidence > 0` filter + `AGGREGATOR_CONFIDENCE_FILTER` log in `services/technical-analysis/app/handlers/analysis.py`; regression test in `services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py`; integration coverage implicit via `test_fresh_clone_round_trip` | `services/technical-analysis/app/handlers/analysis.py` |
| 3. WSL2 BuildKit hang on `docker compose up --build` | DOCUMENTED — no code fix possible (environmental). Workaround: `make build-no-buildkit SVC=<name>` (Plan 02-10) or `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build`. See `## Symptom: BuildKit hang` above. | RUNBOOK § BuildKit hang; `Makefile` |

---

## Tournament harness — first-time setup

The tournament harness (Phase 3) is opt-in via Docker compose profile `tournament`.
It does not start with the default `bootstrap.sh up`. Bring it up with:

    docker compose -f docker-compose.unified.yml --profile tournament up tournament-harness

Before the first tournament can run, two operator steps:

### 1. Apply the tournament_reader migration

The experiment containers use a SELECT-only Postgres role:

    # With the stack running, apply the migration manually
    docker exec -i crypto-bot-timescaledb \
        psql -U cryptobot -d market_data \
        < infrastructure/migrations/005_tournament_reader.sql

    # Confirm role exists
    docker exec crypto-bot-timescaledb \
        psql -U cryptobot -d market_data -c \
        "SELECT rolname FROM pg_roles WHERE rolname = 'tournament_reader';"

### 2. Set + rotate TOURNAMENT_READER_PASSWORD

    # Pick a strong random password
    PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

    # Persist in your .env (NEVER commit to git)
    echo "TOURNAMENT_READER_PASSWORD=$PASSWORD" >> .env

    # Apply to Postgres (rotates from the CHANGE_ME_VIA_ENV placeholder)
    docker exec -i crypto-bot-timescaledb \
        psql -U cryptobot -d market_data -c \
        "ALTER ROLE tournament_reader PASSWORD '$PASSWORD';"

    # Verify by connecting as the role
    docker exec crypto-bot-timescaledb \
        psql -h localhost -U tournament_reader -d market_data -c "SELECT 1 FROM klines LIMIT 1"

    # Confirm SELECT-only (this command MUST fail with permission denied)
    docker exec crypto-bot-timescaledb \
        psql -h localhost -U tournament_reader -d market_data -c \
        "DELETE FROM klines WHERE FALSE"

### Rotating the password later

Same as above — re-run step 2 with a new password. No service restart needed
because the orchestrator reads `TOURNAMENT_READER_PASSWORD` from `.env` at the
start of each tournament.

### Pre-tournament data check

The tournament refuses to start if any (symbol, interval) pair has fewer than
50,000 rows in the 12-month trailing window (D-07 hard floor). Verify ahead of time:

    # Symbols are Bybit-convention (USDT-suffixed) — matches what market-data-service writes.
    # tournament_loader rejects bare base symbols (e.g. 'SOL') at YAML load time, so the
    # rows you see here MUST include 'SOLUSDT' / 'BNBUSDT' / 'ADAUSDT' for the v1
    # validated-symbol set. If you see only bare base entries, market-data-service
    # is misconfigured and no tournament can run.
    docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
      "SELECT symbol, interval, COUNT(*) FROM klines
         WHERE is_mainnet = true
           AND timestamp > now() - interval '365 days'
         GROUP BY symbol, interval
         ORDER BY symbol, interval;"

    # Targeted check for the v1 validated-symbol set (each must show >= 50000 rows):
    docker exec crypto-bot-timescaledb psql -U cryptobot -d market_data -c \
      "SELECT symbol, COUNT(*) FROM klines
         WHERE is_mainnet = true
           AND interval = '5m'
           AND symbol IN ('SOLUSDT','BNBUSDT','ADAUSDT')
           AND timestamp > now() - interval '365 days'
         GROUP BY symbol
         ORDER BY symbol;"
