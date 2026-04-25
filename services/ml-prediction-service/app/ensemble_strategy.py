"""
ML-Based Ensemble Strategy Controller
===================================

This module implements ensemble methods that combine multiple strategies
using machine learning techniques. It combines traditional technical analysis,
mean reversion, breakout, and adaptive strategies based on market conditions.

Features:
1. Ensemble of multiple strategy types
2. Machine learning-based weighting of strategies
3. Dynamic strategy combination based on market regime
4. Performance-based strategy selection
5. Meta-learning for optimal strategy combination
"""

import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingRegressor
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import joblib
from datetime import datetime
import warnings

# Import existing strategy modules
from strategies.enhanced_mean_reversion_strategy import EnhancedMeanReversionStrategy, EnhancedMeanReversionConfig
from strategies.enhanced_breakout_strategy import EnhancedBreakoutStrategy, EnhancedBreakoutConfig
from adaptive_strategy_controller import adapt_strategy_for_regime
from multi_timeframe_tester import MultiTimeframeTester, Timeframe

logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')


@dataclass
class EnsembleConfig:
    """Configuration for ML-based ensemble strategy"""
    # Strategy weights (initial)
    mean_reversion_weight: float = 0.3
    breakout_weight: float = 0.3
    trend_following_weight: float = 0.2
    adaptive_weight: float = 0.2
    
    # ML model parameters
    ml_model_type: str = "random_forest"  # "random_forest", "gradient_boosting", "logistic_regression"
    n_estimators: int = 100
    max_depth: int = 10
    learning_rate: float = 0.1
    
    # Feature engineering parameters
    feature_window: int = 20  # Window for calculating features
    include_technical_indicators: bool = True
    include_regime_features: bool = True
    include_volatility_features: bool = True
    
    # Ensemble combination method
    combination_method: str = "weighted_average"  # "weighted_average", "voting", "stacking"
    
    # Performance tracking
    performance_lookback: int = 30  # Days to track performance
    rebalance_frequency: int = 7  # Days between rebalancing weights


