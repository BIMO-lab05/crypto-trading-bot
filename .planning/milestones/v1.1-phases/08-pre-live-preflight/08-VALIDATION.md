---
phase: 8
slug: pre-live-preflight
status: reconstructed
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-18
reconstructed_from:
  - 08-CONTEXT.md
  - 08-01-PLAN.md / 08-01-SUMMARY.md
  - 08-02-PLAN.md / 08-02-SUMMARY.md
  - 08-03-PLAN.md / 08-03-SUMMARY.md
  - 08-04-PLAN.md / 08-04-SUMMARY.md
  - 08-05-PLAN.md / 08-05-SUMMARY.md
  - 08-VERIFICATION.md
---

# Phase 8 — Validation Strategy (Reconstructed)

> Per-phase validation contract reconstructed retroactively from the executed phase
> artifacts. Phase 8 shipped without an in-flight VALIDATION.md; this document
> codifies the automated sampling surface that already exists in tree and flags
> the items that remain operator-manual (HV1, HV2) or externally blocked
> (PREFLIGHT-03 first green run — Phase 12 CIRESTORE-02 / OP-04 billing).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x (+ pytest-asyncio, pytest-cov, pytest-respx, pytest-timeout) |
| **Service config files** | `services/trading-engine/pytest.ini`, `services/api-gateway/pytest.ini`, repo-root `pytest.ini` |
| **Repo-root config** | `pytest.ini`, `pyproject.toml` |
| **Quick run command** | `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py tests/test_preflight_route.py tests/test_preflight_lifespan.py --no-cov -q` |
| **Grep-gate command (repo root)** | `PYTHONPATH=services/trading-engine python3 -m pytest tests/integration/test_preflight_grep_gates.py --no-cov -q` |
| **Gateway-proxy command** | `cd services/api-gateway && python3 -m pytest tests/test_preflight_proxy.py --no-cov -q` |
| **Full preflight suite** | All four invocations above in sequence (~30s total) |
| **Estimated runtime** | ~30 seconds for full preflight surface |

### Container-vs-host execution notes (CLAUDE.md gotcha)

- **api-gateway tests must run inside the container** (`docker exec crypto-bot-api-gateway pytest tests/test_preflight_proxy.py`). Host pip has fastapi 0.136 (HTTPBearer→401); deployed container pins fastapi 0.109 (→403). The preflight proxy route is unauthenticated so the 401-vs-403 drift does not break preflight tests on host, but other suites in the same file may flake. SUMMARY 08-02 records a host run after `pip --break-system-packages install python-jose`.
- **trading-engine lifespan tests** require module-isolation per file when run together at host level — prometheus `CollectorRegistry` collides because every test file that imports `app.main` re-registers the `http_requests*` collectors. Pass either by running each file separately, by running inside `crypto-bot-trading` container, or with a `prometheus_client.REGISTRY` reset fixture. Tests pass individually; this is a known multi-file-host limitation, not a coverage gap.
- **Grep-gate `test_preflight_module_imports_at_lifespan`** needs `PYTHONPATH=services/trading-engine` (so `app.main` resolves) AND a clean `.env` absent (or `_ENV_FILE=` override) — the local `.env` has comma-separated `CORS_ORIGINS` which pydantic-settings tries to JSON-decode at `Settings()` instantiation. CI fresh checkout starts with no `.env`, so this is host-developer-environment-only.

---

## Sampling Rate

