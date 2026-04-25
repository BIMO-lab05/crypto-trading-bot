"""
Correlation Visualization Module
Created: 2025-12-10
Purpose: Enhanced visualizations for strategy correlation analysis

Provides publication-quality visualizations:
- Correlation heatmaps
- Hierarchical clustering dendrograms
- Rolling correlation time series
- Scatter matrix plots
- Network graphs showing strategy relationships
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json

# Optional imports for advanced visualizations
try:
    from scipy.cluster import hierarchy
    from scipy.spatial.distance import pdist, squareform
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logging.warning("scipy not available - some visualizations will be limited")

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    logging.warning("networkx not available - network graphs disabled")

from strategy_correlation import CorrelationResults, StrategyCorrelationAnalyzer

logger = logging.getLogger(__name__)


class CorrelationVisualizer:
    """
    Visualization engine for strategy correlation analysis

    Creates publication-quality charts and exports for correlation analysis:
    - Heatmaps with annotations
    - Dendrograms for hierarchical clustering
    - Rolling correlation charts
    - Network graphs
    - Scatter matrices
    """

    def __init__(self, output_dir: str = "correlation_plots"):
        """
        Initialize visualizer

        Args:
            output_dir: Directory to save visualization files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set plotting style
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (12, 8)
        plt.rcParams['font.size'] = 10

        logger.info(f"Correlation visualizer initialized, output: {self.output_dir}")

    def plot_correlation_heatmap(
        self,
        correlation_matrix: pd.DataFrame,
        title: str = "Strategy Correlation Matrix",
        filename: str = "correlation_heatmap.png",
        annot: bool = True,
        cmap: str = "RdYlGn",
        vmin: float = -1,
        vmax: float = 1
    ) -> str:
        """
        Create correlation heatmap with annotations

        Args:
            correlation_matrix: Strategy correlation matrix
            title: Chart title
            filename: Output filename
            annot: Show correlation values
            cmap: Colormap (RdYlGn, coolwarm, viridis)
            vmin: Minimum color scale value
            vmax: Maximum color scale value

        Returns:
            Path to saved plot
        """
        logger.info(f"Creating correlation heatmap: {title}")

        fig, ax = plt.subplots(figsize=(12, 10))

        # Create heatmap
        sns.heatmap(
            correlation_matrix,
            annot=annot,
            fmt=".2f",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
            center=0,
            square=True,
            linewidths=0.5,
            cbar_kws={"shrink": 0.8, "label": "Correlation"},
            ax=ax
        )

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel("Strategy", fontsize=12)
        ax.set_ylabel("Strategy", fontsize=12)

        # Rotate labels
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)

        plt.tight_layout()

        # Save
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Saved heatmap to {filepath}")
        return str(filepath)

    def plot_dendrogram(
        self,
        correlation_matrix: pd.DataFrame,
        title: str = "Strategy Hierarchical Clustering",
        filename: str = "correlation_dendrogram.png",
        method: str = 'ward'
    ) -> Optional[str]:
        """
        Create dendrogram showing strategy clustering

        Args:
            correlation_matrix: Strategy correlation matrix
            title: Chart title
            filename: Output filename
            method: Linkage method ('ward', 'average', 'complete')

        Returns:
            Path to saved plot or None if scipy unavailable
        """
        if not SCIPY_AVAILABLE:
            logger.warning("scipy not available - cannot create dendrogram")
            return None

        logger.info(f"Creating dendrogram: {title}")

        # Convert correlation to distance
        distance_matrix = 1 - abs(correlation_matrix.values)
        condensed_dist = pdist(distance_matrix)

        # Perform hierarchical clustering
        linkage_matrix = hierarchy.linkage(condensed_dist, method=method)

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 8))

        # Plot dendrogram
        dendro = hierarchy.dendrogram(
            linkage_matrix,
            labels=correlation_matrix.index.tolist(),
            ax=ax,
            color_threshold=0.7 * max(linkage_matrix[:, 2]),
            above_threshold_color='gray'
        )

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel("Strategy", fontsize=12)
        ax.set_ylabel("Distance (1 - |correlation|)", fontsize=12)

        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()

        # Save
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Saved dendrogram to {filepath}")
        return str(filepath)

    def plot_rolling_correlations(
        self,
        strategy_returns: Dict[str, pd.Series],
        window: int = 30,
        pairs: Optional[List[Tuple[str, str]]] = None,
        title: str = "Rolling Correlation (30-day window)",
        filename: str = "rolling_correlations.png"
    ) -> str:
        """
        Plot rolling correlations between strategy pairs over time

        Args:
            strategy_returns: Dict of {strategy_name: returns_series}
            window: Rolling window size in days
            pairs: List of strategy pairs to plot, or None for all pairs
            title: Chart title
            filename: Output filename

        Returns:
            Path to saved plot
        """
        logger.info(f"Creating rolling correlation chart: {title}")

        # Get strategy names
        strategy_names = list(strategy_returns.keys())

        # If no pairs specified, create combinations
        if pairs is None:
            from itertools import combinations
            pairs = list(combinations(strategy_names, 2))
            # Limit to first 5 pairs for readability
            pairs = pairs[:5]

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 8))

        # Plot each pair
        for strategy1, strategy2 in pairs:
            if strategy1 in strategy_returns and strategy2 in strategy_returns:
                # Calculate rolling correlation
                rolling_corr = strategy_returns[strategy1].rolling(
                    window=window
                ).corr(strategy_returns[strategy2])

                # Plot
                ax.plot(
                    rolling_corr.index,
                    rolling_corr.values,
                    label=f"{strategy1} vs {strategy2}",
                    linewidth=2,
                    alpha=0.7
                )

        ax.axhline(y=0, color='black', linestyle='--', alpha=0.3, linewidth=1)
        ax.axhline(y=0.7, color='red', linestyle=':', alpha=0.3, label='High Correlation')
        ax.axhline(y=-0.7, color='blue', linestyle=':', alpha=0.3, label='High Anti-Correlation')

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.set_xlabel("Date", fontsize=12)
        ax.set_ylabel("Rolling Correlation", fontsize=12)
        ax.legend(loc='best', frameon=True, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-1, 1)

        plt.tight_layout()

        # Save
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Saved rolling correlation chart to {filepath}")
        return str(filepath)

    def plot_correlation_network(
        self,
        correlation_matrix: pd.DataFrame,
        threshold: float = 0.5,
        title: str = "Strategy Correlation Network",
        filename: str = "correlation_network.png"
    ) -> Optional[str]:
        """
        Create network graph showing strategy correlations above threshold

        Args:
            correlation_matrix: Strategy correlation matrix
            threshold: Only show correlations above this value
            title: Chart title
            filename: Output filename

        Returns:
            Path to saved plot or None if networkx unavailable
        """
        if not NETWORKX_AVAILABLE:
            logger.warning("networkx not available - cannot create network graph")
            return None

        logger.info(f"Creating correlation network: {title}")

        # Create graph
        G = nx.Graph()

        # Add nodes (strategies)
        strategies = correlation_matrix.index.tolist()
        G.add_nodes_from(strategies)

        # Add edges (correlations above threshold)
        for i, strategy1 in enumerate(strategies):
            for j, strategy2 in enumerate(strategies):
                if i < j:  # Upper triangle only
                    corr = correlation_matrix.iloc[i, j]
                    if abs(corr) >= threshold:
                        G.add_edge(
                            strategy1,
                            strategy2,
                            weight=abs(corr),
                            correlation=corr
                        )

        # Create figure
        fig, ax = plt.subplots(figsize=(14, 12))

        # Layout
        pos = nx.spring_layout(G, k=2, iterations=50)

        # Draw nodes
        node_sizes = [3000] * len(G.nodes())
        nx.draw_networkx_nodes(
            G, pos,
            node_size=node_sizes,
            node_color='lightblue',
            edgecolors='black',
            linewidths=2,
            ax=ax
        )

        # Draw edges with varying thickness
        edges = G.edges()
        weights = [G[u][v]['weight'] for u, v in edges]
        edge_colors = ['red' if G[u][v]['correlation'] > 0 else 'blue' for u, v in edges]

        nx.draw_networkx_edges(
            G, pos,
            width=[w * 5 for w in weights],  # Scale edge width
            edge_color=edge_colors,
            alpha=0.6,
            ax=ax
        )

        # Draw labels
        nx.draw_networkx_labels(
            G, pos,
            font_size=10,
            font_weight='bold',
            ax=ax
        )

        # Add edge labels (correlation values)
        edge_labels = {(u, v): f"{G[u][v]['correlation']:.2f}" for u, v in edges}
        nx.draw_networkx_edge_labels(
            G, pos,
            edge_labels=edge_labels,
            font_size=8,
            ax=ax
        )

        ax.set_title(title, fontsize=14, fontweight='bold', pad=20)
        ax.axis('off')

        # Legend
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color='red', linewidth=3, label='Positive Correlation'),
            Line2D([0], [0], color='blue', linewidth=3, label='Negative Correlation'),
        ]
        ax.legend(handles=legend_elements, loc='upper right', fontsize=10)

        plt.tight_layout()

        # Save
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Saved correlation network to {filepath}")
        return str(filepath)

    def plot_scatter_matrix(
        self,
        strategy_returns: Dict[str, pd.Series],
        title: str = "Strategy Returns Scatter Matrix",
        filename: str = "scatter_matrix.png",
        max_strategies: int = 5
    ) -> str:
        """
        Create scatter matrix showing pairwise relationships

        Args:
            strategy_returns: Dict of {strategy_name: returns_series}
            title: Chart title
            filename: Output filename
            max_strategies: Maximum number of strategies to include

        Returns:
            Path to saved plot
        """
        logger.info(f"Creating scatter matrix: {title}")

        # Limit number of strategies for readability
        strategy_names = list(strategy_returns.keys())[:max_strategies]

        # Create DataFrame
        df = pd.DataFrame({
            name: strategy_returns[name]
            for name in strategy_names
        })

        # Create scatter matrix
        fig = pd.plotting.scatter_matrix(
            df,
            figsize=(14, 14),
            alpha=0.5,
            diagonal='kde',
            grid=True
        )

        # Add overall title
        plt.suptitle(title, fontsize=14, fontweight='bold', y=1.0)
        plt.tight_layout()

        # Save
        filepath = self.output_dir / filename
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        plt.close()

        logger.info(f"Saved scatter matrix to {filepath}")
        return str(filepath)

    def generate_comprehensive_report(
        self,
        results: CorrelationResults,
        strategy_returns: Dict[str, pd.Series],
        report_name: str = "correlation_analysis"
    ) -> Dict[str, str]:
        """
        Generate complete visualization suite

        Args:
            results: Correlation analysis results
            strategy_returns: Dict of {strategy_name: returns_series}
            report_name: Base name for report files

        Returns:
            Dict of {visualization_type: filepath}
        """
        logger.info("="*60)
        logger.info("GENERATING COMPREHENSIVE VISUALIZATION REPORT")
        logger.info("="*60)

        generated_files = {}

        # 1. Correlation heatmap
        try:
            filepath = self.plot_correlation_heatmap(
                results.return_correlation_matrix,
                title=f"Strategy Correlation Matrix ({len(results.strategy_names)} Strategies)",
                filename=f"{report_name}_heatmap.png"
            )
            generated_files['heatmap'] = filepath
            logger.info(f"✅ Heatmap created")
        except Exception as e:
            logger.error(f"❌ Heatmap failed: {e}")

        # 2. Dendrogram
        try:
            filepath = self.plot_dendrogram(
                results.return_correlation_matrix,
                title="Strategy Hierarchical Clustering",
                filename=f"{report_name}_dendrogram.png"
            )
            if filepath:
                generated_files['dendrogram'] = filepath
                logger.info(f"✅ Dendrogram created")
        except Exception as e:
            logger.error(f"❌ Dendrogram failed: {e}")

        # 3. Rolling correlations
        try:
            filepath = self.plot_rolling_correlations(
                strategy_returns,
                window=30,
                title="Rolling 30-Day Correlation",
                filename=f"{report_name}_rolling_correlations.png"
            )
            generated_files['rolling_correlations'] = filepath
            logger.info(f"✅ Rolling correlations created")
        except Exception as e:
            logger.error(f"❌ Rolling correlations failed: {e}")

        # 4. Correlation network
        try:
            filepath = self.plot_correlation_network(
                results.return_correlation_matrix,
                threshold=0.5,
                title="Strategy Correlation Network (|r| > 0.5)",
                filename=f"{report_name}_network.png"
            )
            if filepath:
                generated_files['network'] = filepath
                logger.info(f"✅ Network graph created")
        except Exception as e:
            logger.error(f"❌ Network graph failed: {e}")

        # 5. Scatter matrix (limited to 5 strategies)
        try:
            filepath = self.plot_scatter_matrix(
                strategy_returns,
                title="Strategy Returns Distribution & Relationships",
                filename=f"{report_name}_scatter_matrix.png",
                max_strategies=5
            )
            generated_files['scatter_matrix'] = filepath
            logger.info(f"✅ Scatter matrix created")
        except Exception as e:
            logger.error(f"❌ Scatter matrix failed: {e}")

        # 6. Drawdown correlation heatmap
        try:
            filepath = self.plot_correlation_heatmap(
                results.drawdown_correlation_matrix,
                title="Drawdown Correlation Matrix",
                filename=f"{report_name}_drawdown_heatmap.png",
                cmap="YlOrRd"
            )
            generated_files['drawdown_heatmap'] = filepath
            logger.info(f"✅ Drawdown heatmap created")
        except Exception as e:
            logger.error(f"❌ Drawdown heatmap failed: {e}")

        # Save summary
        summary_file = self.output_dir / f"{report_name}_summary.json"
        summary = {
            'timestamp': pd.Timestamp.now().isoformat(),
            'strategies_analyzed': len(results.strategy_names),
            'strategy_names': results.strategy_names,
            'average_correlation': float(results.average_pairwise_correlation),
            'diversification_score': float(results.get_diversification_score()),
            'generated_files': generated_files,
            'output_directory': str(self.output_dir)
        }

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info("="*60)
        logger.info(f"VISUALIZATION REPORT COMPLETE")
        logger.info(f"Generated {len(generated_files)} visualizations")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info("="*60)

        return generated_files


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create sample data
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=100, freq='D')

    example_strategies = {
        'trend_following': pd.Series(np.random.normal(0.001, 0.02, 100), index=dates),
        'mean_reversion': pd.Series(np.random.normal(0.0005, 0.015, 100), index=dates),
        'momentum': pd.Series(np.random.normal(0.0008, 0.018, 100), index=dates),
    }

    # Create visualizer
    visualizer = CorrelationVisualizer(output_dir="example_plots")

    # Generate heatmap
    corr_matrix = pd.DataFrame(
        [[1.0, 0.3, 0.7],
         [0.3, 1.0, -0.2],
         [0.7, -0.2, 1.0]],
        index=example_strategies.keys(),
        columns=example_strategies.keys()
    )

    visualizer.plot_correlation_heatmap(
        corr_matrix,
        title="Example Correlation Matrix"
    )

    visualizer.plot_rolling_correlations(
        example_strategies,
        window=20,
        title="Example Rolling Correlations"
    )

    print("Example visualizations created in 'example_plots' directory")
