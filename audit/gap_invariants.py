"""Invariant A (signal→fill lag) and Invariant B (intrabar SL/TP ambiguity)."""

from audit._harness import baseline_strategy, load_candles, make_engine

data = load_candles()

TARGET_IDX = 100


def one_shot(row, position, idx, data):
    if idx == TARGET_IDX and position is None:
        p = float(row["close"])
        return {"action": "BUY", "stop_loss": p * 0.97, "take_profit": p * 1.06}
    return None


eng = make_engine()
res = eng.run_backtest(data, one_shot, "invariant-probe")
bar = data.iloc[TARGET_IDX]
trade = res.trades[0]
# Engine applies slippage on top of the fill base price; recover the base.
base = trade.entry_price / (1 + eng.slippage) if eng.slippage_mode == "fixed" else None
same_bar_close_fill = (
    abs(trade.entry_price - float(bar["close"])) / float(bar["close"]) < 0.01
)
inv_a = (
    "FAIL" if same_bar_close_fill and trade.entry_time == bar["timestamp"] else "PASS"
)
print(f"Invariant A: {inv_a}")
print(f"  signal bar t={TARGET_IDX} close={bar['close']} ts={bar['timestamp']}")
print(f"  fill price={trade.entry_price} entry_time={trade.entry_time}")
print(
    "  static cite: backtest_engine.py:282 (price=row close), :303 (signal from row t), :308 (executed same iteration)"
)

# Invariant B: count bars during open positions where both SL and TP fell inside [low, high].
res2 = eng.run_backtest(data, baseline_strategy, "baseline")
ambiguous = 0
for t in res2.trades:
    if t.stop_loss is None or t.take_profit is None:
        continue
    window = data[
        (data["timestamp"] >= t.entry_time) & (data["timestamp"] <= t.exit_time)
    ]
    both = (
        ((window["low"] <= t.stop_loss) & (window["high"] >= t.take_profit))
        if t.order_type.value == "BUY"
        else ((window["high"] >= t.stop_loss) & (window["low"] <= t.take_profit))
    )
    if both.any():
        ambiguous += 1
print(
    "Invariant B resolution: SL checked before TP (backtest_engine.py:350-361) — worst-case for the trade, conservative."
)
print(
    "  BUT stop/TP fills at exact level even when the bar gapped past it (backtest_engine.py:462-465) — optimistic on gaps."
)
print(
    f"RESULT: invariant_a={inv_a} invariant_b=worst_case ambiguous_trades={ambiguous} total_trades={res2.total_trades}"
)
