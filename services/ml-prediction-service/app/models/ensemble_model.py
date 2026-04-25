"""
Ensemble ML Model for Enhanced Trading Predictions
Target: 5-10% improvement in win rate through better signal quality
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from tensorflow.keras.optimizers import Adam
import joblib
import logging
from typing import Dict, List, Tuple, Optional
import pickle
import os

logger = logging.getLogger(__name__)

class EnsemblePredictor:
    """
    Ensemble model combining multiple ML approaches for improved prediction accuracy
    Target: 5-10% improvement in win rate through better signal quality
    """
    
    def __init__(self):
        self.models = {
            'lstm': None,
            'random_forest': None,
            'gradient_boosting': None,
            'logistic_regression': None
        }
        self.scaler = StandardScaler()
        self.feature_names = []
        self.is_trained = False
        self.model_dir = "models"
        
        # Create models directory if it doesn't exist
        os.makedirs(self.model_dir, exist_ok=True)
        
    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Prepare comprehensive features for ML models
        Enhanced features to improve prediction accuracy
        """
        features_df = df.copy()
        
        # Technical indicators
        features_df['rsi'] = self._calculate_rsi(df['close'])
        features_df['macd'], features_df['macd_signal'] = self._calculate_macd(df['close'])
        features_df['bb_upper'], features_df['bb_middle'], features_df['bb_lower'] = self._calculate_bollinger_bands(df['close'])
        features_df['atr'] = self._calculate_atr(df)
        features_df['adx'] = self._calculate_adx(df)
        
        # Price-based features
        features_df['price_change_pct'] = df['close'].pct_change()
        features_df['high_low_pct'] = (df['high'] - df['low']) / df['close']
        features_df['volume_change_pct'] = df['volume'].pct_change()
        features_df['volatility'] = df['close'].rolling(20).std() / df['close'].rolling(20).mean()
        
        # Momentum features
        features_df['roc_10'] = df['close'].pct_change(10)  # Rate of change
        features_df['roc_20'] = df['close'].pct_change(20)
        features_df['momentum'] = df['close'] - df['close'].shift(10)
        
        # Volume-weighted features
        features_df['vwma'] = self._calculate_vwma(df)
        features_df['volume_sma_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        
        # Trend features
        features_df['ema_fast'] = df['close'].ewm(span=12).mean()
        features_df['ema_slow'] = df['close'].ewm(span=26).mean()
        features_df['trend_strength'] = abs(features_df['ema_fast'] - features_df['ema_slow']) / df['close']
        
        # Lagged features for temporal patterns
        for lag in [1, 2, 3, 5, 10]:
            features_df[f'close_lag_{lag}'] = df['close'].shift(lag)
            features_df[f'volume_lag_{lag}'] = df['volume'].shift(lag)
            features_df[f'volatility_lag_{lag}'] = features_df['volatility'].shift(lag)
        
        # Rolling statistics
        for window in [5, 10, 20]:
            features_df[f'close_ma_{window}'] = df['close'].rolling(window).mean()
            features_df[f'volume_ma_{window}'] = df['volume'].rolling(window).mean()
            features_df[f'volatility_ma_{window}'] = features_df['volatility'].rolling(window).mean()
            features_df[f'price_position_{window}'] = (df['close'] - df['close'].rolling(window).min()) / \
                                                    (df['close'].rolling(window).max() - df['close'].rolling(window).min())
        
        # Target variable: future price direction
        features_df['future_direction'] = (df['close'].shift(-1) > df['close']).astype(int)
        
        # Drop rows with NaN values
        features_df = features_df.dropna()
        
        # Store feature names for later use
        self.feature_names = [col for col in features_df.columns if col not in ['future_direction']]
        
        return features_df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Relative Strength Index"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series]:
        """Calculate MACD and Signal line"""
        exp1 = prices.ewm(span=fast).mean()
        exp2 = prices.ewm(span=slow).mean()
        macd = exp1 - exp2
        signal_line = macd.ewm(span=signal).mean()
        return macd, signal_line
    
    def _calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Calculate Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        return upper_band, sma, lower_band
    
    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = np.maximum(high_low, np.maximum(high_close, low_close))
        atr = true_range.rolling(window=period).mean()
        return atr
    
    def _calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average Directional Index"""
        # Calculate True Range
        tr = self._calculate_atr(df, 1)
        
        # Calculate Directional Movement
        up_move = df['high'].diff()
        down_move = -df['low'].diff()
        
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)
        
        # Smoothed DM
        plus_di = 100 * (plus_dm.rolling(period).sum() / tr.rolling(period).sum())
        minus_di = 100 * (minus_dm.rolling(period).sum() / tr.rolling(period).sum())
        
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(period).mean()
        
        return adx
    
    def _calculate_vwma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Calculate Volume Weighted Moving Average"""
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        return (typical_price * df['volume']).rolling(period).sum() / df['volume'].rolling(period).sum()
    
    def train_models(self, df: pd.DataFrame, test_size: float = 0.2) -> Dict[str, float]:
        """
        Train all ensemble models and return performance metrics
        Focus on improving win rate through better prediction accuracy
        """
        # Prepare features
        features_df = self.prepare_features(df)
        
        if len(features_df) < 100:  # Need sufficient data
            raise ValueError("Insufficient data for training")
        
        # Separate features and target
        X = features_df[self.feature_names]
        y = features_df['future_direction']
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y
        )
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        X_test_scaled = self.scaler.transform(X_test)
        
        # Train models
        results = {}
        
        # LSTM Model
        try:
            lstm_model = self._train_lstm(X_train_scaled, y_train, X_test_scaled, y_test)
            self.models['lstm'] = lstm_model
            results['lstm'] = self._evaluate_model(lstm_model, X_test_scaled, y_test, model_type='lstm')
        except Exception as e:
            logger.error(f"LSTM training failed: {e}")
            results['lstm'] = {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
        
        # Random Forest
        try:
            rf_model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=-1)
            rf_model.fit(X_train_scaled, y_train)
            self.models['random_forest'] = rf_model
            results['random_forest'] = self._evaluate_model(rf_model, X_test_scaled, y_test)
        except Exception as e:
            logger.error(f"Random Forest training failed: {e}")
            results['random_forest'] = {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
        
        # Gradient Boosting
        try:
            gb_model = GradientBoostingClassifier(random_state=42)
            gb_model.fit(X_train_scaled, y_train)
            self.models['gradient_boosting'] = gb_model
            results['gradient_boosting'] = self._evaluate_model(gb_model, X_test_scaled, y_test)
        except Exception as e:
            logger.error(f"Gradient Boosting training failed: {e}")
            results['gradient_boosting'] = {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
        
        # Logistic Regression
        try:
            lr_model = LogisticRegression(random_state=42, max_iter=1000)
            lr_model.fit(X_train_scaled, y_train)
            self.models['logistic_regression'] = lr_model
            results['logistic_regression'] = self._evaluate_model(lr_model, X_test_scaled, y_test)
        except Exception as e:
            logger.error(f"Logistic Regression training failed: {e}")
            results['logistic_regression'] = {'accuracy': 0.0, 'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
        
        self.is_trained = True
        
        # Calculate ensemble performance
        ensemble_pred = self._predict_ensemble(X_test_scaled)
        ensemble_metrics = self._evaluate_model(None, X_test_scaled, y_test, ensemble_pred=ensemble_pred)
        results['ensemble'] = ensemble_metrics
        
        # Save the trained models
        self.save_model(os.path.join(self.model_dir, "ensemble_model.pkl"))
        
        return results
    
    def _train_lstm(self, X_train: np.ndarray, y_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray) -> Sequential:
        """Train LSTM model"""
        # Reshape for LSTM: (samples, timesteps, features)
        X_train_lstm = X_train.reshape((X_train.shape[0], 1, X_train.shape[1]))
        X_test_lstm = X_test.reshape((X_test.shape[0], 1, X_test.shape[2]))
        
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=(X_train_lstm.shape[1], X_train_lstm.shape[2])),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25, activation='relu'),
            Dense(1, activation='sigmoid')
        ])
        
        model.compile(optimizer=Adam(learning_rate=0.001), loss='binary_crossentropy', metrics=['accuracy'])
        
        # Early stopping to prevent overfitting
        from tensorflow.keras.callbacks import EarlyStopping
        early_stop = EarlyStopping(monitor='val_loss', patience=10, restore_best_weights=True)
        
        model.fit(
            X_train_lstm, y_train,
            epochs=100,
            batch_size=32,
            validation_data=(X_test_lstm, y_test),
            callbacks=[early_stop],
            verbose=0
        )
        
        return model
    
    def _evaluate_model(self, model, X_test: np.ndarray, y_test: np.ndarray, model_type: str = 'traditional', ensemble_pred: np.ndarray = None) -> Dict[str, float]:
        """Evaluate model performance"""
        if ensemble_pred is not None:
            y_pred = ensemble_pred
        else:
            if model_type == 'lstm':
                X_test_lstm = X_test.reshape((X_test.shape[0], 1, X_test.shape[2]))
                y_pred_proba = model.predict(X_test_lstm)
                y_pred = (y_pred_proba > 0.5).astype(int).flatten()
            else:
                y_pred_proba = model.predict_proba(X_test)[:, 1]
                y_pred = (y_pred_proba > 0.5).astype(int)
        
        return {
            'accuracy': accuracy_score(y_test, y_pred),
            'precision': precision_score(y_test, y_pred, zero_division=0),
            'recall': recall_score(y_test, y_pred, zero_division=0),
            'f1': f1_score(y_test, y_pred, zero_division=0)
        }
    
    def _predict_ensemble(self, X: np.ndarray) -> np.ndarray:
        """Make ensemble prediction using all trained models"""
        predictions = []
        
        # LSTM prediction
        if self.models['lstm'] is not None:
            X_lstm = X.reshape((X.shape[0], 1, X.shape[1]))
            lstm_pred = self.models['lstm'].predict(X_lstm)
            predictions.append(lstm_pred.flatten())
        
        # Traditional model predictions
        for model_name in ['random_forest', 'gradient_boosting', 'logistic_regression']:
            if self.models[model_name] is not None:
                pred_proba = self.models[model_name].predict_proba(X)[:, 1]
                predictions.append(pred_proba)
        
        if not predictions:
            return np.zeros(len(X))
        
        # Average predictions
        ensemble_pred = np.mean(predictions, axis=0)
        return (ensemble_pred > 0.5).astype(int)
    
    def predict(self, df: pd.DataFrame) -> Dict[str, any]:
        """Make prediction for new data"""
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")
        
        # Prepare features
        features_df = self.prepare_features(df)
        X = features_df[self.feature_names]
        X_scaled = self.scaler.transform(X)
        
        # Get individual model predictions
        individual_predictions = {}
        
        # LSTM prediction
        if self.models['lstm'] is not None:
            X_lstm = X_scaled.reshape((X_scaled.shape[0], 1, X_scaled.shape[1]))
            lstm_pred = self.models['lstm'].predict(X_lstm)
            individual_predictions['lstm'] = {
                'prediction': (lstm_pred[-1][0] > 0.5).astype(int),
                'confidence': float(lstm_pred[-1][0])
            }
        
        # Traditional model predictions
        for model_name in ['random_forest', 'gradient_boosting', 'logistic_regression']:
            if self.models[model_name] is not None:
                pred_proba = self.models[model_name].predict_proba(X_scaled)[-1]
                individual_predictions[model_name] = {
                    'prediction': int(pred_proba[1] > 0.5),
                    'confidence': float(pred_proba[1])
                }
        
        # Ensemble prediction
        ensemble_pred = self._predict_ensemble(X_scaled)
        ensemble_confidence = np.mean([
            pred['confidence'] for pred in individual_predictions.values() if 'confidence' in pred
        ]) if individual_predictions else 0.5
        
        # Calculate consensus among models
        model_predictions = [pred['prediction'] for pred in individual_predictions.values()]
        consensus = sum(model_predictions) / len(model_predictions) if model_predictions else 0.5
        
        # Determine final signal based on consensus and confidence
        if consensus > 0.6:  # Majority predicts UP
            final_signal = 'BUY'
        elif consensus < 0.4:  # Majority predicts DOWN
            final_signal = 'SELL'
        else:
            final_signal = 'HOLD'
        
        return {
            'signal': final_signal,
            'consensus': consensus,
            'confidence': ensemble_confidence,
            'individual_predictions': individual_predictions,
            'model_accuracy': {model: pred['confidence'] for model, pred in individual_predictions.items()},
            'timestamp': pd.Timestamp.now().isoformat()
        }
    
    def save_model(self, filepath: str):
        """Save trained model"""
        model_data = {
            'models': self.models,
            'scaler': self.scaler,
            'feature_names': self.feature_names,
            'is_trained': self.is_trained
        }
        joblib.dump(model_data, filepath)
    
    def load_model(self, filepath: str):
        """Load trained model"""
        if os.path.exists(filepath):
            model_data = joblib.load(filepath)
            self.models = model_data['models']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            self.is_trained = model_data['is_trained']
            return True
        return False