"""
Simple tests to reach 80% coverage - targeting easy wins only
Focus on basic method coverage without complex TensorFlow operations
"""

import pytest
import logging
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
from datetime import datetime
import tempfile

from app.predictor_factory import PredictorFactory, ModelComparator
from app.ml_models.gru_model import GRUPricePredictor
from app.predictor import LSTMPricePredictor


class TestPredictorFactoryBasic:
    """Basic predictor factory tests for simple methods"""

    def test_get_supported_models(self):
        """Test get_supported_models returns list"""
        models = PredictorFactory.get_supported_models()
        assert isinstance(models, list)
        assert 'LSTM' in models
        assert 'GRU' in models
        assert len(models) == 2

    def test_create_predictor_lstm_basic(self):
        """Test creating LSTM predictor"""
        with patch('app.predictor.LSTMPricePredictor.__init__', return_value=None):
            predictor = PredictorFactory.create_predictor('LSTM', 'BTCUSDT', '60')
            assert predictor is not None

    def test_create_predictor_gru_basic(self):
        """Test creating GRU predictor"""
        with patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None):
            predictor = PredictorFactory.create_predictor('GRU', 'BTCUSDT', '60')
            assert predictor is not None

    def test_create_predictor_lowercase(self):
        """Test create_predictor with lowercase input"""
        with patch('app.predictor.LSTMPricePredictor.__init__', return_value=None):
            predictor = PredictorFactory.create_predictor('lstm', 'BTCUSDT', '60')
            assert predictor is not None

    def test_create_predictor_invalid_type(self):
        """Test create_predictor with invalid type"""
        with pytest.raises(ValueError, match="Unsupported model type"):
            PredictorFactory.create_predictor('INVALID', 'BTCUSDT', '60')


