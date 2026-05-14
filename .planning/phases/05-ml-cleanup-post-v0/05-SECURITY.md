---
phase: 5
slug: ml-cleanup-post-v0
status: verified
threats_open: 0
threats_total: 22
threats_closed: 22
asvs_level: 1
block_on: high
created: 2026-05-13
verified: 2026-05-13
auditor: gsd-security-auditor
register_authored_at_plan_time: true
---

# Phase 05 — Security (ml-cleanup-post-v0)

**Plans audited:** 05-01 (forward-paper-test PSR-CI gate), 05-02 (T0.1.x tournament), 05-03 (monitoring tier-2 disposition), 05-04 (extended-backtest divergence disposition)
**ASVS Level:** L1 · **Block-on:** high · **Auditor:** gsd-security-auditor · **Date:** 2026-05-13
**Verdict:** SECURED — 22/22 threats CLOSED

---

## Summary

All 22 declared threats across Phase 05's four plans are CLOSED. Mitigate-disposition
threats verified by code/test grep; accept-disposition threats verified by documented
control on disk (runbook, ADR, decision note); the one option-A-only DoS threat
(T-05-04-05) is moot because Plan 05-04 selected option B per DECISION.md.

No unregistered threat flags surfaced — SUMMARY.md `## Threat Flags` for each plan
either says "None" or maps cleanly to the existing register.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Operator-shell → docker compose (Plan 05-01) | Operator invokes `run_isolation.py` which spawns docker compose with env overrides | flag name + run_id |
| Paper-trade log → load_run_returns (Plan 05-01) | Paper-trade log file on disk feeds returns array into PSR-CI computation | per-trade returns array |
| Evidence dir → trading-engine config gate (Plan 05-01) | Marker file existence triggers default-on gate | PSR_CI_PUBLISHED marker file |
| Operator → tournament harness (Plan 05-02) | Operator writes YAML config; harness executes search | YAML grid spec |
| Tournament-harness → leaderboard SQLite (Plan 05-02) | Phase 3 boundary; no new surface | run records |
| Decision artifact → CI gate (Plan 05-02) | Integration test pass/fail depends on verdict line | verdict + tournament_id |
| Cron → tier-2 escalator (Plan 05-03, ELIMINATED) | Previously: cron triggered claude -p with repo write access | (REMOVED — both viable dispositions eliminated this) |
| Tier-1 monitoring scripts → external services (Plan 05-03) | tier1_monitor.py curls Prometheus, CoinGecko, docker logs | metrics JSON |
| Operator → run_extended_backtest.py (Plan 05-04) | Operator runs script and reads PnL output | PnL numbers + warning text |

---

## Threat Verification — 22/22 CLOSED

### Plan 05-01 — forward-paper-test PSR-CI gate

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-05-01-01 | Tampering | mitigate | closed | `scripts/forward_paper_test/run_isolation.py:282-360` `publish_evidence()`: refuses without `run.json` (L303), without `psr_ci.json` (L314), or when `psr_ci_low <= 0.0` (L328); `--force` writes `force_override.txt` sidecar (L344) |
| T-05-01-02 | Spoofing | accept | closed | `docs/runbooks/forward-paper-test.md` (238 lines) documents honour-system control; SUMMARY 05-01 explicitly notes "operator's honour" |
| T-05-01-03 | Elevation of Privilege | mitigate | closed | Gate at `services/trading-engine/tests/test_config_default_on_gate.py:209` (`test_tier1_flag_default_on_requires_published_evidence`); runbook forbids `TRADING_MODE=LIVE`; `_check_paper_mode_precondition()` at `scripts/forward_paper_test/run_isolation.py:83-111` enforces refusal at launcher |
| T-05-01-04 | Information disclosure | accept | closed | Output git-tracked under `.planning/evidence/forward_paper_test/`; no secrets in `meta.json` / `run.json` / `psr_ci.json` schemas |
| T-05-01-05 | DoS | mitigate | closed | `scripts/forward_paper_test/psr_ci.py:188-192` raises `ValueError("forward-paper-test requires per-trade returns or sub-daily bars; got fewer than 30 observations")` when `len(r) < 30` |

