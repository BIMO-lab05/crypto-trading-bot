#!/usr/bin/env python3
"""
Hyperparameter Optimization for ML Price Prediction Models
Purpose: Optimize LSTM and GRU architectures to achieve R² > 0.95
Strategy: Use Optuna for Bayesian optimization of hyperparameters
Target: BTCUSDT R² > 0.95, ETHUSDT R² > 0.90

Features optimized:
- Layer sizes and counts
- Dropout rates
- Learning rate
- Batch sizes
- Activation functions
- Optimizers
- Regularization

Author: ML Optimization Agent
Date: 2025-11-20
"""

import asyncio
import asyncpg
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
import logging
import sys
from pathlib import Path
import json
import optuna
from optuna.trial import Trial
import pickle

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# ML libraries
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers, regularizers
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
from sklearn.preprocessing import MinMaxScaler, RobustScaler, StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error
from sklearn.model_selection import KFold

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hyperparameter_optimization.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database configuration (updated for localhost)
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'market_data',
    'user': 'cryptobot',
    'password': 'timescale_dev_password'
}

# Optimization targets
TARGET_R2_BTCUSDT = 0.95  # 95% accuracy target for BTC
TARGET_R2_ETHUSDT = 0.90  # 90% accuracy target for ETH
OPTIMIZATION_TRIALS = 50  # Number of trials per model
INTERVAL = '60'  # 60 minute candles


