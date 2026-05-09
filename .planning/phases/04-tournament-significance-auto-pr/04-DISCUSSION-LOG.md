# Phase 4: Tournament Significance & Auto-PR - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-09
**Phase:** 04-tournament-significance-auto-pr
**Areas discussed:** Ensemble inference contract, Baseline + bootstrap test mechanics, Auto-PR mechanics + reproducer, Win-criterion stringency + R² gate location

---

## Ensemble inference contract

### Aggregation

| Option | Description | Selected |
|--------|-------------|----------|
| Average predicted log-returns | Convert each model's price prediction to log-return vs `last_close`, average the 3, compute Sharpe + dir_acc directly on the averaged log-return series. Mirrors `returns_metrics.py` pipeline; cleanest mathematical compose for skill-on-returns. | ✓ |
| Average predicted prices then derive returns | Average the 3 raw price predictions, then run `returns_metrics` on the average. Subtle bias when predictions diverge. | |
| Majority vote on direction | Each model votes UP/DOWN/FLAT; majority wins. Returns derived from the directional decision. Loses magnitude — fine for dir_acc, weak for Sharpe. | |
| DSR-weighted average of log-returns | Like option 1 but weights by per-cell DSR. Rewards confidence; risks overweighting one cell. | |

**User's choice:** Average predicted log-returns
**Notes:** → CONTEXT.md D-02

### Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Per-symbol top-3 (Recommended) | 3 best-by-DSR rows per symbol. One ensemble per symbol; significance reported per-symbol; PR fires if ≥1 symbol passes. Matches per-symbol production deployment. | ✓ |
| Single global top-3 across all cells | 3 highest-DSR rows in the entire leaderboard. Simplest aggregation; mismatches per-symbol production. | |
| Top-3 per (symbol, architecture) | N_symbols × N_architectures ensembles. Exhaustive but combinatorial. | |

**User's choice:** Per-symbol top-3
**Notes:** → CONTEXT.md D-01

### Artifact

| Option | Description | Selected |
|--------|-------------|----------|
| Config-by-reference + run_ids only (Recommended) | JSON lists tournament_id + 3 (symbol, run_id, architecture, hp_hash) per symbol + aggregation method + git_sha. Reproducer re-trains the 3 cells deterministically. No model weights in git. | ✓ |
| Config + serialized model weights (.h5/.npy bundle) | Bundle 3 trained Keras models + scalers. Reproducible without re-training but blows up git LFS-style. | |
| Config + cached prediction series | Store per-cell OOS prediction array (numpy .npz). Mid-size; useful for re-analysis without TF dep. | |

**User's choice:** Config-by-reference + run_ids only
**Notes:** → CONTEXT.md D-03

---

## Baseline + bootstrap test mechanics

### Baseline

| Option | Description | Selected |
|--------|-------------|----------|
| Persistence only (Recommended) | Baseline = predict-last (next bar = current bar, returns = 0). Aligns with `returns_metrics.py:9` reference. Simple, deterministic, no production-aggregator runtime needed in the harness. | ✓ |
| Production-aggregator only | Baseline = current `ENABLE_ML_PREDICTIONS=false` aggregator (9-indicator vote, no ML) replayed over the same OOS bars. Matches what's actually live. Heavier. | |
| Both — must beat each independently | Bootstrap p<0.05 against persistence AND production-aggregator. Strictest gate. Doubles the work. | |
| Both — worse-of-the-two as the reference | Take whichever baseline scores higher on the same OOS slice and beat that one. Pragmatic. | |

**User's choice:** Persistence only
**Notes:** → CONTEXT.md D-04. Production-aggregator deferred for Phase 5 if persistence-only proves trivially beatable.

### Bootstrap

| Option | Description | Selected |
|--------|-------------|----------|
| Block bootstrap, one-tailed, n=10000 (Recommended) | Stationary block bootstrap with block_size = sqrt(N) over per-bar return differences. One-tailed because we want 'better', not 'different'. n_resamples=10000 standard. | ✓ |
| IID paired bootstrap, one-tailed, n=10000 | Resample (ensemble_ret_t, baseline_ret_t) pairs IID. Inflates significance for crypto (autocorrelated). | |
| Block bootstrap, two-tailed, n=10000 | Same machinery but two-tailed. More conservative; wastes power. | |
| Block bootstrap, one-tailed, n=100000 | 10× resamples. Tightens p-value precision near 0.05 boundary; 10× runtime. | |

