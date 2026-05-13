---
phase: 05
slug: ml-cleanup-post-v0
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-13
---

# Phase 05 — Validation Strategy

> Reconstructed from artifacts (State B). Phase 05 was already executed (4 plans, 4 SUMMARY.md files committed) before this VALIDATION.md was authored.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (configured for ≥6.0) |
| **Config file** | `pytest.ini` (root) + `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python3 -m pytest <file> --no-cov -p no:cacheprovider -q` |
| **Full suite command (Phase 05 scope)** | see "Full Phase 05 Suite" below |
| **Estimated runtime** | ~25 s for full Phase 05 scope (51 behavioral + 5 doc-existence = 56 tests) |

### Full Phase 05 Suite

```bash
cd /mnt/d/Bimo_max/crypto-trading-bot && \
python3 -m pytest \
  scripts/forward_paper_test/tests/ \
  --no-cov -p no:cacheprovider -q && \
python3 -m pytest \
  services/trading-engine/tests/test_config_default_on_gate.py \
  services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py \
  --no-cov -p no:cacheprovider --rootdir services/trading-engine -q && \
python3 -m pytest \
  services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py \
  --no-cov -p no:cacheprovider --rootdir services/tournament-harness -q && \
python3 -m pytest \
  tests/security/test_no_unattended_claude_p_in_ci.py \
  tests/docs/test_phase_05_artifacts.py \
  --no-cov -p no:cacheprovider -q
```

> Note: tournament-harness + trading-engine tests are run with `--rootdir` per-service to avoid cross-service `conftest.py` collision (`ImportPathMismatchError` in shared invocation).

---

## Sampling Rate

