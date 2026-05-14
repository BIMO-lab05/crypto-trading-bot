"""Unit tests for app.config.tournament_loader."""

import textwrap
from pathlib import Path

import pytest
import yaml as _yaml

from app.config.tournament_loader import (
    load_tournament,
    enumerate_experiments,
    _hp_hash,
    _experiment_seed,
)


EXAMPLE = (
    Path(__file__).resolve().parents[2] / "app" / "config" / "example_tournament.yaml"
)


def test_load_example_yaml(tmp_path):
    spec = load_tournament(EXAMPLE)
    assert spec.tournament_id == "example_2026_05_08"
    assert spec.seed == 42
    assert (
        "SOLUSDT" in spec.symbols
        and "BNBUSDT" in spec.symbols
        and "ADAUSDT" in spec.symbols
    )


def test_enumerate_full_cartesian(tmp_path):
    spec = load_tournament(EXAMPLE)
    exps = enumerate_experiments(spec)
    assert len(exps) > 0
    # All four arch families appear
    archs = {e.architecture for e in exps}
    assert archs == {"gru", "lstm", "transformer", "tcn"}
    # All three symbols appear
    syms = {e.symbol for e in exps}
    assert {"SOLUSDT", "BNBUSDT", "ADAUSDT"} <= syms


def test_hp_hash_is_deterministic():
    h1 = _hp_hash({"x": 1, "y": [1, 2]})
    h2 = _hp_hash({"y": [1, 2], "x": 1})  # different key order
    assert h1 == h2
    assert len(h1) == 16


def test_experiment_seed_uint32():
    h = "deadbeef" + "00" * 4
    s = _experiment_seed(42, h)
    assert 0 <= s <= 0xFFFFFFFF


def test_re_enumerate_produces_identical_hashes(tmp_path):
    s1 = load_tournament(EXAMPLE)
    s2 = load_tournament(EXAMPLE)
    e1 = enumerate_experiments(s1)
    e2 = enumerate_experiments(s2)
    assert [(x.run_id, x.hp_hash, x.experiment_seed) for x in e1] == [
        (x.run_id, x.hp_hash, x.experiment_seed) for x in e2
    ]


def _write(yaml_path: Path, text: str):
    yaml_path.write_text(textwrap.dedent(text))


def test_load_rejects_missing_top_level(tmp_path):
    p = tmp_path / "bad.yaml"
    _write(
        p,
        """
        tournament_id: t1
        seed: 1
    """,
    )
    with pytest.raises(ValueError, match="missing required"):
        load_tournament(p)


def test_load_rejects_bad_symbol(tmp_path):
    p = tmp_path / "bad.yaml"
    _write(
        p,
        """
        tournament_id: t1
        seed: 1
        symbols: ["BTC; bad-shell-injection-attempt"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        default_resource_caps: {mem_limit: 4g, cpus: 2.0, wallclock_timeout_seconds: 1800}
        architectures:
          gru:
            units: [[32]]
            dropout: [0.1]
            lr: [0.001]
            batch: [32]
            lookback: [60]
            horizon: [5]
    """,
    )
    with pytest.raises(ValueError, match="Bybit-convention"):
        load_tournament(p)


def test_load_rejects_bare_base_symbol(tmp_path):
    """Symbol convention guard — bare base symbols (e.g. 'SOL') must be rejected.

    Bybit's klines.symbol column stores quote-pair form ('SOLUSDT'). Allowing
    bare base symbols would silently miss all rows in production and trip the
    50K row floor on every cell.
    """
    p = tmp_path / "bare.yaml"
    _write(
        p,
        """
        tournament_id: t1
        seed: 1
        symbols: ["SOL"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        default_resource_caps: {mem_limit: 4g, cpus: 2.0, wallclock_timeout_seconds: 1800}
        architectures:
          gru:
            units: [[32]]
            dropout: [0.1]
            lr: [0.001]
            batch: [32]
            lookback: [60]
            horizon: [5]
    """,
    )
    with pytest.raises(ValueError, match="Bybit-convention"):
        load_tournament(p)


def test_load_rejects_unknown_architecture(tmp_path):
    p = tmp_path / "bad.yaml"
    _write(
        p,
        """
        tournament_id: t1
        seed: 1
        symbols: ["SOLUSDT"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        default_resource_caps: {mem_limit: 4g, cpus: 2.0, wallclock_timeout_seconds: 1800}
        architectures:
          random_forest:
            units: [[32]]
    """,
    )
    with pytest.raises(ValueError, match="unknown architectures"):
        load_tournament(p)


def test_enumerate_rejects_grid_exceeding_max(tmp_path):
    p = tmp_path / "huge.yaml"
    _write(
        p,
        """
        tournament_id: t1
        seed: 1
        symbols: ["SOLUSDT"]
        intervals: ["5m"]
        target_modes: ["log_returns"]
        max_experiments: 3
        default_resource_caps: {mem_limit: 4g, cpus: 2.0, wallclock_timeout_seconds: 1800}
        architectures:
          gru:
            units: [[32], [64], [128], [256]]
            dropout: [0.1, 0.2, 0.3]
            lr: [0.001, 0.0005]
            batch: [32]
            lookback: [60]
            horizon: [5]
    """,
    )
    spec = load_tournament(p)
    with pytest.raises(ValueError, match="exceeds max_experiments"):
        enumerate_experiments(spec)


def test_safe_load_rejects_unsafe_python_tag(tmp_path):
    """T-03-11 — yaml.safe_load must reject unsafe !!python/... tags.

    SafeLoader raises ConstructorError on any tag it cannot construct from
    primitive YAML types. This is the security property — tagged Python objects
    cannot deserialise into runnable code.
    """
    p = tmp_path / "tagged.yaml"
    # Use a tag that yaml.SafeLoader does not recognise. The literal string
    # is data on disk; safe_load will raise rather than execute anything.
    p.write_text("tournament_id: !!python/name:builtins.print 'hi'\nseed: 1\n")
    with pytest.raises(_yaml.constructor.ConstructorError):
        load_tournament(p)


def test_resource_caps_override_for_transformer(tmp_path):
    spec = load_tournament(EXAMPLE)
    exps = enumerate_experiments(spec)
    transformer_caps = {
        e.resource_caps["mem_limit"] for e in exps if e.architecture == "transformer"
    }
    gru_caps = {e.resource_caps["mem_limit"] for e in exps if e.architecture == "gru"}
    # Transformer has its own override; GRU uses default
    assert "8g" in transformer_caps
    assert "4g" in gru_caps


def test_run_id_format(tmp_path):
    spec = load_tournament(EXAMPLE)
    exps = enumerate_experiments(spec)
    for e in exps[:5]:
        # run_id contains arch, symbol, hp_hash
        assert e.architecture in e.run_id
        assert e.symbol in e.run_id
        assert e.hp_hash in e.run_id
