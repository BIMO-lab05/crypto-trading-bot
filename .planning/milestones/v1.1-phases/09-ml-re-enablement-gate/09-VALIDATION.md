---
phase: 9
slug: ml-re-enablement-gate
status: reconstructed
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-18
reconstructed_from:
  - 09-01-evidence-loop-driver-PLAN.md / 09-01-evidence-loop-driver-SUMMARY.md
  - 09-02-startup-auto-flip-PLAN.md / 09-02-startup-auto-flip-SUMMARY.md
  - 09-03-reason-enum-and-digest-PLAN.md / 09-03-SUMMARY.md
  - 09-VERIFICATION.md
  - 09-REVIEW.md
  - 09-SECURITY.md
---

# Phase 9 — Validation Strategy (Reconstructed)

> Per-phase validation contract reconstructed retroactively from the executed phase
> artifacts. Phase 9 shipped without an in-flight VALIDATION.md; this document
> codifies the automated sampling surface that already exists in tree and flags
> the items that remain operator-manual.

Phase goal recap: the ML on/off decision is driven by code and evidence, not human memory — `run_evidence_loop.py` manages ≥7-day evidence accrual + PSR-CI publish idempotently; trading-engine startup auto-flips `ENABLE_ML_PREDICTIONS` based on a DSR>0.95 evidence row within the last 14 days and reverts on stale/drop; every "ML disabled" event logs a structured reason from a fixed 5-member enum; Telegram digest aggregates daily counts.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x (+ pytest-asyncio, pytest-respx, pytest-timeout, pytest-cov) |
| **Service config files** | `services/trading-engine/pytest.ini`, `services/notification-service/pytest.ini`, repo-root `pytest.ini` |
| **Repo-root config** | `pytest.ini`, `pyproject.toml` |
| **Plan 09-01 quick command** | `PYTHONPATH=. python3 -m pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py --no-cov -q` |
| **Plan 09-02 quick command** | `cd services/trading-engine && PYTHONPATH=. python3 -m pytest tests/test_ml_gate_auto_flip.py --no-cov -q` |
| **Plan 09-03 quick command** | `cd services/trading-engine && PYTHONPATH=. python3 -m pytest tests/test_ml_gate_reasons.py tests/test_ml_gate_reasons_endpoint.py --no-cov -q && cd ../notification-service && python3 -m pytest tests/test_daily_digest_ml_gate.py tests/test_ml_gate_digest_scheduler.py --no-cov -q` |
| **Grep gates** | `PYTHONPATH=services/trading-engine python3 -m pytest tests/integration/test_mlgate_grep_gates.py tests/integration/test_mlgate_reason_grep_gate.py --no-cov -q` |
| **Full Phase 9 suite** | All four invocations above in sequence (~30 s total) |
| **Estimated runtime** | ~30 seconds for full Phase 9 surface |

### Container-vs-host execution notes (CLAUDE.md gotchas)

- **api-gateway tests must run inside the container** when touching FastAPI auth surfaces (host fastapi 0.136 returns 401 from HTTPBearer; container fastapi 0.109 returns 403). Phase 9 does not touch api-gateway routes directly — all Phase 9 tests are on trading-engine + notification-service + scripts/.
- **trading-engine lifespan tests** require module-isolation per file when run together at host level — prometheus `CollectorRegistry` collides because every test file that imports `app.main` re-registers `http_requests*` collectors. `test_preflight_lifespan.py` (Phase 8) + `test_mlgate_grep_gates.py` (Phase 9) both touch `app.main`; they pass individually or in the container, fail together at host. Documented in 09-VERIFICATION.md "Known Co-Execution Test Issue".
- **`test_mlgate_module_imports_at_main`** grep gate requires `cd services/trading-engine && PYTHONPATH=.` so `app.main` resolves AND a clean `.env` absent (or `_ENV_FILE=` override) — local `.env` has comma-separated `CORS_ORIGINS` which pydantic-settings tries to JSON-decode at `Settings()` instantiation. CI fresh checkout starts with no `.env`. Recommended follow-up (per 09-02-SUMMARY): add `working-directory: services/trading-engine` to the "Grep gates" step in `.github/workflows/preflight-live-readiness.yml`.
- **notification-service tests** run host-only without container indirection — no FastAPI version drift.

