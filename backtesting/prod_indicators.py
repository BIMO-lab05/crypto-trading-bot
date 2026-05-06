"""
Prod-indicator shim for backtesting (2026-05-06, ADR-013 phase B-2).

Re-exports the live `services/technical-analysis/app/indicators/*` calculators
so the backtest can validate the SAME math the production system runs. The
prior in-tree `IndicatorCalculator` in run_phase1_backtest.py was a parallel
implementation with stock-tuned RSI 14/30/70 — it tested a strategy that
DOESN'T match what runs live. Importing the prod modules removes that drift.

Usage:
    from prod_indicators import (
        RSI, EMA, SMA, ATR, ADX, BollingerBands, Stochastic,
        TrendFilter, VolumeConfirmation, signal_to_score,
    )

    rsi_value = RSI(period=9).calculate(df)
    atr_levels = ATR(period=14).calculate(highs, lows, closes, current_price)
    adx = ADXCalculator().calculate(df)

Implementation note: the live indicators import `from app.models import
SignalType`. We prepend services/technical-analysis to sys.path so `app.models`
resolves there. The repo root is also on path (added by run_phase1_backtest.py
etc), so we put the TA path FIRST. This works as long as backtest scripts
don't also import trading-engine's `app.*` (audit confirms they don't).
"""

from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
_TA_PATH = os.path.join(_REPO_ROOT, "services", "technical-analysis")

# Prepend TA path so `app.models` resolves to TA's models, not trading-engine's.
if _TA_PATH not in sys.path:
    sys.path.insert(0, _TA_PATH)

# Re-exports — fail loudly if the TA service tree is missing.
from app.indicators.rsi import RSICalculator as RSI  # noqa: E402
from app.indicators.atr import ATR  # noqa: E402
from app.indicators.adx import ADXCalculator as ADX  # noqa: E402
from app.indicators.bollinger_bands import (  # noqa: E402
    BollingerBandsCalculator as BollingerBands,
)
from app.indicators.macd import MACDCalculator as MACD  # noqa: E402
from app.indicators.moving_averages import (  # noqa: E402
    SMACalculator as SMA,
    EMACalculator as EMA,
)
from app.indicators.stochastic import Stochastic  # noqa: E402
from app.indicators.trend_filter import TrendFilter  # noqa: E402
from app.indicators.volume_confirmation import VolumeConfirmation  # noqa: E402
from app.models import SignalType  # noqa: E402


def signal_to_score(signal: "SignalType") -> float:
    """Map prod SignalType to a -1/0/+1 score for backtest aggregation."""
    if signal == SignalType.BUY:
        return 1.0
    if signal == SignalType.SELL:
        return -1.0
    return 0.0


__all__ = [
    "RSI",
    "ATR",
    "ADX",
    "BollingerBands",
    "MACD",
    "SMA",
    "EMA",
    "Stochastic",
    "TrendFilter",
    "VolumeConfirmation",
    "SignalType",
    "signal_to_score",
]