- **After every task commit:** Run the per-test-file command for the file modified by that task (latency ~5–7s).
- **After every plan wave:** Run the full preflight suite (~30s).
- **Before `/gsd-verify-work`:** Full suite must be green inside container for both trading-engine + api-gateway.
- **Max feedback latency:** 30 seconds (full suite, in-container).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 01 | 1 | PREFLIGHT-01 | T-08-01-05 (info disclosure — `CheckResult.detail` strings carry config values, not secrets) | Frozen dataclasses serialise to JSON-safe `schema_version=1` shape with `PASS/FAIL/UNKNOWN` literal status; cannot be mutated post-construction. | unit | `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py::test_check_cap_paper_allows_10pct tests/test_preflight_checks.py::test_dsr_fixture_schema_matches_production --no-cov -q` | ✅ | ✅ green |
| 08-01-02 | 01 | 1 | PREFLIGHT-01 | T-08-01-01 (sqlite injection — bound params); T-08-01-02 (WSL bind-mount false-FAIL); T-08-01-03 (MLGATE marker tamper — accepted) | `check_dsr_evidence` uses bound-param SQL on `leaderboard` (no string interpolation); `check_emergency_stop` uses `.is_file()` not `.exists()` (directory at path passes); `check_cap` enforces 2% only in LIVE branch (PAPER skipped per ADR-010). | unit | `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py --no-cov -q` (23 tests) | ✅ | ✅ green |
| 08-01-03 | 01 | 1 | PREFLIGHT-01 | T-08-01-06 (fixture schema drift) | Test fixture mirrors production `leaderboard` schema (`tournament_start_ts TEXT NOT NULL`); `test_dsr_fixture_schema_matches_production` source-inspects the file to catch future INTEGER regression. | unit | `cd services/trading-engine && python3 -m pytest tests/test_preflight_checks.py::test_dsr_fixture_schema_matches_production --no-cov -q` | ✅ | ✅ green |
| 08-02-01 | 02 | 2 | PREFLIGHT-01 | T-08-02-05 (CLI dry-run reads `.env.example` from git — accepted; committed, not secret); T-08-02-06 (no privileged escalation) | CLI exits 0 on PASS, 1 on FAIL/UNKNOWN, 2 on bad args; `--dry-run --target=<ref>` reads `.env.example` via `git show`, overlays filtered env onto `os.environ`, calls `reload_settings()`, restores in finally. Filter set is the 6 preflight-relevant keys only. | behavioral (CLI smoke) | `python3 scripts/preflight_live.py --json && python3 scripts/preflight_live.py --check=cap --json && python3 scripts/preflight_live.py --check=bogus; test $? -eq 2` | ✅ | ✅ green (08-02 SUMMARY recorded live spot-check from /tmp; exit-code semantics verified) |
| 08-02-02 | 02 | 2 | PREFLIGHT-01 | T-08-02-01 (D-09 unauthenticated GET — accepted, config-only disclosure); T-08-02-03 (no state change — accepted) | `GET /api/preflight/live-readiness` returns `schema_version=1` body with 6 checks; unauthenticated; surfaces `HTTPException(500)` on internal error (does NOT silently PASS). | unit (route) | `cd services/trading-engine && python3 -m pytest tests/test_preflight_route.py --no-cov -q` (3 tests) | ✅ | ✅ green |
| 08-02-03 | 02 | 2 | PREFLIGHT-01 | T-08-02-02 (proxy must never PASS-fallback on failure — load-bearing); T-08-02-04 (UNKNOWN-leak by design) | api-gateway proxy returns trading-engine body verbatim on 200; on any failure (exception, non-200) returns `overall=UNKNOWN` with all 6 checks UNKNOWN — **never PASS**. Unauthenticated. | unit (proxy) | `cd services/api-gateway && python3 -m pytest tests/test_preflight_proxy.py --no-cov -q` (4 tests) | ✅ | ✅ green |
| 08-03-01 | 03 | 2 | PREFLIGHT-02 | T-08-03-04 (LIVE-cap elevation — mitigated by boot-time gate); T-08-03-05 (cap value disclosure — accepted, not secret) | Lifespan refuses LIVE boot when `max_risk_per_trade > 0.02`; emits `CRITICAL` log literal `LIVE_PREFLIGHT_REJECTED reason=cap_too_high cap={cap} limit=0.02` and raises `RuntimeError`. PAPER mode unaffected per ADR-010. | source-inspection + integration (lifespan) | `cd services/trading-engine && python3 -m pytest tests/test_preflight_lifespan.py::test_lifespan_source_contains_cap_check tests/test_preflight_lifespan.py::test_lifespan_rejects_live_with_high_cap tests/test_preflight_lifespan.py::test_lifespan_accepts_live_with_strict_cap tests/test_preflight_lifespan.py::test_lifespan_paper_mode_skips_cap_check --no-cov -q` | ✅ | ✅ green (in isolation or in-container; multi-file host run hits prometheus REGISTRY collision — known env limitation) |
| 08-03-02 | 03 | 2 | PREFLIGHT-02 | T-08-03-07 (drift between inline lifespan threshold and `check_cap()` — mitigated by boundary-agreement test) | Inline lifespan check (`main.py:271`) and `app.preflight.check_cap()` produce the same verdict for the same `Settings(...)` at 0.0200 (both PASS) and 0.0201 (both FAIL). Test fails with `DRIFT DETECTED` message if either threshold changes. | integration (parametrised) | `cd services/trading-engine && python3 -m pytest "tests/test_preflight_lifespan.py::test_lifespan_and_check_cap_agree_at_boundary" --no-cov -q` (2 parametrised cases) | ✅ | ✅ green (in isolation) |
| 08-03-03 | 03 | 2 | PREFLIGHT-02 | T-08-03-01 (silent removal of log emission); T-08-03-02 (autoflake strips preflight import); T-08-03-03 (refactor moves cap-check out of lifespan body) | Grep gate #1 fails if `LIVE_PREFLIGHT_REJECTED` literal removed from `services/trading-engine/app/` (scope strictly TE_APP, not REPO_ROOT). Grep gate #2 fails if `from app.preflight import` removed from `services/trading-engine/app/main.py`. Manual failure-mode verified during execution (08-03 SUMMARY). | static (grep gate) | `PYTHONPATH=services/trading-engine python3 -m pytest tests/integration/test_preflight_grep_gates.py --no-cov -q` (2 tests) | ✅ | ✅ green for `test_live_preflight_rejected_log_exists`; second test requires `PYTHONPATH` AND clean `.env` at host (CI fresh-checkout clean) — green in container/CI |
| 08-04-01 | 04 | 3 | PREFLIGHT-03 | T-08-04-01 (action supply-chain — mitigated by `@v4`/`@v5` pins); T-08-04-02 (label bypass — accepted; unit-tests run on all PRs); T-08-04-05 (DoS — mitigated by concurrency cancel-in-progress) | Workflow file parses as valid GitHub Actions YAML; `unit-tests` job always runs; `gate` job has `needs: unit-tests` AND `if: contains(github.event.pull_request.labels.*.name, 'live: requested')`; action versions pinned; `fetch-depth: 0` so `git show HEAD:.env.example` resolves in shallow CI clones. | static (YAML schema + grep) | `python3 -c "import yaml; d = yaml.safe_load(open('.github/workflows/preflight-live-readiness.yml')); assert d['jobs']['gate']['needs']=='unit-tests'; assert 'live: requested' in d['jobs']['gate']['if']"` plus the 8 grep assertions in 08-04 SUMMARY | ✅ | ✅ green for structural validation; **first green CI run deferred to Phase 12 CIRESTORE-02** (blocked on OP-04 GH Actions billing) — see Manual-Only #3 |
| 08-05-01 | 05 | 1 | PREFLIGHT-04 | T-08-05-01 (n/a — pure docs, no STRIDE surface); T-08-05-02 (info disclosure — accepted, env-var names only) | RUNBOOK.md gains `## Pre-LIVE Operator Checklist` section with 6 Diagnose/Action/Verification sub-sections (one per precondition); each references its `python3 scripts/preflight_live.py --check=<name>` invocation; Index TOC entry present. | static (grep) | `test "$(grep -c '^## Pre-LIVE Operator Checklist' RUNBOOK.md)" = "1" && test "$(grep -c '^### Precondition ' RUNBOOK.md)" = "6" && grep -q 'I_UNDERSTAND_REAL_MONEY' RUNBOOK.md && grep -q 'LIVE_PREFLIGHT_REJECTED' RUNBOOK.md` | ✅ | ✅ green |
| 08-05-02 | 05 | 1 | PREFLIGHT-04 | T-08-05-01 (n/a) | `.planning/PROJECT.md` `### Out of Scope` adds one sub-bullet under the LIVE-default entry linking to `../RUNBOOK.md#pre-live-operator-checklist`. | static (grep) | `grep -q 'RUNBOOK.md#pre-live-operator-checklist' .planning/PROJECT.md && grep -q 'Pre-LIVE Operator Checklist' .planning/PROJECT.md` | ✅ | ✅ green |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Aggregate test surface