---

## Sampling Rate

- **After every task commit:** Run the per-test-file command for the file modified by that task (latency ~3–7 s).
- **After every plan wave:** Run the full Phase 9 suite (~30 s).
- **Before `/gsd-verify-work`:** Full suite must be green inside container for both trading-engine + notification-service (host-OK for scripts/forward_paper_test/tests).
- **Max feedback latency:** 30 seconds (full suite).

---

## Per-Plan Verification Map

### Plan 09-01 — Evidence Loop Driver (MLGATE-01)

| Task | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 migration 0002 | 1 | MLGATE-01 | T-09-01-02 (forged run_date — read-only, applies 7-day rule) | Adds `run_date TEXT` + `psr_ci_published INTEGER DEFAULT 0` + `idx_leaderboard_psr_published`; schema_version=2 row; idempotent re-apply against fresh DB from `0001_initial.sql` | unit (migration smoke) | `python3 -c "import sqlite3,tempfile; <apply 0001 then 0002 then read PRAGMA + schema_version>"` (covered as `test_evidence_loop_idempotent_two_runs` and `test_evidence_loop_empty_db` fixtures) | ✅ | ✅ green |
| 09-01-02 driver script | 1 | MLGATE-01 | T-09-01-01 (forged DSR row — driver UPDATEs only `psr_ci_published`); T-09-01-03 (sqlite3.Error path leak — log redacted to `type(e).__name__`); T-09-01-05 (LIVE-mode refusal) | `run_evidence_loop.py` orchestrator: idempotent ≥7-day accrual + per-feature PSR-CI publish; refuses `TRADING_MODE=LIVE` with exit 1; SELECT/UPDATE-only on `leaderboard`; reuses `psr_ci.compute_psr_with_bootstrap_ci` (no duplicate np.percentile path) | unit | `PYTHONPATH=. python3 -m pytest scripts/forward_paper_test/tests/test_run_evidence_loop.py --no-cov -q` (8 tests) | ✅ (8 tests) | ✅ green |
| 09-01-03 idempotency + resume | 1 | MLGATE-01 | T-09-01-02 | `test_evidence_loop_idempotent_two_runs` + `test_evidence_loop_resume_from_partial_state` + `test_evidence_loop_two_runs_same_row_count` prove two-run-same-count invariant; resume from last persisted row honoured | unit | (subset of above) | ✅ | ✅ green |
| 09-01-04 LIVE-mode refusal | 1 | MLGATE-01 | T-09-01-05 | `_check_paper_mode_precondition` refuses LIVE; `sys.exit(1)` on TRADING_MODE=LIVE; stderr message | behavioral | `TRADING_MODE=LIVE python3 -m scripts.forward_paper_test.run_evidence_loop --db-path /tmp/none.db --dry-run; test $? -eq 1` (covered by `test_refuses_live`) | ✅ | ✅ green |
| 09-01-05 CLI flags | 1 | MLGATE-01 | T-09-01-04 (DoS — synchronous; no daemon); T-09-01-06 (fake returns_source — developer-only) | `--dry-run`, `--db-path`, `--returns-source` flags work; `--help` exits 0 | behavioral | `PYTHONPATH=. python3 -m scripts.forward_paper_test.run_evidence_loop --help` (covered as `test_dry_run` + `test_evidence_loop_empty_db`) | ✅ | ✅ green |

### Plan 09-02 — Startup Auto-flip (MLGATE-02)

