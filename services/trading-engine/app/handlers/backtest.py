"""
Backtest Handler - API handlers for backtesting endpoints
Provides endpoints to run backtests, list available strategies, and get results.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from decimal import Decimal
from pydantic import BaseModel, Field

from app.backtesting import (
    BacktestEngine,
    BacktestConfig,
    BacktestResult,
    StrategyBase,
    SignalType,
    RealDataProvider,
    DataProviderError
)
from app.backtesting.strategy_base import (
    OHLCV,
    RSIMomentumStrategy,
    RegimeAdaptiveStrategy
)
from app.backtesting.backtest_engine import generate_sample_data
from app.backtesting.performance_metrics import PerformanceMetrics
from app.trading_enhancements.walk_forward_tester import (
    WalkForwardTester,
    WFEConfig,
    TradeData
)

logger = logging.getLogger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class BacktestRequest(BaseModel):
    """Request model for running a backtest"""
    strategy: str = Field(..., description="Strategy name: 'rsi_momentum' or 'regime_adaptive'")
    symbol: str = Field(default="BTCUSDT", description="Trading symbol")
    initial_equity: float = Field(default=10000.0, description="Initial equity")
    commission_pct: float = Field(default=0.1, description="Commission percentage")
    slippage_pct: float = Field(default=0.05, description="Slippage percentage")
    position_size_pct: float = Field(default=10.0, description="Position size as % of equity")

    # Strategy parameters
    rsi_period: int = Field(default=14, description="RSI period (for RSI strategies)")
    rsi_oversold: float = Field(default=30.0, description="RSI oversold threshold")
    rsi_overbought: float = Field(default=70.0, description="RSI overbought threshold")
    atr_multiplier: float = Field(default=2.0, description="ATR multiplier for stop loss")

    # Data parameters
    days: int = Field(default=90, description="Number of days to backtest")
    use_sample_data: bool = Field(default=True, description="Use generated sample data")


class StrategyInfo(BaseModel):
    """Information about an available strategy"""
    name: str
    description: str
    parameters: Dict[str, Any]
    default_values: Dict[str, Any]


class BacktestSummary(BaseModel):
    """Summary of backtest results"""
    strategy_name: str
    symbol: str
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    profit_factor: float
    initial_equity: float
    final_equity: float


# =============================================================================
# Available Strategies Registry
# =============================================================================

AVAILABLE_STRATEGIES = {
    "rsi_momentum": {
        "name": "RSI Momentum Strategy",
        "description": "Buys when RSI crosses above oversold, sells when RSI crosses below overbought",
        "class": RSIMomentumStrategy,
        "parameters": {
            "rsi_period": "RSI calculation period",
            "rsi_oversold": "Oversold threshold (default 30)",
            "rsi_overbought": "Overbought threshold (default 70)",
            "atr_multiplier": "ATR multiplier for stop loss"
        },
        "default_values": {
            "rsi_period": 14,
            "rsi_oversold": 30.0,
            "rsi_overbought": 70.0,
            "atr_multiplier": 2.0
        }
    },
    "regime_adaptive": {
        "name": "Regime-Adaptive RSI Strategy",
        "description": "Uses Hurst exponent to detect market regime and adjusts RSI thresholds accordingly",
        "class": RegimeAdaptiveStrategy,
        "parameters": {
            "rsi_period": "RSI calculation period",
            "hurst_lookback": "Lookback period for Hurst exponent",
            "atr_multiplier": "ATR multiplier for stop loss"
        },
        "default_values": {
            "rsi_period": 6,
            "hurst_lookback": 100,
            "atr_multiplier": 2.5
        }
    }
}


# =============================================================================
# Handler Functions
# =============================================================================

async def list_strategies() -> Dict[str, Any]:
    """
    List all available backtesting strategies

    Returns:
        Dictionary with available strategies and their configurations
    """
    strategies = []

    for key, info in AVAILABLE_STRATEGIES.items():
        strategies.append({
            "id": key,
            "name": info["name"],
            "description": info["description"],
            "parameters": info["parameters"],
            "default_values": info["default_values"]
        })

    return {
        "success": True,
        "strategies_count": len(strategies),
        "strategies": strategies
    }


async def run_backtest(request: BacktestRequest) -> Dict[str, Any]:
    """
    Run a backtest with the specified strategy and parameters

    Args:
        request: Backtest configuration request

    Returns:
        Complete backtest results including metrics and trade list
    """
    logger.info(f"Starting backtest: {request.strategy} on {request.symbol}, {request.days} days")

    # Validate strategy
    if request.strategy not in AVAILABLE_STRATEGIES:
        return {
            "success": False,
            "error": f"Unknown strategy: {request.strategy}",
            "available_strategies": list(AVAILABLE_STRATEGIES.keys())
        }

    try:
        # Create strategy instance
        strategy_info = AVAILABLE_STRATEGIES[request.strategy]

        if request.strategy == "rsi_momentum":
            strategy = RSIMomentumStrategy(
                symbol=request.symbol,
                rsi_period=request.rsi_period,
                rsi_oversold=request.rsi_oversold,
                rsi_overbought=request.rsi_overbought,
                atr_multiplier=request.atr_multiplier
            )
        elif request.strategy == "regime_adaptive":
            strategy = RegimeAdaptiveStrategy(
                symbol=request.symbol,
                rsi_period=request.rsi_period,
                hurst_lookback=100,  # Fixed for now
                atr_multiplier=request.atr_multiplier
            )
        else:
            return {
                "success": False,
                "error": f"Strategy {request.strategy} not implemented"
            }

        # Create backtest config
        config = BacktestConfig(
            initial_equity=request.initial_equity,
            commission_pct=request.commission_pct,
            slippage_pct=request.slippage_pct,
            position_size_pct=request.position_size_pct
        )

        # Get data
        if request.use_sample_data:
            data = generate_sample_data(
                symbol=request.symbol,
                days=request.days,
                start_price=50000.0,  # Default BTC price
                volatility=0.02
            )
        else:
            # Fetch real data from market-data-service
            data_provider = RealDataProvider()
            try:
                # Check service health first
                if not await data_provider.health_check():
                    return {
                        "success": False,
                        "error": "Market data service is not available. "
                                 "Please ensure market-data-service is running."
                    }

                # Fetch historical data
                data = await data_provider.get_historical_data(
                    symbol=request.symbol,
                    interval="60",  # 1-hour candles for backtesting
                    days=request.days
                )

                if not data:
                    return {
                        "success": False,
                        "error": f"No historical data available for {request.symbol}. "
                                 f"Please collect data first using market-data-service."
                    }

                logger.info(f"Fetched {len(data)} bars of real data for backtest")

            except DataProviderError as e:
                logger.error(f"Failed to fetch real data: {e}")
                return {
                    "success": False,
                    "error": f"Failed to fetch real data: {str(e)}"
                }
            finally:
                await data_provider.close()

        # Run backtest
        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Format response
        response = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "strategy": request.strategy,
                "symbol": request.symbol,
                "days": request.days,
                "initial_equity": request.initial_equity
            },
            "summary": {
                "strategy_name": result.strategy_name,
                "symbol": result.symbol,
                "total_return_pct": round(result.metrics.total_return_pct, 2),
                "cagr": round(result.metrics.cagr, 2),
                "sharpe_ratio": round(result.metrics.sharpe_ratio, 2),
                "sortino_ratio": round(result.metrics.sortino_ratio, 2),
                "max_drawdown_pct": round(result.metrics.max_drawdown_pct, 2),
                "volatility": round(result.metrics.volatility, 2),
                "total_trades": result.metrics.total_trades,
                "winning_trades": result.metrics.winning_trades,
                "losing_trades": result.metrics.losing_trades,
                "win_rate": round(result.metrics.win_rate, 2),
                "profit_factor": round(result.metrics.profit_factor, 2),
                "avg_win": round(result.metrics.avg_win, 2),
                "avg_loss": round(result.metrics.avg_loss, 2),
                "largest_win": round(result.metrics.largest_win, 2),
                "largest_loss": round(result.metrics.largest_loss, 2),
                "initial_equity": result.metrics.initial_equity,
                "final_equity": round(result.metrics.final_equity, 2),
                "peak_equity": round(result.metrics.peak_equity, 2)
            },
            "signals": {
                "generated": result.signals_generated,
                "executed": result.signals_executed
            },
            "trades": [t.to_dict() for t in result.trades[:50]],  # Limit to 50 trades
            "trades_total": len(result.trades),
            "equity_curve": {
                "start": round(result.equity_curve[0], 2) if result.equity_curve else 0,
                "end": round(result.equity_curve[-1], 2) if result.equity_curve else 0,
                "min": round(min(result.equity_curve), 2) if result.equity_curve else 0,
                "max": round(max(result.equity_curve), 2) if result.equity_curve else 0,
                "data_points": len(result.equity_curve)
            },
            "config": {
                "commission_pct": config.commission_pct,
                "slippage_pct": config.slippage_pct,
                "position_size_pct": config.position_size_pct,
                "use_stop_loss": config.use_stop_loss,
                "use_take_profit": config.use_take_profit
            }
        }

        logger.info(
            f"Backtest complete: {result.metrics.total_trades} trades, "
            f"Return: {result.metrics.total_return_pct:.2f}%, "
            f"Sharpe: {result.metrics.sharpe_ratio:.2f}"
        )

        return response

    except Exception as e:
        logger.error(f"Backtest failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


async def get_backtest_quick_run(
    strategy: str,
    symbol: str = "BTCUSDT",
    days: int = 30
) -> Dict[str, Any]:
    """
    Quick backtest with default parameters

    Args:
        strategy: Strategy name
        symbol: Trading symbol
        days: Number of days

    Returns:
        Backtest summary
    """
    request = BacktestRequest(
        strategy=strategy,
        symbol=symbol,
        days=days,
        use_sample_data=True
    )

    return await run_backtest(request)


async def compare_strategies(
    symbol: str = "BTCUSDT",
    days: int = 90
) -> Dict[str, Any]:
    """
    Compare all available strategies on the same data

    Args:
        symbol: Trading symbol
        days: Number of days to backtest

    Returns:
        Comparison of all strategies
    """
    logger.info(f"Comparing strategies on {symbol} for {days} days")

    # Generate data once for fair comparison
    data = generate_sample_data(
        symbol=symbol,
        days=days,
        start_price=50000.0,
        volatility=0.02
    )

    config = BacktestConfig(
        initial_equity=10000.0,
        commission_pct=0.1,
        slippage_pct=0.05
    )

    results = []

    for strategy_id, strategy_info in AVAILABLE_STRATEGIES.items():
        try:
            # Create strategy with default params
            if strategy_id == "rsi_momentum":
                strategy = RSIMomentumStrategy(symbol=symbol)
            elif strategy_id == "regime_adaptive":
                strategy = RegimeAdaptiveStrategy(symbol=symbol)
            else:
                continue

            # Run backtest
            engine = BacktestEngine(config)
            result = engine.run(strategy, data)

            results.append({
                "strategy_id": strategy_id,
                "strategy_name": result.strategy_name,
                "total_return_pct": round(result.metrics.total_return_pct, 2),
                "sharpe_ratio": round(result.metrics.sharpe_ratio, 2),
                "sortino_ratio": round(result.metrics.sortino_ratio, 2),
                "max_drawdown_pct": round(result.metrics.max_drawdown_pct, 2),
                "total_trades": result.metrics.total_trades,
                "win_rate": round(result.metrics.win_rate, 2),
                "profit_factor": round(result.metrics.profit_factor, 2),
                "final_equity": round(result.metrics.final_equity, 2)
            })

        except Exception as e:
            logger.error(f"Error running {strategy_id}: {e}")
            results.append({
                "strategy_id": strategy_id,
                "error": str(e)
            })

    # Sort by return
    successful = [r for r in results if "error" not in r]
    successful.sort(key=lambda x: x["total_return_pct"], reverse=True)

    return {
        "success": True,
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "days": days,
        "data_bars": len(data),
        "strategies_compared": len(results),
        "best_strategy": successful[0]["strategy_id"] if successful else None,
        "results": results,
        "ranking": {
            "by_return": [r["strategy_id"] for r in successful],
            "by_sharpe": sorted(
                [r for r in successful],
                key=lambda x: x["sharpe_ratio"],
                reverse=True
            )[:3] if successful else []
        }
    }


async def get_equity_curve(
    strategy: str,
    symbol: str = "BTCUSDT",
    days: int = 30,
    sample_rate: int = 24
) -> Dict[str, Any]:
    """
    Get detailed equity curve data for charting

    Args:
        strategy: Strategy name
        symbol: Trading symbol
        days: Number of days
        sample_rate: Sample every N points (default 24 = daily for hourly data)

    Returns:
        Equity curve data points with timestamps
    """
    request = BacktestRequest(
        strategy=strategy,
        symbol=symbol,
        days=days,
        use_sample_data=True
    )

    # Validate strategy
    if strategy not in AVAILABLE_STRATEGIES:
        return {
            "success": False,
            "error": f"Unknown strategy: {strategy}"
        }

    try:
        # Create strategy
        if strategy == "rsi_momentum":
            strat = RSIMomentumStrategy(symbol=symbol)
        elif strategy == "regime_adaptive":
            strat = RegimeAdaptiveStrategy(symbol=symbol)
        else:
            return {"success": False, "error": "Strategy not implemented"}

        # Generate data and run
        data = generate_sample_data(symbol=symbol, days=days)
        engine = BacktestEngine()
        result = engine.run(strat, data)

        # Sample equity curve
        sampled_equity = []
        for i in range(0, len(result.equity_curve), sample_rate):
            sampled_equity.append({
                "timestamp": result.equity_timestamps[i].isoformat(),
                "equity": round(result.equity_curve[i], 2)
            })

        # Add final point if not included
        if len(result.equity_curve) % sample_rate != 0:
            sampled_equity.append({
                "timestamp": result.equity_timestamps[-1].isoformat(),
                "equity": round(result.equity_curve[-1], 2)
            })

        return {
            "success": True,
            "strategy": strategy,
            "symbol": symbol,
            "days": days,
            "sample_rate": sample_rate,
            "data_points": len(sampled_equity),
            "equity_curve": sampled_equity,
            "summary": {
                "start_equity": round(result.equity_curve[0], 2),
                "end_equity": round(result.equity_curve[-1], 2),
                "peak_equity": round(max(result.equity_curve), 2),
                "min_equity": round(min(result.equity_curve), 2),
                "total_return_pct": round(result.metrics.total_return_pct, 2)
            }
        }

    except Exception as e:
        logger.error(f"Error getting equity curve: {e}")
        return {"success": False, "error": str(e)}


# =============================================================================
# Walk-Forward Analysis Integration
# =============================================================================

class WalkForwardRequest(BaseModel):
    """Request model for walk-forward analysis"""
    strategy: str = Field(..., description="Strategy name")
    symbol: str = Field(default="BTCUSDT", description="Trading symbol")
    days: int = Field(default=180, description="Number of days for analysis (min 90 recommended)")
    use_sample_data: bool = Field(default=True, description="Use generated sample data")

    # Walk-forward configuration
    num_windows: int = Field(default=5, description="Number of walk-forward windows")
    in_sample_pct: float = Field(default=0.70, ge=0.5, le=0.9, description="In-sample percentage")

    # Backtest configuration
    initial_equity: float = Field(default=10000.0, description="Initial equity")
    commission_pct: float = Field(default=0.1, description="Commission percentage")
    slippage_pct: float = Field(default=0.05, description="Slippage percentage")

    # Strategy parameters
    rsi_period: int = Field(default=14, description="RSI period")
    rsi_oversold: float = Field(default=30.0, description="RSI oversold threshold")
    rsi_overbought: float = Field(default=70.0, description="RSI overbought threshold")
    atr_multiplier: float = Field(default=2.0, description="ATR multiplier for stop loss")


def _convert_trades_to_trade_data(
    trades: List,
    strategy_name: str
) -> List[TradeData]:
    """
    Convert backtest Trade objects to TradeData for walk-forward analysis

    Args:
        trades: List of Trade objects from backtest
        strategy_name: Name of the strategy

    Returns:
        List of TradeData objects
    """
    trade_data_list = []

    for trade in trades:
        # Calculate quantity value for fees estimation
        trade_value = trade.entry_price * trade.quantity

        trade_data = TradeData(
            trade_id=trade.trade_id,
            symbol=trade.symbol,
            side=trade.side,
            entry_time=trade.entry_time,
            exit_time=trade.exit_time,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            fees=trade.commission,
            strategy=strategy_name
        )
        trade_data_list.append(trade_data)

    return trade_data_list


async def run_walk_forward_analysis(request: WalkForwardRequest) -> Dict[str, Any]:
    """
    Run backtest with walk-forward efficiency analysis

    This combines backtesting with walk-forward optimization to validate
    strategy robustness and detect overfitting.

    Args:
        request: Walk-forward analysis request

    Returns:
        Complete analysis including backtest results and WFE report
    """
    logger.info(
        f"Starting walk-forward analysis: {request.strategy} on {request.symbol}, "
        f"{request.days} days, {request.num_windows} windows"
    )

    # Validate strategy
    if request.strategy not in AVAILABLE_STRATEGIES:
        return {
            "success": False,
            "error": f"Unknown strategy: {request.strategy}",
            "available_strategies": list(AVAILABLE_STRATEGIES.keys())
        }

    try:
        # Create strategy instance
        if request.strategy == "rsi_momentum":
            strategy = RSIMomentumStrategy(
                symbol=request.symbol,
                rsi_period=request.rsi_period,
                rsi_oversold=request.rsi_oversold,
                rsi_overbought=request.rsi_overbought,
                atr_multiplier=request.atr_multiplier
            )
        elif request.strategy == "regime_adaptive":
            strategy = RegimeAdaptiveStrategy(
                symbol=request.symbol,
                rsi_period=request.rsi_period,
                hurst_lookback=100,
                atr_multiplier=request.atr_multiplier
            )
        else:
            return {"success": False, "error": f"Strategy {request.strategy} not implemented"}

        # Create backtest config
        config = BacktestConfig(
            initial_equity=request.initial_equity,
            commission_pct=request.commission_pct,
            slippage_pct=request.slippage_pct
        )

        # Get data
        if request.use_sample_data:
            data = generate_sample_data(
                symbol=request.symbol,
                days=request.days,
                start_price=50000.0,
                volatility=0.02
            )
        else:
            # Fetch real data from market-data-service
            data_provider = RealDataProvider()
            try:
                if not await data_provider.health_check():
                    return {
                        "success": False,
                        "error": "Market data service is not available"
                    }

                data = await data_provider.get_historical_data(
                    symbol=request.symbol,
                    interval="60",
                    days=request.days
                )

                if not data:
                    return {
                        "success": False,
                        "error": f"No historical data available for {request.symbol}"
                    }
            except DataProviderError as e:
                return {"success": False, "error": f"Failed to fetch data: {str(e)}"}
            finally:
                await data_provider.close()

        # Run backtest
        engine = BacktestEngine(config)
        result = engine.run(strategy, data)

        # Check if we have enough trades for walk-forward analysis
        if len(result.trades) < 30:
            return {
                "success": False,
                "error": f"Insufficient trades ({len(result.trades)}) for walk-forward analysis. "
                         f"Need at least 30 trades. Try increasing the days parameter."
            }

        # Convert trades to TradeData format
        trade_data = _convert_trades_to_trade_data(result.trades, strategy.get_name())

        # Configure walk-forward tester
        wfe_config = WFEConfig(
            in_sample_pct=request.in_sample_pct,
            out_of_sample_pct=1.0 - request.in_sample_pct,
            rolling_windows=request.num_windows
        )

        # Run walk-forward analysis
        from app.trading_enhancements.walk_forward_tester import WalkForwardTester

        tester = WalkForwardTester(config=wfe_config, strategy_name=strategy.get_name())
        tester.add_trades(trade_data)
        window_results = tester.run_walk_forward_test()
        report = tester.get_robustness_report()

        # Format response
        response = {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "request": {
                "strategy": request.strategy,
                "symbol": request.symbol,
                "days": request.days,
                "num_windows": request.num_windows,
                "in_sample_pct": request.in_sample_pct
            },
            "backtest_summary": {
                "strategy_name": result.strategy_name,
                "symbol": result.symbol,
                "total_return_pct": round(result.metrics.total_return_pct, 2),
                "sharpe_ratio": round(result.metrics.sharpe_ratio, 2),
                "sortino_ratio": round(result.metrics.sortino_ratio, 2),
                "max_drawdown_pct": round(result.metrics.max_drawdown_pct, 2),
                "total_trades": result.metrics.total_trades,
                "win_rate": round(result.metrics.win_rate, 2),
                "profit_factor": round(result.metrics.profit_factor, 2),
                "initial_equity": result.metrics.initial_equity,
                "final_equity": round(result.metrics.final_equity, 2)
            },
            "walk_forward_analysis": {
                "overall_status": report.overall_status.value,
                "is_robust": report.overall_status.value == "robust",
                "total_trades_analyzed": report.total_trades,
                "total_windows": report.total_windows,
                "robust_windows": report.robust_windows,
                "robust_percentage": round(report.robust_percentage, 1),
                "avg_wfe_return": round(report.avg_wfe_return * 100, 1),
                "avg_wfe_sharpe": round(report.avg_wfe_sharpe * 100, 1),
                "avg_wfe_profit_factor": round(report.avg_wfe_profit_factor * 100, 1),
                "statistical_confidence": round(report.overall_confidence, 1),
                "wfe_consistency": round(report.wfe_consistency * 100, 2),
                "recommendations": report.recommendations
            },
            "window_details": [
                {
                    "window": r.window_number,
                    "status": r.status.value,
                    "is_robust": r.is_robust,
                    "trade_count": r.trade_count,
                    "wfe_return_pct": round(r.wfe_return * 100, 1),
                    "wfe_sharpe_pct": round(r.wfe_sharpe * 100, 1),
                    "confidence": round(r.confidence_level, 1),
                    "in_sample": {
                        "return_pct": round(r.in_sample_metrics.total_return, 2),
                        "sharpe": round(r.in_sample_metrics.sharpe_ratio, 2),
                        "win_rate": round(r.in_sample_metrics.win_rate * 100, 1),
                        "trades": r.in_sample_metrics.trade_count
                    },
                    "out_of_sample": {
                        "return_pct": round(r.out_of_sample_metrics.total_return, 2),
                        "sharpe": round(r.out_of_sample_metrics.sharpe_ratio, 2),
                        "win_rate": round(r.out_of_sample_metrics.win_rate * 100, 1),
                        "trades": r.out_of_sample_metrics.trade_count
                    },
                    "notes": r.notes
                }
                for r in window_results
            ],
            "interpretation": _generate_interpretation(report)
        }

        logger.info(
            f"Walk-forward analysis complete: {report.overall_status.value}, "
            f"WFE={report.avg_wfe_return:.1%}, "
            f"{report.robust_windows}/{report.total_windows} robust windows"
        )

        return response

    except Exception as e:
        logger.error(f"Walk-forward analysis failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _generate_interpretation(report) -> Dict[str, Any]:
    """
    Generate human-readable interpretation of walk-forward results

    Args:
        report: RobustnessReport from walk-forward analysis

    Returns:
        Dictionary with interpretation details
    """
    status = report.overall_status.value
    wfe = report.avg_wfe_return

    if status == "robust":
        verdict = "RECOMMENDED FOR LIVE TRADING"
        explanation = (
            f"This strategy shows robust out-of-sample performance with "
            f"Walk-Forward Efficiency of {wfe:.1%}. The strategy's performance "
            f"in testing periods closely matches optimization results, indicating "
            f"low overfitting risk."
        )
        risk_level = "LOW"
    elif status == "marginal":
        verdict = "PROCEED WITH CAUTION"
        explanation = (
            f"This strategy shows marginal robustness with WFE of {wfe:.1%}. "
            f"Performance may degrade in live trading compared to backtest results. "
            f"Consider paper trading for an extended period before live deployment."
        )
        risk_level = "MEDIUM"
    elif status == "overfit":
        verdict = "NOT RECOMMENDED"
        explanation = (
            f"This strategy shows signs of overfitting with WFE of {wfe:.1%}. "
            f"Out-of-sample performance is significantly worse than in-sample. "
            f"Consider simplifying the strategy or adjusting parameters."
        )
        risk_level = "HIGH"
    else:  # insufficient_data
        verdict = "INSUFFICIENT DATA"
        explanation = (
            f"Not enough trade data ({report.total_trades} trades) for reliable "
            f"walk-forward analysis. Need at least 385 trades for 95% confidence. "
            f"Collect more data before making trading decisions."
        )
        risk_level = "UNKNOWN"

    return {
        "verdict": verdict,
        "explanation": explanation,
        "risk_level": risk_level,
        "wfe_interpretation": {
            "value": round(wfe * 100, 1),
            "unit": "percent",
            "benchmark": 50,
            "description": "Walk-Forward Efficiency measures how well optimization translates to live trading. >50% is considered robust."
        },
        "confidence_interpretation": {
            "value": round(report.overall_confidence, 1),
            "unit": "percent",
            "benchmark": 95,
            "trades_needed_for_95pct": 385,
            "current_trades": report.total_trades
        }
    }


async def get_walk_forward_quick_analysis(
    strategy: str,
    symbol: str = "BTCUSDT",
    days: int = 180
) -> Dict[str, Any]:
    """
    Quick walk-forward analysis with default parameters

    Args:
        strategy: Strategy name
        symbol: Trading symbol
        days: Number of days (min 90 recommended)

    Returns:
        Walk-forward analysis results
    """
    request = WalkForwardRequest(
        strategy=strategy,
        symbol=symbol,
        days=days,
        use_sample_data=True
    )

    return await run_walk_forward_analysis(request)