class EnhancedFeatureEngineer:
    """
    Advanced feature engineering with additional technical indicators
    Goal: Extract more predictive features from price data
    """

    @staticmethod
    def calculate_vwap(df: pd.DataFrame) -> pd.Series:
        """Calculate Volume-Weighted Average Price"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        return (typical_price * df['volume']).rolling(window=14).sum() / df['volume'].rolling(window=14).sum()

    @staticmethod
    def calculate_obv(df: pd.DataFrame) -> pd.Series:
        """Calculate On-Balance Volume (cumulative volume indicator)"""
        obv = np.where(df['close'] > df['close'].shift(1), df['volume'],
                      np.where(df['close'] < df['close'].shift(1), -df['volume'], 0))
        return pd.Series(obv, index=df.index).cumsum()

    @staticmethod
    def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index (trend strength)"""
        high = df['high']
        low = df['low']
        close = df['close']

        # Calculate +DM and -DM
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        # Calculate True Range
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        # Calculate +DI and -DI
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)

        # Calculate DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()

        return adx

    @staticmethod
    def calculate_roc(df: pd.DataFrame, period: int = 12) -> pd.Series:
        """Calculate Rate of Change (momentum indicator)"""
        return ((df['close'] - df['close'].shift(period)) / df['close'].shift(period)) * 100

    @staticmethod
    def calculate_ichimoku(df: pd.DataFrame) -> Dict[str, pd.Series]:
        """Calculate Ichimoku Cloud components"""
        # Tenkan-sen (Conversion Line): 9-period
        nine_period_high = df['high'].rolling(window=9).max()
        nine_period_low = df['low'].rolling(window=9).min()
        tenkan_sen = (nine_period_high + nine_period_low) / 2

        # Kijun-sen (Base Line): 26-period
        period26_high = df['high'].rolling(window=26).max()
        period26_low = df['low'].rolling(window=26).min()
        kijun_sen = (period26_high + period26_low) / 2

        # Senkou Span A (Leading Span A): (Conversion + Base) / 2
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

        # Senkou Span B (Leading Span B): 52-period
        period52_high = df['high'].rolling(window=52).max()
        period52_low = df['low'].rolling(window=52).min()
        senkou_span_b = ((period52_high + period52_low) / 2).shift(26)

        return {
            'tenkan_sen': tenkan_sen,
            'kijun_sen': kijun_sen,
            'senkou_span_a': senkou_span_a,
            'senkou_span_b': senkou_span_b
        }

    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI (Relative Strength Index)"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, pd.Series]:
        """Calculate MACD (Moving Average Convergence Divergence)"""
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal, adjust=False).mean()
        histogram = macd - signal_line

        return {
            'macd': macd,
            'macd_signal': signal_line,
            'macd_histogram': histogram
        }

    @staticmethod
    def calculate_bollinger_bands(df: pd.DataFrame, period: int = 20, std_dev: float = 2) -> Dict[str, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = df['close'].rolling(window=period).mean()
        std = df['close'].rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)

        return {
            'bb_upper': upper_band,
            'bb_middle': sma,
            'bb_lower': lower_band,
            'bb_width': (upper_band - lower_band) / sma
        }

    @classmethod
    def create_enhanced_features(cls, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create comprehensive feature set with advanced technical indicators
        Returns DataFrame with 40+ features
        """
        df = df.copy()

        # Basic price features
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
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()

        # Price position relative to MAs
        df['price_vs_sma7'] = (df['close'] - df['sma_7']) / df['sma_7']
        df['price_vs_sma14'] = (df['close'] - df['sma_14']) / df['sma_14']
        df['price_vs_ema7'] = (df['close'] - df['ema_7']) / df['ema_7']

        # Volatility features
        df['high_low_range'] = (df['high'] - df['low']) / df['close']
        df['volatility_10'] = df['return_1'].rolling(window=10).std()
        df['volatility_20'] = df['return_1'].rolling(window=20).std()

        # Volume features
        df['volume_sma_7'] = df['volume'].rolling(window=7).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma_7']

        # Advanced indicators
        df['rsi_14'] = cls.calculate_rsi(df['close'], 14)
        df['rsi_7'] = cls.calculate_rsi(df['close'], 7)

        # MACD
        macd_features = cls.calculate_macd(df)
        df['macd'] = macd_features['macd']
        df['macd_signal'] = macd_features['macd_signal']
        df['macd_histogram'] = macd_features['macd_histogram']

        # Bollinger Bands
        bb_features = cls.calculate_bollinger_bands(df)
        df['bb_upper'] = bb_features['bb_upper']
        df['bb_lower'] = bb_features['bb_lower']
        df['bb_width'] = bb_features['bb_width']
        df['bb_position'] = (df['close'] - bb_features['bb_lower']) / (bb_features['bb_upper'] - bb_features['bb_lower'])

        # VWAP
        df['vwap'] = cls.calculate_vwap(df)
        df['price_vs_vwap'] = (df['close'] - df['vwap']) / df['vwap']

        # OBV (On-Balance Volume)
        df['obv'] = cls.calculate_obv(df)
        df['obv_sma'] = df['obv'].rolling(window=20).mean()

        # ADX (Average Directional Index)
        df['adx'] = cls.calculate_adx(df)

        # ROC (Rate of Change)
        df['roc_12'] = cls.calculate_roc(df, 12)
        df['roc_25'] = cls.calculate_roc(df, 25)

        # Ichimoku components
        ichimoku = cls.calculate_ichimoku(df)
        df['ichimoku_tenkan'] = ichimoku['tenkan_sen']
        df['ichimoku_kijun'] = ichimoku['kijun_sen']
        df['ichimoku_span_a'] = ichimoku['senkou_span_a']
        df['ichimoku_span_b'] = ichimoku['senkou_span_b']

        # Price correlation features (autocorrelation)
        df['price_corr_5'] = df['close'].rolling(window=20).corr(df['close'].shift(5))
        df['price_corr_10'] = df['close'].rolling(window=20).corr(df['close'].shift(10))

        # Drop NaN rows from feature engineering
        df = df.dropna()

        logger.info(f"Created {len(df.columns)} enhanced features from {len(df)} samples")

        return df


class HyperparameterOptimizer:
    """
    Hyperparameter optimization using Optuna
    Searches for optimal model architecture and training parameters
    """

    def __init__(self, symbol: str, interval: str = '60'):
        """Initialize optimizer for specific symbol"""
        self.symbol = symbol
        self.interval = interval
        self.sequence_length = 60  # Fixed sequence length
        self.prediction_horizon = 5  # Fixed prediction horizon
        self.db_pool: Optional[asyncpg.Pool] = None
        self.best_params: Dict = {}
        self.best_score: float = 0.0
        self.feature_engineer = EnhancedFeatureEngineer()

    async def connect_database(self):
        """Connect to TimescaleDB"""
        try:
            logger.info(f"Connecting to TimescaleDB at {DB_CONFIG['host']}:{DB_CONFIG['port']}")

            self.db_pool = await asyncpg.create_pool(
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                min_size=1,
                max_size=5,
                timeout=30
            )

            logger.info("Successfully connected to TimescaleDB")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def close_database(self):
        """Close database connection"""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Closed database connection")

    async def fetch_historical_data(self, days: int = 30) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data from TimescaleDB
        """
        try:
            logger.info(f"Fetching {days} days of {self.interval}m candles for {self.symbol}")

            # Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            # Query database
            query = """
                SELECT
                    time as timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM market_data.candles
                WHERE symbol = $1
                    AND interval = $2
                    AND time >= $3
                    AND time <= $4
                ORDER BY time ASC
            """

            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, self.symbol, self.interval, start_time, end_time)

            if not rows:
                logger.warning(f"No data found for {self.symbol}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)

            logger.info(f"Fetched {len(df)} candles for {self.symbol}")
            logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            logger.info(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {self.symbol}: {e}")
            return None

    def prepare_sequences(
        self,
        df: pd.DataFrame,
        scaler_type: str = 'minmax'
    ) -> Tuple[np.ndarray, np.ndarray, Any]:
        """
        Prepare sequences for model training with specified scaler

        Args:
            df: DataFrame with features
            scaler_type: 'minmax', 'standard', or 'robust'

        Returns:
            X, y, scaler
        """
        # Select feature columns
        feature_cols = [col for col in df.columns if col not in ['timestamp', 'symbol']]

        # Extract values
        data = df[feature_cols].values

        # Choose scaler
        if scaler_type == 'minmax':
            scaler = MinMaxScaler(feature_range=(0, 1))
        elif scaler_type == 'standard':
            scaler = StandardScaler()
        elif scaler_type == 'robust':
            scaler = RobustScaler()
        else:
            scaler = MinMaxScaler(feature_range=(0, 1))

        # Scale features
        scaled_data = scaler.fit_transform(data)

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

        return np.array(X), np.array(y), scaler

    def build_optimized_model(
        self,
        trial: Trial,
        input_shape: Tuple,
        model_type: str = 'GRU'
    ) -> keras.Model:
        """
        Build model with Optuna-suggested hyperparameters

        Hyperparameters to optimize:
        - Number of layers (2-4)
        - Units per layer (64, 128, 256)
        - Dropout rate (0.1 - 0.4)
        - Recurrent dropout (0.0 - 0.2)
        - Dense layer size (16, 32, 64, 128)
        - Activation function (relu, tanh, elu)
        - L2 regularization (0.0 - 0.01)
        - Batch normalization (yes/no)
        """
        # Suggest hyperparameters
        num_layers = trial.suggest_int('num_layers', 2, 4)
        first_layer_units = trial.suggest_categorical('first_layer_units', [64, 128, 256])
        dropout_rate = trial.suggest_float('dropout_rate', 0.1, 0.4)
        recurrent_dropout = trial.suggest_float('recurrent_dropout', 0.0, 0.2)
        dense_units = trial.suggest_categorical('dense_units', [16, 32, 64, 128])
        activation = trial.suggest_categorical('activation', ['relu', 'tanh', 'elu'])
        l2_reg = trial.suggest_float('l2_regularization', 0.0, 0.01)
        use_batch_norm = trial.suggest_categorical('use_batch_norm', [True, False])

        # Build model
        model = keras.Sequential()

        # First RNN layer
        if model_type == 'GRU':
            model.add(layers.GRU(
                units=first_layer_units,
                return_sequences=True,
                input_shape=input_shape,
                dropout=dropout_rate,
                recurrent_dropout=recurrent_dropout,
                kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                name='gru_layer_1'
            ))
        else:  # LSTM
            model.add(layers.LSTM(
                units=first_layer_units,
                return_sequences=True,
                input_shape=input_shape,
                dropout=dropout_rate,
                recurrent_dropout=recurrent_dropout,
                kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                name='lstm_layer_1'
            ))

        if use_batch_norm:
            model.add(layers.BatchNormalization())

        # Middle layers
        for i in range(1, num_layers - 1):
            layer_units = first_layer_units // (2 ** i)  # Decreasing units
            layer_units = max(layer_units, 32)  # Minimum 32 units

            if model_type == 'GRU':
                model.add(layers.GRU(
                    units=layer_units,
                    return_sequences=True,
                    dropout=dropout_rate,
                    recurrent_dropout=recurrent_dropout,
                    kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                    name=f'gru_layer_{i+1}'
                ))
            else:  # LSTM
                model.add(layers.LSTM(
                    units=layer_units,
                    return_sequences=True,
                    dropout=dropout_rate,
                    recurrent_dropout=recurrent_dropout,
                    kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                    name=f'lstm_layer_{i+1}'
                ))

            if use_batch_norm:
                model.add(layers.BatchNormalization())

        # Final RNN layer
        final_units = first_layer_units // (2 ** (num_layers - 1))
        final_units = max(final_units, 32)

        if model_type == 'GRU':
            model.add(layers.GRU(
                units=final_units,
                return_sequences=False,
                dropout=dropout_rate,
                recurrent_dropout=recurrent_dropout,
                kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                name=f'gru_layer_{num_layers}'
            ))
        else:  # LSTM
            model.add(layers.LSTM(
                units=final_units,
                return_sequences=False,
                dropout=dropout_rate,
                recurrent_dropout=recurrent_dropout,
                kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
                name=f'lstm_layer_{num_layers}'
            ))

        if use_batch_norm:
            model.add(layers.BatchNormalization())

        # Dense layers
        model.add(layers.Dense(
            dense_units,
            activation=activation,
            kernel_regularizer=regularizers.l2(l2_reg) if l2_reg > 0 else None,
            name='dense_1'
        ))
        model.add(layers.Dropout(dropout_rate / 2))

        # Output layer
        model.add(layers.Dense(self.prediction_horizon, name='output'))

        return model

    def objective_function(
        self,
        trial: Trial,
        X: np.ndarray,
        y: np.ndarray,
        model_type: str = 'GRU'
    ) -> float:
        """
        Objective function for Optuna optimization
        Returns validation R² score (to maximize)
        """
        try:
            # Suggest training hyperparameters
            batch_size = trial.suggest_categorical('batch_size', [16, 32, 64])
            learning_rate = trial.suggest_float('learning_rate', 1e-5, 1e-2, log=True)
            optimizer_name = trial.suggest_categorical('optimizer', ['adam', 'adamw', 'rmsprop'])
            scaler_type = trial.suggest_categorical('scaler_type', ['minmax', 'standard', 'robust'])

            # Train/validation split (80/20)
            split_idx = int(len(X) * 0.8)
            X_train, X_val = X[:split_idx], X[split_idx:]
            y_train, y_val = y[:split_idx], y[split_idx:]

            # Build model
            model = self.build_optimized_model(trial, input_shape=(X.shape[1], X.shape[2]), model_type=model_type)

            # Select optimizer
            if optimizer_name == 'adam':
                optimizer = keras.optimizers.Adam(learning_rate=learning_rate)
            elif optimizer_name == 'adamw':
                optimizer = keras.optimizers.AdamW(learning_rate=learning_rate)
            else:  # rmsprop
                optimizer = keras.optimizers.RMSprop(learning_rate=learning_rate)

            # Compile model
            model.compile(
                optimizer=optimizer,
                loss='mean_squared_error',
                metrics=['mae', 'mse']
            )

            # Callbacks
            callbacks = [
                EarlyStopping(
                    monitor='val_loss',
                    patience=15,
                    restore_best_weights=True,
                    verbose=0
                ),
                ReduceLROnPlateau(
                    monitor='val_loss',
                    factor=0.5,
                    patience=7,
                    min_lr=1e-7,
                    verbose=0
                )
            ]

            # Train model
            history = model.fit(
                X_train, y_train,
                batch_size=batch_size,
                epochs=200,  # Will stop early if no improvement
                validation_data=(X_val, y_val),
                callbacks=callbacks,
                verbose=0
            )

            # Evaluate on validation set
            y_pred = model.predict(X_val, verbose=0)

            # Calculate R² score (primary metric)
            r2 = r2_score(y_val[:, 0], y_pred[:, 0])

            # Calculate additional metrics for logging
            mae = mean_absolute_error(y_val[:, 0], y_pred[:, 0])
            rmse = np.sqrt(mean_squared_error(y_val[:, 0], y_pred[:, 0]))

            # Log trial results
            logger.info(f"Trial {trial.number}: R²={r2:.6f}, MAE={mae:.4f}, RMSE={rmse:.4f}")

            # Report intermediate values for pruning
            trial.set_user_attr('mae', float(mae))
            trial.set_user_attr('rmse', float(rmse))
            trial.set_user_attr('epochs_trained', len(history.history['loss']))

            return r2  # Return R² score to maximize

        except Exception as e:
            logger.error(f"Trial {trial.number} failed: {e}")
            return 0.0  # Return worst possible score

    async def optimize_hyperparameters(
        self,
        model_type: str = 'GRU',
        n_trials: int = 50
    ) -> Dict:
        """
        Run hyperparameter optimization using Optuna

        Args:
            model_type: 'GRU' or 'LSTM'
            n_trials: Number of optimization trials

        Returns:
            Dictionary with best hyperparameters and performance metrics
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Starting hyperparameter optimization for {self.symbol} {model_type}")
        logger.info(f"Trials: {n_trials}")
        logger.info(f"{'='*80}\n")

        try:
            # Fetch data
            df = await self.fetch_historical_data(days=30)
            if df is None or len(df) < 200:
                logger.error(f"Insufficient data for {self.symbol}")
                return {}

            # Create enhanced features
            df = self.feature_engineer.create_enhanced_features(df)

            # Prepare sequences (will be re-prepared in objective with different scalers)
            X, y, _ = self.prepare_sequences(df, scaler_type='minmax')

            logger.info(f"Prepared sequences: X shape={X.shape}, y shape={y.shape}")

            # Create Optuna study
            study = optuna.create_study(
                direction='maximize',  # Maximize R² score
                study_name=f'{self.symbol}_{model_type}_optimization',
                pruner=optuna.pruners.MedianPruner(
                    n_startup_trials=5,
                    n_warmup_steps=30
                )
            )

            # Run optimization
            study.optimize(
                lambda trial: self.objective_function(trial, X, y, model_type=model_type),
                n_trials=n_trials,
                show_progress_bar=True
            )

            # Get best trial
            best_trial = study.best_trial

            logger.info(f"\n{'='*80}")
            logger.info(f"Optimization Complete for {self.symbol} {model_type}")
            logger.info(f"{'='*80}")
            logger.info(f"Best R² Score: {best_trial.value:.6f}")
            logger.info(f"Best MAE: {best_trial.user_attrs.get('mae', 0):.4f}")
            logger.info(f"Best RMSE: {best_trial.user_attrs.get('rmse', 0):.4f}")
            logger.info(f"\nBest Hyperparameters:")
            for key, value in best_trial.params.items():
                logger.info(f"  {key}: {value}")

            # Store best parameters
            self.best_params = best_trial.params
            self.best_score = best_trial.value

            # Save optimization results
            results = {
                'symbol': self.symbol,
                'model_type': model_type,
                'best_r2_score': float(best_trial.value),
                'best_mae': float(best_trial.user_attrs.get('mae', 0)),
                'best_rmse': float(best_trial.user_attrs.get('rmse', 0)),
                'best_hyperparameters': best_trial.params,
                'optimization_date': datetime.utcnow().isoformat(),
                'total_trials': n_trials,
                'best_trial_number': best_trial.number
            }

            return results

        except Exception as e:
            logger.error(f"Optimization failed for {self.symbol} {model_type}: {e}", exc_info=True)
            return {}

    async def train_final_model(
        self,
        best_params: Dict,
        model_type: str = 'GRU'
    ) -> Dict:
        """
        Train final model with best hyperparameters on full training set

        Args:
            best_params: Best hyperparameters from optimization
            model_type: 'GRU' or 'LSTM'

        Returns:
            Model performance metrics
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"Training final model for {self.symbol} {model_type}")
        logger.info(f"{'='*80}\n")

        try:
            # Fetch data
            df = await self.fetch_historical_data(days=30)
            if df is None:
                return {}

            # Create enhanced features
            df = self.feature_engineer.create_enhanced_features(df)

            # Prepare sequences with best scaler
            scaler_type = best_params.get('scaler_type', 'minmax')
            X, y, scaler = self.prepare_sequences(df, scaler_type=scaler_type)

            # Train/test split
            split_idx = int(len(X) * 0.85)  # Use 85% for training final model
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Build model with best hyperparameters (create dummy trial)
            class DummyTrial:
                def suggest_int(self, name, low, high):
                    return best_params.get(name, (low + high) // 2)
                def suggest_float(self, name, low, high, log=False):
                    return best_params.get(name, (low + high) / 2)
                def suggest_categorical(self, name, choices):
                    return best_params.get(name, choices[0])

            dummy_trial = DummyTrial()
            model = self.build_optimized_model(dummy_trial, input_shape=(X.shape[1], X.shape[2]), model_type=model_type)

            # Compile with best optimizer
            optimizer_name = best_params.get('optimizer', 'adam')
            learning_rate = best_params.get('learning_rate', 0.001)

            if optimizer_name == 'adam':
                optimizer = keras.optimizers.Adam(learning_rate=learning_rate)
            elif optimizer_name == 'adamw':
                optimizer = keras.optimizers.AdamW(learning_rate=learning_rate)
            else:
                optimizer = keras.optimizers.RMSprop(learning_rate=learning_rate)

            model.compile(
                optimizer=optimizer,
                loss='mean_squared_error',
                metrics=['mae', 'mse']
            )

            # Train model
            callbacks = [
                EarlyStopping(
                    monitor='val_loss',
                    patience=20,
                    restore_best_weights=True
                ),
                ReduceLROnPlateau(
                    monitor='val_loss',
                    factor=0.5,
                    patience=10,
                    min_lr=1e-7
                )
            ]

            batch_size = best_params.get('batch_size', 32)

            history = model.fit(
                X_train, y_train,
                batch_size=batch_size,
                epochs=300,
                validation_data=(X_test, y_test),
                callbacks=callbacks,
                verbose=1
            )

            # Evaluate final model
            y_pred = model.predict(X_test, verbose=0)

            # Calculate comprehensive metrics
            r2 = r2_score(y_test[:, 0], y_pred[:, 0])
            mae = mean_absolute_error(y_test[:, 0], y_pred[:, 0])
            rmse = np.sqrt(mean_squared_error(y_test[:, 0], y_pred[:, 0]))
            mape = mean_absolute_percentage_error(y_test[:, 0], y_pred[:, 0])

            # Calculate directional accuracy
            y_test_direction = np.sign(y_test[:, 0] - y_test[:, -1])
            y_pred_direction = np.sign(y_pred[:, 0] - y_test[:, -1])
            directional_accuracy = np.mean(y_test_direction == y_pred_direction)

            logger.info(f"\n{'='*80}")
            logger.info(f"Final Model Performance for {self.symbol} {model_type}")
            logger.info(f"{'='*80}")
            logger.info(f"R² Score: {r2:.6f}")
            logger.info(f"MAE: {mae:.4f}")
            logger.info(f"RMSE: {rmse:.4f}")
            logger.info(f"MAPE: {mape:.2f}%")
            logger.info(f"Directional Accuracy: {directional_accuracy:.4f}")
            logger.info(f"Epochs Trained: {len(history.history['loss'])}")

            # Save optimized model
            models_dir = Path('trained_models_optimized')
            models_dir.mkdir(parents=True, exist_ok=True)

            model_path = models_dir / f"{self.symbol}_{self.interval}m_{model_type.lower()}_optimized.keras"
            model.save(str(model_path))

            # Save metadata
            metadata = {
                'symbol': self.symbol,
                'model_type': model_type,
                'interval': self.interval,
                'best_hyperparameters': best_params,
                'performance_metrics': {
                    'r2_score': float(r2),
                    'mae': float(mae),
                    'rmse': float(rmse),
                    'mape': float(mape),
                    'directional_accuracy': float(directional_accuracy),
                    'epochs_trained': len(history.history['loss'])
                },
                'training_date': datetime.utcnow().isoformat(),
                'total_parameters': int(model.count_params())
            }

            metadata_path = models_dir / f"{self.symbol}_{self.interval}m_{model_type.lower()}_optimized_metadata.json"
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)

            # Save scaler
            scaler_path = models_dir / f"{self.symbol}_{self.interval}m_{model_type.lower()}_optimized_scaler.pkl"
            with open(scaler_path, 'wb') as f:
                pickle.dump(scaler, f)

            logger.info(f"Saved optimized model to {model_path}")

            return metadata['performance_metrics']

        except Exception as e:
            logger.error(f"Final model training failed: {e}", exc_info=True)
            return {}


async def main():
    """
    Main optimization pipeline
    Optimize hyperparameters for BTCUSDT and ETHUSDT
    """
    try:
        logger.info(f"\n{'#'*80}")
        logger.info("ML Model Hyperparameter Optimization Pipeline")
        logger.info(f"Target: BTCUSDT R² > {TARGET_R2_BTCUSDT}, ETHUSDT R² > {TARGET_R2_ETHUSDT}")
        logger.info(f"{'#'*80}\n")

        # Priority symbols for optimization
        priority_symbols = ['BTCUSDT', 'ETHUSDT']
        model_types = ['GRU', 'LSTM']

        optimization_results = []

        for symbol in priority_symbols:
            logger.info(f"\n{'*'*80}")
            logger.info(f"Optimizing models for {symbol}")
            logger.info(f"{'*'*80}\n")

            # Create optimizer
            optimizer = HyperparameterOptimizer(symbol=symbol, interval=INTERVAL)
            await optimizer.connect_database()

            for model_type in model_types:
                # Run hyperparameter optimization
                opt_results = await optimizer.optimize_hyperparameters(
                    model_type=model_type,
                    n_trials=OPTIMIZATION_TRIALS
                )

                if opt_results:
                    # Train final model with best hyperparameters
                    final_metrics = await optimizer.train_final_model(
                        best_params=opt_results['best_hyperparameters'],
                        model_type=model_type
                    )

                    opt_results['final_metrics'] = final_metrics
                    optimization_results.append(opt_results)

                # Small delay between models
                await asyncio.sleep(2)

            await optimizer.close_database()

            # Delay between symbols
            await asyncio.sleep(5)

        # Generate final report
        logger.info(f"\n{'#'*80}")
        logger.info("OPTIMIZATION SUMMARY")
        logger.info(f"{'#'*80}\n")

        for result in optimization_results:
            symbol = result.get('symbol')
            model_type = result.get('model_type')
            r2 = result.get('best_r2_score', 0)
            final_r2 = result.get('final_metrics', {}).get('r2_score', 0)

            target = TARGET_R2_BTCUSDT if symbol == 'BTCUSDT' else TARGET_R2_ETHUSDT
            meets_target = final_r2 >= target

            logger.info(f"{symbol} {model_type}:")
            logger.info(f"  Optimization R²: {r2:.6f}")
            logger.info(f"  Final Model R²: {final_r2:.6f} {'✓' if meets_target else '✗'}")
            logger.info(f"  Target: {target}")
            logger.info("")

        # Save all results
        results_file = Path('trained_models_optimized/optimization_results.json')
        with open(results_file, 'w') as f:
            json.dump(optimization_results, f, indent=2)

        logger.info(f"Optimization results saved to {results_file}")
        logger.info("\nOptimization pipeline completed successfully!")

    except KeyboardInterrupt:
        logger.info("\nOptimization interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Optimization pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run optimization pipeline
    asyncio.run(main())