| Task | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-02-01 `auto_flip_ml_predictions()` | 2 | MLGATE-02 | T-09-02-01 (forged DSR — SELECT-only); T-09-02-02 (future-dated run_date — 14-day staleness vs injectable now) | `services/trading-engine/app/lifespan/ml.py` adds module-scope `auto_flip_ml_predictions()` invoked at start of `init_ml()` before aggregator construction; reads via `check_dsr_evidence(now=now)` extended with 14-day staleness + `psr_ci_published=1` filter | unit | `cd services/trading-engine && PYTHONPATH=. python3 -m pytest tests/test_ml_gate_auto_flip.py --no-cov -q` (8 def / 10 invocations) | ✅ (10 tests) | ✅ green |
| 09-02-02 5-branch decision | 2 | MLGATE-02 | T-09-02-01, T-09-02-02 | All 5 disabled-event branches reachable: `dsr_above_gate` (enabled), `no_evidence`, `dsr_below_gate`, `evidence_stale`, `manual_override` (override path); test parametrised × 3 | unit | (subset of above) | ✅ | ✅ green |
| 09-02-03 MLGATE_AUTO_FLIP log emission | 2 | MLGATE-02 | T-09-02-03 (operator removes log — grep gate); SC#2 (literal `MLGATE_AUTO_FLIP direction={direction} reason={reason}` at CRITICAL) | `logger.critical(f"MLGATE_AUTO_FLIP direction={direction} reason={reason}")` at `lifespan/ml.py:167`; log-first-then-mutate ordering honoured | unit | (covered by `test_auto_flip_logs_enabled_when_dsr_above_gate` + `test_auto_flip_logs_disabled_when_no_evidence`) | ✅ | ✅ green |
| 09-02-04 marker JSON write | 2 | MLGATE-02 | T-09-02-04 (DSR value disclosure — public-grade); T-09-02-05 (read-only mount crashes boot — wrapped try/except OSError) | `/run/mlgate_auto_flip.json` payload: 6 fields (`schema_version=1, direction, reason, evaluated_at, dsr_value, run_date`); best-effort write; failure logs warning + continues | unit | `test_auto_flip_marker_write_failure_does_not_raise` + `test_auto_flip_writes_marker_with_schema_v1` | ✅ | ✅ green |
| 09-02-05 cross-plan reason propagation | 2 | MLGATE-02 ↔ MLGATE-03 | T-09-02-07 (set_current_reason raises — best-effort try/except) | Auto-flip outcome propagated via `from app.aggregation.ml_gate_reasons import set_current_reason` → cached for Plan 09-03's `log_ml_disabled` default | unit | `test_auto_flip_does_not_crash_when_set_current_reason_raises` + cross-plan tests in `test_ml_gate_reasons.py` | ✅ | ✅ green |
| 09-02-06 CI grep gate | 2 | MLGATE-02 | T-09-02-03 | `test_mlgate_auto_flip_log_exists` — dual-form scan (pathlib rglob + subprocess grep) scoped to `services/trading-engine/app/`; diagnostic message self-avoidance via `_TOKEN_HEAD + _TOKEN_TAIL` | static (grep gate) | `PYTHONPATH=services/trading-engine python3 -m pytest tests/integration/test_mlgate_grep_gates.py --no-cov -q` (2 tests) | ✅ | ✅ green |

### Plan 09-03 — Reason Enum + Telegram Digest (MLGATE-03)

