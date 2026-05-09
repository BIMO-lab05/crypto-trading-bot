"""
GRU Price Predictor - Gated Recurrent Unit implementation
Handles model training, prediction, and persistence for GRU architecture

GRU is often faster and more memory-efficient than LSTM while maintaining
similar performance for many time series forecasting tasks.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Tuple, Optional, Dict
import logging
import json
from pathlib import Path
import pickle
import time

# ML libraries
try:
    from sklearn.preprocessing import MinMaxScaler
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
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


class GRUPricePredictor:
    """
    GRU-based price predictor

    GRU (Gated Recurrent Unit) is a type of RNN that:
    - Has fewer parameters than LSTM (no separate cell state)
    - Trains faster with similar or better performance
    - Better for datasets where long-term dependencies aren't critical
    - Uses update and reset gates instead of input/forget/output gates

    Uses historical price + technical indicators to predict future prices
    """

    def __init__(self, symbol: str, interval: str = "60"):
        """
        Initialize GRU predictor for a specific symbol/interval

        Args:
            symbol: Trading pair (e.g., BTCUSDT)
            interval: Timeframe in minutes (e.g., 60 for 1 hour)
        """
        self.symbol = symbol
        self.interval = interval
        self.sequence_length = settings.sequence_length  # 60 timesteps
        self.prediction_horizon = settings.prediction_horizon  # 5 steps ahead

        # Model components
        self.model: Optional[keras.Model] = None
        self.price_scaler = MinMaxScaler(feature_range=(0, 1))
        self.feature_scaler = MinMaxScaler(feature_range=(0, 1))

        # Model metadata
        self.model_version = None
        self.last_trained = None
        self.training_stats = {}
        self.inference_time_ms = 0.0  # Track inference speed

        # Track when the on-disk model file was last loaded (mtime, seconds since epoch).
        # Used by _reload_if_stale to pick up retrained models without a service restart.
        self.model_loaded_at: float = 0.0

        # Feature columns
        self.feature_columns = []

        # Load existing model if available
        self._load_model()

    def _get_model_path(self) -> Path:
        """Get path to saved GRU model"""
        models_dir = Path(settings.models_dir)
        models_dir.mkdir(parents=True, exist_ok=True)
        return models_dir / f"{self.symbol}_{self.interval}m_gru.keras"

    def _get_metadata_path(self) -> Path:
        """Get path to model metadata"""
        models_dir = Path(settings.models_dir)
        return models_dir / f"{self.symbol}_{self.interval}m_gru_metadata.json"

    def _load_model(self) -> bool:
        """Load pre-trained GRU model and metadata"""
        try:
            if not TENSORFLOW_AVAILABLE:
                logger.warning("TensorFlow not available, cannot load model")
                return False

            model_path = self._get_model_path()
            metadata_path = self._get_metadata_path()

            if not model_path.exists():
                logger.info(f"No trained GRU model found for {self.symbol} {self.interval}m")
                return False

            # Load model
            self.model = keras.models.load_model(str(model_path))
            self.model_loaded_at = model_path.stat().st_mtime
            logger.info(f"Loaded GRU model from {model_path} (mtime={self.model_loaded_at})")

            # Load metadata
            if metadata_path.exists():
                with open(metadata_path, 'r') as f:
                    metadata = json.load(f)
                    self.model_version = metadata.get('model_version')
                    self.last_trained = datetime.fromisoformat(metadata.get('last_trained'))
                    self.training_stats = metadata.get('training_stats', {})
                    self.feature_columns = metadata.get('feature_columns', [])
                    self.inference_time_ms = metadata.get('inference_time_ms', 0.0)

                    # Load scalers
                    scaler_path = self._get_model_path().parent / f"{self.symbol}_{self.interval}m_gru_scalers.pkl"
                    if scaler_path.exists():
                        with open(scaler_path, 'rb') as f:
                            scaler_data = pickle.load(f)
                            self.price_scaler = scaler_data['price_scaler']
                            self.feature_scaler = scaler_data['feature_scaler']

                logger.info(f"Loaded GRU metadata: version={self.model_version}, trained={self.last_trained}")
                return True

        except Exception as e:
            logger.error(f"Error loading GRU model: {e}")
            return False

    def _reload_if_stale(self) -> bool:
        """
        Reload the model from disk if its mtime is newer than the cached load-time.

        Called at the top of predict() to pick up retrained models without a
        service restart. One stat() per request — overhead is negligible against
        the 10-50 ms predict path. Tolerant of missing files / stat errors:
        a failure leaves the cached model in place and predict() proceeds.

        Returns:
            True if a reload happened, False otherwise.
        """
        try:
            model_path = self._get_model_path()
            if not model_path.exists():
                return False
            disk_mtime = model_path.stat().st_mtime
            if disk_mtime > self.model_loaded_at:
                logger.info(
                    f"Stale GRU model for {self.symbol} {self.interval}m; reloading "
                    f"(loaded={self.model_loaded_at}, disk={disk_mtime})"
                )
                # _load_model resets model, scalers, metadata, and model_loaded_at
                return self._load_model()
        except Exception as e:
            logger.warning(f"Stale-check failed for {self.symbol}: {e}")
        return False

    def _save_model(self):
        """Save trained GRU model and metadata"""
        try:
            model_path = self._get_model_path()
            metadata_path = self._get_metadata_path()

            # Save model
            self.model.save(str(model_path))
            logger.info(f"Saved GRU model to {model_path}")

            # Save metadata
            metadata = {
                'model_type': 'GRU',
                'symbol': self.symbol,
                'interval': self.interval,
                'model_version': self.model_version,
                'last_trained': self.last_trained.isoformat(),
                'training_stats': self.training_stats,
                'feature_columns': self.feature_columns,
                'sequence_length': self.sequence_length,
                'prediction_horizon': self.prediction_horizon,
                'inference_time_ms': self.inference_time_ms
            }

            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save scalers
            scaler_path = model_path.parent / f"{self.symbol}_{self.interval}m_gru_scalers.pkl"
            with open(scaler_path, 'wb') as f:
                pickle.dump({
                    'price_scaler': self.price_scaler,
                    'feature_scaler': self.feature_scaler
                }, f)

            logger.info(f"Saved GRU model metadata to {metadata_path}")

        except Exception as e:
            logger.error(f"Error saving GRU model: {e}")

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Engineer features from price data + technical indicators

        Same feature engineering as LSTM for fair comparison

        Features include:
        - Price features: open, high, low, close, volume
        - Returns: 1-period, 5-period, 10-period log returns
        - Momentum: price momentum over different periods
        - Moving averages: SMA/EMA various periods
        - Price position relative to MAs
        - Volatility: high-low range, rolling std
        - Volume features: volume ratios
        - Technical indicators: RSI
        """
        df = df.copy()

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
        """Calculate RSI (Relative Strength Index) indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _prepare_sequences(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare sequences for GRU training

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

    def _build_gru_model(self, input_shape: Tuple) -> keras.Model:
        """
        Build GRU model architecture

        Architecture:
        - 2 GRU layers with dropout (fewer params than LSTM)
        - Dense layer for non-linear transformations
        - Output layer for multi-step predictions

        GRU advantages:
        - Faster training (25-30% faster than LSTM)
        - Fewer parameters (2/3 of LSTM parameters)
        - Similar or better performance on many tasks
        - Better generalization on smaller datasets

        Args:
            input_shape: Tuple of (sequence_length, num_features)

        Returns:
            Compiled Keras model
        """
        model = keras.Sequential([
            # First GRU layer - returns sequences for next layer
            layers.GRU(
                units=128,
                return_sequences=True,  # Return full sequence for next GRU layer
                input_shape=input_shape,
                name='gru_layer_1'
            ),
            layers.Dropout(0.2, name='dropout_1'),  # Prevent overfitting

            # Second GRU layer - returns only final output
            layers.GRU(
                units=64,
                return_sequences=False,  # Only return final output
                name='gru_layer_2'
            ),
            layers.Dropout(0.2, name='dropout_2'),

            # Dense layers for non-linear transformations
            layers.Dense(32, activation='relu', name='dense_1'),
            layers.Dropout(0.1, name='dropout_3'),

            # Output layer - predict N future prices
            layers.Dense(self.prediction_horizon, name='output')
        ])

        # Compile model with Adam optimizer
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=settings.learning_rate),
            loss='mean_squared_error',  # MSE for regression
            metrics=['mae', 'mse']  # Track MAE and MSE during training
        )

        return model

    async def train(self, historical_data: pd.DataFrame) -> ModelInfo:
        """
        Train GRU model on historical data

        Training pipeline:
        1. Feature engineering (create technical indicators)
        2. Sequence preparation (sliding windows)
        3. Train/test split (80/20)
        4. Model building (GRU architecture)
        5. Training with early stopping
        6. Performance evaluation
        7. Model persistence

        Args:
            historical_data: DataFrame with columns [timestamp, open, high, low, close, volume]

        Returns:
            ModelInfo with training statistics and performance metrics
        """
        if not TENSORFLOW_AVAILABLE:
            raise RuntimeError("TensorFlow not available. Cannot train model.")

        logger.info(f"Training GRU model for {self.symbol} {self.interval}m with {len(historical_data)} samples")
        start_time = datetime.utcnow()

        try:
            # Step 1: Feature engineering
            df = self._create_features(historical_data)
            logger.info(f"Created {len(df.columns)} features from {len(df)} samples")

            # Step 2: Prepare sequences
            X, y = self._prepare_sequences(df)
            logger.info(f"Prepared sequences: X shape={X.shape}, y shape={y.shape}")

            # Step 3: Train/test split (80/20)
            split_idx = int(len(X) * settings.train_test_split)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Step 4: Build GRU model
            self.model = self._build_gru_model(input_shape=(X.shape[1], X.shape[2]))
            logger.info(f"Built GRU model with {self.model.count_params()} parameters")

            # Step 5: Train model with early stopping
            history = self.model.fit(
                X_train, y_train,
                epochs=settings.epochs,
                batch_size=settings.batch_size,
                validation_data=(X_test, y_test),
                verbose=0,
                callbacks=[
                    keras.callbacks.EarlyStopping(
                        monitor='val_loss',
                        patience=10,  # Stop if no improvement for 10 epochs
                        restore_best_weights=True  # Restore best weights
                    ),
                    keras.callbacks.ReduceLROnPlateau(
                        monitor='val_loss',
                        factor=0.5,  # Reduce LR by 50%
                        patience=5,
                        min_lr=0.00001
                    )
                ]
            )

            # Step 6: Evaluate model on test set
            y_pred = self.model.predict(X_test, verbose=0)

            # Calculate comprehensive metrics
            # Use first prediction step for single-value metrics
            mae = mean_absolute_error(y_test[:, 0], y_pred[:, 0])
            rmse = np.sqrt(mean_squared_error(y_test[:, 0], y_pred[:, 0]))
            r2 = r2_score(y_test[:, 0], y_pred[:, 0])

            # Calculate MAPE (Mean Absolute Percentage Error)
            mape = mean_absolute_percentage_error(y_test[:, 0], y_pred[:, 0])

            # Reference is last bar of input sequence (prior bug used y_test[:, -1] —
            # a future bar — making the metric look-ahead leaked and degenerate).
            close_idx = self.feature_columns.index('close')
            last_input_close = X_test[:, -1, close_idx]
            y_test_direction = np.sign(y_test[:, 0] - last_input_close)
            y_pred_direction = np.sign(y_pred[:, 0] - last_input_close)
            directional_accuracy = np.mean(y_test_direction == y_pred_direction)

            # Measure inference time
            inference_start = time.time()
            _ = self.model.predict(X_test[:1], verbose=0)
            self.inference_time_ms = (time.time() - inference_start) * 1000

            # Step 7: Save model
            self.model_version = f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            self.last_trained = datetime.utcnow()
            self.training_stats = {
                'train_samples': len(X_train),
                'test_samples': len(X_test),
                'epochs_trained': len(history.history['loss']),
                'final_train_loss': float(history.history['loss'][-1]),
                'final_val_loss': float(history.history['val_loss'][-1]),
                'mae': float(mae),
                'rmse': float(rmse),
                'r2_score': float(r2),
                'mape': float(mape),
                'directional_accuracy': float(directional_accuracy),
                'total_parameters': int(self.model.count_params())
            }

            self._save_model()

            training_duration = (datetime.utcnow() - start_time).total_seconds()

            logger.info(
                f"GRU Training complete! MAE={mae:.4f}, RMSE={rmse:.4f}, "
                f"R²={r2:.4f}, MAPE={mape:.4f}, Dir_Acc={directional_accuracy:.4f}"
            )

            return ModelInfo(
                model_type='GRU',
                model_version=self.model_version,
                symbols_supported=[self.symbol],
                intervals_supported=[f"{self.interval}m"],
                last_trained=self.last_trained,
                training_samples=len(X_train),
                training_duration_seconds=training_duration,
                validation_accuracy=float(directional_accuracy),
                validation_mae=float(mae),
                validation_rmse=float(rmse),
                validation_r2_score=float(r2),
                top_features=[],  # Could add feature importance later
                status="READY",
                needs_retraining=False
            )

        except Exception as e:
            logger.error(f"GRU training failed: {e}")
            raise

    async def predict(self, recent_data: pd.DataFrame) -> PricePrediction:
        """
        Make price predictions using trained GRU model

        Prediction pipeline:
        1. Feature engineering on recent data
        2. Extract last sequence (60 timesteps)
        3. Scale features
        4. GRU forward pass
        5. Inverse scaling
        6. Build prediction objects with confidence intervals

        Args:
            recent_data: Recent price data (at least sequence_length rows)

        Returns:
            PricePrediction with future price points and metadata
        """
        # Pick up freshly retrained models without a restart (mtime check + reload).
        self._reload_if_stale()

        if not TENSORFLOW_AVAILABLE or self.model is None:
            raise RuntimeError("GRU model not available for predictions")

        try:
            # Measure inference time
            inference_start = time.time()

            # Step 1: Feature engineering on recent data
            df = self._create_features(recent_data)

            # Step 2: Get last sequence
            if len(df) < self.sequence_length:
                raise ValueError(f"Need at least {self.sequence_length} data points, got {len(df)}")

            last_sequence = df.iloc[-self.sequence_length:]
            feature_cols = [col for col in last_sequence.columns if col not in ['timestamp', 'symbol']]
            sequence_data = last_sequence[feature_cols].values

            # Step 3: Scale features
            scaled_sequence = self.feature_scaler.transform(sequence_data)

            # Reshape for prediction [1, sequence_length, features]
            X = np.array([scaled_sequence])

            # Step 4: Predict using GRU
            prediction = self.model.predict(X, verbose=0)[0]

            # Update inference time
            inference_time = (time.time() - inference_start) * 1000
            self.inference_time_ms = inference_time

            # Step 5: Inverse scaling and build predictions
            close_idx = feature_cols.index('close')
            current_price = float(df.iloc[-1]['close'])

            # Build prediction points
            predictions = []
            base_timestamp = df.iloc[-1]['timestamp'] if 'timestamp' in df.columns else datetime.utcnow()

            for i, pred_value in enumerate(prediction):
                # Calculate timestamp for this prediction
                future_timestamp = base_timestamp + timedelta(minutes=int(self.interval) * (i + 1))

                # Inverse scale prediction (approximate)
                predicted_price = float(pred_value * (df['close'].max() - df['close'].min()) + df['close'].min())

                # Calculate confidence (decreases with time horizon).
                # See predictor.py:480-490 for the rationale on the 0.0 floor.
                base_confidence = float(self.training_stats.get('r2_score', 0.5))
                confidence_decay = 0.1 * i  # Confidence decreases with time
                confidence = max(0.0, base_confidence - confidence_decay)

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
                model_type='GRU',
                model_version=self.model_version or "unknown",
                model_last_trained=self.last_trained or datetime.utcnow(),
                average_confidence=float(np.mean([p.confidence for p in predictions])),
                prediction_horizon_minutes=int(self.interval) * self.prediction_horizon,
                predicted_direction=direction,
                directional_strength=directional_strength
            )

        except Exception as e:
            logger.error(f"GRU prediction failed: {e}")
            raise

    def needs_retraining(self) -> bool:
        """Check if model needs retraining based on age"""
        if not self.last_trained:
            return True

        days_since_training = (datetime.utcnow() - self.last_trained).days
        return days_since_training >= settings.model_retrain_days

    def get_model_size_mb(self) -> float:
        """Get model file size in megabytes"""
        model_path = self._get_model_path()
        if model_path.exists():
            return model_path.stat().st_size / (1024 * 1024)
        return 0.0

    def get_performance_metrics(self) -> Dict:
        """
        Get comprehensive performance metrics for model comparison

        Returns:
            Dictionary with training stats, inference time, model size
        """
        return {
            'model_type': 'GRU',
            'training_stats': self.training_stats,
            'inference_time_ms': self.inference_time_ms,
            'model_size_mb': self.get_model_size_mb(),
            'total_parameters': self.training_stats.get('total_parameters', 0),
            'last_trained': self.last_trained.isoformat() if self.last_trained else None,
            'model_version': self.model_version
        }
