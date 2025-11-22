#!/usr/bin/env python3
"""
Test Position Sizing Implementation
Purpose: Test Kelly Criterion, fractional Kelly, and confidence-adjusted sizing
"""

import asyncio
import logging
from decimal import Decimal
from app.position_sizing import get_position_sizer, reset_position_sizer, SizingMethod

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)


def test_position_sizing():
    """Test position sizing with various methods and scenarios"""
    logger.info("=" * 80)
    logger.info("POSITION SIZING TEST")
    logger.info("=" * 80)

    # Test parameters
    balance = Decimal("10000")  # $10,000 capital
    btc_price = Decimal("50000")  # $50,000 BTC price

    # Performance stats (from historical trading)
    performance_stats = {
        'win_rate': 0.625,  # 62.5% win rate
        'avg_win': 0.025,   # 2.5% average win
        'avg_loss': -0.015, # 1.5% average loss (negative)
    }

    # Get position sizer
    reset_position_sizer()  # Reset to defaults
    sizer = get_position_sizer()

    logger.info(f"\n💰 Test Conditions:")
    logger.info(f"Balance: ${balance:,.2f}")
    logger.info(f"BTC Price: ${btc_price:,.2f}")
    logger.info(f"Win Rate: {performance_stats['win_rate']:.2%}")
    logger.info(f"Avg Win: {performance_stats['avg_win']:.2%}")
    logger.info(f"Avg Loss: {performance_stats['avg_loss']:.2%}")

    # Test 1: Fixed sizing
    logger.info("\n" + "=" * 80)
    logger.info("TEST 1: Fixed Position Sizing (Baseline)")
    logger.info("=" * 80)

    result_fixed = sizer.calculate_position_size(
        method=SizingMethod.FIXED,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.7,
        performance_stats=None,
        stop_loss_pct=None
    )

    logger.info(f"📊 Method: {result_fixed.method.value}")
    logger.info(f"📏 Position Size: {result_fixed.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_fixed.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_fixed.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_fixed.reasoning}")

    # Test 2: Full Kelly
    logger.info("\n" + "=" * 80)
    logger.info("TEST 2: Full Kelly Criterion (Theoretical Optimal)")
    logger.info("=" * 80)

    result_kelly = sizer.calculate_position_size(
        method=SizingMethod.KELLY,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.7,
        performance_stats=performance_stats,
        stop_loss_pct=None
    )

    logger.info(f"📊 Method: {result_kelly.method.value}")
    logger.info(f"📏 Kelly Fraction: {result_kelly.kelly_fraction:.4f} ({result_kelly.kelly_fraction * 100:.2f}%)")
    logger.info(f"📏 Position Size: {result_kelly.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_kelly.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_kelly.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_kelly.reasoning}")

    # Test 3: Fractional Kelly (Quarter Kelly)
    logger.info("\n" + "=" * 80)
    logger.info("TEST 3: Fractional Kelly (25% of Full Kelly - Conservative)")
    logger.info("=" * 80)

    result_frac_kelly = sizer.calculate_position_size(
        method=SizingMethod.FRACTIONAL_KELLY,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.7,
        performance_stats=performance_stats,
        stop_loss_pct=None
    )

    logger.info(f"📊 Method: {result_frac_kelly.method.value}")
    logger.info(f"📏 Full Kelly: {result_frac_kelly.kelly_fraction:.4f} ({result_frac_kelly.kelly_fraction * 100:.2f}%)")
    logger.info(f"📏 Fractional (0.25x): {result_frac_kelly.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_frac_kelly.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_frac_kelly.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_frac_kelly.reasoning}")

    # Test 4: Confidence-Adjusted (High Confidence)
    logger.info("\n" + "=" * 80)
    logger.info("TEST 4: Confidence-Adjusted Sizing (High Confidence - 85%)")
    logger.info("=" * 80)

    result_conf_high = sizer.calculate_position_size(
        method=SizingMethod.CONFIDENCE_ADJUSTED,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.85,  # High confidence
        performance_stats=performance_stats,
        stop_loss_pct=None
    )

    logger.info(f"📊 Method: {result_conf_high.method.value}")
    logger.info(f"🎯 Signal Confidence: {0.85:.2%}")
    logger.info(f"📏 Base Kelly: {result_conf_high.kelly_fraction:.4f} ({result_conf_high.kelly_fraction * 100:.2f}%)")
    logger.info(f"🔧 Confidence Modifier: {result_conf_high.confidence_modifier:.2f}x")
    logger.info(f"📏 Final Position Size: {result_conf_high.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_conf_high.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_conf_high.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_conf_high.reasoning}")

    # Test 5: Confidence-Adjusted (Low Confidence)
    logger.info("\n" + "=" * 80)
    logger.info("TEST 5: Confidence-Adjusted Sizing (Low Confidence - 55%)")
    logger.info("=" * 80)

    result_conf_low = sizer.calculate_position_size(
        method=SizingMethod.CONFIDENCE_ADJUSTED,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.55,  # Low confidence
        performance_stats=performance_stats,
        stop_loss_pct=None
    )

    logger.info(f"📊 Method: {result_conf_low.method.value}")
    logger.info(f"🎯 Signal Confidence: {0.55:.2%}")
    logger.info(f"📏 Base Kelly: {result_conf_low.kelly_fraction:.4f} ({result_conf_low.kelly_fraction * 100:.2f}%)")
    logger.info(f"🔧 Confidence Modifier: {result_conf_low.confidence_modifier:.2f}x")
    logger.info(f"📏 Final Position Size: {result_conf_low.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_conf_low.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_conf_low.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_conf_low.reasoning}")

    # Test 6: With Risk Limit (Stop Loss)
    logger.info("\n" + "=" * 80)
    logger.info("TEST 6: Position Size with Risk Limit (2% max risk, 3% stop loss)")
    logger.info("=" * 80)

    stop_loss_pct = 0.03  # 3% stop loss

    result_risk_limit = sizer.calculate_position_size(
        method=SizingMethod.CONFIDENCE_ADJUSTED,
        current_balance=balance,
        current_price=btc_price,
        signal_confidence=0.75,
        performance_stats=performance_stats,
        stop_loss_pct=stop_loss_pct
    )

    logger.info(f"📊 Method: {result_risk_limit.method.value}")
    logger.info(f"🎯 Signal Confidence: {0.75:.2%}")
    logger.info(f"🛡️ Stop Loss Distance: {stop_loss_pct:.2%}")
    logger.info(f"📏 Position Size: {result_risk_limit.position_size_pct:.2f}%")
    logger.info(f"💵 Position Value: ${result_risk_limit.position_value:,.2f}")
    logger.info(f"₿ Quantity: {result_risk_limit.quantity:.4f} BTC")
    logger.info(f"💡 Reasoning: {result_risk_limit.reasoning}")

    # Calculate actual risk
    position_value_float = float(result_risk_limit.position_value)
    actual_risk = position_value_float * stop_loss_pct
    actual_risk_pct = (actual_risk / float(balance)) * 100

    logger.info(f"\n🔍 Risk Analysis:")
    logger.info(f"Position Value: ${position_value_float:,.2f}")
    logger.info(f"Stop Loss Distance: {stop_loss_pct:.2%}")
    logger.info(f"Actual $ Risk: ${actual_risk:,.2f}")
    logger.info(f"Actual % Risk: {actual_risk_pct:.2f}% of capital")

    # Comparison summary
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON SUMMARY")
    logger.info("=" * 80)

    logger.info(f"\n{'Method':<30} {'Size %':<10} {'Value':<12} {'Quantity (BTC)':<15}")
    logger.info("-" * 80)
    logger.info(
        f"{'Fixed (3%)':<30} "
        f"{result_fixed.position_size_pct:>7.2f}% "
        f"${result_fixed.position_value:>9,.2f} "
        f"{result_fixed.quantity:>14.4f}"
    )
    logger.info(
        f"{'Full Kelly':<30} "
        f"{result_kelly.position_size_pct:>7.2f}% "
        f"${result_kelly.position_value:>9,.2f} "
        f"{result_kelly.quantity:>14.4f}"
    )
    logger.info(
        f"{'Fractional Kelly (0.25x)':<30} "
        f"{result_frac_kelly.position_size_pct:>7.2f}% "
        f"${result_frac_kelly.position_value:>9,.2f} "
        f"{result_frac_kelly.quantity:>14.4f}"
    )
    logger.info(
        f"{'Conf-Adjusted (85% conf)':<30} "
        f"{result_conf_high.position_size_pct:>7.2f}% "
        f"${result_conf_high.position_value:>9,.2f} "
        f"{result_conf_high.quantity:>14.4f}"
    )
    logger.info(
        f"{'Conf-Adjusted (55% conf)':<30} "
        f"{result_conf_low.position_size_pct:>7.2f}% "
        f"${result_conf_low.position_value:>9,.2f} "
        f"{result_conf_low.quantity:>14.4f}"
    )
    logger.info(
        f"{'With Risk Limit (3% SL)':<30} "
        f"{result_risk_limit.position_size_pct:>7.2f}% "
        f"${result_risk_limit.position_value:>9,.2f} "
        f"{result_risk_limit.quantity:>14.4f}"
    )

    # Kelly Formula Explanation
    logger.info("\n" + "=" * 80)
    logger.info("KELLY CRITERION FORMULA")
    logger.info("=" * 80)

    win_rate = performance_stats['win_rate']
    avg_win = performance_stats['avg_win']
    avg_loss = abs(performance_stats['avg_loss'])
    win_loss_ratio = avg_win / avg_loss
    kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

    logger.info(f"\nKelly = W - [(1 - W) / R]")
    logger.info(f"Where:")
    logger.info(f"  W = Win Rate = {win_rate:.4f} ({win_rate * 100:.2f}%)")
    logger.info(f"  R = Win/Loss Ratio = {avg_win:.4f} / {avg_loss:.4f} = {win_loss_ratio:.4f}")
    logger.info(f"\nCalculation:")
    logger.info(f"Kelly = {win_rate:.4f} - [(1 - {win_rate:.4f}) / {win_loss_ratio:.4f}]")
    logger.info(f"Kelly = {win_rate:.4f} - [{1 - win_rate:.4f} / {win_loss_ratio:.4f}]")
    logger.info(f"Kelly = {win_rate:.4f} - {(1 - win_rate) / win_loss_ratio:.4f}")
    logger.info(f"Kelly = {kelly:.4f} ({kelly * 100:.2f}%)")

    logger.info(f"\n💡 Interpretation:")
    logger.info(f"Full Kelly suggests betting {kelly * 100:.2f}% of capital")
    logger.info(f"Quarter Kelly (conservative): {kelly * 25:.2f}%")
    logger.info(f"This is the theoretically optimal bet size to maximize log wealth")

    logger.info("\n" + "=" * 80)
    logger.info("✅ Position sizing test completed successfully")
    logger.info("=" * 80)

    return True


def main():
    """Main entry point"""
    success = test_position_sizing()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
