#!/usr/bin/env python3
"""
Single Trading Cycle Demo
Runs one trading cycle to demonstrate enhanced diagnostics
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.automated_trading_loop_with_notifications import TradingBot, TradingConfig, TradingMode

async def main():
    """Run a single trading cycle for demo"""
    
    # Configure for single cycle
    config = TradingConfig(
        symbols=["BTCUSDT"],  # Just test one symbol
        interval_minutes=5,
        signal_interval=60,
        min_confidence=0.65,
        mode=TradingMode.PAPER,
        enable_notifications=False  # Disable for demo
    )
    
    bot = TradingBot(config)
    await bot.client.__aenter__()  # Initialize client
    
    print("\n" + "="*80)
    print("🤖 RUNNING SINGLE TRADING CYCLE WITH ENHANCED DIAGNOSTICS")
    print("="*80 + "\n")
    
    # Run just one cycle
    await bot._trading_cycle()
    
    await bot.client.__aexit__(None, None, None)
    
    print("\n" + "="*80)
    print("✅ Demo Complete!")
    print("="*80)

if __name__ == "__main__":
    asyncio.run(main())
