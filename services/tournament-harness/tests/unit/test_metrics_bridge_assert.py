"""Unit tests for metrics_bridge.assert_canonical_metrics_available (INT-02).

The assertion is the fail-fast guard called from FastAPI lifespan and from the
runner CLI entrypoint. It must:
  - return None when the canonical chain imported successfully (container path);
  - raise RuntimeError with TOURN-07 + INT-02 references when the chain failed
    to import (host pytest path with split `app` namespaces, or a regression
    where Dockerfile PYTHONPATH wiring breaks).

These tests exercise both branches by monkey-patching the module-level flag
rather than the import system itself, since the import attempt happens at
module load time and cannot be cleanly redone.
"""

from __future__ import annotations

import pytest

from app.runner import metrics_bridge


def test_assert_canonical_metrics_returns_none_when_available(monkeypatch):
    """Container path: chain imported, helper is a no-op."""
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_AVAILABLE", True)
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_IMPORT_ERROR", None)
    assert metrics_bridge.assert_canonical_metrics_available() is None


def test_assert_canonical_metrics_raises_when_unavailable(monkeypatch):
    """Container regression path: chain failed to import -> RuntimeError."""
    fake_err = ImportError("simulated PYTHONPATH break")
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_AVAILABLE", False)
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_IMPORT_ERROR", fake_err)
    with pytest.raises(RuntimeError) as exc_info:
        metrics_bridge.assert_canonical_metrics_available()

    msg = str(exc_info.value)
    assert "canonical metric chain unavailable" in msg
    assert "TOURN-07" in msg
    assert "INT-02" in msg
    assert "PYTHONPATH=/app:/opt/ml_retraining" in msg
    assert "simulated PYTHONPATH break" in msg


def test_assert_canonical_metrics_message_actionable(monkeypatch):
    """Error must name the env var to fix and the audit reference, not just say 'failed'."""
    fake_err = ModuleNotFoundError("no module named app.core.returns_metrics")
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_AVAILABLE", False)
    monkeypatch.setattr(metrics_bridge, "_CANONICAL_METRICS_IMPORT_ERROR", fake_err)
    with pytest.raises(RuntimeError) as exc_info:
        metrics_bridge.assert_canonical_metrics_available()

    msg = str(exc_info.value)
    # Operator must see exactly which import failed and where to fix it.
    assert "ModuleNotFoundError" in msg or "no module named app.core" in msg
    # Don't reimplement -- TOURN-07 contract.
    assert "forbids reimplementation" in msg
    # Pointer to the audit so the next reader knows the history.
    assert "v1.0 milestone audit INT-02" in msg
