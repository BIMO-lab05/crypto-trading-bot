"""Parametrised GRU trainer.

Usage (inside the ml-prediction container):
    python -m app.training.train_gru_symbol XRPUSDT
    python -m app.training.train_gru_symbol BTCUSDT
    python -m app.training.train_gru_symbol ETHUSDT --csv /app/data/ml_training/BTCUSDT_1H_24months_20251208.csv

Picks the most recent matching CSV in /app/data/ml_training/ if --csv isn't given.
Writes a single line of JSON-formatted metrics to stdout for easy harvesting.
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

# Importable inside the container — repo root is /app/app/...
sys.path.insert(0, "/app")

from app.ml_models.gru_model import GRUPricePredictor


def find_csv(symbol: str) -> Path:
    base = Path("/app/data/ml_training")
    candidates = sorted(base.glob(f"{symbol}_1H_*.csv"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No 1H CSV found for {symbol} under {base}")
    return candidates[0]


def load_df(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp").drop_duplicates(subset="timestamp")
    return df


async def run(symbol: str, csv_path: Path, interval: str = "60") -> dict:
    print(f"[train] symbol={symbol} csv={csv_path}", flush=True)
    df = load_df(csv_path)
    print(f"[train] loaded {len(df)} candles, {df['timestamp'].min()} -> {df['timestamp'].max()}", flush=True)

    train_size = int(len(df) * 0.85)
    train_df = df.iloc[:train_size].reset_index(drop=True)
    print(f"[train] using {len(train_df)} candles for training (15% reserved as test by GRU class)", flush=True)

    gru = GRUPricePredictor(symbol=symbol, interval=interval)
    t0 = time.time()
    info = await gru.train(train_df)
    elapsed = time.time() - t0
    print(f"[train] done in {elapsed:.1f}s", flush=True)

    return {
        "symbol": symbol,
        "interval_min": int(interval),
        "rows_used": len(train_df),
        "training_seconds": round(elapsed, 1),
        "validation_accuracy": getattr(info, "validation_accuracy", None),
        "validation_mae": getattr(info, "validation_mae", None),
        "validation_rmse": getattr(info, "validation_rmse", None),
        "validation_r2": getattr(info, "validation_r2_score", None),
        "model_size_mb": getattr(info, "model_size_mb", None),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--csv", type=Path, default=None)
    ap.add_argument("--interval", default="60")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    csv_path = args.csv or find_csv(args.symbol)
    metrics = asyncio.run(run(args.symbol, csv_path, args.interval))
    print("METRICS_JSON " + json.dumps(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
