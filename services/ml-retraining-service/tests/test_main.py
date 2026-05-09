"""
Smoke tests for the ml-retraining-service FastAPI surface.

Goal: every documented endpoint returns *something* (success path or
graceful 5xx) when its dependencies are mocked. We are not asserting
business logic here — just that routing, dependency injection, and
deferred imports survive the call.

External deps mocked:
- DB session via the ``get_db`` dependency override (see ``conftest.py``).
- ``DataCollector`` / ``ModelTrainer`` / ``ModelValidator`` / ``ModelDeployer``
  via ``unittest.mock.patch`` at the import site inside each endpoint
  (most are imported lazily inside the route function).
- The ``app.core.scheduler`` module is stubbed in ``conftest.py`` before
  ``app.main`` is loaded.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealthEndpoints:
    def test_health(self, test_client):
        response = test_client.get("/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "healthy"
        assert body["service"] == "ml-retraining-service"
        assert "version" in body
        assert "timestamp" in body

    def test_detailed_health(self, test_client):
        with patch("app.main.check_db_connection", new=AsyncMock(return_value=True)):
            response = test_client.get("/health/detailed")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"healthy", "degraded"}
        assert "running_jobs" in body


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

class TestDataCollectionEndpoints:
    def test_collect_symbol_data(self, test_client):
        fake_collector = MagicMock()
        fake_collector.collect_training_data = AsyncMock(
            return_value={
                "success": True,
                "data": MagicMock(__len__=lambda self: 500),
                "metrics": {"rows": 500, "missing": 0},
                "errors": [],
            }
        )
        fake_collector.close = AsyncMock(return_value=None)

        with patch("app.main.DataCollector", return_value=fake_collector):
            response = test_client.post("/api/v1/data/collect/SOLUSDT?interval=60&days=30")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["symbol"] == "SOLUSDT"
        fake_collector.close.assert_awaited()

    def test_collect_all_data(self, test_client):
        fake_collector = MagicMock()
        fake_collector.collect_all_symbols = AsyncMock(
            return_value={
                "SOLUSDT": {
                    "success": True,
                    "data": MagicMock(__len__=lambda self: 100),
                    "metrics": {},
                    "errors": [],
                }
            }
        )
        fake_collector.close = AsyncMock(return_value=None)

        with patch("app.main.DataCollector", return_value=fake_collector):
            response = test_client.post(
                "/api/v1/data/collect-all?interval=60&symbols=SOLUSDT"
            )

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["symbols_requested"] == 1


# ---------------------------------------------------------------------------
# Model versions / jobs / status
# ---------------------------------------------------------------------------

class TestModelVersionEndpoints:
    def test_list_versions_empty(self, test_client):
        # default fake_db_session returns empty list
        response = test_client.get("/api/v1/models/versions")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["count"] == 0
        assert body["versions"] == []

    def test_get_version_not_found(self, test_client):
        response = test_client.get("/api/v1/models/versions/999")
        assert response.status_code == 404

    def test_list_production_models_empty(self, test_client):
        response = test_client.get("/api/v1/models/production")
        assert response.status_code == 200
        assert response.json()["count"] == 0


class TestRetrainingJobEndpoints:
    def test_list_jobs_empty(self, test_client):
        response = test_client.get("/api/v1/jobs")
        assert response.status_code == 200
        assert response.json()["count"] == 0

    def test_get_job_not_found(self, test_client):
        response = test_client.get("/api/v1/jobs/nonexistent_job_id")
        assert response.status_code == 404


class TestStatusEndpoint:
    def test_service_status(self, test_client):
        response = test_client.get("/api/v1/status")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["service"] == "ml-retraining-service"
        assert "job_statistics" in body
        assert "model_statistics" in body
        assert "configuration" in body


# ---------------------------------------------------------------------------
# Deployment management
# ---------------------------------------------------------------------------

class TestDeploymentEndpoints:
    def test_deploy_version_not_found(self, test_client):
        # default fake DB returns scalar_one_or_none() == None
        response = test_client.post("/api/v1/deploy/123?backup_current=false")
        assert response.status_code == 404

    def test_rollback_success(self, test_client):
        fake_deployer = MagicMock()
        fake_deployer.rollback_deployment = AsyncMock(
            return_value={"success": True, "files_restored": ["x.keras"]}
        )
        with patch("app.main.ModelDeployer", return_value=fake_deployer):
            response = test_client.post("/api/v1/deploy/rollback/SOLUSDT")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_list_backups(self, test_client):
        fake_deployer = MagicMock()
        fake_deployer.list_backups.return_value = []
        with patch("app.main.ModelDeployer", return_value=fake_deployer):
            response = test_client.get("/api/v1/deploy/backups")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["count"] == 0

    def test_deployment_status_no_model(self, test_client):
        # fake_db returns scalar_one_or_none() == None → deployed=False branch
        response = test_client.get("/api/v1/deploy/status/SOLUSDT")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["deployed"] is False


# ---------------------------------------------------------------------------
# Scheduler management (scheduler module is stubbed in conftest.py)
# ---------------------------------------------------------------------------

class TestSchedulerEndpoints:
    def test_scheduler_status(self, test_client):
        response = test_client.get("/api/v1/scheduler/status")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["scheduler_running"] is False

    def test_scheduler_pause(self, test_client):
        response = test_client.post("/api/v1/scheduler/pause")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_scheduler_resume(self, test_client):
        response = test_client.post("/api/v1/scheduler/resume")
        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_scheduler_next_runs(self, test_client):
        response = test_client.get("/api/v1/scheduler/next-runs")
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["total_jobs"] == 0

    def test_scheduler_trigger_invalid_symbol(self, test_client):
        # Non-configured symbol → 400 from the validate-symbols branch
        response = test_client.post(
            "/api/v1/scheduler/trigger?symbols=NOTASYMBOL"
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# CORS / 404
# ---------------------------------------------------------------------------

class TestRoutingBasics:
    def test_unknown_route_returns_404(self, test_client):
        response = test_client.get("/api/v1/this/does/not/exist")
        assert response.status_code == 404

    def test_cors_preflight_health(self, test_client):
        response = test_client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORSMiddleware accepts the preflight
        assert response.status_code in {200, 204}


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
