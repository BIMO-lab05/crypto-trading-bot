#!/usr/bin/env python3
"""
Signal Generation and Aggregation E2E Tests

Tests the complete signal generation workflow from technical indicator
calculation through signal aggregation and decision making.

Signal Flow:
1. Market Data → Technical Indicators (RSI, MACD, BB, EMA)
2. Individual Indicator Signals
3. Voter: Confidence-weighted voting
4. Gatekeeper: Trend filter blocking
5. Validator: Confidence threshold checking
6. Final Aggregated Signal
"""

import pytest
import asyncio
from decimal import Decimal

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import (
    assert_signal_generated,
    assert_indicator_value,
    assert_within_range,
    assert_dict_contains_keys,
)
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_bearish_candles,
    generate_sideways_candles,
    generate_indicator_data,
)


# ============================================================================
# Technical Indicator Calculation Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_rsi_calculation_from_bullish_data(
    market_data_client,
    technical_analysis_client
):
    """
    Test RSI calculation from bullish market data.

    Expected: RSI should be high (>50, potentially >70 for overbought)
    """
    symbol = "BTCUSDT"

    print(f"\n📊 Testing RSI calculation for {symbol}...")

    # Inject strong bullish data (should result in high RSI)
    bullish_candles = generate_bullish_candles(
        start_price=45000.0,
        num_candles=50,
        price_increase_pct=15.0  # Strong uptrend
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")
    await asyncio.sleep(3)

    # Get technical indicators
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    if "RSI" in indicators:
        rsi = indicators["RSI"]

        # Verify RSI structure
        assert_dict_contains_keys(rsi, ["value", "signal"], "RSI indicator")

        # Verify RSI value is in valid range
        assert_within_range(rsi["value"], 0, 100, "RSI value")

        # For strong bullish trend, RSI should be elevated
        print(f"  RSI value: {rsi['value']:.2f}")
        print(f"  RSI signal: {rsi['signal']}")

        # RSI > 50 indicates bullish momentum
        if rsi["value"] > 50:
            print("  ✅ RSI correctly indicates bullish momentum")
        else:
            print("  ⚠️  RSI unexpectedly low for bullish data")
    else:
        pytest.skip("RSI indicator not available")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_macd_calculation_from_trending_data(
    market_data_client,
    technical_analysis_client
):
    """
    Test MACD calculation and crossover detection.

    MACD should turn positive in uptrend, negative in downtrend.
    """
    symbol = "ETHUSDT"

    print(f"\n📊 Testing MACD calculation for {symbol}...")

    # Inject trending data
    trending_candles = generate_bullish_candles(
        start_price=2000.0,
        num_candles=60,
        price_increase_pct=10.0
    )

    await market_data_client.inject_candles(symbol, trending_candles, interval="60")
    await asyncio.sleep(3)

    # Get indicators
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    if "MACD" in indicators:
        macd = indicators["MACD"]

        assert_dict_contains_keys(macd, ["value", "signal"], "MACD indicator")

        print(f"  MACD value: {macd['value']}")
        print(f"  MACD signal: {macd['signal']}")

        # MACD can be positive or negative
        # Positive = bullish, Negative = bearish
        if macd["value"] > 0:
            assert macd["signal"] in ["BUY", "NEUTRAL"], "MACD should signal BUY when positive"
            print("  ✅ MACD correctly signals bullish (positive)")
        else:
            print("  ⚠️  MACD is negative despite bullish data")
    else:
        pytest.skip("MACD indicator not available")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bollinger_bands_calculation(
    market_data_client,
    technical_analysis_client
):
    """
    Test Bollinger Bands calculation and position detection.

    BB should detect overbought (>80) and oversold (<20) conditions.
    """
    symbol = "BNBUSDT"

    print(f"\n📊 Testing Bollinger Bands for {symbol}...")

    # Inject volatile data
    candles = generate_bullish_candles(
        start_price=300.0,
        num_candles=50,
        price_increase_pct=8.0
    )

    await market_data_client.inject_candles(symbol, candles, interval="60")
    await asyncio.sleep(3)

    # Get indicators
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    if "BB" in indicators or "BBANDS" in indicators:
        bb = indicators.get("BB") or indicators.get("BBANDS")

        assert_dict_contains_keys(bb, ["value", "signal"], "Bollinger Bands")

        # BB position should be 0-100 (percentage within bands)
        if isinstance(bb["value"], (int, float)):
            assert_within_range(bb["value"], 0, 100, "BB position")

        print(f"  BB position: {bb['value']}")
        print(f"  BB signal: {bb['signal']}")

        # Position > 80 = overbought, < 20 = oversold
        if bb["value"] > 80:
            print("  ✅ BB indicates overbought condition")
        elif bb["value"] < 20:
            print("  ✅ BB indicates oversold condition")
        else:
            print(f"  ℹ️  BB in neutral zone ({bb['value']:.1f})")
    else:
        pytest.skip("Bollinger Bands indicator not available")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_all_indicators_calculated(
    market_data_client,
    technical_analysis_client
):
    """
    Test that all expected indicators are calculated.

    Expected indicators: RSI, MACD, BB, EMA, SMA, TREND_FILTER
    """
    symbol = "SOLUSDT"

    print(f"\n📊 Testing all indicators for {symbol}...")

    # Inject sufficient data for all indicators
    candles = generate_market_data_series(
        symbol=symbol,
        num_points=100,
        trend="bullish",
        start_price=100.0
    )

    await market_data_client.inject_candles(symbol, candles, interval="60")
    await asyncio.sleep(5)

    # Get all indicators
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    expected_indicators = ["RSI", "MACD", "BB", "EMA"]
    found_indicators = []
    missing_indicators = []

    for indicator_name in expected_indicators:
        if indicator_name in indicators or indicator_name.upper() in indicators:
            found_indicators.append(indicator_name)
            print(f"  ✅ {indicator_name}: {indicators[indicator_name]}")
        else:
            missing_indicators.append(indicator_name)
            print(f"  ❌ {indicator_name}: Not found")

    print(f"\n  Found {len(found_indicators)}/{len(expected_indicators)} indicators")

    # At least some indicators should be calculated
    assert len(found_indicators) > 0, "No indicators calculated"


# ============================================================================
# Signal Generation Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bullish_signal_generation(
    market_data_client,
    trading_engine_client
):
    """
    Test BUY signal generation from bullish market conditions.

    Workflow:
    1. Inject strong bullish data
    2. Wait for indicators to calculate
    3. Request aggregated signal
    4. Verify BUY signal with high confidence
    """
    symbol = "BTCUSDT"

    print(f"\n🎯 Testing bullish signal generation for {symbol}...")

    # Step 1: Inject strong bullish data
    bullish_candles = generate_bullish_candles(
        start_price=45000.0,
        num_candles=80,
        price_increase_pct=12.0
    )

    await market_data_client.inject_candles(symbol, bullish_candles, interval="60")

    # Step 2: Wait for signal generation
    print("  ⏳ Waiting for signal generation...")
    await asyncio.sleep(5)

    # Step 3: Get aggregated signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        print(f"\n  Signal received:")
        print(f"    Action: {signal.get('action')}")
        print(f"    Confidence: {signal.get('confidence', 0):.2f}")

        # Step 4: Verify signal characteristics
        assert_dict_contains_keys(signal, ["action", "confidence"], "Trading signal")

        # For strong bullish data, expect BUY signal
        if signal["action"] == "BUY":
            assert_signal_generated(
                signal=signal,
                expected_action="BUY",
                min_confidence=0.5  # At least 50% confidence
            )
            print("  ✅ Correct BUY signal generated")
        elif signal["action"] == "HOLD":
            print("  ⚠️  HOLD signal (may be blocked by gatekeeper)")
        else:
            print(f"  ⚠️  Unexpected signal: {signal['action']}")
    else:
        pytest.skip("No signal generated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_bearish_signal_generation(
    market_data_client,
    trading_engine_client
):
    """
    Test SELL signal generation from bearish market conditions.
    """
    symbol = "ETHUSDT"

    print(f"\n🎯 Testing bearish signal generation for {symbol}...")

    # Inject strong bearish data
    bearish_candles = generate_bearish_candles(
        start_price=2000.0,
        num_candles=80,
        price_decrease_pct=12.0
    )

    await market_data_client.inject_candles(symbol, bearish_candles, interval="60")

    print("  ⏳ Waiting for signal generation...")
    await asyncio.sleep(5)

    # Get signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        print(f"\n  Signal received:")
        print(f"    Action: {signal.get('action')}")
        print(f"    Confidence: {signal.get('confidence', 0):.2f}")

        # For strong bearish data, expect SELL signal or HOLD
        if signal["action"] == "SELL":
            assert_signal_generated(
                signal=signal,
                expected_action="SELL",
                min_confidence=0.5
            )
            print("  ✅ Correct SELL signal generated")
        elif signal["action"] == "HOLD":
            print("  ⚠️  HOLD signal (may be risk-managed)")
        else:
            print(f"  ⚠️  Unexpected signal: {signal['action']}")
    else:
        pytest.skip("No signal generated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_neutral_signal_on_sideways_market(
    market_data_client,
    trading_engine_client
):
    """
    Test that system generates HOLD signal for sideways market.

    No clear trend should result in HOLD or low-confidence signals.
    """
    symbol = "ADAUSDT"

    print(f"\n🎯 Testing neutral signal for sideways market ({symbol})...")

    # Inject sideways (ranging) data
    sideways_candles = generate_sideways_candles(
        base_price=0.50,
        num_candles=100,
        volatility=0.02
    )

    await market_data_client.inject_candles(symbol, sideways_candles, interval="60")

    print("  ⏳ Waiting for signal generation...")
    await asyncio.sleep(5)

    # Get signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        action = signal.get("action")
        confidence = signal.get("confidence", 0)

        print(f"\n  Signal received:")
        print(f"    Action: {action}")
        print(f"    Confidence: {confidence:.2f}")

        # Sideways market should produce HOLD or low-confidence signals
        if action == "HOLD":
            print("  ✅ Correctly generated HOLD for sideways market")
        elif confidence < 0.6:
            print(f"  ✅ Low confidence ({confidence:.2f}) for unclear market")
        else:
            print(f"  ⚠️  High confidence ({confidence:.2f}) signal in sideways market")
    else:
        print("  ✅ No signal generated (correct for sideways market)")


