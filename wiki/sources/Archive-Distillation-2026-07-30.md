---
type: source
title: "Archive Distillation 2026-07-30"
status: current
created: 2026-07-30
updated: 2026-07-30
tags: [source, archive, distillation]
---

# Archive Distillation — 2026-07-30 vault restructure

On 2026-07-30 ~190 historical session/test/phase reports (Nov 2025 – May 2026) were moved to `docs/archive/` (excluded from the Graphify graph via `.graphifyignore`). This page preserves every **still load-bearing fact** found in them during the pre-archive audit, so nothing operational was lost. Originals remain readable in `docs/archive/`.

## Open engineering risks (verify before trusting/closing)

- **Walk-forward harness validates the wrong strategy.** `backtesting/run_walk_forward.py:105` exercises `phase1_strategy_prod` while production runs `strategy_mode: "ensemble"` (8–9 weighted voters). The ADR-013 §B gate (OOS Sharpe > 1.0, DSR ≥ 0.95 before re-arming) has **never measured the deployed strategy**. Source: `reports/walk-forward/2026-05-19.md`. Same gap flagged in `progress.md` follow-ups.
- **Bot was un-paused 2026-05-19 without clearing ADR-013 gates** — same day the walk-forward run returned GATE FAILS and recommended staying paused (`reports/edge-audits/2026-W21.md`). The weekly edge-audit W20 was silently never filed.
- **Unbounded log growth**: `services/api-gateway/logs/service.log` 834 MB, `services/portfolio-manager/logs/service.log` 941 MB (2026-05-20); no rotation anywhere. Also: trading-engine / technical-analysis / market-data / bybit-connector log to **stdout only** (file logs frozen 2025-10-30); api-gateway / portfolio-manager / risk-metrics write file logs (`reports/runtime-checks/2026-05-09.md`).
- **portfolio-manager snapshot UPSERT failure** (`ON CONFLICT` without matching unique constraint, 8× in `reports/runtime-checks/2026-05-19.md`). Possibly fixed by ADR-024 mirror work — **not explicitly confirmed**; verify before closing.
- **SOL-heavy 60/20/20 `symbol_allocations`** was wired into `services/trading-engine/app/config.py:185-194` (Dec 2025) and its premise invalidated days later. **No record it was ever reverted** — check config.
- **tensorflow==2.16.1 dead dependency** in trading-engine requirements (~600 MB image bloat) and portfolio-manager `/health` always-200 false positive — flagged in REVIVAL_PLAN 2026-05-02, unconfirmed fixed.
- **Dec-2025 security audit**: beyond the fixed JWT default-secret (2026-05-22), 4 HIGH + 6 MEDIUM findings were never individually dispositioned — triage against `AUDIT_2026-07-29_PRODUCTION_REVIEW.md` (`docs/archive/audits/SECURITY_AUDIT_REPORT_2025-12-12.md`).
- **Grafana default credentials `admin / crypto-bot-admin`** are printed in `docs/operations/MONITORING_GUIDE.md` — rotate and scrub.
- **Accessibility audit 2026-05-02** (archived): charts invisible to screen readers, primary CTA contrast 2.43:1, unlabeled Settings inputs — becomes actionable with the frontend-login work.
- **klines retention is 90 days** while walk-forward gates want 180-day windows — standing tension (`docs/architecture/DATA_PROFILE_KLINES.md`).

## Verification pass (2026-07-30, against code on disk)

