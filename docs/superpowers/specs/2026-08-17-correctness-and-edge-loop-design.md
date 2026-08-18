# Correctness + Edge Loop — Design

**Date:** 2026-08-17
**Status:** Approved by operator (section-by-section, this session)
**Predecessors:** `2026-08-12-profit-path-defect-repair-design.md` (16 defects fixed, 29 minors catalogued), edge battery 2026-08-17 (`.planning/evidence/killtests/battery-summary-20260817.md`, 4× REJECT)

## 1. Goal

Two workstreams, strictly ordered:

1. **WS1 Correctness** — fix the catalogued open defects that mechanically lose money, bypass risk rails, or corrupt measurement, so every subsequent number the system produces is trustworthy.
2. **WS2 Edge loop** — a repeating, evidence-gated research cycle that designs smarter strategy candidates and runs them through the `edge_lab` kill-funnel. Only a candidate that passes every gate is implemented in the engine. The loop iterates across batteries until a candidate passes or the operator stops it.

Context this design confronts: the "why unprofitable" question is answered — no bug causes it; deployed strategies are chance-level (H4: 49.07% directional accuracy, DSR 0.0) and round-trip costs exceed gross edge 2–4×. WS1 cannot create profit; it makes WS2's verdicts honest. Profit, if it comes, comes only from WS2.

## 2. Non-goals

- **LIVE trading.** Mechanically impossible at $100 (2% LIVE cap = $2 < $5 Bybit min notional). Nothing here moves toward a LIVE flip.
- **ML re-enable.** Stays `ENABLE_ML_PREDICTIONS=false`; requires a DSR > 0.95 leaderboard row (separate track, Phase 9 auto-flip machinery already armed).
- **Re-auditing closed work.** The 16 fixes of 2026-08-12 and the 2026-08-17 battery verdicts stand as evidence; they are inputs, not subjects.
- **Phase 19/20 scope.** Order reconciliation + `orderLinkId` idempotency (Phase 19), monotonic paper order ids and the Jan-2026 regression-test suite (Phase 20) stay owed to their roadmap phases. Note: §3D's paper funding accrual and backtester stop-fill fixes come from the 2026-08-12 minors catalogue and are *not* part of Phase 20's owed set — no overlap.
- **Reporting-only minors.** PM performance zeros, snapshot upsert collision, unset Prometheus gauges, dead compose keys, per-process paper summary — catalogued in the 2026-08-12 audit, deliberately excluded here.

## 3. WS1 — Correctness (four buckets)

Sources: Phase-22 rounding catalogue, `.planning/evidence/profit-path-audit-2026-08-12.md` deferred-minors table, TA-AGG requirements. All sites re-verified against the working tree on 2026-08-17. One defect per commit, test-first.

### 3A. Precision — the `round(price, 2)` class

The class already caused 30+ flip-flop ADA losses (fixed instance: `487d1bd`). Remaining sites destroy sub-$1 price/stop precision.

**Amended 2026-08-17 after recon — no tick-size helper is built.** The shipped PRICE-01 precedent (`research_optimized_strategy.py:722-724`) is to *remove* the rounding, not to quantize: strategy-layer levels are in-engine triggers compared against market price, never submitted to a venue. Neither `MomentumBreakoutStrategy` nor `TrendFollowingStrategy` has a `symbol` in scope to key a tick lookup, and quantization already has two owners at order time — `costs.quantize_price` and `limit_order_executor._round_to_tick`. The fix is `float(_)` / bare value.

- Remove every price-domain 2dp rounding in:
  - `services/trading-engine/app/strategies/momentum_breakout_strategy.py` (DORMANT — no runtime caller in `app/`)
  - `services/trading-engine/app/strategies/trend_following_strategy.py` (DORMANT)
  - `services/trading-engine/app/strategies/support_resistance_strategy.py` (DORMANT) — SL/TP + EMA + ATR
  - `services/trading-engine/app/utils/support_resistance_detector.py` (DORMANT) — level price + zone bounds
  - `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` (**LIVE** — served at `/api/v1/strategies/sqzmom/signal/{symbol}`) — entry/stop/TP
  - `services/technical-analysis/app/indicators/sqzmom_enhanced.py` `to_dict` — bands/price at 4dp (library-contract rot; not on the live route)
  - Non-price rounds (RSI, volume ratio, position fraction, strength score) are explicitly **excluded** — a blanket strip would be wrong.