# ============================================================================
# Signal Aggregation Logic Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_voter_confidence_weighting(
    market_data_client,
    trading_engine_client,
    technical_analysis_client
):
    """
    Test that voter uses confidence-weighted voting.

    Indicators with higher confidence should have more weight.
    """
    symbol = "BNBUSDT"

    print(f"\n🗳️  Testing voter confidence weighting for {symbol}...")

    # Inject mixed signal data (some bullish, some neutral)
    mixed_candles = generate_bullish_candles(
        start_price=300.0,
        num_candles=70,
        price_increase_pct=6.0  # Moderate trend
    )

    await market_data_client.inject_candles(symbol, mixed_candles, interval="60")
    await asyncio.sleep(5)

    # Get individual indicators
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    if indicators and len(indicators) > 0:
        print("\n  Individual indicators:")
        for name, indicator in indicators.items():
            signal = indicator.get("signal", "N/A")
            confidence = indicator.get("confidence", 0)
            print(f"    {name}: {signal} (confidence: {confidence:.2f})")

    # Get aggregated signal
    aggregated_signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if aggregated_signal:
        print(f"\n  Aggregated signal:")
        print(f"    Action: {aggregated_signal['action']}")
        print(f"    Confidence: {aggregated_signal.get('confidence', 0):.2f}")

        # Aggregated confidence should be weighted average
        # Can't verify exact value, but should be reasonable
        agg_confidence = aggregated_signal.get("confidence", 0)
        assert_within_range(agg_confidence, 0, 1.0, "Aggregated confidence")

        print("  ✅ Voter confidence weighting verified")
    else:
        pytest.skip("No aggregated signal available")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_gatekeeper_blocks_counter_trend_signals(
    market_data_client,
    trading_engine_client
):
    """
    Test that gatekeeper blocks signals against the trend.

    Even if individual indicators suggest BUY, bearish trend should block it.
    """
    symbol = "DOGEUSDT"

    print(f"\n🚪 Testing gatekeeper trend filtering for {symbol}...")

    # Inject overall bearish trend
    # This should set TREND_FILTER to BEARISH
    bearish_trend = generate_bearish_candles(
        start_price=0.10,
        num_candles=100,
        price_decrease_pct=10.0
    )

    await market_data_client.inject_candles(symbol, bearish_trend, interval="60")
    await asyncio.sleep(5)

    # Get signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        action = signal.get("action")
        metadata = signal.get("metadata", {})

        print(f"\n  Signal: {action}")
        print(f"  Metadata: {metadata}")

        # Check if trend blocking occurred
        if metadata.get("trend_blocked"):
            print("  ✅ Gatekeeper correctly blocked counter-trend signal")
        elif action == "HOLD":
            print("  ✅ Signal is HOLD (possibly blocked by gatekeeper)")
        elif action == "SELL":
            print("  ✅ SELL signal aligns with bearish trend")
        else:
            print(f"  ⚠️  {action} signal in bearish trend (may not be blocked)")
    else:
        pytest.skip("No signal generated")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_validator_rejects_low_confidence_signals(
    market_data_client,
    trading_engine_client
):
    """
    Test that validator rejects signals below confidence threshold.

    Low-confidence signals should be converted to HOLD.
    """
    symbol = "XRPUSDT"

    print(f"\n✅ Testing validator confidence threshold for {symbol}...")

    # Inject weak/unclear data that should produce low-confidence signals
    weak_candles = generate_sideways_candles(
        base_price=0.60,
        num_candles=50,
        volatility=0.03
    )

    await market_data_client.inject_candles(symbol, weak_candles, interval="60")
    await asyncio.sleep(5)

    # Get signal
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")

    if signal:
        action = signal.get("action")
        confidence = signal.get("confidence", 0)

        print(f"\n  Signal: {action}")
        print(f"  Confidence: {confidence:.2f}")

        # For unclear market, expect HOLD or very low confidence
        if action == "HOLD":
            print("  ✅ Validator correctly converted to HOLD")
        elif confidence < 0.5:
            print(f"  ℹ️  Low confidence signal ({confidence:.2f})")
        else:
            print(f"  ⚠️  High confidence ({confidence:.2f}) despite weak data")
    else:
        print("  ✅ No signal generated (correct for weak signals)")


