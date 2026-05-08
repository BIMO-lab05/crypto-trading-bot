"""Unit tests for app.core.models.lstm.build (CD-01)."""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip(
    "tensorflow",
    reason="tensorflow not installed in this environment",
)

from app.core.models import lstm  # noqa: E402  (after importorskip)


def test_build_returns_compiled_keras_sequential():
    model = lstm.build(
        input_shape=(60, 17),
        hp={"units": [64, 32], "dropout": 0.2, "lr": 0.001, "horizon": 5},
    )
    # 2 LSTM layers + 2 Dropout + 1 Dense = 5 layers
    assert len(model.layers) == 5
    assert model.optimizer.learning_rate.numpy() == pytest.approx(0.001)
    assert model.loss == "mse"
    # Has at least one LSTM layer
    assert any("lstm" in layer.name.lower() for layer in model.layers)


def test_build_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing required keys"):
        lstm.build(input_shape=(60, 17), hp={"units": [32], "dropout": 0.1})


def test_build_rejects_out_of_range_units():
    with pytest.raises(ValueError, match="entries must be int"):
        lstm.build(
            input_shape=(60, 17),
            hp={
                "units": [10_000_000],
                "dropout": 0.1,
                "lr": 0.001,
                "horizon": 5,
            },
        )


def test_build_rejects_zero_horizon():
    with pytest.raises(ValueError, match="horizon"):
        lstm.build(
            input_shape=(60, 17),
            hp={
                "units": [32],
                "dropout": 0.1,
                "lr": 0.001,
                "horizon": 0,
            },
        )


def test_registry_contains_lstm():
    from app.core.models import REGISTRY

    assert "lstm" in REGISTRY
    assert hasattr(REGISTRY["lstm"], "build")