- **After every task commit:** Run the per-task quick command in the table below.
- **After every plan wave:** Run the full Phase 05 suite.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** ~25 s (full suite).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | MLCL-01 | T-05-01-05 | TIER1_FLAG_PROFILES exposes 3 keys with isolation guarantee | unit | `pytest scripts/forward_paper_test/tests/test_profiles.py -v` | ✅ | ✅ green |
| 05-01-01 | 01 | 1 | MLCL-01 | T-05-01-04 | PSR-CI kernel reuses canonical `probabilistic_sharpe_ratio` + `_generate_block_resample`; no H0 kernel import; no centering; zero-safe sentinel | unit | `pytest scripts/forward_paper_test/tests/test_psr_ci.py -v` | ✅ | ✅ green |
| 05-01-01 | 01 | 1 | MLCL-01 | — | run_isolation CLI exposes `--flag/--duration-days/--dry-run`; dry-run prints valid JSON | smoke | `pytest scripts/forward_paper_test/tests/test_psr_ci.py::test_run_isolation_help_exits_zero_with_expected_flags scripts/forward_paper_test/tests/test_psr_ci.py::test_run_isolation_dry_run_prints_valid_json -v` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | MLCL-01 | T-05-01-01 | Live launch refuses LIVE / non-paper modes; argv contains correct env overrides; meta.json materialised; publish-evidence refuses on `psr_ci_low<=0` unless `--force` | integration | `pytest scripts/forward_paper_test/tests/test_run_isolation_live.py -v` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | MLCL-01 | — | Operator runbook ≥60 lines, contains 7 required sections | unit (file-IO) | `pytest scripts/forward_paper_test/tests/test_run_isolation_live.py::test_runbook_exists_and_is_at_least_60_lines scripts/forward_paper_test/tests/test_run_isolation_live.py::test_runbook_contains_required_sections -v` | ✅ | ✅ green |
| 05-01-03 | 01 | 1 | MLCL-01 | T-05-01-01 | Default-on gate fails when any Tier-1 flag default=True without flag-level PSR_CI_PUBLISHED marker; passes on current `default=False` state | integration | `pytest services/trading-engine/tests/test_config_default_on_gate.py -v --rootdir services/trading-engine` | ✅ | ✅ green |
| 05-02-01 | 02 | 1 | MLCL-02 | — | 05-02-DECISION.md exists, ≥80 lines, has `## Decision:` heading | unit (file-IO) | `pytest services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py::test_decision_doc_exists_has_min_lines_and_decision_heading -v --rootdir services/tournament-harness` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | MLCL-02 | T-05-02-02 | Tournament YAML exists, parses, `tournament_id` starts with `t0_1_x_`, `max_experiments<=100`, `symbols` valid subset | unit (file-IO + yaml) | `pytest services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py::test_yaml_config_exists_and_valid -v --rootdir services/tournament-harness` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | MLCL-02 | — | Leaderboard markdown exists in evidence dir, non-empty | unit (file-IO) | `pytest services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py::test_leaderboard_markdown_exists_and_nonempty -v --rootdir services/tournament-harness` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | MLCL-02 | T-05-02-01 / T-05-02-05 | decision_note.md ≥20 lines, terminal verdict ∈ {EDGE_FOUND, NO_EDGE_FOUND, INSUFFICIENT_DATA}, cites `tournament_id` from YAML | unit (file-IO) | `pytest services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py::test_decision_note_exists_has_min_lines_and_valid_verdict services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py::test_decision_note_cites_tournament_id_from_yaml -v --rootdir services/tournament-harness` | ✅ | ✅ green |
| 05-03-01 | 03 | 1 | MLCL-03 | — | 05-03-DECISION.md exists, ≥100 non-blank lines, contains `## Decision: keep_tier1_delete_tier2` | unit (file-IO) | `pytest tests/docs/test_phase_05_artifacts.py::test_phase_05_03_decision_md_exists_with_min_lines_and_disposition_heading -v` | ✅ | ✅ green |
| 05-03-02 | 03 | 1 | MLCL-03 | T-05-03-01..06 | ADR-011 exists, ≥40 non-blank lines, has `ADR-011` + `Status:` + `## Decision` heading | unit (file-IO) | `pytest tests/docs/test_phase_05_artifacts.py::test_adr_011_exists_with_min_lines_and_required_sections -v` | ✅ | ✅ green |
| 05-03-02 | 03 | 1 | MLCL-03 | T-05-03-01 / T-05-03-02 / T-05-03-04 / T-05-03-06 | scripts/monitoring/README.md contains a "Blast-radius bounds" section (case-insensitive) | unit (file-IO) | `pytest tests/docs/test_phase_05_artifacts.py::test_monitoring_readme_has_blast_radius_bounds_section -v` | ✅ | ✅ green |
| 05-03-03 | 03 | 1 | MLCL-03 | T-05-03-07 | grep `claude\s+-p` returns zero matches in CI workflows, scripts/monitoring/, and broad-scope (with allowlist); test self-excludes | integration (subprocess grep) | `pytest tests/security/test_no_unattended_claude_p_in_ci.py -v` | ✅ | ✅ green |
| 05-04-01 | 04 | 1 | MLCL-04 | — | 05-04-DECISION.md exists, ≥60 non-blank lines, contains `## Decision: document_divergence_permanently` | unit (file-IO) | `pytest tests/docs/test_phase_05_artifacts.py::test_phase_05_04_decision_md_exists_with_min_lines_and_disposition_heading -v` | ✅ | ✅ green |
| 05-04-02 | 04 | 1 | MLCL-04 | T-05-04-02 | ADR-012 exists, ≥30 non-blank lines, has `ADR-012` + `Status:` + `## Decision` heading | unit (file-IO) | `pytest tests/docs/test_phase_05_artifacts.py::test_adr_012_exists_with_min_lines_and_required_sections -v` | ✅ | ✅ green |
| 05-04-02 | 04 | 1 | MLCL-04 | T-05-04-01 / T-05-04-02 | run_extended_backtest.py: SC-4 punt phrases absent; PERMANENT DIVERGENCE marker present; CoreAggregator named; ADR-012 referenced; runtime warning fires at entry | integration (caplog + grep) | `pytest services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py -v --rootdir services/trading-engine` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. Phase 05 reused the project's pytest config; the only gap-filling Wave 0 add was:

