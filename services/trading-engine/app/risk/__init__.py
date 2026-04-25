"""
Risk Management Module
Purpose: Advanced risk management and position sizing tools

Phase 3.1: Enhanced Risk Management with Correlation Analysis
Phase 3.3: Dynamic Risk Budgeting Implementation
Updated: 2025-12-12

Contains:
- Kelly Criterion Position Sizing
- Dynamic capital allocation
- Win rate and edge tracking
- Risk-adjusted position sizing
- Portfolio Correlation Analysis
- Diversification Scoring
- Correlation-based Position Limits
- Sector Exposure Management
- Advanced Diversification Metrics
- Dynamic Risk Budgeting (NEW - Phase 3.3)
"""

# Kelly Criterion Position Sizing
from .kelly_position_sizing import (
    KellyPositionSizer,
    KellyResult,
    TradeRecord,
    KellyMode,
    get_kelly_sizer,
    reset_kelly_sizer,
)

# Portfolio Correlation Analysis (Phase 3.1)
from .correlation_manager import (
    CorrelationManager,
    CorrelationConfig,
    CorrelationMatrix,
    DiversificationScore,
    CorrelationAlert,
    AlertSeverity,
    get_correlation_manager,
    reset_correlation_manager,
)

# Sector Exposure Management (Phase 3.1)
from .sector_exposure import (
    SectorExposureManager,
    SectorExposureConfig,
    CryptoSector,
    SectorPosition,
    SectorExposure,
    SectorRotationSignal,
    SectorAnalysisResult,
    SECTOR_MAPPING,
    SECTOR_CHARACTERISTICS,
    get_sector_exposure_manager,
    reset_sector_exposure_manager,
)

# Advanced Diversification Metrics (Phase 3.1)
from .diversification_calculator import (
    DiversificationCalculator,
    DiversificationConfig,
    DiversificationMetrics,
    ConcentrationLevel,
    PositionData,
    RiskContribution,
    ConcentrationWarning,
    OptimalWeights,
    get_diversification_calculator,
    reset_diversification_calculator,
)

# Dynamic Risk Budgeting - Legacy module (Phase 3.3)
from .dynamic_budget import (
    DynamicBudgetManager,
    BudgetConfig,
    BudgetAlert,
    AlertSeverity as BudgetAlertSeverity,
    get_budget_manager,
    reset_budget_manager,
)

# Dynamic Risk Budgeting - Enhanced module (Phase 3.3)
from .dynamic_risk_budget import (
    DynamicRiskBudget,
    RiskBudgetConfig,
    RiskBudgetRequest,
    RiskBudgetResponse,
    RiskAllocation,
    RiskUtilization,
    RiskAdjustment,
    RiskBudgetAlert,
    RiskBudgetHistoryEntry,
    MarketRegime,
    EmergencyTrigger,
    RiskBudgetAlertSeverity,
    RISK_LADDER,
    LOW_LIQUIDITY_HOURS,
    get_risk_budget_manager,
    reset_risk_budget_manager,
)

__all__ = [
    # Kelly Criterion
    "KellyPositionSizer",
    "KellyResult",
    "TradeRecord",
    "KellyMode",
    "get_kelly_sizer",
    "reset_kelly_sizer",
    # Correlation Analysis (Phase 3.1)
    "CorrelationManager",
    "CorrelationConfig",
    "CorrelationMatrix",
    "DiversificationScore",
    "CorrelationAlert",
    "AlertSeverity",
    "get_correlation_manager",
    "reset_correlation_manager",
    # Sector Exposure (Phase 3.1)
    "SectorExposureManager",
    "SectorExposureConfig",
    "CryptoSector",
    "SectorPosition",
    "SectorExposure",
    "SectorRotationSignal",
    "SectorAnalysisResult",
    "SECTOR_MAPPING",
    "SECTOR_CHARACTERISTICS",
    "get_sector_exposure_manager",
    "reset_sector_exposure_manager",
    # Diversification Calculator (Phase 3.1)
    "DiversificationCalculator",
    "DiversificationConfig",
    "DiversificationMetrics",
    "ConcentrationLevel",
    "PositionData",
    "RiskContribution",
    "ConcentrationWarning",
    "OptimalWeights",
    "get_diversification_calculator",
    "reset_diversification_calculator",
    # Dynamic Risk Budgeting - Legacy (Phase 3.3)
    "DynamicBudgetManager",
    "BudgetConfig",
    "BudgetAlert",
    "BudgetAlertSeverity",
    "get_budget_manager",
    "reset_budget_manager",
    # Dynamic Risk Budgeting - Enhanced (Phase 3.3)
    "DynamicRiskBudget",
    "RiskBudgetConfig",
    "RiskBudgetRequest",
    "RiskBudgetResponse",
    "RiskAllocation",
    "RiskUtilization",
    "RiskAdjustment",
    "RiskBudgetAlert",
    "RiskBudgetHistoryEntry",
    "MarketRegime",
    "EmergencyTrigger",
    "RiskBudgetAlertSeverity",
    "RISK_LADDER",
    "LOW_LIQUIDITY_HOURS",
    "get_risk_budget_manager",
    "reset_risk_budget_manager",
]
