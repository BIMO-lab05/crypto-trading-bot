# Profit-path audit — 2026-08-12

**Question asked:** operator — "check the important services that maybe have that
problem [preventing profitability] and fix it."

**Answer:** the thing preventing profitability is not a service bug — the deployed
ensemble is chance-level (H4 re-score 2026-08-09: 49.7% accuracy, DSR 0.0, REJECT;
gross edge ~4.9 bp/trade vs ~25 bp round-trip cost). That verdict is unchanged.
The audit instead answered: *which remaining defects lose money mechanically, block
trading, or corrupt measurement — for any strategy?* Sixteen were confirmed and
fixed the same day; twenty-nine minors were catalogued and deferred (below).

## Method

Workflow `wf_e13e1ff9-11a`: 6 parallel finder agents (sizing/risk, paper accounting,
TA precision, reporting mirror, config/boot, cost consistency), findings passed to
adversarial verifier agents prompted to REFUTE. 11 findings verified CONFIRMED by
agents; 5 verifier agents died to a session limit and their findings were confirmed
by direct code reading in the main session. **0 refuted.** Design + approval:
`docs/superpowers/specs/2026-08-12-profit-path-defect-repair-design.md`.
Implementation: workflow `wf_f49cd8c4-ec9`, 12 surgical agents, test-first
(failing-first proof recorded per fix), no git access; commits by controller.

## Confirmed and fixed (commits `63595b0`..`2a48846`)

| # | Commit | Finding |
|---|---|---|
| 1 | `63595b0` | Boot position hydration swallowed all failures at 3 layers → engine traded on an empty book |
| 2 | `943b29b` | Partial-exit/scale-in cash flows never persisted → dropped on restart |
| 3 | `1a674aa` | TA served MACD rounded to 2dp → ADA crossovers collapsed |
| 4 | `8722ea7` | Partial-exit ladder `round(price,2)` → ADA TP2/TP3 merged onto one rung |
| 5 | `7c9cd5d` | `grid_trading` dispatched to a non-existent method — AttributeError/cycle, swallowed |
| 6 | `b0b9601`+`bb646b7` | SHORT stop declared, never read → now enforced; dead SHORT sizing/breaker fields deleted |
| 7 | `7c9cd5d` | Ensemble attribution wrote a non-existent pydantic field → ADR-015 learning loop inert since shipped |
| 8 | `bb646b7` | `TRADING_SYMBOLS`/`SYMBOL_ALLOCATIONS` never reached the container (compose whitelist) |
| 9 | `2a48846` | 6 portfolio-manager read endpoints clobbered engine-mirrored equity with the spot formula |
| 10 | `e595732` | Realized-P&L truncated at 1000 rows; DB errors → `success=True` zeros (mirror source) |
| 11 | `2a48846` | Manual buy/sell/rebalance wrote a ledger the mirror erases in 60s → 409-gated |
| 12 | `561ba73` | In-service backtester: long P&L double-counted, short P&L erased |
| 13 | `561ba73` | Open-short equity sign-flipped (`unrealized_pnl` computed, discarded) |
| 14 | `6612595` | Realistic-sim paid a maker REBATE on stops; stops now taker, fees from costs_loader |
| 15 | `5067751` | IS folds ran legacy costs vs OOS realistic → drift gate measured fee delta |
| 16 | `561ba73` | HTTP/in-service backtest fees 0.1%/side (1.8× paper engine) → derived from Settings |

Verification: trading-engine full suite 13 failed / 1830 passed — the 13 are the
two pre-existing families (11 × `test_pairs_trading` pandas-`'H'` alias, 2 ×
connector-contract stale mocks), identical to the pre-work baseline. portfolio-manager
113 passed. TA 3 failed / 472 passed — all three pre-existing (2 ×
`test_comprehensive_80` DataFrame, 1 × `test_signal_aggregator_confidence_zero`,
proven by stash-revert). Killtest regression: `test_screen_reproduces_h3` 12/12 —
committed H3 figures still reproduce exactly. `golden-parity-stamp.json` was
transiently clobbered by an agent's harness run (parity tests need live services)
and restored from git — the committed 2026-08-06 stamp stands.

## Operator-facing behavior changes

- Engine **refuses to boot** if the open-position book cannot be read (was: booted
  on an empty book). A DB outage at boot now crash-loops the container — deliberate.
- Engine refuses to boot with `STRATEGY_MODE=grid_trading` (was: silently traded nothing).
- Frontend Buy/Sell/rebalance-execute now surface **409** (was: fake fills erased by sync).
- `.env` `TRADING_SYMBOLS`/`SYMBOL_ALLOCATIONS` are now LIVE in the container —
  incoherent values fail boot loudly (validator message says exactly what to fix).
