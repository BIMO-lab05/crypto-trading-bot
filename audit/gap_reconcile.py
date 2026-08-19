"""Backtest equity reconciliation to the cent + funding sign check for shorts."""

import sys

from audit._harness import load_candles, make_engine, baseline_strategy

data = load_candles()
eng = make_engine()

funding_events = []
orig_apply = eng._apply_funding


def logged_apply(price, time):
    before = eng.capital
    pos = eng.current_position
    orig_apply(price, time)
    if eng.capital != before:
        funding_events.append(
            {
                "time": time,
                "delta": eng.capital - before,
                "side": pos.order_type.value if pos else None,
            }
        )


eng._apply_funding = logged_apply

res = eng.run_backtest(data, baseline_strategy, "reconcile")

entry_fees = sum(
    t.position_size * t.entry_price * eng._effective_fee_rate("MARKET")
    for t in res.trades
)
funding_total = -sum(e["delta"] for e in funding_events)
expected = (
    res.initial_capital
    + sum(t.profit_loss for t in res.trades)
    - entry_fees
    - funding_total
)
residual = res.final_capital - expected
ok = abs(residual) <= 0.01

shorts_crossing = [
    t
    for t in res.trades
    if t.order_type.value == "SELL"
    and (t.exit_time - t.entry_time).total_seconds() >= 8 * 3600
]
short_funding = [e for e in funding_events if e["side"] == "SELL"]
if not shorts_crossing:
    funding_short = "no_short_crossed"
elif short_funding:
    funding_short = "charged"
else:
    funding_short = "not_charged"  # engine only charges longs (backtest_engine.py:236) — expected finding

print(
    f"initial={res.initial_capital} final={res.final_capital} expected={expected:.6f} residual={residual:.6f}"
)
print(
    f"trades={res.total_trades} entry_fees={entry_fees:.6f} funding_events={len(funding_events)} funding_total={funding_total:.6f}"
)
print(
    f"shorts crossing 8h: {len(shorts_crossing)}; short funding events: {len(short_funding)}"
)
print(
    "note: funding cadence is per-8-BARS not per-8-hours (backtest_engine.py:234); flat rate, not the historical CSVs in backtesting/data/funding/"
)
print(
    f"RESULT: reconcile={'PASS' if ok else 'FAIL'} residual={residual:.6f} funding_short={funding_short}"
)
sys.exit(0 if ok else 1)
