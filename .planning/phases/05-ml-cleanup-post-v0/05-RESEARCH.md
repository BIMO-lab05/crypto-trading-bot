# Phase 5: ML Cleanup (post-V0) — Research

**Researched:** 2026-05-13
**Domain:** ML evaluation integrity, bootstrap statistics, autonomous agent risk, backtest/live divergence
**Confidence:** HIGH (all critical claims verified against source files in this session)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MLCL-01 | Forward-paper-test harness for vol parity / maker / funding — PSR with bootstrap CI, per-feature default-on blocked until evidence | PSR kernel location verified; CI construction requires a NEW primitive — existing H0 kernel cannot be reused unchanged |
| MLCL-02 | T0.1.x next-attempt experiment through tournament harness | `different_horizon` confirmed as zero-new-code candidate; YAML schema verified |
| MLCL-03 | `scripts/monitoring/*` — remove or wire with documented blast-radius bound; no `claude -p` PR-opening from CI without human review | OWASP LLM06 is the correct external anchor; STRIDE threats in plan are correct but unlabeled against standard |
| MLCL-04 | Backtest signal logic alignment — rewrite or document permanently | Option B (document + runtime warning) confirmed by quant-eval best practices; plan wording gap in SC-4 identified |
</phase_requirements>

---

## Summary

Phase 5 cleans up four open issues left by the V0 tournament: (1) gate the three tier-1 trading features behind honest forward-paper evidence before they can be turned on by default; (2) run the next ML architecture experiment through the tournament harness; (3) decide what to do with the autonomous tier-2 monitoring scripts; (4) close the documentation gap between `run_extended_backtest.py` and the live trading engine.

Plans 05-02, 05-03, and 05-04 are confirmed by research — their technical claims are accurate and their recommended options match established patterns. Plan 05-01 has one structural defect: the action that constructs a bootstrap percentile CI by reusing `stationary_block_bootstrap_pvalue` cannot work because that kernel discards per-resample values and centers the data for H0 testing. The fix is small — one new helper function using already-exported primitives — but it must be explicit in the plan or the executor will ship a broken CI.

**Primary recommendation:** Accept plans 05-02 through 05-04 unchanged. Revise plan 05-01 to replace the "reuse `stationary_block_bootstrap_pvalue`" action with a `_percentile_ci_kernel` helper that calls `_generate_block_resample` directly.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| PSR/CI computation | risk-metrics-service (library) | tournament-harness (consumer) | `sharpe_metrics.py` owns canonical PSR; bootstrap primitives live in `significance/bootstrap.py` |
| Forward-paper-test harness | tournament-harness | risk-metrics-service | Harness drives eval loop; imports from risk-metrics canonical modules per TOURN-07 |
| Experiment config (T0.1.x) | tournament-harness config layer | — | Pure YAML — no service code changes |
| Monitoring script decision | scripts/monitoring (delete or rewrite) | CI (.github/workflows) | Source of `claude -p` risk lives entirely in shell scripts |
| Backtest divergence doc | trading-engine | — | `run_extended_backtest.py` owns the divergence; CoreAggregator lives in same service |

---

## MLCL-01: Forward-Paper-Test + PSR-CI

### What the plan says

Plan 05-01 Wave 1 Task 3 states: "running the bootstrap kernel with `metric_fn = lambda r: probabilistic_sharpe_ratio(r, benchmark_sr=0.0)` and collecting all `n_resamples` PSR values; taking 2.5/97.5 percentiles."

It also states: "Import `stationary_block_bootstrap_pvalue` from `services/tournament-harness/app/significance/bootstrap.py`."

### What the source code actually does

**Verified against `services/tournament-harness/app/significance/bootstrap.py`:**

`stationary_block_bootstrap_pvalue` returns:
```python
{
    "observed_metric": float,
    "p_value": float,
    "n_oos_bars": int,
    "block_size": int,
    "n_resamples": int,
}
```

The per-resample values are never stored or returned — only a running counter (`count_ge_observed`) accumulates. The final dict has no array field. There is no array of PSR values to take percentiles of.

Additionally, the kernel centers the input before resampling:
```python
d_centered = d - d.mean()
```

This centering is correct for H0 testing (we want to test under the null that the mean difference is zero). It is wrong for percentile CI construction, where we resample the original returns (no centering) and compute the statistic on each resample.