**User's choice:** Block bootstrap, one-tailed, n=10000
**Notes:** → CONTEXT.md D-05, D-06. Bumping to 100k deferred until borderline-p tournaments become a pattern.

### Module

| Option | Description | Selected |
|--------|-------------|----------|
| New `services/tournament-harness/app/significance/bootstrap.py` (Recommended) | Tournament-specific concern; keep it out of risk-metrics-service. Reuse cpcv.py only for OOS slice construction. | ✓ |
| Extend services/risk-metrics-service/app/cpcv.py | Tighter reuse but couples tournament concerns to a production-trading service. | |
| New shared lib at libs/statistics/ | Cleanest if libs/ exists; over-engineering if it doesn't yet. | |

**User's choice:** New `services/tournament-harness/app/significance/bootstrap.py`
**Notes:** → CONTEXT.md D-07

---

## Auto-PR mechanics + reproducer

### Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Separate `tournament open-pr {tid}` CLI (Recommended) | Operator inspects snapshot, then explicitly invokes `tournament open-pr {tid}`. Operator-in-the-loop matches PROJECT.md "no autonomous loops that can commit/push without checkpoint review". | ✓ |
| End of `tournament run` automatically when ensemble wins | One command, hands-free; couples long Docker job to a network call. | |
| End of `tournament run` always (open or update PR) | Always opens/updates a PR. Maximizes visibility; clutters PR list with losers. | |
| CI workflow on snapshot commit | Decouples local dev from PR creation but requires CI permissions. | |

**User's choice:** Separate `tournament open-pr {tid}` CLI
**Notes:** → CONTEXT.md D-10

### Target/auth

| Option | Description | Selected |
|--------|-------------|----------|
| Read repo from `git remote get-url origin`; require GH_TOKEN env or hard fail (Recommended) | No config knobs. Token absent → exit non-zero with hint. Refuses silent skip — missing PR is the failure we MOST want to surface. | ✓ |
| Config-driven repo (.planning/config.json key) + GH_TOKEN env or skip-with-warning | Operator can override target. Soft skip on missing token; risks unnoticed misses. | |
| CLI flag `--repo owner/repo` + GH_TOKEN required | Per-invocation explicit. Verbose for routine runs. | |

**User's choice:** Read repo from `git remote get-url origin`; require GH_TOKEN env or hard fail
**Notes:** → CONTEXT.md D-11

### Reproducer

| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot-driven: `python -m app.cli reproduce {tid} --git-sha {sha}` (Recommended) | Single line. Internally checks out git_sha, restores tournament.yaml from snapshot, re-runs, asserts identical leaderboard within FP tolerance. | ✓ |
| Multi-step explicit: `git checkout {sha}; tournament run config.yaml --tournament-id {tid}; tournament significance {tid}` | More transparent; verbose; reviewer copies/pastes 3 lines. | |
| Docker-pinned: `docker run --rm tournament-harness:{git_sha} reproduce {tid}` | Captures runtime image. Strongest reproducibility. Requires per-tournament image push to a registry — new infra. | |

**User's choice:** Snapshot-driven `python -m app.cli reproduce {tid} --git-sha {sha}`
**Notes:** → CONTEXT.md D-12

---

## Win-criterion stringency + R² gate location

### Stringency

| Option | Description | Selected |
|--------|-------------|----------|
| p<0.05 on both metrics + lift sign positive + per-symbol gate (Recommended) | Per symbol: ensemble must beat persistence with p<0.05 AND positive raw lift on BOTH OOS Sharpe AND dir_acc_corrected. PR fires when ≥1 symbol passes. | ✓ |
| p<0.05 on both metrics, no lift-sign check | Just p-values. Vulnerable to a 'significantly worse' winner. | |
| p<0.05 + positive lift + ALL symbols pass | Strictest — PR fires only when every per-symbol ensemble wins. High false-negative rate. | |
| p<0.05 + positive lift + minimum effect size (Sharpe lift > 0.1) | Adds an effect-size floor. Defensible but introduces a magic number. | |

