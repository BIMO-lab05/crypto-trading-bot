"""
Precision regression for the SQZMOM strategy's served price levels.

round(x, 2) on a sub-$1 asset is the 487d1bd defect class: ADA trades near
$0.60 with a 0.0001 tick, so two decimals quantize entry/stop/TP onto a
1-cent grid. A 2% stop lands 1.2 cents from entry, so rounding moves it by
up to 40% of the stop distance - and can put it on the wrong side of entry.

These assertions are two-sided: the served value must equal the computed
value exactly, and must NOT equal its 2dp rounding.
"""

import sys

sys.path.insert(
    0, str(__import__("pathlib").Path(__file__).resolve().parent.parent.parent)
)

import numpy as np
import pandas as pd
import pytest

from app.strategies.squeeze_momentum_strategy import SqueezeMomentumStrategy


def _ada_ohlc(n: int = 80, seed: int = 7) -> pd.DataFrame:
    """ADA-scale OHLCV frame: prices near $0.60, ranges near $0.003.

    `seed` is the SECOND parameter deliberately: Task 3 calls _ada_ohlc(120)
    positionally, so inserting seed first would silently change its frame.
    """
    rng = np.random.default_rng(seed)
    close = 0.60 + np.cumsum(rng.normal(0, 0.0015, n))
    return pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.0005, n),
            "high": close + np.abs(rng.normal(0.0015, 0.0005, n)),
            "low": close - np.abs(rng.normal(0.0015, 0.0005, n)),
            "close": close,
            "volume": rng.uniform(900, 1100, n),
        }
    )


def test_entry_price_keeps_full_precision():
    """entry_price is latest close; 2dp erases four significant digits on ADA."""
    df = _ada_ohlc()
    strategy = SqueezeMomentumStrategy()

    result = strategy.analyze(df)

    expected_entry = float(df["close"].iloc[-1])
    assert result["entry_price"] == pytest.approx(expected_entry, rel=1e-12), (
        f"entry_price {result['entry_price']} != close {expected_entry}; "
        "round(price, 2) destroyed ADA precision"
    )
    assert result["entry_price"] != round(expected_entry, 2), (
        "entry_price is still quantized to 2dp"
    )


def test_stop_and_target_keep_their_percentage_distance():
    """A 2% stop must stay 2% away, not snap to the nearest cent."""
    # seed=0 leaves the last bar in a released squeeze with rising positive
    # momentum, so a BUY actually fires. min_momentum_threshold must also be
    # scaled down: the 0.5 default is in PRICE units, and ADA-scale
    # sqz_momentum is ~1e-3, which can never clear it. The default seed=7
    # fixture returns HOLD ("Momentum too weak (-0.0026 < 0.5)") and HOLD
    # hard-sets stop_loss/take_profit to 0.0, so it cannot cover this.
    df = _ada_ohlc(seed=0)
    strategy = SqueezeMomentumStrategy(min_momentum_threshold=1e-9)

    result = strategy.analyze(df)
    assert result["action"] in ("BUY", "SELL"), (
        f"fixture produced no directional entry (action={result['action']}, "
        f"momentum={result['momentum']}); analyze() hard-sets stop_loss and "
        "take_profit to 0.0 on HOLD, so every assertion below would be vacuous"
    )

    entry = result["entry_price"]
    stop = result["stop_loss"]
    target = result["take_profit"]
    sign = 1 if result["action"] == "BUY" else -1

    realized_stop_pct = abs(entry - stop) / entry * 100
    assert realized_stop_pct == pytest.approx(strategy.stop_loss_pct, rel=1e-9), (
        f"stop is {realized_stop_pct:.4f}% from entry, configured "
        f"{strategy.stop_loss_pct}% - rounding moved the stop"
    )

    realized_tp_pct = abs(target - entry) / entry * 100
    assert realized_tp_pct == pytest.approx(strategy.take_profit_pct, rel=1e-9), (
        f"target is {realized_tp_pct:.4f}% from entry, configured "
        f"{strategy.take_profit_pct}% - rounding moved the target"
    )
    assert sign * (target - entry) > 0 and sign * (entry - stop) > 0, (
        "rounding put stop or target on the wrong side of entry"
    )


def test_momentum_keeps_precision_at_ada_scale():
    """ADA-scale sqz_momentum is ~1e-4; 4dp leaves it one significant digit."""
    df = _ada_ohlc()
    strategy = SqueezeMomentumStrategy()

    result = strategy.analyze(df)

    assert (
        result["momentum"] != round(result["momentum"], 4) or result["momentum"] == 0.0
    ), "momentum is still quantized to 4dp"
