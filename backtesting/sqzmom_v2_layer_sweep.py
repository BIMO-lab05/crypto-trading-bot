"""
Phase C-3 layer sweep: run sqzmom_v2 with L0..L5 on a single symbol to
isolate which filter kills trade count.

Run: python3 backtesting/sqzmom_v2_layer_sweep.py
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "strategies"))

import pandas as pd

from data_downloader import HistoricalDataDownloader
from backtest_engine import BacktestEngine
from sqzmom_v2 import precompute_features, make_sqzmom_v2
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402


SYMBOL = "SOLUSDT"
DAYS = 90  # post-flip safe window
INTERVAL = "60"


async def main():
    print(f"=== Phase C layer sweep: {SYMBOL} {DAYS}d @ {INTERVAL}m ===")

    downloader = HistoricalDataDownloader(market_data_url="http://localhost:8002")
    raw = await downloader.download_historical_data(
        symbol=SYMBOL, interval=INTERVAL, days=DAYS
    )
    await downloader.close()

    if raw is None or len(raw) == 0:
        print("FAIL: no data")
        return

    if "timestamp" in raw.columns:
        ts = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw.assign(timestamp=ts).set_index("timestamp")
    print(f"raw bars: {len(raw)}  range: {raw.index[0]} -> {raw.index[-1]}")

    enriched = precompute_features(raw)
    print(f"enriched cols: {len(enriched.columns)}")
    sqz_off_count = enriched["squeeze_off"].sum()
    no_sqz_count = enriched["no_squeeze"].sum()
    print(f"squeeze_off bars: {sqz_off_count}, no_squeeze bars: {no_sqz_count}")
    print(
        f"mom_pos_2 bars: {enriched['mom_pos_2'].sum()}, "
        f"mom_neg_2 bars: {enriched['mom_neg_2'].sum()}"
    )
    print(
        f"adx>=20 bars: {(enriched['adx_14'] >= 20).sum()}, "
        f"vol>=1.2x bars: {(enriched['vol_ratio'] >= 1.2).sum()}"
    )
    print(f"mtf4h color non-null bars: {enriched['mtf4h_sqz_color'].notna().sum()}")

    print(
        f"\n{'Layer':<8} {'Trades':<8} {'Win %':<8} {'P&L %':<8} {'Max DD %':<10} {'PF':<6}"
    )
    print("-" * 60)
    for layer in range(0, 6):
        engine = BacktestEngine(initial_capital=ACCOUNT_EQUITY_USD)
        strategy = make_sqzmom_v2(layer=layer)
        result = engine.run_backtest(
            enriched, strategy, strategy_name=f"sqzmom_v2_L{layer}"
        )
        n = len(engine.trades)
        wr = getattr(result, "win_rate", 0.0)
        pl = getattr(result, "total_profit_loss_pct", 0.0)
        dd = getattr(result, "max_drawdown_pct", 0.0)
        pf = getattr(result, "profit_factor", 0.0)
        print(f"L{layer:<7} {n:<8} {wr:<8.2f} {pl:<8.2f} {dd:<10.2f} {pf:<6.2f}")


if __name__ == "__main__":
    asyncio.run(main())
