"""
Analytics Module for Trading Engine
Purpose: Performance attribution, advanced metrics, and post-trade analysis

This module provides comprehensive analytics for trading strategies:

Phase 5.1 - Attribution Analysis:
- Attribution by Strategy (Pairs Trading, Funding Rate Arb, Triangular Arb, etc.)
- Attribution by Symbol (BTCUSDT, ETHUSDT, SOLUSDT, etc.)
- Attribution by Timeframe (Hourly, Daily, Weekly, Monthly)
- Attribution by Trade Direction (Long vs Short)
- Attribution by Market Condition (Trending vs Ranging)
- Performance Decomposition (Alpha, Beta, Residual)
- Advanced Performance Metrics (Sharpe, Sortino, VaR, CVaR, Beta, etc.)
- Drawdown Analysis and Recovery Tracking
- Rolling Metrics Calculation

Phase 5.2 - Advanced Performance Metrics:
- Risk-Adjusted Returns (Sharpe, Sortino, Calmar, Omega, Treynor, Information Ratio)
- Drawdown Analysis (Max DD, Recovery Factor, Ulcer Index, Pain Index)
- Win/Loss Metrics (Win Rate, Profit Factor, Kelly %, Streaks)
- Risk Metrics (VaR, CVaR, MAE, MFE, Risk of Ruin, Beta)
- Trade Efficiency (Duration, Frequency, Capital Utilization, Turnover)
- Benchmark Comparison (vs BTC)
- Performance Reports (Daily, Monthly, Monte Carlo)

Phase 4.3 - Post-Trade Analysis:
- Trade Cost Analysis (slippage breakdown, fees, opportunity cost)
- Execution Quality Metrics (Implementation Shortfall, Price Improvement)
- Trade Classification (aggressive/passive, market conditions, liquidity)
- Daily Execution Summaries
- Weekly Performance Comparisons
- Improvement Recommendations

Author: Backend Developer Agent
Date: 2025-12-11
Updated: 2025-12-12 - Added Advanced Performance Metrics (Phase 5.2)
"""

from .attribution import (
    # Core models
    AttributionMetrics,
    AttributionDimension,
    MarketCondition,
    TradeDirection,
    TradePeriod,
    TradeRecord,
    AttributionResult,
    AttributionSummary,
    TrendAnalysis,
    PerformanceDecomposition,
    # Service class
    AttributionAnalyzer,
    # Helper functions
    get_attribution_analyzer,
    reset_attribution_analyzer,
)

from .models import (
    # API Request/Response models - Attribution
    AttributionByStrategyResponse,
    AttributionBySymbolResponse,
    AttributionSummaryResponse,
    AttributionTrendsResponse,
    AttributionTrendsRequest,
    # API Request/Response models - Post-Trade Analysis
    PostTradeAnalysisRequest,
    SlippageBreakdownResponse,
    ExecutionQualityResponse,
    TradeClassificationResponse,
    TradeExecutionReport,
    DailySummaryResponse,
    ImprovementRecommendationResponse,
    BestWorstExecutionsResponse,
    StrategyAnalysisResponse,
    SymbolAnalysisResponse,
    WeeklyComparisonResponse,
    PostTradeAnalysisSummaryResponse,
    # Enums
    ExecutionStyleEnum,
    MarketConditionEnum,
    LiquidityLevelEnum,
    TradingSessionEnum,
    QualityGradeEnum,
)

from .advanced_metrics import (
    # Enums
    MetricsPeriod,
    RiskLevel,
    DrawdownStatus,
    # Data Models - Risk Adjusted
    RiskAdjustedMetrics,
    # Data Models - Drawdown
    DrawdownMetrics,
    DrawdownInfo,
    DrawdownAnalysis,
    # Data Models - Win/Loss
    WinLossMetrics,
    # Data Models - Risk
    RiskMetrics,
    # Data Models - Efficiency
    EfficiencyMetrics,
    # Data Models - Benchmark
    BenchmarkComparison,
    # Data Models - Statistical
    StatisticalMetrics,
    # Data Models - Attribution
    AttributionByDimension,
    # Data Models - Rolling
    RollingMetrics,
    # Data Models - Trade
    TradeMetadata,
    # Data Models - All Metrics
    AllMetrics,
    # Data Models - Comprehensive
    ComprehensiveMetrics,
    # Main calculator class
    AdvancedMetricsCalculator,
    # Helper functions
    get_advanced_metrics_calculator,
    reset_advanced_metrics_calculator,
)

from .post_trade_analysis import (
    # Enums
    ExecutionStyle,
    MarketConditionType,
    LiquidityLevel,
    TradingSession,
    ExecutionQualityGrade,
    BenchmarkType,
    # Data Models
    SlippageBreakdown,
    ExecutionQuality,
    TradeClassification,
    TradeExecutionData,
    PostTradeAnalysisResult,
    DailySummary,
    ImprovementRecommendation,
    # Main analyzer class
    PostTradeAnalyzer,
    # Helper functions
    get_post_trade_analyzer,
    reset_post_trade_analyzer,
)