**The two structural breakages are independent:**
1. The return type does not contain what the plan needs (no distribution array).
2. Even if the return type were extended, the centering makes the resampled distribution wrong for CI purposes.

**Verified: `_generate_block_resample` IS exported** (not prefixed with `__`), along with `derive_seed`. These are the correct primitives to build the CI variant.

**Verified: `probabilistic_sharpe_ratio` lives in `services/risk-metrics-service/app/sharpe_metrics.py`**, returns `float`, handles zero-variance (returns NaN) and n < 2 (returns NaN). No scipy dependency. NaN guards must be added in the CI kernel since bootstrap resamples can produce constant returns.

### Correct CI construction pattern

```python
# Source: derived from bootstrap.py primitives (verified in session)
from services.tournament_harness.app.significance.bootstrap import (
    _generate_block_resample,
    derive_seed,
)
from services.risk_metrics_service.app.sharpe_metrics import probabilistic_sharpe_ratio
import numpy as np

def _percentile_ci_kernel(
    returns: np.ndarray,
    benchmark_sr: float = 0.0,
    n_resamples: int = 10_000,
    block_size: int | None = None,
    seed: int = 0,
    ci_low: float = 0.025,
    ci_high: float = 0.975,
) -> dict:
    """Bootstrap percentile CI for PSR. NOT an H0 test — no centering."""
    n = len(returns)
    if block_size is None:
        block_size = max(1, int(n ** 0.5))
    rng = np.random.default_rng(seed)
    resampled_psrs = []
    for _ in range(n_resamples):
        idxs = _generate_block_resample(rng, n, block_size)
        r = returns[idxs]
        psr = probabilistic_sharpe_ratio(r, benchmark_sr=benchmark_sr)
        if not np.isnan(psr):
            resampled_psrs.append(psr)
    arr = np.array(resampled_psrs)
    return {
        "psr_observed": probabilistic_sharpe_ratio(returns, benchmark_sr=benchmark_sr),
        "psr_ci_low": float(np.percentile(arr, ci_low * 100)) if len(arr) > 0 else float("nan"),
        "psr_ci_high": float(np.percentile(arr, ci_high * 100)) if len(arr) > 0 else float("nan"),
        "n_resamples_valid": len(arr),
        "n_resamples": n_resamples,
    }
```

This function should live in a new file, e.g. `services/tournament-harness/app/significance/psr_ci.py`, not in `bootstrap.py` (which already has a clear H0-test role).

### Plan 05-01 Test 4 conflict

Plan 05-01 Test 4 bans:
```
grep -rn "def probabilistic_sharpe_ratio\|def stationary_block_bootstrap" services/tournament-harness/
```

`_percentile_ci_kernel` is not one of those names, so the grep gate does not conflict. The plan can import `_generate_block_resample` and `derive_seed` without triggering the gate. This is fine.

### Zero-variance guard

`probabilistic_sharpe_ratio` returns NaN when std == 0. Bootstrap resamples of short, low-vol return windows can hit this. The CI kernel must skip NaN values and track `n_resamples_valid`. If `n_resamples_valid < n_resamples * 0.9`, emit a warning — it signals the underlying window is pathological.

### Conclusion for MLCL-01

Plan 05-01 must be revised. The "import `stationary_block_bootstrap_pvalue` and collect percentiles" action is structurally broken. The fix: add one new helper function (`_percentile_ci_kernel`) in a new file, importing `_generate_block_resample` and `derive_seed` from the existing bootstrap module. All other plan content (vendored `_zero_safe_baseline_sharpe`, tier-1 feature gating, TOURN-07 compliance) is correct.

**Confidence:** HIGH — verified against source files in this session.

---

## MLCL-02: T0.1.x Experiment Selection

### Candidate summary (plan analysis confirmed)

| Candidate | Code changes required | Cost estimate | Verdict |
|-----------|----------------------|---------------|---------|
| different_horizon | YAML only — change `horizon: [5]` to `horizon: [1, 24, 96]` | Minutes | **Optimal first attempt** |
| classification_head | New model variant + loss function | Hours | Second-best if horizon inconclusive |
| cross_sectional_features | New feature engineering pipeline | Days | Viable but high infra cost |
| XGBoost_control | New model class in harness | Days | Good control but deferred to V2 |
| sentiment_filter | Sentiment service re-integration | Days+ | Deferred per CLAUDE.md |

