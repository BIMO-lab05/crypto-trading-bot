#!/usr/bin/env python3
"""
Trading Signal Monitor
Purpose: Real-time monitoring of trading signals, confidence scores, and indicator decisions
Usage: python monitor_signals.py [--symbol BTCUSDT] [--interval 60] [--continuous]
"""

import asyncio
import argparse
import sys
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional
import logging

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

from app.signal_aggregator import get_aggregator
from app.models import SignalAction

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class SignalMonitor:
    """Monitor and analyze trading signals"""

    def __init__(self):
        self.aggregator = None

    async def initialize(self):
        """Initialize the signal aggregator"""
        logger.info("🚀 Initializing Signal Monitor...")
        self.aggregator = await get_aggregator()

        # Check TA service health
        is_healthy = await self.aggregator.health_check()
        if is_healthy:
            logger.info("✅ Technical Analysis Service: Connected")
        else:
            logger.warning("⚠️  Technical Analysis Service: Not Available")
            return False

        return True

    def format_signal_color(self, action: SignalAction) -> str:
        """Add color coding to signal actions"""
        colors = {
            SignalAction.BUY: "🟢",
            SignalAction.SELL: "🔴",
            SignalAction.HOLD: "🟡"
        }
        return colors.get(action, "⚪")

    def format_confidence(self, confidence: float) -> str:
        """Format confidence with visual indicator"""
        if confidence >= 0.8:
            return f"{confidence:.2f} 🔥"
        elif confidence >= 0.6:
            return f"{confidence:.2f} ✓"
        elif confidence >= 0.4:
            return f"{confidence:.2f} ~"
        else:
            return f"{confidence:.2f} ⚠️"

    async def analyze_symbol(self, symbol: str, interval: str = "60"):
        """
        Analyze a single symbol and display detailed signal breakdown

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            interval: Timeframe interval (default: 60 minutes)
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"📊 SIGNAL ANALYSIS: {symbol} ({interval}m timeframe)")
        logger.info(f"{'='*80}")
        logger.info(f"⏰ Timestamp: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

        try:
            # Fetch trading signal
            signal = await self.aggregator.get_trading_signal(symbol, interval)

            if not signal:
                logger.error(f"❌ Failed to fetch signal for {symbol}")
                return None

            # Display final decision
            logger.info("🎯 FINAL DECISION:")
            logger.info(f"   Action:     {self.format_signal_color(signal.action)} {signal.action.value}")
            logger.info(f"   Confidence: {self.format_confidence(signal.confidence)}")
            logger.info(f"   Score:      {signal.aggregated_score:+.3f}")
            logger.info(f"   Consensus:  {signal.consensus_count} indicators agree")
            logger.info("")

            # Display individual indicators
            logger.info("📈 INDICATOR BREAKDOWN:")
            logger.info(f"{'Indicator':<25} {'Signal':<8} {'Confidence':<12} {'Value':<15} {'Role'}")
            logger.info("-" * 80)

            # Sort indicators by role for better organization
            gatekeepers = []
            validators = []
            voters = []

            for name, indicator in signal.indicators.items():
                role = indicator.metadata.get("role", "VOTER") if indicator.metadata else "VOTER"

                if role == "GATEKEEPER":
                    gatekeepers.append((name, indicator))
                elif role == "VALIDATOR":
                    validators.append((name, indicator))
                else:
                    voters.append((name, indicator))

            # Display gatekeepers first (most important)
            if gatekeepers:
                for name, ind in gatekeepers:
                    value_str = f"{ind.value:.2f}" if ind.value else "N/A"
                    logger.info(
                        f"{name:<25} "
                        f"{self.format_signal_color(ind.signal)} {ind.signal.value:<6} "
                        f"{self.format_confidence(ind.confidence):<12} "
                        f"{value_str:<15} "
                        f"🚪 GATEKEEPER"
                    )

            # Display voting indicators
            if voters:
                for name, ind in voters:
                    value_str = f"{ind.value:.2f}" if ind.value else "N/A"
                    logger.info(
                        f"{name:<25} "
                        f"{self.format_signal_color(ind.signal)} {ind.signal.value:<6} "
                        f"{self.format_confidence(ind.confidence):<12} "
                        f"{value_str:<15} "
                        f"🗳️  VOTER"
                    )

            # Display validators last
            if validators:
                for name, ind in validators:
                    confirmed = ind.metadata.get("confirmed", False) if ind.metadata else False
                    value_str = f"{ind.value:.2f}" if ind.value else "N/A"
                    status = "✓ CONFIRMED" if confirmed else "✗ REJECTED"
                    logger.info(
                        f"{name:<25} "
                        f"{self.format_signal_color(ind.signal)} {ind.signal.value:<6} "
                        f"{self.format_confidence(ind.confidence):<12} "
                        f"{value_str:<15} "
                        f"🔍 {status}"
                    )

            # Display decision rationale
            logger.info("")
            logger.info("💡 DECISION RATIONALE:")

            # Count votes
            buy_votes = sum(1 for _, ind in voters if ind.signal == SignalAction.BUY)
            sell_votes = sum(1 for _, ind in voters if ind.signal == SignalAction.SELL)
            hold_votes = sum(1 for _, ind in voters if ind.signal == SignalAction.HOLD)

            logger.info(f"   Vote Breakdown: BUY={buy_votes}, SELL={sell_votes}, HOLD={hold_votes}")
            logger.info(f"   Aggregated Score: {signal.aggregated_score:+.3f} (threshold: ±0.3)")

            # Explain why this decision was made
            if signal.action == SignalAction.BUY:
                logger.info(f"   ✓ Score {signal.aggregated_score:+.3f} >= +0.3 → BUY signal")
            elif signal.action == SignalAction.SELL:
                logger.info(f"   ✓ Score {signal.aggregated_score:+.3f} <= -0.3 → SELL signal")
            else:
                logger.info(f"   ✓ Score {abs(signal.aggregated_score):.3f} < 0.3 → HOLD (weak consensus)")

            if signal.confidence < 0.6:
                logger.info(f"   ⚠️  Low confidence {signal.confidence:.2f} - signal may not be actionable")

            logger.info("")
            return signal

        except Exception as e:
            logger.error(f"❌ Error analyzing {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return None

    async def continuous_monitor(self, symbol: str, interval: str = "60", delay: int = 60):
        """
        Continuously monitor signals for a symbol

        Args:
            symbol: Trading symbol
            interval: Timeframe interval
            delay: Seconds between checks (default: 60)
        """
        logger.info(f"🔄 Starting continuous monitoring for {symbol} (checking every {delay}s)")
        logger.info(f"   Press Ctrl+C to stop\n")

        try:
            iteration = 0
            while True:
                iteration += 1
                logger.info(f"\n{'#'*80}")
                logger.info(f"# Iteration {iteration} - {datetime.now(UTC).strftime('%H:%M:%S UTC')}")
                logger.info(f"{'#'*80}")

                signal = await self.analyze_symbol(symbol, interval)

                if signal:
                    # Track signal changes
                    logger.info("")
                    logger.info("📌 KEY METRICS:")
                    logger.info(f"   Final Action: {signal.action.value}")
                    logger.info(f"   Confidence: {signal.confidence:.2%}")
                    logger.info(f"   Score: {signal.aggregated_score:+.3f}")

                logger.info(f"\n⏳ Waiting {delay} seconds until next check...")
                await asyncio.sleep(delay)

        except KeyboardInterrupt:
            logger.info("\n\n🛑 Monitoring stopped by user")
        except Exception as e:
            logger.error(f"\n❌ Monitoring error: {e}")

    async def compare_timeframes(self, symbol: str, intervals: list = None):
        """
        Compare signals across multiple timeframes

        Args:
            symbol: Trading symbol
            intervals: List of intervals (default: ["15", "60", "240"])
        """
        if intervals is None:
            intervals = ["15", "60", "240"]  # 15m, 1h, 4h

        logger.info(f"\n{'='*80}")
        logger.info(f"🔍 MULTI-TIMEFRAME ANALYSIS: {symbol}")
        logger.info(f"{'='*80}\n")

        results = []
        for interval in intervals:
            logger.info(f"⏱️  Analyzing {interval}m timeframe...")
            signal = await self.aggregator.get_trading_signal(symbol, interval)

            if signal:
                results.append((interval, signal))
                logger.info(
                    f"   {interval}m: {self.format_signal_color(signal.action)} {signal.action.value} "
                    f"(conf: {signal.confidence:.2f}, score: {signal.aggregated_score:+.3f})"
                )
            else:
                logger.warning(f"   {interval}m: Failed to fetch signal")

            await asyncio.sleep(1)  # Small delay between requests

        # Summary
        logger.info("\n📊 TIMEFRAME ALIGNMENT:")
        if len(results) >= 2:
            actions = [signal.action for _, signal in results]
            if all(action == actions[0] for action in actions):
                logger.info(f"   ✅ Strong alignment: All timeframes agree on {actions[0].value}")
            else:
                logger.info(f"   ⚠️  Mixed signals: Timeframes diverge")
                buy_count = sum(1 for action in actions if action == SignalAction.BUY)
                sell_count = sum(1 for action in actions if action == SignalAction.SELL)
                hold_count = sum(1 for action in actions if action == SignalAction.HOLD)
                logger.info(f"      BUY: {buy_count}/{len(results)}")
                logger.info(f"      SELL: {sell_count}/{len(results)}")
                logger.info(f"      HOLD: {hold_count}/{len(results)}")

        logger.info("")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Monitor trading signals and confidence scores"
    )
    parser.add_argument(
        "--symbol",
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--interval",
        default="60",
        help="Timeframe interval in minutes (default: 60)"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Continuously monitor signals"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=60,
        help="Delay between checks in continuous mode (default: 60 seconds)"
    )
    parser.add_argument(
        "--multi-timeframe",
        action="store_true",
        help="Compare signals across multiple timeframes"
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["15", "60", "240"],
        help="Timeframes for multi-timeframe analysis (default: 15 60 240)"
    )

    args = parser.parse_args()

    # Initialize monitor
    monitor = SignalMonitor()
    if not await monitor.initialize():
        logger.error("❌ Failed to initialize monitor - Technical Analysis service unavailable")
        return 1

    # Run monitoring based on mode
    try:
        if args.multi_timeframe:
            await monitor.compare_timeframes(args.symbol, args.timeframes)
        elif args.continuous:
            await monitor.continuous_monitor(args.symbol, args.interval, args.delay)
        else:
            await monitor.analyze_symbol(args.symbol, args.interval)

        return 0

    except Exception as e:
        logger.error(f"❌ Monitoring failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1
    finally:
        # Cleanup
        if monitor.aggregator:
            await monitor.aggregator.close()


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
