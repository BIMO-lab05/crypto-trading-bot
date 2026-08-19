"""
Triangular Arbitrage Strategy

This strategy exploits price discrepancies in circular trading paths (triangular cycles).

Strategy Overview:
- Identify circular trading paths: A → B → C → A
- Calculate implied exchange rate vs actual rate
- Execute when arbitrage profit > threshold + fees
- Requires ultra-low latency execution (<100ms)

Mathematical Background:
- Exchange Rate Product: P = (1/R_AB) × R_BC × R_CA
- In efficient markets: P ≈ 1.0
- Arbitrage Opportunity: |P - 1| > threshold
- Net Profit = (P - 1) × Capital - Fees

Example:
Starting with 10,000 USDT:
1. BTC/USDT = 50,000 → Buy 0.2 BTC (cost: 10,000 USDT)
2. ETH/BTC = 0.04 → Buy 5 ETH (cost: 0.2 BTC)
3. ETH/USDT = 2,010 → Sell 5 ETH (receive: 10,050 USDT)
4. Net Profit = 50 USDT - fees

Profit Calculation:
- Forward Cycle: USDT → BTC → ETH → USDT
  Profit = (1 / BTC_USDT) × ETH_BTC × ETH_USDT - 1 - total_fees
- Reverse Cycle: USDT → ETH → BTC → USDT
  Profit = (1 / ETH_USDT) × (1 / ETH_BTC) × BTC_USDT - 1 - total_fees

Risks:
- Execution Risk: Prices change during execution
- Latency Risk: Slow execution eliminates profit
- Fee Risk: Trading fees exceed arbitrage profit
- Liquidity Risk: Insufficient liquidity for full execution

Phase 2.2 - Statistical Arbitrage Implementation
Author: Trading Bot Development Team
Date: 2025-12-07
"""

from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
import logging

logger = logging.getLogger(__name__)


@dataclass
class TriangularPath:
    """
    Represents a triangular arbitrage path

    Attributes:
        symbols: Ordered list of symbols in the path (e.g., ['BTC', 'ETH', 'USDT'])
        pairs: Trading pairs in order (e.g., ['BTCUSDT', 'ETHBTC', 'ETHUSDT'])
        direction: Trade direction for each pair ('buy' or 'sell')
        start_asset: Starting asset (usually 'USDT')
    """

    symbols: List[str]
    pairs: List[str]
    directions: List[str]
    start_asset: str

    def __str__(self) -> str:
        path_str = " → ".join([f"{self.symbols[i]}" for i in range(len(self.symbols))])
        return f"{path_str} (start: {self.start_asset})"


@dataclass
class TriangularArbitrageSignal:
    """
    Signal for triangular arbitrage opportunity

    Attributes:
        timestamp: Signal generation time
        path: Triangular path
        profit_pct: Expected profit percentage (before fees)
        net_profit_pct: Net profit after fees
        exchange_rates: Current exchange rates for each pair
        execution_amount: Amount to execute in start_asset
        estimated_latency_ms: Estimated execution latency
        confidence: Signal confidence (0-100)
        reason: Reason for signal
    """

    timestamp: datetime
    path: TriangularPath
    profit_pct: float
    net_profit_pct: float
    exchange_rates: Dict[str, float]
    execution_amount: float
    estimated_latency_ms: float
    confidence: float
    reason: str