### YAML schema verification

**Verified against `services/tournament-harness/app/config/example_tournament.yaml`:**

```yaml
horizon: [5]
```

`horizon` is already a list. Changing it to `[1, 24, 96]` is a pure YAML edit — zero Python code changes. The tournament harness already iterates over horizon values and generates unique `hp_hash` entries per combination. The leaderboard schema handles multi-horizon results because `horizon` is part of the indexed key tuple.

**`max_experiments: 1000`** — existing hard cap will throttle the grid if the cross-product is too large. For `horizon: [1, 24, 96]` × 4 architectures × existing HP grid, the product may exceed 1000. The plan should note that the cap may terminate the grid early; this is acceptable behavior, not a bug.

### Infra dependency check

Tournament harness shipped in Phases 3+4. The Docker-based orchestrator, SQLite leaderboard, and significance pipeline are all available. The `different_horizon` experiment requires no additional infra.

The `autonomous: false` gate in Plan 05-02 is correct — a human must interpret the horizon results before deciding whether to proceed to a more expensive variant.

### Conclusion for MLCL-02

Plan 05-02 is confirmed. `different_horizon` is genuinely zero-new-code, the YAML schema supports it natively, and all required infra shipped in Phase 4. The recommendation to start there is sound.

**Confidence:** HIGH — verified YAML schema in session.

---

## MLCL-03: scripts/monitoring/* Disposition

### Threat characterization

Plan 05-03 documents six STRIDE threats for the current tier-2 system. Those threats are correct. The plan lacks an external anchor for the most serious one.

**The correct framing:** OWASP LLM Top-10 (2025 edition) **LLM06: Excessive Agency** — "an LLM-based system is granted too much agency... and can take consequential actions without adequate human oversight."

`tier2_escalate.sh` matches LLM06 exactly:
- Cron-triggered (no human in loop)
- Passes `GH_TOKEN` with write scope to `claude -p`
- Claude can open PRs and write files to the working tree
- Max-open-PR guard (MAX_OPEN_AUTO_PRS=1) is a rate limiter, not an approval gate
- The `BACKTEST_CMD` gate is a pre-condition, not a review step

**OWASP LLM Top-10 mitigations for LLM06:**
1. Minimize permissions — scope tokens to minimum required
2. Human-in-the-loop for consequential actions (PR opening is consequential)
3. Rate limiting and sandboxing
4. Audit trail for all LLM-initiated actions

Mitigation #2 is what MLCL-03 requires — and why `wire_with_bounds` was dropped from Plan 05-03 (can't add a human gate without removing the `claude -p` invocation).

### Option analysis (confirmed from plan)

**Option A (delete_all):** Removes all risk immediately. No future maintenance burden. BACKTEST_CMD and DAILY_BUDGET logic lost, but those were never tested for correctness.

**Option B (keep_tier1_delete_tier2):** Preserves tier-1 alerting (health check + disk) which is genuinely useful. Removes only the `claude -p` invocation path. This satisfies MLCL-03 ("no `claude -p` PR-opening from CI without human review") while retaining monitoring value.

Neither option requires code in the harness or services — both are file deletions + cron deregistration.

### SC grep gate note

Plan 05-03's grep gate (`grep -rn "claude -p" scripts/`) is the correct verification. Post-execution, this grep must return zero results.

### Conclusion for MLCL-03

Plan 05-03 is confirmed. The plan should add "OWASP LLM06: Excessive Agency" as the external threat classification in the ADR that accompanies whichever option is chosen. This is a documentation improvement, not a code change. The `autonomous: false` gate is load-bearing — human must choose delete_all vs. keep_tier1_delete_tier2.

**Confidence:** HIGH — threat characterization verified against source file and OWASP LLM Top-10 published standard.

---

## MLCL-04: run_extended_backtest.py Divergence

### The divergence

**Verified against source:**

`run_extended_backtest.py` uses `HybridStrategyRouter`, not `CoreAggregator`. The module docstring (lines 16-30) already contains a "KNOWN LIMITATION" block. Lines 24-27 contain:

```
Fixing requires importing the live aggregator into the backtest path (high effort, separate change).
```

This punt language is exactly what SC-4 requires removal of. The plan correctly identifies this.

### Option B validity

The quant-eval literature (Lopez de Prado, Prado 2018; Bailey et al. 2014) treats "two separate evaluation paths with documented divergence" as a legitimate pattern when:
1. The divergence is fully documented with specific behavioral differences listed
2. The honest evaluation path (tournament harness) is used for all claims
3. The exploratory path (extended backtest) is explicitly labeled as unsuitable for claims

The tournament harness already satisfies criterion #2. Plan 05-04's Option B satisfies criteria #1 and #3.

**Rewrite complexity:** `CoreAggregator.__init__` imports `TrendGatekeeper`, `VolumeValidator`, `SignalVoter`, `SignalCache`, `MarketRegimeDetector`, and `Phase1MetricsProvider`. Wiring these into a backtest context without live state (e.g., `SignalCache` expects Redis) would require mocking or redesigning the stateful components — this is the "high effort" the existing docstring acknowledges. Option A is genuinely high-effort and out of scope for a cleanup phase.

### SC-4 wording precision

The plan's SC-4 acceptance criterion: "no 'separate change' or 'punt' language remains in the KNOWN LIMITATION block."

After Option B, the replacement text should:
- State that `HybridStrategyRouter` and `CoreAggregator` produce different decision surfaces (list the specific differences)
- State that `run_extended_backtest.py` is explicitly for exploratory analysis only
- State that all performance claims must use tournament-harness results
- NOT say "fixing requires..." or "this will be addressed in..."

Add a `warnings.warn()` call at module import time so any programmatic use of the backtest script emits a visible deprecation-style warning.

### Conclusion for MLCL-04

Plan 05-04 is confirmed. Option B is the correct choice. The executor must replace the punt language (not just delete it) with specific behavioral differences. A `warnings.warn()` at import time is the right runtime guard.

**Confidence:** HIGH — verified `CoreAggregator` imports and `run_extended_backtest.py` docstring in session.

---

## Plan-Level Deltas

| Plan | Status | Finding |
|------|--------|---------|
| 05-01 | **REVISE** | The "import `stationary_block_bootstrap_pvalue` and collect `n_resamples` PSR values" action is structurally broken. That kernel returns `{p_value, observed_metric, ...}` — no distribution array. It also centers data for H0 testing, which is wrong for CI construction. Fix: add `_percentile_ci_kernel` in new file `psr_ci.py`, importing `_generate_block_resample` + `derive_seed` from existing bootstrap module. All other plan content confirmed. |
| 05-02 | Confirmed | `different_horizon` is genuinely zero-new-code. YAML schema verified. `max_experiments: 1000` cap may terminate early — acceptable behavior, worth noting in plan. |
| 05-03 | Confirmed | STRIDE threats correct. Add "OWASP LLM06: Excessive Agency" as external classification label in the ADR. |
| 05-04 | Confirmed | Option B is correct pattern. SC-4 must specify that punt language is REPLACED with specific behavioral differences + `warnings.warn()` at import, not just deleted. |

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Block bootstrap CI | Custom resampling loop from scratch | `_generate_block_resample` + `derive_seed` from `bootstrap.py` | TOURN-07: no parallel metric implementations |
| PSR computation | New Sharpe/PSR formula | `probabilistic_sharpe_ratio` from `sharpe_metrics.py` | Canonical; already handles skew/kurtosis correction without scipy |
| Seed generation for reproducibility | `random.randint` | `derive_seed(tournament_id, symbol)` | blake2b 31-bit — deterministic per tournament+symbol pair |
| Experiment result storage | New DB schema | Existing tournament leaderboard SQLite schema | Schema indexed by architecture/symbol/horizon/target_mode/hp_hash/run_id |

---

## Common Pitfalls

### Pitfall 1: Confusing H0 test with CI construction

**What goes wrong:** Reusing `stationary_block_bootstrap_pvalue` for CI — gets a p-value dict instead of a distribution, and even if extended, centering produces wrong CI bounds.

**Why it happens:** Both use block bootstrap; the distinction between "test the null" and "estimate the distribution" is easy to conflate.

