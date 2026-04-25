#!/usr/bin/env python3
"""
DEBUGGER: Temporary test file for investigating notification system
TO BE DELETED BEFORE FINAL REPORT
Created: 2025-12-11
"""

import asyncio
import aiohttp
import os
import sys

# Add project root to path
sys.path.insert(0, '/mnt/d/Bimo_max/crypto-trading-bot')

print("[DEBUGGER:TEST] Starting notification system debug test")

async def test_notification_service_direct():
    """Test direct connection to notification service"""
    print("\n" + "="*60)
    print("[DEBUGGER:TEST] Testing direct notification service connection")
    print("="*60)

    # Test both possible URLs
    urls = [
        "http://localhost:8006",
        "http://notification-service:8006",
        "http://localhost:8007",  # Maybe on wrong port?
    ]

    for base_url in urls:
        print(f"\n[DEBUGGER:TEST] Testing URL: {base_url}")
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                # Test health endpoint
                health_url = f"{base_url}/health"
                print(f"[DEBUGGER:TEST] Checking health at: {health_url}")
                async with session.get(health_url) as response:
                    status = response.status
                    body = await response.json()
                    print(f"[DEBUGGER:TEST] Health response: status={status}")
                    print(f"[DEBUGGER:TEST] Health body: {body}")
        except aiohttp.ClientConnectorError as e:
            print(f"[DEBUGGER:TEST] Connection FAILED: {e}")
        except Exception as e:
            print(f"[DEBUGGER:TEST] Error: {type(e).__name__}: {e}")

async def test_notification_send():
    """Test sending a notification"""
    print("\n" + "="*60)
    print("[DEBUGGER:TEST] Testing notification send")
    print("="*60)

    base_url = "http://localhost:8006"

    data = {
        "action": "BUY",
        "symbol": "BTCUSDT_DEBUG_TEST",
        "quantity": 0.001,
        "price": 50000.0,
        "timestamp": "2025-12-11T00:00:00",
        "signal_confidence": 0.75
    }

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            url = f"{base_url}/api/v1/notify/trade"
            print(f"[DEBUGGER:TEST] Sending trade notification to: {url}")
            print(f"[DEBUGGER:TEST] Payload: {data}")

            async with session.post(url, json=data) as response:
                status = response.status
                body = await response.json()
                print(f"[DEBUGGER:TEST] Response status: {status}")
                print(f"[DEBUGGER:TEST] Response body: {body}")

                if body.get("telegram_sent"):
                    print("[DEBUGGER:TEST] SUCCESS - Telegram message was sent!")
                else:
                    print("[DEBUGGER:TEST] FAIL - Telegram message was NOT sent")

    except aiohttp.ClientConnectorError as e:
        print(f"[DEBUGGER:TEST] Connection FAILED: {e}")
    except Exception as e:
        print(f"[DEBUGGER:TEST] Error: {type(e).__name__}: {e}")

async def test_telegram_direct():
    """Test direct Telegram API connection"""
    print("\n" + "="*60)
    print("[DEBUGGER:TEST] Testing direct Telegram API")
    print("="*60)

    # Read from notification service .env
    env_path = "/mnt/d/Bimo_max/crypto-trading-bot/services/notification-service/.env"

    bot_token = None
    chat_id = None

    try:
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('TELEGRAM_BOT_TOKEN='):
                    bot_token = line.split('=', 1)[1].strip()
                elif line.startswith('TELEGRAM_CHAT_ID='):
                    chat_id = line.split('=', 1)[1].strip()

        print(f"[DEBUGGER:TEST] Bot token loaded: {'YES' if bot_token else 'NO'}")
        print(f"[DEBUGGER:TEST] Chat ID loaded: {chat_id}")

        if bot_token and chat_id:
            # Test getMe endpoint
            async with aiohttp.ClientSession() as session:
                url = f"https://api.telegram.org/bot{bot_token}/getMe"
                print(f"[DEBUGGER:TEST] Testing Telegram bot identity...")
                async with session.get(url) as response:
                    body = await response.json()
                    print(f"[DEBUGGER:TEST] getMe response: {body}")

                # Send test message
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                test_msg = {
                    "chat_id": chat_id,
                    "text": "[DEBUG TEST] If you receive this, Telegram API is working!\nTest time: 2025-12-11",
                    "parse_mode": "HTML"
                }
                print(f"[DEBUGGER:TEST] Sending test message to chat {chat_id}...")
                async with session.post(url, json=test_msg) as response:
                    status = response.status
                    body = await response.json()
                    print(f"[DEBUGGER:TEST] sendMessage status: {status}")
                    print(f"[DEBUGGER:TEST] sendMessage response: {body}")

                    if body.get("ok"):
                        print("[DEBUGGER:TEST] SUCCESS - Direct Telegram API works!")
                    else:
                        print(f"[DEBUGGER:TEST] FAIL - Telegram API error: {body.get('description')}")
        else:
            print("[DEBUGGER:TEST] FAIL - Could not load credentials")

    except Exception as e:
        print(f"[DEBUGGER:TEST] Error: {type(e).__name__}: {e}")

async def check_trading_engine_config():
    """Check trading engine configuration"""
    print("\n" + "="*60)
    print("[DEBUGGER:TEST] Checking trading engine configuration")
    print("="*60)

    env_path = "/mnt/d/Bimo_max/crypto-trading-bot/services/trading-engine/.env"

    try:
        with open(env_path, 'r') as f:
            content = f.read()

        print("[DEBUGGER:TEST] Trading Engine .env notification settings:")
        for line in content.split('\n'):
            if 'NOTIF' in line.upper() or 'NOTIFY' in line.upper():
                print(f"  {line}")

        # Check for potential issues
        if 'NOTIFICATION_SERVICE_URL=http://notification-service:8006' in content:
            print("\n[DEBUGGER:TEST] WARNING: URL uses 'notification-service' hostname")
            print("[DEBUGGER:TEST] This works in Docker but fails for local testing!")
            print("[DEBUGGER:TEST] Should be 'http://localhost:8006' for local testing")
        elif 'NOTIFICATION_SERVICE_URL=http://localhost:8006' in content:
            print("\n[DEBUGGER:TEST] URL uses localhost:8006 - good for local testing")

    except Exception as e:
        print(f"[DEBUGGER:TEST] Error reading config: {e}")

async def main():
    print("="*60)
    print("[DEBUGGER:TEST] NOTIFICATION SYSTEM DEBUG TEST")
    print("="*60)

    await check_trading_engine_config()
    await test_notification_service_direct()
    await test_telegram_direct()
    await test_notification_send()

    print("\n" + "="*60)
    print("[DEBUGGER:TEST] TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(main())
