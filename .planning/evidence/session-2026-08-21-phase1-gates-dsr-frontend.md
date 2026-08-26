# Session 2026-08-20/21 — shorts/gates, phase1 honesty, TA errors, DSR honesty, frontend health

Branch `fix/gates-ta-dsr` (from `feature/edge-search-v2` @ `80c7947`), 12 commits `df35367..03ff67d`. Four parallel audit scouts → five fix workflows (ultracode) → hostile reviews → deploy → live verify.

## Audit findings (scouts, 2026-08-20)

1. **No shorts / no trades at all.** Strategies are 90.8% SELL-signal (623:63). Shorts died at `short_min_confidence=0.70` — structurally unreachable: weights frozen at ⅓ (weights file never persisted), leg SELL caps 0.80/1.00, aggregator emitted 0 SELLs in 2,675 → ceiling 0.60. All-time max confidence 0.3804. Current run: **686/686 signals rejected** (379 short floor, 307 general 0.30 floor incl. every BUY). The 5 historical SHORTs predate gate enforcement (`224d4ce`).
2. **Phase 1** = frontend monitoring page for the trading-engine GATEKEEPER→VOTER→VALIDATOR pipeline. Its "errors" were backend: inert `hours` filter, LIMIT-1000 truncation (2524 vs 1000 vs 2517 in one payload), two rejection-rate formulas (46.0 vs 40.016), naive timestamps parsed as local time by JS.
3. **TA service healthy** (zero tracebacks/46h) but: 9,394 pandas FutureWarnings (`sqzmom_enhanced.py:496`), blank `{e}` error logs, BB class default 2.0 vs settings 2.5, endpoint defaults hardcoded not Settings-wired, LOG_LEVEL no-op, dead redis/config. Aggregator: dead `RESEARCH_WEIGHTS` (2026-02-25 Ichimoku tuning never applied), ADX votes by name-list omission, stale SQZMOM-disabled docs.
4. **DSR**: canonical kernel math verified correct against Bailey–LdP. Everything around it leaked: 3 rogue reimplementations fed annualized Sharpe into per-bar z (DSR = step function → **all pre-2026-08-20 walk-forward DSR results VOID**); `num_trials`=45 was CPCV combinatorics, ledger floor never bound; ML deploy gate off-by-default + fail-open on NaN; `cpcv_dsr` dead branch (always == dsr); tournament top-3 undeflated + NaN-truthy sort; `psr` = Sharpe of the model's own forecast path; tests ordering-only (dropping √V passed the suite).
5. **Frontend structurally healthy** (34/34 endpoints resolve, shapes match, 0 lint errors) but: 5 tiles hardcoded `forceStale`, `/phase1/latest` errors swallowed, 53 aborted requests/day (5s polling vs 8s endpoint), no error boundary, 3 dead hooks to nonexistent endpoints.

## Operator decisions

- Fix now; TA deploy mid-window; then **engine too** ("fix the gates too, the window is empty anyway") → isolation run `20260820T151351Z` **ABANDONED** (see `forward_paper_test/prefer_maker_orders/ABANDONED.md`). `complete-run` must not be forced against it.
- `short_min_confidence` → **0.35** (above 0.30 general floor, below 0.60 ceiling). `min_signal_confidence` 0.30 unchanged.
- DSR N = **max(trial-ledger count, 45)**, ledger seeded with documented pre-ledger history (24 entries, each source-cited; ledger 45→69 rows, 36→60 distinct → **floor now binds**), components (`ledger_count`, `n_paths`, `num_trials_used`) in every verdict.

## Fixes shipped (commits)

| Commit | What |
|---|---|
| `df35367` | short gate 0.35 + honest docstring + boot warnings (unreachable ≥0.60, inert ≤ general floor) |
| `66d8cb2` | phase1 provider rewrite: windowed minute buckets, true counts, one rate formula, tz-aware UTC |
| `c517f6e` | weights persistence (atomic write, validated load) |
| `bc77843` | aggregator hygiene: dead table deleted, role-based exclusion (behavior-identical, tested), doc fixes |
| `aec6a91` | TA: FutureWarning kill, Settings-wired endpoints (24 new fields), LOG_LEVEL honored, `{e!r}`+exc_info, dead config out |
| `06e949b` | compose: `trading_engine_data:/app/data` volume; TA redis env dropped |
| `fccd42f` | frontend: real stale badges (`dataUpdatedAt`), latestError surfaced, parseUtc, 30s/10s polling + parallel tickers, ErrorBoundary, dead code out |
| `698736d` | walk-forward DSR via canonical kernel on per-bar returns; NaN fails closed; $10k literals → shared.account |
| `0648d4f` | ledger seeding + trials accounting + repo-wide anti-reimplementation test |
| `6b0c3d1` | services DSR honesty: fail-closed gate ON (0.95) consuming honest-N `test_cpcv_dsr`; `psr`→NULL (`forecast_path_sharpe`); NULL-honest leaderboard; selection_pool_size annotation |
| `03ff67d` | dockerignore `**/logs/` (566MB live log broke repo-root build contexts) |

## Verification (2026-08-21)

Deployed TA, trading-engine, frontend, tournament-harness — 16/16 containers healthy. TA: 0 FutureWarnings, DEBUG honored. Engine: clean boot, no gate warnings at 0.35; rejections logged with reasons (current regime signals 0.11–0.13 < 0.30 — honest no-trade, not a stuck gate). Phase1: `hours=1` vs `hours=24` payloads differ; timestamps `+00:00`. Frontend: new bundle `index-BkYasbMG.js`. Tests: engine 253 passed, TA 559 passed (FutureWarning-as-error proven live — note `pytest.ini -p no:warnings` makes naive `-W error` gates inert; append `-p warnings`), DSR-area suites green; all sweep failures pre-existing (golden-parity staleness, $10k-era risk-metrics fixtures, salted-hash flake, archived-path test, pickle-identity test).

## Parked (design questions, not bugs)

- HOLD votes dilute the aggregator score (weight in denominator, 0 in numerator).
- Whether to apply the never-applied 2026-02-25 Ichimoku SELL-bias tuning.
- `min_signal_confidence=0.30` sits at the top of the observed signal range — most days will be no-trade.
- TA Settings env overrides bypass Query ge/le bounds (no boot validation).
- All-symbols-fail ticker fetch renders "No data yet" instead of Failed (pre-existing).
- risk-metrics: 15 pre-existing test failures with $10k-era fixtures (test files are the defect per CLAUDE.md §1).
