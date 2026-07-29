"""
Portfolio Optimization Endpoint Handlers
Extracted from main.py - Responsibility: Portfolio optimization using Modern Portfolio Theory

Handles:
- Portfolio optimization with various objectives
- Efficient frontier generation
- Rebalancing execution based on target weights
"""

import logging
from typing import Optional, Dict
from decimal import Decimal
from fastapi import HTTPException, Request, Query, Body

from app.models import Portfolio
from app.services import PortfolioManager
from app.optimization import PortfolioOptimizer
from app.optimization.portfolio_optimizer import OptimizationObjective, OptimizationConstraints
from app.config import settings
from app.utils import check_rate_limit, fetch_historical_prices

logger = logging.getLogger(__name__)


def get_portfolio_manager() -> PortfolioManager:
    """Get portfolio manager instance (from global state)"""
    from app.main import portfolio_manager
    if portfolio_manager is None:
        raise HTTPException(status_code=503, detail="Portfolio Manager not initialized")
    return portfolio_manager


def get_portfolio_optimizer() -> PortfolioOptimizer:
    """Get portfolio optimizer instance (from global state)"""
    from app.main import portfolio_optimizer
    if portfolio_optimizer is None:
        raise HTTPException(status_code=503, detail="Portfolio Optimizer not initialized")
    return portfolio_optimizer


async def optimize_portfolio(
    request: Request,
    portfolio_id: str = "default",
    objective: OptimizationObjective = OptimizationObjective.MAX_SHARPE,
    lookback_days: int = Query(default=60, ge=30, le=365, description="Historical data lookback period"),
    max_position_size: float = Query(default=0.30, ge=0.05, le=1.0, description="Maximum position size (0-1)"),
    min_position_size: float = Query(default=0.05, ge=0.0, le=0.5, description="Minimum position size (0-1)"),
    max_portfolio_volatility: Optional[float] = Query(default=None, description="Maximum portfolio volatility"),
):
    """
    Calculate optimal portfolio allocation using Modern Portfolio Theory

    This endpoint analyzes historical price data and calculates the optimal
    portfolio weights based on the selected optimization objective.

    Objectives:
    - max_sharpe: Maximize risk-adjusted return (Sharpe Ratio)
    - min_volatility: Minimize portfolio volatility
    - max_return: Maximize expected return
    - risk_parity: Equal risk contribution from all assets
    - max_diversification: Maximum diversification ratio
    - kelly_criterion: Kelly optimal position sizing

    Process:
    1. Fetch historical price data from Market Data Service
    2. Calculate returns and covariance matrix
    3. Run optimization algorithm based on objective
    4. Calculate expected metrics (return, volatility, Sharpe)
    5. Generate rebalancing trades to achieve target weights

    Args:
        request: FastAPI request (for rate limiting)
        portfolio_id: Portfolio identifier (default: "default")
        objective: Optimization objective
        lookback_days: Historical data period (30-365 days)
        max_position_size: Maximum allocation per asset (0-1)
        min_position_size: Minimum allocation per asset (0-0.5)
        max_portfolio_volatility: Maximum acceptable portfolio volatility

    Returns:
        Dict with optimization results and rebalancing trades

    Raises:
        HTTPException: 400 if insufficient assets, 503 if data unavailable
    """
    # Rate limiting
    check_rate_limit(request, 10)  # 10 requests per minute for optimization

    manager = get_portfolio_manager()
    optimizer = get_portfolio_optimizer()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Get list of symbols in portfolio
    symbols = list(portfolio.assets.keys())
    if len(symbols) < 2:
        raise HTTPException(
            status_code=400,
            detail="Portfolio must have at least 2 assets for optimization"
        )

    try:
        # Fetch historical price data from Market Data Service
        price_data = await fetch_historical_prices(symbols, lookback_days)

        if price_data.empty:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch historical price data from Market Data Service"
            )

        # Calculate returns
        returns = optimizer.calculate_returns_from_prices(price_data)

        # Set up constraints
        constraints = OptimizationConstraints(
            max_position_size=max_position_size,
            min_position_size=min_position_size,
            max_portfolio_volatility=max_portfolio_volatility,
        )

        # Get current weights
        current_weights = {
            symbol: float(asset.current_allocation_pct) / 100.0
            for symbol, asset in portfolio.assets.items()
        }

        # Optimize portfolio
        result = optimizer.optimize_portfolio(
            returns=returns,
            objective=objective,
            constraints=constraints,
            current_weights=current_weights
        )

        # Calculate rebalancing trades
        trades = optimizer.calculate_rebalancing_trades(
            current_weights=current_weights,
            target_weights=result.weights,
            portfolio_value=float(portfolio.total_value),
            min_trade_size=100.0
        )

        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "objective": objective.value,
            "optimization_result": {
                "weights": result.weights,
                "expected_return": f"{result.expected_return:.4f}",
                "expected_volatility": f"{result.expected_volatility:.4f}",
                "sharpe_ratio": f"{result.sharpe_ratio:.4f}",
                "value_at_risk_95": f"{result.value_at_risk_95:.4f}" if result.value_at_risk_95 else None,
                "conditional_var_95": f"{result.conditional_var_95:.4f}" if result.conditional_var_95 else None,
                "diversification_ratio": f"{result.diversification_ratio:.4f}" if result.diversification_ratio else None,
                "effective_num_assets": f"{result.effective_num_assets:.2f}" if result.effective_num_assets else None,
            },
            "rebalancing_trades": [
                {
                    "symbol": symbol,
                    "action": action,
                    "amount_usd": f"{amount:.2f}"
                }
                for symbol, (action, amount) in trades.items()
            ],
            "constraints_met": result.constraints_met,
            "optimization_time": f"{result.optimization_time:.2f}s",
            "message": result.message
        }

    except HTTPException:
        # Preserve intentional HTTP errors (e.g. 503 when price data is
        # unavailable, 400 for bad input) instead of masking them as a 500.
        raise
    except Exception as e:
        logger.error(f"Portfolio optimization error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Portfolio optimization failed: {str(e)}"
        )


