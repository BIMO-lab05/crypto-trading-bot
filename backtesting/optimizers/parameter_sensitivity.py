"""
Parameter Sensitivity Analysis
Created: 2025-12-06
Purpose: Identify which parameters most impact strategy performance

Parameter Sensitivity helps answer:
- Which parameters matter most?
- Which parameters can I ignore?
- How robust is my strategy to parameter changes?
- What's the safe operating range for each parameter?

Methods:
1. One-at-a-time (OAT) analysis: Vary one parameter, hold others constant
2. Variance-based analysis: Calculate contribution to total variance
3. Stability analysis: Test parameter ranges for consistent performance
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import stats
import json

logger = logging.getLogger(__name__)


@dataclass
class SensitivityConfig:
    """Configuration for parameter sensitivity analysis"""

    # Analysis settings
    num_samples: int = 100  # Number of samples per parameter
    perturbation_range: float = 0.20  # ±20% around baseline value

    # Metrics to analyze
    metrics_to_analyze: List[str] = field(default_factory=lambda: [
        'sharpe_ratio',
        'total_return',
        'max_drawdown',
        'win_rate'
    ])

    # Statistical thresholds
    min_correlation: float = 0.30  # Minimum correlation to be considered "sensitive"
    significance_level: float = 0.05  # P-value threshold for statistical significance


@dataclass
class ParameterSensitivity:
    """Sensitivity analysis results for a single parameter"""
    parameter_name: str
    baseline_value: Any
    tested_values: List[Any]
    metric_results: Dict[str, List[float]]  # {metric_name: [results for each test value]}

    # Sensitivity metrics
    correlation_coefficients: Dict[str, float] = field(default_factory=dict)
    p_values: Dict[str, float] = field(default_factory=dict)
    variance_contribution: Dict[str, float] = field(default_factory=dict)

    # Stability metrics
    coefficient_of_variation: Dict[str, float] = field(default_factory=dict)
    safe_range: Tuple[Any, Any] = None  # Range with consistent performance

    def is_sensitive(self, metric: str = 'sharpe_ratio', threshold: float = 0.30) -> bool:
        """
        Check if parameter is sensitive for given metric

        Returns:
            True if parameter significantly impacts metric
        """
        correlation = abs(self.correlation_coefficients.get(metric, 0))
        p_value = self.p_values.get(metric, 1.0)
        return correlation >= threshold and p_value < 0.05

    def get_optimal_range(
        self,
        metric: str = 'sharpe_ratio',
        percentile: float = 75
    ) -> Tuple[Any, Any]:
        """
        Get optimal parameter range based on metric

        Returns top percentile of parameter values by performance

        Args:
            metric: Metric to optimize
            percentile: Top percentile to consider (e.g., 75 = top 25%)

        Returns:
            Tuple of (min, max) values in optimal range
        """
        metric_values = self.metric_results.get(metric, [])
        if not metric_values:
            return self.baseline_value, self.baseline_value

        # Find threshold for top percentile
        threshold = np.percentile(metric_values, percentile)

        # Get parameter values that meet threshold
        optimal_params = [
            self.tested_values[i]
            for i, value in enumerate(metric_values)
            if value >= threshold
        ]

        if not optimal_params:
            return self.baseline_value, self.baseline_value

        return min(optimal_params), max(optimal_params)


@dataclass
class SensitivityResults:
    """Complete sensitivity analysis results"""
    config: SensitivityConfig
    baseline_parameters: Dict[str, Any]
    parameter_sensitivities: Dict[str, ParameterSensitivity]

    # Ranking
    most_sensitive_parameters: List[str] = field(default_factory=list)
    least_sensitive_parameters: List[str] = field(default_factory=list)

    def get_parameter_ranking(
        self,
        metric: str = 'sharpe_ratio'
    ) -> List[Tuple[str, float]]:
        """
        Rank parameters by sensitivity for given metric

        Returns:
            List of (parameter_name, correlation) tuples, sorted by sensitivity
        """
        rankings = []
        for param_name, sensitivity in self.parameter_sensitivities.items():
            correlation = abs(sensitivity.correlation_coefficients.get(metric, 0))
            rankings.append((param_name, correlation))

        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        sharpe_ranking = self.get_parameter_ranking('sharpe_ratio')

        return {
            'baseline_parameters': self.baseline_parameters,
            'sensitivity_ranking': [
                {
                    'parameter': name,
                    'correlation': round(corr, 4),
                    'sensitivity': 'HIGH' if corr >= 0.5 else ('MEDIUM' if corr >= 0.3 else 'LOW')
                }
                for name, corr in sharpe_ranking
            ],
            'detailed_analysis': {
                param_name: {
                    'baseline_value': sens.baseline_value,
                    'sharpe_correlation': round(abs(sens.correlation_coefficients.get('sharpe_ratio', 0)), 4),
                    'p_value': round(sens.p_values.get('sharpe_ratio', 1.0), 4),
                    'is_significant': sens.is_sensitive('sharpe_ratio'),
                    'optimal_range': sens.get_optimal_range('sharpe_ratio'),
                    'coefficient_of_variation': round(sens.coefficient_of_variation.get('sharpe_ratio', 0), 4),
                }
                for param_name, sens in self.parameter_sensitivities.items()
            }
        }


class ParameterSensitivityAnalyzer:
    """
    Parameter Sensitivity Analyzer

    Identifies which parameters have the most impact on strategy performance.

    Usage:
        config = SensitivityConfig(num_samples=50)
        analyzer = ParameterSensitivityAnalyzer(config)

        baseline_params = {
            'rsi_period': 14,
            'rsi_oversold': 30,
            'rsi_overbought': 70,
            'macd_fast': 12,
            'macd_slow': 26,
            'stop_loss_pct': 0.03,
        }

        results = analyzer.analyze(
            baseline_parameters=baseline_params,
            data=historical_data,
            backtest_engine=engine
        )

        # Show most sensitive parameters
        ranking = results.get_parameter_ranking('sharpe_ratio')
        for param, correlation in ranking[:3]:
            print(f"{param}: {correlation:.2%} correlation with Sharpe")

        # Get optimal ranges
        for param_name, sensitivity in results.parameter_sensitivities.items():
            if sensitivity.is_sensitive('sharpe_ratio'):
                opt_range = sensitivity.get_optimal_range('sharpe_ratio')
                print(f"{param_name}: Optimal range {opt_range}")
    """

    def __init__(self, config: Optional[SensitivityConfig] = None):
        """Initialize sensitivity analyzer"""
        self.config = config or SensitivityConfig()
        logger.info(f"Initialized ParameterSensitivityAnalyzer")

    def generate_parameter_samples(
        self,
        baseline_value: Any,
        num_samples: int,
        perturbation_range: float
    ) -> List[Any]:
        """
        Generate parameter samples around baseline value

        Args:
            baseline_value: Baseline parameter value
            num_samples: Number of samples to generate
            perturbation_range: ±% range around baseline (e.g., 0.20 = ±20%)

        Returns:
            List of parameter values to test
        """
        if isinstance(baseline_value, int):
            # Integer parameter
            min_val = int(baseline_value * (1 - perturbation_range))
            max_val = int(baseline_value * (1 + perturbation_range))
            samples = np.linspace(min_val, max_val, num_samples, dtype=int)
            return list(set(samples))  # Remove duplicates

        elif isinstance(baseline_value, float):
            # Float parameter
            min_val = baseline_value * (1 - perturbation_range)
            max_val = baseline_value * (1 + perturbation_range)
            samples = np.linspace(min_val, max_val, num_samples)
            return list(samples)

        else:
            # Cannot perturb non-numeric parameter
            logger.warning(f"Cannot perturb non-numeric parameter: {baseline_value}")
            return [baseline_value]

    def analyze_parameter(
        self,
        parameter_name: str,
        baseline_value: Any,
        baseline_parameters: Dict[str, Any],
        data: Any,
        backtest_engine: Any
    ) -> ParameterSensitivity:
        """
        Analyze sensitivity of a single parameter

        Args:
            parameter_name: Name of parameter to analyze
            baseline_value: Baseline value for parameter
            baseline_parameters: Full baseline parameter set
            data: Historical data
            backtest_engine: Backtesting engine

        Returns:
            ParameterSensitivity with analysis results
        """
        logger.info(f"Analyzing sensitivity of '{parameter_name}' (baseline={baseline_value})")

        # Generate parameter samples
        tested_values = self.generate_parameter_samples(
            baseline_value=baseline_value,
            num_samples=self.config.num_samples,
            perturbation_range=self.config.perturbation_range
        )

        # Run backtest for each sample
        metric_results = {metric: [] for metric in self.config.metrics_to_analyze}

        for test_value in tested_values:
            # Create modified parameters
            test_params = baseline_parameters.copy()
            test_params[parameter_name] = test_value

            try:
                # Run backtest
                results = backtest_engine.run(
                    data=data,
                    strategy_params=test_params
                )

                # Collect metrics
                for metric in self.config.metrics_to_analyze:
                    metric_value = results.get(metric, 0)
                    metric_results[metric].append(metric_value)

            except Exception as e:
                logger.error(f"Error testing {parameter_name}={test_value}: {e}")
                # Append NaN for failed tests
                for metric in self.config.metrics_to_analyze:
                    metric_results[metric].append(np.nan)

        # Calculate sensitivity metrics
        correlation_coefficients = {}
        p_values = {}
        coefficient_of_variation = {}

        for metric in self.config.metrics_to_analyze:
            metric_values = metric_results[metric]

            # Remove NaN values
            valid_indices = [i for i, v in enumerate(metric_values) if not np.isnan(v)]
            valid_test_values = [tested_values[i] for i in valid_indices]
            valid_metric_values = [metric_values[i] for i in valid_indices]

            if len(valid_metric_values) > 2:
                # Calculate Pearson correlation
                corr, p_val = stats.pearsonr(valid_test_values, valid_metric_values)
                correlation_coefficients[metric] = corr
                p_values[metric] = p_val

                # Calculate coefficient of variation (CV = std / mean)
                mean_val = np.mean(valid_metric_values)
                std_val = np.std(valid_metric_values)
                cv = (std_val / abs(mean_val)) if mean_val != 0 else 0
                coefficient_of_variation[metric] = cv

                logger.debug(f"  {metric}: corr={corr:.3f}, p={p_val:.3f}, CV={cv:.3f}")

        # Create sensitivity result
        sensitivity = ParameterSensitivity(
            parameter_name=parameter_name,
            baseline_value=baseline_value,
            tested_values=tested_values,
            metric_results=metric_results,
            correlation_coefficients=correlation_coefficients,
            p_values=p_values,
            coefficient_of_variation=coefficient_of_variation
        )

        # Determine safe range (low variation in performance)
        sharpe_cv = coefficient_of_variation.get('sharpe_ratio', 1.0)
        if sharpe_cv < 0.2:  # Less than 20% variation
            sensitivity.safe_range = (min(tested_values), max(tested_values))
            logger.info(f"  {parameter_name} is stable across full range")
        else:
            # Use top 75th percentile
            sensitivity.safe_range = sensitivity.get_optimal_range('sharpe_ratio', percentile=75)
            logger.info(f"  {parameter_name} optimal range: {sensitivity.safe_range}")

        return sensitivity

    def analyze(
        self,
        baseline_parameters: Dict[str, Any],
        data: Any,
        backtest_engine: Any
    ) -> SensitivityResults:
        """
        Run complete sensitivity analysis on all parameters

        Args:
            baseline_parameters: Baseline parameter values
            data: Historical data
            backtest_engine: Backtesting engine

        Returns:
            SensitivityResults with complete analysis
        """
        logger.info("="*60)
        logger.info("PARAMETER SENSITIVITY ANALYSIS STARTING")
        logger.info("="*60)

        parameter_sensitivities = {}

        # Analyze each parameter
        for param_name, baseline_value in baseline_parameters.items():
            sensitivity = self.analyze_parameter(
                parameter_name=param_name,
                baseline_value=baseline_value,
                baseline_parameters=baseline_parameters,
                data=data,
                backtest_engine=backtest_engine
            )
            parameter_sensitivities[param_name] = sensitivity

        # Create results
        results = SensitivityResults(
            config=self.config,
            baseline_parameters=baseline_parameters,
            parameter_sensitivities=parameter_sensitivities
        )

        # Rank parameters
        ranking = results.get_parameter_ranking('sharpe_ratio')
        results.most_sensitive_parameters = [name for name, corr in ranking[:3]]
        results.least_sensitive_parameters = [name for name, corr in ranking[-3:]]

        logger.info("="*60)
        logger.info("PARAMETER SENSITIVITY ANALYSIS COMPLETE")
        logger.info(f"Most sensitive: {results.most_sensitive_parameters}")
        logger.info(f"Least sensitive: {results.least_sensitive_parameters}")
        logger.info("="*60)

        return results

    def save_results(self, results: SensitivityResults, filepath: str):
        """Save sensitivity analysis results to JSON"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved sensitivity analysis to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load sensitivity analysis results from JSON"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded sensitivity analysis from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    config = SensitivityConfig(num_samples=20, perturbation_range=0.20)
    analyzer = ParameterSensitivityAnalyzer(config)

    baseline_params = {
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'stop_loss_pct': 0.03,
    }

    print(f"Sensitivity Analyzer initialized")
    print(f"Will test {config.num_samples} samples per parameter")
    print(f"Perturbation range: ±{config.perturbation_range:.0%}")
    print(f"Baseline parameters: {baseline_params}")
