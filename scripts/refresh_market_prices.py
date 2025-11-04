#!/usr/bin/env python3
"""
Price Refresh Script
Purpose: Automatically refresh ticker data for all trading pairs
Usage: Run this script periodically (e.g., via cron every 5 minutes)
"""

import requests
import sys
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
MARKET_DATA_URL = "http://localhost:8003"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]


def refresh_ticker(symbol: str) -> bool:
    """
    Refresh ticker data for a single symbol

    Args:
        symbol: Trading pair symbol (e.g., BTCUSDT)

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        url = f"{MARKET_DATA_URL}/api/v1/collect/ticker/{symbol}"
        response = requests.post(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get("success"):
            logger.info(f"✓ {symbol}: ${data['data']['last_price']} ({data['data']['price_change_24h']}%)")
            return True
        else:
            logger.error(f"✗ {symbol}: {data.get('message', 'Unknown error')}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"✗ {symbol}: Network error - {e}")
        return False
    except Exception as e:
        logger.error(f"✗ {symbol}: {e}")
        return False


def main():
    """Main execution function"""
    logger.info("=" * 60)
    logger.info(f"MARKET PRICE REFRESH - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    results = {"success": 0, "failed": 0}

    for symbol in SYMBOLS:
        if refresh_ticker(symbol):
            results["success"] += 1
        else:
            results["failed"] += 1

    logger.info("-" * 60)
    logger.info(f"Completed: {results['success']}/{len(SYMBOLS)} successful")

    if results["failed"] > 0:
        logger.warning(f"Failed to refresh {results['failed']} symbol(s)")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