async def get_efficient_frontier(
    request: Request,
    portfolio_id: str = "default",
    num_points: int = Query(default=50, ge=10, le=100, description="Number of frontier points"),
    lookback_days: int = Query(default=60, ge=30, le=365, description="Historical data lookback period"),
):
    """
    Generate efficient frontier for portfolio

    The efficient frontier shows the set of optimal portfolios offering
    the highest expected return for each level of risk.

    Returns a list of portfolio configurations along the frontier,
    from minimum volatility to maximum return.

    Process:
    1. Fetch historical price data
    2. Calculate returns and covariance
    3. Generate portfolios across risk spectrum
    4. Calculate metrics for each point
    5. Return frontier data for visualization

    Args:
        request: FastAPI request (for rate limiting)
        portfolio_id: Portfolio identifier (default: "default")
        num_points: Number of points to generate (10-100)
        lookback_days: Historical data period (30-365 days)

    Returns:
        Dict with frontier points (return, volatility, Sharpe, weights)

    Raises:
        HTTPException: 400 if insufficient assets, 503 if data unavailable
    """
    # Rate limiting
    check_rate_limit(request, 5)  # 5 requests per minute for frontier generation

    manager = get_portfolio_manager()
    optimizer = get_portfolio_optimizer()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    symbols = list(portfolio.assets.keys())
    if len(symbols) < 2:
        raise HTTPException(
            status_code=400,
            detail="Portfolio must have at least 2 assets for efficient frontier"
        )

    try:
        # Fetch historical price data
        price_data = await fetch_historical_prices(symbols, lookback_days)

        if price_data.empty:
            raise HTTPException(
                status_code=503,
                detail="Unable to fetch historical price data"
            )

        # Calculate returns
        returns = optimizer.calculate_returns_from_prices(price_data)

        # Generate efficient frontier
        frontier_points = optimizer.generate_efficient_frontier(
            returns=returns,
            num_points=num_points
        )

        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "num_points": len(frontier_points),
            "frontier_points": [
                {
                    "expected_return": f"{point.expected_return:.4f}",
                    "expected_volatility": f"{point.expected_volatility:.4f}",
                    "sharpe_ratio": f"{point.sharpe_ratio:.4f}",
                    "weights": point.weights
                }
                for point in frontier_points
            ],
            "message": f"Generated {len(frontier_points)} efficient frontier points"
        }

    except HTTPException:
        # Preserve intentional HTTP errors (e.g. 503 when price data is
        # unavailable, 400 for bad input) instead of masking them as a 500.
        raise
    except Exception as e:
        logger.error(f"Efficient frontier generation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Efficient frontier generation failed: {str(e)}"
        )


