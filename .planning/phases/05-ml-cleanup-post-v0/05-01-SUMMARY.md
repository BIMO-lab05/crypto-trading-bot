---
phase: 05-ml-cleanup-post-v0
plan: 01
subsystem: forward-paper-test
tags: [mlcl-01, psr-ci, evidence-gate, tier1-flags, tdd]
status: complete
requires:
  - "Plan 04-10 _zero_safe_baseline_sharpe pattern (vendored verbatim in psr_ci.py)"
  - "services/risk-metrics-service/app/sharpe_metrics.py:probabilistic_sharpe_ratio"
  - "services/tournament-harness/app/significance/bootstrap.py:_generate_block_resample + derive_seed"
provides:
  - "scripts/forward_paper_test/ — host-runnable isolation-run apparatus for three Tier-1 flags"
  - "services/trading-engine/tests/test_config_default_on_gate.py — pytest gate blocking premature default-on flips"
  - ".planning/evidence/forward_paper_test/ — git-tracked evidence directory"
  - "docs/runbooks/forward-paper-test.md — operator runbook for the 7-day evidence loop"
affects:
  - "services/trading-engine/app/config.py (gate inspects this file via regex; no production code changed)"
  - "CI: test_config_default_on_gate.py runs in every PR touching trading-engine; fails if any Tier-1 flag gains default=True without PSR_CI_PUBLISHED marker"
tech-stack:
  added: []
  patterns:
    - "Percentile-CI bootstrap: _generate_block_resample loop over resamples, collect PSR values, take 2.5/97.5 percentiles — NOT the H0 centering kernel (stationary_block_bootstrap_pvalue)"
    - "Zero-variance short-circuit: var_eps=1e-12, force psr_point=0.0, degenerate CI — verbatim _zero_safe_baseline_sharpe from Plan 04-10"
    - "Filesystem-only pytest gate: regex scan of config.py + marker-file existence, no runtime kernel dependency"
    - "Subprocess-injectable test design: fake_docker parameter in run_isolation for unit-test isolation of live-launch path"
key-files:
  created:
    - "scripts/forward_paper_test/__init__.py"
    - "scripts/forward_paper_test/profiles.py"
    - "scripts/forward_paper_test/psr_ci.py"
    - "scripts/forward_paper_test/run_isolation.py"
    - "scripts/forward_paper_test/tests/__init__.py"
    - "scripts/forward_paper_test/tests/test_profiles.py"
    - "scripts/forward_paper_test/tests/test_psr_ci.py"
    - "scripts/forward_paper_test/tests/test_run_isolation_live.py"
    - "services/trading-engine/tests/test_config_default_on_gate.py"
    - ".planning/evidence/forward_paper_test/.gitkeep"
    - "docs/runbooks/forward-paper-test.md"
  modified: []
  deleted: []
decisions:
  - "H0 kernel (stationary_block_bootstrap_pvalue) NOT imported in psr_ci.py — it returns a p-value dict (no resample distribution), centers input for H0 testing (biases CI bounds), and cannot be used for percentile-CI construction. _generate_block_resample called directly instead."
  - "Marker at .planning/evidence/forward_paper_test/<flag>/PSR_CI_PUBLISHED (flag-level dir, not run_id subdir) — gate checks existence at the flag level so it survives across multiple runs and run_id rotations."
  - "Gate is pure filesystem + regex (no kernel import) — deterministic in CI, no numpy/scipy dependency needed to run the gate test."
  - "publish-evidence refuses when psr_ci_low <= 0.0 unless --force, which writes force_override.txt sibling — T-05-01-01 threat mitigation."
metrics:
  duration_minutes: 90
  completed: "2026-05-13"
  tasks_completed: 3
  tasks_total: 3
---

# Phase 05 Plan 01: Forward-Paper-Test Apparatus + Default-on Gate — Summary

