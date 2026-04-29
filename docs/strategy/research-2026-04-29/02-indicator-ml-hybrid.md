# Hybrid Indicators + ML for Systematic Trading — Literature Synthesis

> Research agent output, 2026-04-29. Source for synthesis task #8.

## Architectures that have replicated

**1. Meta-labeling (López de Prado, 2018; Joubert & Singh / Hudson & Thames, 2022).** A primary signal source (your indicator vote OR the GRU) emits side; a secondary classifier emits go/no-go and size, trained on whether the primary was correct. Empirically replicated to lift Sharpe and reduce drawdown when the primary has high recall but low precision — exactly the diagnostic of a 9-indicator vote. Hudson & Thames' triple-barrier study replicates the technique on equities OOS; QuantConnect's negative results show it fails when the primary is already near-optimal, when classes are too imbalanced, or when the secondary overfits — all retail-tractable issues. **Retail-viable: yes.**

**2. Multi-indicator features stacked into LSTM/GRU (parallel deep model, then voting).** Best-replicated finding in the recent review by Murray et al. (arxiv 2405.11431): variants of LSTM with TA features stacked as inputs beat both pure-OHLCV deep models and pure-indicator rules on RMSE — but the review itself flags that all measured papers predict price level, not returns, and use fixed train/test splits. The "Technical Analysis Meets Bitcoin" paper (arxiv 2511.00665) is rare for reporting net returns: LSTM 53.23% vs. buy-hold 42.31% after 0.1% fees, single fixed split, ~56% directional accuracy. **Retail-viable: yes, modestly.**

**3. Confidence-weighted aggregation gated by a meta filter (Increase Alpha, arxiv 2509.16707).** Curated TA + fundamental + sentiment features, feed-forward + recurrent ensemble, six-quarter rolling calibration → one-quarter OOS, Sharpe ~2.54 net of 4% borrow, live since 2021. The >90% long-side directional-accuracy headline is on a filtered high-confidence subset, not all bars — important caveat. **Retail-viable: partial** (compute is cheap; feature engineering is the moat).

**4. Ensemble of DRL agents weighted by softmax of recent Sharpe (FinRL contests, arxiv 2501.10709).** Stock OOS Sharpe 1.11–1.48; **crypto Sharpe collapses to 0.28** because component agents lacked diversity. Confirms that ensembles only help when components are decorrelated. **Retail-viable: marginal for crypto.**

## Promising but evidence is thin

- **Technical Indicator Networks (Kuhrt, arxiv 2507.20202).** Embeds MACD/MA as differentiable layers initialized at classical values, fine-tuned via RL. Reports Sharpe 2.45–2.74 vs. classical MACD 1.65, but on 30 US30 equities, three-year window, no walk-forward, no code release.
- **CryptoPulse dual-prediction with sentiment-weighted fusion (arxiv 2502.19349).** Reports MSE/MAE only, no Sharpe, no returns, fixed 7:1:2 split, predicts price level. To validate: returns-based OOS, walk-forward, removal of sentiment-leakage risk.
- **Regime-aware ensemble re-weighting (Springer Digital Finance 2024).** Conceptually sound but the FinRL crypto result and the synthetic-controlled-environment study (Arian et al., ScienceDirect S0950705124011110) both show regime detectors that helped in one period failed in the next.

## Common methodology errors — checklist for your hybrid bot

1. **Predicting price level, not log-returns.** R² ≈ 0.99 on price is the signature — a persistence baseline (next price = last price) gets the same. **Your "GRU R² = 0.995, Dir.Acc 79%" is almost certainly this artifact unless R² is computed on returns**; the gap to 79% directional accuracy is the real diagnostic and 79% is itself extraordinary for crypto and warrants suspicion of leakage (label horizon overlapping training, indicator computed using future bars, normalization fit on full set).

2. **Single fixed train/test split.** Used by CryptoPulse, the Bitcoin LSTM paper, and most arXiv crypto-prediction papers. Replace with **CPCV (López de Prado)** — Arian et al. (2024) show CPCV materially lowers PBO and produces more honest Deflated Sharpe than walk-forward.

3. **Reporting RMSE/MAE/R² instead of net Sharpe and turnover.** The Bitcoin paper (2511.00665) shows LightGBM beat LSTM on accuracy (58.4% vs 56.1%) but lost on returns — accuracy and PnL diverge.

4. **No deflated Sharpe.** With 9 indicators × hyperparameter sweeps, the implicit number of trials is high; unadjusted Sharpe is inflated (Bailey & López de Prado 2014).

5. **Look-ahead via indicator construction.** Bollinger/MACD windows that touch the bar being predicted; min-max scaling fit on full series; sentiment scored after the fact.

6. **Static ensemble weights frozen at calibration.** FinRL crypto result shows this collapses on regime change.

## Recommendation — ranked by expected lift

1. **Add a meta-labeling layer on top of your existing aggregator.** Treat the current confidence-weighted vote as the *primary* (side); train a gradient-boosted secondary on triple-barrier labels to gate execution and size. Literature is consistent that this is the highest-lift, lowest-risk addition for a system in your shape (high-recall primary). **Expected lift: largest, most documented.**

2. **Replace fixed split + walk-forward with CPCV + Deflated Sharpe for evaluation.** Doesn't change the bot, changes whether you can trust your metrics. Without this, lift estimates from change #1 are unreliable.

3. **Re-target the GRU on log-returns over a fixed horizon, not price level; report directional accuracy and net-Sharpe of an isolated GRU-only strategy.** If isolated GRU Sharpe is <0.5 OOS net of fees, the current "confidence-weighted aggregator" is mostly weighting noise, and the indicator vote is doing the real work — invert the architecture and use the GRU only as a meta-filter.

## Sources

- Meta-Labeling — López de Prado, *Advances in Financial Machine Learning*
- Hudson & Thames — Does Meta-Labeling Add to Signal Efficacy?
- QuantConnect — Why Meta-Labeling Is Not a Silver Bullet
- Bailey & López de Prado, Deflated Sharpe Ratio (SSRN 2460551)
- Bailey, Borwein, López de Prado, Zhu — Probability of Backtest Overfitting (SSRN 2326253)
- Arian, Norouzi, Seco — Backtest Overfitting in the ML Era / CPCV vs. WF
- Technical Analysis Meets Machine Learning: Bitcoin Evidence (arxiv 2511.00665)
- Review of deep learning models for crypto price prediction (arxiv 2405.11431)
- Enhancing Price Prediction in Crypto with Transformer + Indicators (arxiv 2403.03606)
- Technical Indicator Networks — TINs (arxiv 2507.20202)
- CryptoPulse — dual prediction + cross-correlated indicators (arxiv 2502.19349)
- Increase Alpha: AI-driven trading framework (arxiv 2509.16707)
- Revisiting Ensemble Methods for FinRL Contests 2023/2024 (arxiv 2501.10709)
- Confidence-Threshold Framework for Crypto Price Direction (MDPI Applied Sciences)
- Regime switching forecasting for cryptocurrencies (Springer Digital Finance, 2024)
