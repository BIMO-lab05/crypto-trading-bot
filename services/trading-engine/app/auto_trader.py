"""
Auto Trader - Automated Trading Loop
Purpose: Background task that monitors signals and executes trades automatically
"""

import asyncio
import logging
from typing import Optional, List
from datetime import datetime
from decimal import Decimal

from app.config import get_settings
from app.signal_aggregator import get_aggregator
from app.paper_trading import get_paper_engine
from app.risk_manager import get_risk_manager
from app.position_manager import get_position_manager
from app.position_sizing import get_position_sizer, SizingMethod
from app.performance_tracker import get_performance_tracker
from app.models import OrderSide, OrderType, OrderCreate, OrderStatus

logger = logging.getLogger(__name__)
settings = get_settings()


class AutoTrader:
    """
    Automated trading loop that monitors signals and executes trades

    Features:
    - Periodic signal monitoring (configurable interval)
    - Automatic trade execution based on signal strength
    - Risk management integration
    - Position tracking
    - Emergency halt on risk limits
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        interval: str = "60",
        check_frequency_seconds: int = 300,  # Check every 5 minutes by default
        enable_volume_profile: bool = False,  # Enable VP analysis (Phase 3)
        position_sizing_method: SizingMethod = SizingMethod.CONFIDENCE_ADJUSTED,  # Dynamic sizing
        use_performance_data: bool = True,  # Use performance tracker for Kelly
    ):
        """
        Initialize the automated trader

        Args:
            symbols: List of trading symbols (default: from config)
            interval: Timeframe for analysis (default: 60 minutes)
            check_frequency_seconds: How often to check signals (default: 300 seconds)
            enable_volume_profile: Enable Volume Profile analysis (default: False)
            position_sizing_method: Position sizing method (default: CONFIDENCE_ADJUSTED)
            use_performance_data: Use performance tracker for Kelly calculation
        """
        self.symbols = symbols or settings.trading_symbols
        self.interval = interval
        self.check_frequency = check_frequency_seconds
        self.enable_vp = enable_volume_profile
        self.position_sizing_method = position_sizing_method
        self.use_performance_data = use_performance_data
        self.is_running = False
        self.task: Optional[asyncio.Task] = None

        # Statistics
        self.total_signals_checked = 0
        self.total_trades_executed = 0
        self.total_trades_rejected = 0
        self.last_check_time: Optional[datetime] = None

        logger.info(
            f"AutoTrader initialized: symbols={self.symbols}, "
            f"interval={self.interval}, frequency={self.check_frequency}s, "
            f"VP={'ENABLED' if self.enable_vp else 'DISABLED'}, "
            f"Sizing={self.position_sizing_method.value}"
        )

    async def start(self):
        """Start the automated trading loop"""
        if self.is_running:
            logger.warning("AutoTrader is already running")
            return False

        logger.info("🚀 Starting automated trading loop")
        self.is_running = True
        self.task = asyncio.create_task(self._trading_loop())
        return True

    async def stop(self):
        """Stop the automated trading loop"""
        if not self.is_running:
            logger.warning("AutoTrader is not running")
            return False

        logger.info("🛑 Stopping automated trading loop")
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
        logger.info("📊 Automated trading loop started")

        while self.is_running:
            try:
                # Check each symbol
                for symbol in self.symbols:
                    await self._check_and_trade(symbol)

                # Update last check time
                self.last_check_time = datetime.now()

                # Wait before next check
                logger.info(f"⏳ Waiting {self.check_frequency}s until next check")
                await asyncio.sleep(self.check_frequency)

            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"❌ Error in trading loop: {e}", exc_info=True)
                # Wait a bit before retrying to avoid rapid error loops
                await asyncio.sleep(60)

    async def _check_and_trade(self, symbol: str):
        """
        Check signal for a symbol and execute trade if conditions are met

        Args:
            symbol: Trading symbol to check
        """
        try:
            logger.info(f"🔍 Checking signal for {symbol}")
            self.total_signals_checked += 1

            # Get risk manager
            risk_mgr = get_risk_manager()

            # Check if trading is halted
            if risk_mgr.should_halt_trading():
                logger.warning(f"🛑 Trading halted due to risk limits for {symbol}")
                return

            # Get aggregated signal with multi-timeframe confirmation (Phase 2)
            # and Volume Profile analysis (Phase 3) if enabled
            aggregator = await get_aggregator()

            if self.enable_vp:
                # Use VP-enhanced signals (Phase 3)
                signal = await aggregator.get_trading_signal_with_vp(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"],
                    enable_vp=True,
                    vp_lookback=100
                )
            else:
                # Use multi-timeframe only (Phase 2)
                signal = await aggregator.get_trading_signal_multi_timeframe(
                    symbol=symbol,
                    primary_interval=self.interval,
                    timeframes=["15", self.interval, "240"]  # Short, medium, long-term
                )

            if not signal:
                logger.warning(f"⚠️ No signal data returned for {symbol}")
                return

            # Extract signal information
            action = signal.action.value  # Convert enum to string
            confidence = signal.confidence
            aggregated_score = signal.aggregated_score

            # Log multi-timeframe analysis if available (Phase 2)
            mtf_data = signal.metadata.get("multi_timeframe", {})
            vp_data = signal.metadata.get("volume_profile", {})

            if self.enable_vp and vp_data:
                # Show VP-enhanced signal (Phase 3)
                logger.info(
                    f"📈 Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2%}, score: {aggregated_score:.2f})"
                )
                logger.info(
                    f"   MTF: {mtf_data.get('alignment_strength', 'N/A')} "
                    f"(modifier: {mtf_data.get('confidence_modifier', 1.0):.2f}x)"
                )
                logger.info(
                    f"   VP: {vp_data.get('strategy', 'N/A')} | {vp_data.get('position', 'N/A')} "
                    f"| POC=${vp_data.get('poc', 0):.2f} | SL=${vp_data.get('stop_loss', 0):.2f}"
                )
            elif mtf_data and mtf_data.get("enabled"):
                # Show MTF-only signal (Phase 2)
                logger.info(
                    f"📈 Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2%}, score: {aggregated_score:.2f}) "
                    f"[MTF: {mtf_data.get('alignment_strength')} "
                    f"modifier: {mtf_data.get('confidence_modifier', 1.0):.2f}x]"
                )
            else:
                # Fallback logging
                logger.info(
                    f"📈 Signal for {symbol}: {action} "
                    f"(confidence: {confidence:.2f}, score: {aggregated_score:.2f})"
                )

            # Check if signal meets requirements
            meets_requirements = signal.metadata.get("meets_requirements", False)

            if not meets_requirements:
                logger.info(f"⏭️  Signal doesn't meet minimum requirements for {symbol}")
                self.total_trades_rejected += 1
                return

            # Check if we should trade
            if action in ["BUY", "SELL"]:
                await self._execute_trade(symbol, action, confidence, signal)
            else:
                logger.info(f"⏸️  Holding position for {symbol}")

        except Exception as e:
            logger.error(f"❌ Error checking signal for {symbol}: {e}", exc_info=True)

    async def _execute_trade(
        self,
        symbol: str,
        action: str,
        confidence: float,
        signal
    ):
        """
        Execute a trade based on the signal

        Args:
            symbol: Trading symbol
            action: BUY or SELL
            confidence: Signal confidence score
            signal: TradingSignal object
        """
        try:
            logger.info(f"💰 Executing {action} trade for {symbol} (confidence: {confidence:.2f})")

            # Get paper trading engine
            paper_engine = get_paper_engine()
            position_mgr = get_position_manager()
            risk_mgr = get_risk_manager()
            position_sizer = get_position_sizer()

            # Get current balance
            balance = paper_engine.get_balance()  # Fixed: get_balance() is synchronous
            logger.info(f"💵 Current balance: ${balance:.2f}")

            # Get current price from signal indicators
            current_price = None

            # Try to get price from indicators (dict of IndicatorSignal objects)
            for indicator_name, indicator_signal in signal.indicators.items():
                if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                    if "current_price" in indicator_signal.metadata:
                        current_price = float(indicator_signal.metadata["current_price"])
                        break

            if not current_price:
                logger.warning(f"⚠️ No current price found for {symbol}, skipping trade")
                self.total_trades_rejected += 1
                return

            # Get performance stats for Kelly calculation
            performance_stats = None
            if self.use_performance_data:
                try:
                    perf_tracker = get_performance_tracker()
                    performance_stats = position_sizer.get_performance_stats_from_tracker(perf_tracker)
                    logger.debug(
                        f"📊 Performance stats: win_rate={performance_stats.get('win_rate', 0):.2%}, "
                        f"trades={performance_stats.get('total_trades', 0)}"
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Could not get performance stats: {e}")

            # Get stop loss from VP data if available
            stop_loss_pct = None
            vp_data = signal.metadata.get("volume_profile", {})
            if vp_data and vp_data.get("stop_loss"):
                stop_loss_price = vp_data.get("stop_loss", 0)
                stop_loss_pct = abs(current_price - stop_loss_price) / current_price
                logger.debug(f"🛡️ VP Stop Loss: ${stop_loss_price:.2f} ({stop_loss_pct:.2%})")

            # Calculate dynamic position size
            size_result = position_sizer.calculate_position_size(
                method=self.position_sizing_method,
                current_balance=Decimal(str(balance)),
                current_price=Decimal(str(current_price)),
                signal_confidence=confidence,
                performance_stats=performance_stats,
                stop_loss_pct=stop_loss_pct
            )

            # Use calculated position size
            quantity = size_result.quantity
            position_value = size_result.position_value

            logger.info(
                f"📊 Position sizing: {size_result.method.value} "
                f"| Size: {size_result.position_size_pct:.2f}% "
                f"| Value: ${position_value:.2f} "
                f"| Qty: {quantity:.4f}"
            )
            logger.info(f"💡 Reasoning: {size_result.reasoning}")

            # Check if we already have an open position
            open_positions = position_mgr.get_open_positions()  # Fixed: get_open_positions() is synchronous
            has_position = any(p.symbol == symbol for p in open_positions)

            if has_position:
                logger.info(f"⚠️ Already have open position for {symbol}, skipping")
                self.total_trades_rejected += 1
                return

            # Execute the trade
            side = OrderSide.BUY if action == "BUY" else OrderSide.SELL

            # Fixed: Use execute_market_order() with proper OrderCreate object
            order = OrderCreate(
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,  # Field name is 'type', not 'order_type'
                quantity=Decimal(str(quantity)),
                strategy="auto_trader"
            )

            executed_order, error = await paper_engine.execute_market_order(order, Decimal(str(current_price)))

            if executed_order.status == OrderStatus.FILLED:
                self.total_trades_executed += 1
                logger.info(f"✅ Trade executed successfully for {symbol}")
                logger.info(f"📊 Stats: Checked={self.total_signals_checked}, "
                          f"Executed={self.total_trades_executed}, "
                          f"Rejected={self.total_trades_rejected}")
            else:
                self.total_trades_rejected += 1
                logger.warning(f"❌ Trade execution failed for {symbol}: {error}")

        except Exception as e:
            logger.error(f"❌ Error executing trade for {symbol}: {e}", exc_info=True)
            self.total_trades_rejected += 1

    def get_status(self) -> dict:
        """Get current status of the auto trader"""
        return {
            "is_running": self.is_running,
            "symbols": self.symbols,
            "interval": self.interval,
            "check_frequency_seconds": self.check_frequency,
            "total_signals_checked": self.total_signals_checked,
            "total_trades_executed": self.total_trades_executed,
            "total_trades_rejected": self.total_trades_rejected,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
        }


# Global instance
_auto_trader: Optional[AutoTrader] = None


def get_auto_trader() -> AutoTrader:
    """Get or create the global auto trader instance"""
    global _auto_trader
    if _auto_trader is None:
        _auto_trader = AutoTrader()
    return _auto_trader


def reset_auto_trader():
    """Reset the global auto trader instance (for testing)"""
    global _auto_trader
    _auto_trader = None