**One-liner:** Delivered the full MLCL-01 apparatus — isolation-run CLI with env-override isolation, PSR-with-bootstrap-CI kernel reusing canonical implementations, evidence schema, publish-evidence with positive-CI guard, and a pytest gate in trading-engine that blocks default=True flips on all three Tier-1 flags until `.planning/evidence/forward_paper_test/<flag>/PSR_CI_PUBLISHED` exists.

## Status: **COMPLETE** — MLCL-01 all must_haves met; ROADMAP Phase 5 SC-1 mechanical preconditions in place.

**Operator note:** The ≥7-day evidence loops for enable_vol_targeting, prefer_maker_orders, and enable_funding_gate are operator action (3 flags × ≥7 wall-clock days each). This plan ships the apparatus + gate, NOT the evidence itself.

## Outcomes vs Plan Acceptance Criteria

| # | Criterion | Status |
|---|-----------|--------|
| 1 | `TIER1_FLAG_PROFILES` in profiles.py — 3 keys, isolation env overrides | PASS |
| 2 | `compute_psr_with_bootstrap_ci` + `load_run_returns` exported from psr_ci.py | PASS |
| 3 | No `def probabilistic_sharpe_ratio/stationary_block_bootstrap/deflated_sharpe` in psr_ci.py | PASS (grep returns 0) |
| 4 | `! grep -F 'stationary_block_bootstrap_pvalue' scripts/forward_paper_test/psr_ci.py` exits 0 | PASS |
| 5 | `! grep -E 'returns\s*-\s*returns\.mean'` exits 0 (no centering) | PASS |
| 6 | `python -m scripts.forward_paper_test.run_isolation --help` exits 0 | PASS |
| 7 | `--dry-run` prints JSON with planned env overlays | PASS |
| 8 | `pytest scripts/forward_paper_test/tests/ -v` — 32 tests pass | PASS |
| 9 | `NotImplementedError` absent from run_isolation.py | PASS |
| 10 | `.planning/evidence/forward_paper_test/.gitkeep` exists | PASS |
| 11 | `docs/runbooks/forward-paper-test.md` ≥ 60 lines, 7 headings | PASS (238 lines) |
| 12 | `services/trading-engine/tests/test_config_default_on_gate.py` exists — 5 tests pass | PASS |
| 13 | `grep -F 'PSR_CI_PUBLISHED' test_config_default_on_gate.py` ≥ 2 matches | PASS (10 matches) |
| 14 | Gate is pure filesystem + regex (no kernel runtime dependency) | PASS |
| 15 | `publish-evidence` refuses with non-zero exit when `psr_ci_low <= 0.0` | PASS |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `6cc516c` | test | RED — profiles, PSR-CI kernel, run-isolation CLI (Tasks 1) |
| `b931b24` | feat | GREEN — profiles, PSR-CI kernel, run-isolation CLI |
| `87ef1a4` | test | RED — live launch, evidence schema, publish-evidence, runbook (Task 2) |
| `19c9912` | feat | GREEN — live launch, evidence schema, publish-evidence, runbook |
| `c12a7d2` | test | RED — default-on gate for Tier-1 flags in trading-engine (Task 3) |
| `120c707` | feat | GREEN — implement default-on gate for Tier-1 flags |

## Public API

### `scripts/forward_paper_test/profiles.py`

```python
TIER1_FLAG_PROFILES: dict[str, dict]
# Keys: "enable_vol_targeting", "prefer_maker_orders", "enable_funding_gate"
# Each value: {env_overrides, baseline_env_overrides, description, evidence_subdir}
# Isolation guarantee: env_overrides sets exactly one flag to "true", other two to "false"
```

### `scripts/forward_paper_test/psr_ci.py`

```python
compute_psr_with_bootstrap_ci(
    returns: np.ndarray,
    *,
    seed: int,
    n_resamples: int = 10_000,
) -> dict
# Returns: {psr_point, psr_ci_low, psr_ci_high, n_resamples, n_resamples_valid,
#            block_size, seed, n_bars}
# Raises: ValueError when len(returns) < 30

load_run_returns(run_dir: Path) -> np.ndarray
# Reads run.json from the directory; raises FileNotFoundError or ValueError on bad input
```