### Plan 05-02 — T0.1.x tournament experiment

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-05-02-01 | Tampering | accept | closed | `services/tournament-harness/tests/integration/test_t0_1_x_experiment_shipped.py:136-151` (`test_decision_note_cites_tournament_id_from_yaml`) enforces cross-reference; honour-system documented in 05-02-DECISION.md |
| T-05-02-02 | DoS | mitigate | closed | `services/tournament-harness/app/config/t0_1_x_experiment.yaml:43` `max_experiments: 100`; `tournament_loader.py` raises `ValueError` when Cartesian grid > cap; integration test asserts cap ≤ 100 |
| T-05-02-03 | Information disclosure | accept | closed | YAML L10-11 explicit "SECURITY: no secrets, API keys, or passwords in this file (T-03-13)"; snapshots directory committed per Phase 3 convention |
| T-05-02-04 | Tampering | mitigate | closed | Existing Phase 3+4 grep gates retained: `test_tourn07_grep_gate.py`, `test_no_auto_merge.py`, `test_no_legacy_r2_criterion.py`, `test_klines_filter_required.py`, `test_no_parallel_metric_reimplementations.py`. SUMMARY 05-02 confirms "Phase 4 grep gates also still pass: 9/9" |
| T-05-02-05 | Repudiation | mitigate | closed | `.planning/evidence/t0_1_x/decision_note.md` cites `RuntimeError: TIMESCALE_PASSWORD is unset`; contains "Blocker" section + 5-step remediation; integration Test 3 enforces final-line verdict invariant |

### Plan 05-03 — monitoring tier-2 disposition

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-05-03-01 | Spoofing | mitigate | closed | `scripts/monitoring/tier2_escalate.sh` DELETED; `grep -rEn 'claude\s+-p' scripts/monitoring/` → 0 matches |
| T-05-03-02 | Tampering | mitigate | closed | `tier2_escalate.sh` + `tier2_mission.md` DELETED; `run_monitor.sh` rewritten — no `git` / `gh` / `claude` invocations |
| T-05-03-03 | Repudiation | accept | closed | `docs/decisions/ADR-011-monitoring-disposition.md:69-91` Consequences documents audit-trail boundary; `logs/monitor_tier1_failures.jsonl` retained as structured failure record |
| T-05-03-04 | Information disclosure | mitigate | closed | claude subprocess removed; `run_monitor.sh:24-51` `notify_operator_only()` uses only operator-controlled `TELEGRAM_WEBHOOK_URL`; no `GH_TOKEN` flow |
| T-05-03-05 | DoS | accept | closed | Moot — tier-2 deleted entirely. ADR-011 Consequences documents closure |
| T-05-03-06 | Elevation of Privilege | mitigate | closed | `auto_pr_janitor.sh` DELETED; no `gh pr create` path remains; `grep -rEn 'claude\s+-p' .github/workflows/` → 0 matches |
| T-05-03-07 | Tampering (future re-introduction) | mitigate | closed | `tests/security/test_no_unattended_claude_p_in_ci.py` — 4/4 tests passing (verified live); pins shell pattern `claude\s+-p\b`, Python list-arg pattern `"claude"\s*,\s*"-p"`, broad-scope grep with allowlist |

### Plan 05-04 — extended-backtest divergence

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-05-04-01 | Spoofing | mitigate | closed | `services/trading-engine/run_extended_backtest.py:16-31` "PERMANENT DIVERGENCE" docstring; `_emit_divergence_warning()` at L68-80 fires logger.warning with "RUN_EXTENDED_BACKTEST" + "diverges from live CoreAggregator"; pytest pins both |
| T-05-04-02 | Tampering | mitigate | closed | `services/trading-engine/tests/test_run_extended_backtest_divergence_warning.py` — 5 tests assert: punt language absent, PERMANENT DIVERGENCE marker present, CoreAggregator named, ADR-012 referenced, runtime warning fires |
| T-05-04-03 | Information disclosure | accept | closed | `docs/decisions/ADR-012-extended-backtest-disposition.md:66-93` Consequences + operator-guidance table; runtime warning + permanent docstring are operator-facing controls |
| T-05-04-04 | Repudiation | accept | closed | ADR-012 (102 lines) + 05-04-DECISION.md (198 lines) + docstring marker form audit trail |
| T-05-04-05 | DoS (option A only) | mitigate (N/A) | closed | Plan 05-04 selected option B (`document_divergence_permanently`) per `05-04-DECISION.md:110` — option A's DoS surface never materialized; threat moot |

---

## Per-Plan Verification Summary

| Plan | Threats | All CLOSED? | Test Run |
|------|---------|-------------|----------|
| 05-01 | 5 | yes | 32 tests pass (SUMMARY 05-01) |
| 05-02 | 5 | yes | 5 integration tests pass (SUMMARY 05-02) |
| 05-03 | 7 | yes | 4 security tests pass (verified live: `pytest tests/security/test_no_unattended_claude_p_in_ci.py -q`) |
| 05-04 | 5 | yes | 5 tests pass (SUMMARY 05-04) |
| **Total** | **22** | **22 / 22** | — |

---

## Unregistered Threat Flags

None.

