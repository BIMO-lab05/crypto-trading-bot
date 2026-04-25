#!/usr/bin/env python3
"""
Test Signal Diagnostics
Quick script to test the enhanced signal diagnostics logging
"""

import asyncio
import httpx
import logging
from datetime import datetime

# Configure logging with color support
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def test_signal_diagnostics():
    """Test signal diagnostics for a symbol"""

    symbol = "BTCUSDT"
    api_url = "http://localhost:8000"

    logger.info(f"🔍 Testing Signal Diagnostics for {symbol}")
    logger.info("=" * 80)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Get current ticker
            logger.info("📊 Fetching current price...")
            ticker_response = await client.get(f"{api_url}/api/market/ticker/{symbol}")
            ticker_response.raise_for_status()
            ticker_data = ticker_response.json()

            if 'ticker' in ticker_data:
                ticker = ticker_data['ticker']
                logger.info(f"✓ Current Price: ${ticker['last_price']:,.2f}")
                logger.info(f"  24h Change: {ticker['price_24h_pcnt']:.2%}")
                logger.info(f"  24h Volume: {ticker['volume_24h']:,.2f}")

            # Get trading signal
            logger.info("\n📈 Fetching trading signals...")
            signal_response = await client.get(
                f"{api_url}/api/trading/signals/{symbol}",
                params={"interval": 60}
            )
            signal_response.raise_for_status()
            signal_data = signal_response.json()

            if 'signal' in signal_data:
                signal = signal_data['signal']

                # Display signal overview
                logger.info("\n" + "=" * 80)
                logger.info(f"📊 SIGNAL ANALYSIS FOR {symbol}")
                logger.info("=" * 80)
                logger.info(f"Action: {signal.get('action', 'N/A')}")
                logger.info(f"Confidence: {signal.get('confidence', 0):.1%}")
                logger.info(f"Aggregated Score: {signal.get('aggregated_score', 0):.3f}")
                logger.info(f"Consensus: {signal.get('consensus_count', 0)} indicators")
                logger.info("-" * 80)

                # Display individual indicators
                indicators = signal.get('indicators', {})
                logger.info("\n📈 INDIVIDUAL INDICATORS:")

                buy_count = 0
                sell_count = 0
                hold_count = 0

                for name, data in indicators.items():
                    if name == 'ATR':
                        continue

                    ind_signal = data.get('signal', 'HOLD')
                    ind_confidence = data.get('confidence', 0)

                    if ind_signal == 'BUY':
                        buy_count += 1
                        emoji = "🟢"
                    elif ind_signal == 'SELL':
                        sell_count += 1
                        emoji = "🔴"
                    else:
                        hold_count += 1
                        emoji = "⚪"

                    logger.info(f"  {emoji} {name:20s}: {ind_signal:4s} (conf: {ind_confidence:5.1%})")

                logger.info("-" * 80)
                logger.info(f"📊 VOTE SUMMARY: 🟢 BUY: {buy_count} | 🔴 SELL: {sell_count} | ⚪ HOLD: {hold_count}")

                # Display requirements check
                metadata = signal.get('metadata', {})
                min_confidence = metadata.get('min_confidence_required', 0.65)
                min_consensus = metadata.get('min_consensus_required', 3)
                meets_requirements = metadata.get('meets_requirements', False)

                logger.info("\n✅ REQUIREMENT CHECKS:")
                confidence = signal.get('confidence', 0)
                consensus = signal.get('consensus_count', 0)

                conf_pass = confidence >= min_confidence
                cons_pass = consensus >= min_consensus

                logger.info(f"  {'✓' if conf_pass else '✗'} Confidence: {confidence:.1%} {'≥' if conf_pass else '<'} {min_confidence:.1%}")
                logger.info(f"  {'✓' if cons_pass else '✗'} Consensus: {consensus} {'≥' if cons_pass else '<'} {min_consensus}")
                logger.info(f"  {'✓' if meets_requirements else '✗'} Overall: Requirements {'MET' if meets_requirements else 'NOT MET'}")

                # Show why not trading
                if not meets_requirements:
                    logger.info("\n⚠️  REASONS NOT TRADING:")
                    if not conf_pass:
                        shortage = min_confidence - confidence
                        logger.warning(f"  • Low confidence: {confidence:.1%} < {min_confidence:.1%} (need {shortage:.1%} more)")
                    if not cons_pass:
                        shortage = min_consensus - consensus
                        logger.warning(f"  • Low consensus: {consensus} < {min_consensus} (need {shortage} more)")

                    if metadata.get('trend_blocked'):
                        logger.warning(f"  • Trend blocked: {metadata.get('trend_reason', 'N/A')}")

                    volume_penalty = metadata.get('volume_penalty', 1.0)
                    if volume_penalty < 1.0:
                        logger.warning(f"  • Volume penalty: {volume_penalty:.0%} ({metadata.get('volume_reason', 'N/A')})")

                logger.info("=" * 80)

                # Final decision
                if meets_requirements:
                    logger.info(f"✅ DECISION: {signal.get('action')} - All requirements met! Trade would execute.")
                else:
                    logger.info(f"🛑 DECISION: HOLD - Not trading (requirements not met)")

        except Exception as e:
            logger.error(f"❌ Error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(test_signal_diagnostics())
