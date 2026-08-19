# Battery #2 Pre-Registration Manifest

**Date:** 2026-08-18  
**Status:** Pre-registered, committed before any candidate implementation.

---

## Global Constants (Read Live from Config)

All candidates are evaluated against the same cost model, recorded once to prevent transcription drift.

### Pinned Configuration

| Parameter | Source | Value |
|-----------|--------|-------|
| Account Equity | `shared/account.py:ACCOUNT_EQUITY_USD` | $100 USD |
| Hurdle Multiple | `backtesting/edge_lab/config.py:15` | 2.0× |
| Modelled Fee Rate (per pair) | `backtesting/screen.py:50` | 0.1% |
| Slippage BPS (BTC/ETH/SOL) | `backtesting/edge_lab/config.py:17-21` | 5 bps |
| Slippage BPS (BNB/ADA) | `backtesting/edge_lab/config.py:17-21` | 10 bps |
| Slippage Fallback BPS | `backtesting/edge_lab/config.py:23-25` | 10 bps |
| DSR Threshold | `backtesting/edge_lab/config.py:27` | 0.95 |
| Min Positive Path Frac | `backtesting/edge_lab/config.py:29` | 0.70 |
| Notional per Trade | `backtesting/edge_lab/config.py:34` | $100 USD |
| CPCV Groups | `backtesting/edge_lab/config.py:30` | 10 folds |
| CPCV Test Groups | `backtesting/edge_lab/config.py:31` | 2 test groups |
| CPCV Embargo Pct | `backtesting/edge_lab/config.py:32` | 1% |
| Trial Floor (Static) | `backtesting/edge_lab/config.py:28` | 16 |
| Funding Data Source | `backtesting/data/funding/` | 30+ symbols, 730 days |

**Cost Implications:**  
- Round-trip taker cost: ~11 bps (BTC/ETH/SOL) to ~31 bps (BNB/ADA), plus funding accrual if held across a funding timestamp.
- Per the deployed ensemble benchmark, gross edge is ~4.88 bps per trade against 21–31 bps round-trip cost — a 2.3–4.1× shortfall.

### Universe Pin

| Parameter | Value |
|-----------|-------|
| Universe file | `backtesting/edge_lab/universe_2026-08-17.json` |
| Top N | 30 symbols |
| Min Listing Age | 730 days |
| Date locked | 2026-08-17 |

### Data and Ledger