async def execute_rebalancing(
    request: Request,
    portfolio_id: str = "default",
    target_weights: Dict[str, float] = Body(..., description="Target allocation weights"),
    execute: bool = Query(default=False, description="Execute trades (default: dry run)"),
):
    """
    Execute portfolio rebalancing to target weights

    Calculates and optionally executes trades to bring portfolio
    to target allocation weights.

    Process (dry run):
    1. Validate target weights (must sum to 1.0)
    2. Calculate current weights
    3. Determine required trades
    4. Return rebalancing plan

    Process (execute=True):
    1-4. Same as dry run
    5. Fetch current prices for each asset
    6. Execute BUY/SELL transactions
    7. Return execution results

    Args:
        request: FastAPI request (for rate limiting)
        portfolio_id: Portfolio identifier (default: "default")
        target_weights: Dictionary of {symbol: weight} (weights should sum to 1.0)
        execute: If True, execute trades; if False, return recommendations only

    Returns:
        Dict with rebalancing plan and execution results (if execute=True)

    Raises:
        HTTPException: 400 if weights invalid, 404 if portfolio not found
    """
    # Rate limiting
    check_rate_limit(request, 10)  # 10 requests per minute

    manager = get_portfolio_manager()
    optimizer = get_portfolio_optimizer()

    portfolio = manager.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail=f"Portfolio {portfolio_id} not found")

    # Validate target weights
    total_weight = sum(target_weights.values())
    if not (0.99 <= total_weight <= 1.01):  # Allow small rounding error
        raise HTTPException(
            status_code=400,
            detail=f"Target weights must sum to 1.0 (got {total_weight:.4f})"
        )

    # Normalize weights to exactly 1.0
    target_weights = {k: v / total_weight for k, v in target_weights.items()}

    # Get current weights
    current_weights = {
        symbol: float(asset.current_allocation_pct) / 100.0
        for symbol, asset in portfolio.assets.items()
    }

    # Calculate required trades
    trades = optimizer.calculate_rebalancing_trades(
        current_weights=current_weights,
        target_weights=target_weights,
        portfolio_value=float(portfolio.total_value),
        min_trade_size=100.0
    )

    if not trades:
        return {
            "success": True,
            "portfolio_id": portfolio_id,
            "executed": False,
            "trades": [],
            "message": "No rebalancing needed - portfolio is already within target allocation"
        }

    # Execute trades if requested
    executed_trades = []
    if execute:
        # Serialize the per-trade fetch+execute window per portfolio so a
        # concurrent buy/sell handler can't interleave with these rebalance
        # legs and overdraw the cash balance.
        async with manager.get_transaction_lock(portfolio_id):
            for symbol, (action, amount_usd) in trades.items():
                # Get current price
                current_price = await manager._fetch_current_price(symbol)
                if current_price == 0:
                    logger.warning(f"Skipping {symbol} - unable to fetch price")
                    continue

                # Calculate quantity
                quantity = Decimal(str(amount_usd)) / Decimal(str(current_price))

                # Execute trade
                success, message, realized_pnl = manager.execute_transaction(
                    portfolio_id=portfolio_id,
                    symbol=symbol,
                    action=action,
                    quantity=quantity,
                    price=Decimal(str(current_price))
                )

                executed_trades.append({
                    "symbol": symbol,
                    "action": action,
                    "quantity": str(quantity),
                    "price": str(current_price),
                    "amount_usd": f"{amount_usd:.2f}",
                    "success": success,
                    "message": message
                })

    return {
        "success": True,
        "portfolio_id": portfolio_id,
        "executed": execute,
        "current_weights": current_weights,
        "target_weights": target_weights,
        "trades": [
            {
                "symbol": symbol,
                "action": action,
                "amount_usd": f"{amount:.2f}"
            }
            for symbol, (action, amount) in trades.items()
        ],
        "executed_trades": executed_trades if execute else None,
        "message": f"{'Executed' if execute else 'Planned'} {len(trades)} rebalancing trades"
    }
