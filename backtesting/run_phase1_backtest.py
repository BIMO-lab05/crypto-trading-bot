#!/usr/bin/env python3
"""
Phase 1 Backtest Runner
Compares baseline strategy (without Phase 1) vs Phase 1 strategy
Downloads data, runs backtests, generates comprehensive comparison report
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import pandas as pd
import logging
from backtest_engine import BacktestEngine
from data_downloader import HistoricalDataDownloader

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """Calculate technical indicators for backtesting"""

    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50.0

        deltas = prices.diff()
        gain = deltas.where(deltas > 0, 0.0)
        loss = -deltas.where(deltas < 0, 0.0)

        avg_gain = gain.rolling(window=period).mean().iloc[-1]
        avg_loss = loss.rolling(window=period).mean().iloc[-1]

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> float:
        """Calculate EMA"""
        if len(prices) < period:
            return prices.mean()

        return prices.ewm(span=period, adjust=False).mean().iloc[-1]

    @staticmethod
    def calculate_trend_filter(
        prices: pd.Series, fast_period: int = 50, slow_period: int = 200
    ) -> dict:
        """Calculate Trend Filter (50/200 EMA)"""
        if len(prices) < slow_period:
            return {"trend": "NEUTRAL", "confidence": 0.3}

        fast_ema = IndicatorCalculator.calculate_ema(prices, fast_period)
        slow_ema = IndicatorCalculator.calculate_ema(prices, slow_period)

        spread_pct = (fast_ema - slow_ema) / slow_ema

        if spread_pct > 0.005:  # 0.5%
            return {"trend": "BULLISH", "confidence": min(abs(spread_pct) / 0.05, 1.0)}
        elif spread_pct < -0.005:
            return {"trend": "BEARISH", "confidence": min(abs(spread_pct) / 0.05, 1.0)}
        else:
            return {"trend": "NEUTRAL", "confidence": 0.3}

    @staticmethod
    def calculate_volume_confirmation(volumes: pd.Series, period: int = 20) -> dict:
        """Calculate Volume Confirmation"""
        if len(volumes) < period:
            return {"confirmed": False, "strength": "INSUFFICIENT", "ratio": 0.0}

        current_volume = volumes.iloc[-1]
        avg_volume = volumes.iloc[-period:].mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio >= 1.5:
            return {"confirmed": True, "strength": "STRONG", "ratio": volume_ratio}
        elif volume_ratio >= 1.2:
            return {"confirmed": True, "strength": "MODERATE", "ratio": volume_ratio}
        elif volume_ratio >= 1.0:
            return {"confirmed": False, "strength": "WEAK", "ratio": volume_ratio}
        else:
            return {
                "confirmed": False,
                "strength": "INSUFFICIENT",
                "ratio": volume_ratio,
            }

    @staticmethod
    def calculate_atr(
        highs: pd.Series, lows: pd.Series, closes: pd.Series, period: int = 14
    ) -> dict:
        """Calculate ATR"""
        if len(closes) < period + 1:
            return {"atr": 0.0, "stop_loss_long": 0.0, "take_profit_long": 0.0}

        df = pd.DataFrame(
            {"high": highs, "low": lows, "close": closes, "prev_close": closes.shift(1)}
        )

        df["tr1"] = df["high"] - df["low"]
        df["tr2"] = abs(df["high"] - df["prev_close"])
        df["tr3"] = abs(df["low"] - df["prev_close"])
        df["tr"] = df[["tr1", "tr2", "tr3"]].max(axis=1)

        atr = df["tr"].ewm(span=period, adjust=False).mean().iloc[-1]
        current_price = closes.iloc[-1]

        return {
            "atr": atr,
            "stop_loss_long": current_price - (atr * 2.0),
            "take_profit_long": current_price + (atr * 4.0),
            "stop_loss_short": current_price + (atr * 2.0),
            "take_profit_short": current_price - (atr * 4.0),
        }


def baseline_strategy(row: pd.Series, position, idx: int, data: pd.DataFrame) -> dict:
    """
    Baseline Strategy (WITHOUT Phase 1)
    Uses only RSI + EMA for signals.

    NOTE on divergence (2026-05-06): the live system in
    services/technical-analysis/app/indicators/rsi.py uses crypto-tuned
    defaults (period=9, overbought=80, oversold=20) per its module docstring.
    This backtest historically used stock-tuned 14/70/30 — meaning the
    backtest validated a *different* strategy than what runs in production.
    Aligning here so the headline backtest answers a real question. The
    deeper alignment (importing the actual production indicator code)
    is tracked in the strategy-rebuild plan; until then, params drift can
    silently re-occur. Sync forward: every parameter change in prod must
    be mirrored here, or the backtest is decorative.
    """
    # Need enough historical data. Warmup must fit inside the data window
    # — the prior 200-bar warmup vs 200-bar download (limit-only paginator
    # bug) used to block all signals. With cursor pagination fixed, even a
    # 30-day window is ~720 bars; reduce the warmup to a more reasonable
    # 50 so the strategy actually evaluates the early bars.
    if idx < 50:
        return None

    # Get historical data for indicators
    hist_data = data.iloc[: idx + 1]
    close_prices = hist_data["close"]

    # Crypto-tuned RSI: period 9, OB 80, OS 20 (matches live indicators/rsi.py).
    rsi = IndicatorCalculator.calculate_rsi(close_prices, 9)
    ema_20 = IndicatorCalculator.calculate_ema(close_prices, 20)
    current_price = row["close"]

    # Generate signal
    signal = None

    if not position:
        # Entry signals — crypto thresholds 20/80 (was 30/70).
        if rsi < 20 and current_price > ema_20:  # Oversold + above EMA
            signal = {
                "action": "BUY",
                "stop_loss": current_price * 0.97,  # Fixed 3% stop loss
                "take_profit": current_price * 1.06,  # Fixed 6% take profit
                "metadata": {"rsi": rsi, "ema_20": ema_20, "strategy": "baseline"},
            }

        elif rsi > 80 and current_price < ema_20:  # Overbought + below EMA
            signal = {
                "action": "SELL",
                "stop_loss": current_price * 1.03,
                "take_profit": current_price * 0.94,
                "metadata": {"rsi": rsi, "ema_20": ema_20, "strategy": "baseline"},
            }

    return signal


def phase1_strategy(row: pd.Series, position, idx: int, data: pd.DataFrame) -> dict:
    """
    Phase 1 Strategy (WITH Phase 1 filters)
    Uses RSI + EMA + GATEKEEPER + VALIDATOR + ATR.

    Aligned with crypto-tuned defaults to mirror live indicators (2026-05-06):
    RSI period 9 / OB 80 / OS 20. Same warmup-vs-window note as baseline.
    """
    # Warmup tightened from 200 → 50 so the strategy actually evaluates
    # the early bars on a 30-day window. With cursor pagination fixed in
    # data_downloader, longer windows naturally have warmup headroom.
    if idx < 50:
        return None

    # Get historical data
    hist_data = data.iloc[: idx + 1]
    close_prices = hist_data["close"]
    volumes = hist_data["volume"]
    highs = hist_data["high"]
    lows = hist_data["low"]

    # Crypto-tuned RSI: period 9 (matches services/technical-analysis indicators).
    rsi = IndicatorCalculator.calculate_rsi(close_prices, 9)
    ema_20 = IndicatorCalculator.calculate_ema(close_prices, 20)
    current_price = row["close"]

    # Phase 1: GATEKEEPER (Trend Filter)
    trend_filter = IndicatorCalculator.calculate_trend_filter(close_prices)

    # Phase 1: VALIDATOR (Volume Confirmation)
    volume_conf = IndicatorCalculator.calculate_volume_confirmation(volumes)

    # Phase 1: ATR for dynamic stops
    atr_data = IndicatorCalculator.calculate_atr(highs, lows, close_prices)

    # Generate signal
    signal = None

    if not position:
        # Entry signals
        if rsi < 20 and current_price > ema_20:  # Oversold + above EMA (crypto OS=20)
            # GATEKEEPER: Block counter-trend trades
            if trend_filter["trend"] == "BEARISH":
                logger.debug("GATEKEEPER blocked BUY signal (BEARISH trend)")
                return None

            # VALIDATOR: Check volume confirmation
            if not volume_conf["confirmed"]:
                logger.debug(
                    f"VALIDATOR rejected BUY signal (volume: {volume_conf['strength']})"
                )
                return None

            # Signal passed all Phase 1 filters
            signal = {
                "action": "BUY",
                "stop_loss": atr_data["stop_loss_long"],  # Dynamic ATR-based stop
                "take_profit": atr_data["take_profit_long"],  # Dynamic ATR-based TP
                "metadata": {
                    "rsi": rsi,
                    "ema_20": ema_20,
                    "trend": trend_filter["trend"],
                    "volume_confirmed": volume_conf["confirmed"],
                    "volume_strength": volume_conf["strength"],
                    "atr": atr_data["atr"],
                    "strategy": "phase1",
                },
            }

        elif (
            rsi > 80 and current_price < ema_20
        ):  # Overbought + below EMA (crypto OB=80)
            # GATEKEEPER: Block counter-trend trades
            if trend_filter["trend"] == "BULLISH":
                logger.debug("GATEKEEPER blocked SELL signal (BULLISH trend)")
                return None

            # VALIDATOR: Check volume confirmation
            if not volume_conf["confirmed"]:
                logger.debug(
                    f"VALIDATOR rejected SELL signal (volume: {volume_conf['strength']})"
                )
                return None

            # Signal passed all Phase 1 filters
            signal = {
                "action": "SELL",
                "stop_loss": atr_data["stop_loss_short"],
                "take_profit": atr_data["take_profit_short"],
                "metadata": {
                    "rsi": rsi,
                    "ema_20": ema_20,
                    "trend": trend_filter["trend"],
                    "volume_confirmed": volume_conf["confirmed"],
                    "volume_strength": volume_conf["strength"],
                    "atr": atr_data["atr"],
                    "strategy": "phase1",
                },
            }

    return signal


def print_comparison_report(baseline_result, phase1_result):
    """Print comprehensive comparison report"""
    print("\n" + "=" * 100)
    print(" " * 35 + "PHASE 1 BACKTEST COMPARISON")
    print("=" * 100)

    print("\n📅 TEST PERIOD")
    print(f"  Start: {baseline_result.start_date}")
    print(f"  End:   {baseline_result.end_date}")
    print(f"  Initial Capital: ${baseline_result.initial_capital:,.2f}")

    print("\n" + "-" * 100)
    print(f"{'METRIC':<40} {'BASELINE':<25} {'PHASE 1':<25} {'IMPROVEMENT':<10}")
    print("-" * 100)

    # Trade Count
    improvement = (
        (
            (phase1_result.total_trades - baseline_result.total_trades)
            / baseline_result.total_trades
            * 100
        )
        if baseline_result.total_trades > 0
        else 0
    )
    print(
        f"{'Total Trades':<40} {baseline_result.total_trades:<25} {phase1_result.total_trades:<25} {improvement:>8.1f}%"
    )

    # Win Rate
    improvement = phase1_result.win_rate - baseline_result.win_rate
    status = "✅" if improvement > 0 else "❌"
    print(
        f"{'Win Rate':<40} {baseline_result.win_rate:<24.2f}% {phase1_result.win_rate:<24.2f}% {status} {improvement:>6.2f}%"
    )

    # Total P&L
    improvement = (
        (
            (phase1_result.total_profit_loss - baseline_result.total_profit_loss)
            / abs(baseline_result.total_profit_loss)
            * 100
        )
        if baseline_result.total_profit_loss != 0
        else 0
    )
    status = (
        "✅"
        if phase1_result.total_profit_loss > baseline_result.total_profit_loss
        else "❌"
    )
    print(
        f"{'Total P&L':<40} ${baseline_result.total_profit_loss:<23,.2f} ${phase1_result.total_profit_loss:<23,.2f} {status} {improvement:>6.1f}%"
    )

    # Total P&L %
    improvement = (
        phase1_result.total_profit_loss_pct - baseline_result.total_profit_loss_pct
    )
    status = "✅" if improvement > 0 else "❌"
    print(
        f"{'Total Return':<40} {baseline_result.total_profit_loss_pct:<24.2f}% {phase1_result.total_profit_loss_pct:<24.2f}% {status} {improvement:>6.2f}%"
    )

    # Average profit per trade
    improvement = (
        (
            (phase1_result.avg_profit_per_trade - baseline_result.avg_profit_per_trade)
            / abs(baseline_result.avg_profit_per_trade)
            * 100
        )
        if baseline_result.avg_profit_per_trade != 0
        else 0
    )
    status = (
        "✅"
        if phase1_result.avg_profit_per_trade > baseline_result.avg_profit_per_trade
        else "❌"
    )
    print(
        f"{'Avg Profit/Trade':<40} ${baseline_result.avg_profit_per_trade:<23,.2f} ${phase1_result.avg_profit_per_trade:<23,.2f} {status} {improvement:>6.1f}%"
    )

    # Max Drawdown
    improvement = (
        (
            (baseline_result.max_drawdown_pct - phase1_result.max_drawdown_pct)
            / baseline_result.max_drawdown_pct
            * 100
        )
        if baseline_result.max_drawdown_pct > 0
        else 0
    )
    status = (
        "✅"
        if phase1_result.max_drawdown_pct < baseline_result.max_drawdown_pct
        else "❌"
    )
    print(
        f"{'Max Drawdown':<40} {baseline_result.max_drawdown_pct:<24.2f}% {phase1_result.max_drawdown_pct:<24.2f}% {status} {improvement:>6.1f}%"
    )

    # Sharpe Ratio
    improvement = (
        (
            (phase1_result.sharpe_ratio - baseline_result.sharpe_ratio)
            / abs(baseline_result.sharpe_ratio)
            * 100
        )
        if baseline_result.sharpe_ratio != 0
        else 0
    )
    status = "✅" if phase1_result.sharpe_ratio > baseline_result.sharpe_ratio else "❌"
    print(
        f"{'Sharpe Ratio':<40} {baseline_result.sharpe_ratio:<25.2f} {phase1_result.sharpe_ratio:<25.2f} {status} {improvement:>6.1f}%"
    )

    # Profit Factor
    improvement = (
        (
            (phase1_result.profit_factor - baseline_result.profit_factor)
            / baseline_result.profit_factor
            * 100
        )
        if baseline_result.profit_factor > 0
        else 0
    )
    status = (
        "✅" if phase1_result.profit_factor > baseline_result.profit_factor else "❌"
    )
    print(
        f"{'Profit Factor':<40} {baseline_result.profit_factor:<25.2f} {phase1_result.profit_factor:<25.2f} {status} {improvement:>6.1f}%"
    )

    print("-" * 100)

    # Summary
    print("\n🎯 PHASE 1 GOALS vs RESULTS")
    print("-" * 100)
    win_rate_improvement = phase1_result.win_rate - baseline_result.win_rate
    drawdown_reduction = (
        (
            (baseline_result.max_drawdown_pct - phase1_result.max_drawdown_pct)
            / baseline_result.max_drawdown_pct
            * 100
        )
        if baseline_result.max_drawdown_pct > 0
        else 0
    )

    print("  Goal 1: Increase Win Rate by 10-15%")
    if win_rate_improvement >= 10:
        print(f"    ✅ ACHIEVED: +{win_rate_improvement:.2f}% improvement")
    elif win_rate_improvement >= 5:
        print(
            f"    ⚠️  PARTIAL: +{win_rate_improvement:.2f}% improvement (target: 10-15%)"
        )
    else:
        print(
            f"    ❌ NOT MET: +{win_rate_improvement:.2f}% improvement (target: 10-15%)"
        )

    print("\n  Goal 2: Reduce Drawdown by 20-30%")
    if drawdown_reduction >= 20:
        print(f"    ✅ ACHIEVED: {drawdown_reduction:.2f}% reduction")
    elif drawdown_reduction >= 10:
        print(f"    ⚠️  PARTIAL: {drawdown_reduction:.2f}% reduction (target: 20-30%)")
    else:
        print(f"    ❌ NOT MET: {drawdown_reduction:.2f}% reduction (target: 20-30%)")

    print("\n  Goal 3: Reduce False Signals by 40-50%")
    trades_reduction = (
        (
            (baseline_result.total_trades - phase1_result.total_trades)
            / baseline_result.total_trades
            * 100
        )
        if baseline_result.total_trades > 0
        else 0
    )
    if trades_reduction >= 40:
        print(f"    ✅ ACHIEVED: {trades_reduction:.2f}% fewer trades (filtered out)")
    elif trades_reduction >= 20:
        print(f"    ⚠️  PARTIAL: {trades_reduction:.2f}% fewer trades (target: 40-50%)")
    else:
        print(f"    ❌ NOT MET: {trades_reduction:.2f}% fewer trades (target: 40-50%)")

    print("\n" + "=" * 100)
    print(
        f"{'FINAL CAPITAL':<40} ${baseline_result.final_capital:<23,.2f} ${phase1_result.final_capital:<23,.2f}"
    )
    print("=" * 100 + "\n")


async def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Run Phase 1 backtest comparison")
    parser.add_argument("--symbol", type=str, default="BTCUSDT", help="Trading pair")
    parser.add_argument(
        "--interval", type=str, default="60", help="Candle interval in minutes"
    )
    parser.add_argument("--days", type=int, default=90, help="Days of historical data")
    parser.add_argument(
        "--capital", type=float, default=10000.0, help="Initial capital"
    )
    parser.add_argument(
        "--data-file", type=str, help="Use existing CSV file instead of downloading"
    )
    parser.add_argument(
        "--ack-mixed-data",
        action="store_true",
        help=(
            "Allow backtest spans crossing the 2026-04-25 testnet→mainnet flip. "
            "By default the runner refuses pre-2026-04-25 candles since they "
            "are testnet-tainted in TimescaleDB (CLAUDE.md gotcha)."
        ),
    )

    args = parser.parse_args()

    logger.info("=" * 100)
    logger.info("PHASE 1 BACKTEST - Starting")
    logger.info("=" * 100)

    # Download or load data
    if args.data_file and os.path.exists(args.data_file):
        logger.info(f"Loading data from: {args.data_file}")
        data = pd.read_csv(args.data_file)
        data["timestamp"] = pd.to_datetime(data["timestamp"])
    else:
        logger.info("Downloading historical data...")
        downloader = HistoricalDataDownloader()
        try:
            data = await downloader.download_historical_data(
                symbol=args.symbol,
                interval=args.interval,
                days=args.days,
                output_file=f"backtesting/data/{args.symbol}_{args.interval}m_{args.days}d.csv",
            )
        finally:
            await downloader.close()

        if data.empty:
            logger.error("Failed to download data")
            return

    logger.info(f"Data loaded: {len(data)} candles")

    # Testnet-flip taint guard (ADR-013 phase B-5).
    # Bars before 2026-04-25 came from testnet prices and will produce
    # unrealistic backtest outcomes. Refuse unless operator opts in.
    from datetime import datetime as _dt, timezone as _tz

    _testnet_flip = _dt(2026, 4, 25, tzinfo=_tz.utc)
    try:
        ts_series = pd.to_datetime(data["timestamp"], utc=True, errors="coerce")
        earliest = ts_series.min()
        if pd.notna(earliest) and earliest.to_pydatetime() < _testnet_flip:
            if not args.ack_mixed_data:
                logger.error(
                    f"Earliest bar {earliest} is before 2026-04-25 testnet flip; "
                    f"refusing to run on mixed testnet/mainnet data. "
                    f"Reduce --days or pass --ack-mixed-data to override."
                )
                return
            logger.warning(
                f"PROCEEDING WITH MIXED DATA per --ack-mixed-data. Earliest "
                f"bar {earliest} predates 2026-04-25 testnet flip; metrics are "
                f"NOT promotion-grade."
            )
    except Exception as _guard_err:
        logger.warning(f"testnet-flip guard skipped: {_guard_err}")

    # Run baseline backtest
    logger.info("\n" + "=" * 100)
    logger.info("Running BASELINE strategy (without Phase 1)...")
    logger.info("=" * 100)

    baseline_engine = BacktestEngine(initial_capital=args.capital)
    baseline_result = baseline_engine.run_backtest(
        data=data, strategy_func=baseline_strategy, strategy_name="Baseline (RSI + EMA)"
    )

    # Run Phase 1 backtest
    logger.info("\n" + "=" * 100)
    logger.info("Running PHASE 1 strategy (with filters)...")
    logger.info("=" * 100)

    phase1_engine = BacktestEngine(initial_capital=args.capital)
    phase1_result = phase1_engine.run_backtest(
        data=data,
        strategy_func=phase1_strategy,
        strategy_name="Phase 1 (Baseline + GATEKEEPER + VALIDATOR + ATR)",
    )

    # Print comparison
    print_comparison_report(baseline_result, phase1_result)


if __name__ == "__main__":
    asyncio.run(main())