| Parameter | Value |
|-----------|-------|
| Data cutoff (--date flag) | 2026-08-17 (inclusive, data through EOD) |
| Lookback windows | Daily: 730d; H4: 365d |
| Kline intervals | Daily (1D), H4 (240m) |
| Trial ledger count going in | 8 variants (battery #1 2026-08-17) + ~5 historical (H-series killtests) |
| Ledger gate binding | Ledger count controls DSR threshold. Static floor is 16; ledger-derived count becomes active once it exceeds 16. Currently binding above 16; expected to bind tightly in battery #2. |

---

## Candidate Family #1: Funding-Carry Refinements

**Prior:** HIGHEST  
**Motivation:** Best survivor of battery #1. `thresh_2x` variant cleared Gate 1 at ratio 2.603 (gross edge well above hurdle), but failed Gate 2 with DSR 5.8e−10 (hard REJECT). The mechanism is real and identifiable in the data: perpetual funding rates are a signed payment from crowded long positions to short positions.

### Hypothesis

Funding-rate entry thresholds tuned to percentile entry levels, combined with holding-period restrictions and symbol filtering, can produce a distribution of profitable trades (pooled PF > 1.0, DSR > 0.95) rather than a handful of outliers.

### Economic Mechanism

Bybit perpetual contracts pay funding rates every 8 hours. On crowded long-heavy symbols, shorts receive positive funding (longs pay), creating an immediate carry income. A short position held across 1–3 funding epochs accrues this payment. Entry is triggered when the current funding rate exceeds a percentile threshold (e.g., 75th percentile of historical rates for that symbol), signaling an extreme long-crowding event likely to reverse.

**Who pays:** Long-biased retail traders paying shorts to hold crowded positions. Funding is a measurable, predictable flow (unlike edge from directional forecasting, which the battery has falsified).

### Variants (Exact Parameters, Pre-Registered)

Each variant is a point in the (entry-percentile, holding-period, symbol-set) design space. No variants may be added after the run starts.

| Variant | Entry Percentile | Holding Period (Hours) | Symbol Filter | Bundle Inputs | Label Horizon (Days) | Rationale |
|---------|------------------|----------------------|----------------|-------|---|---|
| `fp_75pct_8h_major` | 75th percentile | 8 (one funding epoch) | BTC, ETH, SOL only | daily, h4, funding | 1 | Baseline: major coins only, minimal hold to capture single funding payment. Entry at elevated rate level to avoid false signals. |
| `fp_90pct_24h_major` | 90th percentile | 24 (three epochs) | BTC, ETH, SOL only | daily, h4, funding | 3 | Higher-threshold variant on majors: entry only on extreme crowding, three epochs of accrual. |
| `fp_75pct_8h_all` | 75th percentile | 8 (one epoch) | Top 30 (full universe) | daily, h4, funding | 1 | Same entry/holding as baseline but across all 30 symbols: tests whether edge persists on lower-liquidity venues. |

**Bundle Inputs:**  
- Daily candles: for mean-reversion baseline comparison.
- H4 candles: for intraday regime context (optional; may improve entry timing).
- Funding rates: from `backtesting/data/funding/<SYMBOL>_funding.csv`, mandatory.

**Cost Exposure:**  
- Notional per trade: $100 (full account, limited by risk cap).
- Cost per round-trip: 11 bps (major coins) to 31 bps (alts), plus funding accrual.
- Funding accrual: signed, per symbol. Positive funding (shorts receive) reduces cost. At typical ~0.01%/day rates, an 8-hour hold accrues ~0.003% (3 bps), partially offsetting taker fee.

### Prior Statement

`thresh_2x` from battery #1 passed the cost hurdle at a 2.603× ratio — a rare win — but failed DSR (5.8e−10, far below 0.95). The failure mode was a handful of extreme-value outliers (>1 month consecutive funding) carrying the entire P&L; the bulk trades were losers. The three variants above attempt to stabilize this:

1. Refinement of entry rules: moving from a single threshold to percentile-based entry for more robust signal.
2. Symbol filtering: testing whether the edge that emerged on major coins during 2026-08-17 generalizes.
3. Holding-period sweep: varying the accrual window to find the sweet spot between fee drag and funding capture.

**Expectation:** Medium-to-low probability of Gate 2 pass, higher than chance but below 10%. The mechanism is sound, but the data span (730d) is short for funding regime estimation, and the earlier failure suggests this is a regime-specific edge rather than a portable one.

---

## Candidate Family #2: Pairs / Statistical Arbitrage

**Prior:** MEDIUM  
**Motivation:** Cointegrated pairs are the one classic mean-reversion family no battery has tested. The mechanism is theoretically sound and has been profitable in equity and fixed-income markets, but crypto microstructure is very different. This is pure exploration — discovering whether the mechanism exists at all.

### Hypothesis

On the top-30 symbols, there exist pairs (e.g., two mid-cap alts) with stable hedge ratios (cointegration parameter γ) such that deviations from the hedge ratio (spread) are mean-reverting within a 4–24 hour window, and spread oscillations over-compensate for round-trip costs on both legs.

### Economic Mechanism

Two assets with a stable long-term price relationship (e.g., two DeFi tokens or two L1 chains) will occasionally diverge due to temporary liquidity imbalances, news, or cascading retail trades. A market-neutral position (long one, short the other at the hedge ratio) profits on mean reversion. 

**Who pays:** Liquidity takers exacerbating the temporary spread. The edge is an artifact of market microstructure, not of fundamental under/overvaluation.

### Variants (Exact Parameters, Pre-Registered)

Cointegration itself is a statistical property, not a parameter knob. The design space is pair selection, hedge-ratio estimation window, and reversion detection.

| Variant | Pair Selection | Hedge Ratio Lookback | Entry Signal | Holding Period | Rationale |
|---------|-----------------|---------------------|--------------|---|---|
| `pairs_sector_30d` | Same sector (e.g., L1s: SOL/BNBUSDT, alts: ADAUSDT/DOGEUSDT). Cointegration test over 30d rolling window. Require ADF p-value < 0.05. | 30 days | Bollinger Band exit (2σ) on the spread (Z-score) | 4 hours | Hypothesis: sector-mates have tighter cointegration. Short lookback (30d) captures recent regimes. 4h window allows multiple round-trip attempts per day. |
| `pairs_volume_top10_60d` | Highest 10 in 24h turnover (excluding BTC/ETH as "too liquid"). Cointegration over 60d rolling. ADF p-value < 0.05. | 60 days | Mean-reverting to zero Z-score (spread normalized by volatility) | 8 hours | Longer lookback (60d) for stability; top-volume restriction to avoid thin-book pairs. 8h window captures one cycle of funding accrual. |
| `pairs_orthogonal_30d` | Pairs with low correlation (ρ < 0.5) but individually liquid. Maximizes diversification and reduces concentration risk. | 30 days | Entry at 1σ excursion; exit at mean | 4 hours | Tests whether low-correlation pairs avoid regime-cluster blowups. Tighter correlation constraint than sector pairs. |

**Bundle Inputs:**  
- Daily candles: for cointegration estimation.
- H4 candles: for regime filtering (optional; can detect intra-day liquidity crises).
- Funding rates: not required, but useful for filtering periods of extreme crowding.

**Cost Exposure:**  
- **Pairs emit TWO trades per position** (long one leg, short the other). Notional per leg: $100 ÷ 2 = $50 (risk cap applies to the pair's net risk, not each leg).
- Cost per round-trip per position: ~22 bps per leg (two legs = 44 bps gross), meaning break-even spread must be >44 bps wide. A typical crypto pair spread oscillates 20–100 bps depending on liquidity; in quiet regimes, spreads narrow below cost.
- Holding horizon: 4–8 hours, crossing potential funding timestamps (8-hour intervals). Funding accrual on the short leg can help; on the long leg, it costs.

### Prior Statement

Pairs trading has never been tested in this battery. The code exists as prior art (`services/trading-engine/app/strategies/pairs_trading.py`) but has known failing tests (`test_pairs_trading`, flagged in 2026-08-17 baseline). Implementing three variants here allows direct empirical testing of whether the mean-reversion mechanism exists in crypto.

**Expectation:** Very low baseline probability of Gate 2 pass (<5%). Crypto lacks the informational structure that makes pairs profitable in equities. That said, if ANY family has an undiscovered edge, it is the one no one has looked at yet. A Gate 1 KILL is expected; a Gate 1 PASS would be surprising and worth Gate 2 scrutiny.

---

## Candidate Family #3: Regime-Gated Trend

**Prior:** LOW (stated plainly)  
**Motivation:** `lf_trend` (lookback-forward trend) cleared Gate 1 decisively (ratios 4.85 and 15.51 — the best performers in battery #1), but failed Gate 2 with pooled PF ≈ 1.0 — all profit came from a handful of outliers, not a distribution. The pinned seed direction is: a regime filter attempts to select only the periods where trend momentum is most reliable, turning outliers into a stable distribution.

### Hypothesis

Directional trend-following has no edge on the full time series (battery #1 verdict), but it may have edge during regimes where volatility is elevated and directional momentum is persistent. A filter gating entry to high-volatility / high-ATR regimes can eliminate the low-signal, high-noise periods and transform a few lucky outliers into a consistent distribution.

### Economic Mechanism

Trend-following works by riding directional momentum (higher prices attract more buying). In trending regimes (high volatility, persistent directional pressure), this feedback loop is real. In ranging regimes (low volatility, price oscillation), the same signal is noise. A regime filter selects for trending periods and ignores ranging periods, reducing false signals and lowering the fraction of losing trades.

**Who pays:** The market inefficiency is real, but only during trending regimes. By filtering, we avoid the drag of trading in noise.

### Variants (Exact Parameters, Pre-Registered)

Regime detection is the only parameter. The underlying trend signal (`lf_trend` from battery #1) remains fixed.

| Variant | Regime Filter | ATR or Volatility Threshold | Entry Only When | Holding Period | Rationale |
|---------|-------|------|-------|---|---|
| `trend_atr_high_20d` | 20-day ATR percentile | 70th percentile (volatility elevated) | ATR(20) > 70th pctile of last 100 bars | Until close below 50-day MA or ATR drops below 30th pctile | Entry gate enforces trending regime. Exit gate allows the trend to reverse naturally. Tested on both buy and sell signals. |
| `trend_vol_spike_20d` | 20-day rolling volatility (σ of returns) | 75th percentile | σ(20 days) > 75th pctile of last 252 days | Until reversal or ATR < 20th pctile | Longer-history volatility percentile (252d) to avoid local over-fitting. Tighter gate (75th) to capture only clear spikes. |
| `trend_vix_analog_10d` | 10-day high-low range as crude vol proxy | 80th percentile | (high(10d) - low(10d)) / close > 80th pctile of last 60 days | Until range contracts or trend reverses | Simpler filter using only OHLC (no indicators). Tests whether the filter must be sophisticated. |

**Bundle Inputs:**  
- Daily candles: for ATR/volatility calculation and trend signal.
- H4 candles: optional, for cross-timeframe confirmation of regime (can reduce false signals).
- Funding rates: not required.

**Cost Exposure:**  
- Notional per trade: $100 (full account).
- Cost per round-trip: 11–31 bps + funding.
- Holding period: 1–10 days typically (trend-following can run longer than mean reversion). Funding accrual spans 4–40 funding epochs.

### Prior Statement

`lf_trend` variants (dc_20_10 and dc_55_20) from battery #1 are the elephant in the room:

- Both cleared Gate 1 (ratios 4.85 and 15.51) with flying colors — seeming to be the best-performing candidates.
- Both failed Gate 2 badly (DSR near zero, pooled PF ≈ 1.0 / 0.99).
- Post-hoc analysis showed that profit was concentrated in a few multi-week trends (e.g., one 4-week bull run accounting for 60% of total P&L); the remaining 95% of the time, the strategy lost.

**This is the textbook overfitting smell.** Gate 2's DSR is *designed* to catch exactly this: a strategy that passes Gate 1 (gross edge) but fails in hold-out folds (no robust distribution). A regime filter that merely *removes the losing periods* in-sample is just a more-selective backtest — same mechanism, tighter data-mine.

**Expectation:** Very low probability of Gate 2 pass (<3%). The regime-filter direction is theoretically sound, but `lf_trend` is suspected overfitting, not a real edge waiting to be refined. If the filter passes Gate 2, it will have done something remarkable: converted an in-sample artifact into an out-of-sample distribution. Possible, but we go in assuming no.

---

## Trial Ledger Continuity

The trial ledger (`backtesting/edge_lab/trial_ledger.json`) currently holds **8 variants** from battery #1 (2026-08-17) plus approximately **5 historical entries** from prior H-series killtests, for a total of ~13 trials as of 2026-08-17.

Battery #2 will append **9 new variants** (3 families × 3 variants each):

- `funding_carry`: fp_75pct_8h_major, fp_90pct_24h_major, fp_75pct_8h_all
- `pairs_trading`: pairs_sector_30d, pairs_volume_top10_60d, pairs_orthogonal_30d
- `trend_regime`: trend_atr_high_20d, trend_vol_spike_20d, trend_vix_analog_10d

**DSR gate will use `num_trials = max(16, ledger_count)` where ledger_count is the total appended through battery #2, expected ~22 trials.**

---

## Anti-P-Hacking Commitment

This manifest pre-registers the three families and nine variants **before any candidate module is written, before any data is fetched, and before any results are observed**.

No candidate or variant will be added after this commitment. No parameter will be changed after testing. Any variant that dies at Gate 1 or produces zero trades will still be recorded in the ledger as a trial (preventing later claims of "we didn't really test that").

The three families represent the limits of exploration for this battery:

1. **Funding-carry refinements** — the highest-prior path, because the mechanism is real in the data.
2. **Pairs / stat-arb** — medium-prior exploration of an untested family.
3. **Regime-gated trend** — a low-prior, adversarial bet that we can recover an apparent overfitting artifact.

If all three families REJECT, the battery is complete and the operator directs whether to continue with battery #3 or pause research.
