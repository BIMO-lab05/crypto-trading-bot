#!/usr/bin/env python3
"""
Automated Trading Loop with Notifications
Purpose: Continuously monitor trading signals and execute trades automatically
Features:
- Configurable trading intervals
- Risk management
- Emergency stop mechanisms
- Comprehensive logging
- Performance tracking
- Real-time notifications (Email & Telegram)
"""

import asyncio
import httpx
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Host-run script: repo-root shared/ is importable (CLAUDE.md money rules).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from shared.account import PAPER_INITIAL_BALANCE  # noqa: E402,F401

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/trading_loop.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class TradingMode(Enum):
    """Trading modes"""

    PAPER = "paper"  # Paper trading (simulation)
    LIVE = "live"  # Live trading with real money


class SignalStrength(Enum):
    """Signal strength levels"""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class TradingConfig:
    """Trading configuration"""

    # API endpoints
    api_gateway_url: str = "http://localhost:8000"
    notification_service_url: str = "http://localhost:8007"

    # Trading parameters
    symbols: List[str] = None
    interval_minutes: int = 5  # Check signals every 5 minutes
    signal_interval: int = 60  # Use 60-minute candles for analysis

    # Risk management
    max_position_size_pct: float = 2.0  # Max 2% per trade
    stop_loss_pct: float = 3.0  # 3% stop loss
    take_profit_pct: float = 6.0  # 6% take profit
    daily_loss_limit_pct: float = 5.0  # Stop if daily loss exceeds 5%
    max_total_exposure_pct: float = 20.0  # Max 20% total portfolio exposure

    # Signal requirements - ADJUSTED 2026-02-25: Lowered from 0.65 to 0.40 to enable trading
    min_confidence: float = (
        0.40  # Minimum signal confidence to trade (40% - balanced for current market)
    )
    require_consensus: bool = True  # Require multiple indicators to agree

    # Trading mode
    mode: TradingMode = TradingMode.PAPER

    # Safety features
    enable_emergency_stop: bool = True
    max_trades_per_day: int = 10
    cooldown_after_loss_minutes: int = 30

    # Notification settings
    enable_notifications: bool = True

    def __post_init__(self):
        """Initialize default symbols"""
        if self.symbols is None:
            self.symbols = ["BTCUSDT", "ETHUSDT"]