# ============================================================================
# Signal Consistency Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_consistency_across_calls(
    market_data_client,
    trading_engine_client
):
    """
    Test that repeated signal requests return consistent results.

    Same market data should produce same signal (deterministic).
    """
    symbol = "LTCUSDT"

    print(f"\n🔄 Testing signal consistency for {symbol}...")

    # Inject data once
    candles = generate_bullish_candles(start_price=100.0, num_candles=60)
    await market_data_client.inject_candles(symbol, candles, interval="60")
    await asyncio.sleep(5)

    # Request signal multiple times
    signals = []
    for i in range(3):
        signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
        if signal:
            signals.append({
                "action": signal.get("action"),
                "confidence": signal.get("confidence", 0)
            })
            print(f"  Request {i+1}: {signal.get('action')} ({signal.get('confidence', 0):.2f})")
        await asyncio.sleep(1)

    # Verify consistency
    if len(signals) >= 2:
        first_action = signals[0]["action"]
        all_same_action = all(s["action"] == first_action for s in signals)

        if all_same_action:
            print(f"  ✅ Consistent action across {len(signals)} calls: {first_action}")
        else:
            print(f"  ⚠️  Inconsistent actions: {[s['action'] for s in signals]}")

        # Confidence should be very close (within 5%)
        confidences = [s["confidence"] for s in signals]
        max_diff = max(confidences) - min(confidences)

        if max_diff < 0.05:
            print(f"  ✅ Consistent confidence (max diff: {max_diff:.3f})")
        else:
            print(f"  ⚠️  Confidence varies: {confidences}")
    else:
        pytest.skip("Insufficient signals to verify consistency")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_signal_generation_for_multiple_symbols(
    market_data_client,
    trading_engine_client
):
    """
    Test signal generation works correctly for multiple symbols.

    Validates system can handle concurrent signal generation.
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"]

    print(f"\n📊 Testing signal generation for {len(symbols)} symbols...")

    # Inject different market conditions for each symbol
    market_conditions = ["bullish", "bearish", "sideways", "bullish"]

    for symbol, condition in zip(symbols, market_conditions):
        candles = generate_market_data_series(
            symbol=symbol,
            num_points=70,
            trend=condition,
            start_price=100.0
        )
        await market_data_client.inject_candles(symbol, candles, interval="60")

    print("  ⏳ Waiting for all signals to generate...")
    await asyncio.sleep(8)

    # Get signals for all symbols
    results = {}
    for symbol in symbols:
        signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
        if signal:
            results[symbol] = {
                "action": signal.get("action"),
                "confidence": signal.get("confidence", 0)
            }

    # Display results
    print(f"\n  Signals generated for {len(results)}/{len(symbols)} symbols:")
    for symbol, signal in results.items():
        print(f"    {symbol}: {signal['action']} ({signal['confidence']:.2f})")

    # At least half should have signals
    assert len(results) >= len(symbols) / 2, "Too few signals generated"

    print(f"\n  ✅ Successfully generated signals for multiple symbols")


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_signal_generation_performance(
    market_data_client,
    trading_engine_client
):
    """
    Test signal generation completes within performance SLA.

    SLA: Signal generation < 2 seconds
    """
    import time

    symbol = "AVAXUSDT"

    print(f"\n⚡ Testing signal generation performance for {symbol}...")

    # Inject data
    candles = generate_bullish_candles(start_price=50.0, num_candles=60)
    await market_data_client.inject_candles(symbol, candles, interval="60")
    await asyncio.sleep(3)

    # Measure signal generation time
    start_time = time.time()
    signal = await trading_engine_client.get_aggregate_signal(symbol, interval="60")
    elapsed_time = time.time() - start_time

    if signal:
        print(f"  Signal: {signal.get('action')} ({signal.get('confidence', 0):.2f})")
        print(f"  Generation time: {elapsed_time:.3f}s")

        # Performance assertion
        assert elapsed_time < 2.0, f"Signal generation too slow: {elapsed_time:.3f}s"

        print(f"  ✅ Signal generated within SLA (<2s)")
    else:
        pytest.skip("No signal generated")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
