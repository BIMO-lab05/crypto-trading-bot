"""
Model Validation System
Purpose: Compare new models against production models and decide deployment
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class ModelValidator:
    """
    Validate new models against current production models

    Determines if new model should be deployed based on:
    - R² improvement threshold
    - Loss reduction threshold
    - No significant metric degradation
    - Minimum performance thresholds
    """

    def __init__(self):
        """Initialize model validator"""
        self.settings = get_settings()

    def validate_model(
        self,
        new_metrics: Dict[str, float],
        current_metrics: Optional[Dict[str, float]] = None,
        symbol: str = ""
    ) -> Dict[str, Any]:
        """
        Validate if new model should be deployed

        Args:
            new_metrics: Metrics from newly trained model
            current_metrics: Metrics from current production model (None if first model)
            symbol: Trading symbol for logging

        Returns:
            Dict containing:
                - is_valid: bool - Whether model passes all validation checks
                - should_deploy: bool - Whether model should be deployed
                - validation_checks: Dict - Results of individual checks
                - improvement_pct: float - Percentage improvement vs current
                - reason: str - Explanation of decision
        """
        logger.info(f"Validating model for {symbol}")

        validation_checks = {}
        reasons = []

        # Extract validation R² (or test R² if validation not available)
        new_r2 = new_metrics.get('val_r2', new_metrics.get('test_r2', 0))
        new_loss = new_metrics.get('val_loss', new_metrics.get('test_loss', 999))
        new_mae = new_metrics.get('val_mae', new_metrics.get('test_mae', 999))

        # Check 1: Minimum performance thresholds
        min_r2_check = new_r2 >= self.settings.retrain_min_r2
        validation_checks['min_r2'] = {
            'passed': min_r2_check,
            'value': new_r2,
            'threshold': self.settings.retrain_min_r2,
        }

        if not min_r2_check:
            reasons.append(
                f"R² ({new_r2:.4f}) below minimum threshold "
                f"({self.settings.retrain_min_r2})"
            )

        # Check 2: Loss threshold (max acceptable)
        max_loss = 0.05  # Maximum acceptable loss
        loss_check = new_loss < max_loss
        validation_checks['max_loss'] = {
            'passed': loss_check,
            'value': new_loss,
            'threshold': max_loss,
        }

        if not loss_check:
            reasons.append(
                f"Loss ({new_loss:.4f}) above maximum threshold ({max_loss})"
            )

        # If no current model, just check minimums
        if current_metrics is None:
            logger.info("No current model - validating against minimum thresholds only")

            is_valid = min_r2_check and loss_check
            should_deploy = is_valid

            if is_valid:
                reasons.append("First model - passed minimum thresholds")
            else:
                reasons.append("First model - failed minimum thresholds")

            return {
                "is_valid": is_valid,
                "should_deploy": should_deploy,
                "validation_checks": validation_checks,
                "improvement_pct": 0.0,
                "reason": "; ".join(reasons),
                "new_metrics": {
                    "r2": new_r2,
                    "loss": new_loss,
                    "mae": new_mae,
                },
            }

        # Compare with current model
        current_r2 = current_metrics.get('val_r2', current_metrics.get('test_r2', 0))
        current_loss = current_metrics.get('val_loss', current_metrics.get('test_loss', 999))
        current_mae = current_metrics.get('val_mae', current_metrics.get('test_mae', 999))

        # Check 3: R² improvement
        r2_improvement = new_r2 - current_r2
        r2_improvement_pct = (r2_improvement / current_r2 * 100) if current_r2 > 0 else 0

        r2_improvement_check = r2_improvement >= self.settings.retrain_min_improvement
        validation_checks['r2_improvement'] = {
            'passed': r2_improvement_check,
            'new_value': new_r2,
            'current_value': current_r2,
            'improvement': r2_improvement,
            'improvement_pct': r2_improvement_pct,
            'threshold': self.settings.retrain_min_improvement,
        }

        if r2_improvement_check:
            reasons.append(
                f"R² improved by {r2_improvement:.4f} "
                f"({r2_improvement_pct:+.2f}%)"
            )
        else:
            reasons.append(
                f"R² improvement ({r2_improvement:.4f}) below threshold "
                f"({self.settings.retrain_min_improvement})"
            )

        # Check 4: Loss reduction
        loss_reduction = current_loss - new_loss
        loss_reduction_pct = (loss_reduction / current_loss * 100) if current_loss > 0 else 0

        # Require at least 5% loss reduction
        min_loss_reduction = 0.05
        loss_reduction_check = loss_reduction >= (current_loss * min_loss_reduction)

        validation_checks['loss_reduction'] = {
            'passed': loss_reduction_check,
            'new_value': new_loss,
            'current_value': current_loss,
            'reduction': loss_reduction,
            'reduction_pct': loss_reduction_pct,
            'threshold_pct': min_loss_reduction * 100,
        }

        if loss_reduction_check:
            reasons.append(
                f"Loss reduced by {loss_reduction:.4f} "
                f"({loss_reduction_pct:+.2f}%)"
            )

        # Check 5: No significant degradation in any metric
        max_degradation = self.settings.retrain_max_degradation

        # Check MAE degradation
        mae_change = new_mae - current_mae
        mae_change_pct = (mae_change / current_mae) if current_mae > 0 else 0

        mae_degradation_check = mae_change_pct <= max_degradation
        validation_checks['mae_degradation'] = {
            'passed': mae_degradation_check,
            'new_value': new_mae,
            'current_value': current_mae,
            'change': mae_change,
            'change_pct': mae_change_pct * 100,
            'max_allowed_pct': max_degradation * 100,
        }

        if not mae_degradation_check:
            reasons.append(
                f"MAE degraded by {mae_change_pct*100:.2f}% "
                f"(max allowed: {max_degradation*100:.0f}%)"
            )

        # Overall validation
        is_valid = all([
            min_r2_check,
            loss_check,
            mae_degradation_check,
        ])

        # Deployment decision
        # Deploy if:
        # 1. Valid (passes all checks)
        # 2. R² improvement OR loss reduction (at least one metric improved)
        should_deploy = is_valid and (r2_improvement_check or loss_reduction_check)

        if should_deploy:
            reasons.append("✅ APPROVED FOR DEPLOYMENT")
        elif is_valid:
            reasons.append("⚠️ Valid but no significant improvement - deployment not recommended")
        else:
            reasons.append("❌ REJECTED - failed validation checks")

        logger.info(
            f"Validation complete: "
            f"Valid={is_valid}, Deploy={should_deploy}, "
            f"R² {current_r2:.4f}→{new_r2:.4f} ({r2_improvement_pct:+.2f}%)"
        )

        return {
            "is_valid": is_valid,
            "should_deploy": should_deploy,
            "validation_checks": validation_checks,
            "improvement_pct": r2_improvement_pct,
            "reason": "; ".join(reasons),
            "new_metrics": {
                "r2": new_r2,
                "loss": new_loss,
                "mae": new_mae,
            },
            "current_metrics": {
                "r2": current_r2,
                "loss": current_loss,
                "mae": current_mae,
            },
            "changes": {
                "r2_change": r2_improvement,
                "r2_change_pct": r2_improvement_pct,
                "loss_change": loss_reduction,
                "loss_change_pct": loss_reduction_pct,
                "mae_change": mae_change,
                "mae_change_pct": mae_change_pct * 100,
            }
        }

    def compare_models(
        self,
        models: List[Dict[str, Any]],
        metric: str = "val_r2"
    ) -> Dict[str, Any]:
        """
        Compare multiple models and rank them

        Args:
            models: List of dicts with 'metrics' and 'metadata'
            metric: Metric to use for ranking (higher is better for R²)

        Returns:
            Dict with ranked models and comparison
        """
        logger.info(f"Comparing {len(models)} models by {metric}")

        # Extract metric values
        model_scores = []
        for i, model in enumerate(models):
            metrics = model.get('metrics', {})
            score = metrics.get(metric, 0)
            model_scores.append({
                'index': i,
                'score': score,
                'model': model,
            })

        # Sort by score (descending for R², ascending for loss)
        reverse = not metric.endswith('loss')  # Higher is better for R², lower is better for loss
        model_scores.sort(key=lambda x: x['score'], reverse=reverse)

        # Calculate differences
        if len(model_scores) > 1:
            best = model_scores[0]
            worst = model_scores[-1]

            improvement = best['score'] - worst['score']
            improvement_pct = (improvement / worst['score'] * 100) if worst['score'] != 0 else 0

            logger.info(
                f"Best model: {metric}={best['score']:.4f}, "
                f"Improvement over worst: {improvement_pct:+.2f}%"
            )
        else:
            improvement = 0
            improvement_pct = 0

        return {
            "ranked_models": model_scores,
            "best_model": model_scores[0] if model_scores else None,
            "worst_model": model_scores[-1] if len(model_scores) > 1 else None,
            "metric_used": metric,
            "improvement": improvement,
            "improvement_pct": improvement_pct,
        }

    def generate_validation_report(
        self,
        validation_result: Dict[str, Any],
        symbol: str,
        version: str
    ) -> Dict[str, Any]:
        """
        Generate comprehensive validation report

        Args:
            validation_result: Result from validate_model()
            symbol: Trading symbol
            version: Model version

        Returns:
            Formatted validation report
        """
        report = {
            "symbol": symbol,
            "version": version,
            "timestamp": datetime.now().isoformat(),
            "decision": {
                "is_valid": validation_result["is_valid"],
                "should_deploy": validation_result["should_deploy"],
                "reason": validation_result["reason"],
            },
            "performance": {
                "new_model": validation_result.get("new_metrics", {}),
                "current_model": validation_result.get("current_metrics", {}),
                "changes": validation_result.get("changes", {}),
            },
            "validation_checks": validation_result["validation_checks"],
            "overall_improvement": validation_result["improvement_pct"],
        }

        # Add recommendations
        recommendations = []

        if validation_result["should_deploy"]:
            recommendations.append("Deploy new model to production")
            recommendations.append("Monitor performance for first 24 hours")
            recommendations.append("Be prepared to rollback if issues detected")
        elif validation_result["is_valid"]:
            recommendations.append("Model is valid but shows minimal improvement")
            recommendations.append("Consider collecting more training data")
            recommendations.append("Try different hyperparameters")
        else:
            recommendations.append("Do NOT deploy - model failed validation")
            recommendations.append("Review training data quality")
            recommendations.append("Check for overfitting")
            recommendations.append("Consider different architecture or features")

        report["recommendations"] = recommendations

        return report
