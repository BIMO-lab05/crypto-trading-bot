"""
Statistical Arbitrage API Endpoint Handlers

Provides REST API endpoints for Phase 2.2 statistical arbitrage strategies:
- Pairs Trading
- Funding Rate Arbitrage
- Triangular Arbitrage

Endpoints:
- GET /api/v1/statistical-arbitrage/status - Get manager status
- POST /api/v1/statistical-arbitrage/initialize - Initialize manager
- POST /api/v1/statistical-arbitrage/pairs/add - Add pairs strategy
- POST /api/v1/statistical-arbitrage/pairs/calibrate - Calibrate pairs strategy
- POST /api/v1/statistical-arbitrage/funding/add - Add funding strategy
- POST /api/v1/statistical-arbitrage/triangular/setup - Setup triangular arbitrage
- POST /api/v1/statistical-arbitrage/signals/generate - Generate signals
- GET /api/v1/statistical-arbitrage/performance - Get performance metrics
- DELETE /api/v1/statistical-arbitrage/reset - Reset manager

Author: Trading Bot Development Team
Date: 2025-12-07
Updated: 2025-12-11 - Fixed parameter name: stop_threshold (not stop_loss_threshold)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException
import pandas as pd

from app.config import get_settings
from app.managers import (
    StatisticalArbitrageManager,
    StrategyAllocation,
)

logger = logging.getLogger(__name__)

# Global manager instance (singleton pattern)
_stat_arb_manager: Optional[StatisticalArbitrageManager] = None


def get_stat_arb_manager() -> Optional[StatisticalArbitrageManager]:
    """Get the global statistical arbitrage manager instance"""
    return _stat_arb_manager


async def initialize_stat_arb_manager(
    total_capital: Optional[float] = None,
    pairs_allocation: float = 0.4,
    funding_allocation: float = 0.4,
    triangular_allocation: float = 0.2,
    enable_pairs: bool = True,
    enable_funding: bool = True,
    enable_triangular: bool = True,
) -> Dict[str, Any]:
    """
    Initialize Statistical Arbitrage Manager

    Args:
        total_capital: Total capital for statistical arbitrage. Defaults to the
            configured paper-trading balance (PAPER_INITIAL_BALANCE).
        pairs_allocation: Allocation for pairs trading (0-1)
        funding_allocation: Allocation for funding rate arbitrage (0-1)
        triangular_allocation: Allocation for triangular arbitrage (0-1)
        enable_pairs: Enable pairs trading strategies
        enable_funding: Enable funding rate arbitrage
        enable_triangular: Enable triangular arbitrage

    Returns:
        Dictionary with initialization status

    Raises:
        HTTPException: If initialization fails
    """
    global _stat_arb_manager

    # FIX 2026-08-03 (capital audit A2): was 100000.0, 1000x the real account.
    # Resolved in the body, not the signature: Python evaluates parameter
    # defaults at MODULE IMPORT, so `= get_settings().paper_initial_balance`
    # would create an import-time settings dependency and freeze the value.
    if total_capital is None:
        total_capital = get_settings().paper_initial_balance

    try:
        # Validate allocations
        total_allocation = pairs_allocation + funding_allocation + triangular_allocation
        if abs(total_allocation - 1.0) > 0.001:
            raise ValueError(f"Allocations must sum to 1.0, got {total_allocation:.3f}")

        # Create allocation
        allocation = StrategyAllocation(
            pairs_trading=pairs_allocation,
            funding_rate=funding_allocation,
            triangular=triangular_allocation,
        )

        # Initialize manager
        _stat_arb_manager = StatisticalArbitrageManager(
            total_capital=total_capital,
            allocation=allocation,
            enable_pairs=enable_pairs,
            enable_funding=enable_funding,
            enable_triangular=enable_triangular,
        )

        logger.info(
            f"Statistical Arbitrage Manager initialized: "
            f"Capital=${total_capital:,.2f}, "
            f"Allocation={allocation.__dict__}"
        )

        return {
            "status": "success",
            "message": "Statistical Arbitrage Manager initialized",
            "config": {
                "total_capital": total_capital,
                "allocation": {
                    "pairs_trading": pairs_allocation,
                    "funding_rate": funding_allocation,
                    "triangular": triangular_allocation,
                },
                "enabled_strategies": {
                    "pairs": enable_pairs,
                    "funding": enable_funding,
                    "triangular": enable_triangular,
                },
            },
            "timestamp": datetime.now().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Validation error initializing manager: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error initializing Statistical Arbitrage Manager: {e}")
        raise HTTPException(status_code=500, detail=f"Initialization failed: {str(e)}")


async def add_pairs_strategy(
    symbol_x: str,
    symbol_y: str,
    entry_threshold: float = 2.0,
    exit_threshold: float = 0.5,
    lookback_period: int = 60,
    stop_loss_z: float = 3.0,
) -> Dict[str, Any]:
    """
    Add a pairs trading strategy

    Args:
        symbol_x: First symbol (e.g., 'BTCUSDT')
        symbol_y: Second symbol (e.g., 'ETHUSDT')
        entry_threshold: Z-score threshold for entry (default: 2.0)
        exit_threshold: Z-score threshold for exit (default: 0.5)
        lookback_period: Lookback period for spread calculation (default: 60)
        stop_loss_z: Z-score threshold for stop loss (default: 3.0)

    Returns:
        Dictionary with strategy ID and status

    Raises:
        HTTPException: If manager not initialized or addition fails
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        # Pass stop_threshold (correct param name for PairsTradingStrategy)
        strategy_id = _stat_arb_manager.add_pairs_strategy(
            symbol_x=symbol_x,
            symbol_y=symbol_y,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            stop_threshold=stop_loss_z,  # Fixed: use stop_threshold not stop_loss_threshold
            lookback_period=lookback_period,
        )

        if not strategy_id:
            raise ValueError("Pairs trading is disabled")

        logger.info(f"Added pairs strategy: {strategy_id}")

        return {
            "status": "success",
            "strategy_id": strategy_id,
            "strategy_type": "pairs_trading",
            "config": {
                "symbol_x": symbol_x,
                "symbol_y": symbol_y,
                "entry_threshold": entry_threshold,
                "exit_threshold": exit_threshold,
                "lookback_period": lookback_period,
                "stop_loss_z": stop_loss_z,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Validation error adding pairs strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding pairs strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add strategy: {str(e)}")


async def calibrate_pairs_strategy(
    strategy_id: str,
    historical_data_x: List[float],
    historical_data_y: List[float],
    timestamps: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Calibrate a pairs trading strategy with historical data

    Args:
        strategy_id: Strategy ID (e.g., 'BTCUSDT_ETHUSDT')
        historical_data_x: Historical prices for symbol X
        historical_data_y: Historical prices for symbol Y
        timestamps: Optional timestamps for data points

    Returns:
        Dictionary with calibration results

    Raises:
        HTTPException: If calibration fails
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        # Convert to pandas Series
        if timestamps:
            index = pd.to_datetime(timestamps)
        else:
            index = range(len(historical_data_x))

        series_x = pd.Series(historical_data_x, index=index)
        series_y = pd.Series(historical_data_y, index=index)

        # Calibrate
        success = _stat_arb_manager.calibrate_pairs_strategy(
            strategy_id=strategy_id,
            historical_data_x=series_x,
            historical_data_y=series_y,
        )

        if success:
            # Get strategy status for calibration results
            strategy = _stat_arb_manager.pairs_strategies.get(strategy_id)
            if strategy:
                status = strategy.get_status()

                return {
                    "status": "success",
                    "strategy_id": strategy_id,
                    "calibrated": True,
                    "is_cointegrated": status["is_cointegrated"],
                    "hedge_ratio": status["hedge_ratio"],
                    "half_life": status["half_life"],
                    "spread_mean": status["spread_mean"],
                    "spread_std": status["spread_std"],
                    "timestamp": datetime.now().isoformat(),
                }

        return {
            "status": "failed",
            "strategy_id": strategy_id,
            "calibrated": False,
            "message": "Pair is not cointegrated",
            "timestamp": datetime.now().isoformat(),
        }

    except KeyError:
        raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
    except ValueError as e:
        logger.error(f"Validation error calibrating strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error calibrating pairs strategy {strategy_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Calibration failed: {str(e)}")


async def add_funding_strategy(
    symbol: str,
    min_funding_rate: float = 0.0003,
    max_basis_pct: float = 2.0,
    position_size_pct: float = 0.2,
) -> Dict[str, Any]:
    """
    Add a funding rate arbitrage strategy

    Args:
        symbol: Trading symbol (e.g., 'BTCUSDT')
        min_funding_rate: Minimum funding rate to trade (default: 0.0003 = 0.03%)
        max_basis_pct: Maximum allowed basis percentage (default: 2.0%)
        position_size_pct: Position size as percentage (default: 0.2 = 20%)

    Returns:
        Dictionary with strategy ID and status

    Raises:
        HTTPException: If manager not initialized or addition fails
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        strategy_id = _stat_arb_manager.add_funding_strategy(
            symbol=symbol,
            min_funding_rate=min_funding_rate,
            max_basis_pct=max_basis_pct,
            position_size_pct=position_size_pct,
        )

        if not strategy_id:
            raise ValueError("Funding rate arbitrage is disabled")

        logger.info(f"Added funding strategy: {strategy_id}")

        # Calculate annualized yield for display
        annualized_yield = (
            min_funding_rate * 365 * 3
        ) * 100  # 3 funding payments per day

        return {
            "status": "success",
            "strategy_id": strategy_id,
            "strategy_type": "funding_rate",
            "config": {
                "symbol": symbol,
                "min_funding_rate": min_funding_rate,
                "min_annualized_yield_pct": annualized_yield,
                "max_basis_pct": max_basis_pct,
                "position_size_pct": position_size_pct,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except ValueError as e:
        logger.error(f"Validation error adding funding strategy: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error adding funding strategy: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add strategy: {str(e)}")


async def setup_triangular_arbitrage(
    assets: List[str],
    min_profit_threshold: float = 0.005,
    trading_fee: float = 0.0005,
    max_latency_ms: float = 100.0,
) -> Dict[str, Any]:
    """
    Setup triangular arbitrage strategy

    Args:
        assets: List of assets (e.g., ['BTC', 'ETH', 'BNB', 'USDT'])
        min_profit_threshold: Minimum profit threshold (default: 0.005 = 0.5%)
        trading_fee: Trading fee per trade (default: 0.0005 = 0.05%)
        max_latency_ms: Maximum latency (default: 100ms)

    Returns:
        Dictionary with discovered paths

    Raises:
        HTTPException: If manager not initialized or setup fails
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        success = _stat_arb_manager.setup_triangular_arbitrage(
            assets=assets,
            min_profit_threshold=min_profit_threshold,
            trading_fee=trading_fee,
            max_latency_ms=max_latency_ms,
        )

        if not success:
            raise ValueError("Triangular arbitrage is disabled or no paths found")

        # Get discovered paths
        if _stat_arb_manager.triangular_strategy:
            num_paths = len(_stat_arb_manager.triangular_strategy.triangular_paths)

            logger.info(f"Triangular arbitrage setup: {num_paths} paths discovered")

            return {
                "status": "success",
                "strategy_type": "triangular_arbitrage",
                "num_paths_discovered": num_paths,
                "config": {
                    "assets": assets,
                    "min_profit_threshold": min_profit_threshold,
                    "trading_fee": trading_fee,
                    "max_latency_ms": max_latency_ms,
                },
                "timestamp": datetime.now().isoformat(),
            }

        raise ValueError("Triangular strategy not configured")

    except ValueError as e:
        logger.error(f"Validation error setting up triangular arbitrage: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error setting up triangular arbitrage: {e}")
        raise HTTPException(status_code=500, detail=f"Setup failed: {str(e)}")


async def generate_signals(market_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate signals from all enabled strategies

    Args:
        market_data: Market data dictionary with:
            - pairs_data: Dict with pairs trading data
            - funding_data: Dict with funding rate data
            - triangular_prices: Dict with triangular arbitrage prices

    Returns:
        Dictionary with generated signals

    Raises:
        HTTPException: If signal generation fails
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        signals = _stat_arb_manager.generate_all_signals(market_data)

        # Convert signals to serializable format
        serializable_signals = {
            "pairs": [
                {
                    "strategy_id": s["strategy_id"],
                    "signal": {
                        "action": s["signal"].action,
                        "z_score": s["signal"].z_score,
                        "spread": s["signal"].spread,
                        "position_size_x": s["signal"].position_size_x,
                        "position_size_y": s["signal"].position_size_y,
                        "confidence": s["signal"].confidence,
                        "reason": s["signal"].reason,
                    },
                    "timestamp": s["timestamp"].isoformat(),
                }
                for s in signals["pairs"]
            ],
            "funding": [
                {
                    "strategy_id": s["strategy_id"],
                    "signal": {
                        "action": s["signal"].action,
                        "symbol": s["signal"].symbol,
                        "funding_rate": s["signal"].funding_rate,
                        "annualized_yield": s["signal"].annualized_yield,
                        "basis_pct": s["signal"].basis_pct,
                        "spot_position_size": s["signal"].spot_position_size,
                        "futures_position_size": s["signal"].futures_position_size,
                        "confidence": s["signal"].confidence,
                        "reason": s["signal"].reason,
                    },
                    "timestamp": s["timestamp"].isoformat(),
                }
                for s in signals["funding"]
            ],
            "triangular": [
                {
                    "strategy_id": s["strategy_id"],
                    "signal": {
                        "path": " -> ".join(s["signal"].path.symbols),
                        "net_profit_pct": s["signal"].net_profit_pct,
                        "execution_amount": s["signal"].execution_amount,
                        "estimated_latency_ms": s["signal"].estimated_latency_ms,
                        "confidence": s["signal"].confidence,
                        "reason": s["signal"].reason,
                    },
                    "timestamp": s["timestamp"].isoformat(),
                }
                for s in signals["triangular"]
            ],
        }

        total_signals = sum(len(s) for s in signals.values())

        return {
            "status": "success",
            "total_signals": total_signals,
            "signals_by_type": {
                "pairs": len(signals["pairs"]),
                "funding": len(signals["funding"]),
                "triangular": len(signals["triangular"]),
            },
            "signals": serializable_signals,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error generating signals: {e}")
        raise HTTPException(
            status_code=500, detail=f"Signal generation failed: {str(e)}"
        )


async def get_performance() -> Dict[str, Any]:
    """
    Get portfolio performance metrics

    Returns:
        Dictionary with comprehensive performance data

    Raises:
        HTTPException: If manager not initialized
    """
    if _stat_arb_manager is None:
        raise HTTPException(
            status_code=400, detail="Manager not initialized. Call /initialize first."
        )

    try:
        performance = _stat_arb_manager.get_portfolio_performance()

        return {
            "status": "success",
            "performance": {
                "total_capital": performance.total_capital,
                "allocated_capital": performance.allocated_capital,
                "total_profit": performance.total_profit,
                "return_on_capital_pct": (
                    performance.total_profit / performance.total_capital * 100
                )
                if performance.total_capital > 0
                else 0.0,
                "total_trades": performance.total_trades,
                "winning_trades": performance.winning_trades,
                "losing_trades": performance.losing_trades,
                "win_rate": performance.win_rate,
                "sharpe_ratio": performance.sharpe_ratio,
                "max_drawdown": performance.max_drawdown,
            },
            "strategies_performance": performance.strategies_performance,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to get performance: {str(e)}"
        )


async def get_status() -> Dict[str, Any]:
    """
    Get comprehensive manager status

    Returns:
        Dictionary with manager and all strategies status

    Raises:
        HTTPException: If manager not initialized
    """
    if _stat_arb_manager is None:
        return {
            "status": "not_initialized",
            "message": "Statistical Arbitrage Manager not initialized",
            "timestamp": datetime.now().isoformat(),
        }

    try:
        status = _stat_arb_manager.get_status_summary()

        return {
            "status": "active",
            "manager_status": status,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error getting status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


async def reset_manager() -> Dict[str, Any]:
    """
    Reset the Statistical Arbitrage Manager

    Returns:
        Dictionary with reset confirmation

    Warning:
        This will clear all strategies and performance data
    """
    global _stat_arb_manager

    if _stat_arb_manager is None:
        return {
            "status": "success",
            "message": "Manager was not initialized",
            "timestamp": datetime.now().isoformat(),
        }

    try:
        _stat_arb_manager = None
        logger.warning("Statistical Arbitrage Manager reset")

        return {
            "status": "success",
            "message": "Statistical Arbitrage Manager reset successfully",
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Error resetting manager: {e}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")
