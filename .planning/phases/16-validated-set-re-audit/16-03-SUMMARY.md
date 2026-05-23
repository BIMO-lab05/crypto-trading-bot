---
phase: 16-validated-set-re-audit
plan: 03
subsystem: audit
tags: [audit, track-b, signal, ml, tournament, lstm-archive, claude-claims]
requires: [AUDIT-01]
provides: [.planning/evidence/AUDIT-01/track-B-deltas.json]
affects: [Phase 21 (TA-AGG-01), Phase 23 (ML-PURGE-01/02/05), Phase 24 (HYG-01)]
tech_stack: {added: [], patterns: [audit-by-code-read]}
key_files:
  created: [.planning/evidence/AUDIT-01/track-B-deltas.json, .planning/phases/16-validated-set-re-audit/16-03-SUMMARY.md]
  modified: []
decisions:
  - "TOURN-07 verdict drift: verbatim claim narrowly satisfied for tournament-harness scope, but plan instructions require drift when r2_score-on-prices exists in ml-retraining-service (confirmed at trainer.py:430,623). Notes call out the scope mismatch explicitly so Phase 23 can extend grep gate."
  - "CLAUDE-SENTIMENT-REMOVED verdict drift even though comments (not log strings) — plan literal criterion was 'Sentiment 15% log strings'; treating stale comments describing 15% sentiment weight in the active use_phase3=True aggregator path as drift, since the comments describe live behavior."
metrics:
  duration_minutes: 12
  total_rows: 19
  satisfied: 15
  drift: 4
  missing: 0
---

# Phase 16 Plan 03: Track B (ML + MLCL + TOURN + EXEC-03 + CLAUDE Signal Claims) Audit Summary

**One-liner:** Track B audit of 19 REQs covering ML metrics correctness, MLCL post-V0 cleanup, tournament-harness orchestration + significance pipeline, the 9-indicator aggregator claim, and two CLAUDE.md signal-pipeline claims; 15 satisfied + 4 drift (EXEC-03 aggregator vote count, TOURN-07 grep-gate scope, CLAUDE-LSTM live import, CLAUDE-SENTIMENT stale comment).

## Status Counts

| Status | Count |
| --- | --- |
| satisfied | 15 |
| drift | 4 |
| missing | 0 |
| **total** | **19** |

## Per-REQ Verdict Table

| REQ-ID | Era | Status | Evidence | Downstream owner |
| --- | --- | --- | --- | --- |
| EXEC-03 | pre-v1 | drift | `services/technical-analysis/app/handlers/analysis.py:67-110` | Phase 21 TA-AGG-01 |
| ML-01 | pre-v1 | satisfied | `services/ml-retraining-service/app/core/returns_metrics.py:25-50` | — |
| ML-02 | pre-v1 | satisfied | `services/ml-retraining-service/app/sharpe_metrics.py:1-80` | — |
| ML-03 | pre-v1 | satisfied | `services/ml-retraining-service/app/cpcv.py:1-60` | — |
| ML-04 | pre-v1 | satisfied | `services/ml-prediction-service/app/ml_models/gru_predictor.py:152-180` | — |
| ML-05 | pre-v1 | satisfied | `services/trading-engine/app/config.py:90-93` + `docker-compose.unified.yml:292,620` | — |
| MLCL-01 | v1.0 | satisfied | `scripts/forward_paper_test/run_isolation.py:1-40` + `psr_ci.py` | — |
| MLCL-02 | v1.0 | satisfied | `services/tournament-harness/app/config/t0_1_x_experiment.yaml:1-10` + test_t0_1_x_experiment_shipped.py | — |
| MLCL-03 | v1.0 | satisfied | `docs/decisions/ADR-011-monitoring-disposition.md:1-90` + `tests/security/test_no_unattended_claude_p_in_ci.py` | — |
| MLCL-04 | v1.0 | satisfied | `services/trading-engine/run_extended_backtest.py:16-80` + ADR-012 | — |
| TOURN-01 | v1.0 | satisfied | `services/tournament-harness/app/orchestrator/launcher.py:92-120` | — |
| TOURN-02 | v1.0 | satisfied | `services/tournament-harness/migrations/0001_initial.sql:9-43` | — |
| TOURN-03 | v1.0 | satisfied | `services/tournament-harness/app/config/tournament_loader.py:25-50` | — |
| TOURN-04 | v1.0 | satisfied | `services/tournament-harness/app/orchestrator/failure.py:1-31` | — |
| TOURN-05 | v1.0 | satisfied | `services/tournament-harness/app/significance/ensemble.py:43-73` + `bootstrap.py:114` + `win_gate.py:31-32` | — |
| TOURN-06 | v1.0 | satisfied | `services/tournament-harness/app/pr/gh.py:61-92` + `tests/integration/test_no_auto_merge.py` | — |
| TOURN-07 | v1.0 | drift | `services/ml-retraining-service/app/core/model_trainer.py:430,623` | Phase 23 ML-PURGE-01 + ML-PURGE-05 |
| CLAUDE-LSTM-ARCHIVED | pre-v1 | drift | `services/ml-prediction-service/app/models/ensemble_model.py:15` + `services/ml-retraining-service/app/core/models/lstm.py` | Phase 23 ML-PURGE-02 |
| CLAUDE-SENTIMENT-REMOVED | pre-v1 | drift | `services/trading-engine/app/auto_trader.py:1130,1261` | Phase 24 HYG-01 |