| Task | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-03-01 5-member enum | 2 | MLGATE-03 | T-09-03-01 (enum drift — ValueError on unknown reason) | `services/trading-engine/app/aggregation/ml_gate_reasons.py` defines `ML_GATE_REASONS` tuple (5 members: `no_evidence, dsr_below_gate, evidence_stale, regime_shift, manual_override`); `log_ml_disabled` raises ValueError on unknown reason | unit | `cd services/trading-engine && PYTHONPATH=. python3 -m pytest tests/test_ml_gate_reasons.py --no-cov -q` (14 def / 22 invocations) | ✅ (22 tests) | ✅ green |
| 09-03-02 cross-plan cache | 2 | MLGATE-03 | T-09-02-07 (auto-flip best-effort propagation) | `set_current_reason`/`get_current_reason` exported; default `"manual_override"`; populated by Plan 09-02 outcome | unit | (subset of above; specifically `test_all_five_reasons_reachable_via_set_current_reason`) | ✅ | ✅ green |
| 09-03-03 emission sites | 2 | MLGATE-03 | T-09-03-02 (symbol/interval disclosure — accept); T-09-03-03 (log flood — ≥30s cadence accept); T-09-03-06 (operator removes call — grep gate) | `enhanced_aggregator.py` emits at 2 sites (lines 88, 143); `signal_aggregator.py` emits on fallback Phase-1 path (line 1141); all via `log_ml_disabled(reason=, detail=)` | unit | covered by `test_ml_gate_reasons.py::test_log_ml_disabled_includes_reason_and_detail` + reachability tests | ✅ | ✅ green |
| 09-03-04 endpoint /api/preflight/ml-gate-reason-counts | 2 | MLGATE-03 | T-09-03-07 (unauth disclosure — D-09 carryforward); T-09-03-09 (mutation — GET-only) | `services/trading-engine/app/handlers/ml_gate_reasons.py` GET-only router returning `snapshot_reasons()` dict; mounted `main.py:494` | integration (route) | `cd services/trading-engine && PYTHONPATH=. python3 -m pytest tests/test_ml_gate_reasons_endpoint.py --no-cov -q` (3 tests) | ✅ (3 tests) | ✅ green |
| 09-03-05 notification-service scheduler | 2 | MLGATE-03 | T-09-03-08 (slow trading-engine — `httpx.AsyncClient(timeout=5.0)` + graceful degradation); T-09-03-05 sub-(b) (scheduler bypasses admin guard via in-process call) | `services/notification-service/app/scheduler/ml_gate_digest.py`: `fetch_and_dispatch_digest`, `_scheduler_loop`, `start_scheduler`; 5s timeout; graceful degradation on 4xx/5xx/ConnectError; calls `alert_manager.send_daily_summary` in-process (not via HTTP) | unit + integration | `cd services/notification-service && python3 -m pytest tests/test_ml_gate_digest_scheduler.py --no-cov -q` (4 tests) | ✅ (4 tests) | ✅ green |
| 09-03-06 send_daily_summary digest render | 2 | MLGATE-03 | T-09-03-04 (canonical order drift — unit test enforces canonical tuple on notification side) | `services/notification-service/app/alert_manager.py:680-733` extended with `ml_gate_reason_counts` kwarg + canonical-ordered render; metadata propagation when dict non-None | unit | `cd services/notification-service && python3 -m pytest tests/test_daily_digest_ml_gate.py --no-cov -q` (7 tests) | ✅ (7 tests) | ✅ green |
| 09-03-07 admin guard on /daily-summary (T-09-03-05 sub-(a)) | 2 | MLGATE-03 (security overlay) | T-09-03-05 | `services/notification-service/app/auth.py::verify_admin_key` reads `X-Admin-Key` header vs `config.admin_api_key`; empty server-side key returns 500 (deploy-without-secret footgun closed); wired into `routers/alerts.py:456` `_admin: str = Depends(verify_admin_key)` on `send_daily_summary` | integration (auth) | `cd services/notification-service && python3 -m pytest tests/test_daily_summary_auth.py --no-cov -q` (5 tests: missing-header→401, invalid-key→403, valid-key→200, unconfigured-server→500, scheduler-path-pin) | ✅ (5 tests) | ✅ green |
| 09-03-08 reason-field CI grep gate | 2 | MLGATE-03 | T-09-03-06 | `test_mlgate_reason_field_present` — every literal `"ML predictions disabled"` in `services/trading-engine/app/` carries `reason=` field; offender count = 0 | static (grep gate) | `PYTHONPATH=services/trading-engine python3 -m pytest tests/integration/test_mlgate_reason_grep_gate.py --no-cov -q` (2 tests) | ✅ | ✅ green |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Aggregate Test Surface

