"""Emit a coverage manifest for backfilled kline CSVs.

Usage: python3 backtesting/killtests/backfill_manifest.py > .planning/evidence/killtests/backfill-manifest-2026-08.md
"""

import hashlib
import os

import pandas as pd

SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
INTERVALS = {"15": 15, "60": 60, "240": 240, "1440": 1440}
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def main() -> None:
    print("# Backfill manifest\n")
    print("| file | rows | first | last | expected step (min) | gaps | sha256[:12] |")
    print("|---|---|---|---|---|---|---|")
    for sym in SYMBOLS:
        for iv, minutes in INTERVALS.items():
            path = os.path.abspath(
                os.path.join(DATA_DIR, f"{sym}_{iv}m_365d_bybit.csv")
            )
            if not os.path.exists(path):
                print(f"| {os.path.basename(path)} | MISSING | | | {minutes} | | |")
                continue
            df = pd.read_csv(path)
            ts = pd.to_datetime(df["timestamp"])
            steps = ts.diff().dropna().dt.total_seconds() / 60
            gaps = int((steps != minutes).sum())
            digest = hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]
            print(
                f"| {os.path.basename(path)} | {len(df)} | {ts.iloc[0]} | {ts.iloc[-1]} "
                f"| {minutes} | {gaps} | {digest} |"
            )


if __name__ == "__main__":
    main()
