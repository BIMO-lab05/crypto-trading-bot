"""
Strategy Correlation Analyzer
Created: 2025-12-06
Purpose: Analyze correlation between multiple trading strategies

Strategy correlation analysis helps answer:
- Are my strategies diversified or redundant?
- Which strategies complement each other?
- How to build a portfolio of uncorrelated strategies?
- What's the diversification benefit?

Key Metrics:
- Return correlation (Pearson)
- Trade overlap (% of concurrent positions)
- Drawdown correlation (risk diversification)
- Rank correlation (Spearman - non-linear relationships)
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import numpy as np
import pandas as pd
from scipy import stats
from scipy.cluster import hierarchy
import json

logger = logging.getLogger(__name__)


@dataclass
class CorrelationConfig:
    """Configuration for strategy correlation analysis"""

    # Correlation methods
    methods: List[str] = field(default_factory=lambda: ['pearson', 'spearman'])

    # Rolling correlation settings
    calculate_rolling: bool = True
    rolling_window: int = 30  # Days for rolling correlation

    # Thresholds
    high_correlation_threshold: float = 0.70  # >70% = highly correlated
    low_correlation_threshold: float = 0.30  # <30% = uncorrelated

    # Clustering
    perform_clustering: bool = True
    max_clusters: int = 5


@dataclass
class StrategyPairCorrelation:
    """Correlation analysis for a pair of strategies"""
    strategy1_name: str
    strategy2_name: str

    # Return correlations
    return_correlation_pearson: float
    return_correlation_spearman: float
    return_correlation_pvalue: float

    # Trade overlap
    trade_overlap_pct: float  # % of days both strategies had positions
    concurrent_wins_pct: float  # % of concurrent winning days
    concurrent_losses_pct: float  # % of concurrent losing days

    # Drawdown correlation
    drawdown_correlation: float

    # Rolling correlation statistics
    rolling_correlation_mean: Optional[float] = None
    rolling_correlation_std: Optional[float] = None
    rolling_correlation_min: Optional[float] = None
    rolling_correlation_max: Optional[float] = None

    def is_diversifying(self, threshold: float = 0.30) -> bool:
        """Check if strategies are diversifying (low correlation)"""
        return abs(self.return_correlation_pearson) < threshold

    def is_redundant(self, threshold: float = 0.70) -> bool:
        """Check if strategies are redundant (high correlation)"""
        return abs(self.return_correlation_pearson) > threshold


@dataclass
class CorrelationResults:
    """Complete strategy correlation analysis results"""
    config: CorrelationConfig
    strategy_names: List[str]
    pairwise_correlations: List[StrategyPairCorrelation]

    # Correlation matrices
    return_correlation_matrix: pd.DataFrame
    drawdown_correlation_matrix: pd.DataFrame

    # Portfolio metrics
    portfolio_diversification_ratio: float  # Higher = better diversification
    average_pairwise_correlation: float
    max_pairwise_correlation: float
    min_pairwise_correlation: float

    # Strategy groups (clustering)
    strategy_clusters: Optional[Dict[str, List[str]]] = None

    # Recommendations
    most_diversifying_pair: Optional[Tuple[str, str]] = None
    most_correlated_pair: Optional[Tuple[str, str]] = None
    redundant_strategies: List[str] = field(default_factory=list)

    def get_correlation_matrix(self, metric: str = 'return') -> pd.DataFrame:
        """Get correlation matrix for visualization"""
        if metric == 'return':
            return self.return_correlation_matrix
        elif metric == 'drawdown':
            return self.drawdown_correlation_matrix
        else:
            raise ValueError(f"Unknown metric: {metric}")

    def get_diversification_score(self) -> float:
        """
        Calculate portfolio diversification score (0-100)

        Higher score = better diversification
        Based on average correlation and number of strategies
        """
        n = len(self.strategy_names)
        if n <= 1:
            return 0.0

        # Diversification ratio = 1 / (1 + avg_correlation)
        # Scale to 0-100
        div_ratio = 1 / (1 + abs(self.average_pairwise_correlation))
        score = div_ratio * 100

        return score

    def to_dict(self) -> Dict[str, Any]:
        """Convert results to dictionary"""
        return {
            'strategies_analyzed': len(self.strategy_names),
            'strategy_names': self.strategy_names,
            'portfolio_metrics': {
                'diversification_ratio': round(self.portfolio_diversification_ratio, 4),
                'diversification_score': round(self.get_diversification_score(), 2),
                'average_correlation': round(self.average_pairwise_correlation, 4),
                'max_correlation': round(self.max_pairwise_correlation, 4),
                'min_correlation': round(self.min_pairwise_correlation, 4),
            },
            'correlation_matrix': self.return_correlation_matrix.to_dict(),
            'top_diversifying_pairs': [
                {
                    'strategy1': corr.strategy1_name,
                    'strategy2': corr.strategy2_name,
                    'correlation': round(corr.return_correlation_pearson, 4),
                    'trade_overlap': round(corr.trade_overlap_pct * 100, 2),
                }
                for corr in sorted(self.pairwise_correlations, key=lambda x: abs(x.return_correlation_pearson))[:5]
            ],
            'most_correlated_pairs': [
                {
                    'strategy1': corr.strategy1_name,
                    'strategy2': corr.strategy2_name,
                    'correlation': round(corr.return_correlation_pearson, 4),
                    'trade_overlap': round(corr.trade_overlap_pct * 100, 2),
                }
                for corr in sorted(self.pairwise_correlations, key=lambda x: abs(x.return_correlation_pearson), reverse=True)[:5]
            ],
            'strategy_clusters': self.strategy_clusters,
            'redundant_strategies': self.redundant_strategies,
        }


class StrategyCorrelationAnalyzer:
    """
    Strategy Correlation Analyzer

    Analyzes correlation between multiple trading strategies to identify
    diversification opportunities and redundant strategies.

    Usage:
        config = CorrelationConfig()
        analyzer = StrategyCorrelationAnalyzer(config)

        # Strategy results (daily returns)
        strategy_results = {
            'trend_following': {
                'daily_returns': pd.Series([0.01, -0.02, 0.03, ...]),
                'equity_curve': pd.Series([10000, 10100, 9898, ...]),
            },
            'mean_reversion': {
                'daily_returns': pd.Series([0.02, 0.01, -0.01, ...]),
                'equity_curve': pd.Series([10000, 10200, 10302, ...]),
            },
            'momentum': {
                'daily_returns': pd.Series([0.015, -0.01, 0.02, ...]),
                'equity_curve': pd.Series([10000, 10150, 10048, ...]),
            }
        }

        results = analyzer.analyze(strategy_results)

        print(f"Diversification score: {results.get_diversification_score():.1f}/100")
        print(f"Average correlation: {results.average_pairwise_correlation:.2%}")

        # Check if adding a new strategy improves diversification
        if results.get_diversification_score() > 70:
            print("✅ Well-diversified strategy portfolio!")
        else:
            print("⚠️  Consider adding uncorrelated strategies")
    """

    def __init__(self, config: Optional[CorrelationConfig] = None):
        """Initialize strategy correlation analyzer"""
        self.config = config or CorrelationConfig()
        logger.info(f"Initialized StrategyCorrelationAnalyzer")

    def calculate_pairwise_correlation(
        self,
        strategy1_name: str,
        strategy1_returns: pd.Series,
        strategy1_equity: pd.Series,
        strategy2_name: str,
        strategy2_returns: pd.Series,
        strategy2_equity: pd.Series
    ) -> StrategyPairCorrelation:
        """
        Calculate correlation between two strategies

        Args:
            strategy1_name: Name of first strategy
            strategy1_returns: Daily returns series
            strategy1_equity: Equity curve series
            strategy2_name: Name of second strategy
            strategy2_returns: Daily returns series
            strategy2_equity: Equity curve series

        Returns:
            StrategyPairCorrelation with all correlation metrics
        """
        # Align series by index
        aligned = pd.DataFrame({
            's1_returns': strategy1_returns,
            's2_returns': strategy2_returns,
            's1_equity': strategy1_equity,
            's2_equity': strategy2_equity
        }).dropna()

        # Return correlations
        pearson_corr, pearson_pval = stats.pearsonr(
            aligned['s1_returns'],
            aligned['s2_returns']
        )

        spearman_corr, _ = stats.spearmanr(
            aligned['s1_returns'],
            aligned['s2_returns']
        )

        # Trade overlap (concurrent non-zero returns)
        s1_active = aligned['s1_returns'] != 0
        s2_active = aligned['s2_returns'] != 0
        both_active = s1_active & s2_active

        trade_overlap_pct = both_active.sum() / len(aligned) if len(aligned) > 0 else 0

        # Concurrent wins/losses
        s1_wins = aligned['s1_returns'] > 0
        s2_wins = aligned['s2_returns'] > 0
        concurrent_wins = (s1_wins & s2_wins & both_active).sum()
        concurrent_losses = ((~s1_wins) & (~s2_wins) & both_active).sum()

        concurrent_wins_pct = concurrent_wins / both_active.sum() if both_active.sum() > 0 else 0
        concurrent_losses_pct = concurrent_losses / both_active.sum() if both_active.sum() > 0 else 0

        # Drawdown correlation
        s1_drawdown = self._calculate_drawdown_series(aligned['s1_equity'])
        s2_drawdown = self._calculate_drawdown_series(aligned['s2_equity'])

        dd_corr, _ = stats.pearsonr(s1_drawdown, s2_drawdown) if len(s1_drawdown) > 1 else (0, 1)

        # Rolling correlation
        rolling_corr_mean = None
        rolling_corr_std = None
        rolling_corr_min = None
        rolling_corr_max = None

        if self.config.calculate_rolling and len(aligned) >= self.config.rolling_window:
            rolling_corr = aligned['s1_returns'].rolling(
                window=self.config.rolling_window
            ).corr(aligned['s2_returns'])

            rolling_corr_mean = rolling_corr.mean()
            rolling_corr_std = rolling_corr.std()
            rolling_corr_min = rolling_corr.min()
            rolling_corr_max = rolling_corr.max()

        pair_correlation = StrategyPairCorrelation(
            strategy1_name=strategy1_name,
            strategy2_name=strategy2_name,
            return_correlation_pearson=pearson_corr,
            return_correlation_spearman=spearman_corr,
            return_correlation_pvalue=pearson_pval,
            trade_overlap_pct=trade_overlap_pct,
            concurrent_wins_pct=concurrent_wins_pct,
            concurrent_losses_pct=concurrent_losses_pct,
            drawdown_correlation=dd_corr,
            rolling_correlation_mean=rolling_corr_mean,
            rolling_correlation_std=rolling_corr_std,
            rolling_correlation_min=rolling_corr_min,
            rolling_correlation_max=rolling_corr_max
        )

        return pair_correlation

    def _calculate_drawdown_series(self, equity_curve: pd.Series) -> pd.Series:
        """Calculate running drawdown series"""
        running_max = equity_curve.cummax()
        drawdown = (equity_curve - running_max) / running_max
        return drawdown

    def cluster_strategies(
        self,
        correlation_matrix: pd.DataFrame
    ) -> Dict[str, List[str]]:
        """
        Cluster strategies by correlation using hierarchical clustering

        Args:
            correlation_matrix: Strategy correlation matrix

        Returns:
            Dict of {cluster_name: [strategy_names]}
        """
        # Convert correlation to distance
        distance_matrix = 1 - abs(correlation_matrix)

        # Hierarchical clustering
        linkage = hierarchy.linkage(distance_matrix, method='ward')

        # Cut tree to form clusters
        cluster_labels = hierarchy.fcluster(
            linkage,
            t=self.config.max_clusters,
            criterion='maxclust'
        )

        # Group strategies by cluster
        clusters = {}
        for strategy_idx, cluster_id in enumerate(cluster_labels):
            cluster_name = f"cluster_{cluster_id}"
            if cluster_name not in clusters:
                clusters[cluster_name] = []

            strategy_name = correlation_matrix.index[strategy_idx]
            clusters[cluster_name].append(strategy_name)

        return clusters

    def analyze(
        self,
        strategy_results: Dict[str, Dict[str, pd.Series]]
    ) -> CorrelationResults:
        """
        Run complete strategy correlation analysis

        Args:
            strategy_results: Dict of {strategy_name: {'daily_returns': Series, 'equity_curve': Series}}

        Returns:
            CorrelationResults with complete analysis
        """
        logger.info("="*60)
        logger.info("STRATEGY CORRELATION ANALYSIS STARTING")
        logger.info(f"Analyzing {len(strategy_results)} strategies")
        logger.info("="*60)

        strategy_names = list(strategy_results.keys())

        # Calculate all pairwise correlations
        pairwise_correlations = []

        for i, strategy1 in enumerate(strategy_names):
            for j, strategy2 in enumerate(strategy_names):
                if i < j:  # Only upper triangle (avoid duplicates)
                    pair_corr = self.calculate_pairwise_correlation(
                        strategy1_name=strategy1,
                        strategy1_returns=strategy_results[strategy1]['daily_returns'],
                        strategy1_equity=strategy_results[strategy1]['equity_curve'],
                        strategy2_name=strategy2,
                        strategy2_returns=strategy_results[strategy2]['daily_returns'],
                        strategy2_equity=strategy_results[strategy2]['equity_curve']
                    )
                    pairwise_correlations.append(pair_corr)

        # Build correlation matrices
        n = len(strategy_names)
        return_corr_matrix = np.eye(n)
        drawdown_corr_matrix = np.eye(n)

        for pair_corr in pairwise_correlations:
            i = strategy_names.index(pair_corr.strategy1_name)
            j = strategy_names.index(pair_corr.strategy2_name)

            return_corr_matrix[i, j] = pair_corr.return_correlation_pearson
            return_corr_matrix[j, i] = pair_corr.return_correlation_pearson

            drawdown_corr_matrix[i, j] = pair_corr.drawdown_correlation
            drawdown_corr_matrix[j, i] = pair_corr.drawdown_correlation

        return_corr_df = pd.DataFrame(
            return_corr_matrix,
            index=strategy_names,
            columns=strategy_names
        )

        drawdown_corr_df = pd.DataFrame(
            drawdown_corr_matrix,
            index=strategy_names,
            columns=strategy_names
        )

        # Calculate portfolio metrics
        pairwise_corr_values = [abs(pc.return_correlation_pearson) for pc in pairwise_correlations]

        avg_pairwise_corr = np.mean(pairwise_corr_values) if pairwise_corr_values else 0
        max_pairwise_corr = np.max(pairwise_corr_values) if pairwise_corr_values else 0
        min_pairwise_corr = np.min(pairwise_corr_values) if pairwise_corr_values else 0

        # Diversification ratio (1 / avg correlation)
        div_ratio = 1 / (1 + avg_pairwise_corr)

        # Find most/least correlated pairs
        most_diversifying = min(pairwise_correlations, key=lambda x: abs(x.return_correlation_pearson))
        most_correlated = max(pairwise_correlations, key=lambda x: abs(x.return_correlation_pearson))

        # Identify redundant strategies (high correlation with others)
        redundant_strategies = []
        for strategy in strategy_names:
            high_corr_count = sum(
                1 for pc in pairwise_correlations
                if (pc.strategy1_name == strategy or pc.strategy2_name == strategy)
                and abs(pc.return_correlation_pearson) > self.config.high_correlation_threshold
            )

            if high_corr_count >= 2:  # Highly correlated with 2+ other strategies
                redundant_strategies.append(strategy)

        # Cluster strategies
        strategy_clusters = None
        if self.config.perform_clustering and n > 2:
            strategy_clusters = self.cluster_strategies(return_corr_df)

        # Create results
        results = CorrelationResults(
            config=self.config,
            strategy_names=strategy_names,
            pairwise_correlations=pairwise_correlations,
            return_correlation_matrix=return_corr_df,
            drawdown_correlation_matrix=drawdown_corr_df,
            portfolio_diversification_ratio=div_ratio,
            average_pairwise_correlation=avg_pairwise_corr,
            max_pairwise_correlation=max_pairwise_corr,
            min_pairwise_correlation=min_pairwise_corr,
            strategy_clusters=strategy_clusters,
            most_diversifying_pair=(most_diversifying.strategy1_name, most_diversifying.strategy2_name),
            most_correlated_pair=(most_correlated.strategy1_name, most_correlated.strategy2_name),
            redundant_strategies=redundant_strategies
        )

        logger.info(f"\nCorrelation Analysis Results:")
        logger.info(f"  Average correlation: {avg_pairwise_corr:.2%}")
        logger.info(f"  Diversification score: {results.get_diversification_score():.1f}/100")
        logger.info(f"  Most diversifying pair: {results.most_diversifying_pair}")
        logger.info(f"  Most correlated pair: {results.most_correlated_pair}")

        if redundant_strategies:
            logger.warning(f"  Redundant strategies detected: {redundant_strategies}")

        logger.info("="*60)
        logger.info("STRATEGY CORRELATION ANALYSIS COMPLETE")
        logger.info("="*60)

        return results

    def save_results(self, results: CorrelationResults, filepath: str):
        """Save correlation analysis results to JSON"""
        with open(filepath, 'w') as f:
            json.dump(results.to_dict(), f, indent=2)
        logger.info(f"Saved correlation analysis to {filepath}")

    def load_results(self, filepath: str) -> Dict[str, Any]:
        """Load correlation analysis results from JSON"""
        with open(filepath, 'r') as f:
            results_dict = json.load(f)
        logger.info(f"Loaded correlation analysis from {filepath}")
        return results_dict


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    config = CorrelationConfig()
    analyzer = StrategyCorrelationAnalyzer(config)

    # Example strategy results
    example_strategies = {
        'trend_following': {
            'daily_returns': pd.Series(np.random.normal(0.001, 0.02, 100)),
            'equity_curve': pd.Series(np.cumsum(np.random.normal(100, 20, 100)) + 10000)
        },
        'mean_reversion': {
            'daily_returns': pd.Series(np.random.normal(0.0005, 0.015, 100)),
            'equity_curve': pd.Series(np.cumsum(np.random.normal(50, 15, 100)) + 10000)
        }
    }

    print(f"Strategy Correlation Analyzer initialized")
    print(f"Will analyze {len(example_strategies)} strategies")