| Layer | File | Defs | Invocations | Notes |
|-------|------|------|-------------|-------|
| Unit (driver) | `scripts/forward_paper_test/tests/test_run_evidence_loop.py` | 8 | 8 | Idempotency, accrual window, resume, two-run-same-count, LIVE refusal, empty DB, dry-run |
| Unit (auto-flip) | `services/trading-engine/tests/test_ml_gate_auto_flip.py` | 8 | 10 | 5 disabled-event branches (parametrised × 3) + marker write + set_current_reason failure tolerance + reason-state propagation |
| Unit (reason enum) | `services/trading-engine/tests/test_ml_gate_reasons.py` | 14 | 22 | ValueError on unknown reason, cross-plan cache, 5-reason reachability (explicit + cached), emission-site reachability |
| Route | `services/trading-engine/tests/test_ml_gate_reasons_endpoint.py` | 3 | 3 | Snapshot dict shape, unauth GET, GET-only (no POST/PUT/DELETE) |
| Unit (digest template) | `services/notification-service/tests/test_daily_digest_ml_gate.py` | 7 | 7 | Backward compat (None kwarg), section render, canonical order, all-5 render, metadata behavior |
| Integration (scheduler) | `services/notification-service/tests/test_ml_gate_digest_scheduler.py` | 4 | 4 | Happy path (respx-mocked), ConnectError, HTTP 500, non-dict body |
| Auth | `services/notification-service/tests/test_daily_summary_auth.py` | 5 | 5 | Missing-header→401, invalid-key→403, valid-key→200, unconfigured-server→500, scheduler-path pin (T-09-03-05 closure) |
| Grep gate (auto-flip) | `tests/integration/test_mlgate_grep_gates.py` | 2 | 2 | MLGATE_AUTO_FLIP log literal survival + module-import survival |
| Grep gate (reason field) | `tests/integration/test_mlgate_reason_grep_gate.py` | 2 | 2 | Every `"ML predictions disabled"` carries `reason=` + dual-form scan |
| **Total** | **9 files** | **53** | **63** | Floor (≥30 across phase) exceeded |

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

Pytest is pre-installed across all services; per-service `pytest.ini` files in tree; conftest fixtures for `test_client`, async patterns, Pydantic Settings overrides, respx mocking, and prometheus registry isolation already present. No framework install was required for Phase 9.

Plan 09-01 installed no new dev dependencies. Plan 09-02 added prometheus registry workaround per local feedback `feedback_main_imports_autoflake.md`. Plan 09-03 reuses `pytest-respx` (already in `pytest.ini`) for scheduler integration tests.

---

## Manual-Only Verifications

| # | Behavior | Requirement | Why Manual | Test Instructions |
|---|----------|-------------|------------|-------------------|
| 1 | **Real Telegram delivery** of daily digest with non-empty `ml_gate_reason_counts` | MLGATE-03 | SC#4 acceptance per ROADMAP is "format confirmed by unit test reading rendered message template" — already satisfied by 7 `test_daily_digest_ml_gate.py` tests. Actual Telegram dispatch is runtime configuration (chat_id + bot token) outside Phase 9 scope. | (a) Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in notification-service env. (b) Seed `_counter` with `set_current_reason('dsr_below_gate')` + emit `log_ml_disabled` × 3. (c) Trigger `_scheduler_loop` (or wait 24h cadence). (d) Observe message in Telegram chat with `ML Gate Reasons (24h):` section in canonical order. |
| 2 | **`/api/preflight/ml-gate-reason-counts` reachability through deployed trading-engine** after image rebuild | MLGATE-03 | Endpoint mounted in source (`main.py:494`); current deployed container was built before this branch. Live curl needs operator-driven rebuild that can't run while the verifier holds the paper stack. | (a) `docker compose -f docker-compose.unified.yml up -d --build trading-engine`. (b) `curl -s http://localhost:8005/api/preflight/ml-gate-reason-counts | jq -e '.reasons | length == 5'` (exit 0). (c) Repeat after `log_ml_disabled('no_evidence', 'test')` invocation and confirm `.reasons.no_evidence` increments. |
| 3 | **Cross-service in-process pin (T-09-03-05 sub-(b))** under live scheduler firing | MLGATE-03 | `test_scheduler_path_does_not_hit_admin_guarded_endpoint` pins the contract statically (asserts `httpx.post('/daily-summary')` never appears in `ml_gate_digest.py`). Runtime confirmation against a real notification-service container is operator territory. | (a) Add `- ADMIN_API_KEY=${ADMIN_API_KEY}` to `docker-compose.unified.yml` notification-service env block; set `ADMIN_API_KEY` in `.env`. (b) `docker compose up -d --build notification-service trading-engine`. (c) `docker exec crypto-bot-notification python3 -c "from app.scheduler.ml_gate_digest import _scheduler_loop; <invoke>"`. (d) `docker logs crypto-bot-notification 2>&1 | grep 'ml-gate-reason-counts'` should appear; no log line `POST /api/v1/alerts/daily-summary`. |
| 4 | **First green CI run of `preflight-live-readiness.yml` grep-gates step** after adding `working-directory: services/trading-engine` | MLGATE-02 | `test_mlgate_module_imports_at_main` requires `cd services/trading-engine && PYTHONPATH=.`. SUMMARY 09-02 flagged the follow-up. Operator must add `working-directory` to the workflow's "Grep gates" step then push a PR. Blocked on OP-04 billing for actual green-run evidence. | (a) Edit `.github/workflows/preflight-live-readiness.yml` `Grep gates` step to add `working-directory: services/trading-engine`. (b) Push to a branch + open a PR. (c) Wait for billing recovery (OP-04) + observe green job. (d) Phase 12 CIRESTORE-02 will track the URL. |

