# Phase 2: Integration Test Suite & RUNBOOK - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

A pytest+testcontainers integration suite asserts the full stack works end-to-end from a fresh `git clone` into a tmp directory, runs deterministically against the Phase 1 recorded tape, ships a checkpointed iteration harness that refuses to silently mock or skip failures, and a RUNBOOK.md captures operator-recovery procedures for known WSL2/Docker failure modes. Three pre-existing concrete bugs (stale in-memory ML model, hardcoded `confidence=0` paths, WSL2 BuildKit env) are each either fixed with regression tests or explicitly deferred with a written decision.

**In scope:**
- pytest+testcontainers integration suite under `tests/integration/`
- Session-scoped `bootstrap.sh`-driven stack fixture
- Per-test tape-cursor reset endpoint on `bybit-connector`
- `scripts/iter-fix.sh` — checkpointed iteration harness with diff-review gate
- Hard enforcement against silent mocks / skips / threshold lowering
- `RUNBOOK.md` covering WSL2 BuildKit hangs, docker context misconfig, stale-model restart, bootstrap-test triage
- INFRA-06 triage of the 3 named pre-existing bugs

**Out of scope (other phases):**
- Tournament harness — Phase 3
- Tournament significance + auto-PR — Phase 4
- Forward-paper-test of opt-in features (vol parity, maker, funding) — Phase 5
- Dashboard audit + safety state — Phase 6
- Playwright frontend smoke — Phase 7

</domain>

<decisions>
## Implementation Decisions

### Test runner & isolation
- **D-01:** Stack bring-up = pytest session-scoped fixture **shells out to `./bootstrap.sh`** (Phase 1 Plan 03 deliverable). No parallel bring-up path; the test harness validates the same script the operator runs. Bypassing bootstrap.sh forfeits the "fresh-clone" promise.
- **D-02:** pytest runs **on the host**, outside compose. Matches the operator path on a fresh clone; avoids docker-in-docker complexity. CI runner (GitHub Actions ubuntu-latest) is also a host.
- **D-03:** Stack lifecycle = **session-scoped, one shared stack** for the whole pytest run. Boot is ~2 min; sharing keeps suite under 10 min total. Per-test isolation via DB TRUNCATE fixtures + tape cursor reset (D-04).
- **D-04:** Tape determinism = **per-test cursor reset** via a new `POST /admin/tape/reset` on `bybit-connector` (gated to `MARKET_DATA_SOURCE=tape` mode only). pytest fixture calls it before each test; stack stays up, data clock rewinds.

### Fresh-clone proof boundary
- **D-05:** Clone source = **local working tree via `git clone file://$(pwd) /tmp/cb-test-<sha>`**. Catches uncommitted-file deps without network; runs offline; deterministic. Origin/main rejected (CI flakes without internet, ignores uncommitted local changes).
- **D-06:** `.env` state at bootstrap entry = **empty `.env`**. Validates the Phase 1 D-17 promise (tape mode bypasses `BYBIT_API_KEY` validation). If empty-creds path breaks, that's a Phase 1 regression to surface, not paper over.
- **D-07:** Run target = **local + CI, same `pytest tests/integration` invocation**. Operator must reproduce every CI failure locally; single source of truth. CI-only or local-only paths rejected for drift risk.
- **D-08:** Tmp clone cleanup = **delete on success, keep on failure**. Matches Phase 1 D-13 "fail loud, leave artifacts". `pytest -x` on failure leaves `/tmp/cb-test-<sha>` for `docker logs` post-mortem.

### Iteration harness UX (INFRA-04)
- **D-09:** Diff-review format = **terminal `git diff` + inline `Apply? [y/N]` prompt**. Simplest UX; works in any shell; no Claude/IDE dep. Persistent record ships via the per-fix git commit, not a separate patch file.
- **D-10:** Entry point = **`scripts/iter-fix.sh`** at repo root. Standalone shell entrypoint; doesn't conflate with pytest internals; can be wrapped by `/gsd-quick` or invoked manually. Pytest plugin path rejected — couples test runner to mutation logic.
- **D-11:** Approval granularity = **per-fix**. Operator approves every individual diff. Catches drift before it compounds. Per-iteration-batch and auto-apply-when-green explicitly rejected — auto-apply is the exact Goodhart pattern INFRA-04 forbids.
- **D-12:** Anti-mock enforcement = **inside the harness script + CI guard**. `iter-fix.sh` greps the proposed diff for additions of `unittest.mock` / `mocker.patch` / `pytest.skip` / `pytest.mark.xfail` / numeric threshold lowering inside `tests/`; hard-refuses to apply matching diffs. CI repeats the check on PR.

### Claude's Discretion

These were noted as gray areas at present-time but not deep-dived. Researcher/planner should treat the stances below as defaults, surface them in RESEARCH.md/PLAN.md, and operator can override before execution.

- **CD-01 (Notification verification, INFRA-01 acceptance "a notification delivers"):** Use a **dedicated test Telegram bot in a private channel**, secret stored in GitHub Actions encrypted secret + `.env.test.example`. Local dev defaults to `NOTIFICATION_TEST_MODE=record` (writes would-be sends to `tests/.notifications.log`); CI sets `NOTIFICATION_TEST_MODE=live` and asserts the bot received the message via `getUpdates`. Pure-mock path rejected per CLAUDE.md verification standards ("notification actually received downstream").
- **CD-02 (INFRA-06 pre-existing bug triage):** Plan-phase produces one plan **02-0X-pre-existing-bug-triage** that investigates all 3 in parallel:
  - *Stale in-memory ML model:* fix with reload hook on model file mtime (~1d effort) — regression test asserts post-retrain prediction differs.
  - *Hardcoded `confidence=0` still emitting signals:* `grep -rn "confidence.*=.*0" services/` to enumerate; fix any that still pass an aggregator gate; regression test asserts a `confidence=0` signal is filtered upstream.
  - *WSL2 BuildKit hang:* documented in RUNBOOK with the `DOCKER_BUILDKIT=0` workaround (no code fix possible — environmental). Add `make build-no-buildkit` target as ergonomic shortcut.
  Default deferral bar: any individual bug whose fix exceeds 1 day or pulls in scope from another service is deferred with a written decision pinned to RUNBOOK.
