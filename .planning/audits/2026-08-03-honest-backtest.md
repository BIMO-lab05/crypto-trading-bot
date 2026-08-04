# Honest backtest — 2x2 (account size × cost model)

**Date:** 2026-08-03
**Engine:** `backtesting/backtest_engine.py` (`BacktestEngine`), constructed directly.
**Data:** cached direct-from-Bybit hourly CSVs, `backtesting/data/{SOL,ADA,BNB}USDT_60m_180d_bybit.csv` —
4,400 bars each, `2025-06-06 16:00` → `2025-12-06 23:00`. No docker, no `market-data-service`,
no TimescaleDB. Not exposed to the 2026-04-25 testnet-pollution window.
**Harness:** `/tmp/claude-1000/-mnt-d-Bimo-max-crypto-trading-bot/98160ef5-5410-439f-aeeb-1df106ea6f59/scratchpad/honest_backtest.py`
(scratchpad only — no repo code was modified; `BacktestEngine` was **subclassed** to account costs).

Nothing was tuned. No parameter was changed to improve any number.

---

## TL;DR — three findings, two of them uncomfortable

1. **The $100 correction changes nothing.** Cells A and C are numerically identical to ~12
   significant figures (max relative difference `1.1e-12`, pure float noise). The engine has no
   capital-scale-dependent mechanic — no minimum notional, no lot size, no rounding floor — so
   every metric is exactly scale-invariant. **100% of the A→D difference is the cost model; 0% is
   the account size.** (A→D is not a degradation — see bullet 3.)
2. **…and that identity is itself the bug.** At the engine default `position_size_pct = 0.02`, a
   $100 account places a **$1.99 median notional**. `shared.account.MIN_NOTIONAL_USD = 5.0`.
   **0 of 3,404 entries in cells C and D clear the venue minimum.** In reality every one of those
   trades would have been rejected. Cell D is therefore not "the honest number" — it is the number
   for an account that is allowed to trade below the exchange floor. The only $100 configuration
   that *can* execute is the ADR-010 10% cap, run as **cell D′** below: **−5.1% / −11.0%** over
   180 days.
3. **"Realistic" costs come out ~28% CHEAPER than "legacy" costs — because the realistic model is
   incompletely wired, not because trading is cheap.** Legacy charges 0.1%/side vs Bybit's actual
   0.055%/side taker, so the fee leg genuinely falls. But `slippage_mode="atr_aware"` is a **no-op**
   (no strategy emits the top-level `atr` key the engine looks for), funding is charged on **longs
   only**, and stop-loss exits are credited a **maker rebate** a real stop-market order would never
   get. Close those three gaps and realistic becomes *more* expensive than legacy. Do not quote
   this bullet without them — see "Why B beats A".

---

## The 2x2

Mean across the 3 symbols, per strategy. `ret%` is capital-based total return over the 180-day
window; `gross%` is that return **before** all costs; `cost%` is total cost (fees + slippage +
funding − rebates) as a fraction of starting capital.

### `multi_indicator` — 1,363 trades (primary, high turnover)

| | legacy costs | realistic costs |
|---|---|---|
| **$10,000** | **A** — ret **−3.037%**, gross −0.356%, cost **2.680%**, WR 44.3%, DD 3.15%, Sharpe −9.25 | **B** — ret **−2.286%**, gross −0.357%, cost **1.929%**, WR 45.6%, DD 2.45%, Sharpe −9.02 |
| **$100** | **C** — ret **−3.037%**, gross −0.356%, cost **2.680%**, WR 44.3%, DD 3.15%, Sharpe −9.25 | **D** — ret **−2.286%**, gross −0.357%, cost **1.929%**, WR 45.6%, DD 2.45%, Sharpe −9.02 |

### `bb_mean_reversion` — 326 trades (primary, moderate turnover)

| | legacy costs | realistic costs |
|---|---|---|
| **$10,000** | **A** — ret **−1.207%**, gross −0.558%, cost **0.649%**, WR 56.1%, DD 1.33%, Sharpe −10.59 | **B** — ret **−1.033%**, gross −0.559%, cost **0.475%**, WR 57.3%, DD 1.21%, Sharpe −10.52 |
| **$100** | **C** — ret **−1.207%**, gross −0.558%, cost **0.649%**, WR 56.1%, DD 1.33%, Sharpe −10.59 | **D** — ret **−1.033%**, gross −0.559%, cost **0.475%**, WR 57.3%, DD 1.21%, Sharpe −10.52 |

