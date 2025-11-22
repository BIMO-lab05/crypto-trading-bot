#!/usr/bin/env python3
"""
ML Model Training Data Readiness Verification
Purpose: Verify all symbols have sufficient data for model training
"""

import asyncio
import asyncpg
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class SymbolRequirement:
    """ML training requirements per symbol"""
    symbol: str
    min_candles: int = 2160  # 90 days × 24 hours
    min_days: float = 90.0
    status: str = "unknown"
    actual_candles: int = 0
    actual_days: float = 0.0
    message: str = ""

class DataReadinessChecker:
    """Verify data is ready for ML training"""

    def __init__(self):
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            host="localhost",
            port=5433,
            database="market_data",
            user="cryptobot",
            password="timescale_dev_password",
        )

    async def disconnect(self):
        if self.pool:
            await self.pool.close()

    async def check_symbol(self, symbol: str) -> SymbolRequirement:
        """Check readiness for one symbol"""
        req = SymbolRequirement(symbol=symbol)

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT
                        COUNT(*) as total_candles,
                        EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) / 86400 as days_covered,
                        MIN(time) as earliest,
                        MAX(time) as latest
                    FROM market_data.candles
                    WHERE symbol = $1 AND interval = '60'
                """, symbol)

                if result and result['total_candles']:
                    req.actual_candles = result['total_candles']
                    req.actual_days = float(result['days_covered'])
                    req.earliest = result['earliest']
                    req.latest = result['latest']

                    # Determine status
                    if req.actual_candles >= req.min_candles:
                        req.status = "READY"
                        req.message = f"✅ Sufficient data: {req.actual_candles} candles ({req.actual_days:.1f} days)"
                    else:
                        gap = req.min_candles - req.actual_candles
                        req.status = "INSUFFICIENT"
                        req.message = f"⚠️ Need {gap} more candles ({(req.min_days - req.actual_days):.1f} more days)"
                else:
                    req.status = "NO_DATA"
                    req.message = "❌ No data in database"

        except Exception as e:
            req.status = "ERROR"
            req.message = f"❌ Error: {str(e)}"

        return req

    async def check_all(self, symbols: List[str]) -> List[SymbolRequirement]:
        """Check all symbols"""
        results = []
        for symbol in symbols:
            req = await self.check_symbol(symbol)
            results.append(req)
        return results

async def main():
    print("\n" + "="*80)
    print("ML MODEL TRAINING DATA READINESS CHECK")
    print("="*80 + "\n")

    # Symbols to check
    symbols = [
        "BTCUSDT",
        "ETHUSDT",
        "BNBUSDT",
        "SOLUSDT",
        "XRPUSDT",
        "ADAUSDT",
        "DOGEUSDT",
    ]

    checker = DataReadinessChecker()

    try:
        await checker.connect()
        results = await checker.check_all(symbols)

        # Print results
        print("Symbol Data Coverage:\n")
        print(f"{'Symbol':10} | {'Status':12} | {'Candles':8} | {'Days':7} | {'Message'}")
        print("-" * 80)

        ready_count = 0
        insufficient_count = 0

        for req in results:
            status_display = req.status
            if req.status == "READY":
                status_display = "✅ READY"
                ready_count += 1
            elif req.status == "INSUFFICIENT":
                status_display = "⚠️  NEED DATA"
                insufficient_count += 1
            elif req.status == "NO_DATA":
                status_display = "❌ NO DATA"
            else:
                status_display = f"❌ {req.status}"

            candles_str = f"{req.actual_candles}" if req.actual_candles else "0"
            days_str = f"{req.actual_days:.1f}" if req.actual_days else "0.0"

            print(
                f"{req.symbol:10} | {status_display:12} | {candles_str:>8} | "
                f"{days_str:>7} | {req.message}"
            )

        # Summary
        print("\n" + "-" * 80)
        print(f"\nSummary:")
        print(f"  Ready for training: {ready_count}/{len(symbols)}")
        print(f"  Insufficient data: {insufficient_count}/{len(symbols)}")

        if ready_count == len(symbols):
            print("\n✅ ALL SYMBOLS READY FOR ML MODEL TRAINING!")
        elif ready_count > 0:
            print(f"\n⚠️ PARTIAL READINESS: {ready_count} symbols ready, {insufficient_count} need more data")
        else:
            print("\n❌ NO SYMBOLS READY - NEED DATA COLLECTION")

        # Recommendations
        print("\nRecommendations:")
        if insufficient_count > 0:
            print("  1. Extend historical data collection using public Bybit API")
            print("  2. Or: Use available data for initial training with validation gaps noted")
            print("  3. Or: Augment data using synthetic generation for training")
        else:
            print("  1. Proceed with full ML model training")
            print("  2. Use cross-validation to optimize parameters")
            print("  3. Plan for weekly model retraining with new data")

        print("\n" + "="*80 + "\n")

    finally:
        await checker.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
