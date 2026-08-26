"""Distribution of realized loss as fraction of equity; stop distance vs 14-bar ATR at entry."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from audit._harness import load_candles, make_engine, baseline_strategy

data = load_candles()
eng = make_engine()
res = eng.run_backtest(data, baseline_strategy, "risk")

# ATR(14) series aligned to data
tr = pd.concat(
    [
        data["high"] - data["low"],
        (data["high"] - data["close"].shift(1)).abs(),
        (data["low"] - data["close"].shift(1)).abs(),
    ],
    axis=1,
).max(axis=1)
atr = tr.rolling(14).mean()
ts_to_atr = dict(zip(data["timestamp"], atr))

# Reconstruct equity before each trade by replaying the equity delta sequence.
equity = res.initial_capital
loss_fracs, stop_atr_ratios = [], []
for t in res.trades:
    if t.profit_loss < 0:
        loss_fracs.append(-t.profit_loss / equity)
    if t.stop_loss is not None:
        a = ts_to_atr.get(t.entry_time)
        if a and a > 0:
            stop_atr_ratios.append(abs(t.entry_price - t.stop_loss) / a)
    equity += (
        t.profit_loss
    )  # entry fee already reduced capital; approximation noted in output

loss_fracs = np.array(loss_fracs) * 100
inside_1atr = (
    100.0 * np.mean([r < 1.0 for r in stop_atr_ratios]) if stop_atr_ratios else 0.0
)
p95 = float(np.percentile(loss_fracs, 95)) if len(loss_fracs) else 0.0
ok = p95 <= 10.0

print(
    f"losing trades={len(loss_fracs)} loss%%equity mean={loss_fracs.mean():.3f} p95={p95:.3f} max={loss_fracs.max():.3f}"
    if len(loss_fracs)
    else "no losing trades"
)
print(
    f"stops inside 1 ATR: {inside_1atr:.1f}% of {len(stop_atr_ratios)} trades (noise-stop risk if high)"
)
print(
    "note: equity replay ignores intra-trade funding/entry-fee timing; error < one fee per trade"
)
print(
    f"RESULT: risk={'PASS' if ok else 'FAIL'} loss_p95_pct={p95:.3f} configured_cap_pct=10.0 stops_inside_1atr_pct={inside_1atr:.1f}"
)
sys.exit(0 if ok else 1)
