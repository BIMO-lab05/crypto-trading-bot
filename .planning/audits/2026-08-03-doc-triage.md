# Documentation Triage — 2026-08-03

Status: COMPLETE.
Scope: ~1,175 total .md files found; 734 real docs after excluding `node_modules` (777 files, not documentation) and `.claude/` (446 files, tooling config, excluded per task instructions).

## Universe partition (see Deliverable 2 for full detail)

| Bucket | Count | Treatment |
|---|---|---|
| `docs/archive/**` | 252 | Already archived by a prior pass. No action. |
| `.planning/**` | 209 (126 MB) | Protected GSD state. Do not move (see §Planning). |
| `wiki/**` | 95 | `wiki/decisions/` (29) untouchable ADR home. Rest classified below. |
| `.playwright-mcp`, `graphify-out`, `.pytest_cache` (root), `frontend/*.md` | 7+5+1+2=15 | Tool output / build artifact, not documentation. Excluded, counted only. |
| `docs/` non-archive | 62 | Classified individually below. |
| `services/`, `reports/`, `infrastructure/`, `backtesting/`, `tests/`, `scripts/`, `.github/`, root | 101 | Classified individually below. |

Excluded entirely and not further discussed: `.claude/` (446 files — agents/skills/commands, tooling not documentation), `node_modules` under `frontend/` (777 files), `services/*/.pytest_cache/README.md` (~11 files, pytest auto-generated), `tests/**/fixtures/*.md` (4 files, test input fixtures not docs).

---

## Deliverable 1 — Contradiction table

Ground rule applied: only **present-tense** claims are flagged. Dated reports/audits that correctly stated a fact **as of their own date** (e.g. "5% daily-loss" in a report from May 2026, before the 12% bump on 2026-08-03) are excluded from this table — they are ARCHIVE candidates for being superseded, not contradictions. This is called out per-row where relevant.

### P0 — actively misleads about money, risk, or safety

