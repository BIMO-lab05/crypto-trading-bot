import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtesting"))

from conftest import DAY, T0, make_daily  # noqa: E402
from edge_lab import trial_ledger  # noqa: E402
from edge_lab.run_battery import run_battery  # noqa: E402
from edge_lab.trades import Trade, Variant  # noqa: E402


def _write_kline_csv(data_dir, sym, df, interval, days):
    import pandas as pd
    from edge_lab.fetch import kline_csv_path

    out = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(df["ts_ms"], unit="ms"),
            "symbol": sym,
            "interval": interval,
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
    out.to_csv(kline_csv_path(data_dir, sym, interval, days), index=False)


def _write_daily_csvs(data_dir, daily):
    for sym, df in daily.items():
        _write_kline_csv(data_dir, sym, df, "D", 730)


def _write_funding_csv(data_dir, sym, ts_list, rate="0.0001"):
    import pandas as pd
    from edge_lab.fetch import funding_csv_path

    path = funding_csv_path(data_dir, sym)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ts_ms": ts_list, "funding_rate": [rate] * len(ts_list)}).to_csv(
        path, index=False
    )


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


def test_crashing_candidate_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
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


def test_zero_trades_recorded_not_screened(tmp_path, monkeypatch):
    monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
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


def test_gate0_drops_are_scoped_to_the_failing_interval(tmp_path):
    """A defect on one interval must not cost a symbol the other one.

    AUSDT: clean daily, holed 4h  -> keeps daily + funding, drops from h4.
    BUSDT: absent daily, clean 4h -> keeps h4 (and gets a 4h sanity row),
    which is the direction that used to be lost to an early `continue`.
    """
    import pandas as pd

    from edge_lab.run_battery import load_bundle
    from edge_lab.universe import load_pin

    h4_ms = 4 * 3_600_000
    daily = make_daily(["AUSDT", "BUSDT"], n_days=400)
    _write_kline_csv(tmp_path, "AUSDT", daily["AUSDT"], "D", 730)  # BUSDT: none

    h4 = make_daily(["AUSDT", "BUSDT"], n_days=600, seed=3)
    for sym, df in h4.items():
        df = df.assign(ts_ms=[T0 + k * h4_ms for k in range(len(df))])
        if sym == "AUSDT":
            # 10 consecutive bars removed -> gap > 2 intervals -> defect
            df = pd.concat([df.iloc[:100], df.iloc[110:]]).reset_index(drop=True)
        _write_kline_csv(tmp_path, sym, df, "240", 365)

    for sym in ("AUSDT", "BUSDT"):
        _write_funding_csv(tmp_path, sym, [T0 + k * (DAY // 3) for k in range(1200)])

    pin = load_pin(_pin(tmp_path, ["AUSDT", "BUSDT"]))
    bundle, summary = load_bundle(tmp_path, pin, T0 + 400 * DAY)

    assert sorted(bundle["daily"]) == ["AUSDT"]
    assert sorted(bundle["h4"]) == ["BUSDT"]
    assert sorted(bundle["funding"]) == ["AUSDT"]  # BUSDT lost daily -> lost funding
    assert "dropped_h4=[AUSDT]" in summary
    assert "dropped_daily=[BUSDT]" in summary
    # BUSDT's 4h row must be present despite it having no daily CSV at all.
    assert "BUSDT [240]" in summary


def test_date_cutoff_drops_rows_after_now_ms(tmp_path):
    """--date is a real data cutoff, not just a filename: a CSV extending
    past now_ms loads only bars that CLOSED by then, and funding likewise."""
    from edge_lab.run_battery import load_bundle
    from edge_lab.universe import load_pin

    _write_daily_csvs(tmp_path, make_daily(["AUSDT"], n_days=400))
    _write_funding_csv(tmp_path, "AUSDT", [T0 + k * (DAY // 3) for k in range(1200)])
    pin = load_pin(_pin(tmp_path, ["AUSDT"]))

    cutoff = T0 + 200 * DAY
    bundle, _ = load_bundle(tmp_path, pin, cutoff)

    bars = bundle["daily"]["AUSDT"]
    assert len(bars) == 200
    # last kept bar OPENS at T0+199d and closes exactly at the cutoff
    assert int(bars["ts_ms"].iloc[-1]) == T0 + 199 * DAY
    assert int(bars["ts_ms"].max()) + DAY <= cutoff

    settlements = bundle["funding"]["AUSDT"]
    assert len(settlements) == 200 * 3
    assert int(settlements["ts_ms"].max()) < cutoff


def test_import_failure_is_error_not_reject(tmp_path, monkeypatch):
    """A candidate whose module failed to import has no variants, so the
    variant loop never runs. It must still be ERROR with the traceback —
    filing it as REJECT makes a broken import indistinguishable from a
    genuine no-edge finding."""
    monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    out = tmp_path / "out"
    res = run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates={
            "broken": {
                "variants": [],
                "inputs": ("daily",),
                "import_error": "ModuleNotFoundError: no such candidate",
            }
        },
    )
    assert res["broken"]["verdict"] == "ERROR"
    assert "no such candidate" in res["broken"]["error"]
    doc = next(out.glob("broken-verdict-*.md")).read_text()
    assert "verdict: ERROR" in doc
    assert "no such candidate" in doc


def test_gate2_drops_trades_on_symbols_with_no_daily_frame(tmp_path, caplog):
    """A 4h-only symbol reaches Gate 2 as a named drop, not a KeyError.

    `load_bundle` keeps a symbol whose 4h bars are clean even when its daily
    bars are absent, so vol_breakout can legitimately trade a symbol Gate 2
    has no closes for. Those trades come out of the scoring — never scored
    against closes resampled from 4h bars — and the drop is logged and
    returned rather than absorbed.
    """
    from edge_lab.run_battery import score_gate2

    daily = make_daily(["AUSDT"], n_days=400)  # BUSDT deliberately has none
    trades = [
        # The dropped symbol trades FIRST: if the window were derived before
        # the filter, start_ms would land on this entry instead of AUSDT's.
        Trade("BUSDT", "LONG", T0 + 10 * DAY, T0 + 17 * DAY, 100.0, 105.0),
        Trade("BUSDT", "SHORT", T0 + 50 * DAY, T0 + 57 * DAY, 100.0, 95.0),
        Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0),
    ]

    with caplog.at_level("WARNING"):
        _result, start_ms, _end_ms, _horizon, dropped = score_gate2(
            trades, daily, "vol_breakout", tmp_path / "funding", 16
        )

    assert dropped == {"BUSDT": 2}
    assert start_ms == T0 + 30 * DAY  # the surviving trade's entry
    assert "BUSDT (2 trades)" in caplog.text


def test_gate2_all_trades_dropped_raises_rather_than_scoring_nothing(tmp_path):
    """Every trade on a daily-less symbol is a data failure, not a REJECT.

    Returning a failed Gate2Result here would render a data outage as an
    honest-looking "no edge" finding — the worst output this battery can
    produce.
    """
    from edge_lab.run_battery import score_gate2

    daily = make_daily(["AUSDT"], n_days=400)
    trades = [Trade("BUSDT", "LONG", T0 + 10 * DAY, T0 + 17 * DAY, 100.0, 105.0)]

    with pytest.raises(RuntimeError, match="data failure"):
        score_gate2(trades, daily, "vol_breakout", tmp_path / "funding", 16)


def test_verdict_docs_written_with_caveats(tmp_path, monkeypatch):
    monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])

    def one_trade(bundle, variant):
        return [Trade("AUSDT", "LONG", T0 + 30 * DAY, T0 + 37 * DAY, 100.0, 105.0)]

    out = tmp_path / "out"
    res = run_battery(
        tmp_path,
        pin,
        out,
        T0 + 400 * DAY,
        candidates=_stub_registry({"solo": one_trade}),
    )
    # The no-drop path of the Gate 2 record. Written even when nothing was
    # dropped, so a reader can tell "none dropped" from "this run predates
    # the field" — the claim score_gate2's caller makes in its comment.
    record = res["solo"]["variants"][0]
    assert record["gate2_trades_dropped_no_daily"] == {}
    assert record["gate2_n_trades_scored"] == 1

    docs = list(out.glob("solo-verdict-*.md"))
    assert len(docs) == 1
    text = docs[0].read_text()
    assert "Survivorship" in text and "num_trials floor = 16" in text
    summaries = list(out.glob("battery-summary-*.md"))
    assert len(summaries) == 1
