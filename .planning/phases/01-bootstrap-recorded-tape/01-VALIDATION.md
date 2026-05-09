---
phase: 01
slug: bootstrap-recorded-tape
status: nyquist-compliant
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-09
updated: 2026-05-09
---

# Phase 01 — Validation Strategy

> Per-phase validation contract. State B reconstruction — derived from PLAN/SUMMARY artifacts after phase completion.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (project-wide) |
| **Config file** | `pyproject.toml` (no `pytest.ini`) |
| **Quick run command** | `python3 -m pytest tests/test_tape_fixtures.py tests/test_bootstrap_script_static.py tests/test_live_smoke_workflow.py -q --no-cov` |
| **Tape client unit suite** | `cd services/bybit-connector && python3 -m pytest tests/test_tape_replay_client.py -q --no-cov` |
| **Estimated runtime** | ~1 second (62 static gates + 11 unit) |
| **CI** | Project-wide pytest job (default lane). `live-smoke.yml` is separate (cron + manual; D-16 explicitly out-of-deterministic-lane). |

---

## Sampling Rate

- **After every task commit:** Run quick suite
- **After every plan wave:** Quick suite + tape replay unit suite
- **Before `/gsd-verify-work`:** Both suites green
- **Max feedback latency:** ~1 second

---

## Per-Plan Verification Map

| Plan ID | Requirement / Success Criterion | Test File | Test Type | Automated Command | Status |
|---|---|---|---|---|---|
| 01-01 | Tape JSONL fixtures: 5 symbols × 2 feeds, `tape_version=1` headers, ≥2000 kline rows/symbol, 7-element list shape, `source=bybit-mainnet`, size <50MB | `tests/test_tape_fixtures.py` | static | `pytest tests/test_tape_fixtures.py` | green (35/35) |
| 01-02 | TapeReplayClient mirrors BybitRestClient signatures; tape mode boots with empty BYBIT_API_KEY/SECRET; unknown symbols return [] without raising | `services/bybit-connector/tests/test_tape_replay_client.py` | unit | `cd services/bybit-connector && pytest tests/test_tape_replay_client.py --no-cov` | green (11/11) |
| 01-03 | bootstrap.sh: `cp -n` .env provisioning, no `git clean -fdx`, `DOCKER_BUILDKIT=0`, `docker-compose.unified.yml`, touches EMERGENCY_STOP, no echo of BYBIT credentials, exits 1 on failure, no `docker compose down` | `tests/test_bootstrap_script_static.py` | static (grep gates) | `pytest tests/test_bootstrap_script_static.py` | green (13/13) |
| 01-04 | live-smoke.yml: no push/PR triggers, `schedule` + `workflow_dispatch` present, `continue-on-error: true` on probe, `BYBIT_TESTNET=true` hardcoded, `PAPER_TRADING_MODE=true`, `AUTO_TRADING_ENABLED=false`, secrets refs not plaintext, `docker-compose.unified.yml`, `down -v` cleanup | `tests/test_live_smoke_workflow.py` | static (workflow grep gates) | `pytest tests/test_live_smoke_workflow.py` | green (14/14) |

---

## ROADMAP Success Criteria Coverage

| # | Success Criterion | Mapped Test(s) | Status |
|---|---|---|---|
| 1 | Operator runs `bootstrap.sh` against empty `.env` → script provisions stack from documented template; no manual editing | `test_bootstrap_script_static.py` (cp -n .env, no manual prompt, no `git clean -fdx`) | green (static) + manual E2E |
| 2 | Recorded-tape replay loader serves Bybit OHLCV (klines + ticker); orderbook + funding deferred per D-02 | `test_tape_fixtures.py` (klines + ticker fixtures present) + `test_tape_replay_client.py` (replay path) | green |
| 3 | bootstrap.sh brings stack to healthy state (15 services pass /health) reproducibly across two consecutive runs in fresh tmp clone | static gates (no destructive flags, idempotent provisioning) + manual E2E | green (static) + manual E2E |
| 4 | Separate "live smoke" path documented + explicitly out-of-scope for deterministic suite (allowed flaky, nightly only) | `test_live_smoke_workflow.py` (no push/PR, schedule+workflow_dispatch, continue-on-error) | green |

---

## Manual-Only / Operator-Procedural

| Item | Source | Rationale |
|---|---|---|
| `bootstrap.sh` E2E run on fresh tmp clone | ROADMAP SC-1 + SC-3 | Requires Docker Desktop + WSL2 host environment; static gates cover all grep-verifiable correctness. E2E is operator-executed before milestone sign-off. |
| Nightly `live-smoke.yml` cron actually firing in GitHub Actions | ROADMAP SC-4 | CI-COVERED by schedule trigger; structural gates (14 tests) verify trigger is present in workflow YAML. Cloud-side execution observable only in Actions run history. |

---

## Accepted Deferrals

| Item | Source | Rationale |
|---|---|---|
| Orderbook + funding tape feeds | `01-CONTEXT.md` D-02 | Their consumers `PREFER_MAKER_ORDERS` / `ENABLE_FUNDING_GATE` default off; forward-test in Phase 5. Not a Phase 1 gap. |
| Live-smoke probe failures | `01-CONTEXT.md` D-16 | `continue-on-error: true` on probe step is by design — failure NOTIFIES (Issue / artifact) but does NOT block deterministic CI lane. |

---

## Test Audit Trail

| Audit Date | Gaps Found | Resolved | Escalated | Manual-Only | Run By |
|------------|------------|----------|-----------|-------------|--------|
| 2026-05-09 | 4 (3 static + 1 impl bug) | 3 static gaps + 1 impl bug fixed | 0 | 2 (operator E2E + cloud cron observability) | gsd-nyquist-auditor |

**Implementation bug fixed during audit:** `services/bybit-connector/app/config.py` was using `List[str]` without importing `List` from `typing`. This caused `NameError: name 'List' is not defined` at pytest collection time, breaking the connector test suite. Fix committed as `f6308f2 fix(bybit-connector): add missing List to typing imports`.

**Final test count:** 62 new static/structural tests + 11 pre-existing tape replay unit tests, all green. Zero regressions.

---

## Sign-Off

- [x] Every Phase 1 success criterion (1-4) maps to an automated command OR documented manual-only step
- [x] Both phase requirements (INFRA-02 tape replay, INFRA-03 bootstrap reproducibility) covered
- [x] Manual-only items are operator-procedural (E2E run + cloud cron observation), not skipped automation
- [x] D-02 deferrals (orderbook/funding) and D-16 (live-smoke out-of-lane) explicitly documented
- [x] Phase is **Nyquist-compliant**
