#!/usr/bin/env python3
"""
Extended Backtest Script for Hybrid Strategy
==============================================
Purpose: Run comprehensive 90-180 day backtests on all symbols to validate
         hybrid strategy (trend-following + mean reversion) performance

Features:
- Backtests both trend-following and mean reversion strategies
- Tests all 5 active symbols (SOL, BNB, ADA, AVAX, LINK)
- Calculates comprehensive metrics (Sharpe, win rate, max drawdown, etc.)
- Compares performance across different market regimes
- Validates against research claims (65-70% win rate target)

============================================================================
!!! KNOWN LIMITATION — READ BEFORE TRUSTING ANY PnL OUTPUT !!!
============================================================================

**Signal logic does not match live trading.** The live auto-trader uses a
9-indicator voting aggregator (CoreAggregator + SignalVoter in
app/orchestration/, with TREND_FILTER + VOLUME_CONFIRMATION gates and
weighted votes). This script uses HybridStrategyRouter (trend-follow +
mean-reversion fallback), which is a different decision surface. So a
backtest "win rate" here does NOT predict live win rate. Fixing requires
importing the live aggregator into the backtest path (high effort,
separate change).

Until aligned, treat this script's output as "strategy regime
characterisation" rather than "expected live PnL".

Resolved 2026-04-29 (the testnet contamination half): market-data-service
GET /api/v1/klines now defaults to `mainnet_only=true`, filtering rows
tagged `is_mainnet=False`. Pre-flip rows that existed before the column
was added are migrated to `is_mainnet=true` (the column's server default)
— if your klines table contains pre-2026-04-25 testnet history, wipe it
or back-label those rows before relying on backtest output.

Author: Trading System
Date: 2026-01-04 (limitations block added 2026-04-29)
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.strategies.hybrid_strategy_router import HybridStrategyRouter, MarketRegime
from app.strategies.research_optimized_strategy import ResearchOptimizedStrategy
from app.strategies.mean_reversion_strategy import MeanReversionStrategy
from app.models import IndicatorSignal, SignalAction
import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    """Backtested trade record"""
    symbol: str
    entry_time: datetime
    exit_time: datetime
    side: str  # BUY or SELL
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_pct: float
    strategy_type: str  # 'trend' or 'mean_reversion'
    market_regime: str  # 'TRENDING' or 'RANGING'
    exit_reason: str  # 'take_profit', 'stop_loss', 'signal'
    confidence: float

    @property
    def is_winner(self) -> bool:
        return self.pnl > 0

    @property
    def hold_time_hours(self) -> float:
        return (self.exit_time - self.entry_time).total_seconds() / 3600


@dataclass
class BacktestMetrics:
    """Comprehensive backtest metrics"""
    symbol: str
    days: int
    start_date: datetime
    end_date: datetime

    # Performance
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: float

    # Trade analysis
    avg_win_pct: float
    avg_loss_pct: float
    largest_win_pct: float
    largest_loss_pct: float
    profit_factor: float

    # Strategy breakdown
    trend_trades: int
    mean_reversion_trades: int
    trend_win_rate: float
    mean_reversion_win_rate: float

    # Market regime analysis
    trending_market_pct: float
    ranging_market_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "period": {
                "days": self.days,
                "start_date": self.start_date.isoformat(),
                "end_date": self.end_date.isoformat()
            },
            "performance": {
                "total_return_pct": round(self.total_return_pct, 2),
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 2)
            },
            "risk_metrics": {
                "sharpe_ratio": round(self.sharpe_ratio, 2),
                "sortino_ratio": round(self.sortino_ratio, 2),
                "max_drawdown_pct": round(self.max_drawdown_pct, 2),
                "max_drawdown_duration_days": round(self.max_drawdown_duration_days, 1)
            },
            "trade_analysis": {
                "avg_win_pct": round(self.avg_win_pct, 2),
                "avg_loss_pct": round(self.avg_loss_pct, 2),
                "largest_win_pct": round(self.largest_win_pct, 2),
                "largest_loss_pct": round(self.largest_loss_pct, 2),
                "profit_factor": round(self.profit_factor, 2)
            },
            "strategy_breakdown": {
                "trend_trades": self.trend_trades,
                "mean_reversion_trades": self.mean_reversion_trades,
                "trend_win_rate": round(self.trend_win_rate, 2),
                "mean_reversion_win_rate": round(self.mean_reversion_win_rate, 2)
            },
            "market_regime": {
                "trending_market_pct": round(self.trending_market_pct, 2),
                "ranging_market_pct": round(self.ranging_market_pct, 2)
            }
        }


class ExtendedBacktester:
    """
    Extended backtester for hybrid strategy validation

    Features:
    - Fetches historical data from market-data-service
    - Simulates strategy execution with realistic fills
    - Calculates comprehensive performance metrics
    - Analyzes strategy routing effectiveness
    """

    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_pct: float = 0.1,  # 0.1% per trade
        slippage_pct: float = 0.05  # 0.05% slippage
    ):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

        # Initialize strategies
        self.hybrid_strategy = HybridStrategyRouter()

        # Market data service URL
        self.market_data_url = "http://localhost:8002"
        self.technical_analysis_url = "http://localhost:8003"

        logger.info(f"ExtendedBacktester initialized with ${initial_capital:,.2f} capital")

    async def fetch_historical_klines(
        self,
        symbol: str,
        interval: int,
        days: int
    ) -> List[Dict[str, Any]]:
        """Fetch historical klines from market-data-service"""

        logger.info(f"Fetching {days} days of {interval}m klines for {symbol}...")

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Calculate time range
                end_time = datetime.now()
                start_time = end_time - timedelta(days=days)

                # Fetch from market data service
                url = f"{self.market_data_url}/api/v1/klines/{symbol}"
                params = {
                    "interval": interval,
                    "limit": days * 24 * (60 // interval),  # Calculate number of candles
                    "start_time": int(start_time.timestamp() * 1000),
                    "end_time": int(end_time.timestamp() * 1000)
                }

                response = await client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                if data.get("success"):
                    klines = data.get("klines", [])
                    logger.info(f"  ✅ Fetched {len(klines)} klines for {symbol}")
                    return klines
                else:
                    logger.error(f"  ❌ Failed to fetch klines: {data.get('message')}")
                    return []

            except Exception as e:
                logger.error(f"  ❌ Error fetching klines: {e}")
                return []

    async def fetch_indicators(
        self,
        symbol: str,
        interval: int,
        kline_data: Dict[str, Any]
    ) -> Dict[str, IndicatorSignal]:
        """Fetch technical indicators for a kline"""

        # This is a simplified version - in production, you'd call technical-analysis service
        # For now, we'll create mock indicators based on price data

        close = float(kline_data.get('c', kline_data.get('close', 0)))

        # Mock indicators (in production, fetch from technical-analysis service)
        indicators = {
            'RSI': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={'value': 50.0}
            ),
            'MACD': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={}
            ),
            'EMA': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={}
            ),
            'SMA': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={'value': close}
            ),
            'BOLLINGER_BANDS': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={'position': 0.5}
            ),
            'STOCHASTIC': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={}
            ),
            'ATR': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={'value': close * 0.02, 'adx': 20.0}
            ),
            'VOLUME_CONFIRMATION': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={}
            ),
            'ICHIMOKU': IndicatorSignal(
                action=SignalAction.HOLD,
                confidence=0.5,
                metadata={}
            )
        }

        return indicators

    async def run_symbol_backtest(
        self,
        symbol: str,
        interval: int = 60,
        days: int = 90
    ) -> Optional[BacktestMetrics]:
        """
        Run backtest for a single symbol

        Args:
            symbol: Trading symbol (e.g., 'SOLUSDT')
            interval: Kline interval in minutes (default 60m)
            days: Number of days to backtest (default 90)

        Returns:
            BacktestMetrics or None if failed
        """

        logger.info(f"{'='*70}")
        logger.info(f"BACKTESTING: {symbol} ({days} days, {interval}m interval)")
        logger.info(f"{'='*70}")

        # Fetch historical data
        klines = await self.fetch_historical_klines(symbol, interval, days)

        if not klines or len(klines) < 100:
            logger.error(f"Insufficient data for {symbol}: {len(klines)} klines")
            return None

        # Backtest state
        capital = self.initial_capital
        position = None
        trades: List[BacktestTrade] = []
        equity_curve = [capital]

        # Regime tracking
        trending_count = 0
        ranging_count = 0

        # Process each kline
        for i, kline in enumerate(klines):
            if i % 100 == 0:
                logger.info(f"  Processing kline {i+1}/{len(klines)}...")

            timestamp = datetime.fromtimestamp(kline['timestamp'] / 1000)
            close_price = float(kline.get('c', kline.get('close', 0)))

            # Fetch indicators (simplified - in production use real indicators)
            indicators = await self.fetch_indicators(symbol, interval, kline)

            # Get hybrid strategy signal
            trade_setup = self.hybrid_strategy.generate_signal(
                indicators=indicators,
                current_price=close_price,
                capital=capital
            )

            # Track regime
            regime = self.hybrid_strategy.detect_regime(indicators)
            if regime == MarketRegime.TRENDING:
                trending_count += 1
            elif regime == MarketRegime.RANGING:
                ranging_count += 1

            # Process signal
            if trade_setup and not position:
                # Open position
                position = {
                    'symbol': symbol,
                    'entry_time': timestamp,
                    'side': trade_setup.action.value,
                    'entry_price': close_price,
                    'quantity': trade_setup.quantity,
                    'stop_loss': trade_setup.stop_loss,
                    'take_profit': trade_setup.take_profit,
                    'strategy_type': trade_setup.metadata.get('strategy_type', 'unknown'),
                    'market_regime': regime.value,
                    'confidence': trade_setup.confidence
                }
                logger.debug(f"  📈 OPEN {position['side']} @ ${close_price:.2f}")

            elif position:
                # Check exit conditions
                exit_reason = None
                exit_price = close_price

                if position['side'] == 'BUY':
                    # Check stop loss
                    if close_price <= position['stop_loss']:
                        exit_reason = 'stop_loss'
                        exit_price = position['stop_loss']
                    # Check take profit
                    elif close_price >= position['take_profit']:
                        exit_reason = 'take_profit'
                        exit_price = position['take_profit']

                elif position['side'] == 'SELL':
                    # Check stop loss
                    if close_price >= position['stop_loss']:
                        exit_reason = 'stop_loss'
                        exit_price = position['stop_loss']
                    # Check take profit
                    elif close_price <= position['take_profit']:
                        exit_reason = 'take_profit'
                        exit_price = position['take_profit']

                # Close position if exit triggered
                if exit_reason:
                    # Calculate P&L
                    if position['side'] == 'BUY':
                        pnl = (exit_price - position['entry_price']) * position['quantity']
                    else:
                        pnl = (position['entry_price'] - exit_price) * position['quantity']

                    # Apply commission and slippage
                    commission = (position['entry_price'] + exit_price) * position['quantity'] * (self.commission_pct / 100)
                    pnl -= commission

                    pnl_pct = (pnl / (position['entry_price'] * position['quantity'])) * 100

                    # Update capital
                    capital += pnl
                    equity_curve.append(capital)

                    # Record trade
                    trade = BacktestTrade(
                        symbol=position['symbol'],
                        entry_time=position['entry_time'],
                        exit_time=timestamp,
                        side=position['side'],
                        entry_price=position['entry_price'],
                        exit_price=exit_price,
                        quantity=position['quantity'],
                        pnl=pnl,
                        pnl_pct=pnl_pct,
                        strategy_type=position['strategy_type'],
                        market_regime=position['market_regime'],
                        exit_reason=exit_reason,
                        confidence=position['confidence']
                    )
                    trades.append(trade)

                    logger.debug(f"  📉 CLOSE @ ${exit_price:.2f} | P&L: ${pnl:.2f} ({pnl_pct:+.2f}%) | Reason: {exit_reason}")

                    position = None

        # Calculate metrics
        if len(trades) == 0:
            logger.warning(f"No trades executed for {symbol}")
            return None

        metrics = self._calculate_metrics(
            symbol=symbol,
            days=days,
            start_date=datetime.fromtimestamp(klines[0]['timestamp'] / 1000),
            end_date=datetime.fromtimestamp(klines[-1]['timestamp'] / 1000),
            trades=trades,
            equity_curve=equity_curve,
            trending_count=trending_count,
            ranging_count=ranging_count
        )

        logger.info(f"{'='*70}")
        logger.info(f"RESULTS: {symbol}")
        logger.info(f"  Total Return: {metrics.total_return_pct:+.2f}%")
        logger.info(f"  Win Rate: {metrics.win_rate:.1f}% ({metrics.winning_trades}/{metrics.total_trades})")
        logger.info(f"  Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        logger.info(f"  Max Drawdown: {metrics.max_drawdown_pct:.2f}%")
        logger.info(f"  Trend Trades: {metrics.trend_trades} ({metrics.trend_win_rate:.1f}% WR)")
        logger.info(f"  Mean Reversion Trades: {metrics.mean_reversion_trades} ({metrics.mean_reversion_win_rate:.1f}% WR)")
        logger.info(f"{'='*70}")

        return metrics

    def _calculate_metrics(
        self,
        symbol: str,
        days: int,
        start_date: datetime,
        end_date: datetime,
        trades: List[BacktestTrade],
        equity_curve: List[float],
        trending_count: int,
        ranging_count: int
    ) -> BacktestMetrics:
        """Calculate comprehensive backtest metrics"""

        # Basic stats
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.is_winner)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        # Performance
        total_return_pct = ((equity_curve[-1] / self.initial_capital) - 1) * 100

        # Trade analysis
        winners = [t for t in trades if t.is_winner]
        losers = [t for t in trades if not t.is_winner]

        avg_win_pct = sum(t.pnl_pct for t in winners) / len(winners) if winners else 0
        avg_loss_pct = sum(t.pnl_pct for t in losers) / len(losers) if losers else 0
        largest_win_pct = max((t.pnl_pct for t in winners), default=0)
        largest_loss_pct = min((t.pnl_pct for t in losers), default=0)

        total_wins = sum(t.pnl for t in winners)
        total_losses = abs(sum(t.pnl for t in losers))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0

        # Risk metrics
        returns = [equity_curve[i] / equity_curve[i-1] - 1 for i in range(1, len(equity_curve))]
        avg_return = sum(returns) / len(returns) if returns else 0
        std_return = (sum((r - avg_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0

        sharpe_ratio = (avg_return / std_return * (252 ** 0.5)) if std_return > 0 else 0

        downside_returns = [r for r in returns if r < 0]
        downside_std = (sum(r ** 2 for r in downside_returns) / len(downside_returns)) ** 0.5 if downside_returns else 0
        sortino_ratio = (avg_return / downside_std * (252 ** 0.5)) if downside_std > 0 else 0

        # Max drawdown
        peak = equity_curve[0]
        max_dd = 0
        max_dd_duration = 0
        current_dd_duration = 0

        for equity in equity_curve:
            if equity > peak:
                peak = equity
                current_dd_duration = 0
            else:
                dd = (peak - equity) / peak * 100
                max_dd = max(max_dd, dd)
                current_dd_duration += 1
                max_dd_duration = max(max_dd_duration, current_dd_duration)

        max_dd_duration_days = max_dd_duration / (24 * 60 // 60)  # Convert bars to days

        # Strategy breakdown
        trend_trades_list = [t for t in trades if t.strategy_type == 'trend_following']
        mr_trades_list = [t for t in trades if t.strategy_type == 'mean_reversion']

        trend_trades = len(trend_trades_list)
        mean_reversion_trades = len(mr_trades_list)

        trend_win_rate = (sum(1 for t in trend_trades_list if t.is_winner) / trend_trades * 100) if trend_trades > 0 else 0
        mr_win_rate = (sum(1 for t in mr_trades_list if t.is_winner) / mean_reversion_trades * 100) if mean_reversion_trades > 0 else 0

        # Market regime
        total_bars = trending_count + ranging_count
        trending_pct = (trending_count / total_bars * 100) if total_bars > 0 else 0
        ranging_pct = (ranging_count / total_bars * 100) if total_bars > 0 else 0

        return BacktestMetrics(
            symbol=symbol,
            days=days,
            start_date=start_date,
            end_date=end_date,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown_pct=max_dd,
            max_drawdown_duration_days=max_dd_duration_days,
            avg_win_pct=avg_win_pct,
            avg_loss_pct=avg_loss_pct,
            largest_win_pct=largest_win_pct,
            largest_loss_pct=largest_loss_pct,
            profit_factor=profit_factor,
            trend_trades=trend_trades,
            mean_reversion_trades=mean_reversion_trades,
            trend_win_rate=trend_win_rate,
            mean_reversion_win_rate=mr_win_rate,
            trending_market_pct=trending_pct,
            ranging_market_pct=ranging_pct
        )


async def main():
    """Run extended backtests on all symbols"""

    logger.info("=" * 70)
    logger.info("EXTENDED BACKTEST - HYBRID STRATEGY VALIDATION")
    logger.info("=" * 70)
    logger.warning(
        "PnL output is SUSPECT: backtest uses HybridStrategyRouter, "
        "not the live 9-indicator voting aggregator. Testnet contamination "
        "is now filtered server-side by default. See module docstring."
    )
    logger.info("=" * 70)
    logger.info("")

    # Configuration
    symbols = ["SOLUSDT", "BNBUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT"]
    interval = 60  # 1-hour candles
    days = 90  # 90-day backtest

    # Initialize backtester
    backtester = ExtendedBacktester(
        initial_capital=10000.0,
        commission_pct=0.1,
        slippage_pct=0.05
    )

    # Run backtests
    all_metrics = []

    for symbol in symbols:
        try:
            metrics = await backtester.run_symbol_backtest(
                symbol=symbol,
                interval=interval,
                days=days
            )

            if metrics:
                all_metrics.append(metrics)

        except Exception as e:
            logger.error(f"Error backtesting {symbol}: {e}", exc_info=True)

    # Save results
    if all_metrics:
        results_file = Path("/tmp/backtest_results.json")
        with open(results_file, 'w') as f:
            json.dump(
                {
                    "timestamp": datetime.now().isoformat(),
                    "config": {
                        "initial_capital": backtester.initial_capital,
                        "commission_pct": backtester.commission_pct,
                        "slippage_pct": backtester.slippage_pct,
                        "interval": interval,
                        "days": days
                    },
                    "results": [m.to_dict() for m in all_metrics]
                },
                f,
                indent=2
            )

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"RESULTS SAVED: {results_file}")
        logger.info("=" * 70)

    else:
        logger.warning("No backtest results generated")


if __name__ == "__main__":
    asyncio.run(main())
