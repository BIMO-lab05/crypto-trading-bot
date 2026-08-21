"""
Model Validation System
Purpose: Compare new models against production models and decide deployment
"""

import logging
import math
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

    def _check_optional_gate(
        self,
        *,
        name: str,
        key: str,
        setting_field: str,
        value: Optional[float],
        threshold: Optional[float],
        validation_checks: Dict[str, Any],
        reasons: List[str],
        fail_closed: bool = False,
    ) -> bool:
        """
        Generic optional minimum-threshold gate.

        Returns True when the gate passes or the threshold is None
        (disabled). When the value is missing/NaN (older artifacts /
        degenerate test set) the behaviour is per-gate explicit:

        - ``fail_closed=False`` (legacy): the gate is skipped and the
          model passes on the remaining checks (fail-open).
        - ``fail_closed=True``: with the gate ENABLED (threshold set), a
          missing/NaN metric FAILS the gate (passed=False, reason
          'metric unavailable') — matching edge_lab gate2 semantics
          where an uncomputable gating metric is a REJECT, never a pass
          (SEV-6 fix 2026-08). With the threshold None the metric is
          still recorded informationally.

        Returns False when a threshold is configured and the value fails
        to clear it, or when ``fail_closed`` and the value is
        unavailable. Always records the value in
        ``validation_checks[key]`` for observability — passed is None
        when the gate didn't fire (disabled / unavailable+fail-open),
        bool when it did.

        Args:
            name: Human label for the metric in log messages
                (e.g. ``"DSR"``, ``"R²(returns)"``, ``"Dir.Acc"``).
            key: Slot in ``validation_checks`` (e.g. ``"dsr"``,
                ``"r2_returns"``, ``"dir_acc_corrected"``).
            setting_field: Name of the corresponding settings field
                referenced in the informational note (so operators know
                which env var enables the gate).
            value: The metric value from the new model's metrics dict.
            threshold: The configured threshold, or None to disable.
            validation_checks: Mutated in-place with the gate's record.
            reasons: Mutated in-place with a one-line explanation when
                a real (non-None) threshold actually fires.
        """
        if value is None or (isinstance(value, float) and math.isnan(value)):
            if threshold is not None and fail_closed:
                # Gate is enabled but the metric cannot be computed:
                # FAIL CLOSED (edge_lab gate2 semantics). A model whose
                # DSR is unmeasurable must not deploy through the gate.
                validation_checks[key] = {
                    'passed': False,
                    'value': value,
                    'threshold': threshold,
                    'note': f'{name} metric unavailable (missing or NaN); '
                            'gate enabled — failing closed',
                }
                reasons.append(
                    f"{name} metric unavailable — gate enabled, failing closed"
                )
                return False
            validation_checks[key] = {
                'passed': None,
                'value': value,
                'threshold': threshold,
                'note': f'{name} unavailable (missing or NaN); gate not applied',
            }
            return True
        if threshold is None:
            validation_checks[key] = {
                'passed': None,
                'value': value,
                'threshold': None,
                'note': f'{name} informational only (set {setting_field} to gate)',
            }
            return True
        passed = value >= threshold
        validation_checks[key] = {
            'passed': passed,
            'value': value,
            'threshold': threshold,
        }
        if passed:
            reasons.append(f"{name}={value:.4f} clears gate ({threshold})")
        else:
            reasons.append(f"{name} ({value:.4f}) below gate ({threshold})")
        return passed

    def _check_dsr_gate(
        self,
        new_dsr: Optional[float],
        validation_checks: Dict[str, Any],
        reasons: List[str],
    ) -> bool:
        """Deflated Sharpe Ratio gate. ON by default at 0.95 and FAIL-CLOSED
        on a missing/NaN DSR (settings.retrain_min_dsr, SEV-6 fix 2026-08)."""
        return self._check_optional_gate(
            name="DSR",
            key="dsr",
            setting_field="retrain_min_dsr",
            value=new_dsr,
            threshold=self.settings.retrain_min_dsr,
            validation_checks=validation_checks,
            reasons=reasons,
            # DSR is the honesty gate: unmeasurable ⇒ REJECT (fail closed).
            fail_closed=True,
        )

    def _check_r2_returns_gate(
        self,
        new_r2_returns: Optional[float],
        validation_checks: Dict[str, Any],
        reasons: List[str],
    ) -> bool:
        """R²-on-log-returns gate. Off by default (settings.retrain_min_r2_returns)."""
        return self._check_optional_gate(
            name="R²(returns)",
            key="r2_returns",
            setting_field="retrain_min_r2_returns",
            value=new_r2_returns,
            threshold=self.settings.retrain_min_r2_returns,
            validation_checks=validation_checks,
            reasons=reasons,
            # Per-gate explicit (SEV-6): T0.1 pre-flight gates stay
            # fail-open on a missing metric — they gate older artifacts
            # that never recorded these metrics. Only DSR fails closed.
            fail_closed=False,
        )

    def _check_dir_acc_gate(
        self,
        new_dir_acc: Optional[float],
        validation_checks: Dict[str, Any],
        reasons: List[str],
    ) -> bool:
        """Corrected directional-accuracy gate. Off by default (settings.retrain_min_dir_acc)."""
        return self._check_optional_gate(
            name="Dir.Acc",
            key="dir_acc_corrected",
            setting_field="retrain_min_dir_acc",
            value=new_dir_acc,
            threshold=self.settings.retrain_min_dir_acc,
            validation_checks=validation_checks,
            reasons=reasons,
            # Per-gate explicit (SEV-6): fail-open, see r2_returns note.
            fail_closed=False,
        )

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
        # Deflated Sharpe Ratio from evaluation-time CPCV. Decision of
        # record (SEV-5, 2026-08): the deploy gate consumes the honest-N
        # variant 'test_cpcv_dsr' (num_trials = max(valid paths, total
        # CPCV path count, e.g. 45 at the pinned 10/2)); the legacy
        # 'test_dsr' (num_trials = valid-path count, under-deflated
        # whenever degenerate paths are dropped) is read only as a
        # fallback for older artifacts that predate the honest-N key.
        # May be missing (older artifacts) or NaN (degenerate test set /
        # zero-variance strategy returns). While retrain_min_dsr is set
        # (default 0.95) a missing/NaN DSR FAILS CLOSED; threshold None
        # records it informationally only.
        if 'test_cpcv_dsr' in new_metrics:
            new_dsr = new_metrics.get('test_cpcv_dsr')
            new_dsr_source = 'test_cpcv_dsr'
        else:
            new_dsr = new_metrics.get('test_dsr')
            new_dsr_source = 'test_dsr'
        # T0.1 pre-flight gates: R² on log-returns + corrected directional
        # accuracy. Same shape as DSR — off by default; informational unless
        # the corresponding settings.retrain_min_* threshold is configured.
        new_r2_returns = new_metrics.get('test_r2_returns')
        new_dir_acc = new_metrics.get('test_dir_acc_corrected')

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

        # DSR gate (ON by default at 0.95, fail-closed — see settings.retrain_min_dsr)
        dsr_check_passed = self._check_dsr_gate(
            new_dsr, validation_checks, reasons
        )
        # Decision of record: every verdict artifact reports the
        # deflation components alongside the DSR. This service has no
        # trial ledger, so ledger_count is None; n_paths /
        # num_trials_used come from evaluation-time CPCV (absent on
        # older artifacts).
        validation_checks['dsr'].update({
            'source': new_dsr_source,
            'ledger_count': None,
            'n_paths': new_metrics.get('test_cpcv_n_paths'),
            'num_trials_used': new_metrics.get('test_cpcv_num_trials_used'),
        })
        # T0.1 pre-flight gates (off by default)
        r2_returns_check_passed = self._check_r2_returns_gate(
            new_r2_returns, validation_checks, reasons
        )
        dir_acc_check_passed = self._check_dir_acc_gate(
            new_dir_acc, validation_checks, reasons
        )

        # If no current model, just check minimums
        if current_metrics is None:
            logger.info("No current model - validating against minimum thresholds only")

            is_valid = (
                min_r2_check
                and loss_check
                and dsr_check_passed
                and r2_returns_check_passed
                and dir_acc_check_passed
            )
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
                    "dsr": new_dsr,
                    "r2_returns": new_r2_returns,
                    "dir_acc_corrected": new_dir_acc,
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
            dsr_check_passed,
            r2_returns_check_passed,
            dir_acc_check_passed,
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
                "dsr": new_dsr,
                "r2_returns": new_r2_returns,
                "dir_acc_corrected": new_dir_acc,
            },
            "current_metrics": {
                "r2": current_r2,
                "loss": current_loss,
                "mae": current_mae,
                "dsr": current_metrics.get(
                    'test_cpcv_dsr', current_metrics.get('test_dsr')
                ),
                "r2_returns": current_metrics.get('test_r2_returns'),
                "dir_acc_corrected": current_metrics.get('test_dir_acc_corrected'),
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