---

## Test-Environment Notes (host-only quirks; not coverage gaps)

These document the environmental conditions under which the existing tests are guaranteed to pass. They do **not** indicate missing tests or coverage gaps.

1. **Prometheus `CollectorRegistry` collision** when `test_preflight_lifespan.py` (Phase 8) + `test_mlgate_grep_gates.py` (Phase 9) run in the same pytest invocation. Symptom: `ValueError: Duplicated timeseries in CollectorRegistry: {'http_requests', 'http_requests_total', 'http_requests_created'}` at setup. Workarounds: (a) run each test file separately; (b) run inside `crypto-bot-trading` container (per-process registry); (c) add `prometheus_client.REGISTRY` reset autouse fixture in `services/trading-engine/tests/conftest.py` (recommended future cleanup; out of Phase 9 scope). Documented in 09-VERIFICATION.md "Known Co-Execution Test Issue".

2. **PYTHONPATH gap for `test_mlgate_module_imports_at_main`** — requires `cd services/trading-engine && PYTHONPATH=.` and a clean `.env` absent (or `_ENV_FILE=` override). Local `.env` has comma-separated `CORS_ORIGINS` which pydantic-settings JSON-decodes at `Settings()` instantiation. CI fresh checkout has no `.env`. Recommended workflow change documented in Manual-Only #4 above.

3. **Wording drift documented in 09-VERIFICATION.md** — REQUIREMENTS.md spec wording references `tournament_results` table + `technical-analysis` service emissions; implementation correctly reads `leaderboard` + emits from `trading-engine` per D-09-01-01 / D-09-02-05 / D-09-03-01. Not a test gap — DOCS-only follow-up identical to Phase 8's PREFLIGHT wording drift.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify OR are documented as manual-only with explicit operator-step instructions
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (53 def / 63 pytest invocations across the phase)
- [x] Wave 0 covers all MISSING references — none required, existing infrastructure sufficient
- [x] No watch-mode flags
- [x] Feedback latency < 30 s (full Phase 9 suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-18 (reconstructed retroactively; no in-flight VALIDATION existed for Phase 9 — this is the first formal validation contract)

---

## Validation Audit 2026-05-18

| Metric | Count |
|--------|-------|
| Requirements in scope | 3 (MLGATE-01..03) |
| Requirements with automated test coverage | 3 / 3 |
| Gaps found (MISSING tests) | 0 |
| Gaps resolved by this audit | 0 |
| Escalated to Manual-Only | 4 (Telegram delivery, deployed-image curl, in-process pin under live scheduler, CI workflow `working-directory` follow-up) |
| Host-environment notes (not gaps) | 3 (prometheus collision, PYTHONPATH/CORS quirks, REQUIREMENTS.md wording drift) |
| Tests added | 0 — existing 53 test definitions cover all 3 requirements |
| Cross-reference | 09-VERIFICATION.md (5/5 SCs verified), 09-SECURITY.md (22/22 threats CLOSED), 09-REVIEW.md (6 warnings, 0 critical) |

**Verdict:** Phase 9 is **Nyquist-compliant**. All three MLGATE requirements have automated test coverage in tree (8 driver + 10 auto-flip + 22 reason-enum + 3 endpoint + 7 digest template + 4 scheduler + 5 auth + 2 + 2 grep gates = 53 test definitions / 63 pytest invocations across 9 files). The four manual-only items are operator-driven runtime confirmations (real Telegram delivery, deployed-image curl, live scheduler in-process pin, CI workflow `working-directory` follow-up); none represent missing automated coverage. No new tests required; reconstruction confirms the validation surface was sufficient at execution time.