- Fix `support_resistance_strategy.py:380` — ATR rounded to 2dp. **Correction:** this does not raise `ZeroDivisionError`. `round(np.float64, 2)` preserves the numpy type and division by `np.float64(0.0)` yields `inf` with a RuntimeWarning, so the failure is *silent*: `atr_multiple=inf` and TP1/TP2 pinned exactly at entry. Also harden the vacuous guard at `:653` (`abs(total_distance) < atr * 1.5` is never true when `atr == 0.0`).
- **Guard:** an AST-based invariant test banning `round(x, 2)` in a bounded `SCANNED_FILES` tuple, modeled on the `$100` account-invariant AST test (`260803-4mt`). `SCANNED_FILES` may list only files already fixed — ~17 out-of-scope sites exist in `app/indicators/*.py`, so the tuple grows per plan, keeping every commit green.

### 3B. Aggregator truth — legs that vote zero or never vote

**Amended 2026-08-17 after recon — the leg inventory in the original draft was wrong.** ADX has voted in the trading-engine since 2026-05-06 (`signal_aggregator.py:750`, active). Volume is deliberately **non-voting** by design: it is a post-vote confidence multiplier in `aggregation/validator.py`, and promoting it to a voter would double-count volume *and* inject systematic long bias through the `confirmed → BUY` mapping at `signal_aggregator.py:301-309`. There are two distinct aggregators — the trading-engine `SignalAggregator` class and the TA-side module function `get_aggregated_signal` (`handlers/analysis.py:19`); every task must name which.

Corrected item list:

- **NEW (live defect, not in the original draft):** TA `get_aggregated_signal` returns `{signal: "BUY", confidence: 0.0}` when every indicator fails — a phantom directional label on zero information. `max()` over the all-zero weight dict returns `"BUY"`, which takes the directional branch and its `else 0.0` arm; the `0.5` neutral fallback is only reachable for `HOLD`. This is one of the 3 known-failing TA tests (`test_empty_signal_list_returns_neutral_fallback`). Highest value-per-line item in WS1.
- **TA-side legs:** add ADX and Enhanced SQZMOM as voting legs to `get_aggregated_signal` (both computed in-service today, neither consulted). Volume enters as a **confidence multiplier** mirroring the engine's validator tiers — never as a vote, since its labels are `CONFIRM`/`REJECT` and would `KeyError` the weight dict into an HTTP 500.
- **Engine dead leg:** `signal_aggregator.py:746` — `SQZMOM_ENHANCED` is commented out of `fetch_all_indicators`. Its disable rationale ("stuck at 0.50 HOLD") was root-caused and fixed 2026-05-05; the fetcher, its 1.4 metadata weight, and its VOLATILITY category all still exist. Re-enable deliberately.
- **Engine ADX hygiene:** ADX is absent from `voter.py` `INDICATOR_CATEGORIES`, so it counts as its own `"OTHER"` category and weakens the diversity gate. One-line fix.
- **Engine MTF (DORMANT — needs both `enable_ml_predictions` and `enable_multi_timeframe`):** `enhanced_aggregator.py:312/317` compares a 0–1 payload against a 50.0 threshold, and `:314` reads `signal_strength`, a key the TA payload never contains (correct key: `confidence`). **Both must land in one task** — either fix alone still yields a permanently-zero leg, so the test stays red.
- **Engine VP: DELETE, not repair.** Unreachable by any flag or env (`enable_volume_profile` defaults False and `get_auto_trader()` never passes it), broken independently at two layers (wrong host + wrong envelope + wrong element shape; `Decimal` without import), zero tests, and every consumer already reads `.get(..., {})` so removal is a behavioral no-op. Repairing it would also activate a latent `TypeError` at `auto_trader.py:4139` (producer writes `take_profit` as a dict).
- **TA-AGG-02/03:** TA `main.py` Query defaults move to the existing Settings fields — the correct names are `default_macd_fast` / `default_macd_slow` / `default_macd_signal`, `default_bb_period` / `default_bb_std`, and `default_rsi_period` (not `macd_*` / `bollinger_std_dev`). The engine deliberately relies on these endpoint defaults as the single source of truth, so an operator env override currently reaches `/analyze` but not `/indicators/macd` — a silent split-brain.

