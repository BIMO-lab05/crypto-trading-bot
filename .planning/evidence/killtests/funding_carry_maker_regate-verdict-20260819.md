# funding_carry_maker_regate verdict: REJECT

**Criterion (edge-research-battery design §5, paraphrased; every threshold below is read live from `edge_lab.config`, not transcribed):** Gate 1 gross edge ≥ 2× the taker round-trip cost; Gate 2 DSR ≥ 0.95 deflated at a num_trials floor of 30, pooled profit factor > 1.0, and positive net expectancy in ≥ 70% of CPCV paths. A variant must clear both gates; the candidate passes if any variant does.

- date: 20260819
- universe pin: 2026-08-17 (top_n=30, min_age_days=730, 30 symbols)
- variants scored: 1

## Variants

| variant | n_trades | gross_edge_bps | cost_bps_taker | ratio_taker | gate1 | dsr | pooled_pf | positive_path_frac (of 45) | n_paths_valid | gate2 |
|---|---|---|---|---|---|---|---|---|---|---|
| thresh_2x_maker | 89 | -364.6800 | 30.5444 | -11.939 | KILL | n/a | n/a | n/a | n/a | FAIL |

`n/a` = not computed (the gate never ran) or NaN (CPCV could not split the series). `inf` = `pooled_pf` with zero losing path-days — read it against `n_trades` in the same row; it is a degenerate sample, not infinite profit.

`positive_path_frac` is a fraction of **all 45 = C(10, 2) combination-paths**. Those paths overlap — each sample lands in every combination that does not hold its group out — so they are correlated windows, not 45 independent trials. `n_paths_valid` counts only the variance-valid subset kept for the Sharpe distribution. Two different denominators: never average or compare them directly.

## Gate 0 — data sanity

```
BTCUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
BTCUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
BTCUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ETHUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
ETHUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
ETHUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
SOLUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
SOLUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
SOLUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
XRPUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
XRPUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
XRPUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
PORTALUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
PORTALUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
PORTALUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
ZECUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
ZECUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
ZECUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ACEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=5381
ACEUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=5381
ACEUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=5381
ADAUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
ADAUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
ADAUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
DOGEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
DOGEUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
DOGEUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
WLDUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
WLDUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
WLDUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
LINKUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
LINKUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
LINKUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
1000PEPEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
1000PEPEUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
1000PEPEUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ONDOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
ONDOUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
ONDOUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
NEARUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
NEARUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
NEARUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
SUIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
SUIUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
SUIUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ENAUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
ENAUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
ENAUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
BNBUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
BNBUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
BNBUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
TAOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
TAOUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
TAOUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
AVAXUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
AVAXUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
AVAXUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
HFTUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2232
HFTUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2232
HFTUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2232
UNIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
UNIUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
UNIUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
XMRUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
XMRUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
XMRUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ONGUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
ONGUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
ONGUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
APTUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
APTUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
APTUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ETHFIUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=3928
ETHFIUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=3928
ETHFIUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=3928
AAVEUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
AAVEUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
AAVEUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
ARBUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
ARBUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
ARBUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
LTCUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
LTCUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
LTCUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
OPUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
OPUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
OPUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
BICOUSDT [D] PASS n_bars=729 gaps=0 funding_ok=True funding_n=2190
BICOUSDT [240] PASS n_bars=2189 gaps=0 funding_ok=True funding_n=2190
BICOUSDT [60] PASS n_bars=8759 gaps=0 funding_ok=True funding_n=2190
pinned=30 kept_daily=30 kept_h4=30 kept_h1=30 funding_series=30 dropped_daily=[] dropped_h4=[] dropped_h1=[]
```

## Caveats

- Survivorship: the universe is today's top-30 by turnover with a ≥2y listing filter; assets that died before the pin date are absent. This biases results optimistic by an unmeasured amount.
- num_trials floor = 30: this is the ledger-derived effective floor — max(NUM_TRIALS_FLOOR=16, distinct trials already spent), where NUM_TRIALS_FLOOR is the static 8 battery variants + 8 historical strategy families composition, not the number shown here. DSR is deflated at num_trials = max(effective_floor, n_paths) = 30 for this run — the floor binds only when it exceeds the CPCV path count, not unconditionally.
- (xs_momentum) Eligibility requires a bar at the exit Monday, so a symbol that stops trading mid-week is never entered that week. This is survivorship-lite and is pinned by design — it is not strictly causal on eligibility.
- (all candidates) Variant warm-up asymmetry: variants of one candidate are NOT scored over a common window. Each variant's Gate 2 return series starts at its own first trade and runs to the end of the data, so a long-lookback variant — which cannot trade until its lookback fills — is measured on a shorter, later series covering a different slice of market regime than a short-lookback one. This cuts BOTH ways and the optimistic direction is the one to watch: every day before a variant's first trade is excluded outright, so a rarely-firing variant is scored only on its post-first-trade stretch and is FLATTERED relative to a common-window measure — on Sharpe, by roughly sqrt(n_common / n_measured). Against that, fewer samples widen the DSR standard-error term, so long lookbacks face a marginally higher bar. Compare variants' verdicts, not their Sharpes. Within a window, flat days after the first trade are kept at 0.0, so idle capital is charged rather than skipped.
- (funding_carry) Per-symbol funding coverage ends at its own date, which need not match the candle end-date. The freshness rule then makes the trade set depend on each feed's end offset. Separately, the entry threshold assumes 9 settlements (a 3-day minimum hold at 8h cadence) while realized holds vary — where a hold is shorter than 3 days the threshold was conservative, i.e. it demanded more edge than the trade collected.
- (Gate 2) DSR is computed on the full return series using a variance derived from the out-of-sample CPCV path Sharpes. It is therefore not a pure out-of-sample statistic. CPCV paths also share training data, so the path Sharpes are correlated trials — mildly anticonservative, the same direction as the H4 verdict's documented caveat.

## Maker fill detail

- maker-mode: entry fills only on strict next-adjacent-bar trade-through; gapped bars = missed; missed entries dropped and counted; slippage table unchanged
- representative variant: thresh_2x (selected pre-hoc: ratio_taker=2.603 (best of 5))
- trades before fill: 120
- missed (unfilled): 31
- fill_rate: 0.7416666666666667
- trades scored (post-fill): 89
- Gate 1 basis: MAKER (ratio_maker >= hurdle_multiple), computed in this runner from screen_trades' returned maker columns (cost_bps_maker/net_maker/ratio_maker) — screen.py's own `verdict` field is TAKER-only and is not read here; screen.py was not modified.