| Layer | File | Count | Notes |
|-------|------|-------|-------|
| Unit (check fns) | `services/trading-engine/tests/test_preflight_checks.py` | 23 | Frozen dataclass shape, 6 check fns × PASS/FAIL/UNKNOWN paths, run_all ordering + precedence, fixture-schema meta-test |
| Route | `services/trading-engine/tests/test_preflight_route.py` | 3 | Schema_v1 body, D-09 no-auth, 500-on-internal-error |
| Lifespan | `services/trading-engine/tests/test_preflight_lifespan.py` | 5 def / 6 invocations | Source-inspection guard, LIVE+0.03 reject, LIVE+0.02 accept, PAPER skip, boundary-agreement (×2 parametrised) |
| Proxy | `services/api-gateway/tests/test_preflight_proxy.py` | 4 | Verbatim pass-through, unreachable→UNKNOWN, non-200→UNKNOWN, D-09 no-auth |
| Grep gates | `tests/integration/test_preflight_grep_gates.py` | 2 | Log literal survival, preflight-import survival |
| **Total** |  | **37 def / 40 invocations** | Meets Phase 8 plan-aggregate floor (≥30 across phase) |

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

Pytest is pre-installed across all services; per-service `pytest.ini` files in tree; conftest fixtures for `test_client`, `admin_client`, async patterns, and Pydantic Settings overrides already present. No framework install was required for Phase 8.

