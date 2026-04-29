# Risk Management Overlays — Measured Sharpe Lift / Drawdown Reduction

> Research agent output, 2026-04-29. Source for synthesis task #8.

**Timescale caveat:** every cited Sharpe number below is from daily or monthly data. An hourly bot will not see the same magnitudes — lookback windows shrink, turnover costs grow, the leverage effect that drives most of these results is weaker intraday.

## Ranked overlays by measured Sharpe lift (all retail-implementable)

1. **Volatility targeting on risk assets (scale exposure to constant realized vol).** Strongest evidence in the literature, but heavily caveated.
   - Barroso & Santa-Clara (2015) on momentum: Sharpe 0.53 → 0.97, max DD -96.7% → -45.2%, kurtosis 18.2 → 2.7 (monthly).
   - Harvey, Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert (Man Group, 2018): Sharpe lift on equities/credit but **negligible on bonds, FX, commodities** — works because of the leverage effect (returns negatively correlated with vol changes).
   - Bitcoin study (Liquidity Shocks paper): 0.72 → 1.21.
   - **Critical hedge:** Cederburg, O'Doherty, Wang & Yan (JFE 2020) and Barroso & Detzel (2021) show **factor-level** vol targeting fails out-of-sample once transaction costs and look-ahead bias are removed; the version that survives is **directional vol targeting on risk assets themselves** (equities/credit/crypto), not factor portfolios. Crypto qualifies — leverage effect is present in BTC.

2. **Fractional Kelly sizing (half- or quarter-Kelly).**
   - MacLean, Ziemba, Blazenko (Mgmt Sci 1992): full Kelly has a 33% probability of halving the bankroll before doubling it.
   - Half-Kelly cuts volatility ~50% while losing only ~25% of expected geometric growth.
   - Universal practitioner consensus. The hard part is the edge estimate — if uncertain, drop to quarter-Kelly or fall back to fixed fractional.

3. **Drawdown-based de-risking (reduce gross exposure proportional to realized DD).**
   - Macrosynergy and Boyd et al. (Stanford, multi-period drawdown control) document that adjusting risk aversion as a function of realized drawdown is the most direct lever on max DD.
   - Quantitative Sharpe lift is modest; the value is in tail control, which is what your 20% DD trigger is already approximating in **binary** form.
   - A continuous version (e.g., halve gross at 10% DD, quarter at 15%) dominates the binary kill-switch.

4. **Time-based stops (mean-reversion strategies only).** Counter-intuitive but supported: simple time-exit rules (close after N bars) outperform price-based stops in mean-reversion contexts because payoff concentrates in early bars. Trailing ATR stops dominate in trend-following.

5. **ATR-based stops (trend-following only).** Useful in trending regimes; sawtooth losses in chop. Strategy-dependent, not a universal Sharpe-lifter.

6. **Equal-weight (1/N) across SOL/BNB/ADA, NOT risk parity / Markowitz.**
   - DeMiguel, Garlappi, Uppal (RFS 2009): 14 optimization models, **none consistently beat 1/N** out-of-sample across 7 datasets.
   - Recent crypto-specific replication (arXiv 2501.12841) confirms this in highly correlated crypto markets.
   - Estimation error eats covariance optimization. SOL/BNB/ADA are >0.7 pairwise correlated — fancy weighting won't pay for itself.

## Folklore that doesn't replicate

- **"Always use a stop loss."** Kaminski & Lo (JFE 2014): under a random walk, simple stop-loss rules **strictly reduce expected return**. They add value only in the presence of multi-month momentum at monthly frequency. For an hourly bot they are net-negative absent a verified momentum signal.
- **HMM / regime detection as alpha.** Most papers showing Sharpe lift don't survive out-of-sample on different regimes. Quantopian's 888-strategy study and the "44% of published strategies fail to replicate" finding apply directly. Regime overlays as a **filter label** are reasonable; as the **source of edge** they are overfitting.
- **Markowitz / risk parity over 1/N for a few-asset portfolio.** Disproven by DeMiguel.
- **Full Kelly.** 33% probability of 50% drawdown before any doubling — psychologically unsurvivable.
- **Tight fixed-% stops (e.g., 1%).** Lund University thesis and Quant-Investing review: most fixed stop levels do not improve performance.

## What to apply FIRST

Given basic caps already in place (5% daily, 2% per-trade, 20% DD), the highest-evidence next step is **portfolio-level realized-volatility targeting**: compute rolling realized vol on hourly returns (e.g., 7-day or 30-day window), set an annualized vol target (start conservatively, ~30-40% for a SOL/BNB/ADA book), and scale gross exposure inversely to realized vol.

This is the single overlay with the most consistent evidence and dominates regime detection as a starting point — **do not add HMM next, the literature does not support it as a first move**.

Once vol targeting is live, replace the fixed 2% per-trade cap with **half-Kelly** sizing **only if** the GRU model's edge is verified directional out-of-sample (the memory's R²=0.995 looks suspiciously high — confirm it's OOS directional, not in-sample R² on regression targets, before sizing on it). Until that's verified, keep fixed-fraction at 2% and let vol targeting do the work.

Convert the 20% DD kill into a **graduated** de-risk (e.g., 0.75x at 10%, 0.5x at 15%, flat at 20%) — same risk floor, smaller path discontinuity.

## Sources

- Barroso & Santa-Clara, "Momentum Has Its Moments" (SSRN 2041429)
- Moreira & Muir, "Volatility-Managed Portfolios" (NBER w22208)
- Harvey, Hoyle et al., "The Impact of Volatility Targeting" (Man Group / SSRN 3175538)
- Cederburg, O'Doherty, Wang & Yan, "On the Performance of Volatility-Managed Portfolios" (JFE 2020)
- DeMiguel, Garlappi & Uppal, "Optimal Versus Naive Diversification" (RFS)
- Kaminski & Lo, "When Do Stop-Loss Rules Stop Losses?" (MIT/SSRN)
- MacLean & Ziemba, "Good and Bad Properties of the Kelly Criterion"
- Boyd et al., "Multi-period Portfolio Selection with Drawdown Control" (Stanford)
- Macrosynergy, "Drawdown Control"
- Liquidity Shocks, Price Volatilities, and Risk-managed Strategy: Bitcoin (JIFMIM)
- Optimal vs naive diversification in crypto (arXiv 2501.12841)
- Man Group, "Overfitting and Its Impact on the Investor"
- Barroso & Detzel critique on transaction costs (Lehigh COWY)
