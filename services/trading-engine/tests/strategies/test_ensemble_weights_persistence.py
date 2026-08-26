"""Persistence tests for StrategyPerformanceWeights (ensemble adaptive weights).

Defect (2026-08-20): /app/data/ensemble_weights.json never existed in the
running trading-engine container. Two causes: docker-compose.unified.yml
mounted nothing at /app/data (state written on trade close died on container
recreate), and _persist only fires from record_outcome on trade close — with
almost no closed trades since 2026-08-18 nothing was ever written. All three
leg win rates therefore sat frozen at the 0.50 default (weights exactly 1/3),
making the adaptive weighting described in the class docstring inert.

The compose fix adds a named volume (trading_engine_data -> /app/data). These
tests pin the code contract so a regression is caught host-side:
  - roundtrip: record_outcome persists; a fresh instance loads the same state
  - missing file -> defaults, no raise
  - corrupt file -> defaults, no raise, next persist overwrites it
  - atomic write: no .tmp file survives a successful persist

No IO mocking: STATE_PATH is monkeypatched to a tmp_path file. (Do NOT patch
builtins.open here — pathlib and _io bypass it; a real tmp file is the only
honest fixture.)
"""

import json

import pytest

from app.strategies.multi_strategy_ensemble import (
    LEG_MEAN_REV,
    LEG_MULTI,
    LEG_RSI,
    StrategyPerformanceWeights,
)


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Point the class at a per-test state file; no singleton involved."""
    path = tmp_path / "ensemble_weights.json"
    monkeypatch.setattr(StrategyPerformanceWeights, "STATE_PATH", str(path))
    return path


def test_missing_file_falls_back_to_defaults(state_file):
    w = StrategyPerformanceWeights()
    assert not state_file.exists()
    assert w._win_rates == {
        LEG_RSI: StrategyPerformanceWeights.DEFAULT_WIN_RATE,
        LEG_MULTI: StrategyPerformanceWeights.DEFAULT_WIN_RATE,
        LEG_MEAN_REV: StrategyPerformanceWeights.DEFAULT_WIN_RATE,
    }
    assert w._trade_counts == {LEG_RSI: 0, LEG_MULTI: 0, LEG_MEAN_REV: 0}
    # Defaults normalize to exactly 1/3 each — the frozen state we observed live.
    for v in w.normalized_weights().values():
        assert v == pytest.approx(1.0 / 3.0)


def test_record_outcome_roundtrips_through_disk(state_file):
    w = StrategyPerformanceWeights()
    w.record_outcome(LEG_RSI, won=True)
    w.record_outcome(LEG_MEAN_REV, won=False)

    # File written on update, not only at shutdown.
    assert state_file.exists()
    on_disk = json.loads(state_file.read_text())
    # EMA from 0.50: win -> 0.55, loss -> 0.45 (alpha = 0.10).
    assert on_disk["win_rates"][LEG_RSI] == pytest.approx(0.55)
    assert on_disk["win_rates"][LEG_MEAN_REV] == pytest.approx(0.45)
    assert on_disk["trade_counts"] == {LEG_RSI: 1, LEG_MULTI: 0, LEG_MEAN_REV: 1}
    assert "ts" in on_disk

    # A fresh instance (restart) loads the same state.
    w2 = StrategyPerformanceWeights()
    assert w2._win_rates == pytest.approx(w._win_rates)
    assert w2._trade_counts == w._trade_counts


def test_corrupt_file_falls_back_to_defaults_and_recovers(state_file):
    state_file.write_text("{this is not json")

    w = StrategyPerformanceWeights()  # must not raise
    assert w._win_rates[LEG_RSI] == StrategyPerformanceWeights.DEFAULT_WIN_RATE
    assert w._trade_counts[LEG_RSI] == 0

    # The next outcome overwrites the corrupt file with valid state.
    w.record_outcome(LEG_MULTI, won=True)
    recovered = json.loads(state_file.read_text())
    assert recovered["win_rates"][LEG_MULTI] == pytest.approx(0.55)


def test_persist_is_atomic_no_tmp_leftover(state_file):
    w = StrategyPerformanceWeights()
    w.record_outcome(LEG_RSI, won=True)
    assert state_file.exists()
    # os.replace consumed the tmp file; a leftover means the write went direct.
    assert not state_file.with_name(state_file.name + ".tmp").exists()


def test_schema_corrupt_file_keeps_defaults_for_bad_entries(state_file):
    """Valid JSON, wrong schema: non-numeric win rate + foreign leg key.
    Neither may be adopted — a blind dict.update would detonate later as a
    TypeError inside normalized_weights, ON THE SIGNAL PATH."""
    state_file.write_text(
        json.dumps({"win_rates": {"simple_rsi": "high", "alien": 0.9}})
    )

    w = StrategyPerformanceWeights()  # must not raise
    # Bad value skipped -> default retained; foreign key never adopted.
    assert w._win_rates[LEG_RSI] == StrategyPerformanceWeights.DEFAULT_WIN_RATE
    assert "alien" not in w._win_rates
    # The signal-path consumer works on the sanitized state.
    weights = w.normalized_weights()
    assert set(weights) == {LEG_RSI, LEG_MULTI, LEG_MEAN_REV}
    for v in weights.values():
        assert v == pytest.approx(1.0 / 3.0)


def test_valid_entries_are_adopted_alongside_corrupt_ones(state_file):
    """Per-entry validation, not all-or-nothing: the good leg keeps its
    persisted rate while the corrupt one falls back to the default."""
    state_file.write_text(
        json.dumps({"win_rates": {"mean_reversion": 0.62, "simple_rsi": "high"}})
    )

    w = StrategyPerformanceWeights()
    assert w._win_rates[LEG_MEAN_REV] == pytest.approx(0.62)
    assert w._win_rates[LEG_RSI] == StrategyPerformanceWeights.DEFAULT_WIN_RATE


def test_persist_failure_does_not_crash_trading(state_file, monkeypatch):
    """A read-only /app/data must degrade to a warning, never break trade close."""
    w = StrategyPerformanceWeights()

    def boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(
        "app.strategies.multi_strategy_ensemble.os.replace", boom
    )
    w.record_outcome(LEG_RSI, won=True)  # must not raise
    # In-memory state still advanced even though persistence failed.
    assert w._win_rates[LEG_RSI] == pytest.approx(0.55)
