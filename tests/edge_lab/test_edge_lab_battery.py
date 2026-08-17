import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, make_daily  # noqa: E402
from edge_lab.run_battery import run_battery  # noqa: E402
from edge_lab.trades import Trade, Variant  # noqa: E402


def _write_daily_csvs(data_dir, daily):
    import pandas as pd
    from edge_lab.fetch import kline_csv_path

    for sym, df in daily.items():
        out = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
                "symbol": sym,
                "interval": "D",
                "open": df["open"],
                "high": df["high"],
                "low": df["low"],
                "close": df["close"],
                "volume": df["volume"],
                "turnover": df["volume"],
                "is_mainnet": True,
                "created_at": df["ts_ms"].iloc[-1],
            }
        )
        out.to_csv(kline_csv_path(data_dir, sym, "D", 730), index=False)


def _pin(tmp_path, symbols):
    from edge_lab.universe import write_pin

    sel = [{"symbol": s, "turnover24h": 1.0, "launch_ms": 0} for s in symbols]
    return write_pin(sel, [], "2026-08-16", tmp_path)


def _stub_registry(gen_map):
    """candidate name -> generate_trades(data_bundle, variant) stub registry."""
    return {
        name: {"variants": [Variant(name, "v0", ())], "generate": fn}
        for name, fn in gen_map.items()
    }


def test_crashing_candidate_isolated(tmp_path):
    daily = make_daily(["AUSDT", "BUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT", "BUSDT"])

    def boom(bundle, variant):
        raise RuntimeError("candidate exploded")

    def quiet(bundle, variant):
        return []

    res = run_battery(
        tmp_path,
        pin,
        tmp_path / "out",
        T0 + 400 * DAY,
        candidates=_stub_registry({"boom": boom, "quiet": quiet}),
    )
    assert res["boom"]["verdict"] == "ERROR"
    assert "candidate exploded" in res["boom"]["error"]
    assert res["quiet"]["verdict"] == "REJECT"  # completed despite boom


def test_zero_trades_recorded_not_screened(tmp_path):
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])
    res = run_battery(
        tmp_path,
        pin,
        tmp_path / "out",
        T0 + 400 * DAY,
        candidates=_stub_registry({"quiet": lambda b, v: []}),
    )
    v = res["quiet"]["variants"][0]
    assert v["n_trades"] == 0 and v["gate1_verdict"] == "NO_TRADES"


def test_verdict_docs_written_with_caveats(tmp_path):
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates=_stub_registry({"solo": one_trade}),
    )
    docs = list(out.glob("solo-verdict-*.md"))
    assert len(docs) == 1
    text = docs[0].read_text()
    assert "Survivorship" in text and "num_trials floor = 16" in text
    summaries = list(out.glob("battery-summary-*.md"))
    assert len(summaries) == 1