- Ensemble weights now actually adapt from trade outcomes (ADR-015 activated).
- Backtest/walk-forward numbers move: costs went up (stops pay taker), ledger math
  corrected. Historical in-service backtest figures are non-reproducible — they were wrong.

## Deferred minors (29) — catalogued, NOT fixed

Several belong to already-planned phases (22 rounding, 24 hygiene). Notables for
triage: #7 (PositionSizer clamp never fires — mitigated by the auto-trader path's
own caps), #18 (ADA ATR→0 ZeroDivisionError), #29 ($10k in active research runners).

| Site | Finding |
|---|---|
| `services/trading-engine/app/risk_manager.py:230` | Exposure check and exposure reporting use original quantity, not remaining quantity |
| `services/trading-engine/app/paper_trading.py:601` | Performance summary presents per-process figures as account totals; resets on every restart |
| `services/trading-engine/app/position_manager.py:414` | update_position_price persistence task lacks the error-surfacing done-callback used everywhere else |
| `services/trading-engine/app/paper_trading.py:266` | Paper engine applies fees and slippage but never funding — held positions accrue zero funding cost |
| `services/trading-engine/app/live_trading.py:229` | LIVE shared path: fills recorded at reference price with zero fees/margin, and live closes overwrite the paper cash ledger |
| `services/trading-engine/app/config.py:441` | Time-based trading filters are dead config — never read by any code |
| `services/trading-engine/app/position_sizing.py:216` | Fraction-vs-percent confusion: PositionSizer max-risk clamp silently never fires on the auto-trader path |
| `services/trading-engine/app/auto_trader.py:3849` | Standard-mode entry path bypasses the daily trade limit and same-symbol cooldown recording |
| `services/trading-engine/app/auto_trader.py:1824` | Research/hybrid portfolio-heat gate fed a size and stop the actual order does not use |
| `services/trading-engine/app/performance_tracker.py:186` | PerformanceTracker P&L gross of fees/slippage, full original quantity — distorts stats feeding Kelly sizing |
| `services/trading-engine/app/auto_trader.py:2249` | Slippage manager fed expected==actual on every entry — adaptive rejection stats measure constant zero |
| `services/portfolio-manager/app/handlers/performance.py:85` | PM /performance and nightly snapshots permanently record 0 trades / 0.0% win rate |
| `services/portfolio-manager/app/handlers/optimization.py:352` | Rebalancing dead on the $100 account: min_trade_size hardcoded to $100 |
| `services/portfolio-manager/app/handlers/transactions.py:204` | Break-even SELL reports realized_pnl=null (falsy Decimal check) |
| `services/portfolio-manager/app/services/performance_history.py:137` | MANUAL snapshot upserts over the day's DAILY row, deleting that day from the series |
| `services/portfolio-manager/app/main.py:111` | Prometheus portfolio money gauges declared but never set |
| `services/trading-engine/app/utils/support_resistance_detector.py:630` | S/R level + zone prices rounded to 2dp (6 sites) — Phase 22 |
| `services/trading-engine/app/strategies/support_resistance_strategy.py:380` | SR strategy rounds ATR to 2dp — ADA ATR becomes 0.0 → ZeroDivisionError + degenerate stops |
| `services/trading-engine/app/signal_aggregator.py:1288` | VP pipeline doubly dead: non-existent TA route + Decimal without import |
| `services/trading-engine/app/aggregation/enhanced_aggregator.py:317` | Phase-3 MTF leg structurally always zero: 0-1 score vs 50.0 threshold + non-existent key |
| `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py:203` | SQZMOM endpoint rounds entry/stop/TP to 2dp — Phase 22 |
| `services/technical-analysis/app/indicators/sqzmom_enhanced.py:118` | Enhanced SQZMOM serializes bands/price at 4dp — lossy below ~$0.01, consumer disabled |
| `docker-compose.unified.yml:676` | EMERGENCY_STOP_LOSS=0.05 dead config — consumed by zero lines |
| `docker-compose.unified.yml:337` | TRADING_MODE passed to api-gateway but not trading-engine — displays can disagree |
| `services/trading-engine/app/config.py:36` | portfolio_manager_url default points at 8006 (notification-service), not 8003 |
| `services/trading-engine/app/backtesting/backtest_engine.py:422` | In-service backtester fills stop/TP exits at bar.close, not the stop price |
| `backtesting/backtest_engine.py:220` | Funding modelled inconsistently across layers; correct only in unused costs.funding_cost |
| `backtesting/screen.py:318` | Third hand-copied slippage table — agrees with paper engine today, drift unguarded |
| `backtesting/run_phase1_backtest.py:494` | Active research runners still default to $10,000 capital |

## What this does NOT change

No fix here creates edge. The path to a profitable system remains a structurally
different strategy clearing the hurdle-first screen (2× cost, `backtesting/screen.py`)
— cross-sectional momentum is the pre-registered candidate. These repairs make the
engine honest and the screen verdict trustworthy for that test.