- SUMMARY 05-01 "Threat Surface": "No new network endpoints, auth paths, or schema changes at trust boundaries beyond those in the plan's threat register."
- SUMMARY 05-02: No `## Threat Flags` section present; no new surface (pure config + evidence dir).
- SUMMARY 05-03 "Threat Flags": "None. No new network endpoints, auth paths, or file access patterns introduced. The removed files eliminated threat surface; the added test file is read-only analysis."
- SUMMARY 05-04: No new attack surface — docstring edit + module-level helper + 1 ADR + 1 test file.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-05-01 | T-05-01-02 | Solo-operator honour system; runbook reminder; no code-level defense against operator lying to themselves | operator | 2026-05-13 |
| AR-05-02 | T-05-01-04 | PSR-CI output committed to git as audit trail by design; no secrets in schema | operator | 2026-05-13 |
| AR-05-03 | T-05-02-01 | Cross-reference test enforced (Test 4); snapshot authenticity cannot be validated by code; PROJECT.md "Verification standards" applies | operator | 2026-05-13 |
| AR-05-04 | T-05-02-03 | Phase 3 commit convention; no PII or secrets in snapshot metadata | operator | 2026-05-13 |
| AR-05-05 | T-05-03-03 | ADR-011 documents audit-trail boundary; solo-founder scope; no regulatory requirement | operator | 2026-05-13 |
| AR-05-06 | T-05-03-05 | Moot — tier-2 deleted entirely under chosen disposition | operator | 2026-05-13 |
| AR-05-07 | T-05-04-03 | Runtime warning + ADR-012 are operator-facing controls; misinterpretation is operator-level concern | operator | 2026-05-13 |
| AR-05-08 | T-05-04-04 | ADR-012 + docstring + DECISION.md form audit trail preventing "edge proven" basis | operator | 2026-05-13 |

*Any organizational scaling beyond solo-founder requires revisiting T-05-01-02, T-05-02-01, T-05-03-03, T-05-04-04 specifically.*

---

## Spot-Check Verifications (Live)

| Check | Command | Result |
|-------|---------|--------|
| No `claude -p` in monitoring | `grep -rEn 'claude\s+-p\|"claude"\s*,\s*"-p"' scripts/monitoring/` | 0 matches |
| No `claude -p` in CI workflows | `grep -rEn 'claude\s+-p\|"claude"\s*,\s*"-p"' .github/workflows/` | 0 matches |
| Punt phrases absent | `grep "Fixing requires" run_extended_backtest.py` | 0 matches |
| Punt phrases absent | `grep "separate change" run_extended_backtest.py` | 0 matches |
| Tier-2 files deleted | `ls scripts/monitoring/tier2_escalate.sh tier2_mission.md auto_pr_janitor.sh` | all "No such file" |
| Tier-1 retained | `ls scripts/monitoring/tier1_monitor.py` | present (6880 bytes) |
| TOURN-07 — no parallel metric impls | grep in `psr_ci.py` | 0 matches |
| No centering in psr_ci.py | `grep "returns - returns.mean"` | 0 matches |
| `stationary_block_bootstrap_pvalue` not imported | grep | 0 matches |
| `probabilistic_sharpe_ratio` imported | grep | 1 match (import) |
| `_generate_block_resample` imported | grep | 1 match (import) |
| `len(returns) < 30` DoS guard present | grep | 1 match |
| YAML max_experiments ≤ 100 | yaml.safe_load | 100 (== cap) |
| YAML symbols ⊆ {SOL,BNB,ADA}USDT | yaml.safe_load | 3 valid symbols |
| Decision-note terminal verdict | `tail -1 decision_note.md` | `INSUFFICIENT_DATA` (valid verdict) |
| Decision-note cites failure reason | `grep "TIMESCALE_PASSWORD\|Blocker"` | multiple matches |
| Security test passes | `pytest tests/security/test_no_unattended_claude_p_in_ci.py -q` | 4 / 4 passed |
| ADR-011 ≥ 40 lines | `wc -l` | 99 lines |
| ADR-012 ≥ 30 lines | `wc -l` | 102 lines |
| Runbook ≥ 60 lines | `wc -l` | 238 lines |
| DECISION.md adequacy | `wc -l` | 285 / 229 / 198 lines (exceed plan minimums) |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-13 | 22 | 22 | 0 | gsd-security-auditor |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log (8 entries)
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-13

---

## Operator Notes

- The 7-day evidence loops per Tier-1 flag (T-05-01-03 chain) are operator action;
  the apparatus + gate are shipped, the evidence itself is not.
- Plan 05-02 tournament outcome is `INSUFFICIENT_DATA` due to empty `TIMESCALE_PASSWORD`
  in the tournament-harness container — documented infrastructure issue, not a code
  defect. Operator action required (5-step remediation in `.planning/evidence/t0_1_x/decision_note.md`).
- All accepted-risk entries (AR-05-01 through AR-05-08) remain solo-operator honour-system
  bound. Any organizational scaling will require revisiting T-05-01-02, T-05-02-01,
  T-05-03-03, T-05-04-04.
