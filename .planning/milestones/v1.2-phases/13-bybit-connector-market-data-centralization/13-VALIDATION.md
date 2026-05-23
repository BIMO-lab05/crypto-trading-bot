---
phase: 13
slug: bybit-connector-market-data-centralization
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-21
populated: 2026-05-21
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from `13-RESEARCH.md` §"Validation Architecture" (lines 826-913).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4.4 + pytest-asyncio 0.23.3 + respx 0.20.2 (httpx mock) |
| **Config file** | `services/<svc>/pyproject.toml` + `pytest.ini` (per-service); `tests/integration/conftest.py` (repo-level fresh-clone harness) |
| **Quick run command** | `pytest tests/ci/test_no_bybit_bypass.py -v` (grep gate, fast — <2s) |
| **Full suite command** | `pytest tests/ -v && pytest services/{ml-prediction-service,market-data-service,trading-engine}/tests/ -v` |
| **Estimated runtime** | ~120s full suite; ~2s grep gate |
| **api-gateway caveat** | api-gateway tests MUST run inside container (`docker exec crypto-bot-api-gateway pytest`) — host fastapi 0.136 vs container fastapi 0.109. Phase 13 does NOT modify api-gateway; caveat noted for sibling-phase awareness only. |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ci/test_no_bybit_bypass.py -v && pytest <relevant service tests>` — grep gate ALWAYS + consumer-specific tests
- **After every plan wave merge:** Run full suite (`pytest tests/ -v && pytest services/{ml-prediction-service,market-data-service,trading-engine}/tests/ -v`)
- **Before `/gsd:verify-work`:** Full suite must be green AND CI workflow `.github/workflows/bybit-bypass-gate.yml` (or equivalent) shows green on phase-close PR
- **Max feedback latency:** ~5s grep gate; ~120s full suite

---

## Per-Task Verification Map

> **Status: populated 2026-05-21.** All 22 tasks across 9 plans mapped. Wave 0 = scaffolding + RED tests; Wave 1 = refactor (GREEN); Wave 2 = Binance archival; Wave 3 = docs + close.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-01-T1 | 13-01 | 0 | BC-01 | — | Audit script `scripts/audit_bybit_bypass.py` enumerates ≥18 in-scope bypass sites; emits JSON array | scaffolding | `python scripts/audit_bybit_bypass.py \| python -c "import json,sys; arr=json.load(sys.stdin); assert isinstance(arr,list) and len(arr)>=18"` | ❌ W0 — script creates | ⬜ |
| 13-01-T2 | 13-01 | 0 | BC-01 | — | Evidence artifact committed at `.planning/evidence/BC-01/bybit-bypass-audit.json` | scaffolding | `test -f .planning/evidence/BC-01/bybit-bypass-audit.json && python -c "import json; arr=json.load(open('.planning/evidence/BC-01/bybit-bypass-audit.json')); assert len(arr)>=18"` | ❌ W0 | ⬜ |
| 13-02-T1 | 13-02 | 0 | BC-03 | T-BC03-LeakedBypass | Grep-gate test file + `__init__.py` exist; in RED state on `main` (bypass sites still present pre-refactor) | unit (gate itself) | `pytest tests/ci/test_no_bybit_bypass.py::test_grep_command_matches_pytest_scan tests/ci/test_no_bybit_bypass.py::test_exempt_paths_excluded -v` | ❌ W0 | ⬜ |
| 13-02-T2 | 13-02 | 0 | BC-03 | T-BC03-LeakedBypass | `.github/workflows/bybit-bypass-gate.yml` exists, valid YAML, invokes the gate on PR | unit | `test -f .github/workflows/bybit-bypass-gate.yml && python -c "import yaml; yaml.safe_load(open('.github/workflows/bybit-bypass-gate.yml'))"` | ❌ W0 | ⬜ |
| 13-03-T1 | 13-03 | 0 | BC-07 | T-BC07-LiveLeak | Tape preservation RED test exists; asserts orderbook tape stub shape `{a, b, ts, u}` | integration (RED) | `pytest tests/integration/test_bybit_connector_tape_preserved.py::test_tape_stub_shapes_match_handler_expectations -v` | ❌ W0 | ⬜ |
| 13-03-T2 | 13-03 | 0 | BC-02 (D-04) | — | Scripts fail-fast RED test exists; parametrize covers refactored scripts + backtesting fetcher | integration (RED) | `test -f tests/integration/test_scripts_fail_fast.py && python -c "import ast; ast.parse(open('tests/integration/test_scripts_fail_fast.py').read())"` | ❌ W0 | ⬜ |
| 13-03-T3 | 13-03 | 0 | BC-05 | — | BC-05 RED test exists in NEW sibling file (NOT in skipped test_config.py per PATTERNS.md W#1); asserts default URL contains `:8001` | unit (RED) | `test -f services/market-data-service/tests/test_config_defaults.py && grep -c "test_bybit_connector_url_default_is_8001" services/market-data-service/tests/test_config_defaults.py` | ❌ W0 | ⬜ |
| 13-04-T1 | 13-04 | 1 | BC-02 | T-BC02-ErrorShape, T-BC07-LiveLeak | ml-prediction orderbook handler hits `${BYBIT_CONNECTOR_URL}/api/v1/market/orderbook` with parser-shape swap (PATTERNS.md W#4); respx-verified | unit (respx) + integration (tape) | `pytest services/ml-prediction-service/tests/test_orderbook_handler.py -v && pytest tests/integration/test_bybit_connector_tape_preserved.py -v` | ❌ W0 → GREEN | ⬜ |
| 13-04-T2 | 13-04 | 1 | BC-02 | T-BC02-ErrorShape | 4 ml-prediction `download_*.py` scripts route through bybit-connector; no banned patterns | unit (grep) | `python -c "import subprocess,sys; files=['services/ml-prediction-service/download_missing_symbols_data.py']; bad=[f for f in files if int(subprocess.run(['grep','-cE','https?://api(-testnet)?\\.bybit\\.com|from pybit|import pybit',f],capture_output=True,text=True).stdout.strip())>0]; assert not bad"` | ❌ W0 → GREEN | ⬜ |
| 13-05-T1 | 13-05 | 1 | BC-02 | T-BC02-ErrorShape | `scripts/collect_180_days_data.py` + `scripts/collect_6months_for_ml.py` route through bybit-connector with fail-fast | unit (grep) + integration (fail-fast) | `pytest tests/integration/test_scripts_fail_fast.py -v -k "collect_180_days or collect_6months_for_ml"` | ❌ W0 → GREEN | ⬜ |
| 13-05-T2 | 13-05 | 1 | BC-02 | T-BC02-ErrorShape | 3 remaining collect/data-quality scripts refactored; no `pybit` import in any `scripts/collect_*.py` | unit (grep) | `python -c "import subprocess; files=['scripts/collect_ml_training_data_simple.py','scripts/collect_bybit_direct_180days.py','scripts/data_quality_enhancement.py']; bad=[f for f in files if int(subprocess.run(['grep','-cE','from pybit|import pybit|https?://api(-testnet)?\\.bybit\\.com',f],capture_output=True,text=True).stdout.strip())>0]; assert not bad"` | ❌ W0 → GREEN | ⬜ |
| 13-06-T1 | 13-06 | 1 | BC-02 | T-BC02-ErrorShape | `scripts/fetch_real_historical_data.py` + `scripts/collect_6months_historical.py` route through bybit-connector with fail-fast | unit (grep) + integration | `pytest tests/integration/test_scripts_fail_fast.py -v -k "fetch_real_historical"` | ❌ W0 → GREEN | ⬜ |
| 13-06-T2 | 13-06 | 1 | BC-02 | T-BC02-ErrorShape | `backtesting/bybit_data_fetcher.py` refactored with fail-fast in `__main__` AND class-level `fetch_klines`; `scripts/test_public_bybit_api.py` deleted | unit (grep) + integration | `test -f backtesting/bybit_data_fetcher.py && grep -cE 'https?://api(-testnet)?\.bybit\.com\|from pybit\|import pybit' backtesting/bybit_data_fetcher.py \| grep -q '^0$' && grep -q 'BYBIT_CONNECTOR_URL' backtesting/bybit_data_fetcher.py && ! test -f scripts/test_public_bybit_api.py && pytest tests/integration/test_scripts_fail_fast.py -v -k backtesting` | ❌ W0 → GREEN | ⬜ |
| 13-06-T3 | 13-06 | 1 | BC-05 | — | `services/market-data-service/app/config.py:58` default reads `:8001`; `test_pagination_fix.py` deleted | unit | `grep -n 'bybit_connector_url' services/market-data-service/app/config.py \| grep -c '8001' \| grep -q '^1$' && ! test -f services/market-data-service/tests/test_pagination_fix.py && pytest services/market-data-service/tests/test_config_defaults.py::test_bybit_connector_url_default_is_8001 -x` | ❌ W0 → GREEN | ⬜ |
| 13-07-T1 | 13-07 | 1 | BC-02 | T-BC02-CredentialSpill | `infrastructure/scripts/rotate_secrets.py` refactored to bybit-connector restart-then-ping (Option A); no `pybit` import; auth-ping hits `/api/v1/account/balance` | unit (respx) + grep | `pytest infrastructure/scripts/tests/test_rotate_secrets_auth_ping.py -v && grep -c '/api/v1/account/balance' infrastructure/scripts/rotate_secrets.py \| grep -q '^[1-9]' && grep -cE 'from pybit\|import pybit' infrastructure/scripts/rotate_secrets.py \| grep -q '^0$'` | ❌ W0 → GREEN | ⬜ |
| 13-07-T2 | 13-07 | 1 | BC-02 | T-BC02-ErrorShape | `shared/health_check.py` refactored to call `${BYBIT_CONNECTOR_URL}/health`; no banned patterns; in-scope-first caller handling per checker amendment | unit (grep + AST) | `grep -cE 'https?://api(-testnet)?\.bybit\.com\|from pybit\|import pybit' shared/health_check.py \| grep -q '^0$' && grep -c 'BYBIT_CONNECTOR_URL' shared/health_check.py \| grep -q '^[1-9]' && python -c "import ast; ast.parse(open('shared/health_check.py').read())"` | ❌ W0 → GREEN | ⬜ |
| 13-08-T1 | 13-08 | 2 | BC-04 | T-BC04-ImportError | `services/trading-engine/app/exchanges/binance.py` archived to `_archive_exchanges/binance.py` at REPO ROOT (PATTERNS.md W#3); `__init__.py` cleaned at imports (329-336), `__all__` (513-516), AND docstring lines 23 + 213 | smoke + unit | `test -f _archive_exchanges/binance.py && ! test -f services/trading-engine/app/exchanges/binance.py && grep -cE "from app.exchanges.binance\|BinanceExchangeAdapter" services/trading-engine/app/exchanges/__init__.py \| grep -q '^0$' && grep -cE "BinanceExchangeAdapter\|Direct Binance API integration" services/trading-engine/app/exchanges/__init__.py \| grep -q '^0$'` | ❌ W2 → GREEN | ⬜ |
| 13-08-T2 | 13-08 | 2 | BC-04 | T-BC04-ImportError, T-BC03-LeakedBypass | `services/trading-engine/tests/test_multi_exchange.py` DELETED (PATTERNS.md W#2 — import-time crash); BC-03 grep gate now GREEN; trading-engine boots without ImportError | smoke + gate | `! test -f services/trading-engine/tests/test_multi_exchange.py && pytest tests/ci/test_no_bybit_bypass.py -v && docker exec crypto-bot-trading-engine python -c "import app.main"` | ❌ W2 → GREEN | ⬜ |
| 13-09-T1 | 13-09 | 3 | BC-06 | — | `RUNBOOK.md` contains "Market-data stale or missing — bybit-connector chain broken" symptom in Diagnose/Action/Verification format | docs | `grep -A 30 'Market-data stale or missing' RUNBOOK.md \| grep -c 'bybit-connector' \| python -c "import sys; assert int(sys.stdin.read()) >= 1"` | ⬜ | ⬜ |
| 13-09-T2 | 13-09 | 3 | BC-06 (D-10) | — | `.planning/codebase/INTEGRATIONS.md` line 231 corrected (stale claim about market-data WS removed) | docs (grep) | `grep -c 'wss://stream.bybit.com/\* \| bybit-connector, market-data' .planning/codebase/INTEGRATIONS.md \| grep -q '^0$'` | ⬜ | ⬜ |
| 13-09-T3 | 13-09 | 3 | BC-06 | All T-BC* | Phase-close verify-stack 4-check matrix: live exchange URL, real notification, DB row, restart-after-config-change. Operator-driven; CI grep gate runs end-to-end | manual + automated | `pytest tests/ci/test_no_bybit_bypass.py -v` + operator runs `/verify-stack` skill | N/A | ⬜ Manual |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · ❌ W0 = file does not exist yet, Wave 0 task creates it · ❌ W0 → GREEN = Wave 0 RED test exists, this Wave 1+ task flips it green*

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · ❌ W0 = file does not exist yet, Wave 0 task creates it*

---

## Wave 0 Requirements

NEW files the planner must create as scaffolding for the per-task verifications:

- [ ] `tests/ci/__init__.py` — new pytest collection dir
- [ ] `tests/ci/test_no_bybit_bypass.py` — covers BC-03 (the grep gate itself; RED-first per TDD mode)
- [ ] `tests/integration/test_bybit_connector_tape_preserved.py` — covers BC-07 (tape mode integration test)
- [ ] `tests/integration/test_scripts_fail_fast.py` — covers BC-02 D-04 fail-fast contract for refactored scripts
- [ ] `services/market-data-service/tests/test_config.py::test_default_bybit_connector_url` — covers BC-05 (new test case in existing file, OR new file if `test_config.py` doesn't exist)
- [ ] `scripts/audit_bybit_bypass.py` — produces BC-01 audit artifact at `.planning/evidence/BC-01/bybit-bypass-audit.json`
- [ ] `.planning/evidence/BC-01/` directory + `.gitkeep` placeholder
- [ ] Per-consumer respx tests under `services/<svc>/tests/test_<module>.py` for every BC-02 refactor (RED-first per TDD heuristic in references/tdd.md — every refactored bypass site = 1 RED test + 1 GREEN refactor)
- [ ] `.github/workflows/bybit-bypass-gate.yml` (or extend existing CI workflow) — runs `tests/ci/test_no_bybit_bypass.py` on every PR

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| RUNBOOK symptom #N narrative quality, Diagnose/Action/Verification chain reads naturally for an oncall operator | BC-06 | Tone/clarity assessment is judgment; automated grep only confirms presence | Read `RUNBOOK.md` §"Market-data stale or missing — bybit-connector chain broken" end-to-end; confirm steps are reproducible and outputs match what an operator would see |

---

## Validation Dimensions (Nyquist)

| Dimension | Behavior Asserted | Method |
|-----------|-------------------|--------|
| **Behavior** | Grep gate finds zero violations across `**/*.py` outside `services/bybit-connector/` | `tests/ci/test_no_bybit_bypass.py` |
| **Behavior** | Tape mode replays canned data through refactored consumers; no live Bybit during tape | `tests/integration/test_bybit_connector_tape_preserved.py` |
| **Contract** | bybit-connector REST endpoints accept same params + return same wrapper shape as before refactor | Implicit (no connector code change); explicit assertion via consumer respx tests |
| **Regression** | Existing tests in services/ml-prediction-service, market-data-service, trading-engine pass post-refactor | Service-level pytest runs in CI |
| **Boundary** | Refactored scripts fail-fast with operator-readable error when bybit-connector unreachable | `tests/integration/test_scripts_fail_fast.py` |
| **Permission** | No new auth flows; existing `BYBIT_API_KEY` / `BYBIT_API_SECRET` env propagation unchanged | Diff review — no new env var introductions |
| **Archival integrity** | trading-engine boots without ImportError after Binance archival | Boot smoke (`python -c "import app.main"` inside container) + Docker healthcheck |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — 22/22 tasks mapped above
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — verified by inspection (only 13-09-T3 is partly manual; flanking tasks have automated verify)
- [x] Wave 0 covers all MISSING references — 13-01..13-03 produce audit script, grep gate, fail-fast test, tape preservation test, BC-05 RED test
- [x] No watch-mode flags — all commands are one-shot (`pytest -x`, `grep`, `python -c`)
- [x] Feedback latency < 120s — grep gate ~2s, full suite ~120s, per-task tests <30s typical
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-21 — per-task map populated by orchestrator post-checker-revision; Dimension 8 coverage confirmed.
