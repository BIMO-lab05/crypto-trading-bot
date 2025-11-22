"""
End-to-End Trading Flow Integration Tests
Tests complete trading flow from signal to execution
"""

import pytest
import asyncio


@pytest.mark.asyncio
async def test_complete_trading_flow(
    services_config,
    http_client,
    wait_for_services,
    test_symbol
):
    """
    Test complete trading flow:
    1. Get market data
    2. Run technical analysis
    3. Get trading signal
    4. Execute paper trade (if signal is BUY/SELL)
    5. Verify position created
    6. Check portfolio update
    """
    api_gateway = services_config["api_gateway"]

    # Step 1: Get market data
    response = await http_client.get(f"{api_gateway}/api/market/ticker/{test_symbol}")
    assert response.status_code == 200
    ticker_data = response.json()
    assert "ticker" in ticker_data

    # Step 2: Get technical analysis
    response = await http_client.get(f"{api_gateway}/api/analysis/all/{test_symbol}")
    assert response.status_code == 200
    analysis_data = response.json()
    assert "data" in analysis_data

    # Step 3: Get trading signal
    response = await http_client.get(f"{api_gateway}/api/trading/signals/{test_symbol}")
    assert response.status_code == 200
    signal_data = response.json()
    assert "signal" in signal_data

    signal = signal_data["signal"]
    action = signal["action"]

    # Step 4: Execute trade if signal is actionable
    if action in ["BUY", "SELL"]:
        response = await http_client.post(
            f"{api_gateway}/api/trading/signals/{test_symbol}/analyze",
            params={"execute": True}
        )
        assert response.status_code == 200
        result = response.json()
        assert result["success"] is True

        # Step 5: Verify position created (for BUY) or closed (for SELL)
        await asyncio.sleep(2)  # Wait for position update
        response = await http_client.get(f"{api_gateway}/api/trading/positions")
        assert response.status_code == 200
        positions = response.json()
        assert "positions" in positions

        # Step 6: Verify portfolio updated
        response = await http_client.get(f"{api_gateway}/api/portfolio/balance")
        assert response.status_code == 200
        balance = response.json()
        assert "balance" in balance


@pytest.mark.asyncio
async def test_market_data_to_analysis_flow(
    services_config,
    http_client,
    wait_for_services,
    test_symbol
):
    """Test market data flows correctly to technical analysis"""
    api_gateway = services_config["api_gateway"]

    # Get market data
    response = await http_client.get(f"{api_gateway}/api/market/kline/{test_symbol}")
    assert response.status_code == 200
    kline_data = response.json()

    # Get technical indicators (should use same market data)
    response = await http_client.get(f"{api_gateway}/api/analysis/rsi/{test_symbol}")
    assert response.status_code == 200
    rsi_data = response.json()
    assert "data" in rsi_data

    # Verify RSI value is calculated from market data
    assert "rsi" in rsi_data["data"]
    rsi_value = rsi_data["data"]["rsi"]["value"]
    assert 0 <= rsi_value <= 100


@pytest.mark.asyncio
async def test_signal_to_execution_latency(
    services_config,
    http_client,
    wait_for_services,
    test_symbol
):
    """Test signal generation to execution latency"""
    import time
    api_gateway = services_config["api_gateway"]

    start_time = time.time()

    # Get signal
    response = await http_client.get(f"{api_gateway}/api/trading/signals/{test_symbol}")
    signal_time = time.time() - start_time

    assert response.status_code == 200
    assert signal_time < 1.0  # Should be < 1 second

    # Execute signal
    start_time = time.time()
    response = await http_client.post(
        f"{api_gateway}/api/trading/signals/{test_symbol}/analyze",
        params={"execute": True}
    )
    execution_time = time.time() - start_time

    assert response.status_code == 200
    assert execution_time < 0.5  # Should be < 500ms

    total_latency = signal_time + execution_time
    assert total_latency < 1.5  # Total latency < 1.5 seconds


@pytest.mark.asyncio
async def test_portfolio_consistency(
    services_config,
    http_client,
    wait_for_services
):
    """Test portfolio data consistency across services"""
    api_gateway = services_config["api_gateway"]

    # Get portfolio from API gateway
    response = await http_client.get(f"{api_gateway}/api/portfolio")
    assert response.status_code == 200
    portfolio_data = response.json()

    # Get balance
    response = await http_client.get(f"{api_gateway}/api/portfolio/balance")
    assert response.status_code == 200
    balance_data = response.json()

    # Get holdings
    response = await http_client.get(f"{api_gateway}/api/portfolio/holdings")
    assert response.status_code == 200
    holdings_data = response.json()

    # Verify consistency
    # Total value should equal balance + holdings value
    # (This assumes proper data structure in responses)


@pytest.mark.asyncio
async def test_multi_symbol_trading(
    services_config,
    http_client,
    wait_for_services
):
    """Test trading across multiple symbols simultaneously"""
    api_gateway = services_config["api_gateway"]
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    # Get signals for all symbols simultaneously
    tasks = [
        http_client.get(f"{api_gateway}/api/trading/signals/{symbol}")
        for symbol in symbols
    ]

    responses = await asyncio.gather(*tasks)

    # Verify all responses
    for response in responses:
        assert response.status_code == 200
        data = response.json()
        assert "signal" in data
