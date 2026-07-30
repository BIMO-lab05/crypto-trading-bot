---
type: component
status: current
created: 2026-07-30
updated: 2026-07-30
tags: [component, trading-engine, volume-profile, signals, strategy]
---

# Volume Profile

Volume-at-price analysis inside [[../modules/trading-engine|trading-engine]] (Phase 3). Computes **POC** (highest-volume price), **VAH**/**VAL** (value-area bounds, 70% of volume) from candle history, then picks a strategy from price position relative to those levels and adjusts the [[Multi-Timeframe-Blender]] signal's confidence and entry/exit levels.

> Merged from `services/trading-engine/VP_INTEGRATION_GUIDE.md` on 2026-07-30.

## Parameters

| Parameter | Default | Env var |
|---|---|---|
| Resolution (price levels) | 30 | `VP_RESOLUTION` |
| Value area | 70% | `VP_VALUE_AREA_PCT` |
| Lookback candles | 100 | `VP_LOOKBACK_CANDLES` |
| Global enable | off | `ENABLE_VOLUME_PROFILE` |

## Strategies

| Strategy | Trigger | SL / TP | Modifier |
|---|---|---|---|
| Mean reversion LONG | price < VAL, MTF BUY/HOLD | SL 0.5% below VAL; TP1 POC, TP2 VAH, TP3 VAH+1% | +15% bullish volume at VAL, +10% strong MTF |
| Mean reversion SHORT | price > VAH, MTF SELL/HOLD | mirror | same |
| POC breakout LONG/SHORT | break ±0.1% past POC, **requires STRONG/VERY_STRONG MTF** | SL 0.2% past POC; TPs at VAH/VAL ± value-area widths | +20% aligned breakout |
| Value-area trade | inside VA, clear MTF BUY/SELL | SL 1.5%; TP 2/4/6% | +5% volume support |

Conflicting signals apply a 0.8–0.9x penalty. Combined confidence = MTF confidence × MTF modifier × VP modifier, capped at 1.0.

## Integration points

- `app/volume_profile.py` — `VolumeProfileCalculator`, `VolumeProfile` dataclass
- `app/vp_strategy.py` — `VPStrategyAnalyzer`, `VPSignal`, `VPStrategyType`
- `app/signal_aggregator.py` — `get_trading_signal_with_vp(symbol, primary_interval, timeframes, enable_vp, vp_lookback)`; VP output lands in `signal.metadata["volume_profile"]` (strategy, poc, stop_loss, take_profit)
- `app/auto_trader.py` — `enable_volume_profile=True` constructor flag
- Candles fetched from technical-analysis (100 extra per signal)

## Gotchas

- **The VP path never traded before 2026-07-28**: `get_trading_signal_with_vp` raised `TypeError` on the `regime_analysis` kwarg (fixed in `signal_aggregator.py:1145–1183`). Any earlier "VP performance" claim is vacuous.
- Win-rate/R:R figures in the 2025-11 source guide (60–65% mean reversion etc.) were **design estimates, never measured** — and pre-2026-07-28 P&L is measurement-corrupted anyway.
- Needs 100+ candles; first signals after cold start are unreliable. Adds ~1–2s per signal.
- Only meaningful on high-volume pairs (BTC/ETH; test SOL); 15m VP is noisy — prefer 60m/240m.
- VP lags in fast markets; it is a confidence modifier, not a standalone signal.
