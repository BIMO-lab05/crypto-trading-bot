"""Invert baseline signals. Inverted profit >> costs = sign/shift defect; ~-costs = no edge either way."""

import sys

from audit._harness import load_candles, make_engine, baseline_strategy, result_summary

data = load_candles()


def inverted(row, position, idx, data):
    sig = baseline_strategy(row, position, idx, data)
    if not sig:
        return None
    p = float(row["close"])
    if sig["action"] == "BUY":
        return {"action": "SELL", "stop_loss": p * 1.03, "take_profit": p * 0.94}
    return {"action": "BUY", "stop_loss": p * 0.97, "take_profit": p * 1.06}


base = make_engine().run_backtest(data, baseline_strategy, "base")
inv = make_engine().run_backtest(data, inverted, "inverted")

fee = make_engine()._effective_fee_rate("MARKET")
est_costs = sum(
    t.position_size * (t.entry_price + t.exit_price) * fee for t in inv.trades
)

defect = inv.total_profit_loss > 2 * est_costs  # materially larger than total costs
print(f"base: {result_summary(base)}")
print(f"inverted: {result_summary(inv)}")
print(f"estimated round-trip fee cost of inverted run: {est_costs:.4f}")
verdict = "SIGN_DEFECT" if defect else "no_edge_either_way"
print(
    f"RESULT: signcheck={verdict} base_pnl={base.total_profit_loss:.4f} inverted_pnl={inv.total_profit_loss:.4f} est_costs={est_costs:.4f}"
)
sys.exit(1 if defect else 0)
