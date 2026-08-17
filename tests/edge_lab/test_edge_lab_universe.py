import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from edge_lab.universe import select_universe, write_pin, load_pin  # noqa: E402

NOW = 1_800_000_000_000
OLD = NOW - 800 * 86_400_000  # ~800 days old
YOUNG = NOW - 100 * 86_400_000  # 100 days old


def _ticker(sym, turnover):
    return {"symbol": sym, "turnover24h": str(turnover)}


def _inst(sym, launch, status="Trading", ctype="LinearPerpetual"):
    return {
        "symbol": sym,
        "launchTime": str(launch),
        "status": status,
        "contractType": ctype,
    }


def test_sorts_by_turnover_and_caps():
    tickers = [_ticker(f"C{i}USDT", 1000 - i) for i in range(40)]
    instruments = [_inst(f"C{i}USDT", OLD) for i in range(40)]
    selected, excluded = select_universe(tickers, instruments, NOW, top_n=30)
    assert len(selected) == 30
    assert selected[0]["symbol"] == "C0USDT"  # highest turnover first
    assert selected[0]["turnover24h"] >= selected[-1]["turnover24h"]


def test_age_filter_excludes_young_and_names_them():
    tickers = [_ticker("OLDUSDT", 100), _ticker("YOUNGUSDT", 99999)]
    instruments = [_inst("OLDUSDT", OLD), _inst("YOUNGUSDT", YOUNG)]
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert [s["symbol"] for s in selected] == ["OLDUSDT"]
    assert "YOUNGUSDT" in excluded


def test_non_usdt_and_non_trading_excluded():
    tickers = [_ticker("AAAUSDT", 5), _ticker("BBBUSD", 9), _ticker("CCCUSDT", 7)]
    instruments = [
        _inst("AAAUSDT", OLD),
        _inst("BBBUSD", OLD),
        _inst("CCCUSDT", OLD, status="Closed"),
    ]
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert [s["symbol"] for s in selected] == ["AAAUSDT"]
    assert "CCCUSDT" in excluded  # named, not silent


def test_missing_launchtime_excluded_not_crash():
    tickers = [_ticker("XUSDT", 5)]
    instruments = [{"symbol": "XUSDT", "status": "Trading"}]  # no launchTime
    selected, excluded = select_universe(tickers, instruments, NOW)
    assert selected == [] and "XUSDT" in excluded


def test_pin_round_trip(tmp_path):
    tickers = [_ticker("AUSDT", 5)]
    instruments = [_inst("AUSDT", OLD)]
    selected, excluded = select_universe(tickers, instruments, NOW)
    p = write_pin(selected, excluded, "2026-08-16", tmp_path)
    pin = load_pin(p)
    assert pin["symbols"][0]["symbol"] == "AUSDT"
    assert pin["date"] == "2026-08-16"
    data = json.loads(p.read_text())
    assert data == pin
