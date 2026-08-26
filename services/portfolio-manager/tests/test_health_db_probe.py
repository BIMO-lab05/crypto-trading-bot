"""
Regression tests for the /health and /ready database probes.

Covers QUICK-260826-NZW: /health `database_connection` and /ready `database`
must derive from a live SELECT 1 against the service's own asyncpg pool
(`app.main.db_pool`), with the legacy `shared.database.connection` import
demoted to a pool-is-None fallback, and the `use_database=False` paths
byte-identical to prior behavior.

Host-run. TestClient is used WITHOUT a context manager so lifespan never
runs and `app.main` globals stay None unless patched. No balance literals
in fixtures (testing.md rule) — these tests carry no money values at all.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

from fastapi.testclient import TestClient

from app.main import app

_LEGACY_IMPORT_BLOCKED = {
    "shared": None,
    "shared.database": None,
    "shared.database.connection": None,
}


def make_fake_pool(fetchval_side_effect=None):
    """Build a MagicMock asyncpg-shaped pool.

    Mirrors asyncpg's acquire-as-async-context-manager: `pool.acquire()`
    returns an object implementing __aenter__/__aexit__ as AsyncMocks,
    with __aenter__ yielding a connection whose `fetchval` is an
    AsyncMock returning 1 (or raising `fetchval_side_effect`).
    """
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=1)
    if fetchval_side_effect is not None:
        conn.fetchval = AsyncMock(side_effect=fetchval_side_effect)

    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=acquire_cm)
    return pool, conn


def _patched_settings(mock_settings, use_database):
    mock_settings.trading_engine_url = "http://trading-engine:8005"
    mock_settings.market_data_url = "http://market-data:8002"
    mock_settings.use_database = use_database


class TestHealthDbProbe:
    """GET /health `database_connection` via the live pool probe."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_health_pool_ok_reports_true(self):
        """Test 1: healthy pool -> database_connection true, SELECT 1 awaited."""
        pool, conn = make_fake_pool()
        with (
            patch(
                "app.handlers.health.check_service_health",
                AsyncMock(return_value=True),
            ),
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.db_pool", pool),
        ):
            _patched_settings(mock_settings, use_database=True)
            response = self.client.get("/health")

        assert response.status_code == 200
        assert response.json()["database_connection"] is True
        conn.fetchval.assert_awaited_once_with("SELECT 1")

    def test_health_probe_raises_reports_false(self):
        """Test 2: probe raises -> database_connection false, no 500."""
        pool, _conn = make_fake_pool(fetchval_side_effect=Exception("connection lost"))
        with (
            patch(
                "app.handlers.health.check_service_health",
                AsyncMock(return_value=True),
            ),
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.db_pool", pool),
        ):
            _patched_settings(mock_settings, use_database=True)
            response = self.client.get("/health")

        assert response.status_code == 200
        assert response.json()["database_connection"] is False

    def test_health_pool_none_and_import_fails_reports_false(self):
        """Test 3: pool None + legacy import blocked -> false, no crash."""
        with (
            patch(
                "app.handlers.health.check_service_health",
                AsyncMock(return_value=True),
            ),
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.db_pool", None),
            patch.dict("sys.modules", _LEGACY_IMPORT_BLOCKED),
        ):
            _patched_settings(mock_settings, use_database=True)
            response = self.client.get("/health")

        assert response.status_code == 200
        assert response.json()["database_connection"] is False

    def test_health_use_database_false_never_probes(self):
        """Test 4: use_database False -> false, pool never touched."""
        pool, _conn = make_fake_pool()
        with (
            patch(
                "app.handlers.health.check_service_health",
                AsyncMock(return_value=True),
            ),
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.db_pool", pool),
        ):
            _patched_settings(mock_settings, use_database=False)
            response = self.client.get("/health")

        assert response.status_code == 200
        assert response.json()["database_connection"] is False
        pool.acquire.assert_not_called()


class TestReadinessDbProbe:
    """GET /ready `database` via the live pool probe."""

    def setup_method(self):
        self.client = TestClient(app)

    def test_ready_pool_ok_reports_ok(self):
        """Test 5: healthy pool -> 200 with database: ok."""
        pool, _conn = make_fake_pool()
        with (
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.portfolio_manager", Mock()),
            patch("app.main.db_pool", pool),
        ):
            _patched_settings(mock_settings, use_database=True)
            response = self.client.get("/ready")

        assert response.status_code == 200
        assert response.json()["database"] == "ok"

    def test_ready_probe_fails_returns_503(self):
        """Test 6: probe raises -> 503."""
        pool, _conn = make_fake_pool(fetchval_side_effect=Exception("connection lost"))
        with (
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.portfolio_manager", Mock()),
            patch("app.main.db_pool", pool),
        ):
            _patched_settings(mock_settings, use_database=True)
            response = self.client.get("/ready")

        assert response.status_code == 503

    def test_ready_use_database_false_skips(self):
        """Test 7: use_database False -> 200 with database: skipped."""
        with (
            patch("app.handlers.health.settings") as mock_settings,
            patch("app.main.portfolio_manager", Mock()),
        ):
            _patched_settings(mock_settings, use_database=False)
            response = self.client.get("/ready")

        assert response.status_code == 200
        assert response.json()["database"] == "skipped"
