"""
Ensemble Prediction System
Combines LSTM and GRU models for improved prediction accuracy
Implements multiple ensemble strategies with dynamic weight adjustment
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Literal
import logging
import json
from pathlib import Path
from dataclasses import dataclass

# ML libraries
try:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.ensemble import GradientBoostingRegressor
    import lightgbm as lgb
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("Scikit-learn/LightGBM not available. Advanced ensemble strategies disabled.")

from app.config import get_settings
from app.models import PricePoint, PricePrediction
from app.predictor import LSTMPricePredictor
from app.ml_models.gru_predictor import GRUPricePredictor

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class EnsemblePerformanceMetrics:
    """Performance metrics for ensemble predictions"""
    strategy: str
    mae: float
    rmse: float
    r2_score: float
    accuracy: float
    lstm_weight: float
    gru_weight: float
    improvement_over_lstm: float
    improvement_over_gru: float
    timestamp: datetime


@dataclass
class ModelPredictionResult:
    """Individual model prediction result"""
    model_type: str
    predictions: List[float]
    confidence: float
    performance_score: float  # Recent performance metric


class EnsemblePredictor:
    """
    Ensemble predictor combining LSTM and GRU models

    Strategies:
    1. Simple Average: Equal weight to both models
    2. Performance-Weighted: Weight by recent accuracy
    3. Confidence-Weighted: Weight by prediction confidence
    4. Stacked Ensemble: Meta-model learns optimal combination
    5. Adaptive Ensemble: Adjust weights based on market conditions
    """

    def __init__(self, symbol: str, interval: str = "60"):
        """
        Initialize ensemble predictor

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes
        """
        self.symbol = symbol
        self.interval = interval

        # Initialize individual models
        self.lstm_predictor = LSTMPricePredictor(symbol, interval)
        self.gru_predictor = GRUPricePredictor(symbol, interval)

        # Ensemble weights (default: equal)
        self.lstm_weight = 0.5
        self.gru_weight = 0.5

        # Performance tracking
        self.performance_history: List[EnsemblePerformanceMetrics] = []
        self.recent_predictions: List[Dict] = []

        # Meta-model for stacking (trained lazily)
        self.meta_model: Optional[lgb.LGBMRegressor] = None

        # Load ensemble configuration
        self._load_ensemble_config()

    def _load_ensemble_config(self):
        """Load ensemble weights and configuration from disk"""
        try:
            config_path = Path(settings.models_dir) / f"{self.symbol}_{self.interval}m_ensemble_config.json"
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    self.lstm_weight = config.get('lstm_weight', 0.5)
                    self.gru_weight = config.get('gru_weight', 0.5)
                    logger.info(f"Loaded ensemble config: LSTM={self.lstm_weight}, GRU={self.gru_weight}")
        except Exception as e:
            logger.warning(f"Could not load ensemble config: {e}")

    def _save_ensemble_config(self):
        """Save ensemble weights and configuration"""
        try:
            config_path = Path(settings.models_dir) / f"{self.symbol}_{self.interval}m_ensemble_config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            config = {
                'symbol': self.symbol,
                'interval': self.interval,
                'lstm_weight': self.lstm_weight,
                'gru_weight': self.gru_weight,
                'last_updated': datetime.utcnow().isoformat()
            }

            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            logger.info(f"Saved ensemble config to {config_path}")
        except Exception as e:
            logger.error(f"Error saving ensemble config: {e}")

    async def predict_simple_average(self, recent_data: pd.DataFrame) -> PricePrediction:
        """
        Strategy 1: Simple Average
        Equal weight to both LSTM and GRU predictions

        Pros: Simple, no bias toward any model
        Cons: Doesn't account for model performance differences
        """
        # Get predictions from both models
        lstm_pred = await self.lstm_predictor.predict(recent_data)
        gru_pred = await self.gru_predictor.predict(recent_data)

        # Average the predictions
        averaged_predictions = []
        for lstm_point, gru_point in zip(lstm_pred.predictions, gru_pred.predictions):
            avg_price = (lstm_point.predicted_price + gru_point.predicted_price) / 2
            avg_confidence = (lstm_point.confidence + gru_point.confidence) / 2

            # Combine confidence intervals
            lower_bound = (lstm_point.lower_bound + gru_point.lower_bound) / 2
            upper_bound = (lstm_point.upper_bound + gru_point.upper_bound) / 2

            averaged_predictions.append(PricePoint(
                timestamp=lstm_point.timestamp,
                predicted_price=avg_price,
                confidence=avg_confidence,
                lower_bound=lower_bound,
                upper_bound=upper_bound
            ))

        # Calculate ensemble metrics
        current_price = lstm_pred.current_price
        avg_predicted = np.mean([p.predicted_price for p in averaged_predictions])
        price_change_pct = ((avg_predicted - current_price) / current_price) * 100

        if price_change_pct > 1.0:
            direction = "UP"
        elif price_change_pct < -1.0:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        directional_strength = min(1.0, abs(price_change_pct) / 5.0)

        return PricePrediction(
            symbol=self.symbol,
            interval=f"{self.interval}m",
            current_price=current_price,
            predictions=averaged_predictions,
            model_type="ENSEMBLE_SIMPLE_AVG",
            model_version=f"LSTM:{lstm_pred.model_version}+GRU:{gru_pred.model_version}",
            model_last_trained=max(lstm_pred.model_last_trained, gru_pred.model_last_trained),
            average_confidence=float(np.mean([p.confidence for p in averaged_predictions])),
            prediction_horizon_minutes=lstm_pred.prediction_horizon_minutes,
            predicted_direction=direction,
            directional_strength=directional_strength
        )

    async def predict_performance_weighted(self, recent_data: pd.DataFrame) -> PricePrediction:
        """
        Strategy 2: Performance-Weighted Average
        Weight predictions by recent model accuracy

        Pros: Favors better-performing model
        Cons: Past performance doesn't guarantee future results
        """
        # Get predictions from both models
        lstm_pred = await self.lstm_predictor.predict(recent_data)
        gru_pred = await self.gru_predictor.predict(recent_data)

        # Get performance scores (R² scores from training)
        lstm_r2 = self.lstm_predictor.training_stats.get('r2_score', 0.5)
        gru_r2 = self.gru_predictor.training_stats.get('r2_score', 0.5)

        # Normalize weights (ensure they sum to 1)
        total_score = lstm_r2 + gru_r2
        lstm_weight = lstm_r2 / total_score if total_score > 0 else 0.5
        gru_weight = gru_r2 / total_score if total_score > 0 else 0.5

        logger.info(f"Performance weights: LSTM={lstm_weight:.3f}, GRU={gru_weight:.3f}")

        # Weighted average of predictions
        weighted_predictions = []
        for lstm_point, gru_point in zip(lstm_pred.predictions, gru_pred.predictions):
            weighted_price = (lstm_point.predicted_price * lstm_weight +
                            gru_point.predicted_price * gru_weight)
            weighted_confidence = (lstm_point.confidence * lstm_weight +
                                 gru_point.confidence * gru_weight)

            lower_bound = (lstm_point.lower_bound * lstm_weight +
                          gru_point.lower_bound * gru_weight)
            upper_bound = (lstm_point.upper_bound * lstm_weight +
                          gru_point.upper_bound * gru_weight)

            weighted_predictions.append(PricePoint(
                timestamp=lstm_point.timestamp,
                predicted_price=weighted_price,
                confidence=weighted_confidence,
                lower_bound=lower_bound,
                upper_bound=upper_bound
            ))

        # Calculate ensemble metrics
        current_price = lstm_pred.current_price
        avg_predicted = np.mean([p.predicted_price for p in weighted_predictions])
        price_change_pct = ((avg_predicted - current_price) / current_price) * 100

        if price_change_pct > 1.0:
            direction = "UP"
        elif price_change_pct < -1.0:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        directional_strength = min(1.0, abs(price_change_pct) / 5.0)

        return PricePrediction(
            symbol=self.symbol,
            interval=f"{self.interval}m",
            current_price=current_price,
            predictions=weighted_predictions,
            model_type="ENSEMBLE_PERFORMANCE_WEIGHTED",
            model_version=f"LSTM:{lstm_pred.model_version}+GRU:{gru_pred.model_version}",
            model_last_trained=max(lstm_pred.model_last_trained, gru_pred.model_last_trained),
            average_confidence=float(np.mean([p.confidence for p in weighted_predictions])),
            prediction_horizon_minutes=lstm_pred.prediction_horizon_minutes,
            predicted_direction=direction,
            directional_strength=directional_strength
        )

    async def predict_confidence_weighted(self, recent_data: pd.DataFrame) -> PricePrediction:
        """
        Strategy 3: Confidence-Weighted Average
        Weight predictions by model confidence scores

        Pros: Uses model's self-assessment
        Cons: Models might be overconfident
        """
        # Get predictions from both models
        lstm_pred = await self.lstm_predictor.predict(recent_data)
        gru_pred = await self.gru_predictor.predict(recent_data)

        # Use average confidence as weight
        lstm_confidence = lstm_pred.average_confidence
        gru_confidence = gru_pred.average_confidence

        total_confidence = lstm_confidence + gru_confidence
        lstm_weight = lstm_confidence / total_confidence if total_confidence > 0 else 0.5
        gru_weight = gru_confidence / total_confidence if total_confidence > 0 else 0.5

        logger.info(f"Confidence weights: LSTM={lstm_weight:.3f}, GRU={gru_weight:.3f}")

        # Weighted average of predictions
        confidence_weighted_predictions = []
        for lstm_point, gru_point in zip(lstm_pred.predictions, gru_pred.predictions):
            # Use individual point confidences for more granular weighting
            point_total = lstm_point.confidence + gru_point.confidence
            point_lstm_weight = lstm_point.confidence / point_total if point_total > 0 else 0.5
            point_gru_weight = gru_point.confidence / point_total if point_total > 0 else 0.5

            weighted_price = (lstm_point.predicted_price * point_lstm_weight +
                            gru_point.predicted_price * point_gru_weight)

            # Confidence is the weighted average of confidences
            weighted_confidence = (lstm_point.confidence * point_lstm_weight +
                                 gru_point.confidence * point_gru_weight)

            lower_bound = (lstm_point.lower_bound * point_lstm_weight +
                          gru_point.lower_bound * point_gru_weight)
            upper_bound = (lstm_point.upper_bound * point_lstm_weight +
                          gru_point.upper_bound * point_gru_weight)

            confidence_weighted_predictions.append(PricePoint(
                timestamp=lstm_point.timestamp,
                predicted_price=weighted_price,
                confidence=weighted_confidence,
                lower_bound=lower_bound,
                upper_bound=upper_bound
            ))

        # Calculate ensemble metrics
        current_price = lstm_pred.current_price
        avg_predicted = np.mean([p.predicted_price for p in confidence_weighted_predictions])
        price_change_pct = ((avg_predicted - current_price) / current_price) * 100

        if price_change_pct > 1.0:
            direction = "UP"
        elif price_change_pct < -1.0:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        directional_strength = min(1.0, abs(price_change_pct) / 5.0)

        return PricePrediction(
            symbol=self.symbol,
            interval=f"{self.interval}m",
            current_price=current_price,
            predictions=confidence_weighted_predictions,
            model_type="ENSEMBLE_CONFIDENCE_WEIGHTED",
            model_version=f"LSTM:{lstm_pred.model_version}+GRU:{gru_pred.model_version}",
            model_last_trained=max(lstm_pred.model_last_trained, gru_pred.model_last_trained),
            average_confidence=float(np.mean([p.confidence for p in confidence_weighted_predictions])),
            prediction_horizon_minutes=lstm_pred.prediction_horizon_minutes,
            predicted_direction=direction,
            directional_strength=directional_strength
        )

    async def predict_adaptive(self, recent_data: pd.DataFrame) -> PricePrediction:
        """
        Strategy 4: Adaptive Ensemble
        Dynamically adjust weights based on market conditions

        Detects:
        - High volatility: Favor model with better volatility handling
        - Trend changes: Adjust based on directional agreement
        - Uncertainty: Equal weights when models disagree

        Pros: Adapts to market conditions
        Cons: More complex, requires market analysis
        """
        # Get predictions from both models
        lstm_pred = await self.lstm_predictor.predict(recent_data)
        gru_pred = await self.gru_predictor.predict(recent_data)

        # Analyze market conditions
        df = recent_data.copy()
        df['returns'] = df['close'].pct_change()

        # Volatility (rolling std of returns)
        current_volatility = df['returns'].rolling(window=20).std().iloc[-1] * 100

        # Trend strength (slope of linear regression)
        prices = df['close'].tail(20).values
        x = np.arange(len(prices))
        trend_slope = np.polyfit(x, prices, 1)[0]
        trend_strength = abs(trend_slope) / prices[-1]  # Normalized

        # Model agreement (how similar are predictions?)
        lstm_prices = [p.predicted_price for p in lstm_pred.predictions]
        gru_prices = [p.predicted_price for p in gru_pred.predictions]
        price_diff = np.mean([abs(l - g) / l for l, g in zip(lstm_prices, gru_prices)])

        # Adaptive weight calculation
        if current_volatility > 3.0:  # High volatility
            # Favor LSTM (generally more stable with long-term memory)
            lstm_weight = 0.6
            gru_weight = 0.4
            logger.info(f"High volatility ({current_volatility:.2f}%), favoring LSTM")

        elif trend_strength > 0.01:  # Strong trend
            # Favor GRU (faster to adapt to trends)
            lstm_weight = 0.4
            gru_weight = 0.6
            logger.info(f"Strong trend detected, favoring GRU")

        elif price_diff > 0.02:  # Models disagree (>2% difference)
            # Equal weights when uncertain
            lstm_weight = 0.5
            gru_weight = 0.5
            logger.info(f"Models disagree ({price_diff*100:.1f}%), using equal weights")

        else:  # Normal conditions
            # Use performance-based weights
            lstm_r2 = self.lstm_predictor.training_stats.get('r2_score', 0.5)
            gru_r2 = self.gru_predictor.training_stats.get('r2_score', 0.5)
            total = lstm_r2 + gru_r2
            lstm_weight = lstm_r2 / total if total > 0 else 0.5
            gru_weight = gru_r2 / total if total > 0 else 0.5
            logger.info("Normal conditions, using performance weights")

        # Weighted average of predictions
        adaptive_predictions = []
        for lstm_point, gru_point in zip(lstm_pred.predictions, gru_pred.predictions):
            weighted_price = (lstm_point.predicted_price * lstm_weight +
                            gru_point.predicted_price * gru_weight)
            weighted_confidence = (lstm_point.confidence * lstm_weight +
                                 gru_point.confidence * gru_weight)

            lower_bound = (lstm_point.lower_bound * lstm_weight +
                          gru_point.lower_bound * gru_weight)
            upper_bound = (lstm_point.upper_bound * lstm_weight +
                          gru_point.upper_bound * gru_weight)

            adaptive_predictions.append(PricePoint(
                timestamp=lstm_point.timestamp,
                predicted_price=weighted_price,
                confidence=weighted_confidence,
                lower_bound=lower_bound,
                upper_bound=upper_bound
            ))

        # Calculate ensemble metrics
        current_price = lstm_pred.current_price
        avg_predicted = np.mean([p.predicted_price for p in adaptive_predictions])
        price_change_pct = ((avg_predicted - current_price) / current_price) * 100

        if price_change_pct > 1.0:
            direction = "UP"
        elif price_change_pct < -1.0:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"

        directional_strength = min(1.0, abs(price_change_pct) / 5.0)

        return PricePrediction(
            symbol=self.symbol,
            interval=f"{self.interval}m",
            current_price=current_price,
            predictions=adaptive_predictions,
            model_type="ENSEMBLE_ADAPTIVE",
            model_version=f"LSTM:{lstm_pred.model_version}+GRU:{gru_pred.model_version}",
            model_last_trained=max(lstm_pred.model_last_trained, gru_pred.model_last_trained),
            average_confidence=float(np.mean([p.confidence for p in adaptive_predictions])),
            prediction_horizon_minutes=lstm_pred.prediction_horizon_minutes,
            predicted_direction=direction,
            directional_strength=directional_strength
        )

    async def predict(
        self,
        recent_data: pd.DataFrame,
        strategy: Literal["simple", "performance", "confidence", "adaptive"] = "adaptive"
    ) -> PricePrediction:
        """
        Make ensemble prediction using specified strategy

        Args:
            recent_data: Recent price data
            strategy: Ensemble strategy to use

        Returns:
            PricePrediction from ensemble
        """
        if strategy == "simple":
            return await self.predict_simple_average(recent_data)
        elif strategy == "performance":
            return await self.predict_performance_weighted(recent_data)
        elif strategy == "confidence":
            return await self.predict_confidence_weighted(recent_data)
        elif strategy == "adaptive":
            return await self.predict_adaptive(recent_data)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

    async def optimize_weights(
        self,
        validation_data: pd.DataFrame,
        actual_prices: List[float]
    ) -> Dict[str, float]:
        """
        Optimize ensemble weights based on validation data

        Tests different weight combinations and selects best performing

        Args:
            validation_data: Historical data for validation
            actual_prices: Actual prices that occurred

        Returns:
            Dict with optimized weights and performance metrics
        """
        if len(actual_prices) != settings.prediction_horizon:
            raise ValueError(f"Expected {settings.prediction_horizon} actual prices, got {len(actual_prices)}")

        # Get predictions from both models
        lstm_pred = await self.lstm_predictor.predict(validation_data)
        gru_pred = await self.gru_predictor.predict(validation_data)

        lstm_prices = [p.predicted_price for p in lstm_pred.predictions]
        gru_prices = [p.predicted_price for p in gru_pred.predictions]

        # Test different weight combinations
        best_mae = float('inf')
        best_lstm_weight = 0.5
        best_gru_weight = 0.5

        # Grid search over weights
        for lstm_w in np.linspace(0, 1, 21):  # 0.0, 0.05, 0.10, ..., 1.0
            gru_w = 1.0 - lstm_w

            # Calculate ensemble predictions
            ensemble_prices = [
                lstm_p * lstm_w + gru_p * gru_w
                for lstm_p, gru_p in zip(lstm_prices, gru_prices)
            ]

            # Calculate MAE
            mae = mean_absolute_error(actual_prices, ensemble_prices)

            if mae < best_mae:
                best_mae = mae
                best_lstm_weight = lstm_w
                best_gru_weight = gru_w

        # Update ensemble weights
        self.lstm_weight = best_lstm_weight
        self.gru_weight = best_gru_weight
        self._save_ensemble_config()

        # Calculate metrics for individual models
        lstm_mae = mean_absolute_error(actual_prices, lstm_prices)
        gru_mae = mean_absolute_error(actual_prices, gru_prices)

        improvement_over_lstm = ((lstm_mae - best_mae) / lstm_mae) * 100
        improvement_over_gru = ((gru_mae - best_mae) / gru_mae) * 100

        logger.info(f"Optimized weights: LSTM={best_lstm_weight:.3f}, GRU={best_gru_weight:.3f}")
        logger.info(f"Ensemble MAE={best_mae:.2f}, LSTM MAE={lstm_mae:.2f}, GRU MAE={gru_mae:.2f}")
        logger.info(f"Improvement: {improvement_over_lstm:.1f}% over LSTM, {improvement_over_gru:.1f}% over GRU")

        return {
            'lstm_weight': float(best_lstm_weight),
            'gru_weight': float(best_gru_weight),
            'ensemble_mae': float(best_mae),
            'lstm_mae': float(lstm_mae),
            'gru_mae': float(gru_mae),
            'improvement_over_lstm_pct': float(improvement_over_lstm),
            'improvement_over_gru_pct': float(improvement_over_gru)
        }

    def get_performance_metrics(self) -> List[EnsemblePerformanceMetrics]:
        """Get historical performance metrics"""
        return self.performance_history

    def detect_disagreement(
        self,
        lstm_predictions: List[float],
        gru_predictions: List[float],
        threshold: float = 0.02
    ) -> Dict:
        """
        Detect when models significantly disagree

        Args:
            lstm_predictions: LSTM predicted prices
            gru_predictions: GRU predicted prices
            threshold: Disagreement threshold (2% default)

        Returns:
            Dict with disagreement analysis
        """
        disagreements = []
        for i, (lstm_p, gru_p) in enumerate(zip(lstm_predictions, gru_predictions)):
            diff_pct = abs(lstm_p - gru_p) / lstm_p
            if diff_pct > threshold:
                disagreements.append({
                    'step': i + 1,
                    'lstm_price': lstm_p,
                    'gru_price': gru_p,
                    'difference_pct': diff_pct * 100
                })

        avg_disagreement = np.mean([abs(l - g) / l for l, g in zip(lstm_predictions, gru_predictions)])

        return {
            'has_significant_disagreement': len(disagreements) > 0,
            'disagreement_count': len(disagreements),
            'average_disagreement_pct': float(avg_disagreement * 100),
            'disagreements': disagreements,
            'recommendation': (
                "CAUTION: Models disagree significantly. Consider waiting for clearer signal."
                if len(disagreements) > 2
                else "Models in reasonable agreement."
            )
        }
