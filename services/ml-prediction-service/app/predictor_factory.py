"""
Predictor Factory - Creates and manages LSTM/GRU model instances
Provides unified interface for model selection and comparison
"""

import logging
from typing import Dict, List, Union, Optional
import pandas as pd
import numpy as np
from datetime import datetime

from app.predictor import LSTMPricePredictor
from app.ml_models.gru_model import GRUPricePredictor
from app.models import PricePrediction, ModelInfo

logger = logging.getLogger(__name__)


class PredictorFactory:
    """
    Factory for creating and managing ML predictors

    Supports:
    - LSTM (Long Short-Term Memory)
    - GRU (Gated Recurrent Unit)
    """

    @staticmethod
    def create_predictor(
        model_type: str,
        symbol: str,
        interval: str = "60"
    ) -> Union[LSTMPricePredictor, GRUPricePredictor]:
        """
        Create a predictor instance based on model type

        Args:
            model_type: Either 'LSTM' or 'GRU'
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes

        Returns:
            Predictor instance (LSTM or GRU)

        Raises:
            ValueError: If model_type is not supported
        """
        model_type = model_type.upper()

        if model_type == 'LSTM':
            logger.info(f"Creating LSTM predictor for {symbol} {interval}m")
            return LSTMPricePredictor(symbol, interval)
        elif model_type == 'GRU':
            logger.info(f"Creating GRU predictor for {symbol} {interval}m")
            return GRUPricePredictor(symbol, interval)
        else:
            raise ValueError(f"Unsupported model type: {model_type}. Use 'LSTM' or 'GRU'")

    @staticmethod
    def get_supported_models() -> List[str]:
        """Get list of supported model types"""
        return ['LSTM', 'GRU']


