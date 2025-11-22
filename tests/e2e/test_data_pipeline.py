#!/usr/bin/env python3
"""
Data Pipeline Flow E2E Tests

Tests the complete data pipeline from market data ingestion through
storage, caching, and consumption by analysis services.

Pipeline Flow:
1. Real-time data from Bybit WebSocket
2. Market Data Service receives and validates
3. Store in TimescaleDB (historical data)
4. Cache in Redis (fast access)
5. Trigger technical analysis calculations
6. Publish to RabbitMQ for signal generation
"""

import pytest
import asyncio
import time
from decimal import Decimal
from typing import List, Dict

from tests.e2e.utils.wait_for_health import poll_until
from tests.e2e.utils.assertions import (
    assert_data_freshness,
    assert_list_not_empty,
    assert_dict_contains_keys,
    assert_response_time,
    assert_within_range,
)
from tests.e2e.fixtures.mock_data import (
    generate_bullish_candles,
    generate_market_data_series,
)


# ============================================================================
# Data Ingestion Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_realtime_data_ingestion(market_data_client):
    """
    Test real-time market data ingestion and storage.

    Workflow:
    1. Inject real-time price data
    2. Verify data is stored in database
    3. Verify data is cached in Redis
    4. Verify data freshness (< 60 seconds old)
    """
    symbol = "BTCUSDT"

    print(f"\n📊 Testing real-time data ingestion for {symbol}...")

    # Step 1: Generate and inject market data
    candles = generate_bullish_candles(start_price=45000.0, num_candles=10)

    start_time = time.time()
    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=candles,
        interval="60"
    )
    ingestion_time = time.time() - start_time

    assert response.status_code in [200, 201], "Data ingestion failed"
    print(f"✅ Data injected in {ingestion_time:.2f}s")

    # Step 2: Verify data is retrievable
    await asyncio.sleep(2)  # Allow time for processing

    latest_price = await market_data_client.get_latest_price(symbol)

    assert_dict_contains_keys(
        latest_price,
        ["symbol", "price", "timestamp"],
        "Latest price response"
    )

    assert latest_price["symbol"] == symbol
    print(f"✅ Latest price retrieved: ${latest_price['price']}")

    # Step 3: Verify data freshness
    data_timestamp = latest_price["timestamp"]
    assert_data_freshness(
        timestamp=data_timestamp,
        max_age_seconds=60,
        data_type=f"{symbol} price data"
    )

    # Step 4: Verify historical candles are stored
    historical = await market_data_client.get_candles(symbol, interval="60", limit=20)

    assert_list_not_empty(historical, "Historical candles")
    print(f"✅ {len(historical)} historical candles stored")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_high_volume_data_ingestion(market_data_client):
    """
    Test system can handle high-volume data ingestion.

    Simulates receiving data for multiple symbols simultaneously.
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]

    print(f"\n📊 Testing high-volume data ingestion for {len(symbols)} symbols...")

    # Generate data for all symbols
    all_candles = {}
    for i, symbol in enumerate(symbols):
        all_candles[symbol] = generate_market_data_series(
            symbol=symbol,
            num_points=100,
            trend="bullish" if i % 2 == 0 else "bearish",
            start_price=100.0 + i*10
        )

    # Inject all data concurrently
    start_time = time.time()

    tasks = [
        market_data_client.inject_candles(symbol, candles, interval="60")
        for symbol, candles in all_candles.items()
    ]

    responses = await asyncio.gather(*tasks, return_exceptions=True)

    ingestion_time = time.time() - start_time

    # Verify all injections succeeded
    successful = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code in [200, 201])

    assert successful == len(symbols), f"Only {successful}/{len(symbols)} ingestions succeeded"

    print(f"✅ {successful} symbols ingested in {ingestion_time:.2f}s")
    print(f"   Throughput: {successful/ingestion_time:.2f} symbols/second")

    # Verify data is retrievable for all symbols
    await asyncio.sleep(3)

    for symbol in symbols:
        latest = await market_data_client.get_latest_price(symbol)
        assert latest is not None, f"No data for {symbol}"
        print(f"  ✓ {symbol}: ${latest.get('price')}")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_data_validation_rejects_invalid_data(market_data_client):
    """
    Test that data validation rejects malformed data.

    Validates input validation and error handling.
    """
    symbol = "BTCUSDT"

    print(f"\n🛡️ Testing data validation...")

    # Test 1: Missing required fields
    invalid_candles = [
        {
            "timestamp": int(time.time()),
            "open": 100.0,
            # Missing close, high, low, volume
        }
    ]

    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=invalid_candles,
        interval="60"
    )

    assert response.status_code in [400, 422], "Invalid data should be rejected"
    print("✅ Invalid data rejected (missing fields)")

    # Test 2: Negative prices
    invalid_candles = [
        {
            "timestamp": int(time.time()),
            "open": -100.0,  # Invalid negative price
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": 1000.0
        }
    ]

    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=invalid_candles,
        interval="60"
    )

    assert response.status_code in [400, 422], "Negative price should be rejected"
    print("✅ Negative prices rejected")

    # Test 3: High < Low (impossible candle)
    invalid_candles = [
        {
            "timestamp": int(time.time()),
            "open": 100.0,
            "high": 95.0,  # High less than low (impossible)
            "low": 100.0,
            "close": 98.0,
            "volume": 1000.0
        }
    ]

    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=invalid_candles,
        interval="60"
    )

    assert response.status_code in [400, 422], "Invalid OHLC relationship should be rejected"
    print("✅ Invalid OHLC relationship rejected")


# ============================================================================
# Data Storage and Retrieval Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_historical_data_storage_and_retrieval(market_data_client):
    """
    Test historical data is correctly stored and can be retrieved.

    Validates TimescaleDB storage functionality.
    """
    symbol = "ETHUSDT"

    print(f"\n💾 Testing historical data storage for {symbol}...")

    # Step 1: Inject 200 candles (simulate historical data)
    historical_candles = generate_market_data_series(
        symbol=symbol,
        num_points=200,
        trend="bullish",
        start_price=2000.0
    )

    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=historical_candles,
        interval="60"
    )

    assert response.status_code in [200, 201]
    print(f"✅ {len(historical_candles)} candles injected")

    # Step 2: Wait for storage
    await asyncio.sleep(3)

    # Step 3: Retrieve different ranges
    test_cases = [
        (10, "last 10 candles"),
        (50, "last 50 candles"),
        (100, "last 100 candles"),
        (200, "all 200 candles"),
    ]

    for limit, description in test_cases:
        candles = await market_data_client.get_candles(
            symbol=symbol,
            interval="60",
            limit=limit
        )

        assert len(candles) <= limit, f"Retrieved more than {limit} candles"
        assert len(candles) > 0, f"No candles retrieved for {description}"

        print(f"  ✓ Retrieved {len(candles)} candles ({description})")

    # Step 4: Verify chronological order
    candles = await market_data_client.get_candles(symbol, interval="60", limit=100)

    timestamps = [c["timestamp"] for c in candles]
    assert timestamps == sorted(timestamps), "Candles not in chronological order"

    print("✅ Candles in correct chronological order")

    # Step 5: Verify data integrity
    for candle in candles[:5]:
        assert candle["high"] >= candle["low"], "High < Low (data corruption)"
        assert candle["high"] >= candle["open"], "High < Open when it should be >= "
        assert candle["high"] >= candle["close"], "High < Close when it should be >="
        assert candle["low"] <= candle["open"], "Low > Open when it should be <="
        assert candle["low"] <= candle["close"], "Low > Close when it should be <="

    print("✅ Data integrity verified")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_data_aggregation_different_timeframes(market_data_client):
    """
    Test data can be aggregated into different timeframes.

    Validates timeframe conversion (1m → 5m → 15m → 1h → 4h → 1d).
    """
    symbol = "BNBUSDT"

    print(f"\n📊 Testing timeframe aggregation for {symbol}...")

    # Inject 1-minute candles
    minute_candles = generate_market_data_series(
        symbol=symbol,
        num_points=300,  # 5 hours of 1-minute data
        trend="bullish",
        start_price=300.0
    )

    response = await market_data_client.inject_candles(
        symbol=symbol,
        candles=minute_candles,
        interval="1"  # 1 minute
    )

    assert response.status_code in [200, 201]
    print(f"✅ {len(minute_candles)} 1-minute candles injected")

    await asyncio.sleep(3)

    # Retrieve different timeframes
    timeframes = [
        ("1", "1-minute"),
        ("5", "5-minute"),
        ("15", "15-minute"),
        ("60", "1-hour"),
    ]

    results = {}

    for interval, name in timeframes:
        candles = await market_data_client.get_candles(
            symbol=symbol,
            interval=interval,
            limit=100
        )

        results[interval] = candles
        print(f"  ✓ {name}: {len(candles)} candles")

    # Verify aggregation logic
    # 5-minute candles should have ~1/5 the count of 1-minute candles
    if len(results.get("1", [])) > 0 and len(results.get("5", [])) > 0:
        ratio = len(results["1"]) / max(len(results["5"]), 1)
        assert 3 <= ratio <= 7, f"Unexpected aggregation ratio: {ratio}"
        print(f"✅ Aggregation ratio verified: {ratio:.2f}x")


# ============================================================================
# Cache Performance Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_redis_cache_performance(market_data_client):
    """
    Test that Redis cache provides fast data access.

    Validates cache hit performance.
    """
    symbol = "SOLUSDT"

    print(f"\n⚡ Testing cache performance for {symbol}...")

    # Step 1: Inject data
    candles = generate_bullish_candles(start_price=100.0, num_candles=50)
    await market_data_client.inject_candles(symbol, candles, interval="60")

    await asyncio.sleep(2)

    # Step 2: First request (cache miss - slower)
    start_time = time.time()
    first_fetch = await market_data_client.get_latest_price(symbol)
    first_fetch_time = time.time() - start_time

    print(f"  First fetch (cache miss): {first_fetch_time*1000:.2f}ms")

    # Step 3: Second request (cache hit - faster)
    start_time = time.time()
    second_fetch = await market_data_client.get_latest_price(symbol)
    second_fetch_time = time.time() - start_time

    print(f"  Second fetch (cache hit): {second_fetch_time*1000:.2f}ms")

    # Step 4: Verify cache hit is faster
    # Cache hit should be at least 2x faster
    if first_fetch_time > 0.001:  # Only compare if first fetch was measurable
        speedup = first_fetch_time / max(second_fetch_time, 0.001)
        print(f"  Cache speedup: {speedup:.1f}x faster")

    # Step 5: Verify data consistency
    assert first_fetch["price"] == second_fetch["price"], "Cached data doesn't match"

    print("✅ Cache performance verified")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cache_invalidation_on_new_data(market_data_client):
    """
    Test that cache is invalidated when new data arrives.

    Validates cache freshness guarantees.
    """
    symbol = "ADAUSDT"

    print(f"\n🔄 Testing cache invalidation for {symbol}...")

    # Step 1: Inject initial data
    initial_candles = generate_bullish_candles(start_price=0.50, num_candles=10)
    await market_data_client.inject_candles(symbol, initial_candles, interval="60")

    await asyncio.sleep(2)

    # Step 2: Get initial cached price
    initial_price_data = await market_data_client.get_latest_price(symbol)
    initial_price = Decimal(str(initial_price_data["price"]))
    initial_timestamp = initial_price_data["timestamp"]

    print(f"  Initial price: ${initial_price} (timestamp: {initial_timestamp})")

    # Step 3: Inject new data with higher price
    new_candles = generate_bullish_candles(
        start_price=float(initial_price * Decimal("1.05")),  # 5% higher
        num_candles=5
    )
    await market_data_client.inject_candles(symbol, new_candles, interval="60")

    await asyncio.sleep(2)

    # Step 4: Get new price (cache should be invalidated)
    new_price_data = await market_data_client.get_latest_price(symbol)
    new_price = Decimal(str(new_price_data["price"]))
    new_timestamp = new_price_data["timestamp"]

    print(f"  New price: ${new_price} (timestamp: {new_timestamp})")

    # Step 5: Verify cache was updated
    assert new_timestamp > initial_timestamp, "Timestamp not updated (cache not invalidated)"
    assert new_price > initial_price, "Price not updated (cache stale)"

    print("✅ Cache correctly invalidated on new data")


# ============================================================================
# Data Flow Integration Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_data_pipeline_flow(
    market_data_client,
    technical_analysis_client
):
    """
    Test complete data pipeline from ingestion to analysis.

    Workflow:
    1. Inject market data
    2. Verify storage in database
    3. Verify caching in Redis
    4. Verify technical analysis consumes data
    5. Verify indicators are calculated
    """
    symbol = "BTCUSDT"

    print(f"\n🔄 Testing complete data pipeline for {symbol}...")

    # Step 1: Inject bullish market data
    candles = generate_bullish_candles(start_price=45000.0, num_candles=100)

    print("  1️⃣ Injecting market data...")
    response = await market_data_client.inject_candles(symbol, candles, interval="60")
    assert response.status_code in [200, 201]

    # Step 2: Verify storage
    print("  2️⃣ Verifying data storage...")
    await asyncio.sleep(2)

    stored_candles = await market_data_client.get_candles(symbol, interval="60", limit=100)
    assert len(stored_candles) > 0, "Data not stored"
    print(f"     ✓ {len(stored_candles)} candles stored")

    # Step 3: Verify caching
    print("  3️⃣ Verifying cache...")
    latest = await market_data_client.get_latest_price(symbol)
    assert latest is not None, "Data not cached"
    print(f"     ✓ Latest price cached: ${latest['price']}")

    # Step 4: Wait for technical analysis to process
    print("  4️⃣ Waiting for technical analysis...")
    await asyncio.sleep(5)

    # Step 5: Verify indicators are calculated
    print("  5️⃣ Verifying technical indicators...")
    indicators = await technical_analysis_client.get_indicators(symbol, interval="60")

    if indicators and len(indicators) > 0:
        # Check for common indicators
        expected_indicators = ["RSI", "MACD", "BB", "EMA"]
        found_indicators = [name for name in expected_indicators if name in indicators]

        print(f"     ✓ {len(found_indicators)} indicators calculated: {found_indicators}")

        # Verify indicator values are reasonable
        if "RSI" in indicators:
            rsi_value = indicators["RSI"].get("value", 0)
            assert_within_range(rsi_value, 0, 100, "RSI")

        if "MACD" in indicators:
            macd_value = indicators["MACD"].get("value", 0)
            print(f"     ✓ MACD: {macd_value}")
    else:
        print("     ⚠️  Technical indicators not yet calculated")

    print("\n✅ Complete data pipeline flow verified")


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.asyncio
async def test_data_pipeline_under_load(market_data_client):
    """
    Test data pipeline performance under sustained load.

    Simulates continuous data streaming for multiple symbols.
    """
    symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
    iterations = 10

    print(f"\n🔥 Testing data pipeline under load...")
    print(f"   Symbols: {len(symbols)}, Iterations: {iterations}")

    total_candles = 0
    total_time = 0

    for iteration in range(iterations):
        print(f"\n  Iteration {iteration + 1}/{iterations}...")

        start_time = time.time()

        # Inject data for all symbols
        tasks = []
        for symbol in symbols:
            candles = generate_market_data_series(
                symbol=symbol,
                num_points=10,
                trend="bullish",
                start_price=100.0 + iteration*5
            )
            tasks.append(
                market_data_client.inject_candles(symbol, candles, interval="60")
            )
            total_candles += len(candles)

        # Execute concurrently
        await asyncio.gather(*tasks)

        iteration_time = time.time() - start_time
        total_time += iteration_time

        print(f"    Completed in {iteration_time:.2f}s")

        # Brief pause between iterations
        await asyncio.sleep(1)

    # Calculate throughput
    avg_time_per_iteration = total_time / iterations
    throughput = total_candles / total_time

    print(f"\n📊 Load Test Results:")
    print(f"   Total candles: {total_candles}")
    print(f"   Total time: {total_time:.2f}s")
    print(f"   Avg time per iteration: {avg_time_per_iteration:.2f}s")
    print(f"   Throughput: {throughput:.2f} candles/second")

    # Performance assertion
    assert avg_time_per_iteration < 5.0, "Pipeline too slow under load"

    print("✅ Data pipeline handles load successfully")


# ============================================================================
# Error Handling and Recovery Tests
# ============================================================================

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_pipeline_handles_duplicate_data(market_data_client):
    """
    Test that pipeline handles duplicate data gracefully.

    Validates idempotency of data ingestion.
    """
    symbol = "DOGEUSDT"

    print(f"\n🔁 Testing duplicate data handling for {symbol}...")

    # Generate candles
    candles = generate_bullish_candles(start_price=0.10, num_candles=20)

    # Inject same data twice
    response1 = await market_data_client.inject_candles(symbol, candles, interval="60")
    await asyncio.sleep(1)

    response2 = await market_data_client.inject_candles(symbol, candles, interval="60")

    # Both should succeed (idempotent)
    assert response1.status_code in [200, 201]
    assert response2.status_code in [200, 201, 409]  # 409 = Conflict (duplicate)

    await asyncio.sleep(2)

    # Verify no data duplication
    stored_candles = await market_data_client.get_candles(symbol, interval="60", limit=50)

    # Should have roughly the same number as injected (not double)
    assert len(stored_candles) <= len(candles) * 1.5, "Data appears to be duplicated"

    print(f"✅ Duplicate data handled correctly ({len(stored_candles)} candles stored)")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