## Drift-to-Downstream Mapping

| Drift REQ | Owner phase / plan | Task hint |
| --- | --- | --- |
| EXEC-03 | Phase 21 TA-AGG-01 | Widen `get_aggregated_signal()` from 3 to 9+ indicator votes (or rewrite PROJECT.md claim from "9-indicator" to actual count). The 13 indicator modules are implemented; only 3 vote. |
| TOURN-07 | Phase 23 ML-PURGE-01 + ML-PURGE-05 | (a) Remove `r2_score()` on `inverse_transform()`-ed price arrays at `model_trainer.py:430` (val_r2) and `:623` (dataset_r2). Replace with `compute_returns_metrics`. (b) Extend `services/tournament-harness/` grep gate scope to cover `services/**` so this drift can't reappear. |
| CLAUDE-LSTM-ARCHIVED | Phase 23 ML-PURGE-02 | (a) Move `services/ml-retraining-service/app/core/models/lstm.py` to `_archive_lstm/` (or delete). (b) Remove `from tensorflow.keras.layers import LSTM` at `ensemble_model.py:15` and the `'lstm'` entry in `EnsemblePredictor.__init__`. |
| CLAUDE-SENTIMENT-REMOVED | Phase 24 HYG-01 | Replace stale `# Phase 3: ... + Sentiment 15% + MTF 15%` comments at `auto_trader.py:1130` and `:1261`. Verify `get_trading_signal_enhanced(use_phase3=True)` aggregator weights actually have sentiment_weight=0 (separate check inside `services/technical-analysis/`). |

## Notable Refinements vs Forensic Audit

| REQ | Forensic verdict | Re-audit verdict | Refinement |
| --- | --- | --- | --- |
| EXEC-03 | drift (3 of 13) | drift (confirmed) | Forensic call correct: 3 indicators vote (RSI, MACD, TrendFilter); 13 indicator modules implemented. Doc claim of "9" is also off — drift covers gap to both 9 (doc) and 13 (implementation). |
| TOURN-07 | drift (r2_score on prices) | drift (split verdict) | Forensic call partially right: r2_score-on-prices DOES exist at `model_trainer.py:430,623`. But the verbatim TOURN-07 claim is scoped to the *tournament-harness* — `metrics_bridge.py:28-35` correctly imports canonical, and the CI grep gate (in metrics_bridge docstring) is enforced for `services/tournament-harness/`. The drift is real but lives in `services/ml-retraining-service/` outside the gate's scope. Notes call this out explicitly so Phase 23 owners pick the right surgery. |
| CLAUDE-LSTM-ARCHIVED | drift (live import) | drift (both fail) | Forensic correct on both halves: ensemble_model.py:15 has live LSTM import AND retraining-service lstm.py exists at non-archive path (63 lines). An `_archive_lstm/` directory does exist but only at `services/ml-prediction-service/models/_archive_lstm` (model artifacts), not at the source path. CLAUDE.md claim "LSTM deleted" is contradicted on both code paths. |
| CLAUDE-SENTIMENT-REMOVED | drift (stale log lines) | drift (stale comments — narrower) | Forensic correct on the file:line locations but slight miscategorization: the strings at `auto_trader.py:1130,1261` are code COMMENTS (not log strings as suspected). Verdict unchanged (drift) since the comments describe live behavior in the `use_phase3=True` aggregator path, which Phase 24 must reconcile (either remove the comments OR verify sentiment_weight=0). |

## Methodology Notes

- All 19 verdicts grounded in direct code reads at cited `file:line` ranges.
- TOURN-07 split-verdict treatment follows plan instructions ("note the divergence: the grep gate exists for the tournament-harness but does NOT cover ml-retraining-service") — verbatim claim narrowly met, but downstream owner is Phase 23 ML-PURGE-01 + ML-PURGE-05.
- LSTM `_archive_lstm/` directory check confirmed missing at the source-code path (`services/ml-retraining-service/app/core/models/`); only model artifacts under `services/ml-prediction-service/models/_archive_lstm` are archived.
- CLAUDE-SENTIMENT-REMOVED claim text was checked literally; verdict is drift because the stale comments describe a runtime behavior CLAUDE.md says is removed. Phase 24 HYG-01 reconciles either by deleting comments or verifying live aggregator removes the weight.

## Files Written

- `.planning/evidence/AUDIT-01/track-B-deltas.json` (19 rows, schema-validated)
- `.planning/phases/16-validated-set-re-audit/16-03-SUMMARY.md` (this file)

## Self-Check: PASSED

- track-B-deltas.json validates against `.planning/evidence/AUDIT-01/_schema.json` (jsonschema)
- 19 rows present (matches plan's expected count)
- 4 drift verdicts each have non-null notes naming the downstream owner phase
- 15 satisfied + 4 drift verdicts each have non-null `evidence_file` + line range
- No `pending` rows remain
- Commit `ea3b383` (deltas) confirmed in `git log --oneline`
