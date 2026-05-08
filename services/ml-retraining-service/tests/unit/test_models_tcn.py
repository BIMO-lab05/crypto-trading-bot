"""Unit tests for app.core.models.tcn.build (CD-01)."""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")
pytest.importorskip(
    "tensorflow",
    reason="tensorflow not installed in this environment",
)

from app.core.models import tcn  # noqa: E402  (after importorskip)


_BASE_HP = {
    "units": [32],
    "dropout": 0.1,
    "lr": 0.001,
    "horizon": 5,
    "kernel_size": 3,
    "dilation_base": 2,
    "n_blocks": 3,
}


def test_build_returns_compiled_keras_model():
    model = tcn.build(input_shape=(60, 17), hp=_BASE_HP)
    assert model.output_shape == (None, 5)
    assert model.optimizer.learning_rate.numpy() == pytest.approx(0.001)
    assert model.loss == "mse"


def test_build_rejects_missing_keys():
    with pytest.raises(ValueError, match="missing required keys"):
        tcn.build(input_shape=(60, 17), hp={"units": [32], "dropout": 0.1})


def test_build_rejects_invalid_kernel_size():
    bad = dict(_BASE_HP, kernel_size=10)
    with pytest.raises(ValueError, match="kernel_size"):
        tcn.build(input_shape=(60, 17), hp=bad)


def test_build_rejects_invalid_dilation_base():
    bad = dict(_BASE_HP, dilation_base=4)
    with pytest.raises(ValueError, match="dilation_base"):
        tcn.build(input_shape=(60, 17), hp=bad)


def test_registry_contains_tcn():
    from app.core.models import REGISTRY

    assert "tcn" in REGISTRY
    assert hasattr(REGISTRY["tcn"], "build")
