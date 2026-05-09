"""
Tests for ``app.core.model_deployer.ModelDeployer``.

Focus: the retrained-model handoff fixed in commit ``ecdb29d``.

The ML prediction service loads scalers from a single
``{symbol}_{interval}m_gru_scalers.pkl`` file. Before ``ecdb29d`` this
side either copied ``.npy`` files or two split ``scaler_x.pkl`` /
``scaler_y.pkl`` files. The prediction service then fell through to a
"no scaler" branch and silently kept using the old in-memory scalers,
so retrained models never went live.

These tests pin the file mapping ``model_deployer._copy_model_files``
emits, the live-reload call, and the rollback path. Everything is
filesystem-mocked via the ``deployer_factory`` fixture in ``conftest.py``,
so no real ``/models/...`` is touched.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# sklearn is needed only to construct realistic pickled objects in the
# regression-hook test. Skip if missing instead of failing collection.
pytest.importorskip("sklearn")
pytest.importorskip("httpx")


# ---------------------------------------------------------------------------
# Module-level import fence — ``app.core.model_deployer`` doesn't pull in TF
# but does need ``app.config.settings`` (pydantic_settings).
# ---------------------------------------------------------------------------

pytest.importorskip("pydantic_settings")


# ---------------------------------------------------------------------------
# REGRESSION HOOK: scaler handoff (commit ecdb29d)
# ---------------------------------------------------------------------------

class TestScalerHandoffRegression:
    """The .pkl scaler contract — paired with TestSaveModelArtifactContract."""

    @pytest.mark.asyncio
    async def test_copy_model_files_maps_scalers_pkl_to_production(
        self, deployer_factory, tmp_path
    ):
        from sklearn.preprocessing import MinMaxScaler

        deployer = deployer_factory()

        # Build a realistic staged artifact set, including a combined
        # scalers.pkl exactly as ModelTrainer.save_model produces it.
        staged = tmp_path / "staged"
        staged.mkdir()
        model_path = staged / "model.h5"
        metadata_path = staged / "metadata.json"
        scalers_path = staged / "scalers.pkl"

        model_path.write_bytes(b"fake-keras-bytes")
        metadata_path.write_text(json.dumps({"version": "v-test"}))
        with open(scalers_path, "wb") as f:
            pickle.dump(
                {"price_scaler": MinMaxScaler(), "feature_scaler": MinMaxScaler()},
                f,
            )

        deployed = await deployer._copy_model_files(
            symbol="SOLUSDT",
            model_path=str(model_path),
            metadata_path=str(metadata_path),
            scalers_path=str(scalers_path),
        )

        # Each file lands at the prediction-service contract path.
        expected_names = {
            "SOLUSDT_60m_gru.keras",
            "SOLUSDT_60m_gru_metadata.json",
            "SOLUSDT_60m_gru_scalers.pkl",
        }
        assert set(deployed) == expected_names

        # Scalers were copied as a single .pkl, NOT .npy or split.
        prod = deployer.production_dir
        assert (prod / "SOLUSDT_60m_gru_scalers.pkl").exists(), (
            "ecdb29d regression: deployed scalers must be a single .pkl"
        )
        assert not (prod / "SOLUSDT_60m_gru_scalers.npy").exists()
        assert not (prod / "SOLUSDT_60m_gru_scaler_x.pkl").exists()
        assert not (prod / "SOLUSDT_60m_gru_scaler_y.pkl").exists()

        # The pickled dict survived the copy intact.
        with open(prod / "SOLUSDT_60m_gru_scalers.pkl", "rb") as f:
            payload = pickle.load(f)
        assert set(payload.keys()) == {"price_scaler", "feature_scaler"}

        # Atomic-rename leaves no stale .tmp staging files in production.
        leftover_tmp = list(prod.glob("*.tmp"))
        assert leftover_tmp == [], f"unexpected .tmp leftovers: {leftover_tmp}"

    @pytest.mark.asyncio
    async def test_copy_skips_missing_source_silently(
        self, deployer_factory, tmp_path
    ):
        deployer = deployer_factory()

        # Only model_path actually exists; the others are missing.
        staged = tmp_path / "staged2"
        staged.mkdir()
        real_model = staged / "model.h5"
        real_model.write_bytes(b"x")

        deployed = await deployer._copy_model_files(
            symbol="BNBUSDT",
            model_path=str(real_model),
            metadata_path=str(staged / "missing-metadata.json"),
            scalers_path=str(staged / "missing-scalers.pkl"),
        )

        assert "BNBUSDT_60m_gru.keras" in deployed
        # Missing sources skipped, not raised.
        assert "BNBUSDT_60m_gru_scalers.pkl" not in deployed


# ---------------------------------------------------------------------------
# Backup / rollback / list_backups
# ---------------------------------------------------------------------------

class TestBackupAndRollback:
    @pytest.mark.asyncio
    async def test_backup_with_no_existing_production_succeeds_empty(
        self, deployer_factory
    ):
        deployer = deployer_factory()
        result = await deployer._backup_production_model("SOLUSDT")

        assert result["success"] is True
        assert result["count"] == 0
        # Backup directory was still created.
        assert Path(result["backup_path"]).exists()

    @pytest.mark.asyncio
    async def test_backup_copies_existing_production_files(self, deployer_factory):
        deployer = deployer_factory()

        # Plant production files that match the deployment naming.
        for filename in (
            "SOLUSDT_60m_gru.keras",
            "SOLUSDT_60m_gru_metadata.json",
            "SOLUSDT_60m_gru_scalers.pkl",
        ):
            (deployer.production_dir / filename).write_bytes(b"x")

        result = await deployer._backup_production_model("SOLUSDT")

        assert result["success"] is True
        assert result["count"] == 3
        backup_dir = Path(result["backup_path"])
        assert (backup_dir / "SOLUSDT_60m_gru_scalers.pkl").exists()

    def test_list_backups_returns_sorted_metadata(self, deployer_factory):
        deployer = deployer_factory()

        b1 = deployer.backup_dir / "SOLUSDT_20260101_000000"
        b2 = deployer.backup_dir / "SOLUSDT_20260201_000000"
        for b in (b1, b2):
            b.mkdir()
            (b / "SOLUSDT_60m_gru.keras").write_bytes(b"x")

        backups = deployer.list_backups(symbol="SOLUSDT")
        assert len(backups) == 2
        # Sorted descending by timestamp
        assert backups[0]["timestamp"] >= backups[1]["timestamp"]

    @pytest.mark.asyncio
    async def test_rollback_with_no_backup_returns_error(self, deployer_factory):
        deployer = deployer_factory()
        # Stub the reload call so rollback doesn't try real HTTP.
        deployer._reload_prediction_service = AsyncMock(
            return_value={"success": True, "method": "lazy_load"}
        )

        result = await deployer.rollback_deployment("SOLUSDT")
        assert result["success"] is False
        assert "No backup" in result["error"]


# ---------------------------------------------------------------------------
# Live reload (httpx mocked)
# ---------------------------------------------------------------------------

class TestReloadPredictionService:
    @pytest.mark.asyncio
    async def test_hot_reload_success_returns_method_hot_reload(
        self, deployer_factory
    ):
        deployer = deployer_factory()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"reloaded": True})

        async_client = MagicMock()
        async_client.post = AsyncMock(return_value=mock_response)
        async_client.__aenter__ = AsyncMock(return_value=async_client)
        async_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.core.model_deployer.httpx.AsyncClient",
            return_value=async_client,
        ):
            result = await deployer._reload_prediction_service("SOLUSDT")

        assert result["success"] is True
        assert result["method"] == "hot_reload"
        async_client.post.assert_awaited()

    @pytest.mark.asyncio
    async def test_reload_falls_back_to_lazy_load_on_http_error(
        self, deployer_factory
    ):
        deployer = deployer_factory()

        import httpx

        async_client = MagicMock()
        async_client.post = AsyncMock(
            side_effect=httpx.ConnectError("ml-prediction down")
        )
        async_client.__aenter__ = AsyncMock(return_value=async_client)
        async_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "app.core.model_deployer.httpx.AsyncClient",
            return_value=async_client,
        ):
            result = await deployer._reload_prediction_service("SOLUSDT")

        # Falls through to "lazy_load" branch — still success=True.
        assert result["success"] is True
        assert result["method"] == "lazy_load"


# ---------------------------------------------------------------------------
# Update deployment metadata
# ---------------------------------------------------------------------------

class TestUpdateDeploymentMetadata:
    @pytest.mark.asyncio
    async def test_writes_deployment_json(self, deployer_factory):
        deployer = deployer_factory()

        await deployer._update_deployment_metadata(
            symbol="ADAUSDT",
            version="v-test",
            files_deployed=["ADAUSDT_60m_gru.keras"],
        )

        meta_file = deployer.production_dir / "ADAUSDT_deployment.json"
        assert meta_file.exists()
        body = json.loads(meta_file.read_text())
        assert body["symbol"] == "ADAUSDT"
        assert body["version"] == "v-test"
        assert body["deployer"] == "ml-retraining-service"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