class TradingBot:
    """Automated trading bot with notification support"""

    def __init__(self, config: TradingConfig):
        """Initialize trading bot"""
        self.config = config
        self.client = httpx.AsyncClient(timeout=30.0)
        self.running = False
        self.trades_today = 0
        self.daily_pnl = 0.0
        self.last_trade_time = None
        self.cooldown_until = None

        # Statistics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0

        logger.info(f"Trading Bot initialized in {config.mode.value} mode")
        logger.info(f"Monitoring symbols: {config.symbols}")
        logger.info(f"Check interval: {config.interval_minutes} minutes")
        logger.info(f"Notifications: {'Enabled' if config.enable_notifications else 'Disabled'}")

    async def _send_notification(self, endpoint: str, data: Dict) -> bool:
        """
        Send notification to notification service

        Args:
            endpoint: API endpoint (e.g., 'notify/trade')
            data: Notification data

        Returns:
            bool: Success status
        """
        if not self.config.enable_notifications:
            return False

        try:
            url = f"{self.config.notification_service_url}/api/v1/{endpoint}"
            response = await self.client.post(url, json=data, timeout=5.0)
            response.raise_for_status()
            logger.debug(f"Notification sent: {endpoint}")
            return True
        except Exception as e:
            logger.warning(f"Failed to send notification: {e}")
            return False

    async def start(self):
        """Start the trading loop"""
        self.running = True
        logger.info("=" * 80)
        logger.info("AUTOMATED TRADING BOT STARTED")
        logger.info("=" * 80)

        # Send startup notification
        await self._send_startup_notification()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        try:
            while self.running:
                await self._trading_cycle()
                await asyncio.sleep(self.config.interval_minutes * 60)
        except Exception as e:
            logger.error(f"Fatal error in trading loop: {e}", exc_info=True)
            # Send error notification
            await self._send_notification(
                "notify/error",
                {
                    "error_message": f"Fatal error in trading loop: {str(e)}",
                    "context": {"timestamp": datetime.now().isoformat()},
                },
            )
        finally:
            await self.stop()

    async def _send_startup_notification(self):
        """Send startup notification"""
        config_summary = {
            "mode": self.config.mode.value,
            "symbols": self.config.symbols,
            "interval_minutes": self.config.interval_minutes,
            # Account size comes from the declaration of record
            # (shared/account.py) — never a literal. This value is announced
            # to the operator over Telegram on every start; a hardcoded
            # 10000.0 here once reported 100x the then-declared $100 account.
            # ADR-029 later set the declared size to $10,000 again, but the
            # routing is the fix, not the number.
            "capital": PAPER_INITIAL_BALANCE,
            "max_position_pct": self.config.max_position_size_pct,
            "daily_loss_limit": self.config.daily_loss_limit_pct,
            "stop_loss_pct": self.config.stop_loss_pct,
        }
        await self._send_notification("notify/startup", config_summary)

    async def stop(self):
        """Stop the trading loop"""
        logger.info("Stopping trading bot...")
        self.running = False
        await self.client.aclose()
        self._print_summary()
        logger.info("Trading bot stopped")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.running = False

    async def _trading_cycle(self):
        """Execute one trading cycle"""
        cycle_start = datetime.now()
        logger.info("-" * 80)
        logger.info(f"Starting trading cycle at {cycle_start}")

        try:
            # Check portfolio status
            portfolio = await self._get_portfolio()
            if not portfolio:
                logger.error("Failed to fetch portfolio")
                return

            # Check daily loss limit
            if self._check_daily_loss_limit(portfolio):
                logger.warning("Daily loss limit reached - halting trading")
                # Send critical notification
                total_loss = float(portfolio.get("total_pnl", 0))
                await self._send_notification("notify/daily-limit", total_loss)
                self.running = False
                return

            # Check cooldown
            if self._in_cooldown():
                logger.info(f"In cooldown period until {self.cooldown_until}")
                return

            # Check max trades limit
            if self.trades_today >= self.config.max_trades_per_day:
                logger.warning(f"Max trades per day ({self.config.max_trades_per_day}) reached")
                return

            # Process each symbol
            for symbol in self.config.symbols:
                await self._process_symbol(symbol, portfolio)

            # Log cycle completion
            cycle_duration = (datetime.now() - cycle_start).total_seconds()
            logger.info(f"Trading cycle completed in {cycle_duration:.2f} seconds")
            logger.info(f"Trades today: {self.trades_today}/{self.config.max_trades_per_day}")
            logger.info(f"Daily P&L: ${self.daily_pnl:.2f}")

        except Exception as e:
            logger.error(f"Error in trading cycle: {e}", exc_info=True)
            # Send error notification
            await self._send_notification(
                "notify/error",
                {
                    "error_message": f"Error in trading cycle: {str(e)}",
                    "context": {"cycle_start": cycle_start.isoformat()},
                },
            )

    async def _process_symbol(self, symbol: str, portfolio: Dict):
        """Process trading signals for a symbol"""
        try:
            logger.info(f"Processing {symbol}...")

            # Get current price
            ticker = await self._get_ticker(symbol)
            if not ticker:
                logger.warning(f"Failed to get ticker for {symbol}")
                return

            current_price = float(ticker["last_price"])
            logger.info(f"{symbol} current price: ${current_price:,.2f}")

            # Get trading signal
            signal = await self._get_signal(symbol)
            if not signal:
                logger.warning(f"Failed to get signal for {symbol}")
                return

            # Evaluate signal with detailed diagnostics
            action = self._evaluate_signal(symbol, signal)

            # Execute trade if appropriate
            if action in ["BUY", "SELL"]:
                await self._execute_trade(symbol, action, current_price, signal, portfolio)
            else:
                logger.info(f"✋ {symbol}: No trade executed - {action}")

        except Exception as e:
            logger.error(f"Error processing {symbol}: {e}", exc_info=True)

    async def _get_portfolio(self) -> Optional[Dict]:
        """Get current portfolio"""
        try:
            url = f"{self.config.api_gateway_url}/api/portfolio"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("portfolio")
        except Exception as e:
            logger.error(f"Error fetching portfolio: {e}")
            return None

    async def _get_ticker(self, symbol: str) -> Optional[Dict]:
        """Get current ticker data"""
        try:
            url = f"{self.config.api_gateway_url}/api/market/ticker/{symbol}"
            response = await self.client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("ticker")
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    async def _get_signal(self, symbol: str) -> Optional[Dict]:
        """Get trading signal"""
        try:
            url = f"{self.config.api_gateway_url}/api/trading/signals/{symbol}"
            params = {"interval": self.config.signal_interval}
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("signal")
        except Exception as e:
            logger.error(f"Error fetching signal for {symbol}: {e}")
            return None

    def _evaluate_signal(self, symbol: str, signal: Dict) -> str:
        """
        Evaluate trading signal and decide action with detailed diagnostics

        Args:
            symbol: Trading symbol
            signal: Signal data from trading engine

        Returns:
            Action to take: BUY, SELL, or HOLD
        """
        if not signal:
            logger.warning(f"⚠️  {symbol}: No signal data received")
            return "HOLD"

        # Extract signal details
        signal_action = signal.get("action", "HOLD")
        confidence = signal.get("confidence", 0)
        aggregated_score = signal.get("aggregated_score", 0)
        consensus_count = signal.get("consensus_count", 0)
        indicators = signal.get("indicators", {})
        metadata = signal.get("metadata", {})

        # Get thresholds from metadata or use config
        min_confidence = metadata.get("min_confidence_required", self.config.min_confidence)
        min_consensus = metadata.get("min_consensus_required", 3)

        # Print detailed signal diagnostics
        logger.info("=" * 80)
        logger.info(f"📊 SIGNAL DIAGNOSTICS FOR {symbol}")
        logger.info("=" * 80)
        logger.info(f"Current Price: ${signal.get('metadata', {}).get('current_price', 'N/A')}")
        logger.info(f"Signal Action: {signal_action}")
        logger.info(f"Aggregated Score: {aggregated_score:.3f}")
        logger.info(f"Confidence: {confidence:.1%} (min required: {min_confidence:.1%})")
        logger.info(f"Consensus: {consensus_count} indicators (min required: {min_consensus})")
        logger.info("-" * 80)

        # Show individual indicators
        logger.info("📈 INDIVIDUAL INDICATORS:")
        buy_count = 0
        sell_count = 0
        hold_count = 0

        for name, data in indicators.items():
            if name == "ATR":  # Skip ATR as it's not a signal
                continue

            ind_signal = data.get("signal", "HOLD")
            ind_confidence = data.get("confidence", 0)
            ind_value = data.get("value", "N/A")
            ind_metadata = data.get("metadata", {})

            # Count votes
            if ind_signal == "BUY":
                buy_count += 1
                emoji = "🟢"
            elif ind_signal == "SELL":
                sell_count += 1
                emoji = "🔴"
            else:
                hold_count += 1
                emoji = "⚪"

            # Format metadata highlights
            highlights = []
            if "weight" in ind_metadata:
                highlights.append(f"weight: {ind_metadata['weight']}x")
            if "role" in ind_metadata:
                highlights.append(f"role: {ind_metadata['role']}")
            if "trend" in ind_metadata:
                highlights.append(f"trend: {ind_metadata['trend']}")
            if "confirmed" in ind_metadata:
                highlights.append(f"confirmed: {ind_metadata['confirmed']}")

            meta_str = f" [{', '.join(highlights)}]" if highlights else ""

            logger.info(
                f"  {emoji} {name:20s}: {ind_signal:4s} (conf: {ind_confidence:5.1%}) {meta_str}"
            )

        logger.info("-" * 80)
        logger.info(
            f"📊 VOTE SUMMARY: 🟢 BUY: {buy_count} | 🔴 SELL: {sell_count} | ⚪ HOLD: {hold_count}"
        )
        logger.info("-" * 80)

        # Check requirements with detailed feedback
        reasons_to_hold = []

        # Check confidence threshold
        confidence_pass = confidence >= min_confidence
        if not confidence_pass:
            reasons_to_hold.append(
                f"Low confidence: {confidence:.1%} < {min_confidence:.1%} "
                f"(need {(min_confidence - confidence):.1%} more)"
            )

        # Check consensus
        consensus_pass = consensus_count >= min_consensus
        if not consensus_pass:
            reasons_to_hold.append(
                f"Low consensus: {consensus_count} < {min_consensus} "
                f"(need {min_consensus - consensus_count} more indicators to agree)"
            )

        # Check for trend blocks or volume issues
        if metadata.get("trend_blocked"):
            reasons_to_hold.append(f"Trend filter blocked: {metadata.get('trend_reason', 'N/A')}")

        volume_penalty = metadata.get("volume_penalty", 1.0)
        if volume_penalty < 1.0:
            reasons_to_hold.append(
                f"Volume penalty applied: {volume_penalty:.0%} "
                f"({metadata.get('volume_reason', 'Low volume')})"
            )

        # Check if requirements met
        meets_requirements = metadata.get("meets_requirements", False)

        logger.info("✅ REQUIREMENT CHECKS:")
        logger.info(
            f"  {'✓' if confidence_pass else '✗'} Confidence: {confidence:.1%} {'≥' if confidence_pass else '<'} {min_confidence:.1%}"
        )
        logger.info(
            f"  {'✓' if consensus_pass else '✗'} Consensus: {consensus_count} {'≥' if consensus_pass else '<'} {min_consensus}"
        )
        logger.info(
            f"  {'✓' if meets_requirements else '✗'} Overall: Requirements {'MET' if meets_requirements else 'NOT MET'}"
        )

        if reasons_to_hold:
            logger.info("-" * 80)
            logger.warning("⚠️  REASONS NOT TRADING:")
            for reason in reasons_to_hold:
                logger.warning(f"  • {reason}")

        logger.info("=" * 80)

        # Make final decision
        if not meets_requirements or reasons_to_hold:
            logger.info(f"🛑 DECISION: HOLD - Not trading {symbol} (requirements not met)")
            return "HOLD"

        # All checks passed
        logger.info(f"✅ DECISION: {signal_action} - All requirements met!")
        return signal_action

    async def _execute_trade(
        self, symbol: str, action: str, price: float, signal: Dict, portfolio: Dict
    ):
        """Execute a trade"""
        try:
            # Calculate position size
            cash_balance = float(portfolio.get("cash_balance", 0))
            position_size = self._calculate_position_size(cash_balance, price)

            if position_size <= 0:
                logger.warning(f"Insufficient funds for {symbol} trade")
                return

            # Prepare trade request
            if action == "BUY":
                url = f"{self.config.api_gateway_url}/api/portfolio/buy"
            else:  # SELL
                url = f"{self.config.api_gateway_url}/api/portfolio/sell"

            params = {"symbol": symbol, "quantity": position_size, "price": price}

            # Execute trade
            logger.info(f"Executing {action} {position_size} {symbol} @ ${price:,.2f}")
            response = await self.client.post(url, params=params)
            response.raise_for_status()
            result = response.json()

            # Update statistics
            self.trades_today += 1
            self.total_trades += 1
            self.last_trade_time = datetime.now()

            logger.info(f"Trade executed successfully: {result}")

            # Send trade notification
            await self._send_notification(
                "notify/trade",
                {
                    "action": action,
                    "symbol": symbol,
                    "quantity": position_size,
                    "price": price,
                    "timestamp": datetime.now().isoformat(),
                    "signal_confidence": signal.get("confidence", 0),
                },
            )

            # Log trade details
            self._log_trade(symbol, action, position_size, price, signal, result)

        except Exception as e:
            logger.error(f"Error executing trade for {symbol}: {e}", exc_info=True)
            # Send error notification
            await self._send_notification(
                "notify/error",
                {
                    "error_message": f"Trade execution failed for {symbol}: {str(e)}",
                    "context": {"symbol": symbol, "action": action, "price": price},
                },
            )
            # Enter cooldown after failed trade
            self.cooldown_until = datetime.now() + timedelta(
                minutes=self.config.cooldown_after_loss_minutes
            )

    def _calculate_position_size(self, cash_balance: float, price: float) -> float:
        """Calculate position size based on risk management rules"""
        # Max position based on percentage
        max_position_value = cash_balance * (self.config.max_position_size_pct / 100)

        # Calculate quantity
        quantity = max_position_value / price

        # Round to reasonable precision
        quantity = round(quantity, 8)

        return quantity

    def _check_daily_loss_limit(self, portfolio: Dict) -> bool:
        """Check if daily loss limit has been reached"""
        total_pnl = float(portfolio.get("total_pnl", 0))
        # FIX 2026-08-05 (AUDIT 2.5): was a hardcoded 10000.0, which made this
        # breaker 100x too lenient on the real $100 account. Prefer the live
        # portfolio figure; otherwise the declaration of record
        # (shared/account.py).
        if "initial_balance" in portfolio:
            initial_balance = float(portfolio["initial_balance"])
        else:
            initial_balance = PAPER_INITIAL_BALANCE

        loss_pct = abs(total_pnl / initial_balance * 100)

        if total_pnl < 0 and loss_pct >= self.config.daily_loss_limit_pct:
            logger.critical(f"DAILY LOSS LIMIT REACHED: {loss_pct:.2f}% loss")
            return True

        return False

    def _in_cooldown(self) -> bool:
        """Check if in cooldown period"""
        if self.cooldown_until and datetime.now() < self.cooldown_until:
            return True
        self.cooldown_until = None
        return False

    def _log_trade(
        self,
        symbol: str,
        action: str,
        quantity: float,
        price: float,
        signal: Dict,
        result: Dict,
    ):
        """Log trade details"""
        trade_log = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "total_value": quantity * price,
            "signal_confidence": signal.get("confidence"),
            "signal_consensus": signal.get("consensus_strength"),
            "result": result,
        }

        # Write to trade log file
        with open("logs/trades.jsonl", "a") as f:
            f.write(json.dumps(trade_log) + "\n")

    def _print_summary(self):
        """Print trading session summary"""
        logger.info("=" * 80)
        logger.info("TRADING SESSION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total trades executed: {self.total_trades}")
        logger.info(f"Winning trades: {self.winning_trades}")
        logger.info(f"Losing trades: {self.losing_trades}")
        if self.total_trades > 0:
            win_rate = self.winning_trades / self.total_trades * 100
            logger.info(f"Win rate: {win_rate:.2f}%")
        logger.info(f"Total profit/loss: ${self.total_profit:.2f}")
        logger.info("=" * 80)


async def main():
    """Main entry point"""
    # Load configuration - ADJUSTED 2026-02-25: Lowered confidence threshold
    config = TradingConfig(
        symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        interval_minutes=5,
        signal_interval=60,
        min_confidence=0.40,  # Lowered from 0.65 to enable trading in current market
        mode=TradingMode.PAPER,
        max_trades_per_day=20,
        enable_notifications=True,  # Enable notifications
    )

    # Create and start bot
    bot = TradingBot(config)
    await bot.start()


if __name__ == "__main__":
    # Create logs directory
    import os

    os.makedirs("logs", exist_ok=True)

    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
