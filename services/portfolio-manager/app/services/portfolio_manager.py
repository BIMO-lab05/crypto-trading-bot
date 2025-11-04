"""
Portfolio Manager Service
Manages portfolio operations, tracking, and integration with Trading Engine
"""

import httpx
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
import logging

from app.models.portfolio import Portfolio, PortfolioSnapshot, RebalanceRecommendation
from app.models.asset import AssetHolding, AssetType
from app.models.performance import AssetPerformance
from app.models.enums import AllocationStrategy
from app.config import settings

logger = logging.getLogger(__name__)


class PortfolioManager:
    """Manages portfolio lifecycle and operations"""

    def __init__(self):
        self.portfolios: Dict[str, Portfolio] = {}
        self.http_client: Optional[httpx.AsyncClient] = None

        # Create default portfolio
        self._create_default_portfolio()

    def _create_default_portfolio(self):
        """Create the default portfolio"""
        default_portfolio = Portfolio(
            portfolio_id="default",
            initial_capital=Decimal(str(settings.initial_capital)),
            cash_balance=Decimal(str(settings.initial_capital))
        )
        self.portfolios["default"] = default_portfolio
        logger.info(f"✓ Created default portfolio with ${settings.initial_capital} capital")

    async def initialize(self):
        """Initialize the portfolio manager"""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("✓ Portfolio Manager initialized")

    async def cleanup(self):
        """Cleanup resources"""
        if self.http_client:
            await self.http_client.aclose()
        logger.info("✓ Portfolio Manager cleaned up")

    def get_portfolio(self, portfolio_id: str = "default") -> Optional[Portfolio]:
        """Get portfolio by ID"""
        return self.portfolios.get(portfolio_id)

    def list_portfolios(self) -> List[Portfolio]:
        """List all portfolios"""
        return list(self.portfolios.values())

    async def sync_with_trading_engine(self, portfolio_id: str = "default") -> bool:
        """Sync portfolio with Trading Engine positions"""
        try:
            portfolio = self.get_portfolio(portfolio_id)
            if not portfolio:
                logger.error(f"Portfolio {portfolio_id} not found")
                return False

            # Fetch positions from Trading Engine
            response = await self.http_client.get(
                f"{settings.trading_engine_url}/api/v1/positions?status=all"
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch positions from Trading Engine: {response.status_code}")
                return False

            data = response.json()
            positions = data.get("positions", [])

            logger.info(f"✓ Fetched {len(positions)} positions from Trading Engine")

            # Update portfolio based on positions
            for position in positions:
                symbol = position["symbol"]
                quantity = Decimal(position["quantity"])
                entry_price = Decimal(position["entry_price"])
                current_price = Decimal(position.get("current_price", entry_price))

                # Get current price from market data if needed
                if current_price == entry_price:
                    current_price = await self._fetch_current_price(symbol)

                # Update or create asset in portfolio
                if position["status"] == "OPEN":
                    if symbol not in portfolio.assets:
                        portfolio.add_asset(
                            symbol=symbol,
                            name=symbol,  # Would ideally fetch full name
                            quantity=quantity,
                            price=entry_price
                        )
                    # Update price
                    portfolio.update_asset_prices({symbol: current_price})

            logger.info(f"✓ Portfolio synced with Trading Engine")
            return True

        except Exception as e:
            logger.error(f"Error syncing with Trading Engine: {e}")
            return False

    async def _fetch_current_price(self, symbol: str) -> Decimal:
        """Fetch current price from Market Data service"""
        try:
            response = await self.http_client.get(
                f"{settings.market_data_url}/api/v1/ticker/{symbol}"
            )

            if response.status_code == 200:
                data = response.json()
                return Decimal(data.get("last_price", "0"))

        except Exception as e:
            logger.warning(f"Could not fetch price for {symbol}: {e}")

        return Decimal("0")

    async def update_prices(self, portfolio_id: str = "default") -> bool:
        """Update all asset prices in portfolio"""
        try:
            portfolio = self.get_portfolio(portfolio_id)
            if not portfolio:
                return False

            # Fetch prices for all assets
            prices = {}
            for symbol in portfolio.assets.keys():
                price = await self._fetch_current_price(symbol)
                if price > 0:
                    prices[symbol] = price

            # Update portfolio
            portfolio.update_asset_prices(prices)

            logger.info(f"✓ Updated prices for {len(prices)} assets")
            return True

        except Exception as e:
            logger.error(f"Error updating prices: {e}")
            return False

    def get_snapshot(self, portfolio_id: str = "default") -> Optional[PortfolioSnapshot]:
        """Get current portfolio snapshot"""
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return None

        # Convert assets to holdings
        holdings = []
        for asset in portfolio.assets.values():
            holding = AssetHolding(
                symbol=asset.symbol,
                quantity=str(asset.quantity),
                current_price=str(asset.current_price),
                current_value=str(asset.current_value),
                unrealized_pnl=str(asset.unrealized_pnl),
                unrealized_pnl_pct=str(asset.unrealized_pnl_pct),
                allocation_pct=str(asset.current_allocation_pct)
            )
            holdings.append(holding)

        snapshot = PortfolioSnapshot(
            portfolio_id=portfolio.portfolio_id,
            cash_balance=str(portfolio.cash_balance),
            total_value=str(portfolio.total_value),
            total_pnl=str(portfolio.total_pnl),
            total_return_pct=str(portfolio.total_return_pct),
            holdings=holdings
        )

        return snapshot

    def get_asset_performance(self, portfolio_id: str = "default") -> List[AssetPerformance]:
        """Get performance metrics for each asset"""
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return []

        performances = []
        for asset in portfolio.assets.values():
            # Calculate hold duration
            hold_duration = (datetime.now().timestamp() * 1000 - asset.last_updated) / (1000 * 60 * 60 * 24)

            perf = AssetPerformance(
                symbol=asset.symbol,
                quantity=str(asset.quantity),
                entry_price=str(asset.average_entry_price),
                current_price=str(asset.current_price),
                unrealized_pnl=str(asset.unrealized_pnl),
                unrealized_pnl_pct=str(asset.unrealized_pnl_pct),
                hold_duration_days=int(hold_duration),
                allocation_pct=str(asset.current_allocation_pct)
            )
            performances.append(perf)

        return performances

    def check_rebalancing_needed(
        self,
        portfolio_id: str = "default"
    ) -> tuple[bool, List[RebalanceRecommendation]]:
        """Check if portfolio needs rebalancing and generate recommendations"""
        portfolio = self.get_portfolio(portfolio_id)
        if not portfolio:
            return False, []

        threshold = Decimal(str(settings.rebalance_threshold_pct))
        recommendations = []

        for asset in portfolio.assets.values():
            if asset.target_allocation_pct is None:
                continue

            drift = abs(asset.current_allocation_pct - asset.target_allocation_pct)

            if drift > threshold:
                # Determine action
                if asset.current_allocation_pct > asset.target_allocation_pct:
                    action = "SELL"
                    # Calculate how much to sell
                    target_value = portfolio.total_value * (asset.target_allocation_pct / Decimal("100"))
                    excess_value = asset.current_value - target_value
                    quantity = excess_value / asset.current_price
                else:
                    action = "BUY"
                    # Calculate how much to buy
                    target_value = portfolio.total_value * (asset.target_allocation_pct / Decimal("100"))
                    shortfall_value = target_value - asset.current_value
                    quantity = shortfall_value / asset.current_price

                recommendation = RebalanceRecommendation(
                    symbol=asset.symbol,
                    current_allocation_pct=str(asset.current_allocation_pct),
                    target_allocation_pct=str(asset.target_allocation_pct),
                    drift_pct=str(drift),
                    action=action,
                    quantity=str(quantity),
                    estimated_cost=str(quantity * asset.current_price * Decimal("0.001"))  # 0.1% commission
                )
                recommendations.append(recommendation)

        needs_rebalancing = len(recommendations) > 0

        return needs_rebalancing, recommendations

    def execute_transaction(
        self,
        portfolio_id: str,
        symbol: str,
        action: str,
        quantity: Decimal,
        price: Decimal
    ) -> tuple[bool, Optional[str], Optional[Decimal]]:
        """Execute a buy or sell transaction"""
        try:
            portfolio = self.get_portfolio(portfolio_id)
            if not portfolio:
                return False, "Portfolio not found", None

            if action == "BUY":
                portfolio.add_asset(
                    symbol=symbol,
                    name=symbol,
                    quantity=quantity,
                    price=price
                )
                logger.info(f"✓ BUY: {quantity} {symbol} @ ${price}")
                return True, f"Bought {quantity} {symbol}", None

            elif action == "SELL":
                realized_pnl = portfolio.remove_asset(symbol, quantity, price)
                logger.info(f"✓ SELL: {quantity} {symbol} @ ${price}, P&L: ${realized_pnl}")
                return True, f"Sold {quantity} {symbol}", realized_pnl

            else:
                return False, f"Invalid action: {action}", None

        except Exception as e:
            logger.error(f"Transaction error: {e}")
            return False, str(e), None
