import asyncio
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from killtests.candles import INTERVAL_MS, CandleStore  # noqa: E402

from conftest import _write_candles  # noqa: E402  # shared writer, same-dir conftest


def test_driver_emits_rows_and_advances_clock(tmp_path):
    for iv, n in [("15", 2000), ("60", 500), ("240", 400), ("1440", 60)]:
        _write_candles(tmp_path, "BTCUSDT", iv, n, "2026-04-01 00:00:00")
    store = CandleStore(str(tmp_path), ["BTCUSDT"], ["15", "60", "240", "1440"])
    from killtests.offline_ensemble import ReplayClock, load_stack, run_replay

    clock = ReplayClock(now_ms=0)
    stack = load_stack(store, clock)
    df = asyncio.run(run_replay(store, stack, clock, ["BTCUSDT"], warmup_bars=450))
    f60 = store.frame("BTCUSDT", "60")
    expected_rows = len(f60) - 450
    assert len(df) == expected_rows
    assert df["ts_ms"].is_monotonic_increasing
    # decision time is always a 60m bar CLOSE
    assert ((df["ts_ms"] - f60["ts_ms"].iloc[0]) % INTERVAL_MS["60"] == 0).all()
    assert set(df["action"].unique()) <= {"BUY", "SELL", "HOLD"}
    assert df["close"].notna().all()