### `baseline_rsi_ema` — 13 trades (reported, **not informative**)

| | legacy costs | realistic costs |
|---|---|---|
| **$10,000** | **A** — ret +0.105%, gross +0.128%, cost 0.022%, WR 64.8%, DD 0.14%, Sharpe −43.6 | **B** — ret +0.116%, gross +0.128%, cost 0.012%, WR 64.8%, DD 0.13%, Sharpe −43.4 |
| **$100** | **C** — identical to A | **D** — identical to B |

### `phase1_filtered` — **0 trades on all 3 symbols, all 4 cells**

Not a run failure. `phase1_strategy` requires RSI(9) < 20 / > 80 **and** the GATEKEEPER trend
filter **and** VALIDATOR volume confirmation. `baseline_strategy` — the same RSI/EMA trigger with
the filters removed — fires only 13 times in 13,200 bars, and the Phase-1 filters reject all 13.
A strategy that never trades is reported here as zero, not dropped.

---

## Per-symbol detail (active strategies)

| cell | strategy | symbol | trades | ret% | gross% | cost% | fees$ | slip$ | fund$ | WR% | DD% | Sharpe (engine) | Sharpe (hourly-annualised) | PF |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| A | bb_mean_reversion | SOL | 109 | −1.4388 | −0.7888 | 0.6499 | 43.33 | 21.66 | 0.00 | 55.05 | 1.464 | −10.31 | −4.85 | 0.597 |
| A | bb_mean_reversion | ADA | 103 | −1.2485 | −0.6344 | 0.6141 | 40.94 | 20.47 | 0.00 | 54.37 | 1.453 | −8.74 | −3.81 | 0.650 |
| A | bb_mean_reversion | BNB | 114 | −0.9327 | −0.2507 | 0.6820 | 45.47 | 22.73 | 0.00 | 58.77 | 1.077 | −12.73 | −4.83 | 0.647 |
| A | multi_indicator | SOL | 436 | −2.7084 | −0.1385 | 2.5699 | 171.33 | 85.66 | 0.00 | 47.71 | 2.934 | −8.41 | −5.74 | 0.762 |
| A | multi_indicator | ADA | 452 | −3.1701 | −0.5064 | 2.6636 | 177.57 | 88.79 | 0.00 | 45.80 | 3.262 | −7.78 | −5.88 | 0.731 |
| A | multi_indicator | BNB | 475 | −3.2311 | −0.4239 | 2.8072 | 187.14 | 93.57 | 0.00 | 39.37 | 3.267 | −11.57 | −8.86 | 0.624 |
| B | bb_mean_reversion | SOL | 109 | −1.2707 | −0.7898 | 0.4809 | 23.85 | 21.68 | 2.56 | 55.96 | 1.300 | −10.24 | −4.51 | 0.623 |
| B | bb_mean_reversion | ADA | 103 | −1.0855 | −0.6349 | 0.4505 | 22.53 | 20.49 | 2.03 | 55.34 | 1.349 | −8.67 | −3.53 | 0.677 |
| B | bb_mean_reversion | BNB | 114 | −0.7433 | −0.2512 | 0.4920 | 25.03 | 22.75 | 1.42 | 60.53 | 0.992 | −12.63 | −4.36 | 0.692 |
| B | multi_indicator | SOL | 436 | −1.9863 | −0.1361 | 1.8502 | 94.58 | 85.98 | 4.46 | 48.62 | 2.279 | −8.20 | −4.62 | 0.807 |
| B | multi_indicator | ADA | 452 | −2.4279 | −0.5071 | 1.9208 | 98.04 | 89.12 | 4.92 | 46.46 | 2.559 | −7.58 | −4.83 | 0.773 |
| B | multi_indicator | BNB | 475 | −2.4428 | −0.4263 | 2.0166 | 103.35 | 93.95 | 4.36 | 41.68 | 2.512 | −11.28 | −7.22 | 0.680 |

Cells C and D reproduce A and B respectively, with all dollar figures scaled by exactly 1/100
(e.g. C/multi_indicator/SOL: fees $1.7133, slippage $0.8566) and every ratio metric bit-for-bit
equal within float noise.

Median entry notional: **~$197 in A/B**, **~$1.97 in C/D**.

