#!/usr/bin/env python3
"""
Debug script to check price discrepancies between system and Bybit
"""

import asyncio
import httpx
import json
from datetime import datetime

async def check_ada_prices():
    print("🔍 Checking ADA price sources...")
    print(f"Timestamp: {datetime.now()}")
    print("-" * 60)

    # Check Bybit Connector directly
    print("\n1. Checking Bybit Connector Service:")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if service is running
            health_resp = await client.get("http://localhost:8001/health")
            print(f"   Bybit Connector Health: {health_resp.status_code == 200}")
            
            # Get ADA ticker from Bybit Connector
            ticker_resp = await client.get("http://localhost:8001/api/v1/market/ticker?symbol=ADAUSDT")
            if ticker_resp.status_code == 200:
                ticker_data = ticker_resp.json()
                ada_price = ticker_data.get('data', {}).get('list', [{}])[0].get('lastPrice')
                print(f"   ADAUSDT from Bybit Connector: ${ada_price}")
            else:
                print(f"   ❌ Failed to get ticker: {ticker_resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error connecting to Bybit Connector: {e}")

    # Check Market Data Service
    print("\n2. Checking Market Data Service:")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if service is running
            health_resp = await client.get("http://localhost:8002/health")
            print(f"   Market Data Service Health: {health_resp.status_code == 200}")
            
            # Get ADA ticker from Market Data Service
            ticker_resp = await client.get("http://localhost:8002/api/v1/ticker/ADAUSDT")
            if ticker_resp.status_code == 200:
                ticker_data = ticker_resp.json()
                ada_price = ticker_data.get('data', {}).get('last_price')
                source = ticker_data.get('source', 'unknown')
                print(f"   ADAUSDT from Market Data Service: ${ada_price} (source: {source})")
            else:
                print(f"   ❌ Failed to get ticker: {ticker_resp.status_code}")
    except Exception as e:
        print(f"   ❌ Error connecting to Market Data Service: {e}")

    # Check Trading Engine
    print("\n3. Checking Trading Engine:")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check if service is running
            health_resp = await client.get("http://localhost:8005/health")
            print(f"   Trading Engine Health: {health_resp.status_code == 200}")
            
            # Get latest kline for ADA from Trading Engine (via API Gateway would be ideal, but let's check direct)
            # This might not have a direct endpoint, so we'll check configuration
            print("   Trading Engine configuration:")
            print("   - Trading Symbols: ADAUSDT should be included")
            print("   - Market Data URL: should point to market-data:8002 in Docker")
    except Exception as e:
        print(f"   ❌ Error connecting to Trading Engine: {e}")

    print("\n4. Checking Docker Services Status:")
    import subprocess
    try:
        result = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
        services_running = [
            'crypto-bot-bybit' in result.stdout,
            'crypto-bot-market-data' in result.stdout,
            'crypto-bot-trading' in result.stdout
        ]
        print(f"   Bybit Connector: {'✅ Running' if services_running[0] else '❌ Not Running'}")
        print(f"   Market Data: {'✅ Running' if services_running[1] else '❌ Not Running'}")
        print(f"   Trading Engine: {'✅ Running' if services_running[2] else '❌ Not Running'}")
    except Exception as e:
        print(f"   ❌ Could not check Docker status: {e}")

    print("\n5. Potential Issues Identified:")
    print("   - Check if API keys are valid (not placeholder values)")
    print("   - Verify services are running in Docker")
    print("   - Clear Redis cache if stale data suspected")
    print("   - Check network connectivity between services")
    
    print("\n💡 Suggestions:")
    print("   1. Run 'docker-compose ps' to check service status")
    print("   2. Check logs: 'docker-compose logs bybit-connector'")
    print("   3. Verify API keys in services/bybit-connector/.env")
    print("   4. Restart services if needed: 'docker-compose restart'")

if __name__ == "__main__":
    asyncio.run(check_ada_prices())