**User's choice:** p<0.05 on both metrics + lift sign positive + per-symbol gate
**Notes:** → CONTEXT.md D-08

### Anti-cherry-picking

| Option | Description | Selected |
|--------|-------------|----------|
| Stamp `tournaments_evaluated_count` in PR body + Bonferroni note (Recommended) | Operator-discipline gate, not a code gate. Doesn't block the PR. | ✓ |
| Block PR until N consecutive winning tournaments | Strong but slow; encourages parameter tuning to chase the streak. | |
| DSR already adjusts for multiple-testing — nothing extra needed | Argue DSR's deflation is enough; do nothing for cross-tournament cherry-picking. | |
| Refuse if same-tid was opened before with a different result | Idempotency check. Conflicts with reproducer-by-rerun semantics. | |

**User's choice:** Stamp `tournaments_evaluated_count` in PR body + Bonferroni note
**Notes:** → CONTEXT.md D-09

### R² gate

| Option | Description | Selected |
|--------|-------------|----------|
| CI grep gate as test in tests/test_no_legacy_r2_criterion.py (Recommended) | pytest test that runs `grep -rEn` for forbidden patterns. Fails the build, not runtime. Same shape as Phase 3's TOURN-07 grep gate. | ✓ |
| Runtime assertion in significance module | Catches dynamic uses but misses comments/strings. | |
| Both: CI grep + runtime assertion | Belt-and-suspenders. Slight maintenance overhead; near-zero new value. | |

**User's choice:** CI grep gate as test in tests/test_no_legacy_r2_criterion.py
**Notes:** → CONTEXT.md D-13. Sibling test `test_no_auto_merge.py` follows the same shape (CD-10).

---

## Claude's Discretion

These were not deep-dived; defaults captured in CONTEXT.md `### Claude's Discretion` (CD-01 through CD-12):

- **CD-01:** PR title format
- **CD-02:** PR branch naming (`tournament/{tournament_id}` with `gh pr edit` idempotency)
- **CD-03:** PR labels (`tournament`, `evaluation-gate`, conditional `winner`)
- **CD-04:** No auto-assignees / reviewers (solo founder)
- **CD-05:** Leaderboard markdown row format (GFM table, fixed column order, 4dp display)
- **CD-06:** `reproduce` builds a temp SQLite DB to avoid touching the operator's main leaderboard
- **CD-07:** Bootstrap RNG seed = blake2b(`tournament_id|sig|symbol`)
- **CD-08:** Insufficient-runs threshold (< 3 successful runs per symbol → skip from gate, report in PR body)
- **CD-09:** `gh` CLI absence handling (exit 2 with install hint)
- **CD-10:** `gh pr merge` ban via `test_no_auto_merge.py` grep gate
- **CD-11:** Ensemble OOS bars sourced via predict-only re-run on the same `is_mainnet=true` 12mo window
- **CD-12:** PR body length cap (link to in-PR `leaderboard.md` when > 60k chars)

## Deferred Ideas

Captured in CONTEXT.md `<deferred>` block:

- Production-aggregator baseline (Phase 5 candidate if persistence-only proves trivial)
- DSR-weighted ensemble averaging
- Per-(symbol, architecture) ensembles
- Single global top-3 as a diagnostic mode
- `n_resamples = 100k` upgrade
- CI workflow `tournament-pr.yml` for snapshot-commit-trigger
- Auto-flipping `ENABLE_ML_PREDICTIONS=true` on PR merge (explicit non-goal)
- Inline-at-`tournament-run` auto-PR
- Idempotency-on-tournament-id PR refusal
- Storing model weights in the ensemble artifact
- N-consecutive-winning-tournaments anti-cherry-picking (escalate to FDR if disclosure proves insufficient)
- Branch / repo / labels in config.json
- Refusing on differing same-tid result
