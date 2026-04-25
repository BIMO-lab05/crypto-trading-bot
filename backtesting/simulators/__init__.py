"""
Backtesting Simulators
Created: 2025-12-06
Purpose: Risk assessment and robustness testing through simulation

This module provides simulation tools for:
- Monte Carlo simulation: Test thousands of random paths
- Risk-of-ruin calculation: Probability of total account loss
- Stress testing: Performance under extreme conditions
"""

__version__ = "1.0.0"
__author__ = "Crypto Trading Bot - Phase 1 Enhancement"

from .monte_carlo import MonteCarloSimulator
from .risk_of_ruin import RiskOfRuinCalculator

__all__ = [
    'MonteCarloSimulator',
    'RiskOfRuinCalculator',
]
