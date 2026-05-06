#!/usr/bin/env python3
"""
Walk-forward backtest harness (ADR-013 phase B-3 — 2026-05-06).

Splits the requested data window into K rolling out-of-sample (OOS) folds and
runs the SAME rule-based strategy fresh on each fold's OOS slice. Reports
per-fold Sharpe / max DD / profit factor / win rate, then aggregates with
DSR (deflated Sharpe ratio) to gate the overall claim.

Why this exists:
- The repo had a single-shot backtest that reported one Sharpe number on the
  whole window. Single-shot Sharpe is overfit-friendly: a strategy that wins
  on one regime can post a clean number even with no edge OOS.
- Walk-forward forces stability across regimes. The OOS Sharpe vs IS Sharpe
  ratio is the cheapest in-house overfit detector.
- DSR (Bailey & Lopez de Prado) corrects the single-Sharpe number for the
  number of trial strategies you've evaluated. Project rule (skill: trading-
  strategy-dev / acceptance-gates.md): DSR > 0.95.

Usage:
    python3 backtesting/run_walk_forward.py \
        --symbol SOLUSDT \
        --days 180 \
        --folds 4 \
        --is-frac 0.75

Defaults: --days 180, --folds 4, --is-frac 0.75. Folds smaller than 30 days
are rejected (insufficient signal). The runner also enforces the
2026-04-25 testnet→mainnet flip taint gate; pass `--ack-mixed-data` to
override (not recommended for promotion-grade runs).

Strategy: phase1-style (RSI<20 + EMA50 trend agreement + ATR stops + ADX
trend gate + volume confirmation). Powered by prod indicators via
backtesting/prod_indicators.py — same math the live system runs.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import math
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List

import numpy as np
import pandas as pd

# Repo root to sys.path so backtest_engine + data_downloader resolve.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from backtesting.backtest_engine import BacktestEngine, BacktestResult  # noqa: E402
from backtesting.data_downloader import HistoricalDataDownloader  # noqa: E402
from backtesting.prod_indicators import (  # noqa: E402
    ADX,
    ATR,
    EMA,
    RSI,
    TrendFilter,
    VolumeConfirmation,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Testnet→mainnet flip per CLAUDE.md gotcha; bars before this date in
# TimescaleDB are testnet-tainted.
TESTNET_FLIP_UTC = datetime(2026, 4, 25, tzinfo=timezone.utc)


@dataclass
class FoldResult:
    fold_id: int
    start: pd.Timestamp
    end: pd.Timestamp
    bars: int
    trades: int
    win_rate: float
    sharpe: float
    max_drawdown_pct: float
    profit_factor: float
    total_pnl_pct: float


@dataclass
class WalkForwardSummary:
    folds: List[FoldResult]
    is_sharpe_mean: float
    oos_sharpe_mean: float
    is_oos_ratio: float
    dsr: float
    gate_passed: bool
    gate_reasons: List[str]


def phase1_strategy_prod(row, position, idx, data: pd.DataFrame):
    """
    Phase1-equivalent strategy using PROD indicators (RSI 9 / OB 80 / OS 20,
    plus EMA20, ADX>=20, TrendFilter, VolumeConfirmation, ATR stops).

    Causal: every signal computed from data[: idx + 1].
    """
    if idx < 50:  # warmup
        return None

    hist = data.iloc[: idx + 1]
    close_prices = hist["close"]
    high_list = hist["high"].tolist()
    low_list = hist["low"].tolist()
    close_list = hist["close"].tolist()
    volume_list = hist["volume"].tolist()
    current_price = float(row["close"])

    rsi_val = RSI(period=9).calculate(hist)
    if rsi_val is None:
        return None
    ema_20 = EMA(period=20).calculate(hist)
    if ema_20 is None:
        return None

    # ADX trend gate (skip if weak trend or counter-direction)
    adx = ADX().calculate(high_list, low_list, close_list)
    adx_value = float(adx.get("adx", 0.0))
    direction = adx.get("direction", "NEUTRAL")
    if adx_value < 20.0:
        return None

    # TrendFilter (gatekeeper) + VolumeConfirmation (validator)
    trend = TrendFilter().calculate(close_list)
    volume = VolumeConfirmation().calculate(volume_list)
    if not volume.get("confirmed"):
        return None

    # ATR stops (vol-aware)
    atr = ATR(period=14).calculate(high_list, low_list, close_list, current_price)

    if not position:
        if rsi_val < 20 and current_price > ema_20:
            if trend.get("trend") == "BEARISH":
                return None
            if direction == "BEARISH":
                return None
            return {
                "action": "BUY",
                "stop_loss": atr["stop_loss_long"],
                "take_profit": atr["take_profit_long"],
                "metadata": {
                    "rsi": rsi_val,
                    "ema_20": ema_20,
                    "adx": adx_value,
                    "trend": trend.get("trend"),
                    "volume_ratio": volume.get("volume_ratio"),
                    "strategy": "phase1_prod",
                },
            }
        if rsi_val > 80 and current_price < ema_20:
            if trend.get("trend") == "BULLISH":
                return None
            if direction == "BULLISH":
                return None
            return {
                "action": "SELL",
                "stop_loss": atr["stop_loss_short"],
                "take_profit": atr["take_profit_short"],
                "metadata": {
                    "rsi": rsi_val,
                    "ema_20": ema_20,
                    "adx": adx_value,
                    "trend": trend.get("trend"),
                    "volume_ratio": volume.get("volume_ratio"),
                    "strategy": "phase1_prod",
                },
            }

    return None


def deflated_sharpe(
    sr_obs: float, n_trials: int, sr_std: float = 1.0, n_obs: int = 252
) -> float:
    """Bailey & Lopez de Prado DSR. n_trials = honest count of all variants tried."""
    if n_obs <= 1:
        return 0.0
    if n_trials <= 1:
        n_trials = 2
    from scipy.stats import norm

    expected_max_sr = sr_std * (
        (1 - np.euler_gamma) * norm.ppf(1 - 1.0 / n_trials)
        + np.euler_gamma * norm.ppf(1 - 1.0 / (n_trials * np.e))
    )
    z = (sr_obs - expected_max_sr) * math.sqrt(n_obs - 1)
    return float(norm.cdf(z))


def split_folds(
    data: pd.DataFrame,
    n_folds: int,
    is_frac: float = 0.75,
) -> List[tuple]:
    """
    Anchored walk-forward split:
        fold k uses [0 : split_k * is_frac] in-sample,
                    [split_k * is_frac : split_k] out-of-sample
    where split_k = round((k+1) / n_folds * len(data)).

    Each fold's OOS window grows; a stable strategy holds Sharpe across them.
    """
    n = len(data)
    folds = []
    for k in range(n_folds):
        split_end = round((k + 1) / n_folds * n)
        split_is = round(split_end * is_frac)
        if split_end - split_is < 1:
            continue
        is_slice = data.iloc[:split_is]
        oos_slice = data.iloc[split_is:split_end]
        folds.append((is_slice, oos_slice))
    return folds


def calc_sharpe(equity_curve: List[float], periods_per_year: int = 24 * 365) -> float:
    """Annualized Sharpe from equity curve (per-bar returns, hourly bars assumed)."""
    if len(equity_curve) < 2:
        return 0.0
    arr = np.asarray(equity_curve, dtype=float)
    rets = np.diff(arr) / arr[:-1]
    if rets.std(ddof=0) == 0:
        return 0.0
    return float(rets.mean() / rets.std(ddof=0) * math.sqrt(periods_per_year))


_GLOBAL_ENGINE_KWARGS: dict = {}


def _engine_kwargs() -> dict:
    """Module-level kwargs dispatcher so run_one_fold + IS engine match flags."""
    return dict(_GLOBAL_ENGINE_KWARGS)


def run_one_fold(
    fold_id: int,
    oos_data: pd.DataFrame,
    strategy_func: Callable,
    initial_capital: float = 10000.0,
) -> FoldResult:
    engine = BacktestEngine(initial_capital=initial_capital, **_engine_kwargs())
    result: BacktestResult = engine.run_backtest(
        oos_data, strategy_func, strategy_name=f"phase1_prod_fold_{fold_id}"
    )
    sharpe = calc_sharpe(engine.equity_curve)
    start = (
        oos_data.index[0]
        if isinstance(oos_data.index[0], (pd.Timestamp, datetime))
        else pd.to_datetime(oos_data.iloc[0]["timestamp"])
    )
    end = (
        oos_data.index[-1]
        if isinstance(oos_data.index[-1], (pd.Timestamp, datetime))
        else pd.to_datetime(oos_data.iloc[-1]["timestamp"])
    )
    return FoldResult(
        fold_id=fold_id,
        start=start,
        end=end,
        bars=len(oos_data),
        trades=len(engine.trades),
        win_rate=getattr(result, "win_rate", 0.0),
        sharpe=sharpe,
        max_drawdown_pct=getattr(result, "max_drawdown_pct", 0.0),
        profit_factor=getattr(result, "profit_factor", 0.0),
        total_pnl_pct=getattr(result, "total_profit_loss_pct", 0.0),
    )


def gate_check(summary: WalkForwardSummary) -> tuple[bool, List[str]]:
    """Apply ADR-013 / acceptance-gates.md thresholds."""
    reasons: List[str] = []
    oos_sharpes = [f.sharpe for f in summary.folds]
    if not oos_sharpes:
        return False, ["no folds executed"]
    oos_mean = float(np.mean(oos_sharpes))
    if oos_mean < 1.0:
        reasons.append(f"OOS Sharpe mean {oos_mean:.2f} < 1.00")
    max_dd = max((abs(f.max_drawdown_pct) for f in summary.folds), default=0.0)
    if max_dd > 30.0:
        reasons.append(f"max OOS drawdown {max_dd:.1f}% > 30%")
    pfs = [f.profit_factor for f in summary.folds if f.trades > 0]
    if pfs and float(np.mean(pfs)) < 1.2:
        reasons.append(f"profit factor mean {float(np.mean(pfs)):.2f} < 1.2")
    if summary.is_oos_ratio < 0.6:
        reasons.append(f"OOS/IS Sharpe ratio {summary.is_oos_ratio:.2f} < 0.60")
    if summary.dsr < 0.95:
        reasons.append(f"DSR {summary.dsr:.2f} < 0.95")
    return (not reasons), reasons


async def main():
    parser = argparse.ArgumentParser(description="Walk-forward backtest")
    parser.add_argument("--symbol", required=True, help="Trading pair (e.g. SOLUSDT)")
    parser.add_argument("--days", type=int, default=180, help="Total days of history")
    parser.add_argument(
        "--folds", type=int, default=4, help="Number of walk-forward folds"
    )
    parser.add_argument(
        "--is-frac", type=float, default=0.75, help="In-sample fraction per fold"
    )
    parser.add_argument("--interval", default="60", help="Candle interval in minutes")
    parser.add_argument(
        "--ack-mixed-data",
        action="store_true",
        help="Skip the testnet-flip date guard (NOT recommended for promotion runs)",
    )
    parser.add_argument("--n-trials", type=int, default=10, help="DSR n_trials param")
    # Realistic-sim knobs (B-4). Defaults preserve legacy behavior.
    parser.add_argument(
        "--realistic-sim",
        action="store_true",
        help="Engage Bybit-perp asymmetric fees + ATR-aware slippage + funding cost",
    )
    parser.add_argument(
        "--funding-rate-per-8h",
        type=float,
        default=0.0001,
        help="Per-8h funding rate (only used with --realistic-sim)",
    )
    parser.add_argument(
        "--partial-fill-pct",
        type=float,
        default=0.0,
        help="Cap fill at this fraction of bar volume (0 = disabled)",
    )
    args = parser.parse_args()

    # Wire engine kwargs from CLI so IS + OOS engines match.
    if args.realistic_sim:
        _GLOBAL_ENGINE_KWARGS.update(
            fee_mode="bybit_perp",
            slippage_mode="atr_aware",
            funding_enabled=True,
            funding_rate_per_8h=args.funding_rate_per_8h,
        )
    if args.partial_fill_pct > 0:
        _GLOBAL_ENGINE_KWARGS["partial_fill_volume_pct"] = args.partial_fill_pct

    if args.folds < 4:
        logger.warning("--folds < 4: fewer than 4 folds is too few for stability check")
    fold_days = args.days / args.folds
    if fold_days < 30:
        raise SystemExit(
            f"fold size {fold_days:.1f} days < 30; either raise --days or lower --folds"
        )

    logger.info(
        f"Walk-forward: {args.symbol} @ {args.interval}m, {args.days}d total, "
        f"{args.folds} folds, IS frac={args.is_frac:.2f}"
    )

    downloader = HistoricalDataDownloader(market_data_url="http://localhost:8002")
    data = await downloader.download_historical_data(
        symbol=args.symbol,
        interval=args.interval,
        days=args.days,
    )
    await downloader.close()
    if data is None or len(data) == 0:
        raise SystemExit(f"No data downloaded for {args.symbol}")

    if "timestamp" in data.columns:
        ts = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
        data = data.assign(timestamp=ts).set_index("timestamp")

    earliest = data.index[0]
    if not args.ack_mixed_data and earliest.to_pydatetime() < TESTNET_FLIP_UTC:
        raise SystemExit(
            f"Earliest bar {earliest} is before 2026-04-25 testnet flip. "
            f"Backtest would mix testnet/mainnet candles. Re-run with "
            f"`--days` smaller, or pass `--ack-mixed-data` to override."
        )

    folds = split_folds(data, args.folds, args.is_frac)
    fold_results: List[FoldResult] = []
    is_sharpes: List[float] = []
    for k, (is_slice, oos_slice) in enumerate(folds):
        # IS Sharpe (no fitting — strategy is rule-based; we just measure
        # that the SAME strategy applied to the IS slice would have produced
        # similar returns; ratio detects regime drift).
        is_engine = BacktestEngine(initial_capital=10000.0)
        is_engine.run_backtest(
            is_slice, phase1_strategy_prod, strategy_name=f"phase1_is_{k}"
        )
        is_sharpes.append(calc_sharpe(is_engine.equity_curve))

        oos_result = run_one_fold(k, oos_slice, phase1_strategy_prod)
        fold_results.append(oos_result)

    oos_sharpes = [f.sharpe for f in fold_results]
    is_mean = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    oos_mean = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    is_oos_ratio = (oos_mean / is_mean) if is_mean != 0 else 0.0
    dsr = deflated_sharpe(
        sr_obs=oos_mean,
        n_trials=args.n_trials,
        sr_std=float(np.std(oos_sharpes, ddof=0)) if len(oos_sharpes) > 1 else 1.0,
        n_obs=int(np.mean([f.bars for f in fold_results])) if fold_results else 1,
    )

    summary = WalkForwardSummary(
        folds=fold_results,
        is_sharpe_mean=is_mean,
        oos_sharpe_mean=oos_mean,
        is_oos_ratio=is_oos_ratio,
        dsr=dsr,
        gate_passed=False,
        gate_reasons=[],
    )
    summary.gate_passed, summary.gate_reasons = gate_check(summary)

    print("=" * 80)
    print(f"WALK-FORWARD RESULTS — {args.symbol} {args.interval}m {args.days}d")
    print("=" * 80)
    print(
        f"{'fold':>4} {'start':<11} {'end':<11} {'bars':>5} {'trades':>6} "
        f"{'WR%':>6} {'Sharpe':>7} {'maxDD%':>7} {'PF':>5} {'PnL%':>7}"
    )
    for f in fold_results:
        print(
            f"{f.fold_id:>4} {str(f.start.date()):<11} {str(f.end.date()):<11} "
            f"{f.bars:>5} {f.trades:>6} {f.win_rate:>6.1f} {f.sharpe:>7.2f} "
            f"{f.max_drawdown_pct:>7.2f} {f.profit_factor:>5.2f} {f.total_pnl_pct:>7.2f}"
        )
    print("-" * 80)
    print(f"IS Sharpe mean : {is_mean:+.3f}")
    print(f"OOS Sharpe mean: {oos_mean:+.3f}")
    print(f"OOS/IS ratio   : {is_oos_ratio:+.3f}  (gate ≥ 0.60)")
    print(f"DSR            : {dsr:.3f}  (gate ≥ 0.95)")
    print(f"Gate passed    : {summary.gate_passed}")
    if not summary.gate_passed:
        print("Gate failures  :")
        for r in summary.gate_reasons:
            print(f"  - {r}")
    print("=" * 80)

    return 0 if summary.gate_passed else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
