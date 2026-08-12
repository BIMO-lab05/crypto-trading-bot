# Profit-Path Defect Repair — Design

**Date:** 2026-08-12
**Status:** Approved (operator selected "all 3 waves" scope)
**Origin:** Full-service audit (6 parallel finders + adversarial verification, workflow `wf_e13e1ff9-11a`), triggered by the operator question "check the important services that maybe have that problem [preventing profitability] and fix it."

## Framing — what this is and is not

The edge question is **answered and not reopened here**: the deployed ensemble is
chance-level (H4 re-score 2026-08-09: 49.7% directional accuracy, DSR 0.0, REJECT),
and its gross edge (~4.9 bp/trade) is a fifth of its round-trip cost (~25 bp).
**No fix in this document creates edge.** The audit asked a different question:
*which remaining defects lose money mechanically, block trading, or corrupt
measurement — for any strategy, including the next candidate?* Sixteen findings
were confirmed (11 by adversarial verifier agents, 5 by direct code verification
after the verifier pool hit its session limit; 0 refuted). ~25 minors were
catalogued and deferred.

## Wave 1 — stop the bleed (live money path)

| # | Site | Defect | Fix |
|---|---|---|---|
| 1 | `services/trading-engine/app/position_manager.py:1115`, `app/repositories.py:397`, `app/lifespan/data.py:55` | Boot-time position hydration swallows every exception and returns 0; repositories layer swallows again and returns `[]`. Engine trades believing it has zero open positions: none monitored, none stopped, cash reconstructed against an empty book. | Fail loud. `load_positions_from_db` re-raises; the repository path it uses re-raises (keep the lenient behavior for the dashboard caller via a separate strict path); lifespan lets the failure abort boot. A book we cannot verify is a book we do not trade. |
| 2 | `services/trading-engine/app/paper_trading.py:179` | Restart cash reconstruction classifies positions by `opened_at > portfolios.updated_at`, but partial exits and scale-ins never write the portfolio ledger — their cash flows are silently dropped on restart. | Persist a cash snapshot (`portfolio_repo.update_balance`) after the reduce and scale-in branches, matching the existing close-path write. |
| 3 | `services/technical-analysis/app/services/indicator_service.py:84-86` | MACD line/signal/histogram rounded to 2 dp in the API layer. ADA MACD values are ~1e-4 scale — crossover detection downstream collapses. Same defect family as the 30-loss ADA flip-flop bug (487d1bd). | `round(x, 2)` → `float(x)`, mirroring the Bollinger handler in the same file. PRICE-01/02 site. |
| 4 | `services/trading-engine/app/strategies/research_optimized_strategy.py:722` | Partial-exit ladder built with `price=round(price, 2)` on the live hybrid path — ADA TP1 collapses onto entry or shifts >1% of price. | Drop the round. The level is a trigger compared against market price; no exchange precision needed at this layer. PRICE-01/02 site. |
| 5 | `services/trading-engine/app/auto_trader.py:963` | `STRATEGY_MODE=grid_trading` dispatches to `_check_and_trade_grid`, which does not exist. AttributeError per symbol per cycle, swallowed by the per-symbol except, feeding the circuit breaker. | Boot refusal in `AutoTrader.__init__` with an explicit error naming the supported modes; delete the dead dispatch branch. Keep `grid_trading` out of silent-fallback paths. |
| 6 | `services/trading-engine/app/config.py:494`, `app/risk_manager.py:167` | Every SHORT-specific risk control (`short_stop_loss_pct`, `short_max_position_pct`, SHORT circuit-breaker fields) is declared and enforced nowhere. | **Decision (approved default):** enforce the stop — side-aware fallback in `risk_manager` (`short_stop_loss_pct` when side is SHORT). Do **not** enforce `short_max_position_pct` (3% of $100 = $3 < $5 venue minimum ⇒ under reject-don't-clamp it would silently end all SHORT trading); delete it and the never-read SHORT breaker fields rather than leave dead config. |
| 7 | `services/trading-engine/app/auto_trader.py:4925` | Ensemble attribution write assigns a non-existent `Position.metadata` field → ValueError swallowed at debug level; `record_trade_outcome` has no caller. The ADR-015 learning loop has been inert since it shipped — weights never adapt. | Trader-side attribution store: `self._ensemble_attribution[position_id] = leg_contributions` at fill; feed `record_trade_outcome` from `_finalize_closed_position`. This deliberately activates weight adaptation (ADR-015 intent). |
| 8 | `docker-compose.unified.yml:653` (trading-engine env block) | Compose whitelists ~30 env vars; `TRADING_SYMBOLS` and `SYMBOL_ALLOCATIONS` are absent and no `env_file` exists for this service (Dockerfile copies only `app/`). Operator symbol/risk edits in `.env` are silently ignored; the engine trades hardcoded defaults. Same silent-dead-config class as the pre-ADR-028 daily-loss breaker. | Pass both through in compose **guarded against the empty-string trap** (an unset var must fall back to the pydantic default, not inject `""` into a JSON list/dict field). Verify the operator `.env` values are coherent with the validator (OP-16) before enabling; fix `.env` locally if not (never committed). |

## Wave 2 — fix the measurement instrument (backtest/screen layers)

| # | Site | Defect | Fix |
|---|---|---|---|
| 12 | `services/trading-engine/app/backtesting/backtest_engine.py:465` | Close credits `exit_notional + net_pnl` after open debited `entry_notional`: long P&L double-counted, short P&L dropped entirely. Every metric derived from the equity curve is wrong. | `self._cash += entry_value + net_pnl` — round-trip delta becomes exactly `pnl − fees` for both sides. |
| 13 | same file `:541` | `_calculate_equity` computes `unrealized_pnl` then discards it, adding `quantity * current_price` — sign-flipped for shorts (price rises ⇒ reported equity rises). | `equity += entry_value + unrealized_pnl`, side-aware. |
| 14 | `backtesting/backtest_engine.py:474` (+ `:140`) | Realistic-sim (`bybit_perp`) classifies stop-loss/take-profit exits as LIMIT and bills them at `bybit_maker_fee = -0.0001` — a rebate. Every stop-out *credits* ~1 bp instead of charging 5.5 bp taker. Bybit stop orders execute as taker; $100 accounts get no rebates. | Stops/TPs are taker. Align the maker rate with `app/costs.py` (maker = +2 bp charge) via the existing `costs_loader` so the research engine stops hand-copying fee constants. |
| 15 | `backtesting/run_walk_forward.py:410` (+ `run_walk_forward_ensemble.py:598,604`) | IS engines are built bare (legacy costs) while OOS engines get `**_engine_kwargs()` (realistic costs). The IS/OOS ratio — the ADR-013 regime-drift gate — measures the fee-model delta, not drift. | Build IS engines with the same `**_engine_kwargs()`. |
| 16 | `services/trading-engine/app/handlers/backtest.py:53,380,548`, `app/backtesting/backtest_engine.py:144` | Five fee/slippage implementations across layers; the HTTP backtest API and in-service defaults cost trades at 0.1%/side — 1.8× the paper engine's 0.055% taker. Screen verdicts and engine P&L cannot reconcile. | Defaults derive from `Settings` (the paper engine's own fee source) instead of literals. One source of truth; the unit is percent at these sites — convert explicitly and test the value, not the shape. |

