# Retail-Scale Algo Trading Practitioners: Public Methodologies & Performance

> Research agent output, 2026-04-29. Source for synthesis task #8.

## Practitioner Table

| Practitioner | What/How They Trade | Disclosed Performance | Retail Viability | Crypto Applicability |
|---|---|---|---|---|
| **Andreas Clenow** (ACIES AM, Switzerland) | Diversified trend-following on 50+ futures markets; volatility-parity sizing; 20-day ATR risk units; momentum stock rotation ("Stocks on the Move") | Sharpe **0.7–0.9** historically across 50 vol-scaled futures (book disclosure 2002–2021); managed-futures industry-typical | High for futures-funded accounts (~$100k+); stock-momentum version works at any size | Partial — trend logic transfers; needs adaptation for 24/7 funding/regime shifts |
| **Ernie Chan** (QTS Capital, PredictNow.ai) | Multi-strategy (~10 sleeves): mean-reversion pairs, intraday stat-arb, vol-risk-premium; ML for regime gating | QTS doesn't publicly disclose Sharpe (reg-restricted); investor letters cite "superb 3yr Sortino"; books show backtests Sharpe 1–2 range pre-cost | High for stat-arb / pairs; ML overlay needs care | Moderate — pairs/cointegration on BTC vs alts is well-trodden retail territory |
| **Marcos López de Prado** (institutional, but methodology public) | Not a strategy author — **research methodology**: triple-barrier labels, fractional differentiation, purged k-fold CV, CPCV, Deflated Sharpe Ratio, meta-labeling | N/A (no retail-replicable strategy disclosed; methods only) | Methods retail-applicable; conclusions ("most ML strats are overfit") brutal but useful | High — directly relevant to ML-driven crypto bots like ours |
| **Robert Carver** (ex-AHL PM, trades own money) | Diversified systematic futures + equities; combined forecasts (trend + carry), volatility targeting (~25% annualized cap), continuous position sizing | Trades own capital w/ his published rules; book-quoted realistic Sharpe ~**0.5 single, ~1.0 diversified portfolio**; quarter-Kelly for negative-skew | Highest of all four — explicitly written for retail; full code at github.com/robcarver17/pysystemtrade | Moderate — futures-flavored but the framework (forecasts → vol-target → portfolio) is asset-agnostic |
| **Kevin Davey** (KJ Trading) | Short-term futures systems (ES, currencies); strict R&D pipeline (data mining → Monte Carlo → walk-forward → live) | World Cup Trading Championship: 1st 2006, 2nd 2005 & 2007; **148%, 107%, 112%** annual returns over those years (small-account, leveraged futures, single-year) | High in process; the headline returns are championship-context (high leverage, survivorship-flavored) — don't expect them | Low — futures bias, but his **system-development discipline** is the transferable part |

## Cross-cutting Consensus (≥3 agree)

1. **Volatility targeting / vol-parity position sizing** — Carver, Clenow, Chan, Davey all size positions inversely to recent realized vol (ATR or stdev). Static % risk-per-trade is dismissed.
2. **Diversification across uncorrelated bets is the only free lunch** — Clenow ("a lot of bets across many markets"), Carver (forecast diversification multiplier), Chan (10 strategy sleeves). Single-asset edges are tiny; portfolio Sharpe comes from breadth.
3. **Realistic Sharpe expectations: 0.5–1.0 single-strategy** — Carver, Clenow, López de Prado all explicitly call out that backtests showing Sharpe >2 are almost certainly overfit. Carver: "even good systems have low Sharpe."
4. **Backtest validation is the bottleneck, not signal discovery** — López de Prado (DSR, CPCV, PBO), Davey (Monte Carlo + walk-forward + incubation), Chan (cross-validation, white reality check). Consensus: if you didn't penalize for trial count, your Sharpe is fiction.
5. **Trend/momentum is robust; mean-reversion is fragile to regime change** — Clenow & Carver both run trend; Chan explicitly warns mean-reversion "decays" and needs continuous re-fitting. All agree pure mean-reversion is shorter-half-life than trend.

## Takeaways the bot doesn't already do (with practitioner backing)

1. **Replace the 9-indicator equal-weight vote with Carver-style continuous forecast combination** — each indicator outputs a scaled forecast in [-20, +20], then weighted-summed and capped. Carver shows this ~doubles diversification multiplier vs binary voting. Our voting throws away signal magnitude. *(Carver, Systematic Trading; pysystemtrade)*

2. **Compute Deflated Sharpe Ratio on the GRU ensemble's live results, not just R²/Dir.Acc.** — Memory says mean R²=0.995 / DirAcc=79%; that's a red flag for label leakage or trivial target (López de Prado would call this "the chart is too clean"). DSR penalizes for the number of model variants tried during selection. *(Bailey & López de Prado, 2014)*

3. **Add portfolio-level volatility targeting on top of per-symbol sizing** — currently risk is per-trade; Carver/Clenow size at the *portfolio* level so total realized vol hits a target (e.g., 20% annualized). When 5 symbols all signal long together in a correlated regime, per-trade caps don't prevent portfolio blow-up. This is the highest-leverage missing piece.

Skipped honorable mentions: Larry Connors (course-seller, fails the constraint), Nick Radge (Australian retail systematic, similar to Clenow but less disclosed), Jonathan Kinlay (institutional, less reproducible). r/algotrading "disclosed" results are mostly anecdote. Closest approachable retail crypto practitioner community is **Freqtrade** but no individual maintains a verified live track record there.

## Sources

- Andreas Clenow — *Following the Trend*; *Stocks on the Move*
- Meb Faber Ep. 188 — Clenow on trend following
- Ernie Chan — QTS Capital; *Algorithmic Trading*; *Machine Trading*
- Robert Carver — *Systematic Trading*; pysystemtrade (github.com/robcarver17/pysystemtrade)
- Kevin Davey — *Building Winning Algorithmic Trading Systems* (Wiley)
- López de Prado — *Advances in Financial Machine Learning*
- Bailey & López de Prado — Deflated Sharpe Ratio (SSRN 2460551)
- Freqtrade — open-source crypto bot (github.com/freqtrade/freqtrade)
