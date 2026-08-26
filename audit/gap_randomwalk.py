"""Run the unmodified engine on GBM noise. Profit on noise = defect, not edge."""

import sys

import numpy as np
import pandas as pd

from audit._harness import load_candles, make_engine, baseline_strategy, result_summary

real = load_candles()
log_ret = np.log(real["close"] / real["close"].shift(1)).dropna()
sigma = float(log_ret.std())
n = len(real)

pnls = []
for seed in range(20):
    rng = np.random.default_rng(seed)
    steps = rng.normal(
        -0.5 * sigma**2, sigma, n
    )  # Ito correction: drift-free in price space
    close = float(real["close"].iloc[0]) * np.exp(np.cumsum(steps))
    intrabar = np.abs(rng.normal(0.0, sigma, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + intrabar)
    low = np.minimum(open_, close) * (1 - intrabar)
    vol = np.full(n, float(real["volume"].median()))
    df = pd.DataFrame(
        {
            "timestamp": real["timestamp"].values,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
        }
    )
    res = make_engine().run_backtest(df, baseline_strategy, f"gbm-{seed}")
    s = result_summary(res)
    pnls.append(s["pnl"])
    print(f"seed={seed} trades={s['trades']} pnl={s['pnl']}")

mean_pnl = float(np.mean(pnls))
positive = sum(1 for p in pnls if p > 0)
# Consistent positive expectancy on noise (binomial p<0.05 for >=15/20) fails.
ok = mean_pnl <= 0 or positive < 15
print(
    f"RESULT: randomwalk={'PASS' if ok else 'FAIL'} mean_pnl={mean_pnl:.4f} positive_seeds={positive}/20"
)
sys.exit(0 if ok else 1)
