"""Shared harness for gap-audit scripts. Read-only: imports the engine, never edits it."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import numpy as np
import pandas as pd

from backtesting.backtest_engine import BacktestEngine, BacktestResult  # noqa: E402
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "backtesting" / "data" / "BTCUSDT_60m_365d_bybit.csv"


def load_candles(path: Path = DEFAULT_CSV) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(
            f"not verified — blocked by missing columns {missing} in {path}"
        )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").reset_index(drop=True)
    assert (df["high"] >= df["low"]).all(), "high < low rows present"
    return df


def make_engine(**overrides) -> BacktestEngine:
    """Canonical realistic-cost engine. Costs may only be raised via overrides, never lowered."""
    cfg = dict(
        initial_capital=ACCOUNT_EQUITY_USD,
        position_size_pct=0.10,
        fee_mode="bybit_perp",
        slippage_mode="atr_aware",
        funding_enabled=True,
    )
    cfg.update(overrides)
    return BacktestEngine(**cfg)


def _rsi(close: pd.Series, period: int = 9) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return float((100 - 100 / (1 + rs)).iloc[-1])


def baseline_strategy(row, position, idx, data):
    """RSI9/EMA20 baseline, mirrors run_phase1_backtest.baseline_strategy:130
    but self-contained so audit scripts have no import side effects."""
    if idx < 50:
        return None
    hist = data.iloc[: idx + 1]["close"]
    rsi = _rsi(hist)
    ema20 = float(hist.ewm(span=20, adjust=False).mean().iloc[-1])
    price = float(row["close"])
    if position is None:
        if rsi < 20 and price > ema20:
            return {
                "action": "BUY",
                "stop_loss": price * 0.97,
                "take_profit": price * 1.06,
            }
        if rsi > 80 and price < ema20:
            return {
                "action": "SELL",
                "stop_loss": price * 1.03,
                "take_profit": price * 0.94,
            }
    return None


def result_summary(result: BacktestResult) -> dict:
    return {
        "strategy": result.strategy_name,
        "trades": result.total_trades,
        "win_rate": round(result.win_rate, 6),
        "pnl": round(result.total_profit_loss, 6),
        "pnl_pct": round(result.total_profit_loss_pct, 6),
        "final_capital": round(result.final_capital, 6),
        "max_dd_pct": round(result.max_drawdown_pct, 6),
        "sharpe": round(result.sharpe_ratio, 6),
    }
