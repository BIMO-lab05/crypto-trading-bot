# funding_carry verdict: REJECT

**Criterion (edge-research-battery design §5, paraphrased; every threshold below is read live from `edge_lab.config`, not transcribed):** Gate 1 gross edge ≥ 2× the taker round-trip cost; Gate 2 DSR ≥ 0.95 deflated at a num_trials floor of 16, pooled profit factor > 1.0, and positive net expectancy in ≥ 70% of CPCV paths. A variant must clear both gates; the candidate passes if any variant does.

- date: 20260817
- universe pin: 2026-08-17 (top_n=30, min_age_days=730, 30 symbols)
- variants scored: 2

## Variants

| variant | n_trades | gross_edge_bps | cost_bps_taker | ratio_taker | gate1 | dsr | pooled_pf | positive_path_frac (of 45) | n_paths_valid | gate2 |
|---|---|---|---|---|---|---|---|---|---|---|
| thresh_1.5x | 201 | 59.3973 | 30.0510 | 1.977 | KILL | n/a | n/a | n/a | n/a | FAIL |
| thresh_2x | 120 | 79.3988 | 30.5000 | 2.603 | PASS | 0.0000 | 1.1536 | 0.4444 | 45 | FAIL |

`n/a` = not computed (the gate never ran) or NaN (CPCV could not split the series). `inf` = `pooled_pf` with zero losing path-days — read it against `n_trades` in the same row; it is a degenerate sample, not infinite profit.

`positive_path_frac` is a fraction of **all 45 = C(10, 2) combination-paths**. Those paths overlap — each sample lands in every combination that does not hold its group out — so they are correlated windows, not 45 independent trials. `n_paths_valid` counts only the variance-valid subset kept for the Sharpe distribution. Two different denominators: never average or compare them directly.

## Gate 2 detail

- **thresh_2x**
  - return window: 2024-09-23 00:00 UTC -> 2026-08-16 00:00 UTC (693 calendar days, flat days included at 0.0)
  - path Sharpe mean -0.0177 / std 0.0983 over 45 variance-valid paths
  - label horizon: 10 days (CPCV purge/embargo)
  - FAIL: dsr 0.0000 below threshold 0.95
  - FAIL: positive_path_frac 0.4444 below 0.7

## Gate 0 — data sanity

```
BTCUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
BTCUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ETHUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
ETHUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
SOLUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
SOLUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
XRPUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
XRPUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
PORTALUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
PORTALUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
ZECUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
ZECUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ACEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=5377
ACEUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=5377
ADAUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
ADAUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
DOGEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
DOGEUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
WLDUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
WLDUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
LINKUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
LINKUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
1000PEPEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
1000PEPEUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ONDOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
ONDOUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
NEARUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
NEARUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
SUIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
SUIUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ENAUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
ENAUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
BNBUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
BNBUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
TAOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
TAOUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
AVAXUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
AVAXUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
HFTUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2230
HFTUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2230
UNIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
UNIUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
XMRUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
XMRUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ONGUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
ONGUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
APTUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
APTUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ETHFIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3924
ETHFIUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=3924
AAVEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
AAVEUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
ARBUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
ARBUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
LTCUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
LTCUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
OPUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
OPUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
BICOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2188
BICOUSDT [240] PASS n_bars=2186 gaps=0 funding_ok=True funding_n=2188
pinned=30 kept_daily=30 kept_h4=30 funding_series=30 dropped_daily=[] dropped_h4=[]
```

## Caveats

- Survivorship: the universe is today's top-30 by turnover with a ≥2y listing filter; assets that died before the pin date are absent. This biases results optimistic by an unmeasured amount.
- num_trials floor = 16: 8 battery variants + 8 historical strategy families. DSR is deflated against that floor, not against the CPCV path count, which would understate the search space actually spent on this repo.
- (xs_momentum) Eligibility requires a bar at the exit Monday, so a symbol that stops trading mid-week is never entered that week. This is survivorship-lite and is pinned by design — it is not strictly causal on eligibility.
- (all candidates) Variant warm-up asymmetry: variants of one candidate are NOT scored over a common window. Each variant's Gate 2 return series starts at its own first trade and runs to the end of the data, so a long-lookback variant — which cannot trade until its lookback fills — is measured on a shorter, later series covering a different slice of market regime than a short-lookback one. This cuts BOTH ways and the optimistic direction is the one to watch: every day before a variant's first trade is excluded outright, so a rarely-firing variant is scored only on its post-first-trade stretch and is FLATTERED relative to a common-window measure — on Sharpe, by roughly sqrt(n_common / n_measured). Against that, fewer samples widen the DSR standard-error term, so long lookbacks face a marginally higher bar. Compare variants' verdicts, not their Sharpes. Within a window, flat days after the first trade are kept at 0.0, so idle capital is charged rather than skipped.
- (funding_carry) Per-symbol funding coverage ends at its own date, which need not match the candle end-date. The freshness rule then makes the trade set depend on each feed's end offset. Separately, the entry threshold assumes 9 settlements (a 3-day minimum hold at 8h cadence) while realized holds vary — where a hold is shorter than 3 days the threshold was conservative, i.e. it demanded more edge than the trade collected.
- (Gate 2) DSR is computed on the full return series using a variance derived from the out-of-sample CPCV path Sharpes. It is therefore not a pure out-of-sample statistic. CPCV paths also share training data, so the path Sharpes are correlated trials — mildly anticonservative, the same direction as the H4 verdict's documented caveat.