| Doc file:line | Claim | Refuted by (code/ADR) | Severity |
|---|---|---|---|
| `services/trading-engine/MULTI_SYMBOL_PORTFOLIO_GUIDE.md:38,128,147,151,179` | "Total Portfolio Value: $10,000 (paper trading)"; sizing math worked from a $10,000 base | `shared/account.py:11-13` ("THE ACCOUNT IS $100 USDT"); `services/trading-engine/app/config.py:568-571` (`paper_initial_balance` default `100.0`) | P0 |
| `services/trading-engine/MULTI_SYMBOL_PORTFOLIO_GUIDE.md:537` | "✓ Slippage considered (paper trading)" | `services/trading-engine/app/paper_trading.py:224-231` — order fills at `filled_price=current_price` with no slippage adjustment anywhere in the file; `wiki/decisions/ADR-011-paper-deterministic-execution.md` ("zero slippage... not invoked inside the paper engine") | P0 |
| `services/trading-engine/POSITION_SIZING_GUIDE.md:220,297` | Worked examples use `Balance: $10,000.00` / `current_balance=Decimal("10000")` for position-size math | `shared/account.py`; `config.py:568` (`100.0`) | P0 |
| `services/portfolio-manager/README.md:103-104,146,356` | Example API responses `"cash_balance": "10000.0"`, `"total_value": "10000.0"`; env example `INITIAL_CAPITAL=10000.0` | `services/portfolio-manager/app/config.py:51-52` (`initial_capital` default `100.0`) | P0 |
| `services/portfolio-manager/docs/PERFORMANCE_TRACKING.md:114,134` | Example payloads `"portfolio_value": "10000.00"`, `"start_value": "10000.00"` | same, `config.py:51-52` | P0 |
| `wiki/concepts/Risk-Model.md:14` (canonical KEEP page) | "Daily-loss circuit-breaker: 5% (`max_daily_loss_pct`)" | `wiki/decisions/ADR-028-daily-loss-breaker-reconciliation.md` (filed 2026-08-03, same vault) + `services/trading-engine/app/config.py:364-365` default now `12.0` | P0 |
| `wiki/concepts/_index.md:17`, `wiki/overview.md:44` | "5% daily-loss breaker" | same as above — `ADR-028` / `config.py:365` | P0 |
| `services/trading-engine/README.md:25` (service's own canonical README) | "5% daily loss circuit breaker" | `config.py:364-365` (`12.0`, bumped same day per ADR-028) | P0 |
| `services/technical-analysis/backtesting/OPTION_C_IMPLEMENTATION.md:5,20,62,64` | "three profitable symbols (SOLUSDT, **DOGEUSDT**, BNBUSDT)"; table row "DOGEUSDT \| +630% \| 28% \| 5.41 \| 29" | `CLAUDE.md` "Validated symbols" section — DOGEUSDT explicitly **excluded**, "no silent re-add"; CLAUDE.md §2 — every strategy has negative Sharpe, no demonstrated edge. Also dated Nov 2025, pre-2026-04-25 testnet/mainnet contamination cutoff | P0 |

### P1 — wrong architecture or API surface

| Doc file:line | Claim | Refuted by | Severity |
|---|---|---|---|
| `README.md:13` (root keeper file) | "RabbitMQ (events)" listed as part of the data stack, implying a live event bus | `wiki/decisions/ADR-016-http-not-events.md`; `docs/architecture/SYSTEM_OVERVIEW.md:10` ("no live RabbitMQ event bus... 0/11 services... treat any event topic as aspirational") | P1 |
| `docs/operations/DOCKER_REFERENCE.md:621,630,636,696`; `docs/operations/RUNBOOK.md:664`; `docs/deploy/KUBERNETES_RUNBOOK.md:775` | Plain `docker-compose.yml` presented as the base/dev/prod compose file to run against | `wiki/decisions/ADR-009-docker-compose-unified-canonical.md` — unified is canonical, plain file is incomplete and disagrees on values. Confirmed concretely: `docker-compose.yml:325` sets `MAX_TOTAL_EXPOSURE_PCT=70.0` vs `docker-compose.unified.yml:616` default `80.0` | P1 |
| `services/ml-prediction-service/docs/GRU_MODEL.md`, `ENSEMBLE_PREDICTIONS.md`, `GRU_IMPLEMENTATION_SUMMARY.md`, `tests/README.md` | Describe LSTM as a live, selectable, trainable model with full working API examples ("default: 'LSTM'", `train_lstm_model(...)`, LSTM/GRU comparison) | `services/ml-prediction-service/app/predictor_factory.py:25-26` (`if model_type == "LSTM": raise ValueError(...)`) ; `app/main.py:1386-1392` (`POST /api/v1/models/train` returns "LSTM training removed") | P1 |
| `CLAUDE.md` ML stack bullet — "`_archive_lstm/` does not exist anywhere in the tree" | Claim about LSTM purge completeness | Filesystem: `services/ml-prediction-service/models/_archive_lstm/` **exists**, with 18+ archived `.keras` files, matching the path `wiki/decisions/ADR-001-LSTM-removed.md:25` itself describes. Narrow miss: real path is `models/_archive_lstm/`, not `app/_archive_lstm/`. The other half of the CLAUDE.md claim ("`ensemble_model.py:15` still imports LSTM") is verified correct — `services/ml-prediction-service/app/models/ensemble_model.py:15` does `from tensorflow.keras.layers import LSTM, ...` | P1 |

### P2 — stale status claims (detail, not exhaustive — see note)

- Widespread "5% daily-loss" mentions across `docs/operations/{ALERTING_GUIDE,MONITORING_GUIDE}.md`, `infrastructure/monitoring/README.md`, `scripts/README.md`, `services/ml-retraining-service/docs/REENABLE_ML_RUNBOOK.md`, `services/trading-engine/DEPLOYMENT_CHECKLIST.md:15,187` — all now stale post-ADR-028 (2026-08-03, same day as this audit), expected drift, low urgency since the bump is hours old.
- `services/risk-metrics-service/README.md:59,173` — "5% daily loss limit" — **checked and excluded**: matches that service's own `app/config.py:38` (`max_daily_loss: float = 0.05`), a real but pre-existing cross-service inconsistency already documented in `wiki/.raw/agent-reports/risk-metrics-service.md:155`, not a new doc/code contradiction.
- `services/trading-engine/DEPLOYMENT_CHECKLIST.md:702,717` — contains a stale `{"balance": 10000.00}` example but **self-annotates** the error at line 717 ("Default paper balance is $100 (ADR-010), not $10,000"). Lower severity because self-correcting.
- Dated reports that were correct for their own date (excluded from contradiction table, routed to ARCHIVE instead): `FIXES_2026-07-28_COMPREHENSIVE.md:24`, `reports/edge-audits/2026-W21.md:178-247`, `reports/runtime-checks/2026-05-09.md:49`, `reports/runtime-checks/2026-05-19.md:112`.
- `docs/testing/TESTING_QUICK_START.md:181,194,197` and `docs/development/E2E_TESTING_GUIDE.md:352` use `Portfolio(balance=10000)` / `Decimal("10000.00")` as generic pedagogical example fixtures. Not a claim about the real account (no severity assigned) but worth a one-line fix to avoid teaching the wrong convention.
- `docs/setup/BYBIT_API_SETUP_GUIDE.md:233-234` "available_balance": 100000.0 — this is a real Bybit **testnet** wallet response (Bybit testnet accounts are preloaded with 100k testnet USDT), unrelated to our $100 paper balance. Checked and excluded.


---

## Deliverable 2 — Classification and counts

### Root (target ≤ 6; landing at 4)

| File | Verdict | Why |
|---|---|---|
| `README.md` | KEEP | Primary entry point; correct except the RabbitMQ P1 line noted above |
| `CLAUDE.md` | KEEP | Load-bearing agent instructions; correct except the narrow `_archive_lstm/` path claim above |
| `RUNBOOK.md` | KEEP | Current (references ADR-004/010/028-era flags correctly), cross-linked from `docs/operations/RUNBOOK.md` |
| `progress.md` | KEEP | Running session log per project convention; append-only, explicitly not where ADRs go |
| `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` | ARCHIVE | Dated one-off audit, superseded by `.planning/audits/2026-07-31-full-system-diagnostic.md` and later ADRs |
| `FIXES_2026-07-28_COMPREHENSIVE.md` | ARCHIVE | Dated "comprehensive fixes" completion note; content already folded into CLAUDE.md gotchas and wiki ADRs |

Root lands at **4** files — under the 6-file ceiling (a ceiling, not a quota, per task wording).

### Counts by directory (excluding `.claude/` and `node_modules`, per task instructions)

| Directory | Files | KEEP | MERGE | ARCHIVE | UNSURE |
|---|---|---|---|---|---|
| root | 6 | 4 | 0 | 2 | 0 |
| `docs/` (non-archive) | 62 | 37 | 1 | 24 | 0 |
| `docs/archive/` | 252 | — (already archived, no action) | | | |
| `wiki/` (non-decisions) | 66 | 54 | 0 | 12 | 0 |
| `wiki/decisions/` | 29 | 29 (untouchable) | 0 | 0 | 0 |
| `services/` | 56 total, 11 excluded (`.pytest_cache`) → 45 real | 26 | 0 | 19 | 0 |
| `reports/` | 10 | 0 | 0 | 10 | 0 |
| `infrastructure/` | 10 | 8 | 0 | 2 | 0 |
| `backtesting/` | 7 | 1 | 0 | 6 | 0 |
| `tests/` (excl. 4 fixture .md, not docs) | 2 | 2 | 0 | 0 | 0 |
| `scripts/` | 3 | 3 | 0 | 0 | 0 |
| `.github/` | 3 | 1 | 0 | 2 | 0 |
| `.planning/` | 209 | protected — not classified, see below | | | |

Excluded entirely, counted only (not documentation): `.claude/` 446, `frontend/node_modules` 777, `.playwright-mcp` 7, `graphify-out` 5, root `.pytest_cache` 1, `frontend/*.md` 2 (real: `PRICECHART.md`, `README.md` — these ARE real docs, see below), `services/*/.pytest_cache/README.md` ~11, `tests/**/fixtures/*.md` 4.

Correction: `frontend/PRICECHART.md` and `frontend/README.md` are real documentation (not node_modules). Both KEEP — frontend has no other doc coverage and these are the only source of frontend-specific setup/component notes; not duplicated in `docs/` or `wiki/`.

### `.planning/` (209 files, 126 MB) — GSD framework state, left alone per task rule

Not classified individually; per-task instruction: "do not archive anything from the current milestone." The v1.0/v1.1/v1.2 milestone trees (`MILESTONE-AUDIT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `*-phases/`) look like completed-milestone ARCHIVE candidates by content, but moving GSD framework state risks breaking the framework's own path resolution — flagged as **UNSURE**, proposed as a separate commented-out batch in the script requiring explicit operator sign-off, not executed here.

Cross-checked against `.planning/audits/2026-07-31-full-system-diagnostic.md` and `.planning/audits/2026-07-30-strategy-audit.md` as prior-audit evidence sources (not ground truth, per coordinator note) — both predate the 2026-08-03 capital/ADR-028 work and their capital-related claims were treated as historical, not current.

### `docs/` non-archive detail (62 files)

**ARCHIVE (24):**
- `docs/strategy/` — entire tree (22 files): `RESEARCH_PLAN_2026-04-29.md`; `evidence/phase_b_walkforward_ensemble_2026-05-20.md`, `evidence/phase_c_results_2026-05-06.md`; `research-2026-04-29/` (14 files: `01-crypto-factors.md` through `06-execution-sizing.md`, `T0.1-*`, `T0.2-cpcv-design.md`, `T1.2-*`, `V0-FINDINGS-gru-metric-bug.md`, `V0-RESULTS-no-edge.md`); `research-2026-05-21/` (5 files incl. `horizon-1D/`, `horizon-4H/`, `horizon-4H-fresh/` subdirs). Rationale: dated research folders (explicit ARCHIVE signal), orphaned — **nothing in `wiki/` links to `docs/strategy/`** (checked via grep, zero hits), and superseded by `wiki/decisions/ADR-013-strategy-rebuild-plan.md` which is the living decision record.
- `docs/ml/ML_DATA_COLLECTION_GUIDE.md` — pre-GRU-rebuild era framing ("ALL technical analysis strategies failed... Phase 3 development"), superseded by `wiki/concepts/ML-Status.md`.

**MERGE (1):**
- `docs/operations/DOCKER_REFERENCE.md` → target `wiki/decisions/ADR-009-docker-compose-unified-canonical.md`. Carry over: the dev/prod-overlay command patterns (`docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d` etc., lines 621-636) are genuinely useful *if* rewritten against `docker-compose.unified.yml` — the overlay pattern itself isn't wrong, only the base-file choice is. Otherwise KEEP-with-fix, not archive, since it's the only doc covering overlay composition.

**KEEP (37):** everything else — `docs/README.md`, `docs/architecture/*` (2), `docs/deploy/*` (4), `docs/development/*` (3), `docs/operations/*` (10 of 11, excl. merged one), `docs/reference/*` (2), `docs/runbooks/*` (2), `docs/security/*` (7), `docs/setup/*` (2), `docs/testing/*` (5). These are current operational/reference guides; several need small content fixes (noted in P2) but are structurally load-bearing and not superseded elsewhere.


### `wiki/` non-decisions detail (66 files)

**ARCHIVE (12):**
- `wiki/.raw/agent-reports/*.md` (11 files) — raw ingestion inputs from the Stage-1 code-mapping agents; superseded by the distilled `wiki/modules/*.md` pages that cite them. Per wiki's own page-type convention these are working inputs, not a page type (`module`/`concept`/`flow`/`decision`/`source`) meant for ongoing reference.
- `wiki/meta/lint-report-2026-05-06.md` — superseded by `wiki/meta/lint-report-2026-07-30.md` (keep the newer one).

**KEEP (54):** `wiki/CLAUDE.md`, `_templates/*` (5, schema), `components/*` (3), `concepts/*` (13, incl. `_index.md`), `dependencies/_index.md`, `flows/*` (4), `hot.md`, `index.md`, `log.md`, `meta/_index.md`, `meta/lint-report-2026-07-30.md`, `modules/*` (10, incl. `_index.md`), `overview.md`, `questions/_index.md`, `sources/*` (5, incl. `_index.md`) — this is the living vault; content-fix flags (Risk-Model.md, concepts/_index.md, overview.md needing the 12% update) are noted in the contradiction table, not archived.

### `services/` detail (45 real files after excluding `.pytest_cache`)

**ARCHIVE (19):**
- `services/ml-prediction-service/docs/ENSEMBLE_PREDICTIONS.md`, `GRU_IMPLEMENTATION_SUMMARY.md`, `GRU_MODEL.md` — describe removed LSTM as live (P1 contradiction above)
- `services/ml-prediction-service/tests/README.md` — LSTM test suite description, stale
- `services/trading-engine/DEPLOYMENT_CHECKLIST.md` — self-annotated historical; superseded by root `RUNBOOK.md`'s "Pre-LIVE Operator Checklist" (which the file itself points readers to at line 187)
- `services/trading-engine/MULTI_SYMBOL_PORTFOLIO_GUIDE.md` — P0 contradictions above, no self-correction
- `services/trading-engine/POSITION_SIZING_GUIDE.md` — P0 contradiction above
- `services/trading-engine/docs/AUTOMATED_TESTING_SUMMARY.md` — dated 2025-11-11, "Status: ALL TASKS COMPLETED"
- `services/trading-engine/tests/integration/DATABASE_PERSISTENCE_TESTS_IMPLEMENTATION.md`, `INTEGRATION_TEST_REPORT.md` — completion reports
- `services/technical-analysis/backtesting/BACKTEST_IMPLEMENTATION_COMPLETE.md`, `BTC_ETH_REAL_DATA_ANALYSIS.md`, `DELIVERY_SUMMARY.md`, `OPTION_C_IMPLEMENTATION.md` (P0 above), `PARAMETER_OPTIMIZATION_DELIVERY.md`, `SQZMOM_BACKTEST_REPORT.md` — dated Nov 2025 result/completion reports, pre-2026-04-25 testnet-contamination cutoff

**KEEP (26):** `api-gateway/README.md`, `bybit-connector/README.md`, `market-data-service/README.md` + `SCHEDULER_SETUP.md`, `ml-prediction-service/README.md` (already self-corrects the LSTM status — good current doc), `ml-retraining-service/README.md` + `docs/REENABLE_ML_RUNBOOK.md`, `notification-service/README.md`, `portfolio-manager/README.md` (KEEP-with-fix, P0 noted above) + `app/optimization/README.md` + `docs/PERFORMANCE_TRACKING.md` (KEEP-with-fix), `risk-metrics-service/README.md` + `docs/CIRCUIT_BREAKER.md` + `tests/README.md`, `sentiment-analysis-service/README.md` + `agents/README.md` (explicitly self-annotated as an inert scaffold, honest) + `tests/README.md`, `technical-analysis/README.md` + `backtesting/README.md` + `backtesting/README_OPTIMIZATION.md` + `backtesting/OPTIMIZATION_GUIDE.md` + `docs/SQZMOM_INDICATOR.md` + `docs/SQZMOM_QUICK_START.md`, `trading-engine/README.md` (KEEP-with-fix, P0 daily-loss % noted above) + `MONITORING_GUIDE.md` (dated 2026-07-30, current) + `app/strategies/arbitrage/README.md` + `docs/DEPENDENCY_MANAGEMENT.md` + `tests/integration/README.md` + `tests/integration/QUICK_START.md`.

### `reports/` (10 files) — ARCHIVE, all

`edge-audits/2026-W19.md`, `edge-audits/2026-W21.md`, `premarket/2026-05-08.md`, `premarket/2026-05-19.md`, `premarket/2026-05-20.md`, `runtime-checks/2026-05-08.md`, `runtime-checks/2026-05-09.md`, `runtime-checks/2026-05-19.md`, `runtime-checks/2026-05-20.md`, `walk-forward/2026-05-19.md`. All are individually dated, self-contained scheduled-task output snapshots (verdicts like "SKIPPED", "DEGRADED", "GATE FAILS") — the definition of a dated status report. The living how-to guides for this reporting system (`docs/operations/PERFORMANCE_REPORTING.md`, `WEEKLY_REPORT_INDEX.md`, `WEEKLY_REPORT_QUICK_START.md`) are KEEP and unaffected.

### `infrastructure/` (10 files)

**ARCHIVE (2):** `kubernetes/staging/DEPLOYMENT_REPORT.md` (dated 2025-12-12, one-off deployment summary), `kubernetes/security/SECURITY_CONFIGURATION_SUMMARY.md` (dated 2025-12-12, "Summary" completion report, superseded by `docs/security/SECURITY_HARDENING.md`).
**KEEP (8):** `DATABASE_SETUP.md`, `helm/README.md`, `kubernetes/README.md`, `kubernetes/security/README.md`, `kubernetes/staging/README.md`, `monitoring/PROMETHEUS_INSTRUMENTATION_GUIDE.md`, `monitoring/README.md`, `production/README.md`.

### `backtesting/` (7 files)

**ARCHIVE (6):** all of `backtesting/backtesting/results/*.md` — dated result snapshots from 2025-11-14/16, pre-2026-04-25 testnet/mainnet contamination cutoff, i.e. doubly invalid as evidence (stale AND contaminated data).
**KEEP (1):** `backtesting/README.md` — living how-to for the module.

### `tests/`, `scripts/`, `.github/`

- `tests/e2e/README.md`, `tests/security/README.md` — KEEP (living test guides). `tests/closure/fixtures/*.md` (2) and `tests/fixtures/v15_supersession/*.md` (2) are test fixture data, not documentation — excluded from classification.
- `scripts/README.md`, `scripts/forward_paper_test/README.md`, `scripts/monitoring/README.md` — KEEP, all current operational guides.
- `.github/CICD_README.md` — KEEP, living reference matching the 20 workflow files actually in `.github/workflows/`.
- `.github/CICD_IMPLEMENTATION_REPORT.md`, `CICD_SUMMARY.md` — ARCHIVE, dated 2025-11-23 completion reports, redundant with `CICD_README.md`.


---

## Deliverable 3 — the script

`.planning/audits/2026-08-03-doc-archive-plan.sh` — 8 commit batches, 73 files total, `set -euo pipefail`, loud "UNREVIEWED" banner at top. Not executed. `.planning/` completed-milestone cleanup is deliberately left as a commented-out, unenumerated block requiring separate operator review (see script tail).

All 73 candidate paths were verified both `git ls-files`-tracked and present on disk before being written into the script (checked via `git ls-files --error-unmatch`, not bare `git status`).

## Status: COMPLETE