from .trade_report import (
    # Enums
    ReportFormat,
    ReportPeriod,
    TrendDirection,
    # Data Models
    IndividualTradeReport,
    WeeklyComparisonReport,
    ExecutionTrend,
    # Main generator class
    TradeReportGenerator,
    # Helper functions
    get_trade_report_generator,
    reset_trade_report_generator,
)

from .performance_report import (
    # Report Data Models
    DailyReportData,
    MonthlyReportData,
    MonteCarloResult,
    # Report Generator
    PerformanceReportGenerator,
    get_report_generator,
)

__all__ = [
    # =========================================================================
    # Attribution Module Exports (Phase 5.1)
    # =========================================================================
    # Core models
    "AttributionMetrics",
    "AttributionDimension",
    "MarketCondition",
    "TradeDirection",
    "TradePeriod",
    "TradeRecord",
    "AttributionResult",
    "AttributionSummary",
    "TrendAnalysis",
    "PerformanceDecomposition",
    # Service class
    "AttributionAnalyzer",
    # Helper functions
    "get_attribution_analyzer",
    "reset_attribution_analyzer",
    # API models
    "AttributionByStrategyResponse",
    "AttributionBySymbolResponse",
    "AttributionSummaryResponse",
    "AttributionTrendsResponse",
    "AttributionTrendsRequest",
    # =========================================================================
    # Advanced Metrics Module Exports (Phase 5.2)
    # =========================================================================
    # Enums
    "MetricsPeriod",
    "RiskLevel",
    "DrawdownStatus",
    # Data Models - Risk Adjusted
    "RiskAdjustedMetrics",
    # Data Models - Drawdown
    "DrawdownMetrics",
    "DrawdownInfo",
    "DrawdownAnalysis",
    # Data Models - Win/Loss
    "WinLossMetrics",
    # Data Models - Risk
    "RiskMetrics",
    # Data Models - Efficiency
    "EfficiencyMetrics",
    # Data Models - Benchmark
    "BenchmarkComparison",
    # Data Models - Statistical
    "StatisticalMetrics",
    # Data Models - Attribution
    "AttributionByDimension",
    # Data Models - Rolling
    "RollingMetrics",
    # Data Models - Trade
    "TradeMetadata",
    # Data Models - All Metrics
    "AllMetrics",
    # Data Models - Comprehensive
    "ComprehensiveMetrics",
    # Main calculator class
    "AdvancedMetricsCalculator",
    # Helper functions
    "get_advanced_metrics_calculator",
    "reset_advanced_metrics_calculator",
    # =========================================================================
    # Performance Report Module Exports (Phase 5.2)
    # =========================================================================
    # Report Data Models
    "DailyReportData",
    "MonthlyReportData",
    "MonteCarloResult",
    # Report Generator
    "PerformanceReportGenerator",
    "get_report_generator",
    # =========================================================================
    # Post-Trade Analysis Module Exports (Phase 4.3)
    # =========================================================================
    # Enums
    "ExecutionStyle",
    "MarketConditionType",
    "LiquidityLevel",
    "TradingSession",
    "ExecutionQualityGrade",
    "BenchmarkType",
    # Data Models
    "SlippageBreakdown",
    "ExecutionQuality",
    "TradeClassification",
    "TradeExecutionData",
    "PostTradeAnalysisResult",
    "DailySummary",
    "ImprovementRecommendation",
    # Main analyzer class
    "PostTradeAnalyzer",
    # Helper functions
    "get_post_trade_analyzer",
    "reset_post_trade_analyzer",
    # =========================================================================
    # Trade Report Module Exports
    # =========================================================================
    # Enums
    "ReportFormat",
    "ReportPeriod",
    "TrendDirection",
    # Data Models
    "IndividualTradeReport",
    "WeeklyComparisonReport",
    "ExecutionTrend",
    # Main generator class
    "TradeReportGenerator",
    # Helper functions
    "get_trade_report_generator",
    "reset_trade_report_generator",
    # =========================================================================
    # API Model Exports (Pydantic)
    # =========================================================================
    # Post-Trade Analysis API models
    "PostTradeAnalysisRequest",
    "SlippageBreakdownResponse",
    "ExecutionQualityResponse",
    "TradeClassificationResponse",
    "TradeExecutionReport",
    "DailySummaryResponse",
    "ImprovementRecommendationResponse",
    "BestWorstExecutionsResponse",
    "StrategyAnalysisResponse",
    "SymbolAnalysisResponse",
    "WeeklyComparisonResponse",
    "PostTradeAnalysisSummaryResponse",
    # API Enums
    "ExecutionStyleEnum",
    "MarketConditionEnum",
    "LiquidityLevelEnum",
    "TradingSessionEnum",
    "QualityGradeEnum",
]