### 3C. Risk-rail integrity

| Site | Defect |
|---|---|
| `services/trading-engine/app/risk_manager.py:230` | Exposure check/reporting uses original quantity, not remaining quantity |
| `services/trading-engine/app/position_sizing.py:216` | Fraction-vs-percent confusion — PositionSizer max-risk clamp silently never fires on the auto-trader path |
| `services/trading-engine/app/auto_trader.py:3849` | Standard-mode entry bypasses daily trade limit and same-symbol cooldown recording |
| `services/trading-engine/app/auto_trader.py:1824` | Portfolio-heat gate fed a size and stop the actual order does not use |
| `services/trading-engine/app/performance_tracker.py:186` | P&L gross of fees/slippage on full original quantity — distorts stats feeding Kelly sizing |
| `services/trading-engine/app/auto_trader.py:2249` | Slippage manager fed expected==actual on every entry — adaptive rejection stats measure constant zero |

The units trap applies (`max_risk_per_trade` fraction vs `*_pct` percents) — every fix here normalizes before comparing.

### 3D. Measurement honesty

| Site | Defect / action |
|---|---|
| `services/trading-engine/app/paper_trading.py:266` | Paper engine never accrues funding (~$49 unmodelled in H3 economics). Add funding accrual on held positions |
| `services/trading-engine/app/backtesting/backtest_engine.py:422` | In-service backtester fills stop/TP exits at bar.close, not the stop price. Fill at stop with slippage |
| `backtesting/run_phase1_backtest.py:494` | Research runners default to $10,000 — violate the $100 invariant; source from `shared.account` |
| `backtesting/screen.py:318` | Third hand-copied slippage table — add a drift-guard test asserting agreement with the paper engine's model |
| `services/trading-engine/app/config.py:36` | `portfolio_manager_url` default points at 8006 (notification-service), not 8003 |
| `services/trading-engine/app/live_trading.py:229` | LIVE shared path records fills at reference price with zero fees and overwrites the paper cash ledger. **Fence it** (hard error / isolation), do not build it out — LIVE is a non-goal |

## 4. WS2 — Edge loop

### 4.1 Battery protocol (per round)

1. **Pre-register** — `backtesting/edge_lab/candidates/battery_<date>_manifest.md`, committed *before* implementation. Per candidate: hypothesis, economic mechanism (why the edge should exist and who pays it), variant parameters, cost assumptions. No candidates or variants added after the run starts.
2. **Implement** — candidate modules under `backtesting/edge_lab/candidates/`, reusing `fetch`, `universe`, `gate1`, `gate2`. Universe stays pinned (`universe_2026-08-17.json`); data traps already handled (`datetime64[us]` cast, pre-2026-04-25 pollution excluded by CSV-based pipeline).
3. **Run** — `run_battery.py`: Gate 0 data sanity → Gate 1 cost hurdle (gross edge ≥ 2× round-trip cost) → Gate 2 CPCV + DSR > 0.95, pooled PF (pooled over trades, never mean-of-folds).
4. **Verdict** — one `*-verdict-<date>.md` + JSON per candidate plus a battery summary in `.planning/evidence/killtests/`. REJECT is a complete, successful deliverable.
5. **Checkpoint** — operator reviews verdicts and directs (or stops) the next round. Batteries never auto-loop.

### 4.2 Trial ledger — the anti-p-hacking rail

Operator chose open-ended iteration ("iterate more batteries until something passes"). Unbounded candidate mining makes a lucky false positive inevitable unless the selection bar accounts for every trial ever made. Therefore:

- `backtesting/edge_lab/trial_ledger.json` — append-only record of every variant ever gate-tested, seeded retroactively with the 2026-08-17 battery (8 variants) and the H-series killtests.
- Gate 2 computes DSR with the trial count read from the ledger, not from the current battery.
- A ledger entry is written even for variants that die at Gate 1 or produce zero trades — they were still trials.
- **Honest statement of when the rail actually binds (amended 2026-08-17).** `gate2.py:263` uses `num_trials=max(num_trials_floor, n_paths)`, and `n_paths` reaches 45 at the pinned CPCV 10/2 configuration (the H4 verdict records `num_trials_used: 45`). A ledger-derived count therefore changes nothing until it exceeds 45, or when a short series yields few variance-valid paths. The rail is still correct and still the right design — it binds where mining would otherwise be cheapest — but "the bar rises every battery" is false as a literal claim and must not be repeated in verdict docs.
- **Threading requirement.** `Gate2Result` has no field recording the trials count actually used, and `verdicts.py` imports `NUM_TRIALS_FLOOR` directly at three render sites (`TRIALS_CAVEAT`, the criterion line, the JSON `thresholds` block). The effective floor must be threaded into `Gate2Result`, the variant record, and all three render sites — otherwise every future verdict doc states 16 while Gate 2 deflated against something else, and the docs' own "read live from `edge_lab.config`, not transcribed" claim becomes a lie.
- `NUM_TRIALS_FLOOR = 16` stays pinned as the static lower bound (`config.py`'s docstring: changing a pinned value after verdicts exist invalidates them). The ledger count layers on top via `run_gate2`'s existing `num_trials_floor` parameter, which no production caller passes today.

### 4.3 Battery #1 seeds (finalized at pre-registration)

| Candidate | Rationale | Prior |
|---|---|---|
| Funding-carry refinements | Best survivor 2026-08-17: `thresh_2x` cleared Gate 1 at ratio 2.603, died Gate 2. Variants: funding-percentile entry, holding-period sweep, symbol filter | Highest |
| Pairs / stat-arb | Cointegration on the pinned top-30 — the one classic family no battery has tested. `pairs_trading` code exists as prior art (its tests are among the known-failing families; edge_lab implementation is independent) | Medium |
| Regime-gated trend | lf_trend cleared Gate 1 (ratios 4.85 / 15.51) but profit was a few outliers; a regime filter attempts to turn outliers into a distribution | Low (stated honestly) |

### 4.4 Promotion path (only on Gate-2 PASS)

1. Hostile review by `quant-skeptic` — default verdict "no edge"; the PASS must survive it.
2. Implementation per `trading-strategy-dev` contract: `StrategyBase` subclass, ATR-derived stops (no fixed-percentage), `calculate_position_size` honoring caps, SHORT enforcement per `380a674`.
3. Venue-floor check: with a $10 per-trade cap and $5 min notional, the candidate must be tradeable on SOL/BNB/ADA-class notionals; a trade below min notional is rejected with a reason, never clamped up.
4. Backtest re-confirmation through the repaired (post-WS1) engine.
5. One paper trade observed end-to-end: `signals` row → `orders` row → notification received. Service restarted after any config change.

## 5. Testing and verification

- **Test-first per defect:** failing test reproducing the defect → minimal fix → green. One defect per commit, `fix(service): …` messages, commits use pathspecs (shared-index discipline).
- **Suites:** trading-engine and TA host runs from their service directories with `--no-cov` (cwd-sensitive). Baselines verified 2026-08-17: trading-engine collects 2642 tests with **zero** collection errors (the old "13 collection errors" story is stale — `conftest.py` pinning `env_file=None` fixed it) and runs **13 known failures** (11 × `test_pairs_trading` pandas `'H'` alias, 2 × `TestLiveTradingResponseEnvelope` connector-contract stale mocks); technical-analysis collects 481 and runs **3 known failures** (2 × `test_comprehensive_80`, 1 × `test_signal_aggregator_confidence_zero` — which this work fixes, taking the baseline to 2). Known failures are not chased but must not grow; the count is asserted before and after every task. One known timing flake to ignore: `tests/unit/test_signal_cache.py::TestSignalCache::test_cache_entries_isolated`.
- **The two `TestLiveTradingResponseEnvelope` failures were verified red before any of this work began** — they stub the retired `risk_manager.can_open_position` API. State this next to the LIVE-fence task or the fence will be blamed for them.
- **New invariant guards:** price-domain-round AST test (§3A), screen slippage drift test (§3D).
- **Deployment proof per repo standard:** rebuild + restart every touched service (stale in-memory state is the canonical false pass), `/verify-stack`, DB `SELECT` evidence — never an HTTP 200 alone.
- **WS2 evidence:** every battery commits verdict docs + JSON + ledger append. No verbal verdicts.

## 6. Sequencing

**Amended 2026-08-17.** The original "aggregator last" rule assumed the aggregator work was uniformly behavior-changing. Recon shows it splits across live and dormant code (the empty-vote defect and the TA legs are live; MTF and VP are dormant behind two default-False flags), so bucket order no longer tracks risk. **Sequence by liveness, and label every task LIVE or DORMANT.**

Work is cut into three plans on the **test-suite boundary**, so each plan has exactly one suite, one known-failure baseline, and one reviewer gate:

| Plan | Suite / cwd | Baseline | Contents |
|---|---|---|---|
| A — technical-analysis | `cd services/technical-analysis` | 3 known failures → 2 after the empty-vote fix | empty-vote neutral fallback (LIVE), squeeze_momentum precision (LIVE), `sqzmom_enhanced.to_dict` precision, Query defaults from Settings (LIVE), ADX + SQZMOM legs and the Volume multiplier (LIVE), AST guard created over A's files |
| B — trading-engine | `cd services/trading-engine` | 13 known failures | exposure remaining-quantity, sizing clamp units, daily-limit + `_record_trade`, heat-gate move, slippage stats, performance-tracker net P&L, funding accrual, SQZMOM re-enable, ADX category, MTF pair-fix (DORMANT), VP delete (DORMANT), `portfolio_manager_url`, LIVE fence, dormant-strategy rounding, AST guard extended to B's files |
| C — research layer + WS2 | repo root | repo-root suite | `screen.py` table hoist + drift guard, `run_phase1` capital + bespoke AST test, trial ledger + verdicts threading, battery #1 manifest and candidates |

Ordering: A → B → C. The two research-layer fixes live in C rather than B because they are prerequisites for *trusting* battery verdicts, not for engine correctness. WS2 battery #1 runs only after A and B are merged and deployed — verdicts must come from the honest engine. Checkpoint after every battery; operator directs battery N+1 or stops.

## 7. Error handling

- Engine fixes follow the fail-loud doctrine: incoherent state refuses boot rather than trading wrong.
- Battery runner: import failures and empty fetches are ERROR, never silently filed as REJECT (bug class caught in the 2026-08-17 build review; keep the guard).
- Any WS1 fix that surfaces a deeper defect than catalogued: stop, report, do not widen scope silently.

## 8. Risks

| Risk | Mitigation |
|---|---|
| **Funding accrual is the highest-risk task.** A charge applied only to `self.balance` passes a naive test and never reaches reported P&L or the daily-loss breaker | It must flow through **both** ledgers: the balance line at `paper_trading.py:377` **and** `close_commission` into `close_position` **and** `reduce_position` — exactly how `close_commission` itself is dual-booked today. This is the documented "wired but never bites" trap at `paper_trading.py:256-266` |
| **The obvious position-sizing fix is 100× wrong.** Multiplying auto_trader's fraction stop by 100 while leaving the `:216` formula alone cuts a 10% position to 5% — $5, exactly the venue floor — and rejects anything with a wider stop | Adopt the fraction contract in `position_sizing.py`; `kelly_position_sizing.py:366` is the checked reference (`max_risk_pct / stop_pct * 100`). Quote the DO-NOT verbatim in the task |
| `auto_trader.py` is very large; three C-bucket fixes live in it | Surgical per-defect edits, no piggybacked refactors, test per fix |
| Aggregator changes alter live TA signals | The live changes are narrow and each is pinned by a test asserting the specific defect two-sidedly; the dormant ones (MTF, VP) cannot change runtime behavior at all |
| The exposure fix **breaks two currently-passing tests** (`tests/unit/test_risk_manager.py:254,269` use bare `Mock()`, so `getattr` returns a child Mock and `Decimal * Mock` raises `TypeError`) | Updating those two tests is a step inside that task, never a follow-up |
| Batteries may all REJECT indefinitely | Ledger-driven DSR keeps it honest (within the limits stated in §4.2); per-battery checkpoint gives the operator a stop lever; REJECT documented as deliverable |
| Fee/funding model drift across the three cost layers | Drift-guard test (§3D) pins them together |
| The ruff format hook runs at 88 cols vs the repo's 100 and has stripped imports before | Surgical single-line edits; grep the diff for import churn after every edit that touches an import block |
