"""
Model Training Engine for GRU Models
Purpose: Train GRU models for price prediction with technical indicators
"""

import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import json
import pickle

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, callbacks
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

from app.config.settings import get_settings
from app.core.cpcv_evaluation import evaluate_with_cpcv
from app.core.returns_metrics import compute_returns_metrics
from app.core.stationary_features import (
    STATIONARY_FEATURE_COLS,
    compute_stationary_features,
)

logger = logging.getLogger(__name__)


class ModelTrainer:
    """
    Train GRU models for cryptocurrency price prediction

    Uses same architecture as current production models:
    - 2-layer GRU (128 units, 64 units)
    - Sequence length: 60
    - Prediction horizon: 5
    - Technical indicators as features
    """

    def __init__(self):
        """Initialize model trainer"""
        self.settings = get_settings()
        self.scaler_x = MinMaxScaler()
        self.scaler_y = MinMaxScaler()

        # Model configuration (same as current production models)
        self.sequence_length = 60  # 60 time steps (hours for 60min interval)
        self.prediction_horizon = 5  # Predict 5 hours ahead
        # GRU widths in order. Default [128, 64] = legacy production.
        # T0.1 rebuild script overrides via env to [32] (single-layer).
        self.gru_units = list(self.settings.retrain_gru_units)
        self.dropout_rate = 0.2

        # Target mode: 'price' (legacy) or 'log_returns' (T0.1 rebuild).
        # In log_returns mode, the model predicts log(close_{t+h}/close_{t+h-1});
        # downstream metric paths recover predicted prices via
        # last_close * exp(pred_log_return) so the existing returns_metrics
        # / CPCV plumbing keeps working unchanged.
        self.target_mode = self.settings.retrain_target_mode
        self.target_col = "close" if self.target_mode == "price" else "log_returns"

        # Feature set: 'legacy' (22-indicator pile, default) or
        # 'stationary' (17 stationary-only features for T0.1). See
        # app/core/stationary_features.py.
        self.feature_set = self.settings.retrain_feature_set

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators from OHLCV data.

        Dispatches on ``self.feature_set``:
        - ``"legacy"`` (default): the 22-indicator pile every production
          retrain has used; computed inline below.
        - ``"stationary"``: the 17-feature stationary-only set for the
          T0.1 GRU rebuild; delegated to
          ``app.core.stationary_features.compute_stationary_features``.

        Args:
            df: DataFrame with columns: timestamp, open, high, low, close, volume

        Returns:
            DataFrame with technical indicators as features
        """
        if self.feature_set == "stationary":
            logger.info(
                f"Preparing stationary features from {len(df)} data points"
            )
            return compute_stationary_features(df)

        logger.info(f"Preparing features from {len(df)} data points")

        # Make a copy to avoid modifying original
        data = df.copy()

        # Price-based features
        data['returns'] = data['close'].pct_change()
        data['log_returns'] = np.log(data['close'] / data['close'].shift(1))

        # Moving averages
        data['sma_7'] = data['close'].rolling(window=7).mean()
        data['sma_14'] = data['close'].rolling(window=14).mean()
        data['sma_30'] = data['close'].rolling(window=30).mean()
        data['ema_7'] = data['close'].ewm(span=7, adjust=False).mean()
        data['ema_14'] = data['close'].ewm(span=14, adjust=False).mean()

        # Volatility
        data['volatility_7'] = data['returns'].rolling(window=7).std()
        data['volatility_14'] = data['returns'].rolling(window=14).std()

        # RSI (Relative Strength Index)
        delta = data['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        data['rsi'] = 100 - (100 / (1 + rs))

        # MACD
        ema_12 = data['close'].ewm(span=12, adjust=False).mean()
        ema_26 = data['close'].ewm(span=26, adjust=False).mean()
        data['macd'] = ema_12 - ema_26
        data['macd_signal'] = data['macd'].ewm(span=9, adjust=False).mean()
        data['macd_hist'] = data['macd'] - data['macd_signal']

        # Bollinger Bands
        data['bb_middle'] = data['close'].rolling(window=20).mean()
        bb_std = data['close'].rolling(window=20).std()
        data['bb_upper'] = data['bb_middle'] + (2 * bb_std)
        data['bb_lower'] = data['bb_middle'] - (2 * bb_std)
        data['bb_width'] = (data['bb_upper'] - data['bb_lower']) / data['bb_middle']

        # Volume indicators
        data['volume_sma'] = data['volume'].rolling(window=20).mean()
        data['volume_ratio'] = data['volume'] / data['volume_sma']

        # Price position in range
        data['high_low_ratio'] = (data['close'] - data['low']) / (data['high'] - data['low'])

        # Momentum
        data['momentum_7'] = data['close'] / data['close'].shift(7) - 1
        data['momentum_14'] = data['close'] / data['close'].shift(14) - 1

        # Drop rows with NaN values (from indicators calculation)
        data_clean = data.dropna()

        logger.info(
            f"Features prepared: {len(data_clean)} valid rows "
            f"({len(df) - len(data_clean)} rows dropped due to NaN)"
        )

        return data_clean

    def create_sequences(
        self,
        data: pd.DataFrame,
        target_col: str = 'close',
        feature_cols: Optional[List[str]] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create sequences for GRU training

        Args:
            data: DataFrame with features
            target_col: Column name for prediction target
            feature_cols: Explicit feature column list. When None (legacy
                callers), uses every column except ``timestamp`` and
                ``target_col``. The trainer passes
                ``STATIONARY_FEATURE_COLS`` here in stationary mode so the
                model never sees ``close`` or other level columns even
                when they remain in the DataFrame for ``last_close``
                extraction downstream.

        Returns:
            Tuple of (X, y) where:
                X: shape (samples, sequence_length, features)
                y: shape (samples, prediction_horizon)
        """
        logger.info(f"Creating sequences: length={self.sequence_length}, horizon={self.prediction_horizon}")

        # Select feature columns: explicit list wins, else exclude
        # timestamp + target_col as legacy callers expect.
        if feature_cols is None:
            feature_cols = [
                col for col in data.columns
                if col not in ['timestamp', target_col]
            ]

        # Extract features and target
        features = data[feature_cols].values
        target = data[target_col].values

        # Scale features and target
        features_scaled = self.scaler_x.fit_transform(features)
        target_scaled = self.scaler_y.fit_transform(target.reshape(-1, 1)).flatten()

        X, y = [], []

        # Create sequences
        for i in range(len(data) - self.sequence_length - self.prediction_horizon):
            # Input: sequence of features
            X.append(features_scaled[i:i + self.sequence_length])

            # Output: future prices (prediction_horizon steps ahead)
            y.append(target_scaled[i + self.sequence_length:i + self.sequence_length + self.prediction_horizon])

        X = np.array(X)
        y = np.array(y)

        logger.info(f"Created {len(X)} sequences: X shape={X.shape}, y shape={y.shape}")

        return X, y

    def build_gru_model(self, input_shape: Tuple[int, int]) -> keras.Model:
        """
        Build GRU model architecture from ``self.gru_units``.

        Stacks ``len(self.gru_units)`` GRU layers in order. All layers
        except the last set ``return_sequences=True``; the last sets
        ``return_sequences=False`` so it feeds a Dense head. Dropout is
        applied after every GRU layer. Default ``[128, 64]`` is the
        legacy 2-layer architecture; ``[32]`` is the T0.1 rebuild's
        single-layer pick (smaller nets generalise better on low-SNR
        log-return targets).

        Args:
            input_shape: (sequence_length, num_features)

        Returns:
            Compiled Keras model
        """
        logger.info(
            f"Building GRU model with input shape: {input_shape}, "
            f"layers={self.gru_units}"
        )

        n_layers = len(self.gru_units)
        model = keras.Sequential()
        for i, units in enumerate(self.gru_units):
            return_sequences = (i < n_layers - 1)
            if i == 0:
                model.add(
                    layers.GRU(
                        units,
                        return_sequences=return_sequences,
                        input_shape=input_shape,
                    )
                )
            else:
                model.add(
                    layers.GRU(units, return_sequences=return_sequences)
                )
            model.add(layers.Dropout(self.dropout_rate))

        # Dense output layer (prediction_horizon outputs)
        model.add(layers.Dense(self.prediction_horizon))

        # Compile model
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss='mse',
            metrics=['mae'],
        )

        logger.info(f"Model built: {model.count_params():,} parameters")

        return model

    def train_model(
        self,
        data: pd.DataFrame,
        symbol: str,
        interval: str = "60",
        test_size: float = 0.2,
        validation_split: float = 0.2
    ) -> Dict[str, Any]:
        """
        Train GRU model with given data

        Args:
            data: DataFrame with OHLCV data
            symbol: Trading symbol (e.g., "SOLUSDT")
            interval: Kline interval
            test_size: Fraction of data for testing
            validation_split: Fraction of training data for validation

        Returns:
            Dict containing:
                - model: Trained Keras model
                - scaler_x: Feature scaler
                - scaler_y: Target scaler
                - train_metrics: Training metrics
                - val_metrics: Validation metrics
                - test_metrics: Test metrics
                - history: Training history
                - metadata: Model metadata
        """
        logger.info(f"Starting training for {symbol} ({interval}min)")
        start_time = datetime.now()

        try:
            # Step 1: Prepare features
            data_with_features = self.prepare_features(data)

            if len(data_with_features) < self.sequence_length + self.prediction_horizon + 100:
                raise ValueError(
                    f"Insufficient data after feature preparation: {len(data_with_features)} rows. "
                    f"Need at least {self.sequence_length + self.prediction_horizon + 100}"
                )

            # Step 2: Create sequences (target_col flips on target_mode;
            # feature_cols flips on feature_set — stationary mode passes
            # an explicit list so close / level features are excluded)
            feature_cols_used: Optional[List[str]] = (
                list(STATIONARY_FEATURE_COLS)
                if self.feature_set == "stationary"
                else None
            )
            X, y = self.create_sequences(
                data_with_features,
                target_col=self.target_col,
                feature_cols=feature_cols_used,
            )

            # Step 3: Split data (train/test)
            X_train, X_test, y_train, y_test = train_test_split(
                X, y,
                test_size=test_size,
                shuffle=False  # Don't shuffle time series data
            )

            logger.info(
                f"Data split: train={len(X_train)}, test={len(X_test)} "
                f"({test_size*100:.0f}% test)"
            )

            # Step 4: Build model
            model = self.build_gru_model(input_shape=(X_train.shape[1], X_train.shape[2]))

            # Step 5: Setup callbacks
            early_stopping = callbacks.EarlyStopping(
                monitor='val_loss',
                patience=10,
                restore_best_weights=True,
                verbose=1
            )

            reduce_lr = callbacks.ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=0.00001,
                verbose=1
            )

            # Step 6: Train model
            logger.info(f"Training model (max {self.settings.retrain_max_epochs} epochs)...")

            history = model.fit(
                X_train, y_train,
                epochs=self.settings.retrain_max_epochs,
                batch_size=self.settings.retrain_batch_size,
                validation_split=validation_split,
                callbacks=[early_stopping, reduce_lr],
                verbose=1
            )

            training_time = (datetime.now() - start_time).total_seconds()
            epochs_trained = len(history.history['loss'])

            logger.info(
                f"Training complete: {epochs_trained} epochs in {training_time:.1f}s "
                f"({training_time/epochs_trained:.1f}s/epoch)"
            )

            # Step 7: Calculate metrics
            train_metrics = self._calculate_metrics(model, X_train, y_train, "train")
            test_metrics = self._calculate_metrics(model, X_test, y_test, "test")

            # Honest skill-on-returns metrics. References are the close of the
            # last bar of each input sequence (sample i in X uses index
            # i + sequence_length - 1 in data_with_features).
            close_unscaled = data_with_features['close'].values
            last_close_train = close_unscaled[
                self.sequence_length - 1 :
                self.sequence_length - 1 + len(X_train)
            ]
            last_close_test = close_unscaled[
                self.sequence_length - 1 + len(X_train) :
                self.sequence_length - 1 + len(X_train) + len(X_test)
            ]
            train_metrics.update(
                self._calculate_returns_metrics(
                    model, X_train, y_train, last_close_train, "train"
                )
            )
            test_metrics.update(
                self._calculate_returns_metrics(
                    model, X_test, y_test, last_close_test, "test"
                )
            )

            # Evaluation-time CPCV on the test set: derive a strategy-return
            # series from (actual, predicted, last_close) and run combinatorial
            # purged folds. Emits Deflated Sharpe + per-path Sharpe distribution
            # into test_metrics. See docs/strategy/research-2026-04-29/
            # T0.2-cpcv-design.md §4 — evaluation-time, not retraining-time.
            cpcv_metrics, eval_arrays = self._calculate_cpcv_metrics(
                model, X_test, y_test, last_close_test, "test"
            )
            test_metrics.update(cpcv_metrics)

            # Validation metrics (last epoch from history)
            val_metrics = {
                "val_loss": float(history.history['val_loss'][-1]),
                "val_mae": float(history.history['val_mae'][-1]),
            }

            # Add R² for validation set (predict on validation portion)
            val_split_idx = int(len(X_train) * (1 - validation_split))
            X_val = X_train[val_split_idx:]
            y_val = y_train[val_split_idx:]

            y_val_pred = model.predict(X_val, verbose=0)

            # Inverse transform for R² calculation
            y_val_actual = self.scaler_y.inverse_transform(y_val)
            y_val_pred_actual = self.scaler_y.inverse_transform(y_val_pred)

            val_r2 = r2_score(y_val_actual.flatten(), y_val_pred_actual.flatten())
            val_metrics["val_r2"] = float(val_r2)

            # Step 8: Create metadata
            metadata = {
                "version": f"v{datetime.now().strftime('%Y-%m-%d_%H-%M')}",
                "symbol": symbol,
                "interval": interval,
                "model_type": "GRU",
                "target_mode": self.target_mode,
                "target_col": self.target_col,
                "feature_set": self.feature_set,
                "architecture": {
                    "layers": self.gru_units,
                    "sequence_length": self.sequence_length,
                    "prediction_horizon": self.prediction_horizon,
                    "dropout_rate": self.dropout_rate,
                },
                "training": {
                    "data_range": f"{data['timestamp'].min()} to {data['timestamp'].max()}",
                    "samples_total": len(X),
                    "samples_train": len(X_train),
                    "samples_test": len(X_test),
                    "epochs_trained": epochs_trained,
                    "training_time_seconds": training_time,
                    "batch_size": self.settings.retrain_batch_size,
                },
                "features": {
                    "num_features": X_train.shape[2],
                    "feature_names": (
                        feature_cols_used
                        if feature_cols_used is not None
                        else [
                            col for col in data_with_features.columns
                            if col not in ['timestamp', self.target_col]
                        ]
                    ),
                },
            }

            logger.info(f"✅ Training successful: R²={train_metrics['train_r2']:.4f}, Val R²={val_r2:.4f}")

            return {
                "success": True,
                "model": model,
                "scaler_x": self.scaler_x,
                "scaler_y": self.scaler_y,
                "train_metrics": train_metrics,
                "val_metrics": val_metrics,
                "test_metrics": test_metrics,
                "history": history.history,
                "metadata": metadata,
                "eval_arrays": eval_arrays,
            }

        except Exception as e:
            logger.error(f"❌ Training failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "metadata": {
                    "symbol": symbol,
                    "interval": interval,
                    "training_time_seconds": (datetime.now() - start_time).total_seconds(),
                }
            }

    def _recover_prices(
        self,
        y_unscaled_first_step: np.ndarray,
        last_close: np.ndarray,
    ) -> np.ndarray:
        """
        Translate the model's first-step target to a 1-bar-ahead price.

        Price-mode targets are already prices — returned unchanged. In
        log-returns mode, the model predicts ``log(close_{t+1}/last_close)``,
        recovered as ``last_close * exp(pred_log_return)``. Keeps the
        downstream returns-metrics / CPCV plumbing price-shaped regardless
        of target_mode.
        """
        y_unscaled_first_step = np.asarray(y_unscaled_first_step, dtype=float)
        if self.target_mode == "log_returns":
            last_close = np.asarray(last_close, dtype=float)
            return last_close * np.exp(y_unscaled_first_step)
        return y_unscaled_first_step

    def _calculate_cpcv_metrics(
        self,
        model: keras.Model,
        X: np.ndarray,
        y: np.ndarray,
        last_close: np.ndarray,
        dataset_name: str,
    ) -> Tuple[Dict[str, float], Dict[str, np.ndarray]]:
        """
        Evaluation-time CPCV on (actual, predicted, last_close) triples.

        Returns:
            (cpcv_metrics, eval_arrays) where ``cpcv_metrics`` is a flat
            ``{dataset}_*`` dict ready to merge into test_metrics, and
            ``eval_arrays`` is the underlying numpy triple — persisted by
            ``save_model`` as ``eval_arrays.npz`` so risk-metrics-service
            can re-run CPCV later with different group/horizon settings.

        Conservative ``label_horizon = sequence_length + prediction_horizon - 1``
        accounts for both the model's prediction horizon and the input
        window's bar overlap between adjacent samples — see
        T0.2-cpcv-design.md §2.
        """
        y_pred = model.predict(X, verbose=0)
        actual_unscaled = self.scaler_y.inverse_transform(y)[:, 0]
        pred_unscaled = self.scaler_y.inverse_transform(y_pred)[:, 0]
        actual_prices = self._recover_prices(actual_unscaled, last_close)
        pred_prices = self._recover_prices(pred_unscaled, last_close)

        label_horizon = self.sequence_length + self.prediction_horizon - 1
        cpcv_metrics = evaluate_with_cpcv(
            actual_prices,
            pred_prices,
            last_close,
            dataset_name=dataset_name,
            label_horizon=label_horizon,
        )

        eval_arrays = {
            "actual_prices": np.asarray(actual_prices, dtype=float),
            "pred_prices": np.asarray(pred_prices, dtype=float),
            "last_close": np.asarray(last_close, dtype=float),
        }
        return cpcv_metrics, eval_arrays

    def _calculate_returns_metrics(
        self,
        model: keras.Model,
        X: np.ndarray,
        y: np.ndarray,
        last_close: np.ndarray,
        dataset_name: str,
    ) -> Dict[str, float]:
        """
        Honest skill-on-returns metrics, complementing _calculate_metrics().

        The existing R² in _calculate_metrics is on raw close-price levels
        and is dominated by autocorrelation — a persistence baseline gets
        the same number on hourly crypto. This computes:

          {dataset}_r2_returns       — R² on log-returns from last input bar
          {dataset}_dir_acc_corrected — directional accuracy with the input
                                         sequence's last bar as reference

        References docs/strategy/research-2026-04-29/V0-FINDINGS-gru-metric-bug.md.
        """
        y_pred = model.predict(X, verbose=0)
        actual_unscaled = self.scaler_y.inverse_transform(y)[:, 0]
        pred_unscaled = self.scaler_y.inverse_transform(y_pred)[:, 0]
        actual_prices = self._recover_prices(actual_unscaled, last_close)
        pred_prices = self._recover_prices(pred_unscaled, last_close)
        return compute_returns_metrics(
            actual_prices, pred_prices, last_close, dataset_name
        )

    def _calculate_metrics(
        self,
        model: keras.Model,
        X: np.ndarray,
        y: np.ndarray,
        dataset_name: str
    ) -> Dict[str, float]:
        """
        Calculate comprehensive metrics for a dataset

        Args:
            model: Trained model
            X: Input features
            y: True targets (scaled)
            dataset_name: Name for logging (e.g., "train", "test")

        Returns:
            Dict with loss, MAE, MSE, RMSE, R²
        """
        # Predictions
        y_pred = model.predict(X, verbose=0)

        # Inverse transform to original scale
        y_actual = self.scaler_y.inverse_transform(y)
        y_pred_actual = self.scaler_y.inverse_transform(y_pred)

        # Calculate metrics
        mse = mean_squared_error(y_actual.flatten(), y_pred_actual.flatten())
        mae = mean_absolute_error(y_actual.flatten(), y_pred_actual.flatten())
        rmse = np.sqrt(mse)
        r2 = r2_score(y_actual.flatten(), y_pred_actual.flatten())

        # Also get model's loss (on scaled data)
        loss = model.evaluate(X, y, verbose=0)[0]

        metrics = {
            f"{dataset_name}_loss": float(loss),
            f"{dataset_name}_mae": float(mae),
            f"{dataset_name}_mse": float(mse),
            f"{dataset_name}_rmse": float(rmse),
            f"{dataset_name}_r2": float(r2),
        }

        logger.info(
            f"{dataset_name.upper()} metrics: "
            f"Loss={loss:.4f}, MAE={mae:.2f}, RMSE={rmse:.2f}, R²={r2:.4f}"
        )

        return metrics

    def save_model(
        self,
        model: keras.Model,
        metadata: Dict[str, Any],
        train_metrics: Dict[str, float],
        val_metrics: Dict[str, float],
        test_metrics: Dict[str, float],
        scaler_x: MinMaxScaler,
        scaler_y: MinMaxScaler,
        output_dir: str,
        eval_arrays: Optional[Dict[str, np.ndarray]] = None,
    ) -> Dict[str, str]:
        """
        Save trained model and metadata to disk

        Args:
            model: Trained Keras model
            metadata: Model metadata
            train_metrics: Training metrics
            val_metrics: Validation metrics
            test_metrics: Test metrics
            scaler_x: Feature scaler
            scaler_y: Target scaler
            output_dir: Directory to save files
            eval_arrays: Optional dict of evaluation arrays (e.g. actual_prices,
                pred_prices, last_close from the held-out test set). Persisted
                as ``eval_arrays.npz`` so CPCV / DSR can be re-run later
                without retraining — see ``_calculate_cpcv_metrics``.

        Returns:
            Dict with paths to saved files
        """
        logger.info(f"Saving model to {output_dir}")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # File paths
        model_path = os.path.join(output_dir, "model.h5")
        metadata_path = os.path.join(output_dir, "metadata.json")
        metrics_path = os.path.join(output_dir, "metrics.json")
        # Single combined scalers.pkl matching the prediction-service contract:
        # {'price_scaler': MinMaxScaler, 'feature_scaler': MinMaxScaler} as full
        # sklearn objects (gru_model.py:_load_model in ml-prediction-service).
        scalers_path = os.path.join(output_dir, "scalers.pkl")

        # Save model
        model.save(model_path)
        logger.info(f"Model saved: {model_path}")

        # Save metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        logger.info(f"Metadata saved: {metadata_path}")

        # Save metrics
        all_metrics = {
            **train_metrics,
            **val_metrics,
            **test_metrics,
        }
        with open(metrics_path, 'w') as f:
            json.dump(all_metrics, f, indent=2)
        logger.info(f"Metrics saved: {metrics_path}")

        # Save scalers as a single pickle file matching the prediction-service
        # contract. Mapping: scaler_y is fit on the target/close-price column
        # (price_scaler); scaler_x is fit on the feature columns (feature_scaler).
        # Storing the full sklearn objects (not just attribute arrays) so the
        # prediction service can use them directly via pickle.load.
        with open(scalers_path, 'wb') as f:
            pickle.dump({
                'price_scaler': scaler_y,
                'feature_scaler': scaler_x,
            }, f)
        logger.info(f"Scalers saved: {scalers_path}")

        result = {
            "model_path": model_path,
            "metadata_path": metadata_path,
            "metrics_path": metrics_path,
            "scalers_path": scalers_path,
        }

        if eval_arrays:
            eval_arrays_path = os.path.join(output_dir, "eval_arrays.npz")
            np.savez(eval_arrays_path, **eval_arrays)
            logger.info(f"Eval arrays saved: {eval_arrays_path}")
            result["eval_arrays_path"] = eval_arrays_path

        return result