All 48 rows (4 cells × 4 strategies × 3 symbols, including the C/D dollar figures and the
zero-trade `phase1_filtered` rows) are in `results.json` alongside the harness in the scratchpad
path given at the top.

---

## Total cost paid — the point of the exercise

Cost as a fraction of starting capital. **Percentages are pooled across the 3 symbols**
(`total USD cost / (capital × 3)`), which equals the mean of the per-symbol fractions because each
run starts from the same capital. **The `trades` column is a sum, not a mean.** Verified against
`results.json`.

| strategy | trades (sum) | cost model | fees | slippage | funding | rebates | **total cost, % of capital** | gross return % | net return % |
|---|---:|---|---:|---:|---:|---:|---:|---:|---:|
| multi_indicator | 1,363 | legacy | 1.7868% | 0.8934% | 0.0000% | 0 | **2.680%** | −0.356% | **−3.037%** |
| multi_indicator | 1,363 | realistic | 0.9865% | 0.8969% | 0.0458% | 0 | **1.929%** | −0.357% | **−2.286%** |
| bb_mean_reversion | 326 | legacy | 0.4324% | 0.2162% | 0.0000% | 0 | **0.649%** | −0.558% | **−1.207%** |
| bb_mean_reversion | 326 | realistic | 0.2381% | 0.2164% | 0.0200% | 0 | **0.475%** | −0.559% | **−1.033%** |

Implied round-trip cost per trade:

- legacy: **0.300% of notional** ($0.590 on a $196 position)
- realistic: **0.216% of notional** ($0.425 on a $197 position)

**Cost vs. edge, stated as a ratio rather than asserted:**

- `multi_indicator`: gross return is **−0.36%** over 180 days. Costs are **1.93–2.68%**.
  Costs are **5.4x to 7.5x the magnitude of the gross P&L** — and the gross P&L is already
  negative. There is no edge for costs to eat. Costs turn a nothing into a clear loss.
- `bb_mean_reversion`: gross **−0.56%**, costs **0.48–0.65%**. Same conclusion at lower turnover.

Both strategies win >44% (mean reversion wins **56–57%**) and still lose. Profit factor
0.62–0.81. That is the signature of a coin-flip signal paying a spread on every flip.

---

## Answers to the specific questions

### How much degradation is the cost model (A→B) vs the account size (A→C)?

- **A→C (account size): exactly 0.000%.** Not "small" — zero. Verified by direct field comparison
  across all 12 (strategy × symbol) runs; the largest relative difference in any metric is
  `1.1e-12`, i.e. IEEE-754 rounding. Ratio metrics are scale-invariant because
  `_open_position` computes `position_size = (capital * position_size_pct) / price` with no floor,
  no tick/lot rounding, and `partial_fill_volume_pct = 0.0` by default (the one mechanic that
  would break invariance is off).
- **A→B (cost model): +0.75pp for `multi_indicator`, +0.17pp for `bb_mean_reversion` — in the
  IMPROVING direction.** Switching to "realistic" costs makes the result *better*, not worse.

### Why B beats A — the "realistic" model is cheaper than the legacy one

| component | legacy | realistic (`bybit_perp` / `atr_aware` / funding on) |
|---|---|---|
| fee per side | 0.1000% (`commission=0.001`) | 0.0550% taker (`bybit_taker_fee`) |
| slippage per side | 0.0500% (`slippage=0.0005`) | **0.0500% — the ATR path never engages, see below** |
| funding | none | 0.01%/8h on **open longs only** |
| **round trip** | **0.300%** | **0.216%** |

The legacy `commission = 0.001` is ~1.8x Bybit's actual 0.055% taker fee. So the "cheap legacy
cost model" was, on fees, the *pessimistic* one. The optimism in the Dec-2025 regime was never
the fee rate.

Three caveats that make the realistic mode less realistic than its name implies:

1. **`slippage_mode="atr_aware"` is a no-op for both strategies.** `_effective_slippage` reads
   `signal.get("atr")` — a **top-level** key. Neither `mean_reversion_strategy.py` nor
   `multi_indicator_strategy.py` emits one (`phase1_strategy` puts ATR in `metadata`, which the
   *entry* path does not read — `_close_position` reads `metadata["atr"]`, `_open_position` reads
   `signal["atr"]`; the two paths disagree). With `atr_value=None` the function silently falls
   back to the legacy fixed 5 bps. Slippage in B is within 0.1% of slippage in A — that is the
   fingerprint of the fallback, not of ATR scaling. Had ATR been supplied, `0.05 * ATR/price`
   would have exceeded the 5 bps floor on **66%/69%/27%** of SOL/ADA/BNB bars (median ATR/price
   1.12%/1.19%/0.74%), so real ATR-aware slippage would be materially **higher** than reported.