class ModelComparator:
    """
    Compares performance between LSTM and GRU models

    Metrics compared:
    - Prediction accuracy (RMSE, MAE, MAPE, R²)
    - Directional accuracy
    - Training time
    - Inference speed
    - Model size
    - Parameter count
    """

    def __init__(self, symbol: str, interval: str = "60"):
        """
        Initialize comparator for a specific symbol/interval

        Args:
            symbol: Trading pair
            interval: Timeframe in minutes
        """
        self.symbol = symbol
        self.interval = interval

        # Create both predictors
        self.lstm_predictor = LSTMPricePredictor(symbol, interval)
        self.gru_predictor = GRUPricePredictor(symbol, interval)

    async def compare_predictions(
        self,
        recent_data: pd.DataFrame
    ) -> Dict:
        """
        Compare predictions from LSTM and GRU on the same data

        Args:
            recent_data: Recent price data for prediction

        Returns:
            Comparison dictionary with predictions and metrics
        """
        try:
            results = {
                'symbol': self.symbol,
                'interval': f"{self.interval}m",
                'timestamp': datetime.utcnow().isoformat(),
                'lstm': None,
                'gru': None,
                'comparison': {}
            }

            # Get LSTM prediction if model exists
            if self.lstm_predictor.model is not None:
                try:
                    lstm_pred = await self.lstm_predictor.predict(recent_data)
                    results['lstm'] = {
                        'predictions': [
                            {
                                'timestamp': p.timestamp.isoformat(),
                                'price': p.predicted_price,
                                'confidence': p.confidence
                            }
                            for p in lstm_pred.predictions
                        ],
                        'direction': lstm_pred.predicted_direction,
                        'avg_confidence': lstm_pred.average_confidence,
                        'inference_time_ms': self.lstm_predictor.training_stats.get('inference_time_ms', 0)
                    }
                except Exception as e:
                    logger.error(f"LSTM prediction failed: {e}")
                    results['lstm'] = {'error': str(e)}

            # Get GRU prediction if model exists
            if self.gru_predictor.model is not None:
                try:
                    gru_pred = await self.gru_predictor.predict(recent_data)
                    results['gru'] = {
                        'predictions': [
                            {
                                'timestamp': p.timestamp.isoformat(),
                                'price': p.predicted_price,
                                'confidence': p.confidence
                            }
                            for p in gru_pred.predictions
                        ],
                        'direction': gru_pred.predicted_direction,
                        'avg_confidence': gru_pred.average_confidence,
                        'inference_time_ms': self.gru_predictor.inference_time_ms
                    }
                except Exception as e:
                    logger.error(f"GRU prediction failed: {e}")
                    results['gru'] = {'error': str(e)}

            # Compare if both predictions succeeded
            if results['lstm'] and results['gru'] and 'error' not in results['lstm'] and 'error' not in results['gru']:
                lstm_prices = [p['price'] for p in results['lstm']['predictions']]
                gru_prices = [p['price'] for p in results['gru']['predictions']]

                # Calculate agreement metrics
                price_diff = np.abs(np.array(lstm_prices) - np.array(gru_prices))
                avg_price_diff = float(np.mean(price_diff))
                max_price_diff = float(np.max(price_diff))

                # Direction agreement
                direction_agreement = results['lstm']['direction'] == results['gru']['direction']

                results['comparison'] = {
                    'avg_price_difference': avg_price_diff,
                    'max_price_difference': max_price_diff,
                    'direction_agreement': direction_agreement,
                    'lstm_faster': results['lstm']['inference_time_ms'] < results['gru']['inference_time_ms'],
                    'speed_difference_ms': abs(
                        results['lstm']['inference_time_ms'] - results['gru']['inference_time_ms']
                    )
                }

            return results

        except Exception as e:
            logger.error(f"Comparison failed: {e}")
            raise

    async def compare_training_metrics(self) -> Dict:
        """
        Compare training performance metrics

        Returns:
            Dictionary with comprehensive training comparison
        """
        lstm_metrics = self._get_training_metrics(self.lstm_predictor, 'LSTM')
        gru_metrics = self._get_training_metrics(self.gru_predictor, 'GRU')

        comparison = {
            'symbol': self.symbol,
            'interval': f"{self.interval}m",
            'models': {
                'lstm': lstm_metrics,
                'gru': gru_metrics
            },
            'winner': {}
        }

        # Determine winners for each metric (lower is better for errors, higher for accuracy)
        if lstm_metrics and gru_metrics:
            comparison['winner'] = {
                'rmse': 'LSTM' if lstm_metrics.get('rmse', float('inf')) < gru_metrics.get('rmse', float('inf')) else 'GRU',
                'mae': 'LSTM' if lstm_metrics.get('mae', float('inf')) < gru_metrics.get('mae', float('inf')) else 'GRU',
                'r2_score': 'LSTM' if lstm_metrics.get('r2_score', 0) > gru_metrics.get('r2_score', 0) else 'GRU',
                'directional_accuracy': 'LSTM' if lstm_metrics.get('directional_accuracy', 0) > gru_metrics.get('directional_accuracy', 0) else 'GRU',
                'training_speed': 'LSTM' if lstm_metrics.get('training_duration_seconds', float('inf')) < gru_metrics.get('training_duration_seconds', float('inf')) else 'GRU',
                'inference_speed': 'LSTM' if lstm_metrics.get('inference_time_ms', float('inf')) < gru_metrics.get('inference_time_ms', float('inf')) else 'GRU',
                'model_size': 'LSTM' if lstm_metrics.get('model_size_mb', float('inf')) < gru_metrics.get('model_size_mb', float('inf')) else 'GRU',
                'parameters': 'LSTM' if lstm_metrics.get('total_parameters', float('inf')) < gru_metrics.get('total_parameters', float('inf')) else 'GRU'
            }

            # Overall winner (based on weighted score)
            lstm_score = self._calculate_overall_score(lstm_metrics)
            gru_score = self._calculate_overall_score(gru_metrics)

            comparison['winner']['overall'] = 'LSTM' if lstm_score > gru_score else 'GRU'
            comparison['scores'] = {
                'lstm_score': lstm_score,
                'gru_score': gru_score
            }

        return comparison

    def _get_training_metrics(self, predictor, model_type: str) -> Optional[Dict]:
        """Extract training metrics from a predictor"""
        if predictor.model is None:
            return None

        metrics = {
            'model_type': model_type,
            'trained': predictor.last_trained.isoformat() if predictor.last_trained else None,
            'version': predictor.model_version
        }

        # Add training stats
        if hasattr(predictor, 'training_stats') and predictor.training_stats:
            metrics.update({
                'rmse': predictor.training_stats.get('rmse', 0),
                'mae': predictor.training_stats.get('mae', 0),
                'r2_score': predictor.training_stats.get('r2_score', 0),
                'mape': predictor.training_stats.get('mape', 0),
                'directional_accuracy': predictor.training_stats.get('directional_accuracy', 0),
                'train_samples': predictor.training_stats.get('train_samples', 0),
                'test_samples': predictor.training_stats.get('test_samples', 0),
                'total_parameters': predictor.training_stats.get('total_parameters', 0)
            })

        # Add inference time
        if hasattr(predictor, 'inference_time_ms'):
            metrics['inference_time_ms'] = predictor.inference_time_ms

        # Add model size for GRU
        if hasattr(predictor, 'get_model_size_mb'):
            metrics['model_size_mb'] = predictor.get_model_size_mb()
        else:
            # Calculate for LSTM
            model_path = predictor._get_model_path()
            if model_path.exists():
                metrics['model_size_mb'] = model_path.stat().st_size / (1024 * 1024)

        return metrics

    def _calculate_overall_score(self, metrics: Dict) -> float:
        """
        Calculate overall score for a model

        Weighted combination of metrics:
        - 30% R² score (accuracy)
        - 20% Directional accuracy
        - 15% RMSE (normalized, inverted)
        - 15% MAE (normalized, inverted)
        - 10% Inference speed (inverted)
        - 10% Model size (inverted)
        """
        if not metrics:
            return 0.0

        score = 0.0

        # R² score (0-1, higher is better)
        score += metrics.get('r2_score', 0) * 0.30

        # Directional accuracy (0-1, higher is better)
        score += metrics.get('directional_accuracy', 0) * 0.20

        # RMSE (lower is better, normalize to 0-1)
        rmse = metrics.get('rmse', 0)
        if rmse > 0:
            score += (1 / (1 + rmse)) * 0.15

        # MAE (lower is better, normalize to 0-1)
        mae = metrics.get('mae', 0)
        if mae > 0:
            score += (1 / (1 + mae)) * 0.15

        # Inference speed (lower ms is better)
        inference_ms = metrics.get('inference_time_ms', 100)
        if inference_ms > 0:
            score += (100 / (100 + inference_ms)) * 0.10

        # Model size (lower MB is better)
        size_mb = metrics.get('model_size_mb', 10)
        if size_mb > 0:
            score += (10 / (10 + size_mb)) * 0.10

        return score

    def get_recommendation(self) -> str:
        """
        Get recommendation on which model to use

        Returns:
            'LSTM', 'GRU', or 'NONE' with reasoning
        """
        lstm_has_model = self.lstm_predictor.model is not None
        gru_has_model = self.gru_predictor.model is not None

        if not lstm_has_model and not gru_has_model:
            return "NONE: No models trained yet"

        if lstm_has_model and not gru_has_model:
            return "LSTM: Only LSTM model available"

        if gru_has_model and not lstm_has_model:
            return "GRU: Only GRU model available"

        # Both available, compare performance
        lstm_score = self._calculate_overall_score(
            self._get_training_metrics(self.lstm_predictor, 'LSTM')
        )
        gru_score = self._calculate_overall_score(
            self._get_training_metrics(self.gru_predictor, 'GRU')
        )

        if lstm_score > gru_score:
            diff = ((lstm_score - gru_score) / gru_score) * 100
            return f"LSTM: {diff:.1f}% better overall performance"
        else:
            diff = ((gru_score - lstm_score) / lstm_score) * 100
            return f"GRU: {diff:.1f}% better overall performance (faster & more efficient)"