- **CD-03 (RUNBOOK.md scope):** **Failure-triage-first format** — one section per symptom with `Symptom → Diagnose → Action → Verification`. Sections: BuildKit hang, docker context misconfig (`default` vs `desktop-linux`), bind-mount race (the `force-recreate` recovery from CLAUDE.md gotchas), stale-model restart, bootstrap-test failure triage, EMERGENCY_STOP recovery. No nominal-ops chapters — those live in `docs/development/SETUP.md`.
- **CD-04 (Paper-trade <60s assertion mechanics, INFRA-01):** Trigger via existing/new `POST /api/trading/force-signal` admin endpoint on `trading-engine` with a deterministic synthetic candle. "Round-trip" = signal published to RabbitMQ → portfolio_manager `positions` DB row inserted with non-null `created_at`. 60s timer = `time.monotonic()` between fixture-side request and DB-row presence (asserted via SELECT polling at 250 ms cadence). Real exchange call NOT in path (tape mode).
- **CD-05 (ML-models-loaded variant, INFRA-01 "if `ENABLE_ML_PREDICTIONS=true`"):** Default suite runs **ML-off** (matches Phase 1 D-10 stack-default). ML-on variant runs **nightly + manual** via `pytest tests/integration -m ml_on`, gated on the same flag flip. ML-on variant asserts model files present + GRU prediction endpoint returns non-default confidence; does NOT re-validate model edge (V0 finding stands; that's Phase 5).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project context
- `.planning/PROJECT.md` — milestone scope, validated capability, V0 finding pinning ML-off-by-default
- `.planning/REQUIREMENTS.md` — INFRA-01, INFRA-04, INFRA-05, INFRA-06 acceptance criteria
- `.planning/ROADMAP.md` § "Phase 2: Integration Test Suite & RUNBOOK" — goal, depends-on, success criteria

### Phase 1 carry-forward (load-bearing)
- `.planning/phases/01-bootstrap-recorded-tape/01-CONTEXT.md` § Decisions D-01..D-17 — tape format, healthy-idle definition, MARKET_DATA_SOURCE selector, EMERGENCY_STOP-touched-by-bootstrap default
- `bootstrap.sh` — Phase 1 Plan 03 deliverable; **session fixture in Phase 2 invokes this**
- `tests/fixtures/tape/{klines,ticker}/*.jsonl` — Phase 1 Plan 01 deliverable; 5 symbols × 7 days, klines+ticker only
- `services/bybit-connector/` — Phase 1 Plan 02 added tape replay; Phase 2 adds `POST /admin/tape/reset` (D-04)
- `.github/workflows/live-smoke.yml` — Phase 1 Plan 04; nightly live-mode advisory probe; **explicitly NOT extended in Phase 2**

### Operator-facing rules (load-bearing)
- `crypto-trading-bot/CLAUDE.md` § "Verification standards" — no "working" claims on HTTP-200 alone, restart-on-config-change rule, bind-mount race
- `crypto-trading-bot/CLAUDE.md` § "Environment" — WSL2 Docker context, BuildKit hangs, bind-mount race recovery
- `crypto-trading-bot/CLAUDE.md` § "Gotchas" — `docker-compose.unified.yml` is canonical, two pytest-host caveats (api-gateway test fastapi version pin), `pathlib.Path.write_text` mocking trap
- `crypto-trading-bot/CLAUDE.md` § "Project rules" — flag semantics, validated symbol set, EMERGENCY_STOP wiring

### Existing assets to reuse / extend
- `tests/integration/conftest.py` — existing pytest fixtures; Phase 2 EXTENDS, does not replace
- `tests/integration/test_e2e_trading_flow.py`, `test_end_to_end_trading.py`, `test_failure_scenarios.py`, `test_phase3_integration.py` — existing integration tests; Phase 2 layers on; harden or supersede as needed
- `health_check.sh` — health-probe shell pattern (used by `bootstrap.sh`); pytest fixture wraps the same logic
- `services/bybit-connector/app/` — tape replay loader (Phase 1) lives here; admin reset endpoint slots in
- `services/api-gateway/tests/conftest.py` — `admin_client` fixture pattern for auth-guarded routes (relevant for `force-signal` if reused)
- `docker-compose.unified.yml` — canonical compose; Phase 2 must NOT add a `test-runner` service (D-02)

### V0 / safety baseline
- Memory: `project_v0_finding_2026-04-30.md` — why ML-off-by-default; the ML-on variant test (CD-05) does NOT re-validate edge
- Memory: `feedback_pf_metric_pooling.md` — pooled-PF rule; relevant if any test asserts on PF reporting
- Memory: `feedback_pathlib_mocking.md` — patch `pathlib.Path.write_text` not `builtins.open` if any new test mocks file IO

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`bootstrap.sh`** — Phase 1 deliverable, drives compose up + health probe. Session fixture wraps it via `subprocess.run(["./bootstrap.sh"], cwd=tmp_clone, check=True)`.
- **`tests/fixtures/tape/`** — 5 symbols × {klines, ticker} × 7 days JSONL. `bybit-connector` already streams from this in tape mode; the new `POST /admin/tape/reset` resets the cursor without remounting.
- **`tests/integration/conftest.py`** — existing fixtures (db, http client). Phase 2 adds `bootstrap_stack`, `tape_reset`, `tmp_fresh_clone`, `force_signal` session/function fixtures.
- **`health_check.sh`** — health-probe semantics (`curl /health` per service, retry/backoff). Avoid duplicating in Python; either source it or call it from the fixture.
- **`services/api-gateway/tests/conftest.py:admin_client`** — pattern for invoking admin-guarded routes; `force-signal` and `tape/reset` likely reuse this.

### Established Patterns
- **Conventional Commits + per-fix atomic commits** — `iter-fix.sh` produces one commit per accepted fix (`fix(<service>): <one-line>`); aligns with the project commit rule.
- **Python `pathlib.Path.write_text`/`read_text`** bypasses `builtins.open` — any new test mocking file IO must patch `pathlib.Path.*` directly (memory: `feedback_pathlib_mocking.md`).
- **api-gateway suite runs in container** — fastapi 0.109 (container) vs 0.136 (host pip) returns different status codes for `HTTPBearer` (memory: `feedback_api_gateway_test_env.md`). The Phase 2 host-side suite does NOT subsume `services/api-gateway/tests/`; that suite still runs `docker exec`.

### Integration Points
- **pytest fixture ↔ `bootstrap.sh`** — fixture invokes script in tmp clone; captures exit code + last-N log lines; on failure, surfaces them in pytest output.
- **pytest fixture ↔ `bybit-connector` `/admin/tape/reset`** — function-scoped fixture HTTPs the endpoint before each test.
- **pytest ↔ DB (TimescaleDB + Postgres)** — function-scoped fixture TRUNCATEs `klines`, `tickers`, `positions`, `orders`, etc. between tests; preserves schema.
- **`iter-fix.sh` ↔ `pytest`** — script runs pytest until first failure, captures the failure log, runs a fix attempt (Claude/operator), presents diff, applies + commits on approval, re-runs.
- **`iter-fix.sh` ↔ git** — every accepted fix is its own commit; harness tags failed attempts with `wip(iter)` so they can be `git restore`d cheaply.
- **`force-signal` admin endpoint ↔ trading-engine** — synthetic-signal entry point (CD-04); behind `admin_client` auth; emits the same RabbitMQ event a real strategy would.

</code_context>

<specifics>
## Specific Ideas

- "No silent mock / no skip / no threshold lowering" is a **structural mechanism**, not a code-review note — the harness script enforces it via diff grep and refuses to apply. Memory of why: prior project pattern was for tests to drift under pressure; the user's INFRA-04 requirement explicitly forbids the unattended green-loop.
- `bootstrap.sh` is the **single bring-up path**; the suite proves the same script the operator runs. Validating a parallel pytest-managed compose path was rejected as drift-risk.
- Per-fix commits (D-09, D-11) feed into git history as atomic units — no "WIP iter dump" merges. If a fix is later rejected, it's `git revert` of one commit, not unraveling a batch.

</specifics>

<deferred>
## Deferred Ideas

- **Notification verification deep-dive** — gray area surfaced but not selected for discussion; default stance captured in CD-01. Operator may override during plan-phase review.
- **Pre-existing bug triage deep-dive (INFRA-06)** — gray area surfaced; default stance in CD-02 (fix all 3 with cost cap). Plan-phase will fan out one parallelizable triage plan; operator may pre-empt scope.
- **RUNBOOK.md format deep-dive** — default stance failure-triage-first (CD-03). Open to revision when researcher reads existing `docs/development/SETUP.md`.
- **Paper-trade <60s mechanics deep-dive** — default stance in CD-04 (force-signal endpoint + DB-row timing). Researcher may flag if `force-signal` doesn't already exist (then it's a new admin-endpoint task in the plan).
- **ML-on test variant** — default stance in CD-05 (nightly + manual; default suite is ML-off).
- **Tape grow / refresh policy beyond v1** — Phase 1 D-06 set "manual on demand". Phase 2 doesn't change that; surface during Phase 5 forward-paper-test if 7-day window proves too tight.
- **Parallel test-run isolation** (multiple devs concurrently) — not raised; deferred. Default: each dev's `pytest` boots its own stack on its own ports; if collision, follow-up plan adds a port-prefix env var.

### Reviewed Todos (not folded)
None — the cross-reference todo step returned 0 matches.

</deferred>

---

*Phase: 02-integration-test-suite-runbook*
*Context gathered: 2026-05-07*
