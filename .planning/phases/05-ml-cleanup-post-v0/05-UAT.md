---
status: complete
phase: 05-ml-cleanup-post-v0
source:
  - 05-01-SUMMARY.md
  - 05-02-SUMMARY.md
  - 05-03-SUMMARY.md
  - 05-04-SUMMARY.md
started: "2026-05-13T11:12:28Z"
updated: "2026-05-13T11:55:00Z"
---

## Current Test

[testing complete]

## Tests

### 1. All Phase 5 pytest gates pass on host
expected: |
  All 51 Phase 5 pytest cases pass on host (forward_paper_test 32 + default-on gate 5 + divergence-warning 5 + tournament-harness integration 5 + security grep gate 4).
result: pass
notes: |
  Combined `pytest` invocation hit conftest collision (trading-engine vs tournament-harness `tests.conftest`).
  Ran each suite separately and forward_paper_test required `PYTHONPATH=.`. Final tallies:
    - forward_paper_test                              32/32 PASS
    - test_config_default_on_gate + divergence_warning 10/10 PASS (5+5)
    - tournament-harness T0.1.x integration            5/5 PASS
    - tests/security/test_no_unattended_claude_p_in_ci 4/4 PASS
  Total: 51/51 PASS. Trading-engine coverage gate "FAIL 80%" fired but is unrelated to Phase 5 gates.

### 2. Forward-paper-test CLI dry-run prints planned overlay JSON
expected: |
  Run from repo root:

      python -m scripts.forward_paper_test.run_isolation \
        --flag enable_vol_targeting \
        --duration-days 7 \
        --dry-run

  Expected: exit 0; stdout contains a JSON object with keys
  `{flag, env_overrides, baseline_env_overrides, evidence_path, planned_start, planned_end, duration_days, git_sha}`.
  evidence_path ends with `enable_vol_targeting/<run_id>`. planned_end - planned_start = 7 days (ISO).
  env_overrides has ENABLE_VOL_TARGETING=true and the other two flags explicitly =false.
result: pass
notes: |
  Required `PYTHONPATH=. python3 -m ...` (no `python` on host; PATH only has python3).
  All 8 keys present. evidence_path ends with `enable_vol_targeting/20260513T114051Z`.
  planned_start=2026-05-13T11:40:51, planned_end=2026-05-20T11:40:51 (Δ=7 days).
  env_overrides shows ENABLE_VOL_TARGETING=true with the other two flags =false.
  git_sha=279be08.

### 3. Tournament harness T0.1.x evidence files honest about INSUFFICIENT_DATA
expected: |
  - File `services/tournament-harness/app/config/t0_1_x_experiment.yaml` exists and starts `tournament_id: t0_1_x_horizon_sweep` (or similar pre-confirmed slug).
  - File `.planning/evidence/t0_1_x/leaderboard_row.md` exists.
  - File `.planning/evidence/t0_1_x/decision_note.md` exists, ≥20 lines, terminal non-blank line equals `INSUFFICIENT_DATA` (executor could not run docker-exec from agent context — see 05-02-SUMMARY.md operator remediation).
  - decision_note.md contains a "Blocker" section naming the env mismatch (TIMESCALE_PASSWORD) and the 5-step operator remediation.

  This is the EXPECTED outcome for this UAT — `INSUFFICIENT_DATA` is a valid MLCL-02 verdict per the plan ("no edge is a valid outcome"). Confirming the artifacts are honest about the infra-failure rather than fabricating a fake EDGE/NO_EDGE.
result: pass
notes: |
  yaml: tournament_id: "t0_1_x_horizon_sweep" at line 16 (header comment line 1).
  leaderboard_row.md present.
  decision_note.md: 137 lines, terminal non-blank = INSUFFICIENT_DATA, Blocker section at line 61 names TIMESCALE_PASSWORD,
    operator remediation steps present (Step 1 at line 76+).

### 4. scripts/monitoring/* tier-2 deleted, tier-1 retained, grep gate enforces no claude -p
expected: |
  - `! test -f scripts/monitoring/tier2_escalate.sh` (gone)
  - `! test -f scripts/monitoring/tier2_mission.md` (gone)
  - `! test -f scripts/monitoring/auto_pr_janitor.sh` (gone)
  - `test -f scripts/monitoring/tier1_monitor.py` (retained — value-bearing)
  - `test -f scripts/monitoring/run_monitor.sh` (retained, rewritten with `notify_operator_only()`)
  - `grep -i 'blast.radius' scripts/monitoring/README.md` returns ≥1 match
  - `grep -rE 'claude\s+-p|"claude"\s*,\s*"-p"' scripts/monitoring/ .github/workflows/` returns zero matches
  - `pytest tests/security/test_no_unattended_claude_p_in_ci.py -v` shows 4/4 PASS
result: pass
notes: |
  All 3 tier-2 paths gone. tier1_monitor.py + run_monitor.sh retained.
  notify_operator_only() defined at run_monitor.sh:24 and invoked at :64.
  blast.radius: 1 match in README.md.
  claude -p search: ZERO MATCHES.
  pytest test_no_unattended_claude_p_in_ci.py: 4/4 PASS (test 1).

### 5. run_extended_backtest.py — punt language gone, PERMANENT DIVERGENCE marker present, runtime warning fires
expected: |
  - `! grep -E 'Fixing requires|separate change' services/trading-engine/run_extended_backtest.py` exits 0 (punt language gone)
  - `grep -F 'PERMANENT DIVERGENCE' services/trading-engine/run_extended_backtest.py` returns ≥1 match
  - `grep -F 'CoreAggregator' services/trading-engine/run_extended_backtest.py` returns ≥1 match
  - `grep -F 'ADR-012' services/trading-engine/run_extended_backtest.py` returns ≥1 match
  - `pytest services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py -v` shows 5/5 PASS, including the test that captures the `RUN_EXTENDED_BACKTEST: signal logic diverges from live CoreAggregator` log emit at script entry.
result: pass
notes: |
  Punt language: zero matches.
  PERMANENT DIVERGENCE: 4 occurrences.
  CoreAggregator: 3 occurrences.
  ADR-012: 5 occurrences.
  test_run_extended_backtest_divergence_warning.py: 5/5 PASS (run within test 1).

### 6. ADR-011 and ADR-012 both filed in docs/decisions/
expected: |
  - `test -f docs/decisions/ADR-011-monitoring-disposition.md`
  - `test -f docs/decisions/ADR-012-extended-backtest-disposition.md`
  - Each ≥40 lines (`wc -l` returns ≥40 for each)
  - ADR-011 names `keep_tier1_delete_tier2` as the chosen disposition; ADR-012 names `document_divergence_permanently`.
result: pass
notes: |
  ADR-011: 99 lines, slug `keep_tier1_delete_tier2` at line 48.
  ADR-012: 102 lines (after fix), slug `document_divergence_permanently` added at line 44.
  Both ADRs now symmetric — chosen-disposition slug present in dedicated bold line above the prose decision.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0

## Gaps

[resolved in-session: added `**Chosen disposition: \`document_divergence_permanently\`**` at ADR-012:44 — slug symmetry restored vs ADR-011]
