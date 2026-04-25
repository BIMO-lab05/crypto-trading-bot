"""
Database Models for ML Retraining Service
Purpose: Track model versions, metrics, and deployment history
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional

Base = declarative_base()


class ModelStatus(str, Enum):
    """Model deployment status"""
    TRAINING = "training"
    VALIDATION = "validation"
    APPROVED = "approved"
    DEPLOYED = "deployed"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class RetrainingStatus(str, Enum):
    """Retraining job status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ModelVersion(Base):
    """
    Track individual model versions with metadata and metrics

    Each model version represents a trained model for a specific symbol/interval
    """
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Model identification
    version = Column(String(100), nullable=False, unique=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    interval = Column(String(10), nullable=False)
    model_type = Column(String(20), default="GRU", nullable=False)

    # Model architecture (stored as JSON)
    architecture = Column(JSON, nullable=False)
    # Example: {"layers": [128, 64], "sequence_length": 60, "prediction_horizon": 5}

    # Training information (stored as JSON)
    training_info = Column(JSON, nullable=False)
    # Example: {"data_range": "2025-06-13 to 2025-12-10", "samples": 12000, ...}

    # Training metrics (stored as JSON)
    train_metrics = Column(JSON, nullable=False)
    # Example: {"train_r2": 0.9234, "train_loss": 0.015, "train_mae": 120.5, ...}

    # Validation metrics (stored as JSON)
    val_metrics = Column(JSON, nullable=False)
    # Example: {"val_r2": 0.8956, "val_loss": 0.018, "val_mae": 135.2, ...}

    # Backtest metrics (stored as JSON, optional)
    backtest_metrics = Column(JSON, nullable=True)
    # Example: {"backtest_accuracy": 0.65, "backtest_sharpe": 1.8, ...}

    # Model file paths
    model_path = Column(String(500), nullable=False)
    metadata_path = Column(String(500), nullable=True)

    # Status and deployment
    status = Column(SQLEnum(ModelStatus), default=ModelStatus.VALIDATION, nullable=False, index=True)
    deployed_at = Column(DateTime(timezone=True), nullable=True)
    deployed_by = Column(String(100), nullable=True)
    replaced_version = Column(String(100), nullable=True)  # Previous production version

    # Comparison with previous model
    is_better = Column(Boolean, default=False, nullable=False)
    improvement_pct = Column(Float, nullable=True)  # Percentage improvement vs previous

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "version": self.version,
            "symbol": self.symbol,
            "interval": self.interval,
            "model_type": self.model_type,
            "architecture": self.architecture,
            "training_info": self.training_info,
            "train_metrics": self.train_metrics,
            "val_metrics": self.val_metrics,
            "backtest_metrics": self.backtest_metrics,
            "model_path": self.model_path,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "deployed_at": self.deployed_at.isoformat() if self.deployed_at else None,
            "deployed_by": self.deployed_by,
            "replaced_version": self.replaced_version,
            "is_better": self.is_better,
            "improvement_pct": self.improvement_pct,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class RetrainingJob(Base):
    """
    Track retraining job execution and results

    Each job represents a scheduled or manual retraining run
    """
    __tablename__ = "retraining_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Job identification
    job_id = Column(String(100), nullable=False, unique=True, index=True)
    trigger_type = Column(String(20), nullable=False)  # "scheduled", "manual", "api"
    triggered_by = Column(String(100), nullable=True)

    # Job configuration (stored as JSON)
    config = Column(JSON, nullable=False)
    # Example: {"symbols": ["SOLUSDT", "BNBUSDT"], "data_days": 180, ...}

    # Execution information
    status = Column(SQLEnum(RetrainingStatus), default=RetrainingStatus.PENDING, nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Results (stored as JSON)
    results = Column(JSON, nullable=True)
    # Example: {"models_trained": 3, "models_deployed": 2, "models_rejected": 1, ...}

    # Error information
    error_message = Column(String(1000), nullable=True)
    error_details = Column(JSON, nullable=True)

    # Metrics summary (stored as JSON)
    metrics_summary = Column(JSON, nullable=True)
    # Example: {"avg_r2_improvement": 0.03, "total_training_time": 450, ...}

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary"""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "trigger_type": self.trigger_type,
            "triggered_by": self.triggered_by,
            "config": self.config,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "results": self.results,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "metrics_summary": self.metrics_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ModelPerformanceLog(Base):
    """
    Track post-deployment performance of models

    Used for monitoring and automatic rollback
    """
    __tablename__ = "model_performance_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Model identification
    model_version = Column(String(100), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)

    # Performance metrics (stored as JSON)
    performance_metrics = Column(JSON, nullable=False)
    # Example: {"prediction_accuracy": 0.67, "error_rate": 0.05, "response_time_ms": 45, ...}

    # Comparison with pre-deployment metrics
    pre_deployment_metrics = Column(JSON, nullable=True)
    degradation_pct = Column(Float, nullable=True)  # Negative = improvement

    # Alert status
    alert_triggered = Column(Boolean, default=False, nullable=False)
    alert_reason = Column(String(500), nullable=True)

    # Timestamps
    measured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        """Convert log to dictionary"""
        return {
            "id": self.id,
            "model_version": self.model_version,
            "symbol": self.symbol,
            "performance_metrics": self.performance_metrics,
            "pre_deployment_metrics": self.pre_deployment_metrics,
            "degradation_pct": self.degradation_pct,
            "alert_triggered": self.alert_triggered,
            "alert_reason": self.alert_reason,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
