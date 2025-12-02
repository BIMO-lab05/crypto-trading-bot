#!/usr/bin/env python3
"""
Trade Sample Collector
Accelerates trade sample collection by triggering analyses on multiple symbols

Usage:
    python scripts/collect_trades.py --target 50 --interval 60
"""

import asyncio
import httpx
import argparse
import logging
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
TRADING_ENGINE_URL = "http://localhost:8005"
ML_SERVICE_URL = "http://localhost:8007"

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "LTCUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT"
]


async def get_current_trade_count(client: httpx.AsyncClient) -> int:
    """Get current number of trades"""
    try:
        response = await client.get(f"{TRADING_ENGINE_URL}/api/v1/trades/history")
        if response.status_code == 200:
            data = response.json()
            return data.get("stats", {}).get("total_trades", 0)
    except Exception as e:
        logger.error(f"Failed to get trade count: {e}")
    return 0


async def get_position_count(client: httpx.AsyncClient) -> Dict[str, int]:
    """Get open and closed position counts"""
    try:
        response = await client.get(f"{TRADING_ENGINE_URL}/api/v1/positions?status=all")
        if response.status_code == 200:
            data = response.json()
            positions = data.get("positions", [])
            open_count = sum(1 for p in positions if p.get("status") == "OPEN")
            closed_count = sum(1 for p in positions if p.get("status") == "CLOSED")
            return {"open": open_count, "closed": closed_count, "total": len(positions)}
    except Exception as e:
        logger.error(f"Failed to get positions: {e}")
    return {"open": 0, "closed": 0, "total": 0}


async def trigger_analysis(client: httpx.AsyncClient, symbol: str) -> Dict[str, Any]:
    """Trigger signal analysis for a symbol"""
    try:
        response = await client.get(
            f"{TRADING_ENGINE_URL}/api/v1/signals/{symbol}",
            params={"interval": "60"}
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.warning(f"Failed to analyze {symbol}: {e}")
    return {}


async def trigger_trade_signal(client: httpx.AsyncClient, symbol: str) -> Dict[str, Any]:
    """Trigger trade analysis which may execute a trade"""
    try:
        response = await client.post(
            f"{TRADING_ENGINE_URL}/api/v1/strategies/sqzmom/trade/{symbol}"
        )
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.warning(f"Failed to trigger trade for {symbol}: {e}")
    return {}


async def get_trading_status(client: httpx.AsyncClient) -> Dict[str, Any]:
    """Get auto-trading status"""
    try:
        response = await client.get(f"{TRADING_ENGINE_URL}/api/v1/trading/status")
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        logger.error(f"Failed to get trading status: {e}")
    return {}


async def train_ml_model(client: httpx.AsyncClient, symbol: str, model_type: str = "GRU") -> bool:
    """Train ML model for a symbol"""
    try:
        response = await client.post(
            f"{ML_SERVICE_URL}/api/v1/models/train",
            json={
                "symbol": symbol,
                "model_type": model_type,
                "epochs": 100,
                "force_retrain": True
            },
            timeout=300  # 5 minutes timeout for training
        )
        if response.status_code == 200:
            data = response.json()
            logger.info(f"  {symbol} model trained: {data.get('message', 'Success')}")
            return data.get("success", False)
    except Exception as e:
        logger.warning(f"  Failed to train {symbol} model: {e}")
    return False


async def collect_trades(target: int, check_interval: int = 60):
    """Main trade collection loop"""
    logger.info("=" * 60)
    logger.info("TRADE SAMPLE COLLECTOR")
    logger.info("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check initial status
        positions = await get_position_count(client)
        logger.info(f"Initial positions: {positions['total']} (open: {positions['open']}, closed: {positions['closed']})")

        trading_status = await get_trading_status(client)
        status = trading_status.get("status", {})
        logger.info(f"Auto-trader running: {status.get('is_running', False)}")
        logger.info(f"Strategy: {status.get('strategy_mode', 'unknown')}")

        # Collection loop
        cycle = 0
        while True:
            cycle += 1
            logger.info(f"\n--- Cycle {cycle} ---")

            # Get current counts
            positions = await get_position_count(client)
            total_samples = positions['total']

            logger.info(f"Current samples: {total_samples} / {target} (open: {positions['open']}, closed: {positions['closed']})")

            if total_samples >= target:
                logger.info(f"\n*** TARGET REACHED: {total_samples} samples collected! ***")
                break

            # Trigger analyses for all symbols
            logger.info("Triggering signal analyses...")
            for symbol in SYMBOLS[:10]:  # Top 10 symbols
                result = await trigger_analysis(client, symbol)
                signal = result.get("signal", {})
                if signal.get("signal_type") not in [None, "HOLD", "NEUTRAL"]:
                    logger.info(f"  {symbol}: {signal.get('signal_type')} (strength: {signal.get('strength', 'N/A')})")
                await asyncio.sleep(0.5)

            # Wait for next cycle
            remaining = target - total_samples
            logger.info(f"Waiting {check_interval}s for next cycle... ({remaining} samples remaining)")
            await asyncio.sleep(check_interval)


async def train_models_for_symbols(symbols: List[str], model_type: str = "GRU"):
    """Train ML models for multiple symbols"""
    logger.info("=" * 60)
    logger.info(f"TRAINING {model_type} MODELS")
    logger.info("=" * 60)

    async with httpx.AsyncClient(timeout=300.0) as client:
        trained = 0
        failed = 0

        for symbol in symbols:
            logger.info(f"Training {symbol}...")
            success = await train_ml_model(client, symbol, model_type)
            if success:
                trained += 1
            else:
                failed += 1
            await asyncio.sleep(2)  # Small delay between trainings

        logger.info(f"\nTraining complete: {trained} successful, {failed} failed")


async def main():
    parser = argparse.ArgumentParser(description="Collect trade samples")
    parser.add_argument("--target", type=int, default=50, help="Target number of trade samples")
    parser.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    parser.add_argument("--train-ml", action="store_true", help="Train ML models first")
    parser.add_argument("--model-type", type=str, default="GRU", help="ML model type (LSTM or GRU)")
    args = parser.parse_args()

    if args.train_ml:
        await train_models_for_symbols(SYMBOLS[:7], args.model_type)

    await collect_trades(args.target, args.interval)


if __name__ == "__main__":
    asyncio.run(main())