The Phase 8 plans installed no new dev dependencies. Three host-only `pip --break-system-packages` deps were used during execution (`tensorflow-cpu`, `respx`, `aiohttp`, `python-jose`) per `feedback_local_test_setup.md`; these are not Phase 8 requirements but documented as the host-run path for operators replicating SUMMARY 08-02's local proxy-test run.

---

## Manual-Only Verifications

| # | Behavior | Requirement | Why Manual | Test Instructions |
|---|----------|-------------|------------|-------------------|
| 1 | **Container-restart smoke for boot-time cap-check** (ROADMAP SC #3, CLAUDE.md "Verification standards") | PREFLIGHT-02 | Lifespan tests exercise the same predicate inside `pytest.raises`, but ROADMAP SC #3 explicitly says "container startup" and CLAUDE.md requires real-restart proof + live log line in container logs after any config change. SUMMARY 08-03 records a partial in-container `docker exec` smoke confirming the predicate; full rebuild + restart cycle is the operator's call. | (a) Set `.env`: `TRADING_MODE=LIVE`, `MAX_RISK_PER_TRADE=0.03`, `LIVE_TRADING_ACK=I_UNDERSTAND_REAL_MONEY`. (b) Rebuild trading-engine: `docker compose -f docker-compose.unified.yml build trading-engine`. (c) `docker compose -f docker-compose.unified.yml up trading-engine` and observe container exits non-zero. (d) `docker logs crypto-bot-trading 2>&1 \| grep "LIVE_PREFLIGHT_REJECTED reason=cap_too_high cap=0.03 limit=0.02"` must return the line. (e) **REVERT `.env`** to paper-trading defaults (`MAX_RISK_PER_TRADE=0.10`, `TRADING_MODE=PAPER`, remove `LIVE_TRADING_ACK` or set to non-sentinel) before resuming normal operation. |
| 2 | **End-to-end HTTP reachability through api-gateway** (ROADMAP SC #2) | PREFLIGHT-01 | Route is mounted in source (`services/trading-engine/app/main.py:481`), but the currently deployed container was built before this branch; the live image does not yet expose the route. Live curl needs a rebuild that the verifier cannot do without disrupting the running paper stack. | (a) Rebuild + restart both services: `docker compose -f docker-compose.unified.yml up -d --build trading-engine api-gateway`. (b) Direct port check: `curl -s http://localhost:8005/api/preflight/live-readiness \| jq -e '.schema_version == 1 and (.checks \| length) == 6'` (exit 0). (c) Gateway proxy check: `curl -s http://localhost:8000/api/preflight/live-readiness \| jq -e '.schema_version == 1 and (.checks \| length) == 6'` (exit 0). (d) Both URLs without auth headers (D-09). (e) Negative test: `docker compose -f docker-compose.unified.yml stop trading-engine && curl -s http://localhost:8000/api/preflight/live-readiness \| jq -e '.overall == "UNKNOWN"'` (exit 0; graceful degradation, not 5xx). Restart trading-engine after. |
| 3 | **First green CI run of `.github/workflows/preflight-live-readiness.yml`** (ROADMAP SC #4, PREFLIGHT-03) | PREFLIGHT-03 | Phase 8 ships the workflow YAML and the local-CLI smoke confirms `python3 scripts/preflight_live.py --dry-run --target=HEAD --json` works. **First actual CI invocation is gated on Phase 12 CIRESTORE-02**, which is blocked on `OP-04` (GitHub Actions billing restoration). Phase 8's deliverable is file existence + structural validation, not live CI evidence. | Open any PR that touches a Phase 8 path against `main` or `develop`. Verify the `Preflight Live-Readiness Gate / unit-tests` check appears in the PR Checks tab and turns green. Add label `live: requested` to that PR; verify the `gate` job becomes required, runs the dry-run CLI invocation, and either passes or fails per the snapshot in `.env.example`. **Cannot execute until OP-04 is resolved** — track under Phase 12 CIRESTORE-02. |

---

## Test-Environment Notes (host-only quirks; not coverage gaps)

These are reliability notes for operators reproducing the suite on a development host. They do **not** indicate missing tests or coverage gaps — they document the environmental conditions under which the existing tests are guaranteed to pass.

1. **Prometheus `CollectorRegistry` collision when multiple lifespan-importing test files run together at host level.** Symptom: `ValueError: Duplicated timeseries in CollectorRegistry: {'http_requests', 'http_requests_total', 'http_requests_created'}` in test setup. Cause: each test file that imports `app.main` re-registers the metrics. Workarounds: (a) run each test file separately; (b) run inside `crypto-bot-trading` container where prometheus registry is per-process and not multi-file-test-polluted; (c) add a `prometheus_client.REGISTRY` reset autouse fixture in `services/trading-engine/tests/conftest.py` (recommended future cleanup; out of Phase 8 scope).

2. **`test_preflight_module_imports_at_lifespan` host pre-conditions.** Requires `PYTHONPATH=services/trading-engine` so `app.main` resolves AND the working directory to be clean of a non-JSON-formatted `.env` `CORS_ORIGINS` field (pydantic-settings JSON-decodes list-typed env vars). CI fresh-checkout has no `.env`, so this is host-developer-environment-only. Workaround for host runs: `cd /tmp && PYTHONPATH=/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine python3 -m pytest /mnt/d/Bimo_max/crypto-trading-bot/tests/integration/test_preflight_grep_gates.py --no-cov` (no `.env` in `/tmp`).

3. **api-gateway test host-vs-container fastapi version drift.** Tests in `services/api-gateway/tests/` may show spurious 401-vs-403 failures on host due to `HTTPBearer.auto_error` behavior change between fastapi 0.109 (container pin) and 0.136 (host pip). The preflight proxy route is **unauthenticated**, so `test_preflight_proxy.py` is unaffected — host run is green. Other api-gateway suites should run inside the container.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify OR are documented as manual-only with explicit operator-step instructions
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (37 def / 40 pytest invocations across the phase)
- [x] Wave 0 covers all MISSING references — none required, existing infrastructure sufficient
- [x] No watch-mode flags
- [x] Feedback latency < 30s (full preflight suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-18 (reconstructed retroactively; no in-flight VALIDATION existed for Phase 8 — this is the first formal validation contract)

---

## Validation Audit 2026-05-18

| Metric | Count |
|--------|-------|
| Requirements in scope | 4 (PREFLIGHT-01..04) |
| Requirements with automated test coverage | 4 / 4 |
| Gaps found (MISSING tests) | 0 |
| Gaps resolved by this audit | 0 |
| Escalated to Manual-Only | 3 (HV1 container-restart, HV2 end-to-end curl, HV3 first green CI run) |
| Host-environment notes (not gaps) | 3 (prometheus collision, PYTHONPATH/CORS quirks, fastapi version drift) |
| Tests added | 0 — existing 37 test definitions cover all 4 requirements |

**Verdict:** Phase 8 is **Nyquist-compliant**. All four PREFLIGHT requirements have automated test coverage in tree (23 unit + 3 route + 4 proxy + 5 lifespan + 2 grep-gate = 37 test definitions / 40 pytest invocations). The three manual-only items are operationally-bounded (container rebuild + restart, end-to-end curl, first CI run) and explicitly tracked against ROADMAP SC #2/#3/#4 + Phase 12 CIRESTORE-02. No new tests required; reconstruction confirms the validation surface was sufficient at execution time.
