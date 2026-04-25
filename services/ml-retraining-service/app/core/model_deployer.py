"""
Model Deployment System
Purpose: Automated deployment of trained models to production with backup and rollback
"""

import logging
import shutil
import json
import httpx
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class ModelDeployer:
    """
    Handles automated deployment of ML models to production

    Features:
    - Backup current production models before deployment
    - Deploy new models to ML prediction service
    - Update model metadata
    - Verify deployment success
    - Automatic rollback on failure
    - Deployment history tracking
    """

    def __init__(self):
        """Initialize model deployer"""
        self.settings = get_settings()

        # Deployment directories
        self.staging_dir = Path("/models/staging")  # Where new models are saved
        self.production_dir = Path("/models/production")  # Production directory
        self.backup_dir = Path("/models/backups")  # Backup directory

        # Create directories if they don't exist
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.production_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    async def deploy_model(
        self,
        symbol: str,
        model_path: str,
        metadata_path: str,
        scaler_x_path: str,
        scaler_y_path: str,
        version: str,
        backup_current: bool = True,
        verify_deployment: bool = True
    ) -> Dict[str, Any]:
        """
        Deploy trained model to production

        Args:
            symbol: Trading symbol
            model_path: Path to trained model file
            metadata_path: Path to model metadata JSON
            scaler_x_path: Path to X scaler pickle
            scaler_y_path: Path to Y scaler pickle
            version: Model version identifier
            backup_current: Whether to backup current production model
            verify_deployment: Whether to verify after deployment

        Returns:
            Dict with deployment results
        """
        logger.info(f"Starting deployment for {symbol} version {version}")

        deployment_result = {
            "symbol": symbol,
            "version": version,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "backup_created": False,
            "files_deployed": [],
            "verification_passed": False,
            "error": None
        }

        try:
            # Step 1: Backup current production model
            if backup_current:
                backup_result = await self._backup_production_model(symbol)
                deployment_result["backup_created"] = backup_result["success"]
                deployment_result["backup_path"] = backup_result.get("backup_path")

                if not backup_result["success"]:
                    raise Exception(f"Backup failed: {backup_result.get('error')}")

            # Step 2: Copy model files to production directory
            files_deployed = await self._copy_model_files(
                symbol=symbol,
                model_path=model_path,
                metadata_path=metadata_path,
                scaler_x_path=scaler_x_path,
                scaler_y_path=scaler_y_path
            )
            deployment_result["files_deployed"] = files_deployed

            # Step 3: Update deployment metadata
            await self._update_deployment_metadata(symbol, version, files_deployed)

            # Step 4: Reload ML prediction service (hot reload)
            reload_result = await self._reload_prediction_service(symbol)
            deployment_result["reload_success"] = reload_result["success"]

            # Step 5: Verify deployment
            if verify_deployment:
                verification_result = await self._verify_deployment(symbol)
                deployment_result["verification_passed"] = verification_result["success"]
                deployment_result["verification_details"] = verification_result

                if not verification_result["success"]:
                    # Rollback on verification failure
                    logger.error(f"Verification failed for {symbol}, initiating rollback")
                    rollback_result = await self.rollback_deployment(symbol)
                    deployment_result["rollback_performed"] = True
                    deployment_result["rollback_result"] = rollback_result
                    raise Exception(f"Verification failed: {verification_result.get('error')}")

            deployment_result["success"] = True
            logger.info(f"✅ Deployment successful for {symbol} version {version}")

        except Exception as e:
            logger.error(f"❌ Deployment failed for {symbol}: {e}", exc_info=True)
            deployment_result["error"] = str(e)
            deployment_result["success"] = False

        return deployment_result

    async def _backup_production_model(self, symbol: str) -> Dict[str, Any]:
        """
        Backup current production model

        Args:
            symbol: Trading symbol

        Returns:
            Dict with backup results
        """
        logger.info(f"Backing up production model for {symbol}")

        try:
            # Create timestamped backup directory
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.backup_dir / f"{symbol}_{timestamp}"
            backup_path.mkdir(parents=True, exist_ok=True)

            # Files to backup
            interval = "60"  # Default interval
            files_to_backup = [
                f"{symbol}_{interval}m_gru.keras",
                f"{symbol}_{interval}m_gru_metadata.json",
                f"{symbol}_{interval}m_gru_scalers.pkl"
            ]

            backed_up_files = []

            for filename in files_to_backup:
                source = self.production_dir / filename

                if source.exists():
                    dest = backup_path / filename
                    shutil.copy2(str(source), str(dest))
                    backed_up_files.append(filename)
                    logger.debug(f"Backed up: {filename}")

            if not backed_up_files:
                logger.warning(f"No production model found to backup for {symbol}")

            return {
                "success": True,
                "backup_path": str(backup_path),
                "files_backed_up": backed_up_files,
                "count": len(backed_up_files)
            }

        except Exception as e:
            logger.error(f"Error backing up model for {symbol}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _copy_model_files(
        self,
        symbol: str,
        model_path: str,
        metadata_path: str,
        scaler_x_path: str,
        scaler_y_path: str
    ) -> list:
        """
        Copy model files from staging to production

        Args:
            symbol: Trading symbol
            model_path: Source model file path
            metadata_path: Source metadata file path
            scaler_x_path: Source X scaler path
            scaler_y_path: Source Y scaler path

        Returns:
            List of deployed file names
        """
        logger.info(f"Copying model files to production for {symbol}")

        interval = "60"  # Default interval
        deployed_files = []

        # File mappings: source -> destination
        file_mappings = {
            model_path: self.production_dir / f"{symbol}_{interval}m_gru.keras",
            metadata_path: self.production_dir / f"{symbol}_{interval}m_gru_metadata.json"
        }

        # Combine scalers into single pickle file for ML prediction service
        # Note: ML prediction service expects a single scalers.pkl file
        # We'll need to merge scaler_x and scaler_y
        if Path(scaler_x_path).exists() and Path(scaler_y_path).exists():
            # For now, copy scaler_x as the scalers file
            # TODO: Merge both scalers into a single file
            file_mappings[scaler_x_path] = self.production_dir / f"{symbol}_{interval}m_gru_scalers.pkl"

        # Copy files
        for source, dest in file_mappings.items():
            source_path = Path(source)

            if not source_path.exists():
                logger.warning(f"Source file not found: {source}")
                continue

            try:
                shutil.copy2(str(source_path), str(dest))
                deployed_files.append(dest.name)
                logger.info(f"Copied: {source_path.name} -> {dest.name}")
            except Exception as e:
                logger.error(f"Error copying {source_path.name}: {e}")
                raise

        return deployed_files

    async def _update_deployment_metadata(
        self,
        symbol: str,
        version: str,
        files_deployed: list
    ):
        """
        Update deployment metadata file

        Args:
            symbol: Trading symbol
            version: Model version
            files_deployed: List of deployed files
        """
        metadata_file = self.production_dir / f"{symbol}_deployment.json"

        deployment_info = {
            "symbol": symbol,
            "version": version,
            "deployed_at": datetime.now().isoformat(),
            "files": files_deployed,
            "deployer": "ml-retraining-service"
        }

        try:
            with open(metadata_file, 'w') as f:
                json.dump(deployment_info, f, indent=2)
            logger.info(f"Updated deployment metadata: {metadata_file}")
        except Exception as e:
            logger.error(f"Error updating deployment metadata: {e}")
            # Non-critical, don't raise

    async def _reload_prediction_service(self, symbol: str) -> Dict[str, Any]:
        """
        Reload ML prediction service to load new model

        This can be done via:
        1. Hot reload API endpoint (if available)
        2. Service restart (via docker restart)
        3. Model cache invalidation

        Args:
            symbol: Trading symbol

        Returns:
            Dict with reload results
        """
        logger.info(f"Reloading prediction service for {symbol}")

        try:
            # Option 1: Try hot reload via API
            ml_prediction_url = self.settings.ml_prediction_url
            reload_endpoint = f"{ml_prediction_url}/api/v1/models/reload/{symbol}"

            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    response = await client.post(reload_endpoint)

                    if response.status_code == 200:
                        logger.info(f"✅ Hot reload successful for {symbol}")
                        return {
                            "success": True,
                            "method": "hot_reload",
                            "response": response.json()
                        }
                except httpx.HTTPError as e:
                    logger.warning(f"Hot reload API not available: {e}")

            # Option 2: Model will be loaded on next prediction request
            # ML prediction service loads models lazily
            logger.info(f"Model will be loaded on next prediction request for {symbol}")

            return {
                "success": True,
                "method": "lazy_load",
                "message": "Model will be loaded on next prediction"
            }

        except Exception as e:
            logger.error(f"Error reloading prediction service: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _verify_deployment(self, symbol: str) -> Dict[str, Any]:
        """
        Verify that deployed model is working correctly

        Tests:
        1. Model files exist in production
        2. Model can be loaded
        3. Test prediction works

        Args:
            symbol: Trading symbol

        Returns:
            Dict with verification results
        """
        logger.info(f"Verifying deployment for {symbol}")

        verification_results = {
            "success": False,
            "checks": {}
        }

        try:
            interval = "60"

            # Check 1: Files exist
            required_files = [
                f"{symbol}_{interval}m_gru.keras",
                f"{symbol}_{interval}m_gru_metadata.json",
                f"{symbol}_{interval}m_gru_scalers.pkl"
            ]

            files_exist = all(
                (self.production_dir / filename).exists()
                for filename in required_files
            )
            verification_results["checks"]["files_exist"] = files_exist

            if not files_exist:
                verification_results["error"] = "Required model files not found in production"
                return verification_results

            # Check 2: Test prediction via ML prediction service
            ml_prediction_url = self.settings.ml_prediction_url
            predict_endpoint = f"{ml_prediction_url}/api/v1/predict/{symbol}/gru"

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(predict_endpoint)

                prediction_works = response.status_code == 200
                verification_results["checks"]["prediction_works"] = prediction_works

                if prediction_works:
                    prediction_data = response.json()
                    verification_results["checks"]["prediction_data"] = {
                        "has_prediction": "prediction" in prediction_data,
                        "has_confidence": "confidence" in prediction_data
                    }

            # Overall verification success
            verification_results["success"] = all(
                check for check in verification_results["checks"].values()
                if isinstance(check, bool)
            )

            if verification_results["success"]:
                logger.info(f"✅ Verification passed for {symbol}")
            else:
                logger.warning(f"⚠️ Verification failed for {symbol}")

        except Exception as e:
            logger.error(f"Error during verification: {e}", exc_info=True)
            verification_results["error"] = str(e)
            verification_results["success"] = False

        return verification_results

    async def rollback_deployment(self, symbol: str) -> Dict[str, Any]:
        """
        Rollback to previous production model

        Args:
            symbol: Trading symbol

        Returns:
            Dict with rollback results
        """
        logger.info(f"Rolling back deployment for {symbol}")

        try:
            # Find most recent backup
            backups = sorted(
                [d for d in self.backup_dir.iterdir() if d.is_dir() and d.name.startswith(symbol)],
                key=lambda x: x.name,
                reverse=True
            )

            if not backups:
                return {
                    "success": False,
                    "error": f"No backup found for {symbol}"
                }

            latest_backup = backups[0]
            logger.info(f"Restoring from backup: {latest_backup}")

            # Copy backup files to production
            restored_files = []
            for backup_file in latest_backup.iterdir():
                if backup_file.is_file():
                    dest = self.production_dir / backup_file.name
                    shutil.copy2(str(backup_file), str(dest))
                    restored_files.append(backup_file.name)
                    logger.info(f"Restored: {backup_file.name}")

            # Reload service
            reload_result = await self._reload_prediction_service(symbol)

            return {
                "success": True,
                "backup_restored": str(latest_backup),
                "files_restored": restored_files,
                "reload_result": reload_result
            }

        except Exception as e:
            logger.error(f"Error during rollback: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    def list_backups(self, symbol: Optional[str] = None) -> list:
        """
        List available backups

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            List of backup directories
        """
        try:
            backups = []

            for backup_dir in self.backup_dir.iterdir():
                if not backup_dir.is_dir():
                    continue

                # Filter by symbol if provided
                if symbol and not backup_dir.name.startswith(symbol):
                    continue

                # Extract backup info
                parts = backup_dir.name.split('_')
                if len(parts) >= 3:
                    backup_symbol = parts[0]
                    backup_timestamp = '_'.join(parts[1:])

                    backups.append({
                        "symbol": backup_symbol,
                        "timestamp": backup_timestamp,
                        "path": str(backup_dir),
                        "files": [f.name for f in backup_dir.iterdir() if f.is_file()]
                    })

            return sorted(backups, key=lambda x: x["timestamp"], reverse=True)

        except Exception as e:
            logger.error(f"Error listing backups: {e}")
            return []
