"""
ML Price Predictor - Core LSTM implementation
Handles model training, prediction, and persistence
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict, Union
import logging
import json
from pathlib import Path
import pickle

# ML libraries
try:
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logging.warning("TensorFlow not available. ML predictions will be disabled.")

from app.config import get_settings
from app.models import PricePoint, PricePrediction, ModelInfo

logger = logging.getLogger(__name__)
settings = get_settings()


class LSTMPricePredictor:
    """
    LSTM-based price predictor
    Uses historical price + technical indicators to predict future prices
    """

    def __init__(self, symbol: str, interval: str = "60"):
        """
        Initialize predictor for a specific symbol/interval

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes (e.g., 60 for 1 hour)
        """
        self.symbol = symbol
        self.interval = interval
        self.sequence_length = settings.sequence_length
        self.prediction_horizon = settings.prediction_horizon

        # Model components
        self.model: Optional[keras.Model] = None
        self.price_scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_scaler = MinMaxScaler(feature_range=(0, 1))

        # Model metadata
        self.model_version = None
        self.last_trained = None
        self.training_stats = {}

        # Feature columns
        self.feature_columns = []

        # Load existing model if available
        self._load_model()

    def _get_model_path(self) -> Path:
        """Get path to saved model"""
        models_dir = Path(settings.models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir / f"{self.symbol}_{self.interval}m_lstm.keras"

    def _get_metadata_path(self) -> Path:
        """Get path to model metadata"""
        models_dir = Path(settings.models_dir)
        return models_dir / f"{self.symbol}_{self.interval}m_metadata.json"

    def _load_model(self) -> bool:
        """Load pre-trained model and metadata"""
        try:
            if not TENSORFLOW_AVAILABLE:
                logger.warning("TensorFlow not available, cannot load model")
                return False

            model_path = self._get_model_path()
            metadata_path = self._get_metadata_path()

            if not model_path.exists():
                logger.info(f"No trained model found for {self.symbol} {self.interval}m")
                return False

            # Load model
            self.model = keras.models.load_model(str(model_path))
            logger.info(f"Loaded model from {model_path}")

            # Load metadata
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    self.model_version = metadata.get('model_version')
                    self.last_trained = datetime.fromisoformat(metadata.get('last_trained'))
                    self.training_stats = metadata.get('training_stats', {})
                    self.feature_columns = metadata.get('feature_columns', [])

                    # Load scalers
                    scaler_path = self._get_model_path().parent / f"{self.symbol}_{self.interval}m_scalers.pkl"
                    if scaler_path.exists():
                        with open(scaler_path, 'rb') as f:
                            scaler_data = pickle.load(f)
                            self.price_scaler = scaler_data['price_scaler']
                            self.feature_scaler = scaler_data['feature_scaler']

                logger.info(f"Loaded model metadata: version={self.model_version}, trained={self.last_trained}")
                return True

        except Exception as e:
            logger.error(f"Error loading model: {e}")
            return False

    def _save_model(self):
        """Save trained model and metadata"""
        try:
            model_path = self._get_model_path()
            metadata_path = self._get_metadata_path()

            # Save model
            self.model.save(str(model_path))
            logger.info(f"Saved model to {model_path}")

            # Save metadata
            metadata = {
                'symbol': self.symbol,
                'interval': self.interval,
                'model_version': self.model_version,
                'last_trained': self.last_trained.isoformat(),
                'training_stats': self.training_stats,
                'feature_columns': self.feature_columns,
                'sequence_length': self.sequence_length,
                'prediction_horizon': self.prediction_horizon
            }

            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save scalers
            scaler_path = model_path.parent / f"{self.symbol}_{self.interval}m_scalers.pkl"
            with open(scaler_path, 'wb') as f:
                pickle.dump({
                    'price_scaler': self.price_scaler,
                    'feature_scaler': self.feature_scaler
                }, f)

            logger.info(f"Saved model metadata to {metadata_path}")

        except Exception as e:
            logger.error(f"Error saving model: {e}")

    def _create_features(self, data: Union[pd.DataFrame, List[Dict]]) -> pd.DataFrame:
        """
        Engineer features from price data + technical indicators

        Args:
            data: Either a DataFrame or list of dicts with OHLCV data

        Features:
        - Price features: open, high, low, close, volume
        - Returns: 1-period, 5-period, 10-period returns
        - Technical indicators: RSI, MACD, Bollinger Bands, etc.
        - Moving averages: SMA/EMA various periods
        - Volatility: ATR, historical volatility
        """
        # Convert list to DataFrame if needed
        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data.copy()

        # Price returns (log returns for better distribution)
        df['return_1'] = np.log(df['close'] / df['close'].shift(1))
        df['return_5'] = np.log(df['close'] / df['close'].shift(5))
        df['return_10'] = np.log(df['close'] / df['close'].shift(10))

        # Price momentum
        df['price_momentum_5'] = df['close'] - df['close'].shift(5)
        df['price_momentum_10'] = df['close'] - df['close'].shift(10)

        # Moving averages
        df['sma_7'] = df['close'].rolling(window=7).mean()
        df['sma_14'] = df['close'].rolling(window=14).mean()
        df['sma_30'] = df['close'].rolling(window=30).mean()
        df['ema_7'] = df['close'].ewm(span=7, adjust=False).mean()
        df['ema_14'] = df['close'].ewm(span=14, adjust=False).mean()

        # Price position relative to MAs
        df['price_vs_sma7'] = (df['close'] - df['sma_7']) / df['sma_7']
        df['price_vs_sma14'] = (df['close'] - df['sma_14']) / df['sma_14']

        # Volatility features
        df['high_low_range'] = (df['high'] - df['low']) / df['close']
        df['volatility_10'] = df['return_1'].rolling(window=10).std()
        df['volatility_20'] = df['return_1'].rolling(window=20).std()

        # Volume features
        df['volume_sma_7'] = df['volume'].rolling(window=7).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma_7']

        # RSI calculation
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)

        # Drop NaN rows from feature engineering
        df = df.dropna()

        return df

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _prepare_sequences(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for LSTM training

        Returns:
            X: Input sequences [samples, sequence_length, features]
            y: Target prices [samples, prediction_horizon]
        """
        # Select feature columns
        feature_cols = [col for col in df.columns if col not in ['timestamp', 'symbol']]
        self.feature_columns = feature_cols

        # Extract values
        data = df[feature_cols].values

        # Scale features
        scaled_data = self.feature_scaler.fit_transform(data)

        # Prepare sequences
        X, y = [], []

        for i in range(len(scaled_data) - self.sequence_length - self.prediction_horizon):
            # Input sequence
            X.append(scaled_data[i:i + self.sequence_length])

            # Target: future close prices
            close_idx = feature_cols.index('close')
            future_prices = scaled_data[
                i + self.sequence_length:i + self.sequence_length + self.prediction_horizon,
                close_idx
            ]
            y.append(future_prices)

        return np.array(X), np.array(y)

    def _build_lstm_model(self, input_shape: Tuple) -> keras.Model:
        """
        Build LSTM model architecture

        Architecture:
        - 2 LSTM layers with dropout
        - Dense layer
        - Output layer (prediction_horizon outputs)
        """
        model = keras.Sequential([
            # First LSTM layer
            layers.LSTM(
                units=128,
                return_sequences=True,
                input_shape=input_shape
            ),
            layers.Dropout(0.2),

            # Second LSTM layer
            layers.LSTM(
                units=64,
                return_sequences=False
            ),
            layers.Dropout(0.2),

            # Dense layers
            layers.Dense(32, activation='relu'),
            layers.Dropout(0.1),

            # Output layer (predict N future prices)
            layers.Dense(self.prediction_horizon)
        ])

        # Compile model
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=settings.learning_rate),
            loss='mean_squared_error',
            metrics=['mae']
        )

        return model

    async def train(self, historical_data: Union[pd.DataFrame, List[Dict]]) -> ModelInfo:
        """
        Train LSTM model on historical data

        Args:
            historical_data: DataFrame or list with columns [timestamp, open, high, low, close, volume]

        Returns:
            ModelInfo with training statistics
        """
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow not available. Cannot train model.")

        # Convert to DataFrame if needed
        if isinstance(historical_data, list):
            historical_data = pd.DataFrame(historical_data)

        logger.info(f"Training model for {self.symbol} {self.interval}m with {len(historical_data)} samples")
        start_time = datetime.utcnow()

        try:
            # Feature engineering
            df = self._create_features(historical_data)
            logger.info(f"Created {len(df.columns)} features from {len(df)} samples")

            # Prepare sequences
            X, y = self._prepare_sequences(df)
            logger.info(f"Prepared sequences: X shape={X.shape}, y shape={y.shape}")

            # Train/test split
            split_idx = int(len(X) * settings.train_test_split)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Build model
            self.model = self._build_lstm_model(input_shape=(X.shape[1], X.shape[2]))
            logger.info("Built LSTM model")

            # Train model
            history = self.model.fit(
                X_train, y_train,
                epochs=settings.epochs,
                batch_size=settings.batch_size,
                validation_data=(X_test, y_test),
                verbose=0,
                callbacks=[
                    keras.callbacks.EarlyStopping(
                        monitor='val_loss',
                        patience=10,
                        restore_best_weights=True
                    )
                ]
            )

            # Evaluate model
            y_pred = self.model.predict(X_test, verbose=0)

            # Calculate metrics (on first prediction step only for simplicity)
            mae = mean_absolute_error(y_test[:, 0], y_pred[:, 0])
            rmse = np.sqrt(mean_squared_error(y_test[:, 0], y_pred[:, 0]))
            r2 = r2_score(y_test[:, 0], y_pred[:, 0])

            # Save model
            self.model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            self.last_trained = datetime.utcnow()
            self.training_stats = {
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'final_train_loss': float(history.history['loss'][-1]),
                'final_val_loss': float(history.history['val_loss'][-1]),
                'mae': float(mae),
                'rmse': float(rmse),
                'r2_score': float(r2)
            }

            self._save_model()

            training_duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info(f"Training complete! MAE={mae:.4f}, RMSE={rmse:.4f}, R²={r2:.4f}")

            return ModelInfo(
                model_type=settings.model_type,
                model_version=self.model_version,
                symbols_supported=[self.symbol],
                intervals_supported=[f"{self.interval}m"],
                last_trained=self.last_trained,
                training_samples=len(X_train),
                training_duration_seconds=training_duration,
                validation_accuracy=float(r2),
                validation_mae=float(mae),
                validation_rmse=float(rmse),
                validation_r2_score=float(r2),
                top_features=[],
                status="READY",
                needs_retraining=False
            )

        except Exception as e:
            logger.error(f"Training failed: {e}")
            raise

    async def predict(self, recent_data: Union[pd.DataFrame, List[Dict]]) -> PricePrediction:
        """
        Make price predictions using trained model

        Args:
            recent_data: Recent price data (at least sequence_length rows)

        Returns:
            PricePrediction with future price points
        """
        if not TENSORFLOW_AVAILABLE or self.model is None:
            raise RuntimeError("Model not available for predictions")

        # Convert to DataFrame if needed
        if isinstance(recent_data, list):
            recent_data = pd.DataFrame(recent_data)

        try:
            # Sort data by timestamp ascending (oldest first) for time-series processing
            if 'timestamp' in recent_data.columns:
                recent_data = recent_data.sort_values('timestamp', ascending=True).reset_index(drop=True)

            # Store the actual current price BEFORE feature engineering (which may drop rows)
            actual_current_price = float(recent_data.iloc[-1]['close'])
            actual_current_timestamp = recent_data.iloc[-1]['timestamp'] if 'timestamp' in recent_data.columns else datetime.utcnow()

            # Feature engineering on recent data
            df = self._create_features(recent_data)

            # Get last sequence
            if len(df) < self.sequence_length:
                raise ValueError(f"Need at least {self.sequence_length} data points, got {len(df)}")

            last_sequence = df.iloc[-self.sequence_length:]
            feature_cols = [col for col in last_sequence.columns if col not in ['timestamp', 'symbol']]
            sequence_data = last_sequence[feature_cols].values

            # Scale
            scaled_sequence = self.feature_scaler.transform(sequence_data)

            # Reshape for prediction
            X = np.array([scaled_sequence])

            # Predict
            prediction = self.model.predict(X, verbose=0)[0]

            # Get close price index for inverse scaling
            close_idx = feature_cols.index('close')

            # Use the actual current price we stored before feature engineering
            current_price = actual_current_price

            # Build prediction points
            predictions = []
            # Use the actual current timestamp for proper future time calculation
            base_timestamp = actual_current_timestamp if isinstance(actual_current_timestamp, datetime) else datetime.utcnow()

            for i, pred_value in enumerate(prediction):
                # Calculate timestamp for this prediction
                future_timestamp = base_timestamp + timedelta(minutes=int(self.interval) * (i + 1))

                # Inverse scale prediction using proper method:
                # The model outputs scaled values [0-1], we need to convert back to price
                # Use the current price as anchor and apply relative change
                price_range = df['close'].max() - df['close'].min()
                if price_range > 0:
                    # Scale predicted value relative to current price
                    # pred_value is in scaled space, convert to price change ratio
                    scaled_current = (current_price - df['close'].min()) / price_range
                    price_change_ratio = pred_value - scaled_current
                    predicted_price = float(current_price * (1 + price_change_ratio * 0.1))  # Dampen extreme predictions
                else:
                    predicted_price = float(current_price)

                # Calculate confidence (based on model performance and prediction variance)
                base_confidence = float(self.training_stats.get('r2_score', 0.5))
                confidence_decay = 0.1 * i  # Confidence decreases with time horizon
                confidence = max(0.3, base_confidence - confidence_decay)

                # Confidence intervals (±2 standard deviations)
                std_dev = float(self.training_stats.get('rmse', predicted_price * 0.02))
                lower_bound = predicted_price - (2 * std_dev)
                upper_bound = predicted_price + (2 * std_dev)

                predictions.append(PricePoint(
                    timestamp=future_timestamp,
                    predicted_price=predicted_price,
                    confidence=confidence,
                    lower_bound=lower_bound,
                    upper_bound=upper_bound
                ))

            # Determine overall direction
            avg_predicted = np.mean([p.predicted_price for p in predictions])
            price_change_pct = ((avg_predicted - current_price) / current_price) * 100

            if price_change_pct > 1.0:
                direction = "UP"
            elif price_change_pct < -1.0:
                direction = "DOWN"
            else:
                direction = "SIDEWAYS"

            directional_strength = min(1.0, abs(price_change_pct) / 5.0)  # 5% change = 100% strength

            return PricePrediction(
                symbol=self.symbol,
                interval=f"{self.interval}m",
                current_price=current_price,
                predictions=predictions,
                model_type=settings.model_type,
                model_version=self.model_version or "unknown",
                model_last_trained=self.last_trained or datetime.utcnow(),
                average_confidence=float(np.mean([p.confidence for p in predictions])),
                prediction_horizon_minutes=int(self.interval) * self.prediction_horizon,
                predicted_direction=direction,
                directional_strength=directional_strength
            )

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise

    def needs_retraining(self) -> bool:
        """Check if model needs retraining based on age"""
        if not self.last_trained:
            return True

        days_since_training = (datetime.utcnow() - self.last_trained).days
        return days_since_training >= settings.model_retrain_days
