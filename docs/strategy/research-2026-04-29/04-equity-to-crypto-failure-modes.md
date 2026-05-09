# Failure Modes: Equity Strategies Ported to Crypto

> Research agent output, 2026-04-29. Source for synthesis task #8.

## Ranked by blast radius for a retail bot

**1. Survivorship bias in factor backtests (highest blast radius)**
Crypto factor papers routinely backtest on token universes that exclude dead coins. LUNA was a top-10 asset in April 2022; any momentum/value backtest using "currently-listed top-50" universes silently drops the $50B wipeout in May 2022 (Briola et al. 2022, "Anatomy of a Stablecoin's failure"). Liu & Tsyvinski's three-factor model (2022 *J. Finance*) requires constituents survive a $1M market-cap filter, which already prunes failures. A retail bot that re-fits Fama-MacBeth on Coingecko's current universe will overstate momentum Sharpe by 30-50%.

**2. Counterparty/custody risk (no equity analog)**
FTX (Nov 2022) destroyed live PnL for funds running market-neutral basis trades. Galois Capital lost ~50% of AUM held as collateral; Ikigai disclosed "majority" of fund stuck. A backtested Sharpe-2 funding-rate carry strategy realized a -100% return at the exchange level. Equity prime brokers fail rarely and SIPC insures; crypto venues fail every cycle (Mt Gox 2014, QuadrigaCX 2019, FTX 2022). See Aramonte et al., BIS Bulletin No. 69.

**3. Funding-rate regime breaks delta-neutral and pairs trading**
Perpetual swap funding (BitMEX-style 8-hour resets) is a hidden fee/income stream absent in equity-pairs trading. BitMEX Q3 2025 derivatives report: funding positive >92% of Q3 2025, then flips violently during deleveraging. Equity stat-arb code that ignores funding either bleeds 10-30% annually paying it (long-perp legs) or has phantom alpha (short-perp legs collecting it).

**4. Vol regime + jump risk breaks Sharpe-targeted sizing**
Crypto kurtosis is severe; jump component dominates total variance more than in equities (Scaillet et al., extreme-tail studies). A vol-targeted equity momentum bot ported naively will under-react to gap risk: a Sharpe-1.5 strategy can survive a 70% drawdown (arXiv 2404.04962). Kelly/vol-target sizing calibrated on SPX gets blown up by a single weekend halving-cycle gap.

**5. Weekend/24-7 microstructure breaks signal definitions**
Equity "close-to-close" returns and "overnight gap" effects don't exist; weekend liquidity drops ~30% (Amberdata depth study) and altcoin weekend momentum *exceeds* weekday, inverting the equity weekend-effect literature (ACR Journal, "Weekend Effect in Crypto Momentum"). Any feature engineered on equity calendar conventions (Mon-effect, Friday-close) maps to noise.

**6. No fundamental anchor breaks value factor**
Crypto has no book value, earnings, or dividend yield. "Value" proxies (NVT, MVRV, P/S for tokens with revenue) are unstable and untested across regimes. Wei (2024) shows fundamental factors in crypto are "lucky factors" with weak out-of-sample power.

**7. Retail-dominated flow + fragmentation (lower blast radius for small bots)**
Bid-ask cost asymmetric: a $500 BTC trade is essentially free; a $15k small-cap altcoin trade burns 50-150bps (Blofin slippage analysis). For a retail bot under ~$100k AUM trading top-20 names this is manageable; it kills institutional capacity but not retail viability.

**8. Short data history (~10 yrs vs 70-100 yrs equities)**
Insufficient regime samples. Two halving cycles, one ZIRP regime, one tightening cycle. Any factor "discovered" is at high risk of being a single-regime artifact (Liu, Tsyvinski & Wu 2022 caveat their own results on this).

## Equity strategies that DO port well

- **Time-series momentum / trend-following** (1-4 week horizon). Liu & Tsyvinski (2022) and ACFR replication confirm robust TSMOM in BTC/ETH; mirrors Moskowitz-Ooi-Pedersen (2012) findings.
- **Cross-sectional momentum on top-quintile market cap only.** The signal exists for top ~2% by mcap; vanishes/inverts for the long tail (Quantitative Finance 2023, "Cryptocurrency factor momentum").
- **Vol-managed momentum** (Barroso-Santa-Clara style): explicitly mitigates the crypto momentum-crash problem documented in Springer FMPM 2025 ("Cryptocurrency momentum has (not) its moments").
- **Carry/basis trades** — port natively as funding-rate arbitrage; this is the best-documented crypto-native analog of FX/equity carry.

## Equity strategies that do NOT port

- **Book-value / earnings-yield value (Fama-French HML).** No denominator exists.
- **Low-volatility / betting-against-beta.** Crypto beta dispersion is unstable and dominated by idiosyncratic jumps; BAB has no documented out-of-sample edge.
- **Equity pairs trading on cointegration.** Cointegration is non-stationary across halving cycles and exchange listings; tokens get delisted or fork.
- **Short-interest / borrow-cost factors.** Crypto borrow markets are venue-specific and dwarfed by perp funding; the equity short-squeeze mechanism (regulated locate, FTD) doesn't apply.
- **Post-earnings-announcement drift / accruals.** No earnings.
- **Calendar effects (Monday, January, turn-of-month).** Inverted or absent in 24/7 markets.

## Sources

- Liu, Tsyvinski, Wu — Common Risk Factors in Cryptocurrency, *Journal of Finance* 2022
- Liu & Tsyvinski — Risks and Returns of Cryptocurrency, *RFS* 2021
- Cryptocurrency factor momentum — *Quantitative Finance* 23(12), 2023
- Cryptocurrency momentum has (not) its moments — *FMPM* 2025
- Moskowitz, Ooi, Pedersen — Time Series Momentum, 2012 *JFE*
- Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market — ACFR
- Briola et al. — Anatomy of a Stablecoin's failure: Terra-Luna (arXiv 2207.13914)
- Aramonte et al. — BIS Bulletin No 69, Crypto shocks and retail losses
- Easley et al. — Microstructure and Market Dynamics in Crypto Markets
- Weekend Effect in Crypto Momentum — *Advances in Consumer Research*
- BitMEX Q3 2025 Derivatives Report — funding regimes
- A Comparison of Cryptocurrency Volatility — arXiv 2404.04962
- FTX Collapse and systemic risk spillovers — *Finance Research Letters*
- Wei (2024) — Cryptocurrencies and Lucky Factors, *IJFE*
- Blofin — Slippage in crypto trading
- Amberdata — Rhythm of Liquidity
