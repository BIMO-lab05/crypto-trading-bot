#!/usr/bin/env python3
"""
Test Grid Trading v1 WITHOUT Filters - CSV Data
================================================
Tests if the 0% win rate is caused by overly restrictive filters.

Hypothesis: Filters (ADX/RSI/Volume) block all profitable trades
Test: Run Grid v1 with filters DISABLED on same CSV data

Expected: Win rate should improve if filters are the problem
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'trading-engine'))

# DISABLE ALL FILTERS
import app.strategies.grid_trading_strategy as grid_module
grid_module.USE_ADX_FILTER = False
grid_module.USE_RSI_FILTER = False
grid_module.USE_VOLUME_FILTER = False
grid_module.USE_ADAPTIVE_FILTERS = False

# Now run the same test
from test_grid_v1_with_csv import main

if __name__ == "__main__":
    import asyncio
    print("\n" + "="*80)
    print("🔓 TESTING GRID V1 WITHOUT FILTERS (CSV DATA)")
    print("="*80)
    print("Filters: ALL DISABLED")
    print("Data: Real 180-day Bybit historical CSV")
    print("="*80 + "\n")
    asyncio.run(main())