### Gate: `services/trading-engine/tests/test_config_default_on_gate.py`

```python
_check_default_on_gate(config_path: Path, evidence_base: Path) -> list[str]
# Returns violation messages; empty = gate passes.
# Called with real paths by test_gate_passes_on_current_repo_state (Test 1).
# Checks: enable_vol_targeting, prefer_maker_orders, enable_funding_gate
# Marker path: evidence_base / <flag_name> / "PSR_CI_PUBLISHED"
```

## Runbook

`docs/runbooks/forward-paper-test.md` — covers Goal, Prerequisites, Step 1 (start isolation run), Step 2 (compute PSR CI), Step 3 (publish marker), Default-on gate rationale, and Troubleshooting. 238 lines.

## Test Results

```
$ python3 -m pytest scripts/forward_paper_test/tests/ --no-cov -q
32 passed in 3.42s

$ python3 -m pytest services/trading-engine/tests/test_config_default_on_gate.py --no-cov -v
5 passed in 0.47s
```

Total: **37 tests pass** across 4 test files.

## Operator Handoff

The ≥7-day evidence loops per flag are operator action. Sequence:

1. `python -m scripts.forward_paper_test.run_isolation --flag enable_vol_targeting --duration-days 7 --paper-trade-log <log>` — starts isolation run, writes `meta.json`
2. Wait ≥7 wall-clock days of paper trading with the flag enabled in isolation.
3. `python -m scripts.forward_paper_test.run_isolation complete-run --evidence-dir .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>` — extracts per-trade returns, writes `run.json`
4. `python -m scripts.forward_paper_test.psr_ci --evidence-dir <run_dir>` — computes PSR CI, writes `psr_ci.json`
5. `python -m scripts.forward_paper_test.run_isolation publish-evidence <run_dir>` — validates `psr_ci_low > 0.0`, writes `PSR_CI_PUBLISHED`
6. Create `.planning/evidence/forward_paper_test/enable_vol_targeting/PSR_CI_PUBLISHED` (flag-level marker; the gate checks this path)
7. Open PR that flips `enable_vol_targeting: bool = Field(default=True, ...)` — CI will PASS

Repeat for `prefer_maker_orders` and `enable_funding_gate`. Each requires its own ≥7-day run.

## Deviations from Plan

None — plan executed exactly as written across all three tasks.

## Known Stubs

None — all public API paths are fully implemented. Live-launch path in `run_isolation.py` invokes real `subprocess.run` with docker compose argv; `fake_docker` parameter is for test injection only and is not a stub.

## Threat Surface

No new network endpoints, auth paths, or schema changes at trust boundaries beyond those in the plan's threat register. All T-05-01-xx mitigations delivered as specified.

## Self-Check: PASSED

Files verified to exist:

- `scripts/forward_paper_test/profiles.py` — FOUND
- `scripts/forward_paper_test/psr_ci.py` — FOUND
- `scripts/forward_paper_test/run_isolation.py` — FOUND
- `scripts/forward_paper_test/tests/test_profiles.py` — FOUND
- `scripts/forward_paper_test/tests/test_psr_ci.py` — FOUND
- `scripts/forward_paper_test/tests/test_run_isolation_live.py` — FOUND
- `services/trading-engine/tests/test_config_default_on_gate.py` — FOUND
- `.planning/evidence/forward_paper_test/.gitkeep` — FOUND
- `docs/runbooks/forward-paper-test.md` — FOUND (238 lines)

Commits verified in `git log`:

- `6cc516c` (test RED Task 1) — FOUND
- `b931b24` (feat GREEN Task 1) — FOUND
- `87ef1a4` (test RED Task 2) — FOUND
- `19c9912` (feat GREEN Task 2) — FOUND
- `c12a7d2` (test RED Task 3) — FOUND
- `120c707` (feat GREEN Task 3) — FOUND
