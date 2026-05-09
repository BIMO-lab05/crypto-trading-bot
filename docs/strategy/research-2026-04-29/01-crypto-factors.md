# Crypto Systematic Factors: Empirical Evidence for Retail SOL/BNB/ADA, Hourly/Daily

> Research agent output, 2026-04-29. Source for synthesis task #8.

## Important context first

Universe is n=3 majors. Most published crypto factor work is cross-sectional on 50–500 coins where the "size" leg dominates returns; **those results do not translate to a 3-asset book.** Findings below filtered for what survives at n=3 on hourly/daily bars.

## Ranked factors

| # | Factor | Lookback / horizon | Reported Sharpe | Primary citation | Retail viability | Key caveat |
|---|---|---|---|---|---|---|
| 1 | **Time-series momentum (per-asset trend)** | 20–50d MA crossover, or 28d lookback / 5d hold | 1.5–1.9 in-sample; ~0.84 buy-and-hold benchmark | Moskowitz/Ooi/Pedersen (JFE 2012); Han/Kang/Ryu SSRN 4675565; Grayscale 2024 (50d MA, 2012–23: ann 126%, SR 1.9) | **High.** Daily bars, 1 signal/asset, low turnover. Survives on majors. | Backtests heavily overlap the 2017–21 bull. Severe crashes in regime turns (Apr 2021, Nov 2022) — must combine with vol scaling (#3). |
| 2 | **Cash-and-carry / funding-rate basis** (delta-neutral spot vs. perp) | Hold while basis > cost; 8h funding cycle | He/Manela/Ross arxiv 2212.06888 report **SR ≈ 1.8 net of retail fees, 3.5 for MMs**. BIS WP 1087: avg basis >10% p.a., excursions to 40%+. | He, Manela, Ross (arxiv 2212.06888 v5, 2024); Hou/Choi BIS WP 1087 (2023) | **Medium.** Mechanically works on Bybit for SOL/BNB; needs spot+perp leg, exchange/credit risk, careful sizing vs. liquidation. | Profitability has **compressed sharply 2024→2025** (BIS, multiple practitioners); peak SR was a 2020–22 phenomenon. Real risk is exchange failure (FTX, see Nov 2022 carry going to −50% APR). |
| 3 | **Volatility-managed / inverse-vol scaling overlay** (not a standalone signal) | Scale position by 1/σ̂ (20–60d window) | Barroso & Santa-Clara (JFE 2015): roughly doubled momentum SR; replications in crypto (Wang et al. 2025, FRL S1544612325011377) report ~30% SR uplift on weekly crypto momentum | Moreira & Muir (JF 2017); Barroso & Santa-Clara (JFE 2015) | **High.** Just position sizing — pure overlay on #1. | Cederburg et al. (JFE 2020) show vol-managed portfolios do **not** systematically outperform OOS vs. unmanaged. Treat as crash-mitigation, not alpha. |
| 4 | **On-chain / network factor** (active addresses, hash-rate growth) | Weekly to monthly | Bhambhwani, Delikouras & Korniotis (JIFMIM 2023): network/hash-rate factors price the cross-section with statistically significant risk premia | Bhambhwani et al. (SSRN 3387313, JIFMIM 2023); Liu, Tsyvinski, Wu (Cowles 2022) | **Medium.** Daily on-chain APIs free for SOL/BNB/ADA. | Designed for cross-section; with n=3 you're really running 3 univariate signals. Very slow — better as a regime filter than entry signal. |
| 5 | **Intraday reversal** (overnight/early-session reversal of prior session move) | 1h–24h | Wen, Bouri, Xu, Zhao (NAJEF 62, 2022): significant intraday reversal in BTC, ETH, LTC, XRP; "timing strategy beats buy-and-hold" — paper does not publish a clean Sharpe net of costs | Wen et al. NAJEF 2022 | **Medium-low.** Hourly works in your stack, but turnover is high and after Bybit fees + slippage net edge is thin. | Sample ends May 2020 — pre–perp dominance. Treat as hypothesis to retest, not established fact. |
| 6 | **BTC–ETH (and major–major) cointegration / pairs** | z-score on 30–90d residual | Several arxiv/journal pieces report SR 1.5–2.5 in-sample on BTC-ETH; sensitive to cointegration window and break in regime changes | Tadi (arxiv 2305.06961, 2023); Evaluation of Dynamic Cointegration arxiv 2109.10662 | **Medium.** Mechanically suits a 3-asset book, but ADA/BNB cointegration with BTC is unstable. | Cointegration breaks repeatedly post-2021 (ETH/BTC regime shift, BNB exchange-token dynamics). The high Sharpes are typically pre-cost, in-sample. |
| 7 | Cross-sectional momentum / size / "trend factor" | weekly | 1.2–1.5 in published papers | Liu, Tsyvinski, Wu (JF 2022) | **Not applicable at n=3.** Returns are largely a small-cap illiquidity premium. Listed for completeness only. | — |

## What's contested or stale

The **cross-sectional momentum** literature is genuinely contested: Liu-Tsyvinski-Wu (JF 2022) find ~3%/week long-short payoffs on weekly data 2014–2020, but Grobys & Sapkota (Econ Lett 2019; IJF&E 2025 "Is It an Illusion?") and Shen et al. (2020) find no significant CSMOM on monthly/weekly data once you restrict to large caps and post-July-2020 — the original effect is largely a small-cap, pre-2021 phenomenon. **Crypto carry** had SR ~6 over 2020–2024 windows but **went negative in 2025** as basis compressed post-spot-ETF launch (BIS data; multiple desk reports) — past Sharpes mislead. **Volatility-managed portfolios** outperform in-sample but Cederburg, O'Doherty, Wang & Yang (JFE 2020) show OOS reasonable implementations underperform unmanaged. Anything backtested only 2017–2021 should be assumed stale: that window covers one bull, one bear, no spot ETF, no high real rates, no MEV-dominated DEX flow.

## What's specific to crypto (not borrowed from equities)

- **Funding-rate carry on perpetuals** — no equity analogue; market-microstructure artifact of perp design (8-hour funding payment to peg perp to spot).
- **On-chain network factors** (active addresses, hash-rate, fee burn) — crypto-native fundamentals with no equity counterpart; Bhambhwani et al. show predictive power.
- **24/7 + weekend liquidity drain** — literature mixed but the structural fact is genuine: institutional desks closed Sat/Sun, lower depth, larger gaps at Mon-Asia open. Exploitable as regime filter, not standalone alpha.
- **Stablecoin flow and exchange-balance signals** (Glassnode-class) — no equity analogue; evidence mostly practitioner, weakly academic.
- **Conspicuously absent**: a "value" factor (price-to-fundamental ratios on crypto are unstable); equity-style "quality" factor.

## Sources

- Liu, Tsyvinski, Wu — Common Risk Factors in Cryptocurrency (JF 2022 / NBER w25882)
- Han, Kang, Ryu — Time-Series and Cross-Sectional Momentum in Crypto (SSRN 4675565)
- Moskowitz, Ooi, Pedersen — Time Series Momentum (JFE 2012)
- Grayscale — The Trend is Your Friend (2024)
- He, Manela, Ross — Fundamentals of Perpetual Futures (arxiv 2212.06888)
- Hou & Choi — Crypto Carry (BIS WP 1087, 2023)
- Moreira & Muir — Volatility-Managed Portfolios (JF 2017)
- Cederburg et al. — On the performance of volatility-managed portfolios (JFE 2020)
- Bhambhwani, Delikouras, Korniotis — Blockchain Characteristics and Crypto Returns (SSRN 3387313)
- Liu, Tsyvinski, Wu — Accounting for Cryptocurrency Value (Cowles 2022)
- Wen, Bouri, Xu, Zhao — Intraday Predictability in Crypto (NAJEF 2022)
- Grobys & Sapkota — Cryptocurrencies and Momentum (Econ Lett 2019)
- Grobys — Cryptocurrency Momentum: Is It an Illusion? (IJF&E 2025)
- Cryptocurrency market risk-managed momentum strategies (FRL 2025)
- Tadi — Copula-Based Trading of Cointegrated Crypto Pairs (arxiv 2305.06961)
- Cryptocurrency Momentum Has (Not) Its Moments (FMPM 2025)
