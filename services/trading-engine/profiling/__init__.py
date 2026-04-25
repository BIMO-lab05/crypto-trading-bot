"""
Profiling Module for Trading Engine Performance Analysis

This module provides comprehensive profiling tools for:
- Execution flow profiling (order placement, fills)
- Risk calculation profiling
- Analytics/metrics calculation profiling
- WebSocket update broadcasting

Usage:
    from profiling import ExecutionProfiler, RiskProfiler, AnalyticsProfiler

    profiler = ExecutionProfiler()
    results = profiler.run_profile(iterations=100)
    profiler.generate_report()

Author: Backend Developer Agent
Date: 2025-12-12
"""

from .profile_execution import ExecutionProfiler, profile_execution_flow
from .profile_risk import RiskProfiler, profile_risk_calculations
from .profile_analytics import AnalyticsProfiler, profile_metrics_calculation

__all__ = [
    "ExecutionProfiler",
    "profile_execution_flow",
    "RiskProfiler",
    "profile_risk_calculations",
    "AnalyticsProfiler",
    "profile_metrics_calculation",
]
