---
phase: 21
slug: ta-aggregator-widening-leakage-net
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-26
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from 21-RESEARCH.md `## Validation Architecture` (authoritative detail lives there).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (both services) |
| **Config file** | `services/technical-analysis/pytest.ini`; `services/trading-engine/pytest.ini` (+ conftest pinning `env_file=None`) |
| **Quick run command** | TA: `cd services/technical-analysis && python3 -m pytest tests/test_leakage_regression.py tests/test_aggregator_new_legs.py --no-cov -q` · Engine: `cd services/trading-engine && python3 -m pytest tests/strategies/ --no-cov -q` |
| **Full suite command** | `cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q` and `cd services/trading-engine && python3 -m pytest tests/ --no-cov -q` |
| **Estimated runtime** | quick < 30 s; full suites minutes-scale |

**Non-negotiable:** engine tests run from `services/trading-engine` cwd, always `--no-cov`, never with env-var overrides (Dict deep-merge trap). No in-container engine test path.

---

## Sampling Rate

- **After every task commit:** Run the task's own targeted test file (quick command)
- **After every plan wave:** Run the changed service's full suite
- **Before `/gsd:verify-work`:** Both full suites green + repo-root guards (`tests/test_account_size_invariant.py`, `tests/test_account_config_sync.py`, `tests/test_price_rounding_invariant.py`) + rebuild `--force-recreate` of `technical-analysis` and `trading-engine` + `/verify-stack`
- **Max feedback latency:** 30 seconds (targeted file)

---

## Per-Task Verification Map

Task IDs assigned at planning; requirement-level map (full detail: 21-RESEARCH.md §Validation Architecture):

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | — | TA-AGG-01 (gating tests) | — | N/A | unit | `TA pytest tests/test_aggregator_new_legs.py --no-cov` | ✅ extend | ⬜ pending |
| TBD | — | — | TA-AGG-02/03 (closure evidence) | — | N/A | unit | `TA pytest tests/test_endpoint_defaults_from_settings.py --no-cov` | ✅ green | ⬜ pending |
| TBD | — | — | TA-AGG-04 (leakage suite) | — | N/A | unit | `TA pytest tests/test_leakage_regression.py --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-1 ATR threading + unit contract | — | N/A | unit | `engine pytest tests/strategies/test_ensemble_leg_wiring.py -k atr --no-cov` | ✅ extend + ❌ W0 | ⬜ pending |
| TBD | — | — | P21-2 diversity guard (+ no double jeopardy) | — | N/A | unit | `engine pytest tests/strategies/ -k diversity --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-2/3 threshold-lock guard | — | N/A | unit | `engine pytest tests/ -k threshold_lock --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-3 MTF demotion gates all legs | — | N/A | unit | `engine pytest tests/test_mtf_confidence_consolidation.py --no-cov` | ✅ extend | ⬜ pending |
| TBD | — | — | P21-4/5 engine param omission + Settings canon | — | N/A | unit | `engine pytest tests/test_engine_param_omission.py --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-6 constructor sourcing | — | N/A | unit | `TA pytest tests/test_aggregator_new_legs.py -k settings --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-7 mirror resolution | — | N/A | unit | `engine pytest tests/aggregation/ -k adx --no-cov` | ❌ W0 | ⬜ pending |
| TBD | — | — | P21-8 hygiene (capital guard stays green; .bak gone) | — | N/A | unit/guard | root `pytest tests/test_account_size_invariant.py --no-cov` | ✅ green | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `services/technical-analysis/tests/test_leakage_regression.py` — TA-AGG-04 (new; 400-bar `_synthetic_ohlcv` fixture)
- [ ] `services/trading-engine/tests/test_engine_param_omission.py` — P21-4/5 (new file)
- [ ] ATR unit-contract test in `tests/strategies/test_ensemble_leg_wiring.py` — P21-1 (percent-vs-fraction: `atr_pct=0.8` → 0.008)
- [ ] Threshold-lock guard test — pins MIN_AGREEING_LEGS=1 / AGGREGATION_THRESHOLD=0.10 / min_signal_confidence=0.30
- [ ] Leg source-diversity tests (block + multi_indicator-alone pass) — P21-2
- [ ] `demoted_to_hold` metadata + all-leg suppression tests — P21-3
- [ ] P21-6 constructor-sourcing tests in `test_aggregator_new_legs.py`
- [ ] No framework install needed — pytest present, both pytest.ini present

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Aggregate-endpoint vote documented | TA-AGG-01 | prose | Review `wiki/modules/technical-analysis.md` section exists and matches `handlers/analysis.py` behavior |
| Before/after signal comparison, 5 symbols | phase gate | live stack | Pull signals via running stack pre/post deploy; rebuild + `--force-recreate` both services; `/verify-stack` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