2. **Funding is charged on longs only.** `_apply_funding` returns early unless
   `order_type == BUY`. Short positions pay zero funding, ever. Funding is only 0.02–0.05% of
   capital here for that reason.
3. **Maker rebates were ~zero because there were no SL/TP exits.** Both strategies exit via a
   `HOLD` signal, so `_close_position` is always called with `reason="signal"` → taker. Only
   `baseline_rsi_ema` (13 trades) hit stop/TP levels and earned the `−0.01%` maker rebate. Worth
   flagging as a latent optimism: in `bybit_perp` mode, stop-loss exits are credited a **rebate**,
   which a real stop-market order would never receive.

### Does $100 change anything structurally? — min-notional finding

**No, and that is the defect.** `BacktestEngine` enforces **no minimum notional whatsoever**.
`_open_position` (`backtest_engine.py:380-436`) computes size, optionally applies the
`partial_fill_volume_pct` cap, applies slippage and fees, and opens the position. There is no
`min_notional` check, and `grep -i "min_notional\|min_order" backtesting/*.py` returns nothing.

Quantified:

- `MIN_NOTIONAL_USD = 5.0` (`shared/account.py`).
- Engine default `position_size_pct = 0.02` → on $100 the notional is **$1.99 median**.
- **Entries clearing $5.00 in cells C and D: 0 out of 3,404 (1,702 per cell).** Not "some trades" — *all* of them.
  The notional is a fixed fraction of capital, so it never grows into the floor.

**Therefore cell D overstates.** A real $100 Bybit account could not have placed a single one of
those 3,404 orders. The correct real-world result for cells C/D is *no trading at all*, not
−1.03%/−2.29%.

### Cell D′ — the only $100 configuration that could actually have executed

The engine's `position_size_pct = 0.02` default is an *engine* default; it disagrees with the
repo's declared paper cap `shared.account.MAX_RISK_PER_TRADE = 0.10` (ADR-010, relaxed precisely
to clear Bybit min-notional on $100). Re-running cell D with the declared cap — **not a tuning
change; it substitutes the repo's own declared value for an undocumented engine default** —
gives $9.33–$9.83 median notional, so **all 1,689 entries clear the $5 floor**:

| strategy | trades | ret% | gross% | cost% of capital | WR% | max DD% | Sharpe (engine) | Sharpe (hourly) | median notional | entries ≥ $5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| bb_mean_reversion | 326 | **−5.100** | −2.766 | **2.333** | 57.28 | 5.95 | −2.43 | −2.47 | $9.83 | 326/326 |
| multi_indicator | 1,363 | **−10.978** | −1.823 | **9.155** | 45.59 | 11.72 | −2.44 | −4.21 | $9.33 | 1,363/1,363 |

Per symbol (all realistic costs, $100, 10% sizing): bb_mean_reversion SOL −6.24% / ADA −5.36% /
BNB −3.69%; multi_indicator SOL −9.61% / ADA −11.65% / BNB −11.67%. Raw rows in
`results_10pct.json` in the scratchpad.

**This is the number to quote as the honest one.** −5.1% (326 trades) to −11.0% (1,363 trades)
over 180 days on a $100 account, with costs of 2.3%–9.2% of the entire account against a gross
P&L of −1.8% to −2.8%. `multi_indicator`'s 11.7% mean max drawdown sits right at
`MAX_DAILY_LOSS_PCT = 12.0` — a whole-run drawdown, not a daily one, but close enough to note.

Also worth recording: the engine's Sharpe becomes −2.0 to −3.1 here rather than −7 to −12, purely
because larger per-bar returns dilute the mis-scaled risk-free term. That is further confirmation
the Sharpe defect below is real — a metric whose value depends on position size that much is not
measuring risk-adjusted return.

Finally, `LIVE_MAX_RISK_PER_TRADE = 0.02` on $100 sizes $2 notional — below the $5 floor. LIVE
remains mechanically non-viable at this account size regardless of any result above.

---

## LOUD: cell A does **not** reproduce the published −0.22..−0.50 Sharpe range