class TriangularArbitrageStrategy:
    """
    Triangular Arbitrage Strategy

    This strategy:
    1. Discovers all possible triangular paths
    2. Monitors real-time prices for all pairs in paths
    3. Calculates arbitrage profit considering fees
    4. Executes when profit > threshold (ultra-fast)
    5. Monitors latency to ensure profitability

    Usage:
        strategy = TriangularArbitrageStrategy(
            base_asset='USDT',
            min_profit_threshold=0.001,  # 0.1% minimum profit
            trading_fee=0.0005,           # 0.05% per trade
        )

        # Discover paths
        paths = strategy.discover_paths(['BTC', 'ETH', 'USDT', 'BNB'])

        # Check for arbitrage (capital = the caller's allocated capital,
        # e.g. manager.total_capital * allocation.triangular)
        signal = strategy.generate_signal(current_prices, capital=allocated_capital)
    """

    def __init__(
        self,
        base_asset: str = "USDT",
        min_profit_threshold: float = 0.001,  # 0.1% minimum profit after fees
        trading_fee: float = 0.0005,  # 0.05% per trade (Bybit VIP 0)
        max_latency_ms: float = 100.0,  # Max 100ms execution latency
        execution_amount_pct: float = 0.1,  # 10% of portfolio per arbitrage
        max_slippage: float = 0.001,  # 0.1% max slippage
    ):
        """
        Initialize Triangular Arbitrage Strategy

        Args:
            base_asset: Starting asset (default: 'USDT')
            min_profit_threshold: Minimum profit % to execute (default: 0.001 = 0.1%)
            trading_fee: Trading fee per trade (default: 0.0005 = 0.05%)
            max_latency_ms: Maximum acceptable latency (default: 100ms)
            execution_amount_pct: Percentage of portfolio per arbitrage (default: 0.1 = 10%)
            max_slippage: Maximum acceptable slippage (default: 0.001 = 0.1%)
        """
        self.base_asset = base_asset
        self.min_profit_threshold = min_profit_threshold
        self.trading_fee = trading_fee
        self.max_latency_ms = max_latency_ms
        self.execution_amount_pct = execution_amount_pct
        self.max_slippage = max_slippage

        # Discovered paths
        self.triangular_paths: List[TriangularPath] = []

        # Performance tracking
        self.total_arbitrages_executed: int = 0
        self.total_profit: float = 0.0
        self.arbitrage_history: List[Dict] = []
        self.average_latency_ms: float = 0.0

        logger.info(
            f"TriangularArbitrageStrategy initialized:\\n"
            f"  Base asset: {base_asset}\\n"
            f"  Min profit threshold: {min_profit_threshold * 100:.2f}%\\n"
            f"  Trading fee: {trading_fee * 100:.3f}% per trade\\n"
            f"  Max latency: {max_latency_ms}ms\\n"
            f"  Execution amount: {execution_amount_pct * 100}% of portfolio"
        )

    def discover_paths(self, available_assets: List[str]) -> List[TriangularPath]:
        """
        Discover all possible triangular arbitrage paths

        For N assets, there are N! / (N-3)! / 2 possible triangular paths.
        For 4 assets (BTC, ETH, BNB, USDT): 12 paths

        Args:
            available_assets: List of available trading assets

        Returns:
            List of discovered TriangularPath objects
        """
        paths = []

        # Ensure base asset is included
        if self.base_asset not in available_assets:
            available_assets.append(self.base_asset)

        # Generate all 3-asset combinations including base asset
        for asset1, asset2 in permutations(
            [a for a in available_assets if a != self.base_asset], 2
        ):
            # Path: base_asset → asset1 → asset2 → base_asset
            symbols = [self.base_asset, asset1, asset2, self.base_asset]

            # Determine trading pairs and directions
            pairs = []
            directions = []

            for i in range(3):
                from_asset = symbols[i]
                to_asset = symbols[i + 1]

                # Try both pair formats (e.g., BTCUSDT or USDTBTC)
                pair_format1 = f"{from_asset}{to_asset}"
                pair_format2 = f"{to_asset}{from_asset}"

                # For simplicity, assume format1 exists and determine direction
                # In practice, check which format exists on exchange
                if from_asset == self.base_asset:
                    # Buying asset1 with USDT: BUY BTC/USDT
                    pairs.append(f"{to_asset}{from_asset}")
                    directions.append("buy")
                elif to_asset == self.base_asset:
                    # Selling asset2 for USDT: SELL ETH/USDT
                    pairs.append(f"{from_asset}{to_asset}")
                    directions.append("sell")
                else:
                    # Trading between two non-base assets: BUY ETH/BTC or SELL BTC/ETH
                    pairs.append(f"{to_asset}{from_asset}")
                    directions.append("buy")

            path = TriangularPath(
                symbols=symbols[:-1],  # Remove duplicate base asset at end
                pairs=pairs,
                directions=directions,
                start_asset=self.base_asset,
            )

            paths.append(path)
            logger.debug(f"Discovered path: {path}")

        self.triangular_paths = paths
        logger.info(f"Discovered {len(paths)} triangular arbitrage paths")
        return paths

    def _calculate_arbitrage_profit(
        self, path: TriangularPath, prices: Dict[str, float], capital: float
    ) -> Tuple[float, float, Dict[str, float]]:
        """
        Calculate arbitrage profit for a given path

        Formula:
        - Start with capital in base_asset
        - For each step: amount = amount × rate × (1 - fee)
        - Profit % = (final_amount - capital) / capital × 100

        Args:
            path: Triangular path
            prices: Current prices for all pairs {pair: price}
            capital: Starting capital in base_asset

        Returns:
            Tuple of (gross_profit_pct, net_profit_pct, exchange_rates_used)
        """
        amount = capital
        exchange_rates = {}

        for i, pair in enumerate(path.pairs):
            if pair not in prices:
                logger.warning(f"Price not available for {pair}")
                return 0.0, 0.0, {}

            price = prices[pair]
            direction = path.directions[i]

            # Apply exchange rate and fee
            if direction == "buy":
                # Buying: amount / price × (1 - fee)
                amount = (amount / price) * (1 - self.trading_fee)
                exchange_rates[pair] = price
            else:  # 'sell'
                # Selling: amount × price × (1 - fee)
                amount = (amount * price) * (1 - self.trading_fee)
                exchange_rates[pair] = price

        # Calculate profit
        gross_profit = amount - capital
        gross_profit_pct = (gross_profit / capital) * 100

        # Net profit already includes fees
        net_profit_pct = gross_profit_pct

        logger.debug(
            f"Path {path}: Capital={capital:.2f}, Final={amount:.2f}, "
            f"Profit={net_profit_pct:.4f}%"
        )

        return gross_profit_pct, net_profit_pct, exchange_rates

    def _estimate_execution_latency(
        self, path: TriangularPath, prices: Dict[str, float]
    ) -> float:
        """
        Estimate execution latency for triangular path

        Latency factors:
        - Network latency: ~20-50ms per order
        - Order matching: ~10-30ms per order
        - Total: ~90-240ms for 3 orders

        Args:
            path: Triangular path
            prices: Current prices

        Returns:
            Estimated latency in milliseconds
        """
        # Base latency per order
        base_latency_per_order = 30  # ms

        # Network latency (assume same exchange)
        network_latency = 20  # ms

        # Total for 3 orders
        total_latency = (base_latency_per_order * len(path.pairs)) + network_latency

        return total_latency

    def generate_signal(
        self,
        current_prices: Dict[str, float],
        capital: float,
    ) -> Optional[TriangularArbitrageSignal]:
        """
        Generate arbitrage signal by checking all discovered paths

        Args:
            current_prices: Current prices for all pairs {pair: price}
            capital: Available capital in base_asset. REQUIRED — the old
                10000.0 default was 100x the real account; every live caller
                (StatisticalArbitrageManager) passes allocated capital
                explicitly (AUDIT 2.5).

        Returns:
            TriangularArbitrageSignal if profitable opportunity found, None otherwise
        """
        if not self.triangular_paths:
            logger.warning(
                "No triangular paths discovered. Call discover_paths() first."
            )
            return None

        best_signal = None
        best_profit = self.min_profit_threshold

        for path in self.triangular_paths:
            try:
                # Calculate arbitrage profit
                gross_profit_pct, net_profit_pct, exchange_rates = (
                    self._calculate_arbitrage_profit(path, current_prices, capital)
                )

                # Convert percentage to decimal for comparison
                net_profit_decimal = net_profit_pct / 100

                # Check if profitable
                if net_profit_decimal > best_profit:
                    # Estimate execution latency
                    latency_ms = self._estimate_execution_latency(path, current_prices)

                    # Check if latency is acceptable
                    if latency_ms > self.max_latency_ms:
                        logger.debug(
                            f"Path {path} rejected: latency {latency_ms:.1f}ms > "
                            f"max {self.max_latency_ms}ms"
                        )
                        continue

                    # Calculate execution amount
                    execution_amount = capital * self.execution_amount_pct

                    # Calculate confidence based on profit margin
                    confidence = min(
                        100.0,
                        (net_profit_decimal / self.min_profit_threshold) * 50 + 50,
                    )

                    # Create signal
                    signal = TriangularArbitrageSignal(
                        timestamp=datetime.now(),
                        path=path,
                        profit_pct=gross_profit_pct,
                        net_profit_pct=net_profit_pct,
                        exchange_rates=exchange_rates,
                        execution_amount=execution_amount,
                        estimated_latency_ms=latency_ms,
                        confidence=confidence,
                        reason=(
                            f"Arbitrage opportunity: {net_profit_pct:.4f}% profit "
                            f"(latency: {latency_ms:.1f}ms, path: {path})"
                        ),
                    )

                    best_signal = signal
                    best_profit = net_profit_decimal

                    logger.debug(
                        f"New best arbitrage: {net_profit_pct:.4f}% via {path}"
                    )

            except Exception as e:
                logger.error(f"Error calculating profit for {path}: {e}")
                continue

        if best_signal:
            logger.info(
                f"Arbitrage signal generated: {best_signal.net_profit_pct:.4f}% "
                f"profit via {best_signal.path}"
            )
        else:
            logger.debug("No profitable arbitrage opportunities found")

        return best_signal

    def record_arbitrage_execution(
        self,
        signal: TriangularArbitrageSignal,
        actual_profit: float,
        actual_latency_ms: float,
        execution_status: str,
    ):
        """
        Record arbitrage execution for performance tracking

        Args:
            signal: Original signal
            actual_profit: Actual profit realized
            actual_latency_ms: Actual execution latency
            execution_status: 'success' or 'failed'
        """
        if execution_status == "success":
            self.total_arbitrages_executed += 1
            self.total_profit += actual_profit

        # Update average latency
        if self.total_arbitrages_executed > 0:
            self.average_latency_ms = (
                self.average_latency_ms * (self.total_arbitrages_executed - 1)
                + actual_latency_ms
            ) / self.total_arbitrages_executed

        self.arbitrage_history.append(
            {
                "timestamp": datetime.now(),
                "path": str(signal.path),
                "expected_profit_pct": signal.net_profit_pct,
                "actual_profit": actual_profit,
                "expected_latency_ms": signal.estimated_latency_ms,
                "actual_latency_ms": actual_latency_ms,
                "status": execution_status,
            }
        )

        logger.info(
            f"Arbitrage execution recorded: {execution_status}, "
            f"profit=${actual_profit:.2f}, latency={actual_latency_ms:.1f}ms"
        )

    def get_status(self) -> Dict:
        """
        Get current strategy status

        Returns:
            Dictionary with strategy state
        """
        return {
            "base_asset": self.base_asset,
            "num_paths_discovered": len(self.triangular_paths),
            "total_arbitrages_executed": self.total_arbitrages_executed,
            "total_profit": self.total_profit,
            "average_latency_ms": self.average_latency_ms,
            "parameters": {
                "min_profit_threshold": self.min_profit_threshold,
                "trading_fee": self.trading_fee,
                "max_latency_ms": self.max_latency_ms,
                "execution_amount_pct": self.execution_amount_pct,
                "max_slippage": self.max_slippage,
            },
            "paths": [str(path) for path in self.triangular_paths],
        }

    def get_arbitrage_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent arbitrage execution history

        Args:
            limit: Maximum number of records to return

        Returns:
            List of recent arbitrage executions
        """
        return self.arbitrage_history[-limit:]

    def calculate_potential_daily_profit(
        self,
        capital: float,
        average_opportunities_per_day: int = 10,
        average_profit_pct: float = 0.2,
    ) -> Dict:
        """
        Calculate potential daily profit from triangular arbitrage

        Args:
            capital: Trading capital. REQUIRED (moved first so it cannot be
                silently omitted) — the old 10000.0 default was 100x the real
                account (AUDIT 2.5).
            average_opportunities_per_day: Expected number of opportunities per day
            average_profit_pct: Average profit percentage per opportunity

        Returns:
            Dictionary with profit projections
        """
        execution_amount = capital * self.execution_amount_pct
        profit_per_opportunity = execution_amount * (average_profit_pct / 100)
        daily_profit = profit_per_opportunity * average_opportunities_per_day
        daily_return_pct = (daily_profit / capital) * 100
        annual_return_pct = daily_return_pct * 365

        return {
            "execution_amount": execution_amount,
            "profit_per_opportunity": profit_per_opportunity,
            "opportunities_per_day": average_opportunities_per_day,
            "daily_profit": daily_profit,
            "daily_return_pct": daily_return_pct,
            "annual_return_pct": annual_return_pct,
            "annual_profit": daily_profit * 365,
        }
