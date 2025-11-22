#!/usr/bin/env python3
"""
Test Volume Profile Integration
Purpose: Test VP calculator, strategy analyzer, and integration with MTF signals
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime, timedelta
from app.signal_aggregator import get_aggregator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


async def test_vp_integration():
    """Test Volume Profile integration with multi-timeframe signals"""
    logger.info("=" * 80)
    logger.info("VOLUME PROFILE INTEGRATION TEST")
    logger.info("=" * 80)

    symbol = "BTCUSDT"

    try:
        # Get aggregator
        aggregator = await get_aggregator()

        # Test 1: Multi-timeframe signal without VP (Phase 2)
        logger.info("\n📊 Test 1: Multi-Timeframe Signal (NO VP)")
        logger.info("-" * 80)

        signal_mtf = await aggregator.get_trading_signal_multi_timeframe(
            symbol=symbol,
            primary_interval="60",
            timeframes=["15", "60", "240"]
        )

        logger.info(f"Symbol: {symbol}")
        logger.info(f"Action: {signal_mtf.action.value}")
        logger.info(f"Confidence: {signal_mtf.confidence:.2%}")
        logger.info(f"Score: {signal_mtf.aggregated_score:+.2f}")

        mtf_data = signal_mtf.metadata.get("multi_timeframe", {})
        if mtf_data:
            logger.info(f"MTF Alignment: {mtf_data.get('alignment_strength')}")
            logger.info(f"MTF Modifier: {mtf_data.get('confidence_modifier'):.2f}x")

        # Test 2: Volume Profile enhanced signal (Phase 3)
        logger.info("\n📊 Test 2: VP-Enhanced Signal")
        logger.info("-" * 80)

        signal_vp = await aggregator.get_trading_signal_with_vp(
            symbol=symbol,
            primary_interval="60",
            timeframes=["15", "60", "240"],
            enable_vp=True,
            vp_lookback=100
        )

        logger.info(f"\n📋 Results:")
        logger.info(f"Action: {signal_vp.action.value}")
        logger.info(f"Confidence: {signal_vp.confidence:.2%}")
        logger.info(f"Score: {signal_vp.aggregated_score:+.2f}")

        # Display multi-timeframe metadata
        mtf_data = signal_vp.metadata.get("multi_timeframe", {})
        if mtf_data:
            logger.info(f"\n🎯 Multi-Timeframe Details:")
            logger.info(f"Consensus Action: {mtf_data.get('consensus_action')}")
            logger.info(f"Alignment Strength: {mtf_data.get('alignment_strength')}")
            logger.info(f"Confidence Modifier: {mtf_data.get('confidence_modifier'):.2f}x")

        # Display volume profile metadata
        vp_data = signal_vp.metadata.get("volume_profile", {})
        if vp_data:
            logger.info(f"\n📊 Volume Profile Details:")
            logger.info(f"Strategy: {vp_data.get('strategy')}")
            logger.info(f"Position: {vp_data.get('position')}")
            logger.info(f"Volume Bias: {vp_data.get('volume_bias')}")

            logger.info(f"\n📈 VP Levels:")
            logger.info(f"POC (Point of Control): ${vp_data.get('poc', 0):.2f}")
            logger.info(f"VAH (Value Area High): ${vp_data.get('vah', 0):.2f}")
            logger.info(f"VAL (Value Area Low): ${vp_data.get('val', 0):.2f}")

            logger.info(f"\n💰 Trade Levels:")
            logger.info(f"Stop Loss: ${vp_data.get('stop_loss', 0):.2f}")

            tp_levels = vp_data.get('take_profit', {})
            if tp_levels:
                logger.info(f"Take Profit 1: ${tp_levels.get('tp1', 0):.2f}")
                logger.info(f"Take Profit 2: ${tp_levels.get('tp2', 0):.2f}")
                logger.info(f"Take Profit 3: ${tp_levels.get('tp3', 0):.2f}")

            logger.info(f"\n💡 Reasoning:")
            logger.info(f"   {vp_data.get('reasoning', 'N/A')}")

        # Test 3: Compare confidence changes
        logger.info(f"\n📊 Confidence Comparison:")
        logger.info(f"MTF Only: {signal_mtf.confidence:.2%}")
        logger.info(f"MTF + VP: {signal_vp.confidence:.2%}")

        confidence_change = ((signal_vp.confidence - signal_mtf.confidence) / signal_mtf.confidence) * 100
        if confidence_change > 0:
            logger.info(f"Change: +{confidence_change:.1f}% (BOOST)")
        elif confidence_change < 0:
            logger.info(f"Change: {confidence_change:.1f}% (PENALTY)")
        else:
            logger.info(f"Change: No change")

        # Test 4: Calculate Risk:Reward
        if vp_data:
            try:
                current_price = Decimal(str(vp_data.get('poc', 0)))  # Use POC as proxy
                stop_loss = Decimal(str(vp_data.get('stop_loss', 0)))
                tp1 = Decimal(str(tp_levels.get('tp1', 0)))

                risk = abs(current_price - stop_loss)
                reward = abs(tp1 - current_price)
                rr_ratio = float(reward / risk) if risk > 0 else 0

                logger.info(f"\n⚖️ Risk:Reward Analysis:")
                logger.info(f"Risk: ${risk:.2f} ({float(risk/current_price*100):.2f}%)")
                logger.info(f"Reward (TP1): ${reward:.2f} ({float(reward/current_price*100):.2f}%)")
                logger.info(f"R:R Ratio: 1:{rr_ratio:.2f}")

            except Exception as e:
                logger.warning(f"⚠️ Could not calculate R:R: {e}")

        logger.info("\n" + "=" * 80)
        logger.info("✅ Volume Profile integration test completed successfully")
        logger.info("=" * 80)

        return True

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False


async def main():
    """Main entry point"""
    success = await test_vp_integration()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