Cell A Sharpes are **−7.6 to −54.6**, not −0.22 to −0.50. The comparison is **not clean**, and the
reason is provenance, not drift:

**The Dec-2025 numbers were never produced by `backtesting/backtest_engine.py`.**
`comprehensive_FINAL_RESULTS.log` was generated by `scripts/test_all_strategies_csv.py`, which
defines its own `PatchedBacktestEngine` wrapping the **trading-engine service's**
`app.backtesting.backtest_engine` (`BacktestConfig` / `StrategyBase` / `calculate_all_metrics`) —
a different engine, different strategy classes (`RSIMomentum`, `EMACrossover`,
`BollingerMeanReversion`, …), 10 symbols at 4,320 bars, `initial_equity=10000.0` and
`position_size_pct=2.0` hardcoded at line 877-880 of that script.

**Consequence:** the premise that those logs were optimistic *because `BacktestEngine()` defaulted
to `$10,000`* is incorrect. `BacktestEngine`'s default never touched them. The $10,000 in the
published results comes from `scripts/test_all_strategies_csv.py:877`, which the 2026-08-03
capital fix (`4489fe7`) did **not** change. That literal is still there.

Two things are nevertheless consistent between the two runs and are the honest read-across:

- `BollingerMeanReversion` in the log: **43.1% WR, −0.02% return, ~285 trades/symbol**.
  `bb_mean_reversion` here: **56.1% WR, ~109 trades/symbol**. Same family, different
  parameterisation and different sizing convention — consistent in sign and in "loses money at a
  respectable win rate", not comparable in magnitude.
- Every strategy in both runs is negative on every symbol. Nothing here contradicts the published
  conclusion; it just cannot be called a reproduction of it.

### Why the Sharpe magnitudes are absurd (engine defect, reported not fixed)

`_calculate_sharpe_ratio` (`backtest_engine.py:663-678`) computes per-**bar** returns from an
**hourly** equity curve, then subtracts a **daily** risk-free increment (`risk_free_rate / 365`)
and annualises with `sqrt(365)`. On hourly bars the risk-free subtraction (`5.48e-5`) is ~50x the
mean per-bar return and dominates the whole statistic — which is why even the +0.11%-return
`baseline_rsi_ema` reports Sharpe **−43.6**. The engine's number is reported above as primary
(faithful to what the code emits); the `sharpe_hourly_annualised` column re-runs the identical
formula with `periods = 365*24` and gives **−3.5 to −8.9** for the active strategies. Both are
negative; neither is comparable to the published −0.22..−0.50, which came from a different metric
implementation. **This engine's Sharpe should not be quoted as a headline number until the
period convention is fixed.**

Near-zero max drawdown (1.0–3.3%) has the same cause as in the old log: a 2%-of-capital notional
means equity barely moves regardless of what the strategy does.

---

## Method notes / engine bugs found while running (none fixed)

- **`reset()` does not zero `_bar_count`** (`backtest_engine.py:230-235` vs `:187,:297`). Reusing
  one engine across symbols leaks the 8-hour funding cadence phase into the next run. Worked
  around by constructing a **fresh engine per (cell × strategy × symbol)** — 48 engines.
- **`total_profit_loss` excludes entry commissions.** `_open_position` deducts the entry fee
  straight from `self.capital`; it never enters the `Trade` record, so `sum(trade.profit_loss)`
  is net of the *exit* fee only. `total_profit_loss_pct` (built from the capital delta) is the
  only correct net figure, and it is what this report uses. The two disagree by exactly the entry
  fees (e.g. multi_indicator/SOL/A: −$185.15 vs −$270.84).
- Cost accounting was done by subclassing and measuring capital deltas around the engine's own
  calls, so fees/funding are exact rather than re-derived. Slippage is
  `size * |fill_price − bar_close|`, computed **only** on entries and non-SL/TP exits (SL/TP exits
  use a preset level and the engine applies no slippage there).

## Scope limitation — state this wherever these numbers are cited

Only **3 of the 5 validated symbols** have 180-day cache. **BTC and ETH are absent**
(`BTCUSDT_60m_90d_bybit.csv` is 90d, `ETHUSDT` has only a 60d file). This is **not** a full
validated-set result. It is 3 mid-cap symbols over one 180-day window (2025-06 → 2025-12),
single-window, no walk-forward, no CPCV, no PSR/DSR. Do not promote any of these figures to an
edge claim in either direction.