## Wave 3 — honest reporting

| # | Site | Defect | Fix |
|---|---|---|---|
| 9 | `services/portfolio-manager/app/handlers/portfolio.py:129,172`, `handlers/performance.py:82,190`, `handlers/allocation.py:53,94` | Six endpoints call `update_prices` unconditionally, clobbering engine-mirrored equity with a spot formula (`cash + full notional`). | Replicate the committed sync-first pattern from `get_portfolio`: try `sync_with_trading_engine`, fall back to `update_prices` only on sync failure. |
| 10 | `services/trading-engine/app/handlers/performance.py:46`, `app/repositories.py:420` | Realized P&L summed over the most recent **1000** closed positions only; DB errors are swallowed into `success=True` with zeroed figures. This endpoint is the upstream source for the portfolio-manager mirror. | SQL aggregate (no limit) in the repository — count/wins/losses/sum in one query; DB failure raises (HTTP 500), never fake zeros. |
| 11 | `services/portfolio-manager/app/handlers/transactions.py:94,183`, `handlers/optimization.py` execute branch | Manual buy/sell/rebalance write a local spot ledger that the engine mirror erases within 60 s — fake fills, guaranteed drift. | **Decision (approved default):** 409-gate the mutating paths with an explicit reason. Breaks the frontend Buy/Sell buttons — which currently fabricate fills the mirror deletes anyway. |

## Testing

Test-first per fix: pin the wrong behavior's correction with a failing test, fix,
run the touched service's targeted suite. Environment constraints (from
`.claude/rules/testing.md` + session memory): trading-engine host runs from
`services/trading-engine` with `--no-cov` and **no** exported env prefix;
api-gateway suites only in-container; TA and portfolio-manager host-run.
Full-suite runs per wave before commit; the known pre-existing failure families
(`test_pairs_trading`, connector contract) are recorded and must not grow.

## Out of scope

- Anything that claims to add edge. Next-candidate work (cross-sectional
  momentum through the hurdle-first screen) is a separate effort.
- The ~25 catalogued minors (dead time-filter config, Prometheus gauges never
  set, PerformanceTracker gross-of-fees stats, $10k defaults in inactive research
  runners, SR-detector 2 dp sites, MTF/VP dead legs). Filed in the audit evidence
  doc for later triage — several belong to already-planned phases (22, 24).
- LIVE-path changes beyond what shared code requires. LIVE remains mechanically
  impossible at $100 (2% cap = $2 < $5 venue minimum).
