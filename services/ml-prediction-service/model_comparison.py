#!/usr/bin/env python3
"""
Model Performance Comparison Tool
Purpose: Compare baseline models vs optimized models
Generate detailed performance reports with visualizations

Author: ML Optimization Agent
Date: 2025-11-20
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ModelComparator:
    """
    Compare baseline and optimized models
    Generate comprehensive performance reports
    """

    def __init__(self):
        """Initialize comparator"""
        self.baseline_dir = Path('services/ml-prediction-service/trained_models')
        self.optimized_dir = Path('services/ml-prediction-service/trained_models_optimized')
        self.baseline_results = None
        self.optimized_results = None

    def load_baseline_results(self) -> Dict:
        """Load baseline model training results"""
        try:
            results_file = self.baseline_dir / 'training_results.json'
            if not results_file.exists():
                logger.warning(f"Baseline results not found: {results_file}")
                return {}

            with open(results_file, 'r') as f:
                data = json.load(f)

            logger.info(f"Loaded baseline results from {results_file}")
            return data

        except Exception as e:
            logger.error(f"Error loading baseline results: {e}")
            return {}

    def load_optimized_results(self) -> Dict:
        """Load optimized model results"""
        try:
            results_file = self.optimized_dir / 'optimization_results.json'
            if not results_file.exists():
                logger.warning(f"Optimized results not found: {results_file}")
                return {}

            with open(results_file, 'r') as f:
                data = json.load(f)

            logger.info(f"Loaded optimized results from {results_file}")
            return data

        except Exception as e:
            logger.error(f"Error loading optimized results: {e}")
            return {}

    def compare_models(self) -> pd.DataFrame:
        """
        Create comparison table between baseline and optimized models

        Returns:
            DataFrame with comparison metrics
        """
        # Load results
        baseline = self.load_baseline_results()
        optimized = self.load_optimized_results()

        if not baseline or not optimized:
            logger.error("Cannot compare - missing results")
            return pd.DataFrame()

        # Extract baseline results
        baseline_results = baseline.get('results', [])

        # Create comparison data
        comparison_data = []

        for opt_result in optimized:
            symbol = opt_result.get('symbol')
            model_type = opt_result.get('model_type')

            # Find corresponding baseline result
            baseline_result = next(
                (r for r in baseline_results if r.get('symbol') == symbol and r.get('model_type') == model_type),
                None
            )

            if baseline_result:
                # Extract metrics
                baseline_r2 = baseline_result.get('r2_score', 0)
                optimized_r2 = opt_result.get('final_metrics', {}).get('r2_score', 0)

                baseline_mae = baseline_result.get('mae', 0)
                optimized_mae = opt_result.get('final_metrics', {}).get('mae', 0)

                baseline_rmse = baseline_result.get('rmse', 0)
                optimized_rmse = opt_result.get('final_metrics', {}).get('rmse', 0)

                # Calculate improvements
                r2_improvement = optimized_r2 - baseline_r2
                r2_improvement_pct = (r2_improvement / abs(baseline_r2)) * 100 if baseline_r2 != 0 else 0

                mae_improvement = baseline_mae - optimized_mae
                mae_improvement_pct = (mae_improvement / baseline_mae) * 100 if baseline_mae != 0 else 0

                rmse_improvement = baseline_rmse - optimized_rmse
                rmse_improvement_pct = (rmse_improvement / baseline_rmse) * 100 if baseline_rmse != 0 else 0

                comparison_data.append({
                    'Symbol': symbol,
                    'Model': model_type,
                    'Baseline_R2': baseline_r2,
                    'Optimized_R2': optimized_r2,
                    'R2_Improvement': r2_improvement,
                    'R2_Improvement_Pct': r2_improvement_pct,
                    'Baseline_MAE': baseline_mae,
                    'Optimized_MAE': optimized_mae,
                    'MAE_Improvement': mae_improvement,
                    'MAE_Improvement_Pct': mae_improvement_pct,
                    'Baseline_RMSE': baseline_rmse,
                    'Optimized_RMSE': optimized_rmse,
                    'RMSE_Improvement': rmse_improvement,
                    'RMSE_Improvement_Pct': rmse_improvement_pct,
                    'Directional_Accuracy': opt_result.get('final_metrics', {}).get('directional_accuracy', 0)
                })

        df = pd.DataFrame(comparison_data)
        return df

    def generate_report(self) -> str:
        """
        Generate comprehensive comparison report

        Returns:
            Markdown formatted report
        """
        df = self.compare_models()

        if df.empty:
            return "# Model Comparison Report\n\nNo data available for comparison."

        report = []
        report.append("# ML Model Optimization Report")
        report.append(f"\nGenerated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        report.append("\n---\n")

        # Executive Summary
        report.append("## Executive Summary\n")
        avg_r2_improvement = df['R2_Improvement'].mean()
        avg_r2_improvement_pct = df['R2_Improvement_Pct'].mean()
        best_model = df.loc[df['Optimized_R2'].idxmax()]

        report.append(f"- **Average R² Improvement**: {avg_r2_improvement:.4f} ({avg_r2_improvement_pct:+.2f}%)")
        report.append(f"- **Best Performing Model**: {best_model['Symbol']} {best_model['Model']} (R²={best_model['Optimized_R2']:.4f})")
        report.append(f"- **Models Meeting Target**: {len(df[df['Optimized_R2'] >= 0.95])}/{len(df)} achieved R² ≥ 0.95")
        report.append("\n---\n")

        # Performance Table
        report.append("## Performance Comparison Table\n")
        report.append("| Symbol | Model | Baseline R² | Optimized R² | Improvement | MAE Improvement | RMSE Improvement |")
        report.append("|--------|-------|-------------|--------------|-------------|-----------------|------------------|")

        for _, row in df.iterrows():
            report.append(
                f"| {row['Symbol']} | {row['Model']} | "
                f"{row['Baseline_R2']:.4f} | {row['Optimized_R2']:.4f} | "
                f"{row['R2_Improvement']:+.4f} ({row['R2_Improvement_Pct']:+.2f}%) | "
                f"{row['MAE_Improvement_Pct']:+.2f}% | "
                f"{row['RMSE_Improvement_Pct']:+.2f}% |"
            )

        report.append("\n---\n")

        # Detailed Analysis per Symbol
        report.append("## Detailed Analysis by Symbol\n")

        for symbol in df['Symbol'].unique():
            symbol_df = df[df['Symbol'] == symbol]

            report.append(f"\n### {symbol}\n")

            for _, row in symbol_df.iterrows():
                model_type = row['Model']
                meets_target = "✓" if row['Optimized_R2'] >= 0.95 else "✗"

                report.append(f"\n#### {model_type} Model {meets_target}\n")
                report.append(f"**Performance Metrics:**")
                report.append(f"- R² Score: {row['Baseline_R2']:.4f} → {row['Optimized_R2']:.4f} ({row['R2_Improvement']:+.4f})")
                report.append(f"- MAE: {row['Baseline_MAE']:.4f} → {row['Optimized_MAE']:.4f} ({row['MAE_Improvement_Pct']:+.2f}%)")
                report.append(f"- RMSE: {row['Baseline_RMSE']:.4f} → {row['Optimized_RMSE']:.4f} ({row['RMSE_Improvement_Pct']:+.2f}%)")
                report.append(f"- Directional Accuracy: {row['Directional_Accuracy']:.2%}")
                report.append("")

        report.append("\n---\n")

        # Key Findings
        report.append("## Key Findings\n")

        # Best improvements
        best_r2_improvement = df.loc[df['R2_Improvement'].idxmax()]
        best_mae_improvement = df.loc[df['MAE_Improvement_Pct'].idxmax()]

        report.append(f"**Largest R² Improvement:**")
        report.append(f"- {best_r2_improvement['Symbol']} {best_r2_improvement['Model']}: "
                     f"{best_r2_improvement['R2_Improvement']:+.4f} ({best_r2_improvement['R2_Improvement_Pct']:+.2f}%)")
        report.append("")

        report.append(f"**Largest MAE Improvement:**")
        report.append(f"- {best_mae_improvement['Symbol']} {best_mae_improvement['Model']}: "
                     f"{best_mae_improvement['MAE_Improvement_Pct']:+.2f}%")
        report.append("")

        # Models not meeting target
        not_meeting_target = df[df['Optimized_R2'] < 0.95]
        if not not_meeting_target.empty:
            report.append(f"**Models Not Meeting Target (R² < 0.95):**")
            for _, row in not_meeting_target.iterrows():
                report.append(f"- {row['Symbol']} {row['Model']}: R²={row['Optimized_R2']:.4f} "
                             f"(needs {0.95 - row['Optimized_R2']:.4f} more)")
            report.append("")

        report.append("\n---\n")

        # Recommendations
        report.append("## Recommendations\n")

        report.append("**For Production Deployment:**")
        production_ready = df[df['Optimized_R2'] >= 0.95]
        if not production_ready.empty:
            for _, row in production_ready.iterrows():
                report.append(f"- ✓ Deploy {row['Symbol']} {row['Model']} (R²={row['Optimized_R2']:.4f})")
        else:
            report.append("- No models currently meet production threshold (R² ≥ 0.95)")

        report.append("")
        report.append("**For Further Optimization:**")
        needs_optimization = df[df['Optimized_R2'] < 0.95]
        if not needs_optimization.empty:
            for _, row in needs_optimization.iterrows():
                report.append(f"- Continue tuning {row['Symbol']} {row['Model']}")
                report.append(f"  - Current: R²={row['Optimized_R2']:.4f}")
                report.append(f"  - Target: R²=0.95")
                report.append(f"  - Gap: {0.95 - row['Optimized_R2']:.4f}")

        report.append("\n---\n")

        # Optimization Strategy Insights
        report.append("## Optimization Strategy Insights\n")
        report.append("**Techniques Applied:**")
        report.append("- Bayesian hyperparameter optimization with Optuna (50 trials)")
        report.append("- Enhanced feature engineering (40+ technical indicators)")
        report.append("- Advanced architecture (2-4 layers, batch normalization)")
        report.append("- Regularization (L2, dropout, recurrent dropout)")
        report.append("- Learning rate scheduling (ReduceLROnPlateau)")
        report.append("- Early stopping (patience=20)")
        report.append("- Multiple scaler types (MinMax, Standard, Robust)")
        report.append("- Multiple optimizers (Adam, AdamW, RMSprop)")
        report.append("")

        return "\n".join(report)

    def save_report(self, filename: str = 'optimization_report.md'):
        """
        Generate and save comparison report to file

        Args:
            filename: Output filename
        """
        report = self.generate_report()

        output_dir = Path('services/ml-prediction-service/trained_models_optimized')
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / filename

        with open(output_path, 'w') as f:
            f.write(report)

        logger.info(f"Saved comparison report to {output_path}")
        print(f"\nReport saved to: {output_path}")

        # Also print to console
        print("\n" + "="*80)
        print(report)
        print("="*80 + "\n")

    def get_best_hyperparameters(self, symbol: str, model_type: str) -> Dict:
        """
        Get best hyperparameters for a specific model

        Args:
            symbol: Trading symbol
            model_type: Model type (GRU or LSTM)

        Returns:
            Dictionary with best hyperparameters
        """
        optimized = self.load_optimized_results()

        if not optimized:
            return {}

        result = next(
            (r for r in optimized if r.get('symbol') == symbol and r.get('model_type') == model_type),
            None
        )

        if result:
            return result.get('best_hyperparameters', {})

        return {}

    def export_hyperparameters_csv(self, filename: str = 'best_hyperparameters.csv'):
        """
        Export all best hyperparameters to CSV for easy reference

        Args:
            filename: Output CSV filename
        """
        optimized = self.load_optimized_results()

        if not optimized:
            logger.warning("No optimized results to export")
            return

        export_data = []

        for result in optimized:
            params = result.get('best_hyperparameters', {})
            metrics = result.get('final_metrics', {})

            row = {
                'symbol': result.get('symbol'),
                'model_type': result.get('model_type'),
                'r2_score': metrics.get('r2_score', 0),
                'mae': metrics.get('mae', 0),
                'rmse': metrics.get('rmse', 0)
            }
            row.update(params)

            export_data.append(row)

        df = pd.DataFrame(export_data)

        output_dir = Path('services/ml-prediction-service/trained_models_optimized')
        output_path = output_dir / filename

        df.to_csv(output_path, index=False)
        logger.info(f"Exported hyperparameters to {output_path}")
        print(f"\nHyperparameters exported to: {output_path}")


def main():
    """
    Main execution
    Generate comparison reports
    """
    logger.info("Starting model comparison analysis...")

    comparator = ModelComparator()

    # Generate and save report
    comparator.save_report('optimization_report.md')

    # Export hyperparameters
    comparator.export_hyperparameters_csv('best_hyperparameters.csv')

    logger.info("Comparison analysis complete!")


if __name__ == "__main__":
    main()
