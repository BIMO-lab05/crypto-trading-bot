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

## INFRA-06 Bug Triage Outcomes (Phase 2)

Logged 2026-05-08 per Phase 2 INFRA-06 / CD-02. All three bugs from the INFRA-06 defect register have been addressed.

| Bug | Status | Reference |
|-----|--------|-----------|
| 1. Stale in-memory ML model after retrain | FIXED — `_reload_if_stale()` added to `gru_predictor.py` (mirrors existing `gru_model.py:140-166`); log format aligned to `MODEL_RELOAD: path=` in both predictors; regression tests in `services/ml-prediction-service/tests/test_model_reload.py` and `tests/integration/test_pre_existing_bug_regressions.py::test_stale_ml_model_reload` | `services/ml-prediction-service/app/ml_models/gru_predictor.py` |
| 2. Hardcoded confidence=0 still emitting signals | FIXED — explicit `confidence > 0` filter + `AGGREGATOR_CONFIDENCE_FILTER` log in `services/technical-analysis/app/handlers/analysis.py`; regression test in `services/technical-analysis/tests/test_signal_aggregator_confidence_zero.py`; integration coverage implicit via `test_fresh_clone_round_trip` | `services/technical-analysis/app/handlers/analysis.py` |
| 3. WSL2 BuildKit hang on `docker compose up --build` | DOCUMENTED — no code fix possible (environmental). Workaround: `make build-no-buildkit SVC=<name>` (Plan 02-10) or `DOCKER_BUILDKIT=0 docker compose -f docker-compose.unified.yml build`. See `## Symptom: BuildKit hang` above. | RUNBOOK § BuildKit hang; `Makefile` |
