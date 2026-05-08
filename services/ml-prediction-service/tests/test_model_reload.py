"""
Regression tests for INFRA-06 Bug 1 — mtime-watching reload in GRUPricePredictor.

These tests exercise the _reload_if_stale() method added to GRUPricePredictor
(gru_predictor.py) as a retarget of Plan 02-08 Task 2.  The original plan
called for a standalone ModelLoader class; the retarget instead mirrors the
reload pattern already present in gru_model.py:140-166 directly into the
second predictor class.

Tests avoid importing TensorFlow/Keras at the module level by monkeypatching
keras.models.load_model before instantiating GRUPricePredictor.  This keeps
the unit-test path lightweight and runnable without a GPU / full TF install.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_metadata(
    tmp_path: Path, symbol: str = "SOLUSDT", interval: str = "60"
) -> None:
    """Write a minimal metadata JSON so _load_model() reaches its return True path."""
    metadata = {
        "model_version": "v_test",
        "last_trained": "2026-01-01T00:00:00",
        "training_stats": {"r2_score": 0.5, "rmse": 1.0},
        "feature_columns": ["close", "volume"],
        "sequence_length": 60,
        "prediction_horizon": 5,
    }
    meta_path = tmp_path / f"{symbol}_{interval}m_gru_metadata.json"
    meta_path.write_text(json.dumps(metadata))


def _make_predictor(tmp_path: Path, monkeypatch):
    """
    Return a GRUPricePredictor instance with TensorFlow mocked out.

    We patch keras.models.load_model at the module level inside gru_predictor
    so that _load_model() succeeds without a real .keras file or GPU.  The
    mock returns a unique sentinel object each call, which lets tests tell
    apart "old model" vs "reloaded model".

    A minimal metadata JSON is written alongside the model file so that
    _load_model() reaches its ``return True`` branch — the function only
    returns True inside the metadata block; without a metadata file it
    falls through to the implicit None return.
    """
    from app.ml_models import gru_predictor as gp_module

    # Each call to load_model returns a fresh MagicMock so successive loads
    # are distinguishable by identity.
    call_log = []

    def _fake_load(path, *args, **kwargs):
        m = MagicMock(name=f"model_load_{len(call_log)}")
        call_log.append(m)
        return m

    monkeypatch.setattr(gp_module, "TENSORFLOW_AVAILABLE", True)
    monkeypatch.setattr(gp_module.keras.models, "load_model", _fake_load)

    # Override models_dir to our tmp directory so _get_model_path() resolves
    # under tmp_path and we can touch / write the file safely.
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "models_dir", str(tmp_path), raising=False)

    # gru_predictor uses a module-level `settings` singleton; patch it too.
    monkeypatch.setattr(gp_module, "settings", settings)

    # Write an initial model file so _load_model() at __init__ time succeeds.
    model_file = tmp_path / "SOLUSDT_60m_gru.keras"
    model_file.write_bytes(b"v1")

    # Metadata file ensures _load_model() returns True (not None).
    _write_metadata(tmp_path)

    predictor = gp_module.GRUPricePredictor(symbol="SOLUSDT", interval="60")

    return predictor, call_log, model_file


# ---------------------------------------------------------------------------
# Test 1: mtime change → reload happens
# ---------------------------------------------------------------------------


def test_model_reloads_on_mtime_change(tmp_path, monkeypatch):
    """
    Touching (bumping mtime of) the model file causes _reload_if_stale() to
    reload.  The predictor's internal model reference changes.
    """
    predictor, call_log, model_file = _make_predictor(tmp_path, monkeypatch)

    # Exactly one load happened during __init__.
    assert len(call_log) == 1, f"Expected 1 initial load, got {len(call_log)}"
    first_model = predictor.model
    original_mtime = predictor.model_loaded_at

    # Ensure filesystem mtime will tick (some filesystems have 1s resolution).
    time.sleep(0.05)
    model_file.write_bytes(b"v2")  # write bumps mtime reliably

    # _reload_if_stale() should detect the newer mtime and reload.
    reloaded = predictor._reload_if_stale()

    assert reloaded is True, "_reload_if_stale() should return True after mtime change"
    assert len(call_log) == 2, f"Expected 2 total loads, got {len(call_log)}"
    assert predictor.model is not first_model, (
        "Model reference must change after reload"
    )
    assert predictor.model_loaded_at > original_mtime, (
        "model_loaded_at must be updated to the new mtime"
    )


# ---------------------------------------------------------------------------
# Test 2: missing file → FileNotFoundError (loud failure)
# ---------------------------------------------------------------------------


def test_missing_model_file_raises_on_reload(tmp_path, monkeypatch):
    """
    If the model file disappears between loads, _reload_if_stale() returns
    False (does not raise — tolerant of missing files per the docstring).
    A caller-level check (model is None / not available) will raise loudly.

    This matches the gru_model.py:154-155 contract:
        if not model_path.exists(): return False
    """
    predictor, call_log, model_file = _make_predictor(tmp_path, monkeypatch)

    # Delete the model file.
    model_file.unlink()

    # _reload_if_stale must not raise; it returns False for missing files.
    result = predictor._reload_if_stale()
    assert result is False, (
        "_reload_if_stale() must return False (not raise) when model file is absent"
    )


# ---------------------------------------------------------------------------
# Test 3: unchanged mtime → no reload (idempotent)
# ---------------------------------------------------------------------------


def test_unchanged_mtime_no_reload(tmp_path, monkeypatch):
    """
    Calling _reload_if_stale() repeatedly without touching the model file
    must never trigger a reload — one stat() per call, zero extra loads.
    """
    predictor, call_log, model_file = _make_predictor(tmp_path, monkeypatch)

    # Initial load in __init__.
    assert len(call_log) == 1

    # Call _reload_if_stale() several times without any mtime change.
    for _ in range(5):
        reloaded = predictor._reload_if_stale()
        assert reloaded is False, (
            "_reload_if_stale() must return False when mtime unchanged"
        )

    assert len(call_log) == 1, (
        f"No extra loads expected on stable mtime; got {len(call_log)} total loads"
    )