- **SOL-heavy 60/20/20 — SUPERSEDED, not silently live.** `trading-engine/app/config.py:253` now carries a "BACKTEST-OPTIMIZED ALLOCATION (2026-01-19)": SOL 30%, BTC 25%, remainder ADA/BNB/ETH. ⚠️ **New finding:** those weights were optimized on Jan-2026 backtests — i.e., on the pre-ADR-018/021 corrupted measurement (broken accounting + testnet-polluted candles). The allocation itself deserves re-derivation on clean data.
- **tensorflow dead-dep — FIXED.** Removed from trading-engine requirements 2026-05-02 (comment in `requirements.txt:19`).
- **portfolio-manager UPSERT — FIXED.** `app/services/performance_history.py:137` now uses `ON CONFLICT (portfolio_id, ((timestamp AT TIME ZONE 'UTC')::date))` matching the `uniq_performance_portfolio_day` immutable-expression unique index from migration 002; the code comment documents the exact failure this repairs.
- **Legacy ensemble endpoint — STILL PRESENT.** `ml-prediction-service/app/main.py` still builds an `EnsemblePredictor` (which imports LSTM — part of the ML-PURGE footprint). Behind the `ml` compose profile so inert by default; delete with Phase 23.

## Settled empirical verdicts (do not re-litigate)

- **Grid trading v1**: 0.1% win rate on real 180-day data; every filter made it worse; crypto trends ~80% of the time vs grid's ranging requirement (`docs/archive/strategy-2025/GRID_TRADING_V1_FILTER_ANALYSIS.md`).
- **TA-only ML ceiling**: LSTM and GRU cannot beat ~53% (chance) directional accuracy on 60-min bars from technical indicators alone; more data/tuning didn't close the gap (`docs/archive/services/ml-prediction-service/ML_EXPERIMENTS_COMPLETE_SUMMARY.md`). Empirical basis for `ENABLE_ML_PREDICTIONS=false`.
- **`HYPERPARAMETER_OPTIMIZATION_GUIDE.md`** (archived) targets "R² > 0.95" on price levels — the exact forbidden V0 anti-pattern. Preserved as anti-example only.
- **All pre-2026-07-28 P&L numbers are measurement-corrupted** (broken paper accounting + testnet-polluted candles): the "+$35.67 profitable week", the 3.3×-improvement thesis, the 66%-WR loss analysis, and the symbol win-rate comparisons. The 5-symbol validated set was re-audited independently 2026-05-23 (Phase 16), so it stands on newer evidence.
- **Only live ensemble sample** (pre-accounting-fix, treat as corrupted): 31 closed trades / 30 days, 6.45% win rate, ~−$25 on $100 (2026-05-19).
- **Coverage-gaming pattern**: multiple services carry dedicated "coverage push" test files written to satisfy the 80% gate (8× in ml-prediction alone) — the Nov-2025 coverage numbers overstate real test quality (`docs/archive/testing-2025/TEST_INFRASTRUCTURE_ANALYSIS_REPORT.md`).

## Operational facts rescued from archived guides

- **Backups**: `scripts/backup_{timescaledb,postgresql,redis,all}.sh`, daily 02:00, 7-day daily / 28-day weekly retention (from PRODUCTION_FEATURES → see `docs/operations/DISASTER_RECOVERY.md`).
- **Redis 7.4.5** rejects inline comments in `redis.conf` `save` directive; `RABBITMQ_VM_MEMORY_HIGH_WATERMARK` env var is deprecated — both caused 24h+ restart loops (fixes live in `infrastructure/config/redis.conf` + compose).
- **Stat-arb code exists dormant** at `services/trading-engine/app/utils/statistical/` (~600-line cointegration.py + 23 tests, statsmodels/scipy deps).
- **Legacy ensemble endpoint** `GET /api/v1/predict/ensemble/{symbol}` on ml-prediction (:8007) with TA 40/ML 30/Sent 15/MTF 15 weights — contradicts the current pipeline; deletion candidate.
- **Backtester has always modeled 0.1% commission + 0.05% slippage** while the paper engine models neither (PAPER-01 gap).
- **Test DBs**: postgres :5434, timescaledb :5435, redis :6380; `scripts/test-db-{start,stop}.sh`, `verify-test-db.sh` (living guide: `docs/testing/TEST_DATABASE_SETUP.md`).

## Related

- [[_index|Sources Index]] · [[../hot|Hot Cache]] · [[../decisions/_index|Decisions]]
- Archive layout: `docs/archive/README.md`
