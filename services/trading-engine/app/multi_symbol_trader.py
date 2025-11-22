"""
Multi-Symbol Auto Trader
Purpose: Trade 5-10 symbols simultaneously with portfolio-level risk management
Enhanced with correlation analysis and intelligent capital allocation
"""

import asyncio
import logging
from typing import Optional, List, Dict
from datetime import datetime
from decimal import Decimal

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.paper_trading import get_paper_engine
from app.risk_manager import get_risk_manager
from app.position_manager import get_position_manager
from app.portfolio_optimizer import get_portfolio_optimizer, PortfolioMetrics
from app.models import OrderSide, OrderType, OrderCreate, OrderStatus

logger = logging.getLogger(__name__)
settings = get_settings()


class MultiSymbolTrader:
    """
    Advanced multi-symbol automated trader with portfolio optimization

    Features:
    - Simultaneous trading of 5-10 symbols
    - Correlation-based diversification
    - Portfolio-level risk management
    - Priority-based symbol selection
    - Intelligent capital allocation
    - Real-time portfolio rebalancing
    """

    def __init__(
        self,
        interval: str = "60",
        check_frequency_seconds: int = 300,
        enable_portfolio_optimization: bool = True,
    ):
        """
        Initialize multi-symbol trader

        Args:
            interval: Timeframe for analysis (default: 60 minutes)
            check_frequency_seconds: How often to check signals (default: 300 seconds)
            enable_portfolio_optimization: Enable portfolio optimization features
        """
        self.interval = interval
        self.check_frequency = check_frequency_seconds
        self.enable_optimization = enable_portfolio_optimization
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

        # Get portfolio optimizer
        self.portfolio_optimizer = get_portfolio_optimizer()

        # Get symbols from portfolio allocation
        self.symbols = list(self.portfolio_optimizer.allocations.keys())

        # Statistics
        self.total_signals_checked = 0
        self.total_trades_executed = 0
        self.total_trades_rejected = 0
        self.symbol_stats: Dict[str, Dict] = {
            symbol: {
                "signals_checked": 0,
                "trades_executed": 0,
                "trades_rejected": 0,
            }
            for symbol in self.symbols
        }
        self.last_check_time: Optional[datetime] = None
        self.last_portfolio_metrics: Optional[PortfolioMetrics] = None

        logger.info(
            f"MultiSymbolTrader initialized: {len(self.symbols)} symbols, "
            f"interval={self.interval}, frequency={self.check_frequency}s, "
            f"optimization={self.enable_optimization}"
        )
        logger.info(f"Portfolio symbols: {', '.join(self.symbols)}")

    async def start(self):
        """Start the automated trading loop"""
        if self.is_running:
            logger.warning("MultiSymbolTrader is already running")
            return False

        logger.info("🚀 Starting multi-symbol automated trading loop")
        self.is_running = True
        self.task = asyncio.create_task(self._trading_loop())
        return True

    async def stop(self):
        """Stop the automated trading loop"""
        if not self.is_running:
            logger.warning("MultiSymbolTrader is not running")
            return False

        logger.info("🛑 Stopping multi-symbol trading loop")
        self.is_running = False

        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("Trading loop task cancelled successfully")

        return True

    async def _trading_loop(self):
        """Main trading loop - runs continuously until stopped"""
        logger.info("📊 Multi-symbol automated trading loop started")
        logger.info(f"   Trading {len(self.symbols)} symbols with portfolio optimization")

        while self.is_running:
            try:
                # Get current portfolio status
                await self._check_and_log_portfolio_status()

                # Get trading priority list (symbols without open positions)
                position_mgr = get_position_manager()
                current_positions = position_mgr.get_all_positions()
                priority_symbols = self.portfolio_optimizer.get_trading_priority_list(current_positions)

                logger.info(f"\n{'='*60}")
                logger.info(f"📋 TRADING CYCLE - {len(priority_symbols)} symbols available")
                logger.info(f"{'='*60}")

                # Check each symbol in priority order
                for symbol in priority_symbols:
                    if not self.is_running:
                        break

                    await self._check_and_trade(symbol)
                    await asyncio.sleep(1)  # Small delay between symbols

                # Update last check time
                self.last_check_time = datetime.now()

                # Log cycle summary
                logger.info(f"\n{'='*60}")
                logger.info(f"✓ Trading cycle complete")
                logger.info(f"  Signals checked: {self.total_signals_checked}")
                logger.info(f"  Trades executed: {self.total_trades_executed}")
                logger.info(f"  Trades rejected: {self.total_trades_rejected}")
                logger.info(f"{'='*60}\n")

                # Wait before next cycle
                logger.info(f"⏳ Waiting {self.check_frequency}s until next cycle")
                await asyncio.sleep(self.check_frequency)

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in trading loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait before retrying

    async def _check_and_log_portfolio_status(self):
        """Check and log current portfolio status"""
        try:
            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()

            balance = paper_engine.get_balance()
            positions = position_mgr.get_all_positions()

            # Calculate portfolio metrics
            metrics = self.portfolio_optimizer.get_portfolio_metrics(balance, positions)
            self.last_portfolio_metrics = metrics

            # Log portfolio status
            self.portfolio_optimizer.log_portfolio_status(metrics)

            # Warning thresholds
            if metrics.exposure_pct > 80:
                logger.warning(f"⚠️  High portfolio exposure: {metrics.exposure_pct:.1f}%")

            if metrics.correlation_risk > 0.7:
                logger.warning(f"⚠️  High correlation risk: {metrics.correlation_risk:.2%}")

            if metrics.diversification_score < 0.5:
                logger.warning(f"⚠️  Low diversification: {metrics.diversification_score:.2%}")

        except Exception as e:
            logger.error(f"Error checking portfolio status: {e}")

    async def _check_and_trade(self, symbol: str):
        """
        Check signal for a symbol and execute trade if conditions are met

        Args:
            symbol: Trading symbol to check
        """
        try:
            logger.info(f"\n🔍 Checking {symbol}")
            self.total_signals_checked += 1
            self.symbol_stats[symbol]["signals_checked"] += 1

            # Get risk manager and paper engine
            risk_mgr = get_risk_manager()
            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()

            # Check if trading is halted
            if risk_mgr.should_halt_trading():
                logger.warning(f"🛑 Trading halted due to risk limits")
                return

            # Check portfolio-level constraints
            balance = paper_engine.get_balance()
            positions = position_mgr.get_all_positions()

            should_trade, reason = self.portfolio_optimizer.should_trade_symbol(
                symbol, positions, balance
            )

            if not should_trade:
                logger.info(f"⏭️  Skipping {symbol}: {reason}")
                self.total_trades_rejected += 1
                self.symbol_stats[symbol]["trades_rejected"] += 1
                return

            # Get aggregated signal
            aggregator = await get_aggregator()
            signal = await aggregator.get_trading_signal(
                symbol=symbol,
                interval=self.interval
            )

            if not signal:
                logger.warning(f"⚠️  No signal data for {symbol}")
                return

            # Extract signal information
            action = signal.action.value
            confidence = signal.confidence
            aggregated_score = signal.aggregated_score

            logger.info(
                f"  Signal: {action} (conf: {confidence:.2f}, score: {aggregated_score:+.2f})"
            )

            # Update price history for correlation analysis
            current_price = self._extract_current_price(signal)
            if current_price:
                self.portfolio_optimizer.update_price_history(symbol, current_price)

            # Check if signal meets requirements
            meets_requirements = signal.metadata.get("meets_requirements", False)

            if not meets_requirements:
                logger.info(f"  ⏭️  Signal doesn't meet minimum requirements")
                self.total_trades_rejected += 1
                self.symbol_stats[symbol]["trades_rejected"] += 1
                return

            # Check if we should trade
            if action in ["BUY", "SELL"]:
                await self._execute_trade(symbol, action, confidence, signal)
            else:
                logger.info(f"  ⏸️  Holding position")

        except Exception as e:
            logger.error(f"❌ Error checking signal for {symbol}: {e}", exc_info=True)

    def _extract_current_price(self, signal) -> Optional[float]:
        """Extract current price from signal indicators"""
        for indicator_name, indicator_signal in signal.indicators.items():
            if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                if "current_price" in indicator_signal.metadata:
                    return float(indicator_signal.metadata["current_price"])
        return None

    async def _execute_trade(
        self,
        symbol: str,
        action: str,
        confidence: float,
        signal
    ):
        """
        Execute a trade with portfolio-optimized position sizing

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            confidence: Signal confidence score
            signal: TradingSignal object
        """
        try:
            logger.info(f"  💰 Executing {action} for {symbol} (conf: {confidence:.2f})")

            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()

            # Get current balance
            balance = paper_engine.get_balance()
            logger.info(f"  💵 Portfolio balance: ${balance:.2f}")

            # Get current price
            current_price = self._extract_current_price(signal)
            if not current_price:
                logger.warning(f"  ⚠️  No current price for {symbol}, skipping")
                self.total_trades_rejected += 1
                self.symbol_stats[symbol]["trades_rejected"] += 1
                return

            # Calculate portfolio-optimized position size
            quantity = self.portfolio_optimizer.calculate_position_size(
                symbol,
                Decimal(str(current_price)),
                balance
            )

            position_value = Decimal(str(current_price)) * quantity

            logger.info(
                f"  📊 Position sizing:"
            )
            logger.info(f"     Price: ${current_price:.2f}")
            logger.info(f"     Quantity: {quantity:.6f}")
            logger.info(f"     Value: ${position_value:.2f}")

            # Check allocation
            if symbol in self.portfolio_optimizer.allocations:
                alloc = self.portfolio_optimizer.allocations[symbol]
                logger.info(f"     Target weight: {alloc.target_weight:.1%}")
                logger.info(f"     Correlation group: {alloc.correlation_group}")

            # Execute the trade
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

            order = OrderCreate(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,
                quantity=quantity,
                strategy="multi_symbol_portfolio"
            )

            executed_order, error = await paper_engine.execute_market_order(
                order,
                Decimal(str(current_price))
            )

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                self.symbol_stats[symbol]["trades_executed"] += 1

                logger.info(f"  ✅ Trade executed for {symbol}")
                logger.info(f"     Order ID: {executed_order.id}")

                # Recalculate correlation matrix after significant portfolio change
                if len(self.portfolio_optimizer.price_history) >= 2:
                    self.portfolio_optimizer.calculate_correlation_matrix()

                # Log updated statistics
                logger.info(f"\n  📊 {symbol} Statistics:")
                stats = self.symbol_stats[symbol]
                logger.info(f"     Signals checked: {stats['signals_checked']}")
                logger.info(f"     Trades executed: {stats['trades_executed']}")
                logger.info(f"     Trades rejected: {stats['trades_rejected']}")

            else:
                self.total_trades_rejected += 1
                self.symbol_stats[symbol]["trades_rejected"] += 1
                logger.warning(f"  ❌ Trade execution failed: {error}")

        except Exception as e:
            logger.error(f"❌ Error executing trade for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1
            self.symbol_stats[symbol]["trades_rejected"] += 1

    def get_status(self) -> dict:
        """Get current status of the multi-symbol trader"""
        return {
            "is_running": self.is_running,
            "symbols": self.symbols,
            "num_symbols": len(self.symbols),
            "interval": self.interval,
            "check_frequency_seconds": self.check_frequency,
            "portfolio_optimization_enabled": self.enable_optimization,
            "total_signals_checked": self.total_signals_checked,
            "total_trades_executed": self.total_trades_executed,
            "total_trades_rejected": self.total_trades_rejected,
            "symbol_statistics": self.symbol_stats,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "portfolio_metrics": {
                "total_value": float(self.last_portfolio_metrics.total_value) if self.last_portfolio_metrics else None,
                "exposure_pct": self.last_portfolio_metrics.exposure_pct if self.last_portfolio_metrics else None,
                "num_positions": self.last_portfolio_metrics.num_positions if self.last_portfolio_metrics else None,
                "diversification_score": self.last_portfolio_metrics.diversification_score if self.last_portfolio_metrics else None,
                "correlation_risk": self.last_portfolio_metrics.correlation_risk if self.last_portfolio_metrics else None,
            } if self.last_portfolio_metrics else None,
        }


# Global instance
_multi_symbol_trader: Optional[MultiSymbolTrader] = None


def get_multi_symbol_trader() -> MultiSymbolTrader:
    """Get or create the global multi-symbol trader instance"""
    global _multi_symbol_trader
    if _multi_symbol_trader is None:
        _multi_symbol_trader = MultiSymbolTrader()
    return _multi_symbol_trader


def reset_multi_symbol_trader():
    """Reset the global multi-symbol trader instance (for testing)"""
    global _multi_symbol_trader
    _multi_symbol_trader = None
