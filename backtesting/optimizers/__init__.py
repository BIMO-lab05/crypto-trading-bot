"""
Backtesting Optimization Engines
Created: 2025-12-06
Purpose: Advanced parameter optimization to prevent overfitting

This module provides professional-grade optimization tools:
- Walk-Forward Optimization: Rolling windows for out-of-sample validation
- Genetic Algorithms: Evolutionary parameter search
- Grid Search: Exhaustive parameter combinations
- Parameter Sensitivity Analysis: Robustness testing
"""

__version__ = "1.0.0"
__author__ = "Crypto Trading Bot - Phase 1 Enhancement"

from .walk_forward_optimizer import WalkForwardOptimizer
from .genetic_optimizer import GeneticOptimizer
from .grid_search_optimizer import GridSearchOptimizer
from .parameter_sensitivity import ParameterSensitivityAnalyzer

__all__ = [
    'WalkForwardOptimizer',
    'GeneticOptimizer',
    'GridSearchOptimizer',
    'ParameterSensitivityAnalyzer',
]
