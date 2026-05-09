"""
Pytest configuration and shared fixtures for ml-retraining-service tests.

Two structural quirks of the production code force us to do early stubbing
before importing ``app.main``:

1. ``app/core/scheduler.py`` (line ~18) imports ``JobStatus, TriggerType``
   from ``app.database.models`` — those names do not exist in the model
   module (only ``ModelStatus`` and ``RetrainingStatus``). Importing
   ``app.main`` therefore raises ImportError at collection time. Per the
   "do not refactor production code in a test-only commit" constraint,
   we stub the scheduler module out via ``sys.modules`` *before* main is
   imported. See the commit body for the deferred fix.

2. ``ModelDeployer.__init__`` calls ``mkdir(parents=True, exist_ok=True)``
   on absolute paths under ``/models/...``. Tests that instantiate the
   deployer must redirect those paths to ``tmp_path`` first — see the
   ``deployer_factory`` fixture.
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Module-import shims (must run before any ``from app.main import app``)
# ---------------------------------------------------------------------------

def _install_scheduler_stub() -> None:
    """Replace ``app.core.scheduler`` with a no-op stub.

    The real module fails to import because of the missing
    ``JobStatus``/``TriggerType`` names. We register a substitute in
    ``sys.modules`` so ``main.py`` can ``from app.core.scheduler import …``
    without crashing.
    """
    if "app.core.scheduler" in sys.modules:
        return

    stub = types.ModuleType("app.core.scheduler")

    fake_scheduler = MagicMock()
    fake_scheduler.is_scheduler_running = MagicMock(return_value=False)
    fake_scheduler.get_scheduled_jobs = MagicMock(return_value=[])
    fake_scheduler.get_running_jobs = MagicMock(return_value=[])
    fake_scheduler.trigger_manual_retrain = AsyncMock(
        return_value={"results": {}}
    )
    fake_scheduler.pause_scheduled_jobs = AsyncMock(return_value=None)
    fake_scheduler.resume_scheduled_jobs = AsyncMock(return_value=None)

    stub.start_scheduler = AsyncMock(return_value=None)
    stub.stop_scheduler = AsyncMock(return_value=None)
    stub.get_scheduler = AsyncMock(return_value=fake_scheduler)
    stub._fake_scheduler = fake_scheduler  # exposed for tests that want to assert

    sys.modules["app.core.scheduler"] = stub


_install_scheduler_stub()


# Make the service root importable as ``app.*`` regardless of cwd
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_db_session():
    """An ``AsyncMock`` standing in for an ``AsyncSession``.

    Tests can override ``db.execute(...).scalars().all()`` etc. as needed.
    Default ``execute`` returns a result whose ``scalars().all()`` is ``[]``
    and ``scalar_one_or_none()`` is ``None``.
    """
    session = AsyncMock()

    default_result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = []
    default_result.scalars.return_value = scalars
    default_result.scalar_one_or_none.return_value = None
    session.execute.return_value = default_result
    session.commit = AsyncMock(return_value=None)
    session.refresh = AsyncMock(return_value=None)
    session.add = MagicMock()

    return session


@pytest.fixture
def test_client(fake_db_session):
    """FastAPI ``TestClient`` with ``get_db`` overridden to a mock session.

    Note: starlette's ``TestClient`` does not run ``lifespan`` unless used as
    a context manager, so we don't need to stub ``init_db`` here.
    """
    from fastapi.testclient import TestClient

    from app.database.database import get_db
    from app.main import app

    async def _override_get_db():
        yield fake_db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        # Plain ``TestClient(app)`` (not used as a context manager) does
        # not trigger starlette ``lifespan`` events. That's what we want
        # here — lifespan would call ``init_db`` against a real DB.
        client = TestClient(app)
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Filesystem helpers for ModelDeployer
# ---------------------------------------------------------------------------

@pytest.fixture
def deployer_factory(tmp_path, monkeypatch):
    """Build a ``ModelDeployer`` whose dirs live under ``tmp_path``.

    ``ModelDeployer.__init__`` insists on creating ``/models/staging``,
    ``/models/production``, and ``/models/backups``. We patch the ``Path``
    references at the class level *before* ``__init__`` runs so tests can
    safely instantiate the deployer in CI sandboxes.
    """

    def _factory():
        from app.core import model_deployer as md_mod

        staging = tmp_path / "staging"
        production = tmp_path / "production"
        backups = tmp_path / "backups"
        for d in (staging, production, backups):
            d.mkdir(parents=True, exist_ok=True)

        deployer = md_mod.ModelDeployer.__new__(md_mod.ModelDeployer)
        deployer.settings = MagicMock()
        deployer.settings.ml_prediction_url = "http://ml-prediction.test"
        deployer.staging_dir = staging
        deployer.production_dir = production
        deployer.backup_dir = backups
        return deployer

    return _factory


# ---------------------------------------------------------------------------
# Synthetic OHLCV data for ModelTrainer feature engineering
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_ohlcv():
    """A small but valid OHLCV DataFrame for feature-engineering tests."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(42)
    n = 200
    base = 100 + np.cumsum(rng.normal(0, 1, n))
    high = base + np.abs(rng.normal(0, 0.5, n))
    low = base - np.abs(rng.normal(0, 0.5, n))
    open_ = base + rng.normal(0, 0.2, n)
    close = base + rng.normal(0, 0.2, n)
    volume = np.abs(rng.normal(1000, 100, n))
    timestamps = pd.date_range("2024-01-01", periods=n, freq="60min")

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )
