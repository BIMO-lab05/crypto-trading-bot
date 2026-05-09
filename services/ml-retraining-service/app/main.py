"""
ML Model Retraining Service - Main Application
Purpose: Automated GRU model retraining with validation and deployment
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import uvicorn

from app.config.settings import get_settings
from app.database.database import init_db, close_db, get_db, check_db_connection
from app.database.models import ModelVersion, RetrainingJob, ModelStatus, RetrainingStatus
from app.core.data_collector import DataCollector
from app.core.scheduler import start_scheduler, stop_scheduler, get_scheduler
from app.core.model_deployer import ModelDeployer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    # Startup
    logger.info("=" * 60)
    logger.info(f"Starting {settings.service_name} v{__import__('app').__version__}")
    logger.info("=" * 60)

    try:
        # Initialize database
        await init_db()
        logger.info("✅ Database initialized")

        # Check database connection
        db_healthy = await check_db_connection()
        if not db_healthy:
            logger.error("❌ Database connection check failed")
        else:
            logger.info("✅ Database connection healthy")

        # Start scheduler if enabled
        if settings.retrain_schedule_enabled:
            await start_scheduler()
            logger.info("✅ Retraining scheduler started")
        else:
            logger.info("⚠️  Retraining scheduler disabled (RETRAIN_SCHEDULE_ENABLED=false)")

        logger.info(f"🚀 Service ready on {settings.service_host}:{settings.service_port}")

    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise

    yield

    # Shutdown
    logger.info("Shutting down service...")

    # Stop scheduler
    if settings.retrain_schedule_enabled:
        await stop_scheduler()
        logger.info("✅ Scheduler stopped")

    await close_db()
    logger.info("✅ Service stopped")


# Create FastAPI app
app = FastAPI(
    title="ML Model Retraining Service",
    description="Automated GRU model retraining with validation and deployment",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """
    Service health check

    Returns basic service status
    """
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": __import__('app').__version__,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health/detailed", tags=["Health"])
async def detailed_health_check(db: AsyncSession = Depends(get_db)):
    """
    Detailed health check including database connection

    Returns comprehensive health status
    """
    # Check database
    db_healthy = await check_db_connection()

    # Get recent jobs count
    try:
        result = await db.execute(
            select(RetrainingJob)
            .filter(RetrainingJob.status == RetrainingStatus.RUNNING)
        )
        running_jobs = len(result.scalars().all())
    except Exception as e:
        logger.error(f"Error checking running jobs: {e}")
        running_jobs = -1

    return {
        "status": "healthy" if db_healthy else "degraded",
        "service": settings.service_name,
        "version": __import__('app').__version__,
        "database": "healthy" if db_healthy else "unhealthy",
        "running_jobs": running_jobs,
        "timestamp": datetime.now().isoformat()
    }


# ============================================================================
# DATA COLLECTION ENDPOINTS
# ============================================================================

@app.post("/api/v1/data/collect/{symbol}", tags=["Data Collection"])
async def collect_symbol_data(
    symbol: str,
    interval: str = Query(default="60", description="Kline interval in minutes"),
    days: Optional[int] = Query(default=None, description="Days of data to collect"),
    background_tasks: BackgroundTasks = None
):
    """
    Collect historical data for a specific symbol

    Args:
        symbol: Trading symbol (e.g., SOLUSDT)
        interval: Kline interval in minutes
        days: Days of historical data (default from settings)

    Returns:
        Data collection result with metrics
    """
    logger.info(f"Starting data collection for {symbol} ({interval}min)")

    try:
        collector = DataCollector()

        try:
            result = await collector.collect_training_data(
                symbol=symbol,
                interval=interval,
                days=days
            )

            # Don't return the full DataFrame, just metrics
            return {
                "success": result["success"],
                "symbol": symbol,
                "interval": interval,
                "metrics": result["metrics"],
                "errors": result["errors"],
                "data_points": len(result["data"]) if result["data"] is not None else 0,
                "timestamp": datetime.now().isoformat()
            }

        finally:
            await collector.close()

    except Exception as e:
        logger.error(f"Data collection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/data/collect-all", tags=["Data Collection"])
async def collect_all_data(
    interval: str = Query(default="60", description="Kline interval in minutes"),
    symbols: Optional[List[str]] = Query(default=None, description="Symbols to collect")
):
    """
    Collect historical data for all configured symbols

    Args:
        interval: Kline interval in minutes
        symbols: List of symbols (default from settings)

    Returns:
        Collection results for all symbols
    """
    symbols = symbols or settings.retrain_data_symbols

    logger.info(f"Starting data collection for {len(symbols)} symbols")

    try:
        collector = DataCollector()

        try:
            results = await collector.collect_all_symbols(
                symbols=symbols,
                interval=interval
            )

            # Format response
            response = {
                "success": True,
                "symbols_requested": len(symbols),
                "symbols_successful": sum(1 for r in results.values() if r["success"]),
                "symbols_failed": sum(1 for r in results.values() if not r["success"]),
                "results": {}
            }

            # Add summary for each symbol
            for symbol, result in results.items():
                response["results"][symbol] = {
                    "success": result["success"],
                    "data_points": len(result["data"]) if result["data"] is not None else 0,
                    "metrics": result["metrics"],
                    "errors": result["errors"]
                }

            return response

        finally:
            await collector.close()

    except Exception as e:
        logger.error(f"Bulk data collection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MODEL VERSION ENDPOINTS
# ============================================================================

@app.get("/api/v1/models/versions", tags=["Models"])
async def list_model_versions(
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, le=500, description="Max results"),
    db: AsyncSession = Depends(get_db)
):
    """
    List model versions with optional filters

    Args:
        symbol: Filter by trading symbol
        status: Filter by model status
        limit: Maximum number of results

    Returns:
        List of model versions
    """
    try:
        # Build query
        query = select(ModelVersion).order_by(ModelVersion.created_at.desc())

        if symbol:
            query = query.filter(ModelVersion.symbol == symbol)

        if status:
            query = query.filter(ModelVersion.status == status)

        query = query.limit(limit)

        # Execute query
        result = await db.execute(query)
        versions = result.scalars().all()

        return {
            "success": True,
            "count": len(versions),
            "versions": [v.to_dict() for v in versions]
        }

    except Exception as e:
        logger.error(f"Error listing model versions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/models/versions/{version_id}", tags=["Models"])
async def get_model_version(
    version_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific model version

    Args:
        version_id: Model version ID

    Returns:
        Model version details
    """
    try:
        result = await db.execute(
            select(ModelVersion).filter(ModelVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            raise HTTPException(status_code=404, detail="Model version not found")

        return {
            "success": True,
            "version": version.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching model version: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/models/production", tags=["Models"])
async def list_production_models(db: AsyncSession = Depends(get_db)):
    """
    List all currently deployed production models

    Returns:
        List of production models
    """
    try:
        result = await db.execute(
            select(ModelVersion)
            .filter(ModelVersion.status == ModelStatus.DEPLOYED)
            .order_by(ModelVersion.deployed_at.desc())
        )
        models = result.scalars().all()

        return {
            "success": True,
            "count": len(models),
            "models": [m.to_dict() for m in models]
        }

    except Exception as e:
        logger.error(f"Error listing production models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# RETRAINING JOB ENDPOINTS
# ============================================================================

@app.get("/api/v1/jobs", tags=["Retraining Jobs"])
async def list_retraining_jobs(
    status: Optional[str] = Query(default=None, description="Filter by status"),
    limit: int = Query(default=50, le=500, description="Max results"),
    db: AsyncSession = Depends(get_db)
):
    """
    List retraining jobs with optional filters

    Args:
        status: Filter by job status
        limit: Maximum number of results

    Returns:
        List of retraining jobs
    """
    try:
        query = select(RetrainingJob).order_by(RetrainingJob.created_at.desc())

        if status:
            query = query.filter(RetrainingJob.status == status)

        query = query.limit(limit)

        result = await db.execute(query)
        jobs = result.scalars().all()

        return {
            "success": True,
            "count": len(jobs),
            "jobs": [j.to_dict() for j in jobs]
        }

    except Exception as e:
        logger.error(f"Error listing jobs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", tags=["Retraining Jobs"])
async def get_retraining_job(
    job_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get details of a specific retraining job

    Args:
        job_id: Job identifier

    Returns:
        Job details
    """
    try:
        result = await db.execute(
            select(RetrainingJob).filter(RetrainingJob.job_id == job_id)
        )
        job = result.scalar_one_or_none()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return {
            "success": True,
            "job": job.to_dict()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# STATUS ENDPOINTS
# ============================================================================

@app.get("/api/v1/status", tags=["Status"])
async def get_service_status(db: AsyncSession = Depends(get_db)):
    """
    Get overall service status and statistics

    Returns:
        Service status with key metrics
    """
    try:
        # Count jobs by status
        result = await db.execute(select(RetrainingJob))
        all_jobs = result.scalars().all()

        job_stats = {
            "total": len(all_jobs),
            "pending": sum(1 for j in all_jobs if j.status == RetrainingStatus.PENDING),
            "running": sum(1 for j in all_jobs if j.status == RetrainingStatus.RUNNING),
            "completed": sum(1 for j in all_jobs if j.status == RetrainingStatus.COMPLETED),
            "failed": sum(1 for j in all_jobs if j.status == RetrainingStatus.FAILED),
        }

        # Count models by status
        result = await db.execute(select(ModelVersion))
        all_models = result.scalars().all()

        model_stats = {
            "total": len(all_models),
            "deployed": sum(1 for m in all_models if m.status == ModelStatus.DEPLOYED),
            "approved": sum(1 for m in all_models if m.status == ModelStatus.APPROVED),
            "rejected": sum(1 for m in all_models if m.status == ModelStatus.REJECTED),
        }

        # Get last job
        result = await db.execute(
            select(RetrainingJob)
            .order_by(RetrainingJob.created_at.desc())
            .limit(1)
        )
        last_job = result.scalar_one_or_none()

        return {
            "success": True,
            "service": settings.service_name,
            "version": __import__('app').__version__,
            "job_statistics": job_stats,
            "model_statistics": model_stats,
            "last_job": last_job.to_dict() if last_job else None,
            "configuration": {
                "auto_deploy": settings.retrain_auto_deploy,
                "schedule_enabled": settings.retrain_schedule_enabled,
                "schedule_cron": settings.retrain_schedule_cron,
                "symbols": settings.retrain_data_symbols,
            },
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error fetching service status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRAINING & VALIDATION ENDPOINTS
# ============================================================================

@app.post("/api/v1/train/{symbol}", tags=["Training"])
async def train_model(
    symbol: str,
    interval: str = Query(default="60", description="Kline interval in minutes"),
    test_size: float = Query(default=0.2, ge=0.1, le=0.5, description="Test set fraction"),
    save_model: bool = Query(default=True, description="Save trained model"),
    db: AsyncSession = Depends(get_db)
):
    """
    Train a new GRU model for a symbol

    Args:
        symbol: Trading symbol (e.g., SOLUSDT)
        interval: Kline interval in minutes
        test_size: Fraction of data for testing
        save_model: Whether to save the trained model

    Returns:
        Training results with metrics
    """
    from app.core.data_collector import DataCollector
    from app.core.model_trainer import ModelTrainer
    import os

    logger.info(f"Training request for {symbol} ({interval}min)")

    try:
        # Step 1: Collect training data
        collector = DataCollector()

        try:
            data_result = await collector.collect_training_data(
                symbol=symbol,
                interval=interval
            )

            if not data_result["success"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Data collection failed: {data_result['errors']}"
                )

            logger.info(f"Data collected: {len(data_result['data'])} points")

        finally:
            await collector.close()

        # Step 2: Train model
        trainer = ModelTrainer()

        training_result = trainer.train_model(
            data=data_result["data"],
            symbol=symbol,
            interval=interval,
            test_size=test_size
        )

        if not training_result["success"]:
            raise HTTPException(
                status_code=500,
                detail=f"Training failed: {training_result.get('error', 'Unknown error')}"
            )

        # Step 3: Save model if requested
        saved_paths = {}
        if save_model:
            version = training_result["metadata"]["version"]
            output_dir = os.path.join(
                settings.models_versions_dir,
                symbol,
                version
            )

            saved_paths = trainer.save_model(
                model=training_result["model"],
                metadata=training_result["metadata"],
                train_metrics=training_result["train_metrics"],
                val_metrics=training_result["val_metrics"],
                test_metrics=training_result["test_metrics"],
                scaler_x=training_result["scaler_x"],
                scaler_y=training_result["scaler_y"],
                output_dir=output_dir,
                eval_arrays=training_result.get("eval_arrays"),
            )

            logger.info(f"Model saved to {output_dir}")

            # Step 4: Record in database
            from app.database.models import ModelVersion, ModelStatus

            model_version = ModelVersion(
                version=version,
                symbol=symbol,
                interval=interval,
                model_type="GRU",
                architecture=training_result["metadata"]["architecture"],
                training_info=training_result["metadata"]["training"],
                train_metrics=training_result["train_metrics"],
                val_metrics=training_result["val_metrics"],
                backtest_metrics=training_result["test_metrics"],
                model_path=saved_paths["model_path"],
                metadata_path=saved_paths["metadata_path"],
                status=ModelStatus.VALIDATION,
                is_better=False,  # Will be set by validation
            )

            db.add(model_version)
            await db.commit()
            await db.refresh(model_version)

            logger.info(f"Model version recorded in database: ID={model_version.id}")

        # Return results (excluding the actual Keras model object)
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "version": training_result["metadata"]["version"],
            "metrics": {
                **training_result["train_metrics"],
                **training_result["val_metrics"],
                **training_result["test_metrics"],
            },
            "metadata": training_result["metadata"],
            "saved_paths": saved_paths if save_model else None,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Training failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/validate/{version_id}", tags=["Validation"])
async def validate_model(
    version_id: int,
    current_version_id: Optional[int] = Query(default=None, description="Current production model ID"),
    db: AsyncSession = Depends(get_db)
):
    """
    Validate a trained model

    Args:
        version_id: New model version ID to validate
        current_version_id: Current production model ID (optional)

    Returns:
        Validation results and deployment recommendation
    """
    from app.core.model_validator import ModelValidator

    logger.info(f"Validation request for version {version_id}")

    try:
        # Get new model
        result = await db.execute(
            select(ModelVersion).filter(ModelVersion.id == version_id)
        )
        new_model = result.scalar_one_or_none()

        if not new_model:
            raise HTTPException(status_code=404, detail="Model version not found")

        # Get current production model if specified
        current_metrics = None
        if current_version_id:
            result = await db.execute(
                select(ModelVersion).filter(ModelVersion.id == current_version_id)
            )
            current_model = result.scalar_one_or_none()

            if current_model:
                current_metrics = {
                    **current_model.val_metrics,
                    **current_model.train_metrics,
                }

        # Validate
        validator = ModelValidator()

        new_metrics = {
            **new_model.val_metrics,
            **new_model.train_metrics,
        }

        validation_result = validator.validate_model(
            new_metrics=new_metrics,
            current_metrics=current_metrics,
            symbol=new_model.symbol
        )

        # Generate report
        report = validator.generate_validation_report(
            validation_result=validation_result,
            symbol=new_model.symbol,
            version=new_model.version
        )

        # Update model status based on validation
        if validation_result["should_deploy"]:
            new_model.status = ModelStatus.APPROVED
            new_model.is_better = True
            new_model.improvement_pct = validation_result["improvement_pct"]
        elif validation_result["is_valid"]:
            new_model.status = ModelStatus.VALIDATION
            new_model.is_better = False
        else:
            new_model.status = ModelStatus.REJECTED
            new_model.is_better = False

        await db.commit()

        logger.info(
            f"Validation complete: {new_model.status.value}, "
            f"Deploy={validation_result['should_deploy']}"
        )

        return {
            "success": True,
            "validation_result": validation_result,
            "report": report,
            "model_status": new_model.status.value,
            "timestamp": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/retrain/{symbol}", tags=["Retraining"])
async def retrain_model(
    symbol: str,
    interval: str = Query(default="60", description="Kline interval"),
    auto_validate: bool = Query(default=True, description="Automatically validate after training"),
    auto_deploy: bool = Query(default=None, description="Auto-deploy if validated (uses config default if None)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Complete retraining workflow: collect data → train → validate → (optionally deploy)

    Args:
        symbol: Trading symbol
        interval: Kline interval
        auto_validate: Run validation after training
        auto_deploy: Deploy if validation passes (None = use config default)

    Returns:
        Complete retraining results
    """
    from app.core.data_collector import DataCollector
    from app.core.model_trainer import ModelTrainer
    from app.core.model_validator import ModelValidator
    import uuid
    import os

    # Use config default if not specified
    if auto_deploy is None:
        auto_deploy = settings.retrain_auto_deploy

    job_id = f"retrain_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

    logger.info(f"Starting retraining job: {job_id}")

    # Create job record
    job = RetrainingJob(
        job_id=job_id,
        trigger_type="api",
        triggered_by="manual",
        config={
            "symbol": symbol,
            "interval": interval,
            "auto_validate": auto_validate,
            "auto_deploy": auto_deploy,
        },
        status=RetrainingStatus.RUNNING,
        started_at=datetime.now()
    )
    db.add(job)
    await db.commit()

    try:
        results = {}

        # Step 1: Collect data
        logger.info("Step 1/4: Collecting training data...")
        collector = DataCollector()

        try:
            data_result = await collector.collect_training_data(symbol=symbol, interval=interval)
            results["data_collection"] = {
                "success": data_result["success"],
                "data_points": len(data_result["data"]) if data_result["data"] is not None else 0,
                "metrics": data_result["metrics"],
            }

            if not data_result["success"]:
                raise Exception(f"Data collection failed: {data_result['errors']}")

        finally:
            await collector.close()

        # Step 2: Train model
        logger.info("Step 2/4: Training GRU model...")
        trainer = ModelTrainer()

        training_result = trainer.train_model(
            data=data_result["data"],
            symbol=symbol,
            interval=interval
        )

        if not training_result["success"]:
            raise Exception(f"Training failed: {training_result.get('error')}")

        # Save model
        version = training_result["metadata"]["version"]
        output_dir = os.path.join(settings.models_versions_dir, symbol, version)

        saved_paths = trainer.save_model(
            model=training_result["model"],
            metadata=training_result["metadata"],
            train_metrics=training_result["train_metrics"],
            val_metrics=training_result["val_metrics"],
            test_metrics=training_result["test_metrics"],
            scaler_x=training_result["scaler_x"],
            scaler_y=training_result["scaler_y"],
            output_dir=output_dir,
            eval_arrays=training_result.get("eval_arrays"),
        )

        # Record model version
        model_version = ModelVersion(
            version=version,
            symbol=symbol,
            interval=interval,
            model_type="GRU",
            architecture=training_result["metadata"]["architecture"],
            training_info=training_result["metadata"]["training"],
            train_metrics=training_result["train_metrics"],
            val_metrics=training_result["val_metrics"],
            backtest_metrics=training_result["test_metrics"],
            model_path=saved_paths["model_path"],
            metadata_path=saved_paths["metadata_path"],
            status=ModelStatus.TRAINING,
        )
        db.add(model_version)
        await db.commit()
        await db.refresh(model_version)

        results["training"] = {
            "success": True,
            "version": version,
            "version_id": model_version.id,
            "metrics": training_result["val_metrics"],
        }

        # Step 3: Validate (if enabled)
        validation_result = None
        if auto_validate:
            logger.info("Step 3/4: Validating model...")

            # Find current production model
            result_prod = await db.execute(
                select(ModelVersion)
                .filter(ModelVersion.symbol == symbol)
                .filter(ModelVersion.status == ModelStatus.DEPLOYED)
                .order_by(ModelVersion.deployed_at.desc())
                .limit(1)
            )
            current_model = result_prod.scalar_one_or_none()

            current_metrics = None
            if current_model:
                current_metrics = {**current_model.val_metrics, **current_model.train_metrics}

            validator = ModelValidator()
            new_metrics = {**model_version.val_metrics, **model_version.train_metrics}

            validation_result = validator.validate_model(
                new_metrics=new_metrics,
                current_metrics=current_metrics,
                symbol=symbol
            )

            # Update model status
            if validation_result["should_deploy"]:
                model_version.status = ModelStatus.APPROVED
                model_version.is_better = True
                model_version.improvement_pct = validation_result["improvement_pct"]
                if current_model:
                    model_version.replaced_version = current_model.version
            else:
                model_version.status = ModelStatus.REJECTED if not validation_result["is_valid"] else ModelStatus.VALIDATION
                model_version.is_better = False

            await db.commit()

            results["validation"] = {
                "success": True,
                "should_deploy": validation_result["should_deploy"],
                "is_valid": validation_result["is_valid"],
                "improvement_pct": validation_result["improvement_pct"],
                "reason": validation_result["reason"],
            }

        # Step 4: Deploy (if approved and auto_deploy enabled)
        deployed = False
        deployment_result = None

        if auto_validate and validation_result and validation_result["should_deploy"] and auto_deploy:
            logger.info("Step 4/4: Deploying model to production...")

            try:
                deployer = ModelDeployer()

                deployment_result = await deployer.deploy_model(
                    symbol=symbol,
                    model_path=saved_paths["model_path"],
                    metadata_path=saved_paths["metadata_path"],
                    scalers_path=saved_paths["scalers_path"],
                    version=version,
                    backup_current=settings.retrain_backup_before_deploy,
                    verify_deployment=True
                )

                if deployment_result["success"]:
                    # Update model status
                    model_version.status = ModelStatus.DEPLOYED
                    model_version.deployed_at = datetime.now()
                    model_version.deployed_by = "automated_retraining"
                    await db.commit()

                    deployed = True
                    results["deployment"] = {
                        "success": True,
                        "deployed_at": model_version.deployed_at.isoformat(),
                        "backup_created": deployment_result.get("backup_created"),
                        "files_deployed": deployment_result.get("files_deployed"),
                        "verification_passed": deployment_result.get("verification_passed"),
                    }
                else:
                    logger.error(f"Deployment failed: {deployment_result.get('error')}")
                    results["deployment"] = {
                        "success": False,
                        "error": deployment_result.get("error"),
                        "rollback_performed": deployment_result.get("rollback_performed", False),
                    }

            except Exception as e:
                logger.error(f"Deployment exception: {e}", exc_info=True)
                results["deployment"] = {
                    "success": False,
                    "error": str(e),
                }
        else:
            results["deployment"] = {
                "success": False,
                "reason": "Deployment not triggered" if not auto_deploy else "Model not approved for deployment",
            }

        # Update job
        job.status = RetrainingStatus.COMPLETED
        job.completed_at = datetime.now()
        job.duration_seconds = (job.completed_at - job.started_at).total_seconds()
        job.results = results
        job.metrics_summary = {
            "val_r2": training_result["val_metrics"]["val_r2"],
            "improvement_pct": validation_result["improvement_pct"] if validation_result else 0,
            "deployed": deployed,
        }
        await db.commit()

        logger.info(f"✅ Retraining job complete: {job_id}")

        return {
            "success": True,
            "job_id": job_id,
            "results": results,
            "model_version_id": model_version.id,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"❌ Retraining job failed: {e}", exc_info=True)

        # Update job status
        job.status = RetrainingStatus.FAILED
        job.completed_at = datetime.now()
        job.duration_seconds = (job.completed_at - job.started_at).total_seconds()
        job.error_message = str(e)
        await db.commit()

        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DEPLOYMENT MANAGEMENT ENDPOINTS
# ============================================================================

@app.post("/api/v1/deploy/{version_id}", tags=["Deployment"])
async def deploy_model_version(
    version_id: int,
    backup_current: bool = Query(default=True, description="Backup current production model"),
    verify_deployment: bool = Query(default=True, description="Verify after deployment"),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually deploy a specific model version to production

    Args:
        version_id: Model version ID from database
        backup_current: Whether to backup current production model
        verify_deployment: Whether to verify deployment

    Returns:
        Deployment results
    """
    try:
        # Get model version
        result = await db.execute(
            select(ModelVersion).filter(ModelVersion.id == version_id)
        )
        model_version = result.scalar_one_or_none()

        if not model_version:
            raise HTTPException(status_code=404, detail=f"Model version {version_id} not found")

        # Check if model is approved
        if model_version.status not in [ModelStatus.APPROVED, ModelStatus.VALIDATION]:
            logger.warning(
                f"Deploying model with status {model_version.status} (not APPROVED)"
            )

        logger.info(f"Deploying model version {version_id} for {model_version.symbol}")

        # Deploy model
        deployer = ModelDeployer()

        # Extract file paths from model_version
        # Assuming paths are stored in metadata or we reconstruct them
        import os
        model_dir = os.path.dirname(model_version.model_path)

        deployment_result = await deployer.deploy_model(
            symbol=model_version.symbol,
            model_path=model_version.model_path,
            metadata_path=model_version.metadata_path,
            scalers_path=os.path.join(model_dir, "scalers.pkl"),
            version=model_version.version,
            backup_current=backup_current,
            verify_deployment=verify_deployment
        )

        if deployment_result["success"]:
            # Update model status
            model_version.status = ModelStatus.DEPLOYED
            model_version.deployed_at = datetime.now()
            model_version.deployed_by = "manual_deployment"
            await db.commit()

            return {
                "success": True,
                "model_version_id": version_id,
                "symbol": model_version.symbol,
                "version": model_version.version,
                "deployment_result": deployment_result,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": deployment_result.get("error"),
                "deployment_result": deployment_result
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deploying model version {version_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/deploy/rollback/{symbol}", tags=["Deployment"])
async def rollback_deployment(
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Rollback to previous production model

    Args:
        symbol: Trading symbol to rollback

    Returns:
        Rollback results
    """
    try:
        logger.info(f"Rolling back deployment for {symbol}")

        deployer = ModelDeployer()
        rollback_result = await deployer.rollback_deployment(symbol)

        if rollback_result["success"]:
            # Update database - mark current as rolled back, restore previous as deployed
            # Find currently deployed model
            result = await db.execute(
                select(ModelVersion)
                .filter(ModelVersion.symbol == symbol)
                .filter(ModelVersion.status == ModelStatus.DEPLOYED)
                .order_by(ModelVersion.deployed_at.desc())
            )
            current_models = result.scalars().all()

            for model in current_models:
                model.status = ModelStatus.ROLLED_BACK
                await db.commit()

            return {
                "success": True,
                "symbol": symbol,
                "rollback_result": rollback_result,
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "success": False,
                "error": rollback_result.get("error")
            }

    except Exception as e:
        logger.error(f"Error rolling back deployment for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/deploy/backups", tags=["Deployment"])
async def list_backups(
    symbol: Optional[str] = Query(default=None, description="Filter by symbol")
):
    """
    List available model backups

    Args:
        symbol: Optional symbol filter

    Returns:
        List of available backups
    """
    try:
        deployer = ModelDeployer()
        backups = deployer.list_backups(symbol=symbol)

        return {
            "success": True,
            "count": len(backups),
            "backups": backups,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error listing backups: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/deploy/status/{symbol}", tags=["Deployment"])
async def get_deployment_status(
    symbol: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current deployment status for a symbol

    Args:
        symbol: Trading symbol

    Returns:
        Current deployment status
    """
    try:
        # Get currently deployed model
        result = await db.execute(
            select(ModelVersion)
            .filter(ModelVersion.symbol == symbol)
            .filter(ModelVersion.status == ModelStatus.DEPLOYED)
            .order_by(ModelVersion.deployed_at.desc())
            .limit(1)
        )
        deployed_model = result.scalar_one_or_none()

        if not deployed_model:
            return {
                "success": True,
                "symbol": symbol,
                "deployed": False,
                "message": f"No deployed model found for {symbol}"
            }

        # Check if files exist in production
        deployer = ModelDeployer()
        interval = deployed_model.interval
        production_files = [
            deployer.production_dir / f"{symbol}_{interval}m_gru.keras",
            deployer.production_dir / f"{symbol}_{interval}m_gru_metadata.json",
            deployer.production_dir / f"{symbol}_{interval}m_gru_scalers.pkl"
        ]

        files_exist = all(f.exists() for f in production_files)

        return {
            "success": True,
            "symbol": symbol,
            "deployed": True,
            "current_version": {
                "id": deployed_model.id,
                "version": deployed_model.version,
                "deployed_at": deployed_model.deployed_at.isoformat() if deployed_model.deployed_at else None,
                "deployed_by": deployed_model.deployed_by,
                "metrics": deployed_model.val_metrics,
            },
            "files_in_production": files_exist,
            "production_files": [str(f) for f in production_files]
        }

    except Exception as e:
        logger.error(f"Error getting deployment status for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SCHEDULER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/v1/scheduler/status", tags=["Scheduler"])
async def get_scheduler_status():
    """
    Get scheduler status and information

    Returns scheduler state, scheduled jobs, and running jobs
    """
    try:
        scheduler = await get_scheduler()

        return {
            "success": True,
            "scheduler_running": scheduler.is_scheduler_running(),
            "schedule_enabled": settings.retrain_schedule_enabled,
            "schedule_cron": settings.retrain_schedule_cron,
            "scheduled_jobs": scheduler.get_scheduled_jobs(),
            "running_jobs": scheduler.get_running_jobs(),
            "configured_symbols": settings.retrain_data_symbols,
        }

    except Exception as e:
        logger.error(f"Error getting scheduler status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/trigger", tags=["Scheduler"])
async def trigger_manual_retraining(
    symbols: Optional[List[str]] = Query(default=None),
    triggered_by: str = Query(default="api"),
):
    """
    Manually trigger retraining for one or more symbols

    Args:
        symbols: List of symbols to retrain (None = all configured symbols)
        triggered_by: Who triggered the retraining

    Returns:
        Results for each symbol
    """
    try:
        scheduler = await get_scheduler()

        # Validate symbols if provided
        if symbols:
            invalid_symbols = [s for s in symbols if s not in settings.retrain_data_symbols]
            if invalid_symbols:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid symbols: {invalid_symbols}. "
                           f"Configured symbols: {settings.retrain_data_symbols}"
                )

        # Trigger retraining
        results = await scheduler.trigger_manual_retrain(
            symbols=symbols,
            triggered_by=triggered_by
        )

        return {
            "success": True,
            "triggered_at": datetime.now().isoformat(),
            "triggered_by": triggered_by,
            **results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering manual retraining: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/pause", tags=["Scheduler"])
async def pause_scheduler():
    """
    Pause all scheduled jobs

    Running jobs will continue, but no new jobs will start
    """
    try:
        scheduler = await get_scheduler()
        await scheduler.pause_scheduled_jobs()

        return {
            "success": True,
            "message": "Scheduled jobs paused",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error pausing scheduler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/scheduler/resume", tags=["Scheduler"])
async def resume_scheduler():
    """
    Resume all scheduled jobs
    """
    try:
        scheduler = await get_scheduler()
        await scheduler.resume_scheduled_jobs()

        return {
            "success": True,
            "message": "Scheduled jobs resumed",
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error resuming scheduler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/scheduler/next-runs", tags=["Scheduler"])
async def get_next_scheduled_runs():
    """
    Get next scheduled run times for all symbols

    Returns list of upcoming scheduled retraining jobs
    """
    try:
        scheduler = await get_scheduler()
        scheduled_jobs = scheduler.get_scheduled_jobs()

        # Sort by next run time
        scheduled_jobs.sort(
            key=lambda x: x['next_run'] if x['next_run'] else '9999-12-31'
        )

        return {
            "success": True,
            "total_jobs": len(scheduled_jobs),
            "jobs": scheduled_jobs,
            "current_time": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"Error getting next runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.service_host,
        port=settings.service_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