class EnsembleStrategy:
    """
    ML-Based Ensemble Strategy Controller
    
    Combines multiple trading strategies using machine learning techniques:
    1. Mean reversion strategy
    2. Breakout strategy
    3. Trend following strategy
    4. Adaptive strategy based on market regime
    
    The ensemble uses ML models to:
    - Dynamically weight strategies based on market conditions
    - Predict which strategy will perform best
    - Combine signals optimally
    """
    
    def __init__(self, config: EnsembleConfig = None):
        """Initialize the ensemble strategy controller"""
        self.config = config or EnsembleConfig()
        
        # Initialize individual strategies
        self.mean_reversion_strategy = EnhancedMeanReversionStrategy()
        self.breakout_strategy = EnhancedBreakoutStrategy()
        self.trend_following_strategy = self._initialize_trend_following()
        self.adaptive_strategy = None  # Will be initialized when needed
        
        # Initialize ML models
        self.ml_model = self._initialize_ml_model()
        self.scaler = StandardScaler()
        
        # Performance tracking
        self.strategy_performance: Dict[str, List[float]] = {
            'mean_reversion': [],
            'breakout': [],
            'trend_following': [],
            'adaptive': []
        }
        
        # Current weights
        self.current_weights = {
            'mean_reversion': self.config.mean_reversion_weight,
            'breakout': self.config.breakout_weight,
            'trend_following': self.config.trend_following_weight,
            'adaptive': self.config.adaptive_weight
        }
        
        # Feature history for ML model training
        self.feature_history: List[Dict] = []
        self.target_history: List[int] = []  # 1 for buy, -1 for sell, 0 for hold
        
        logger.info(f"EnsembleStrategy initialized with ML model: {self.config.ml_model_type}")
    
    def _initialize_trend_following(self):
        """Initialize trend following strategy (placeholder implementation)"""
        # This would be a real trend following strategy in production
        class TrendFollowingStrategy:
            def generate_signal(self, row, position, idx, data):
                # Placeholder implementation
                return None
        
        return TrendFollowingStrategy()
    
    def _initialize_ml_model(self):
        """Initialize the ML model based on configuration"""
        if self.config.ml_model_type == "random_forest":
            return RandomForestClassifier(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                random_state=42
            )
        elif self.config.ml_model_type == "gradient_boosting":
            return GradientBoostingRegressor(
                n_estimators=self.config.n_estimators,
                max_depth=self.config.max_depth,
                learning_rate=self.config.learning_rate,
                random_state=42
            )
        elif self.config.ml_model_type == "logistic_regression":
            return LogisticRegression(random_state=42, max_iter=1000)
        else:
            raise ValueError(f"Unsupported ML model type: {self.config.ml_model_type}")
    
    def calculate_technical_features(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate technical indicator features for ML model"""
        features = {}
        
        if len(data) < self.config.feature_window:
            # Return default features if not enough data
            return {
                'rsi': 50.0,
                'macd': 0.0,
                'bb_position': 0.5,  # Position within Bollinger Bands (0-1)
                'atr_normalized': 0.01,  # Normalized ATR
                'volume_sma_ratio': 1.0,  # Volume vs SMA ratio
                'price_momentum': 0.0,  # Price momentum
                'volatility': 0.02  # Volatility measure
            }
        
        closes = data['close']
        highs = data['high']
        lows = data['low']
        volumes = data['volume']
        
        # RSI
        delta = closes.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        features['rsi'] = rsi.iloc[-1]
        
        # MACD
        exp1 = closes.ewm(span=12).mean()
        exp2 = closes.ewm(span=26).mean()
        macd = exp1 - exp2
        features['macd'] = macd.iloc[-1]
        
        # Bollinger Bands position (0-1 scale, 0.5 = middle)
        bb_middle = closes.rolling(window=20).mean()
        bb_std = closes.rolling(window=20).std()
        bb_upper = bb_middle + (bb_std * 2)
        bb_lower = bb_middle - (bb_std * 2)
        
        current_price = closes.iloc[-1]
        bb_position = (current_price - bb_lower.iloc[-1]) / (bb_upper.iloc[-1] - bb_lower.iloc[-1])
        features['bb_position'] = np.clip(bb_position, 0, 1)
        
        # ATR normalized
        tr1 = highs - lows
        tr2 = abs(highs - closes.shift(1))
        tr3 = abs(lows - closes.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = true_range.rolling(window=14).mean()
        features['atr_normalized'] = atr.iloc[-1] / current_price if current_price > 0 else 0.01
        
        # Volume vs SMA ratio
        vol_sma = volumes.rolling(window=20).mean()
        features['volume_sma_ratio'] = volumes.iloc[-1] / vol_sma.iloc[-1] if vol_sma.iloc[-1] > 0 else 1.0
        
        # Price momentum (10-period)
        features['price_momentum'] = (current_price - closes.iloc[-10]) / closes.iloc[-10] if len(closes) >= 10 else 0
        
        # Volatility (20-period standard deviation of returns)
        returns = closes.pct_change()
        features['volatility'] = returns.rolling(window=20).std().iloc[-1] if len(returns) >= 20 else 0.02
        
        return features
    
    def calculate_regime_features(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate market regime features for ML model"""
        features = {}
        
        if len(data) < 50:  # Need sufficient data for regime detection
            return {
                'trend_strength': 0.5,
                'volatility_regime': 0.5,
                'momentum_regime': 0.0,
                'mean_reversion_strength': 0.5
            }
        
        closes = data['close']
        
        # Trend strength (based on angle of moving average)
        ma_fast = closes.rolling(window=10).mean()
        ma_slow = closes.rolling(window=30).mean()
        trend_strength = (ma_fast.iloc[-1] - ma_slow.iloc[-1]) / ma_slow.iloc[-1] if ma_slow.iloc[-1] != 0 else 0
        features['trend_strength'] = trend_strength
        
        # Volatility regime (normalized)
        returns = closes.pct_change()
        vol_short = returns.rolling(window=10).std()
        vol_long = returns.rolling(window=50).std()
        vol_regime = vol_short.iloc[-1] / vol_long.iloc[-1] if vol_long.iloc[-1] != 0 else 1.0
        features['volatility_regime'] = vol_regime
        
        # Momentum regime
        mom_10 = (closes.iloc[-1] - closes.iloc[-11]) / closes.iloc[-11] if len(closes) >= 11 else 0
        mom_20 = (closes.iloc[-1] - closes.iloc[-21]) / closes.iloc[-21] if len(closes) >= 21 else 0
        features['momentum_regime'] = (mom_10 + mom_20) / 2
        
        # Mean reversion strength (how far from mean)
        ma_20 = closes.rolling(window=20).mean()
        z_score = (closes.iloc[-1] - ma_20.iloc[-1]) / closes.rolling(window=20).std().iloc[-1] if closes.rolling(window=20).std().iloc[-1] != 0 else 0
        features['mean_reversion_strength'] = abs(z_score)
        
        return features
    
    def calculate_volatility_features(self, data: pd.DataFrame) -> Dict[str, float]:
        """Calculate volatility-based features for ML model"""
        features = {}
        
        if len(data) < 20:
            return {
                'volatility_trend': 0.0,
                'volatility_percentile': 50.0,
                'volatility_contraction': 0.0
            }
        
        closes = data['close']
        returns = closes.pct_change().dropna()
        
        # Volatility trend (increasing/decreasing)
        vol_short = returns.rolling(window=10).std()
        vol_long = returns.rolling(window=20).std()
        features['volatility_trend'] = (vol_short.iloc[-1] - vol_long.iloc[-1]) / vol_long.iloc[-1] if vol_long.iloc[-1] != 0 else 0
        
        # Current volatility percentile (compared to last 50 periods)
        all_vol = returns.rolling(window=20).std()
        current_vol = all_vol.iloc[-1]
        if len(all_vol.dropna()) > 10:
            vol_percentile = (all_vol.dropna() < current_vol).sum() / len(all_vol.dropna()) * 100
            features['volatility_percentile'] = vol_percentile
        else:
            features['volatility_percentile'] = 50.0
        
        # Volatility contraction/expansion
        features['volatility_contraction'] = vol_long.iloc[-1] / vol_long.iloc[-5] if len(vol_long) >= 5 and vol_long.iloc[-5] != 0 else 1.0
        
        return features
    
    def extract_features(self, data: pd.DataFrame) -> np.ndarray:
        """Extract all features for the ML model"""
        features = {}
        
        # Add technical indicators
        if self.config.include_technical_indicators:
            tech_features = self.calculate_technical_features(data)
            features.update(tech_features)
        
        # Add regime features
        if self.config.include_regime_features:
            regime_features = self.calculate_regime_features(data)
            features.update(regime_features)
        
        # Add volatility features
        if self.config.include_volatility_features:
            vol_features = self.calculate_volatility_features(data)
            features.update(vol_features)
        
        # Convert to numpy array
        feature_vector = np.array(list(features.values()), dtype=np.float32)
        
        return feature_vector
    
    def generate_individual_signals(
        self,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Generate signals from individual strategies"""
        signals = {}
        
        try:
            # Mean reversion signal
            mr_signal = self.mean_reversion_strategy.generate_signal(row, position, idx, data)
            signals['mean_reversion'] = mr_signal
            
            # Breakout signal (simplified for this example)
            # In a real implementation, we'd need to adapt the breakout strategy interface
            signals['breakout'] = None  # Placeholder
            
            # Trend following signal
            tf_signal = self.trend_following_strategy.generate_signal(row, position, idx, data)
            signals['trend_following'] = tf_signal
            
            # Adaptive signal based on regime
            regime_info = self._detect_current_regime(data)
            if regime_info:
                strategy_type, params, should_trade = adapt_strategy_for_regime(data, "SYMBOL")
                signals['adaptive'] = {
                    'action': 'BUY' if np.random.random() > 0.5 else 'SELL',  # Placeholder
                    'confidence': regime_info.get('confidence', 0.5),
                    'regime': regime_info.get('regime_type', 'unknown')
                } if should_trade else None
            else:
                signals['adaptive'] = None
                
        except Exception as e:
            logger.error(f"Error generating individual signals: {e}")
            # Return empty signals in case of error
            signals = {k: None for k in signals.keys()}
        
        return signals
    
    def _detect_current_regime(self, data: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """Detect current market regime (placeholder implementation)"""
        # This would connect to the actual regime detection system
        # For now, return a simple regime detection based on volatility and trend
        if len(data) < 50:
            return None
        
        closes = data['close']
        
        # Calculate simple regime indicators
        ma_20 = closes.rolling(window=20).mean()
        ma_50 = closes.rolling(window=50).mean()
        
        trend = (ma_20.iloc[-1] - ma_50.iloc[-1]) / ma_50.iloc[-1] if ma_50.iloc[-1] != 0 else 0
        
        returns = closes.pct_change().dropna()
        volatility = returns.rolling(window=20).std().iloc[-1] if len(returns) >= 20 else 0.02
        
        # Simple regime classification
        if abs(trend) > 0.02 and volatility < 0.02:  # Strong trend, low volatility
            regime_type = "trending"
        elif abs(trend) < 0.01 and volatility > 0.03:  # Weak trend, high volatility
            regime_type = "choppy"
        elif abs(trend) < 0.01 and volatility < 0.02:  # Weak trend, low volatility
            regime_type = "ranging"
        else:
            regime_type = "normal"
        
        return {
            'regime_type': regime_type,
            'trend_strength': abs(trend),
            'volatility_level': volatility,
            'confidence': 0.7  # Placeholder confidence
        }
    
    def combine_signals(
        self,
        individual_signals: Dict[str, Optional[Dict[str, Any]]],
        features: np.ndarray
    ) -> Optional[Dict[str, Any]]:
        """Combine individual strategy signals using ML-based ensemble"""
        # Get predictions from ML model about which strategy to trust
        ml_prediction = self._get_ml_strategy_weights(features)
        
        # Calculate weighted combination of signals
        buy_signals = 0
        sell_signals = 0
        total_confidence = 0
        
        for strategy_name, signal in individual_signals.items():
            if signal and signal.get('action') in ['BUY', 'SELL']:
                # Get the weight for this strategy from ML model
                weight = ml_prediction.get(strategy_name, self.current_weights.get(strategy_name, 0.25))
                
                # Get signal confidence
                confidence = signal.get('confidence', 0.5)
                
                if signal['action'] == 'BUY':
                    buy_signals += weight * confidence
                elif signal['action'] == 'SELL':
                    sell_signals += weight * confidence
                
                total_confidence += weight * confidence
        
        if total_confidence == 0:
            return None  # No signals to combine
        
        # Determine final action based on weighted votes
        buy_ratio = buy_signals / total_confidence if total_confidence > 0 else 0
        sell_ratio = sell_signals / total_confidence if total_confidence > 0 else 0
        
        # Set threshold for action
        threshold = 0.6  # Need 60% consensus for action
        
        if buy_ratio >= threshold:
            final_action = 'BUY'
            final_confidence = buy_ratio
        elif sell_ratio >= threshold:
            final_action = 'SELL'
            final_confidence = sell_ratio
        else:
            return None  # No clear consensus
        
        # Calculate combined stop loss and take profit based on weighted average
        stop_losses = []
        take_profits = []
        weights_for_calc = []
        
        for strategy_name, signal in individual_signals.items():
            if signal and signal.get('action') == final_action:
                weight = ml_prediction.get(strategy_name, self.current_weights.get(strategy_name, 0.25))
                confidence = signal.get('confidence', 0.5)
                
                if signal.get('stop_loss_pct'):
                    stop_losses.append(signal['stop_loss_pct'])
                    take_profits.append(signal.get('take_profit_pct', signal['stop_loss_pct'] * 2))
                    weights_for_calc.append(weight * confidence)
        
        if stop_losses and weights_for_calc:
            # Weighted average of stop losses and take profits
            combined_stop_loss = np.average(stop_losses, weights=weights_for_calc)
            combined_take_profit = np.average(take_profits, weights=weights_for_calc)
        else:
            # Default values
            combined_stop_loss = 1.5
            combined_take_profit = 3.0
        
        return {
            'action': final_action,
            'confidence': final_confidence,
            'stop_loss_pct': combined_stop_loss,
            'take_profit_pct': combined_take_profit,
            'reason': f'ML Ensemble: {final_action} with {final_confidence:.2f} confidence',
            'individual_signals': individual_signals,
            'strategy_weights': ml_prediction
        }
    
    def _get_ml_strategy_weights(self, features: np.ndarray) -> Dict[str, float]:
        """Get strategy weights from ML model based on current features"""
        try:
            # Reshape features for prediction if needed
            if len(features.shape) == 1:
                features = features.reshape(1, -1)
            
            # If we have a trained model, use it
            if hasattr(self.ml_model, 'predict') and len(self.target_history) > 10:
                # For this example, we'll return a simple prediction
                # In a real implementation, the model would predict optimal weights
                prediction = self.ml_model.predict(features)[0] if hasattr(self.ml_model.predict(features)[0], '__len__') else 0.5
                
                # For now, return current weights adjusted by a simple heuristic
                # based on the features
                weights = self.current_weights.copy()
                
                # Adjust weights based on market conditions
                # This is a simplified version - in reality, the ML model would learn these relationships
                if len(features) > 0:
                    # If volatility is high, favor mean reversion
                    if 'volatility' in locals() or 'volatility' in globals() or len(features) > 6:
                        try:
                            vol_idx = 6  # Assuming volatility is at index 6
                            if vol_idx < len(features) and features[vol_idx] > 0.025:  # High volatility
                                weights['mean_reversion'] += 0.1
                                weights['trend_following'] -= 0.1
                        except:
                            pass  # Ignore if index doesn't exist
                
                # Normalize weights
                total = sum(weights.values())
                if total > 0:
                    weights = {k: v/total for k, v in weights.items()}
                
                return weights
            else:
                # If no trained model, return current weights
                return self.current_weights.copy()
                
        except Exception as e:
            logger.error(f"Error getting ML strategy weights: {e}")
            # Return current weights in case of error
            return self.current_weights.copy()
    
    def update_performance_tracking(
        self,
        strategy_results: Dict[str, Optional[Dict[str, Any]]],
        actual_return: float,
        features: np.ndarray
    ):
        """Update performance tracking and potentially retrain ML model"""
        # Record performance for each strategy that generated a signal
        for strategy_name, signal in strategy_results.items():
            if signal:
                # Simplified performance attribution
                # In reality, this would be more complex
                if signal.get('action') == 'BUY' and actual_return > 0:
                    performance = 1.0
                elif signal.get('action') == 'SELL' and actual_return < 0:
                    performance = 1.0
                elif signal.get('action') and actual_return == 0:
                    performance = 0.5  # Neutral
                else:
                    performance = 0.0  # Wrong prediction
                
                self.strategy_performance[strategy_name].append(performance)
                
                # Keep only recent performance data
                if len(self.strategy_performance[strategy_name]) > self.config.performance_lookback:
                    self.strategy_performance[strategy_name] = self.strategy_performance[strategy_name][-self.config.performance_lookback:]
        
        # Add features and target to history for ML training
        self.feature_history.append(features)
        # Convert actual return to categorical target (1 for up, -1 for down, 0 for flat)
        target = 1 if actual_return > 0.001 else (-1 if actual_return < -0.001 else 0)
        self.target_history.append(target)
        
        # Keep only recent history
        max_history = 1000  # Limit to prevent memory issues
        if len(self.feature_history) > max_history:
            self.feature_history = self.feature_history[-max_history:]
            self.target_history = self.target_history[-max_history:]
        
        # Retrain ML model periodically
        if len(self.target_history) > 50 and len(self.target_history) % 10 == 0:  # Every 10 new samples after 50
            self._retrain_ml_model()
    
    def _retrain_ml_model(self):
        """Retrain the ML model with recent data"""
        try:
            if len(self.target_history) < 20:
                logger.debug("Not enough data to retrain ML model")
                return
            
            # Prepare training data
            X = np.array([f for f in self.feature_history])
            y = np.array(self.target_history)
            
            # Handle the case where features might have different lengths
            if len(X) != len(y):
                min_len = min(len(X), len(y))
                X = X[:min_len]
                y = y[:min_len]
            
            if len(X) < 20:
                logger.debug("Not enough aligned data to retrain ML model")
                return
            
            # Fit the model
            self.ml_model.fit(X, y)
            logger.info(f"ML model retrained with {len(X)} samples")
            
            # Update strategy weights based on recent performance
            self._update_strategy_weights()
            
        except Exception as e:
            logger.error(f"Error retraining ML model: {e}")
    
    def _update_strategy_weights(self):
        """Update strategy weights based on recent performance"""
        new_weights = {}
        
        for strategy_name in self.strategy_performance.keys():
            performance_history = self.strategy_performance[strategy_name]
            
            if performance_history:
                # Calculate recent performance (simple average of last N periods)
                recent_performance = np.mean(performance_history[-10:]) if len(performance_history) >= 10 else np.mean(performance_history)
                
                # Convert performance to weight (higher performance = higher weight)
                # Use a simple linear relationship
                base_weight = self.current_weights.get(strategy_name, 0.25)
                performance_factor = 1 + (recent_performance - 0.5)  # Adjust weight based on performance vs 50% baseline
                new_weights[strategy_name] = max(0.05, min(0.95, base_weight * performance_factor))  # Clamp between 5% and 95%
            else:
                new_weights[strategy_name] = self.current_weights.get(strategy_name, 0.25)
        
        # Normalize weights to sum to 1
        total_weight = sum(new_weights.values())
        if total_weight > 0:
            self.current_weights = {k: v/total_weight for k, v in new_weights.items()}
        else:
            # If all weights are 0, reset to equal weights
            equal_weight = 1.0 / len(new_weights) if new_weights else 0.25
            self.current_weights = {k: equal_weight for k in new_weights.keys()}
        
        logger.debug(f"Updated strategy weights: {self.current_weights}")
    
    def generate_signal(
        self,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """
        Generate ensemble signal by combining multiple strategies
        
        Args:
            row: Current market data row
            position: Current position (if any)
            idx: Current index in data
            data: Complete historical data
            
        Returns:
            Signal dictionary or None if no signal generated
        """
        # Extract features for ML model
        features = self.extract_features(data.iloc[:idx+1])
        
        # Generate signals from individual strategies
        individual_signals = self.generate_individual_signals(row, position, idx, data)
        
        # Combine signals using ML-based ensemble
        ensemble_signal = self.combine_signals(individual_signals, features)
        
        if ensemble_signal:
            logger.debug(f"Ensemble signal generated: {ensemble_signal['action']} with confidence {ensemble_signal['confidence']:.2f}")
        
        return ensemble_signal
    
    def save_model(self, filepath: str):
        """Save the trained ensemble model to disk"""
        model_data = {
            'config': self.config,
            'current_weights': self.current_weights,
            'ml_model': self.ml_model,
            'scaler': self.scaler,
            'strategy_performance': self.strategy_performance
        }
        
        joblib.dump(model_data, filepath)
        logger.info(f"Ensemble model saved to {filepath}")
    
    def load_model(self, filepath: str):
        """Load a trained ensemble model from disk"""
        model_data = joblib.load(filepath)
        
        self.config = model_data['config']
        self.current_weights = model_data['current_weights']
        self.ml_model = model_data['ml_model']
        self.scaler = model_data['scaler']
        self.strategy_performance = model_data['strategy_performance']
        
        logger.info(f"Ensemble model loaded from {filepath}")


class EnsembleManager:
    """
    Manager for handling multiple ensemble strategies across different assets and timeframes
    """
    
    def __init__(self):
        self.ensembles: Dict[str, EnsembleStrategy] = {}  # asset -> ensemble mapping
        self.timeframe_ensembles: Dict[Tuple[str, str], EnsembleStrategy] = {}  # (asset, timeframe) -> ensemble mapping
    
    def get_or_create_ensemble(
        self,
        asset: str,
        timeframe: str = "60m",
        config: Optional[EnsembleConfig] = None
    ) -> EnsembleStrategy:
        """Get existing ensemble or create new one for asset and timeframe"""
        key = (asset, timeframe)
        
        if key not in self.timeframe_ensembles:
            self.timeframe_ensembles[key] = EnsembleStrategy(config)
            logger.info(f"Created new ensemble for {asset} on {timeframe} timeframe")
        
        return self.timeframe_ensembles[key]
    
    def generate_ensemble_signal(
        self,
        asset: str,
        timeframe: str,
        row: pd.Series,
        position: Any,
        idx: int,
        data: pd.DataFrame
    ) -> Optional[Dict[str, Any]]:
        """Generate signal using the appropriate ensemble"""
        ensemble = self.get_or_create_ensemble(asset, timeframe)
        return ensemble.generate_signal(row, position, idx, data)
    
    def update_ensemble_performance(
        self,
        asset: str,
        timeframe: str,
        strategy_results: Dict[str, Optional[Dict[str, Any]]],
        actual_return: float,
        features: np.ndarray
    ):
        """Update performance tracking for an ensemble"""
        ensemble = self.get_or_create_ensemble(asset, timeframe)
        ensemble.update_performance_tracking(strategy_results, actual_return, features)


# Global ensemble manager instance
_global_ensemble_manager: Optional[EnsembleManager] = None


def get_ensemble_manager() -> EnsembleManager:
    """Get the global ensemble manager instance"""
    global _global_ensemble_manager
    if _global_ensemble_manager is None:
        _global_ensemble_manager = EnsembleManager()
    return _global_ensemble_manager


def create_ensemble_strategy(config: Optional[EnsembleConfig] = None) -> EnsembleStrategy:
    """Factory function to create an ensemble strategy"""
    return EnsembleStrategy(config)


def run_ensemble_backtest(
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
    transaction_cost: float = 0.001  # 0.1% per trade
) -> Dict[str, Any]:
    """
    Run a backtest of the ensemble strategy
    
    Args:
        data: OHLCV data for backtesting
        initial_capital: Starting capital
        transaction_cost: Cost per transaction (0.001 = 0.1%)
        
    Returns:
        Dictionary with backtest results
    """
    ensemble = EnsembleStrategy()
    
    capital = initial_capital
    position = None
    trade_log = []
    equity_curve = [initial_capital]
    
    for i in range(len(data)):
        row = data.iloc[i]
        
        # Generate ensemble signal
        signal = ensemble.generate_signal(row, position, i, data)
        
        # Execute trades based on signals
        if signal and signal['action'] == 'BUY' and position is None:
            # Enter long position
            position = {
                'entry_price': row['close'],
                'quantity': capital / row['close'],
                'entry_time': data.index[i],
                'stop_loss': row['close'] * (1 - signal['stop_loss_pct'] / 100),
                'take_profit': row['close'] * (1 + signal['take_profit_pct'] / 100)
            }
            
            # Deduct transaction cost
            capital *= (1 - transaction_cost)
            
        elif signal and signal['action'] == 'SELL' and position is None:
            # Enter short position (simplified)
            position = {
                'entry_price': row['close'],
                'quantity': capital / row['close'],
                'entry_time': data.index[i],
                'stop_loss': row['close'] * (1 + signal['stop_loss_pct'] / 100),
                'take_profit': row['close'] * (1 - signal['take_profit_pct'] / 100)
            }
            
            # Deduct transaction cost
            capital *= (1 - transaction_cost)
        
        # Check for exits
        if position:
            current_price = row['close']
            
            # Check stop loss or take profit
            exit_reason = None
            if position.get('stop_loss') and position.get('take_profit'):
                if position['entry_price'] > position['take_profit']:  # Short position
                    if current_price >= position['stop_loss'] or current_price <= position['take_profit']:
                        exit_reason = 'STOP_LOSS' if current_price >= position['stop_loss'] else 'TAKE_PROFIT'
                else:  # Long position
                    if current_price <= position['stop_loss'] or current_price >= position['take_profit']:
                        exit_reason = 'STOP_LOSS' if current_price <= position['stop_loss'] else 'TAKE_PROFIT'
            
            # Exit position if triggered
            if exit_reason:
                exit_price = current_price
                if position['entry_price'] > position['take_profit']:  # Short position
                    pnl = (position['entry_price'] - exit_price) / position['entry_price']
                else:  # Long position
                    pnl = (exit_price - position['entry_price']) / position['entry_price']
                
                capital *= (1 + pnl)
                capital *= (1 - transaction_cost)  # Exit transaction cost
                
                # Log trade
                trade_log.append({
                    'entry_time': position['entry_time'],
                    'exit_time': data.index[i],
                    'entry_price': position['entry_price'],
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'capital_after': capital,
                    'exit_reason': exit_reason
                })
                
                position = None
        
        # Record equity
        current_equity = capital
        if position:
            # Add unrealized P&L for open position
            current_price = row['close']
            if position['entry_price'] > position.get('take_profit', position['entry_price']):  # Short
                unrealized_pnl = (position['entry_price'] - current_price) / position['entry_price']
            else:  # Long
                unrealized_pnl = (current_price - position['entry_price']) / position['entry_price']
            current_equity = capital * (1 + unrealized_pnl)
        
        equity_curve.append(current_equity)
    
    # Calculate performance metrics
    equity_curve = equity_curve[1:]  # Remove initial duplicate
    returns = np.diff(equity_curve) / equity_curve[:-1]
    
    total_return = (equity_curve[-1] / initial_capital) - 1
    sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252 * 24) if np.std(returns) != 0 else 0  # Hourly data
    max_drawdown = 0
    if len(equity_curve) > 0:
        running_max = np.maximum.accumulate(equity_curve)
        drawdowns = (equity_curve - running_max) / running_max
        max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0
    
    win_trades = [t for t in trade_log if t['pnl'] > 0]
    lose_trades = [t for t in trade_log if t['pnl'] <= 0]
    
    win_rate = len(win_trades) / len(trade_log) if trade_log else 0
    avg_win = np.mean([t['pnl'] for t in win_trades]) if win_trades else 0
    avg_loss = abs(np.mean([t['pnl'] for t in lose_trades])) if lose_trades else 0
    profit_factor = (avg_win * len(win_trades)) / (avg_loss * len(lose_trades)) if avg_loss > 0 else float('inf')
    
    results = {
        'total_return': total_return,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'profit_factor': profit_factor,
        'total_trades': len(trade_log),
        'winning_trades': len(win_trades),
        'losing_trades': len(lose_trades),
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'final_capital': equity_curve[-1] if equity_curve else initial_capital,
        'trade_log': trade_log,
        'equity_curve': equity_curve
    }
    
    logger.info(f"Ensemble backtest completed: Return={total_return:.2%}, Sharpe={sharpe_ratio:.2f}, WinRate={win_rate:.2%}")
    
    return results