class TestModelComparatorBasic:
    """Basic ModelComparator tests"""

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_comparator_initialization(self, gru_init, lstm_init):
        """Test ModelComparator initialization"""
        comparator = ModelComparator('BTCUSDT', '60')
        assert comparator.symbol == 'BTCUSDT'
        assert comparator.interval == '60'
        assert comparator.lstm_predictor is not None
        assert comparator.gru_predictor is not None

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_training_metrics_no_model(self, gru_init, lstm_init):
        """Test _get_training_metrics with no trained model"""
        comparator = ModelComparator('BTCUSDT', '60')
        predictor = LSTMPricePredictor.__new__(LSTMPricePredictor)
        predictor.model = None
        predictor.last_trained = None
        predictor.model_version = None

        metrics = comparator._get_training_metrics(predictor, 'LSTM')
        assert metrics is None

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_training_metrics_with_stats(self, gru_init, lstm_init):
        """Test _get_training_metrics with training stats"""
        comparator = ModelComparator('BTCUSDT', '60')
        predictor = LSTMPricePredictor.__new__(LSTMPricePredictor)
        predictor.model = Mock()
        predictor.last_trained = datetime.now()
        predictor.model_version = '1.0'
        predictor.training_stats = {'rmse': 0.02, 'mae': 0.01, 'r2_score': 0.95}
        predictor.inference_time_ms = 10.5

        metrics = comparator._get_training_metrics(predictor, 'LSTM')
        assert metrics is not None
        assert metrics['model_type'] == 'LSTM'
        assert metrics['trained'] is not None
        assert metrics['rmse'] == 0.02

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_training_metrics_with_get_model_size_mb(self, gru_init, lstm_init):
        """Test _get_training_metrics with get_model_size_mb method"""
        comparator = ModelComparator('BTCUSDT', '60')
        predictor = LSTMPricePredictor.__new__(LSTMPricePredictor)
        predictor.model = Mock()
        predictor.last_trained = datetime.now()
        predictor.model_version = '1.0'
        predictor.training_stats = {}
        predictor.inference_time_ms = 10.5
        predictor.get_model_size_mb = Mock(return_value=50.0)

        metrics = comparator._get_training_metrics(predictor, 'LSTM')
        assert metrics is not None
        assert metrics['model_size_mb'] == 50.0

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_training_metrics_with_existing_model_file(self, gru_init, lstm_init):
        """Test _get_training_metrics calculates model size from file"""
        comparator = ModelComparator('BTCUSDT', '60')
        predictor = LSTMPricePredictor.__new__(LSTMPricePredictor)
        predictor.model = Mock()
        predictor.last_trained = datetime.now()
        predictor.model_version = '1.0'
        predictor.training_stats = {}
        predictor.inference_time_ms = 10.5

        # Create a temporary model file
        with tempfile.NamedTemporaryFile(suffix='.keras', delete=False) as f:
            f.write(b'test' * 1024)  # Write 4KB
            temp_path = f.name

        try:
            mock_path = Mock(spec=Path)
            mock_path.exists.return_value = True
            mock_path.stat.return_value = Mock(st_size=4096)  # 4KB
            predictor._get_model_path = Mock(return_value=mock_path)

            metrics = comparator._get_training_metrics(predictor, 'LSTM')
            assert metrics is not None
            assert 'model_size_mb' in metrics
        finally:
            import os
            try:
                os.unlink(temp_path)
            except:
                pass

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_calculate_overall_score_no_metrics(self, gru_init, lstm_init):
        """Test _calculate_overall_score with empty metrics"""
        comparator = ModelComparator('BTCUSDT', '60')
        score = comparator._calculate_overall_score({})
        assert score == 0.0

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_calculate_overall_score_with_metrics(self, gru_init, lstm_init):
        """Test _calculate_overall_score with actual metrics"""
        comparator = ModelComparator('BTCUSDT', '60')
        metrics = {
            'r2_score': 0.95,
            'directional_accuracy': 0.85,
            'rmse': 0.02,
            'mae': 0.01,
            'inference_time_ms': 5.0,
            'model_size_mb': 50.0
        }
        score = comparator._calculate_overall_score(metrics)
        assert score > 0.0
        assert score <= 1.0

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_recommendation_no_models(self, gru_init, lstm_init):
        """Test get_recommendation when no models are trained"""
        comparator = ModelComparator('BTCUSDT', '60')
        comparator.lstm_predictor.model = None
        comparator.gru_predictor.model = None

        recommendation = comparator.get_recommendation()
        assert "NONE" in recommendation

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_recommendation_lstm_only(self, gru_init, lstm_init):
        """Test get_recommendation when only LSTM is trained"""
        comparator = ModelComparator('BTCUSDT', '60')
        comparator.lstm_predictor.model = Mock()
        comparator.gru_predictor.model = None

        recommendation = comparator.get_recommendation()
        assert "LSTM" in recommendation and "NONE" not in recommendation

    @patch('app.predictor.LSTMPricePredictor.__init__', return_value=None)
    @patch('app.ml_models.gru_model.GRUPricePredictor.__init__', return_value=None)
    def test_get_recommendation_gru_only(self, gru_init, lstm_init):
        """Test get_recommendation when only GRU is trained"""
        comparator = ModelComparator('BTCUSDT', '60')
        comparator.lstm_predictor.model = None
        comparator.gru_predictor.model = Mock()

        recommendation = comparator.get_recommendation()
        assert "GRU" in recommendation and "NONE" not in recommendation


class TestGRUPricePredictor:
    """Basic GRU predictor tests"""

    def test_gru_init_basic(self):
        """Test GRUPricePredictor initialization"""
        with patch('app.ml_models.gru_model.GRUPricePredictor._load_model'):
            predictor = GRUPricePredictor('BTCUSDT', '60')
            assert predictor.symbol == 'BTCUSDT'
            assert predictor.interval == '60'
            assert predictor.model is None

    def test_gru_get_model_path(self):
        """Test GRU model path generation"""
        with patch('app.ml_models.gru_model.GRUPricePredictor._load_model'):
            predictor = GRUPricePredictor('BTCUSDT', '60')
            path = predictor._get_model_path()
            assert isinstance(path, Path)
            assert 'gru' in str(path).lower()
            assert 'btcusdt' in str(path).lower()

    def test_gru_get_metadata_path(self):
        """Test GRU metadata path generation"""
        with patch('app.ml_models.gru_model.GRUPricePredictor._load_model'):
            predictor = GRUPricePredictor('BTCUSDT', '60')
            path = predictor._get_metadata_path()
            assert isinstance(path, Path)
            assert 'gru_metadata' in str(path).lower()
