#!/usr/bin/env python3
"""
Test Multi-Timeframe Analysis
Purpose: Quick test of multi-timeframe signal confirmation
"""

import asyncio
import sys
import logging
from app.signal_aggregator import get_aggregator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


async def test_multi_timeframe():
    """Test multi-timeframe signal analysis"""
    logger.info("=" * 80)
    logger.info("MULTI-TIMEFRAME ANALYSIS TEST")
    logger.info("=" * 80)

    symbol = "BTCUSDT"

    try:
        # Get aggregator
        aggregator = await get_aggregator()

        # Test 1: Fetch single-timeframe signal (baseline)
        logger.info("\n📊 Test 1: Single Timeframe (60m baseline)")
        logger.info("-" * 80)

        signal_60m = await aggregator.get_trading_signal(symbol, "60")

        logger.info(f"Symbol: {symbol}")
        logger.info(f"Interval: 60m")
        logger.info(f"Action: {signal_60m.action.value}")
        logger.info(f"Confidence: {signal_60m.confidence:.2%}")
        logger.info(f"Score: {signal_60m.aggregated_score:+.2f}")
        logger.info(f"Meets Requirements: {signal_60m.metadata.get('meets_requirements', False)}")

        # Test 2: Multi-timeframe analysis
        logger.info("\n🔍 Test 2: Multi-Timeframe Analysis (15m, 60m, 240m)")
        logger.info("-" * 80)

        signal_mtf = await aggregator.get_trading_signal_multi_timeframe(
            symbol=symbol,
            primary_interval="60",
            timeframes=["15", "60", "240"]
        )

        logger.info(f"\n📋 Results:")
        logger.info(f"Primary Action (60m): {signal_mtf.action.value}")
        logger.info(f"Adjusted Confidence: {signal_mtf.confidence:.2%}")
        logger.info(f"Score: {signal_mtf.aggregated_score:+.2f}")

        # Display multi-timeframe metadata
        mtf_data = signal_mtf.metadata.get("multi_timeframe", {})
        if mtf_data:
            logger.info(f"\n🎯 Multi-Timeframe Details:")
            logger.info(f"Consensus Action: {mtf_data.get('consensus_action')}")
            logger.info(f"Alignment Strength: {mtf_data.get('alignment_strength')}")
            logger.info(f"Confidence Modifier: {mtf_data.get('confidence_modifier'):.2f}x")
            logger.info(f"Agreement: {mtf_data.get('agreement_pct'):.1f}%")
            logger.info(f"Reasoning: {mtf_data.get('reasoning')}")

            logger.info(f"\n📈 Timeframe Breakdown:")
            for interval, tf_signal in mtf_data.get('timeframe_signals', {}).items():
                logger.info(
                    f"  {interval}m: {tf_signal['action']} "
                    f"(conf: {tf_signal['confidence']:.2f}, "
                    f"score: {tf_signal['score']:+.2f})"
                )

        # Test 3: Compare confidence changes
        logger.info(f"\n📊 Confidence Comparison:")
        logger.info(f"Single Timeframe (60m): {signal_60m.confidence:.2%}")
        logger.info(f"Multi-Timeframe (adjusted): {signal_mtf.confidence:.2%}")

        confidence_change = ((signal_mtf.confidence - signal_60m.confidence) / signal_60m.confidence) * 100
        if confidence_change > 0:
            logger.info(f"Change: +{confidence_change:.1f}% (BOOST)")
        elif confidence_change < 0:
            logger.info(f"Change: {confidence_change:.1f}% (PENALTY)")
        else:
            logger.info(f"Change: No change")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Multi-timeframe analysis test completed successfully")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False


async def main():
    """Main entry point"""
    success = await test_multi_timeframe()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
