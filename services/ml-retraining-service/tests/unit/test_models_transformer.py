"""Unit tests for app.core.models.transformer.build (CD-01)."""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip(
    "tensorflow",
    reason="tensorflow not installed in this environment",
)

from app.core.models import transformer  # noqa: E402  (after importorskip)


_BASE_HP = {
    "units": [64],
    "dropout": 0.1,
    "lr": 0.001,
    "horizon": 5,
    "n_heads": 4,
    "n_blocks": 2,
}


def test_build_returns_compiled_keras_model():
    model = transformer.build(input_shape=(60, 17), hp=_BASE_HP)
    # Functional model — exercise it has output of (None, horizon)
    assert model.output_shape == (None, 5)
    assert model.optimizer.learning_rate.numpy() == pytest.approx(0.001)
    assert model.loss == "mse"


def test_build_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing required keys"):
        transformer.build(input_shape=(60, 17), hp={"units": [32], "dropout": 0.1})


def test_build_rejects_invalid_n_heads():
    bad = dict(_BASE_HP, n_heads=3)
    with pytest.raises(ValueError, match="n_heads"):
        transformer.build(input_shape=(60, 17), hp=bad)


def test_build_rejects_out_of_range_units():
    bad = dict(_BASE_HP, units=[10_000_000])
    with pytest.raises(ValueError, match="entries must be int"):
        transformer.build(input_shape=(60, 17), hp=bad)


def test_registry_contains_transformer():
    from app.core.models import REGISTRY

    assert "transformer" in REGISTRY
    assert hasattr(REGISTRY["transformer"], "build")
