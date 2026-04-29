"""
Per-Position Volatility Parity Sizing
Purpose: Equalise expected risk contribution across positions by sizing
         inversely to realised volatility.

Why per-position parity, not portfolio-level vol targeting:
The bot makes per-position decisions (live_trading.py:130). True portfolio-
level vol targeting needs a portfolio constructor that sees all symbols at
once and rescales the book, which doesn't exist. Per-position parity gives
most of the documented benefit (Carver, Barroso & Santa-Clara) without
inventing that infrastructure.

Reference:
- docs/strategy/research-2026-04-29/T1.2-design.md
- docs/strategy/research-2026-04-29/03-risk-management-overlays.md (item #1)
"""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Deque, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Annualisation factor for hourly returns: sqrt(24 * 365) ≈ 92.74
HOURLY_ANNUALISATION = math.sqrt(24 * 365)


@dataclass
class VolEstimatorConfig:
    """Configuration for RealizedVolEstimator."""

    window_bars: int = 168  # 7 days at hourly bars
    min_samples: int = 96  # 4 days minimum before estimator returns a number
    vol_floor_annualised: float = 0.05  # 5% annualised lower bound on realised vol


class RealizedVolEstimator:
    """
    Rolling realised volatility on log returns.

    update(symbol, ts, close) appends a return; get_realized_vol_annualized(symbol)
    returns annualised vol once min_samples accrued, else None.

    Stateless across restarts — caller is responsible for warm-up (replaying
    enough recent bars before the first sizing decision).
    """

    def __init__(self, config: Optional[VolEstimatorConfig] = None):
        self.config = config or VolEstimatorConfig()
        # symbol -> deque of (ts, last_close)
        self._closes: Dict[str, Deque[Tuple[datetime, float]]] = {}
        # symbol -> deque of log returns (most recent rightmost)
        self._returns: Dict[str, Deque[float]] = {}

    def update(self, symbol: str, ts: datetime, close: float) -> None:
        if close is None or close <= 0 or not math.isfinite(close):
            logger.warning("vol_targeting: dropping non-positive close for %s at %s", symbol, ts)
            return
        prev = self._closes.setdefault(symbol, deque(maxlen=2))
        if prev:
            prev_ts, prev_close = prev[-1]
            if ts <= prev_ts:
                # Out-of-order or duplicate bar — ignore.
                return
            ret = math.log(close / prev_close)
            rets = self._returns.setdefault(
                symbol, deque(maxlen=self.config.window_bars)
            )
            rets.append(ret)
        prev.append((ts, close))

    def get_realized_vol_annualized(self, symbol: str) -> Optional[float]:
        rets = self._returns.get(symbol)
        if not rets or len(rets) < self.config.min_samples:
            return None
        # Sample stdev (ddof=1) of log returns, annualised.
        n = len(rets)
        mean = sum(rets) / n
        var = sum((r - mean) ** 2 for r in rets) / (n - 1)
        bar_vol = math.sqrt(var)
        return bar_vol * HOURLY_ANNUALISATION

    def sample_count(self, symbol: str) -> int:
        rets = self._returns.get(symbol)
        return len(rets) if rets else 0


@dataclass
class VolParitySizingConfig:
    """Configuration for vol_parity_size helper."""

    target_vol_annualised: float = 0.30  # 30% annualised target per position
    cap_multiplier: float = 3.0  # Never scale baseline up by more than 3x
    floor_multiplier: float = 0.1  # Never scale baseline down past 0.1x
    vol_floor_annualised: float = 0.05  # Realised vol clamp before division


def vol_parity_size(
    baseline_size: Decimal,
    realized_vol_annualised: Optional[float],
    config: Optional[VolParitySizingConfig] = None,
) -> Decimal:
    """
    Scale baseline_size so the position contributes target_vol of risk.

    size = baseline * (target_vol / max(realised_vol, vol_floor))
    bounded to [floor_multiplier * baseline, cap_multiplier * baseline].

    Falls back to baseline_size when realized_vol_annualised is None
    (estimator not warm) or non-positive.
    """
    cfg = config or VolParitySizingConfig()

    if (
        realized_vol_annualised is None
        or not math.isfinite(realized_vol_annualised)
        or realized_vol_annualised <= 0
    ):
        return baseline_size

    rv = max(realized_vol_annualised, cfg.vol_floor_annualised)
    raw_multiplier = cfg.target_vol_annualised / rv
    bounded_multiplier = max(
        cfg.floor_multiplier, min(cfg.cap_multiplier, raw_multiplier)
    )
    return (baseline_size * Decimal(str(bounded_multiplier))).quantize(Decimal("1e-8"))
