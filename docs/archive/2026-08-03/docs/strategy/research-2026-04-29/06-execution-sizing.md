# Execution & Sizing Research: Retail Crypto Bot (Bybit, SOL/BNB/ADA, hourly bars)

> Research agent output, 2026-04-29. Source for synthesis task #8.

## Ranked techniques by measured PnL impact

| # | Technique | Estimated impact | Retail-viable |
|---|---|---|---|
| 1 | **Maker (post-only limit) vs taker on perps** | ~3.5 bps saved per fill = ~7 bps round-trip on Bybit perp (taker 0.055% vs maker 0.020%); on spot it is 0 bps savings (both 0.1%). At 200 round-trip trades/yr that is ~140 bps/yr of return that flips from drag to neutral. | YES on perp; NO on spot |
| 2 | **Volatility-/ATR-based position sizing vs naive fixed-notional** | Empirically equalises risk per trade across regimes. Balsara (1992) and follow-up backtests show fixed-fractional/ATR delivers materially lower max drawdown (often 30-50% lower) and better Calmar than fixed-notional, even when raw return is similar. Half-Kelly captures ~75% of optimal growth at ~50% of full-Kelly drawdown. | YES |
| 3 | **Stop-loss design: stop-market with explicit slippage cap, not naked stop-limit** | Flash-crash data: stop-market fills routinely slip 5-10% on retail venues during fast moves; naked stop-limits frequently do not fill at all and turn a planned -2% loss into a -20% loss. Bybit market orders are internally converted to IOC limits with a slippage threshold (mark-price-relative), which is the right primitive to use. | YES |
| 4 | **Funding-rate awareness on perp entries** | Funding settles every 8h on Bybit (default for SOL/BNB/ADA-USDT perps). Rate is bounded ~±0.05% per settlement plus interest, so worst-case ~0.15%/day = ~55%/yr drag if persistently long into positive funding. Skip-the-snapshot or flip-to-spot when \|funding\| > ~0.03%/8h has measurable PnL benefit on directional holds longer than one settlement. | YES |
| 5 | **Market vs limit at retail size on top-3 alts** | SOL/BNB/ADA-USDT on Bybit are top-tier liquid; spreads are typically 1-2 bps and a $10k market order absorbs with negligible price impact (well under 5 bps). Folklore says "always use limit"; measured difference on these symbols is ~1-3 bps per fill, dwarfed by the 35 bps maker/taker delta. **Conclusion: choose maker vs taker for fee economics, not slippage.** | YES |
| 6 | **TWAP / VWAP / iceberg slicing** | Documented benefit kicks in once order > ~3% of period volume (2-10 bps savings). For $100-$10k orders on SOL/BNB/ADA hourly bars (per-bar volume in millions of USD), order is <<0.1% of volume. **Confirmed: not worth implementing.** | NO – skip |

## Bybit-specific items to action (or skip)

1. **Use `timeInForce=PostOnly` on perp entries when not time-urgent.** Confirmed in the v5 create-order docs: PostOnly cancels rather than crosses, guaranteeing the 0.020% maker rate. Add a "stale-quote" timeout (e.g., re-quote after N seconds or convert to taker if the signal is still valid) so the bot does not silently miss fills.

2. **Pull `GET /v5/market/funding/history`** (or instruments-info for the per-symbol interval) and gate perp entries on funding sign/magnitude. Formula: F = P + clamp(I - P, -0.05%, 0.05%); fee = position_value × funding_rate, settled every funding interval. Closing 1-2 minutes before settlement avoids the charge if the bot is otherwise indifferent to holding through it.

3. **Skip TWAP/VWAP/iceberg, skip RPI** (RPI is whitelisted to designated MMs per the v5 docs) and **skip the spot maker rebate game** (spot is flat 0.1%/0.1% on Bybit – no rebate to harvest).

## Common retail-bot execution mistakes that bleed alpha

- **Routing all orders as `Market` on perps.** Pays 0.055% taker every fill; on a strategy with 200 round-trips/yr this is ~22% of equity in fees alone.
- **Backtests with zero fees / zero slippage.** Forward-test PnL collapses; flagged as the #1 bot failure mode.
- **Naked stop-limit stops without a market-fallback.** During fast moves the limit does not fill, position keeps bleeding.
- **Ignoring funding when holding perps overnight.** Persistent funding can exceed strategy edge on hourly-bar systems.
- **Fixed-notional sizing across volatility regimes.** Causes oversize during high-vol and undersize during low-vol, inflating drawdowns vs ATR-scaled sizing.
- **Overtrading from over-fit signals.** Each extra round-trip costs ~7-20 bps; >50% of measured retail-bot underperformance traces to fee drag, not signal failure.

## Sources

- Bybit v5 API – Place Order, Funding Rate History
- Bybit – Introduction to Funding Rate, Funding Fee Calculation, Trading Fee Structure
- Bybit – Market Order with Slippage Tolerance
- Balsara — *Money Management Strategies for Futures Traders*
- Position sizing frameworks: fixed-fractional, ATR, Kelly-lite
- QuantPedia – Beware of Excessive Leverage / Kelly
- B2Prime – Flash Crash Trading Guide
- Paybis – How to Backtest a Crypto Bot
- ForTraders – Why Most Trading Bots Lose Money
- Empirica – TWAP threshold (3% of volume)
- Axon Trade – Maker/Taker Math
