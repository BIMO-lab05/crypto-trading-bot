# Leakage + survivorship tests

Three tests every new indicator/strategy must pass before backtest.

## 1. Prefix-stability test (look-ahead detector)

The output of an indicator at bar `t` must not change when later bars are added or removed.

```python
import numpy as np
import pandas as pd
from app.indicators.your_new_indicator import compute   # or wherever

def test_prefix_stability(sample_ohlcv: pd.DataFrame):
    full = compute(sample_ohlcv)
    half = compute(sample_ohlcv.iloc[: len(sample_ohlcv) // 2])
    n = len(half)
    pd.testing.assert_series_equal(
        full.iloc[:n].reset_index(drop=True),
        half.reset_index(drop=True),
        check_names=False,
    )
```

If this fails, your indicator depends on future bars. Common culprits: centered moving averages, rolling `.apply` with non-causal windows, fitting on the whole series and using fitted params for early bars.

## 2. Bar-boundary test (signal timing)

Signals at bar `t` must use only data with timestamp `<= t`. Strategies fill at bar `t+1` open (or current bar close if event-driven).

```python
def test_signal_no_future_data(strategy, sample_ohlcv):
    # snapshot data up to bar i
    for i in range(50, len(sample_ohlcv)):
        partial = sample_ohlcv.iloc[: i + 1]
        signal_partial = strategy.generate_signal_sync(partial).iloc[-1]
        # recompute on full series, take same bar
        full = sample_ohlcv
        signal_full = strategy.generate_signal_sync(full).iloc[i]
        assert signal_partial == signal_full, f"signal at bar {i} drifted when future was visible"
```

## 3. Survivorship and listing-bias check (universe)

Validated symbol set is fixed: `SOLUSDT, BNBUSDT, ADAUSDT, BTCUSDT, ETHUSDT`. Don't filter the universe by "currently profitable" coins or coins still trading today — that's survivorship. If you want to expand the universe, expand it for the entire backtest window, including pairs that later got delisted on Bybit.

If your strategy quietly drops a symbol mid-backtest because of insufficient liquidity, that decision must be made on data available *at that bar*, not in hindsight.

## 4. Train/validation/test discipline

If you tune any parameter (period, threshold, weight) by looking at backtest output, that backtest is your *training* set. Hold out the most recent 25% of the period as a test set you never tune against. Walk-forward only.

Forbidden patterns:
- Picking RSI period by sweeping {7..21} on the same window you then report Sharpe over.
- Optimizing stops on the same window used for the headline equity curve.
- "Just one more tweak" after seeing the test-set number — that promotes test set to train set.

## 5. Deflated Sharpe Ratio

For ML / signal-quality changes, headline metric is DSR (Bailey & Lopez de Prado), not raw Sharpe. Acceptance gate: DSR > 0.95.

Quick approximation:

```python
import numpy as np

def deflated_sharpe(sr_obs, n_trials, sr_std=1.0, n_obs=252):
    # adjusts for selection bias from trying many strategies
    from scipy.stats import norm
    expected_max_sr = sr_std * (
        (1 - np.euler_gamma) * norm.ppf(1 - 1.0 / n_trials)
        + np.euler_gamma * norm.ppf(1 - 1.0 / (n_trials * np.e))
    )
    z = (sr_obs - expected_max_sr) * np.sqrt(n_obs - 1)
    return float(norm.cdf(z))
```

`n_trials` is the honest count of all strategy variants you tried (not just the one you're reporting).