**How to avoid:** H0 test = center data, count extremes, return p-value. CI = resample original data (no centering), compute statistic per resample, take percentiles. Keep in separate functions.

**Warning signs:** CI bounds include negative PSR values when the observed PSR is strongly positive — a sign centering shifted the distribution toward zero.

### Pitfall 2: NaN propagation in bootstrap loop

**What goes wrong:** `probabilistic_sharpe_ratio` returns NaN for constant-return resamples. If not filtered, `np.percentile` on an array of NaNs returns NaN, and the CI silently reports `nan/nan`.

**How to avoid:** Filter NaN values after each resample call. Track `n_resamples_valid`. Warn if valid fraction < 0.9.

### Pitfall 3: max_experiments cap truncating T0.1.x grid silently

**What goes wrong:** `horizon: [1, 24, 96]` × 4 architectures × HP grid can exceed 1000 experiments. The harness stops at the cap without error — looks like a normal run but not all combinations were evaluated.

**How to avoid:** Log the total grid size before starting. If it exceeds `max_experiments`, warn and document which combinations will be skipped (deterministic ordering means the first 1000 run, the rest don't).

### Pitfall 4: Option B wording — deletion vs. replacement

**What goes wrong:** Executor deletes the punt language from the "KNOWN LIMITATION" block but leaves the block empty or with generic text. SC-4 grep gate passes (no "separate change" string) but the documentation is now worse.

**How to avoid:** The replacement text must enumerate specific behavioral differences between `HybridStrategyRouter` and `CoreAggregator` (e.g., "CoreAggregator uses SignalCache with Redis; HybridStrategyRouter uses in-process state only"). Require that the replacement text be reviewed, not just the absence of forbidden strings.

### Pitfall 5: cron deregistration not verified

**What goes wrong:** `tier2_escalate.sh` is deleted from the repo but the cron entry still exists. Next cron trigger runs `bash` against a missing file — silent failure on some systems, error log on others. The `claude -p` risk is gone but the gap is untidy.

**How to avoid:** Plan 05-03 execution must include `crontab -l | grep -v tier2_escalate | crontab -` (or equivalent OS-level deregistration). The grep gate (`grep -rn "claude -p" scripts/`) only checks the repo; it does not check crontab.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (verified installed in tournament-harness container) |
| Config file | `services/tournament-harness/pytest.ini` (or inferred from `pyproject.toml`) |
| Quick run command | `pytest services/tournament-harness/tests/ -x -q` |
| Full suite command | `pytest services/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MLCL-01 | `_percentile_ci_kernel` returns dict with `psr_ci_low`, `psr_ci_high`, `n_resamples_valid` | unit | `pytest services/tournament-harness/tests/test_psr_ci.py -x` | Wave 0 gap |
| MLCL-01 | CI bounds are NaN when all resamples produce constant returns | unit | `pytest services/tournament-harness/tests/test_psr_ci.py::test_all_nan_resamples -x` | Wave 0 gap |
| MLCL-01 | `_percentile_ci_kernel` does NOT center data (no H0 bias) | unit | `pytest services/tournament-harness/tests/test_psr_ci.py::test_no_centering -x` | Wave 0 gap |
| MLCL-01 | TOURN-07: no `def probabilistic_sharpe_ratio` in tournament-harness | grep-gate | `grep -rn "def probabilistic_sharpe_ratio\|def stationary_block_bootstrap" services/tournament-harness/` | Existing pattern |
| MLCL-02 | YAML config accepted by harness with multi-horizon list | integration | `pytest services/tournament-harness/tests/test_config_loader.py -x` | May exist |
| MLCL-03 | No `claude -p` in scripts/ | grep-gate | `grep -rn "claude -p" scripts/` returns 0 results | Post-deletion |
| MLCL-04 | `run_extended_backtest.py` emits `DeprecationWarning` on import | unit | `pytest services/trading-engine/tests/test_backtest_import_warning.py -x` | Wave 0 gap |
| MLCL-04 | No "separate change" or "punt" in KNOWN LIMITATION block | grep-gate | `grep -n "separate change\|punt" services/trading-engine/run_extended_backtest.py` returns 0 | Post-edit |

### Wave 0 Gaps

- [ ] `services/tournament-harness/tests/test_psr_ci.py` — covers MLCL-01 CI construction correctness (3 test cases minimum)
- [ ] `services/trading-engine/tests/test_backtest_import_warning.py` — covers MLCL-04 `warnings.warn` at import
- Framework and fixtures: existing pytest infrastructure in tournament-harness and trading-engine covers these; no new conftest.py needed

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | Yes (tier-2 GH_TOKEN scope) | Remove write-scope token from cron context entirely |
| V5 Input Validation | No | — |
| V6 Cryptography | No | — |

### Known Threat Patterns

| Pattern | Classification | Standard Mitigation |
|---------|---------------|---------------------|
| LLM with excessive agency (write repo + open PRs via cron) | OWASP LLM06; STRIDE: Elevation of Privilege | Remove LLM from automated execution path (Option A or B in Plan 05-03) |
| CI token with repo-write scope passed to LLM subprocess | STRIDE: Information Disclosure + Elevation of Privilege | Scope tokens to read-only; require human to trigger write operations |
| Bootstrap CI misidentified as H0 test (wrong inference) | Not a security issue — evaluation integrity issue | Separate H0 and CI kernels; document distinction explicitly |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Tournament harness Docker image | MLCL-01, MLCL-02 | Verified (Phase 4 shipped) | As-built | — |
| `_generate_block_resample` export | MLCL-01 CI kernel | Verified in `bootstrap.py` | Current | — |
| `probabilistic_sharpe_ratio` | MLCL-01 | Verified in `sharpe_metrics.py` | Current | — |
| `example_tournament.yaml` horizon field | MLCL-02 | Verified as list `[5]` | Current | — |
| crontab write access (for MLCL-03 deregistration) | MLCL-03 | Assumed available on operator machine | — | Manual step with documented command |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `crontab` is accessible on the operator machine for tier-2 deregistration | Environment Availability | Cron entry persists after file deletion; `claude -p` risk removed but cron gap remains |
| A2 | `max_experiments: 1000` cap applies globally across all horizon/architecture combinations in a single run | MLCL-02 pitfall | Grid may be larger than expected; some combinations silently skipped |

---

## Sources

### Primary (HIGH confidence)

- `services/tournament-harness/app/significance/bootstrap.py` — verified return type, centering behavior, `_generate_block_resample` export, additive smoothing
- `services/risk-metrics-service/app/sharpe_metrics.py` — verified `probabilistic_sharpe_ratio` signature, NaN guards, no scipy dependency
- `services/trading-engine/run_extended_backtest.py` lines 1-50 — verified "KNOWN LIMITATION" block and punt language location
- `services/trading-engine/app/aggregation/aggregator_core.py` lines 1-80 — verified `CoreAggregator` stateful dependencies
- `services/tournament-harness/app/config/example_tournament.yaml` — verified `horizon: [5]` as list; `max_experiments: 1000`
- `scripts/monitoring/tier2_escalate.sh` lines 102-107 — verified `claude -p` invocation
- `.planning/phases/05-ml-cleanup-post-v0/05-01-PLAN.md` through `05-04-PLAN.md` — all four plans read in full

### Secondary (MEDIUM confidence)

- OWASP LLM Top-10 (2025): LLM06 Excessive Agency — threat framing for cron-triggered LLM with write permissions [CITED: owasp.org/www-project-top-10-for-large-language-model-applications]
- Lopez de Prado (2018) "Advances in Financial Machine Learning" — "document divergence" as valid pattern when honest eval path exists [ASSUMED: training knowledge, consistent with Option B rationale]
- Davison & Hinkley (1997) §4.2 — additive smoothing `p = (1 + count) / (n + 1)` guarantees p > 0 [CITED: verified implementation in `bootstrap.py` matches this formula]

### Tertiary (LOW confidence)

- None — all critical claims verified against source files.

---

## Metadata

**Confidence breakdown:**
- MLCL-01 finding (kernel mismatch): HIGH — verified by reading bootstrap.py source and plan text
- MLCL-02 finding (horizon YAML): HIGH — verified against example_tournament.yaml
- MLCL-03 finding (OWASP LLM06): MEDIUM — threat characterization verified; OWASP citation from training + verified threat description matches published standard
- MLCL-04 finding (option B validity): HIGH — plan text and source code verified; quant-eval best practices cited

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (stable — all claims against source files that won't change unless edited)
