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

- Add one tick-size-aware formatting helper per service:
  - trading-engine: sources tick size from `InstrumentsCache` (healthy 5/5 since 2026-08-16).
  - technical-analysis: static tick map with conservative fallback — indicator code makes no network/DB calls per the indicator contract.
- Remove every price-domain 2dp rounding in:
  - `services/trading-engine/app/strategies/momentum_breakout_strategy.py`
  - `services/trading-engine/app/strategies/trend_following_strategy.py`
  - `services/trading-engine/app/strategies/support_resistance_strategy.py` (SL/TP + indicator returns)
  - `services/trading-engine/app/utils/support_resistance_detector.py`
  - `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` (entry/stop/TP)
  - Exact site enumeration happens at planning time via the audit grep; the AST guard below defines "done", not a fixed count.
- Fix `support_resistance_strategy.py:380` — ATR rounded to 2dp; ADA ATR becomes 0.0 → ZeroDivisionError and degenerate stops. ATR is price-domain.
- **Guard:** an AST-based invariant test banning price-domain `round(x, 2)` in strategy/indicator/detector code, modeled on the `$100` account-invariant AST test (`260803-4mt`).

### 3B. Aggregator truth — legs that vote zero or never vote

- **TA-AGG-01:** wire ADX, SQZMOM, and Volume indicators into the aggregator vote. They are computed today and never consulted.
- `services/trading-engine/app/aggregation/enhanced_aggregator.py:317` — Phase-3 MTF leg is structurally always zero (0–1 score compared against a 50.0 threshold, plus a non-existent key). Fix scale and key.
- `services/trading-engine/app/signal_aggregator.py:1288` — VP pipeline doubly dead (calls a non-existent TA route; uses `Decimal` without import). Repair or remove; no half-dead code path stays.
- **TA-AGG-02/03:** MACD 5/35/5 and BB std-dev 2.5 move from hardcoded `Query(default=…)` literals in TA `main.py` to `settings.macd_*` / `settings.bollinger_std_dev` (values already correct; single-sourcing owed).

Ships **last** within WS1 (see §6 sequencing) because it changes live signal behavior; lands with a before/after replay comparison so the behavior change is measured, not assumed.

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
- Gate 2 computes DSR with the trial count read from the ledger, not from the current battery. The pass bar rises monotonically across batteries.
- A ledger entry is written even for candidates that die at Gate 1 — they were still trials.

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
- **Suites:** trading-engine and TA host runs from their service directories with `--no-cov` (cwd-sensitive). Known pre-existing failures (trading-engine 13: pairs_trading pandas 'H' + connector contract; TA 3) are not chased but must not grow — failure count asserted before/after.
- **New invariant guards:** price-domain-round AST test (§3A), screen slippage drift test (§3D).
- **Deployment proof per repo standard:** rebuild + restart every touched service (stale in-memory state is the canonical false pass), `/verify-stack`, DB `SELECT` evidence — never an HTTP 200 alone.
- **WS2 evidence:** every battery commits verdict docs + JSON + ledger append. No verbal verdicts.

## 6. Sequencing

1. WS1-A precision → WS1-C risk rails → WS1-D measurement (independent, mechanical, no behavior redesign).
2. WS1-B aggregator last within WS1 — behavior-changing; ships with before/after replay comparison.
3. WS2 battery #1 only after WS1 complete and deployed (verdicts must come from the honest engine).
4. Checkpoint after every battery; operator directs battery N+1 or stops.

## 7. Error handling

- Engine fixes follow the fail-loud doctrine: incoherent state refuses boot rather than trading wrong.
- Battery runner: import failures and empty fetches are ERROR, never silently filed as REJECT (bug class caught in the 2026-08-17 build review; keep the guard).
- Any WS1 fix that surfaces a deeper defect than catalogued: stop, report, do not widen scope silently.

## 8. Risks

| Risk | Mitigation |
|---|---|
| `auto_trader.py` is very large; three C-bucket fixes live in it | Surgical per-defect edits, no piggybacked refactors, test per fix |
| Aggregator re-weighting changes live paper signals | Before/after replay comparison committed with the change; lands last |
| Batteries may all REJECT indefinitely | Ledger-driven DSR keeps it honest; per-battery checkpoint gives the operator a stop lever; REJECT documented as deliverable |
| Tick-size source unavailable at runtime (cache miss) | Conservative fallback (max known precision for the symbol class), fail-loud on unknown symbols |
| Fee/funding model drift across the three cost layers | Drift-guard test (§3D) pins them together |
