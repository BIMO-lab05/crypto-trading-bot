#!/usr/bin/env python3
"""
Complete System Integration Test
Purpose: Test Phase 2 (MTF) + Phase 3 (VP) + Dynamic Position Sizing working together

This demonstrates the full trading pipeline:
1. Multi-Timeframe Analysis (15m, 60m, 240m consensus)
2. Volume Profile Integration (POC, VAH, VAL strategies)
3. Dynamic Position Sizing (Kelly Criterion + confidence adjustment)
"""

import asyncio
import logging
from decimal import Decimal
from datetime import datetime
from app.signal_aggregator import get_aggregator
from app.position_sizing import get_position_sizer, SizingMethod
from app.performance_tracker import get_performance_tracker, reset_performance_tracker
from app.models import Position, PositionSide, PositionStatus
from uuid import uuid4

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


async def test_complete_integration():
    """Test complete system integration: MTF + VP + Position Sizing"""
    logger.info("=" * 100)
    logger.info("COMPLETE SYSTEM INTEGRATION TEST")
    logger.info("Phase 2 (Multi-Timeframe) + Phase 3 (Volume Profile) + Dynamic Position Sizing")
    logger.info("=" * 100)

    symbol = "BTCUSDT"
    balance = Decimal("10000")  # $10,000 starting capital

    try:
        # Setup: Create mock performance tracker with some historical trades
        logger.info("\n📊 SETUP: Creating Performance History")
        logger.info("-" * 100)

        reset_performance_tracker()
        perf_tracker = get_performance_tracker(initial_balance=balance)

        # Add mock historical trades for Kelly calculation
        mock_trades = [
            # (side, entry_price, exit_price, quantity, hours_held)
            (PositionSide.LONG, 48000, 49200, 0.02, 4),   # +2.5% win
            (PositionSide.LONG, 49500, 50500, 0.02, 3),   # +2.0% win
            (PositionSide.LONG, 50000, 49000, 0.02, 2),   # -2.0% loss
            (PositionSide.LONG, 48500, 49500, 0.02, 5),   # +2.1% win
            (PositionSide.LONG, 51000, 50000, 0.02, 1),   # -2.0% loss
            (PositionSide.LONG, 49000, 50000, 0.02, 6),   # +2.0% win
            (PositionSide.LONG, 50500, 51500, 0.02, 4),   # +2.0% win
            (PositionSide.LONG, 52000, 51500, 0.02, 2),   # -1.0% loss
        ]

        for i, (side, entry, exit, qty, hours) in enumerate(mock_trades):
            entry_time = datetime.now()
            exit_time = datetime.now()

            position = Position(
                id=uuid4(),
                symbol=symbol,
                side=side,
                entry_price=Decimal(str(entry)),
                quantity=Decimal(str(qty)),
                status=PositionStatus.CLOSED,
                opened_at=entry_time,
                closed_at=exit_time,
                strategy="test_integration"
            )

            trade = perf_tracker.add_trade(position, Decimal(str(exit)), exit_time)

        metrics = perf_tracker.calculate_metrics()
        logger.info(f"✅ Created {metrics.total_trades} historical trades")
        logger.info(f"   Win Rate: {metrics.win_rate:.2%}")
        logger.info(f"   Profit Factor: {metrics.profit_factor:.2f}")
        logger.info(f"   Total P&L: ${metrics.total_pnl:.2f}")

        # TEST 1: Multi-Timeframe Signal Only (Phase 2 baseline)
        logger.info("\n" + "=" * 100)
        logger.info("TEST 1: Multi-Timeframe Analysis (Phase 2 - Baseline)")
        logger.info("=" * 100)

        aggregator = await get_aggregator()

        signal_mtf = await aggregator.get_trading_signal_multi_timeframe(
            symbol=symbol,
            primary_interval="60",
            timeframes=["15", "60", "240"]
        )

        logger.info(f"\n📊 MTF Signal Results:")
        logger.info(f"Action: {signal_mtf.action.value}")
        logger.info(f"Confidence: {signal_mtf.confidence:.2%}")
        logger.info(f"Score: {signal_mtf.aggregated_score:+.2f}")

        mtf_data = signal_mtf.metadata.get("multi_timeframe", {})
        if mtf_data:
            logger.info(f"\n🎯 Multi-Timeframe Details:")
            logger.info(f"Consensus Action: {mtf_data.get('consensus_action')}")
            logger.info(f"Alignment Strength: {mtf_data.get('alignment_strength')}")
            logger.info(f"Confidence Modifier: {mtf_data.get('confidence_modifier'):.2f}x")

            timeframe_signals = mtf_data.get('timeframe_signals', {})
            logger.info(f"\nTimeframe Breakdown:")
            for tf, tf_signal in timeframe_signals.items():
                logger.info(f"  {tf:>4}: {tf_signal.get('action'):<5} (conf: {tf_signal.get('confidence'):.2%})")

        # TEST 2: MTF + Volume Profile (Phase 2 + Phase 3)
        logger.info("\n" + "=" * 100)
        logger.info("TEST 2: MTF + Volume Profile Integration (Phase 2 + Phase 3)")
        logger.info("=" * 100)

        signal_vp = await aggregator.get_trading_signal_with_vp(
            symbol=symbol,
            primary_interval="60",
            timeframes=["15", "60", "240"],
            enable_vp=True,
            vp_lookback=100
        )

        logger.info(f"\n📊 VP-Enhanced Signal Results:")
        logger.info(f"Action: {signal_vp.action.value}")
        logger.info(f"Confidence: {signal_vp.confidence:.2%}")
        logger.info(f"Score: {signal_vp.aggregated_score:+.2f}")

        # Show confidence change
        conf_change = ((signal_vp.confidence - signal_mtf.confidence) / signal_mtf.confidence) * 100
        if conf_change > 0:
            logger.info(f"Confidence Change: +{conf_change:.1f}% (VP BOOST)")
        elif conf_change < 0:
            logger.info(f"Confidence Change: {conf_change:.1f}% (VP PENALTY)")
        else:
            logger.info(f"Confidence Change: No change")

        vp_data = signal_vp.metadata.get("volume_profile", {})
        if vp_data:
            logger.info(f"\n📈 Volume Profile Details:")
            logger.info(f"Strategy: {vp_data.get('strategy')}")
            logger.info(f"Position: {vp_data.get('position')}")
            logger.info(f"Volume Bias: {vp_data.get('volume_bias')}")

            logger.info(f"\n📊 VP Levels:")
            logger.info(f"POC (Point of Control): ${vp_data.get('poc', 0):,.2f}")
            logger.info(f"VAH (Value Area High):  ${vp_data.get('vah', 0):,.2f}")
            logger.info(f"VAL (Value Area Low):   ${vp_data.get('val', 0):,.2f}")

            logger.info(f"\n🛡️ Trade Levels:")
            logger.info(f"Stop Loss: ${vp_data.get('stop_loss', 0):,.2f}")

            tp_levels = vp_data.get('take_profit', {})
            if tp_levels:
                logger.info(f"Take Profit 1: ${tp_levels.get('tp1', 0):,.2f}")
                logger.info(f"Take Profit 2: ${tp_levels.get('tp2', 0):,.2f}")
                logger.info(f"Take Profit 3: ${tp_levels.get('tp3', 0):,.2f}")

            logger.info(f"\n💡 VP Reasoning:")
            logger.info(f"   {vp_data.get('reasoning', 'N/A')}")

        # TEST 3: Position Sizing Integration
        logger.info("\n" + "=" * 100)
        logger.info("TEST 3: Dynamic Position Sizing (Complete Integration)")
        logger.info("=" * 100)

        # Get current price from signal
        current_price = None
        for indicator_name, indicator_signal in signal_vp.indicators.items():
            if hasattr(indicator_signal, 'metadata') and indicator_signal.metadata:
                if "current_price" in indicator_signal.metadata:
                    current_price = Decimal(str(indicator_signal.metadata["current_price"]))
                    break

        if not current_price:
            logger.warning("⚠️ No current price found, using mock price")
            current_price = Decimal("50000")

        # Calculate position size with all methods for comparison
        position_sizer = get_position_sizer()

        # Get performance stats
        performance_stats = position_sizer.get_performance_stats_from_tracker(perf_tracker)

        # Get stop loss from VP
        stop_loss_pct = None
        if vp_data and vp_data.get("stop_loss"):
            stop_loss_price = Decimal(str(vp_data.get("stop_loss", 0)))
            stop_loss_pct = abs(float((current_price - stop_loss_price) / current_price))

        logger.info(f"\n💰 Position Sizing Inputs:")
        logger.info(f"Current Balance: ${balance:,.2f}")
        logger.info(f"Current Price: ${current_price:,.2f}")
        logger.info(f"Signal Confidence: {signal_vp.confidence:.2%}")
        logger.info(f"Win Rate: {performance_stats.get('win_rate', 0):.2%}")
        logger.info(f"Avg Win: {performance_stats.get('avg_win', 0):.2%}")
        logger.info(f"Avg Loss: {performance_stats.get('avg_loss', 0):.2%}")
        if stop_loss_pct:
            logger.info(f"VP Stop Loss: {stop_loss_pct:.2%} from entry")

        # Method 1: Fixed (baseline)
        result_fixed = position_sizer.calculate_position_size(
            method=SizingMethod.FIXED,
            current_balance=balance,
            current_price=current_price,
            signal_confidence=signal_vp.confidence,
            performance_stats=None,
            stop_loss_pct=stop_loss_pct
        )

        # Method 2: Fractional Kelly
        result_kelly = position_sizer.calculate_position_size(
            method=SizingMethod.FRACTIONAL_KELLY,
            current_balance=balance,
            current_price=current_price,
            signal_confidence=signal_vp.confidence,
            performance_stats=performance_stats,
            stop_loss_pct=stop_loss_pct
        )

        # Method 3: Confidence-Adjusted (RECOMMENDED)
        result_conf = position_sizer.calculate_position_size(
            method=SizingMethod.CONFIDENCE_ADJUSTED,
            current_balance=balance,
            current_price=current_price,
            signal_confidence=signal_vp.confidence,
            performance_stats=performance_stats,
            stop_loss_pct=stop_loss_pct
        )

        # Display results
        logger.info("\n" + "=" * 100)
        logger.info("POSITION SIZING COMPARISON")
        logger.info("=" * 100)

        logger.info(f"\n1️⃣  FIXED SIZING (Baseline)")
        logger.info(f"    Position Size: {result_fixed.position_size_pct:.2f}%")
        logger.info(f"    Position Value: ${result_fixed.position_value:,.2f}")
        logger.info(f"    Quantity: {result_fixed.quantity:.4f} BTC")
        logger.info(f"    Reasoning: {result_fixed.reasoning}")

        logger.info(f"\n2️⃣  FRACTIONAL KELLY (Performance-Based)")
        logger.info(f"    Kelly Fraction: {result_kelly.kelly_fraction:.4f} ({result_kelly.kelly_fraction * 100:.2f}%)")
        logger.info(f"    Position Size: {result_kelly.position_size_pct:.2f}%")
        logger.info(f"    Position Value: ${result_kelly.position_value:,.2f}")
        logger.info(f"    Quantity: {result_kelly.quantity:.4f} BTC")
        logger.info(f"    Reasoning: {result_kelly.reasoning}")

        logger.info(f"\n3️⃣  CONFIDENCE-ADJUSTED (RECOMMENDED)")
        logger.info(f"    Kelly Fraction: {result_conf.kelly_fraction:.4f} ({result_conf.kelly_fraction * 100:.2f}%)")
        logger.info(f"    Confidence Modifier: {result_conf.confidence_modifier:.2f}x")
        logger.info(f"    Position Size: {result_conf.position_size_pct:.2f}%")
        logger.info(f"    Position Value: ${result_conf.position_value:,.2f}")
        logger.info(f"    Quantity: {result_conf.quantity:.4f} BTC")
        logger.info(f"    Reasoning: {result_conf.reasoning}")

        # Comparison table
        logger.info("\n" + "-" * 100)
        logger.info(f"{'Method':<30} {'Size %':>10} {'Value':>15} {'Quantity (BTC)':>20} {'vs Fixed':>15}")
        logger.info("-" * 100)

        for method_name, result in [
            ("Fixed (Baseline)", result_fixed),
            ("Fractional Kelly", result_kelly),
            ("Confidence-Adjusted", result_conf)
        ]:
            vs_fixed = ((result.position_size_pct - result_fixed.position_size_pct) / result_fixed.position_size_pct) * 100
            logger.info(
                f"{method_name:<30} "
                f"{result.position_size_pct:>9.2f}% "
                f"${result.position_value:>13,.2f} "
                f"{result.quantity:>19.4f} "
                f"{vs_fixed:>+14.1f}%"
            )

        # TEST 4: Complete Trade Simulation
        logger.info("\n" + "=" * 100)
        logger.info("TEST 4: Complete Trade Simulation")
        logger.info("=" * 100)

        logger.info(f"\n🎬 Trade Execution Simulation:")
        logger.info(f"Signal: {signal_vp.action.value}")
        logger.info(f"Strategy: {vp_data.get('strategy', 'N/A')}")
        logger.info(f"Entry Price: ${current_price:,.2f}")
        logger.info(f"Position Size: {result_conf.position_size_pct:.2f}% (${result_conf.position_value:,.2f})")
        logger.info(f"Quantity: {result_conf.quantity:.4f} BTC")

        if vp_data:
            stop_loss = vp_data.get('stop_loss', 0)
            tp1 = tp_levels.get('tp1', 0) if tp_levels else 0

            logger.info(f"\n🎯 Risk Management:")
            logger.info(f"Stop Loss: ${stop_loss:,.2f} ({stop_loss_pct:.2%} from entry)")
            logger.info(f"Take Profit 1: ${tp1:,.2f}")

            # Calculate risk/reward
            risk_amount = abs(float(current_price) - stop_loss) * float(result_conf.quantity)
            reward_amount = abs(tp1 - float(current_price)) * float(result_conf.quantity)

            if risk_amount > 0:
                rr_ratio = reward_amount / risk_amount
                logger.info(f"\n⚖️  Risk:Reward Analysis:")
                logger.info(f"Risk: ${risk_amount:.2f}")
                logger.info(f"Reward (TP1): ${reward_amount:.2f}")
                logger.info(f"R:R Ratio: 1:{rr_ratio:.2f}")

                # Calculate actual risk as % of capital
                risk_pct = (risk_amount / float(balance)) * 100
                logger.info(f"Actual Risk: {risk_pct:.2f}% of capital")

        # Summary
        logger.info("\n" + "=" * 100)
        logger.info("INTEGRATION TEST SUMMARY")
        logger.info("=" * 100)

        logger.info(f"\n✅ Phase 2 (Multi-Timeframe):")
        logger.info(f"   Consensus: {mtf_data.get('consensus_action')}")
        logger.info(f"   Alignment: {mtf_data.get('alignment_strength')}")
        logger.info(f"   Confidence: {signal_mtf.confidence:.2%}")

        logger.info(f"\n✅ Phase 3 (Volume Profile):")
        logger.info(f"   Strategy: {vp_data.get('strategy', 'N/A')}")
        logger.info(f"   Position: {vp_data.get('position', 'N/A')}")
        logger.info(f"   Confidence: {signal_vp.confidence:.2%} ({conf_change:+.1f}% vs MTF)")

        logger.info(f"\n✅ Dynamic Position Sizing:")
        logger.info(f"   Method: {result_conf.method.value}")
        logger.info(f"   Kelly: {result_conf.kelly_fraction:.4f} ({result_conf.kelly_fraction * 100:.2f}%)")
        logger.info(f"   Size: {result_conf.position_size_pct:.2f}% (vs {result_fixed.position_size_pct:.2f}% fixed)")
        logger.info(f"   Improvement: {((result_conf.position_size_pct / result_fixed.position_size_pct - 1) * 100):+.1f}%")

        logger.info(f"\n🎯 Expected Benefits:")
        logger.info(f"   • Higher capital efficiency: {result_conf.position_size_pct / result_fixed.position_size_pct:.2f}x vs fixed")
        logger.info(f"   • Better risk management: VP-optimized stop loss")
        logger.info(f"   • Optimal growth rate: Kelly Criterion maximizes long-term returns")
        logger.info(f"   • Adaptive sizing: Scales with signal confidence and performance")

        logger.info("\n" + "=" * 100)
        logger.info("✅ Complete system integration test PASSED")
        logger.info("All components (MTF + VP + Position Sizing) working together successfully!")
        logger.info("=" * 100)

        return True

    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}", exc_info=True)
        return False


async def main():
    """Main entry point"""
    success = await test_complete_integration()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