- [x] `tests/docs/__init__.py` — package marker
- [x] `tests/docs/test_phase_05_artifacts.py` — 5 doc-existence tests for MLCL-03/04 plan-mandated artifacts (DECISION.md ×2, ADR ×2, README blast-radius section)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `.planning/STATE.md` Blockers/Concerns line about scripts/monitoring/ updated to reflect ADR-011 resolution | MLCL-03 must_have | Free-form prose change in a state file — pinning specific text would brittle-couple validation to STATE.md authoring style | Inspect `.planning/STATE.md` Blockers section after Phase 05 close; confirm scripts/monitoring/ entry mentions ADR-011 + tier-2 deletion |
| Tournament leaderboard rows for `t0_1_x_horizon_sweep` (verbatim, with actual DSR/PSR/CPCV-DSR values) | MLCL-02 must_have ("verbatim leaderboard committed") | Plan 02 produced INSUFFICIENT_DATA verdict due to empty `TIMESCALE_PASSWORD` in tournament-harness container — operator action required before real rows can land. The `leaderboard_row.md` schema-stub is intentional and documented per Plan 02(F). | Operator: (1) `grep TIMESCALE_PASSWORD .env`, (2) `docker compose -f docker-compose.unified.yml --profile tournament up -d --force-recreate tournament-harness`, (3) `docker exec crypto-bot-tournament-harness python -m app.cli run /app/app/config/t0_1_x_experiment.yaml`, (4) copy actual leaderboard.md into `.planning/evidence/t0_1_x/leaderboard_row.md`, (5) update `decision_note.md` terminal verdict to EDGE_FOUND or NO_EDGE_FOUND with bootstrap p-values. Gate `test_t0_1_x_experiment_shipped.py` already accepts INSUFFICIENT_DATA as valid; manual upgrade only changes the verdict. |
| 7-day forward-paper-test isolation runs for each Tier-1 flag (`enable_vol_targeting`, `prefer_maker_orders`, `enable_funding_gate`) | MLCL-01 plan-scope explicit carve-out ("apparatus + gate, NOT the 7-day evidence") | 3 flags × ≥7 wall-clock days each = ≥21 days operator time. Plan 01 ships the apparatus + the default-on gate that refuses `default=True` without `PSR_CI_PUBLISHED` marker. The marker file existence IS automated-gated (`test_config_default_on_gate.py`); the evidence behind the marker is operator homework. | Operator: per-flag, run `python -m scripts.forward_paper_test.run_isolation --flag <flag> --duration-days 7 --paper-trade-log <log>`, wait ≥7 days, run `complete-run` + `psr_ci`, then `publish-evidence` (writes marker only if `psr_ci_low > 0.0`). See `docs/runbooks/forward-paper-test.md` (238 lines). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify (Phase 05 scope: 56 tests across 9 test files; 0 manual-only behaviors lack a corresponding test gate where pinnable)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (5 doc-existence gaps filled; see "Wave 0 Requirements")
- [x] No watch-mode flags (`-p no:cacheprovider --no-cov` only)
- [x] Feedback latency < 30 s (full Phase 05 suite ~25 s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-13

---

## Validation Audit 2026-05-13

| Metric | Count |
|--------|-------|
| Gaps found | 5 |
| Resolved | 5 |
| Escalated | 0 |
| Manual-only added | 3 |

### Resolved Gaps (auditor: gsd-nyquist-auditor)

1. **MLCL-03 / 05-03-DECISION.md**: existence + ≥100 non-blank lines + `## Decision: keep_tier1_delete_tier2` heading — pinned via `tests/docs/test_phase_05_artifacts.py::test_phase_05_03_decision_md_exists_with_min_lines_and_disposition_heading`.
2. **MLCL-03 / ADR-011**: existence + ≥40 non-blank lines + ADR sections (`ADR-011`, `Status:`, `## Decision`) — pinned via `test_adr_011_exists_with_min_lines_and_required_sections`.
3. **MLCL-03 / scripts/monitoring/README.md**: case-insensitive "blast-radius" section presence — pinned via `test_monitoring_readme_has_blast_radius_bounds_section`.
4. **MLCL-04 / 05-04-DECISION.md**: existence + ≥60 non-blank lines + `## Decision: document_divergence_permanently` heading — pinned via `test_phase_05_04_decision_md_exists_with_min_lines_and_disposition_heading`.
5. **MLCL-04 / ADR-012**: existence + ≥30 non-blank lines + ADR sections — pinned via `test_adr_012_exists_with_min_lines_and_required_sections`.

Adversarial sanity verification (auditor): each gate tripped under simulated regression (disposition flip, file truncation, README section removal). Test runtime 0.47 s.
