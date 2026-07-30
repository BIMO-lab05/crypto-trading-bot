---
type: component
status: current
created: 2026-07-30
updated: 2026-07-30
tags: [component, trading-engine, multi-timeframe, signals, aggregation]
---

# Multi-Timeframe Blender

Cross-timeframe confirmation layer in [[../modules/trading-engine|trading-engine]] (Phase 2). Fetches signals for 15m/60m/240m concurrently, computes a weighted consensus, classifies alignment, and scales the primary (60m) signal's confidence. Feeds the [[Volume-Profile]] path, which multiplies its own modifier on top.

> Merged from `services/trading-engine/MULTI_TIMEFRAME_IMPLEMENTATION.md` on 2026-07-30.

## Parameters

| Timeframe | Role | Weight |
|---|---|---|
| 15m | entry/exit timing | 0.20 |
| 60m | primary signal | 0.50 |
| 240m | trend confirmation | 0.30 |

Consensus score = Σ(score×weight)/Σ(weight); BUY ≥ +0.3, SELL ≤ −0.3, else HOLD.

**Alignment tiers → confidence modifier:**

| Tier | Condition | Modifier |
|---|---|---|
| VERY_STRONG | all 3 agree BUY/SELL | 1.2x |
| STRONG | 2 agree + 1 HOLD | 1.1x |
| MODERATE | 2 agree + 1 disagrees | 1.0x |
| WEAK | no consensus / all HOLD | 0.8x |
| CONTRADICTORY | direct BUY-vs-SELL opposition | 0.6x |

+5% bonus when 60m and 240m align (non-HOLD). Modifier clamped to **0.5x–1.3x**; final confidence clamped to [0,1]. Env: `ENABLE_MULTI_TIMEFRAME`, `MULTI_TIMEFRAME_INTERVALS=15,60,240`, `PRIMARY_INTERVAL=60`, `MULTI_TF_MIN_MODIFIER=0.5`, `MULTI_TF_MAX_MODIFIER=1.3`.

## Integration points

- `app/aggregation/multi_timeframe.py` — `MultiTimeframeAnalyzer`, `TimeframeSignal`, `MultiTimeframeAnalysis`
- `app/signal_aggregator.py` — `get_trading_signal_multi_timeframe(symbol, primary_interval, timeframes)`; results in `signal.metadata["multi_timeframe"]` (`alignment_strength`, `confidence_modifier`, `reasoning`, `agreement_pct`)
- `app/auto_trader.py` — auto-trader calls the MTF method in its poll loop
- Downstream gates unchanged: min confidence 0.6 and min consensus still apply **after** the modifier

## Gotchas

- **All-HOLD gets penalized as WEAK (0.8x)** — market indecision is treated like disagreement; slow trend formations may be missed.
- 3x indicator fetches per signal (concurrent via asyncio, ~2–3s vs ~1s single-timeframe); 240m history can be sparse for newer listings — fallback drops to fewer timeframes, and <2 available timeframes falls back to single-timeframe; analysis failure passes the primary signal through unmodified.
- The source doc's impact numbers (−50% false positives, +25% quality signals) were **projections, not measurements**; pre-2026-07-28 P&L evidence is measurement-corrupted, so treat them as history only.
- Since 2026-07-28 consensus counts directional votes only (aggregator-side fix) — older examples mixing HOLD into consensus counts are stale.
