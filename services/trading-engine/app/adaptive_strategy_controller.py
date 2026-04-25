"""
Adaptive Strategy Controller with Market Regime Detection
=========================================================

This module integrates market regime detection with adaptive parameter selection
for trading strategies. It uses Hurst exponent and other indicators to detect
market conditions and adjusts strategy parameters accordingly.

Features:
1. Real-time market regime detection (trending, mean-reverting, random walk)
2. Adaptive parameter selection based on detected regime
3. Strategy selection based on market conditions
4. Confidence-based parameter adjustments
5. Dynamic risk management
"""

import logging
from enum import Enum
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import numpy as np
import pandas as pd
from datetime import datetime

# Import existing modules
from trading_enhancements.hurst_exponent import HurstExponentCalculator, MarketRegimeType
from trading_enhancements.regime_strategy_selector import RegimeStrategySelector, get_regime_strategy_selector
from strategies.enhanced_mean_reversion_strategy import EnhancedMeanReversionConfig
from strategies.enhanced_breakout_strategy import EnhancedBreakoutConfig

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Types of strategies supported by the adaptive controller"""
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    TREND_FOLLOWING = "trend_following"
    MIXED = "mixed"


@dataclass
class AdaptiveParameters:
    """Container for adaptive strategy parameters"""
    # Strategy selection
    selected_strategy: StrategyType
    
    # Mean reversion parameters
    mr_bb_period: int = 20
    mr_bb_std: float = 2.0
    mr_rsi_period: int = 14
    mr_rsi_oversold: int = 30
    mr_rsi_overbought: int = 70
    mr_max_stop_loss: float = 2.0
    mr_take_profit_ratio: float = 2.0
    
    # Breakout parameters
    br_consolidation_lookback: int = 20
    br_volume_spike_multiplier: float = 2.0
    br_default_stop_loss: float = 1.5
    br_take_profit_ratio: float = 3.0
    
    # Risk management
    position_size_multiplier: float = 1.0
    max_position_pct: float = 5.0
    risk_per_trade_pct: float = 1.5
    
    # Confidence and filtering
    min_signal_confidence: float = 0.5
    enable_dynamic_stops: bool = True


class AdaptiveStrategyController:
    """
    Adaptive Strategy Controller with Market Regime Detection
    
    This class monitors market conditions and adapts strategy parameters
    and selection based on detected market regime. It uses Hurst exponent
    analysis along with other indicators to determine the optimal strategy
    approach for current market conditions.
    
    The controller:
    1. Detects market regime using Hurst exponent
    2. Selects appropriate strategy based on regime
    3. Adjusts parameters for optimal performance in current regime
    4. Manages risk based on market predictability
    """
    
    def __init__(self):
        """Initialize the adaptive strategy controller"""
        self.hurst_calculator = HurstExponentCalculator()
        self.regime_selector = get_regime_strategy_selector()
        
        # Store historical regime data
        self.regime_history: Dict[str, list] = {}
        self.last_regime_switch: Dict[str, datetime] = {}
        
        logger.info("AdaptiveStrategyController initialized with Hurst exponent calculator and regime selector")
    
    def detect_market_regime(self, prices: pd.DataFrame, symbol: str = "UNKNOWN") -> Dict[str, Any]:
        """
        Detect current market regime using Hurst exponent and other indicators
        
        Args:
            prices: DataFrame with OHLCV data
            symbol: Trading symbol
            
        Returns:
            Dictionary with regime information
        """
        try:
            # Calculate Hurst exponent
            closes = prices['close'].values
            hurst_result = self.hurst_calculator.calculate_hurst_exponent(closes)
            
            # Additional regime indicators
            volatility_regime = self._assess_volatility_regime(prices)
            trend_regime = self._assess_trend_regime(prices)
            
            # Combine assessments
            combined_regime = self._combine_regime_assessments(hurst_result, volatility_regime, trend_regime)
            
            # Store in history
            if symbol not in self.regime_history:
                self.regime_history[symbol] = []
            self.regime_history[symbol].append({
                'timestamp': datetime.now(),
                'hurst_result': hurst_result,
                'volatility_regime': volatility_regime,
                'trend_regime': trend_regime,
                'combined_regime': combined_regime
            })
            
            # Keep only recent history (last 100 entries)
            if len(self.regime_history[symbol]) > 100:
                self.regime_history[symbol] = self.regime_history[symbol][-100:]
            
            result = {
                'regime_type': hurst_result.regime.value,
                'hurst_exponent': hurst_result.hurst_exponent,
                'confidence': hurst_result.confidence,
                'volatility_regime': volatility_regime,
                'trend_regime': trend_regime,
                'combined_regime': combined_regime,
                'regime_changed': self._has_regime_changed(symbol, hurst_result.regime)
            }
            
            logger.debug(f"Detected regime for {symbol}: {result['regime_type']} (H={hurst_result.hurst_exponent:.3f}, conf={hurst_result.confidence:.2f})")
            
            return result
            
        except Exception as e:
            logger.error(f"Error detecting market regime for {symbol}: {e}")
            # Return default random walk regime if detection fails
            return {
                'regime_type': MarketRegimeType.RANDOM_WALK.value,
                'hurst_exponent': 0.5,
                'confidence': 0.3,
                'volatility_regime': 'normal',
                'trend_regime': 'sideways',
                'combined_regime': MarketRegimeType.RANDOM_WALK,
                'regime_changed': False
            }
    
    def _assess_volatility_regime(self, prices: pd.DataFrame) -> str:
        """Assess volatility regime based on ATR and price movements"""
        if len(prices) < 20:
            return 'normal'
        
        # Calculate ATR-based volatility
        high = prices['high']
        low = prices['low']
        close = prices['close']
        
        # True Range calculation
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # ATR over 14 periods
        atr = true_range.rolling(window=14).mean()
        
        # Compare current ATR to historical average
        historical_avg = atr.rolling(window=50).mean()
        current_atr = atr.iloc[-1]
        historical_avg_val = historical_avg.iloc[-1] if len(historical_avg) > 0 else current_atr
        
        if current_atr > historical_avg_val * 1.5:
            return 'high'
        elif current_atr < historical_avg_val * 0.7:
            return 'low'
        else:
            return 'normal'
    
    def _assess_trend_regime(self, prices: pd.DataFrame) -> str:
        """Assess trend regime based on price movement patterns"""
        if len(prices) < 50:
            return 'sideways'
        
        closes = prices['close']
        
        # Calculate 20 and 50 period EMAs
        ema_20 = closes.ewm(span=20).mean()
        ema_50 = closes.ewm(span=50).mean()
        
        # Check if EMAs are aligned (indicating trend)
        price = closes.iloc[-1]
        ema_20_val = ema_20.iloc[-1]
        ema_50_val = ema_50.iloc[-1]
        
        # Determine trend direction
        if ema_20_val > ema_50_val and price > ema_20_val:
            return 'uptrend'
        elif ema_20_val < ema_50_val and price < ema_20_val:
            return 'downtrend'
        else:
            return 'sideways'
    
    def _combine_regime_assessments(self, hurst_result, volatility_regime, trend_regime) -> MarketRegimeType:
        """Combine multiple regime assessments into a single determination"""
        # Primary driver is Hurst exponent
        primary_regime = hurst_result.regime
        
        # Adjust based on volatility and trend
        if primary_regime == MarketRegimeType.TRENDING:
            # In trending regime, high volatility supports continuation
            if volatility_regime == 'high':
                return MarketRegimeType.TRENDING
            else:
                # Lower volatility might suggest trend is weakening
                return MarketRegimeType.MEAN_REVERTING
        elif primary_regime == MarketRegimeType.MEAN_REVERTING:
            # In mean reverting regime, low volatility supports continuation
            if volatility_regime == 'low':
                return MarketRegimeType.MEAN_REVERTING
            else:
                # Higher volatility might suggest trend emergence
                return MarketRegimeType.TRENDING
        else:  # RANDOM_WALK
            # In random walk, look for emerging trends
            if trend_regime != 'sideways':
                return MarketRegimeType.TRENDING
            else:
                return MarketRegimeType.RANDOM_WALK
    
    def _has_regime_changed(self, symbol: str, current_regime: MarketRegimeType) -> bool:
        """Check if there has been a regime change for this symbol"""
        if symbol in self.regime_history and len(self.regime_history[symbol]) > 1:
            previous_regime = self.regime_history[symbol][-2]['combined_regime']
            return previous_regime != current_regime
        return True  # Consider as change if no history
    
    def select_strategy_for_regime(self, regime_info: Dict[str, Any]) -> StrategyType:
        """
        Select the most appropriate strategy based on market regime
        
        Args:
            regime_info: Dictionary with regime information
            
        Returns:
            StrategyType enum value
        """
        regime_type = MarketRegimeType(regime_info['regime_type'])
        
        # Strategy selection logic based on regime
        if regime_type == MarketRegimeType.TRENDING:
            # In trending markets, trend-following or breakout strategies work best
            return StrategyType.BREAKOUT
        elif regime_type == MarketRegimeType.MEAN_REVERTING:
            # In mean-reverting markets, mean reversion strategies work best
            return StrategyType.MEAN_REVERSION
        else:  # RANDOM_WALK
            # In random walk markets, use conservative approach
            return StrategyType.MEAN_REVERSION  # Still use mean reversion but with conservative parameters
    
    def get_adaptive_parameters(self, regime_info: Dict[str, Any]) -> AdaptiveParameters:
        """
        Get adaptive parameters based on market regime
        
        Args:
            regime_info: Dictionary with regime information
            
        Returns:
            AdaptiveParameters object with regime-appropriate settings
        """
        regime_type = MarketRegimeType(regime_info['regime_type'])
        confidence = regime_info['confidence']
        
        # Get regime-specific strategy parameters
        strategy_params = self.regime_selector.get_strategy_for_regime(regime_type)
        
        # Adjust parameters based on regime
        if regime_type == MarketRegimeType.TRENDING:
            # In trending markets, use more aggressive parameters
            params = AdaptiveParameters(
                selected_strategy=StrategyType.BREAKOUT,
                br_consolidation_lookback=15,  # Shorter lookback for faster trend detection
                br_volume_spike_multiplier=1.8,  # Lower threshold for trend confirmation
                br_default_stop_loss=2.0,  # Wider stops for trend continuation
                br_take_profit_ratio=2.5,  # Larger targets for extended moves
                mr_bb_period=25,  # Longer term for trend identification
                mr_bb_std=2.2,  # Wider bands for trending markets
                position_size_multiplier=strategy_params['parameters']['position_size_multiplier'],
                max_position_pct=6.0,  # Slightly higher in trending markets
                risk_per_trade_pct=2.0,  # Higher risk in trending markets
                min_signal_confidence=0.4,  # Lower threshold in trending markets
                enable_dynamic_stops=True
            )
            
        elif regime_type == MarketRegimeType.MEAN_REVERTING:
            # In mean-reverting markets, use tighter parameters
            params = AdaptiveParameters(
                selected_strategy=StrategyType.MEAN_REVERSION,
                mr_bb_period=15,  # Shorter period for quicker signals
                mr_bb_std=1.8,  # Tighter bands for mean reversion
                mr_rsi_period=10,  # Faster RSI for quicker signals
                mr_rsi_oversold=25,  # More sensitive oversold
                mr_rsi_overbought=75,  # More sensitive overbought
                mr_max_stop_loss=1.2,  # Tighter stops for quick reversions
                mr_take_profit_ratio=1.5,  # Smaller targets for mean reversion
                br_consolidation_lookback=25,  # Longer lookback for consolidation
                position_size_multiplier=strategy_params['parameters']['position_size_multiplier'],
                max_position_pct=4.0,  # Conservative sizing
                risk_per_trade_pct=1.2,  # Lower risk in mean-reverting markets
                min_signal_confidence=0.6,  # Higher threshold for quality signals
                enable_dynamic_stops=True
            )
            
        else:  # RANDOM_WALK
            # In random walk markets, use most conservative parameters
            params = AdaptiveParameters(
                selected_strategy=StrategyType.MEAN_REVERSION,
                mr_bb_period=20,  # Standard period
                mr_bb_std=2.0,  # Standard bands
                mr_rsi_period=14,  # Standard RSI
                mr_rsi_oversold=30,  # Standard oversold
                mr_rsi_overbought=70,  # Standard overbought
                mr_max_stop_loss=1.5,  # Standard stops
                mr_take_profit_ratio=1.8,  # Moderate targets
                br_consolidation_lookback=30,  # Longer lookback for clearer signals
                br_volume_spike_multiplier=2.5,  # Higher threshold to avoid false signals
                position_size_multiplier=min(strategy_params['parameters']['position_size_multiplier'], 0.4),  # Very conservative
                max_position_pct=3.0,  # Very conservative sizing
                risk_per_trade_pct=1.0,  # Minimal risk
                min_signal_confidence=0.7,  # High threshold for quality signals
                enable_dynamic_stops=True
            )
        
        # Further adjust based on confidence level
        confidence_factor = min(confidence / 0.7, 1.2)  # Scale between 0.7-1.2 based on confidence
        params.position_size_multiplier *= confidence_factor
        params.risk_per_trade_pct *= confidence_factor
        
        # Ensure parameters stay within reasonable bounds
        params.position_size_multiplier = max(0.1, min(1.5, params.position_size_multiplier))
        params.risk_per_trade_pct = max(0.5, min(3.0, params.risk_per_trade_pct))
        
        logger.debug(f"Adaptive parameters for {regime_type.value}: {params.selected_strategy.value}, pos_size_mult={params.position_size_multiplier:.2f}")
        
        return params
    
    def adapt_strategy_parameters(
        self,
        strategy_type: StrategyType,
        adaptive_params: AdaptiveParameters
    ) -> Dict[str, Any]:
        """
        Adapt specific strategy parameters based on adaptive settings
        
        Args:
            strategy_type: Type of strategy to adapt
            adaptive_params: Adaptive parameters container
            
        Returns:
            Dictionary with adapted strategy parameters
        """
        if strategy_type == StrategyType.MEAN_REVERSION:
            # Adapt mean reversion strategy parameters
            params = {
                'bb_period': adaptive_params.mr_bb_period,
                'bb_std': adaptive_params.mr_bb_std,
                'rsi_period': adaptive_params.mr_rsi_period,
                'rsi_oversold': adaptive_params.mr_rsi_oversold,
                'rsi_overbought': adaptive_params.mr_rsi_overbought,
                'max_stop_loss_pct': adaptive_params.mr_max_stop_loss,
                'take_profit_ratio': adaptive_params.mr_take_profit_ratio,
                'use_dynamic_stops': adaptive_params.enable_dynamic_stops
            }
            
        elif strategy_type == StrategyType.BREAKOUT:
            # Adapt breakout strategy parameters
            params = {
                'consolidation_lookback': adaptive_params.br_consolidation_lookback,
                'volume_spike_multiplier': adaptive_params.br_volume_spike_multiplier,
                'default_stop_loss_pct': adaptive_params.br_default_stop_loss,
                'take_profit_ratio': adaptive_params.br_take_profit_ratio,
                'enable_dynamic_stops': adaptive_params.enable_dynamic_stops
            }
            
        else:
            # Default parameters for other strategies
            params = {
                'default_stop_loss_pct': 1.5,
                'take_profit_ratio': 2.0,
                'position_size_multiplier': adaptive_params.position_size_multiplier
            }
        
        # Add risk management parameters
        params.update({
            'position_size_multiplier': adaptive_params.position_size_multiplier,
            'max_position_pct': adaptive_params.max_position_pct,
            'risk_per_trade_pct': adaptive_params.risk_per_trade_pct,
            'min_signal_confidence': adaptive_params.min_signal_confidence
        })
        
        return params
    
    def should_trade_in_current_regime(
        self,
        regime_info: Dict[str, Any],
        signal_confidence: float = 0.0
    ) -> bool:
        """
        Determine if trading is advisable in current market regime
        
        Args:
            regime_info: Dictionary with regime information
            signal_confidence: Confidence in the trading signal
            
        Returns:
            Boolean indicating whether to trade
        """
        regime_type = MarketRegimeType(regime_info['regime_type'])
        regime_confidence = regime_info['confidence']
        
        # Use the regime selector's method for determining if trading is advisable
        should_trade = self.regime_selector.should_trade_in_regime(regime_type, regime_confidence)
        
        # Additional check: if signal confidence is too low, don't trade
        min_signal_conf = self.regime_selector._configs[regime_type].min_signal_confidence
        if signal_confidence < min_signal_conf:
            should_trade = False
        
        logger.debug(f"Trade decision: should_trade={should_trade}, regime={regime_type.value}, "
                    f"regime_conf={regime_confidence:.2f}, signal_conf={signal_confidence:.2f}")
        
        return should_trade
    
    def get_regime_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Get summary of regime history for a symbol
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with regime summary information
        """
        if symbol not in self.regime_history or not self.regime_history[symbol]:
            return {
                'symbol': symbol,
                'regime_count': 0,
                'current_regime': 'unknown',
                'regime_confidence': 0.0,
                'regime_change_frequency': 0.0
            }
        
        history = self.regime_history[symbol]
        current_regime = history[-1]['combined_regime']
        current_confidence = history[-1]['hurst_result'].confidence
        
        # Calculate regime change frequency
        regime_changes = 0
        for i in range(1, len(history)):
            if history[i]['combined_regime'] != history[i-1]['combined_regime']:
                regime_changes += 1
        
        change_frequency = regime_changes / len(history) if history else 0
        
        return {
            'symbol': symbol,
            'regime_count': len(history),
            'current_regime': current_regime.value,
            'regime_confidence': current_confidence,
            'regime_change_frequency': change_frequency,
            'total_regime_changes': regime_changes
        }


# Global instance for easy access
_adaptive_controller: Optional[AdaptiveStrategyController] = None


def get_adaptive_strategy_controller() -> AdaptiveStrategyController:
    """
    Get the global adaptive strategy controller instance
    
    Returns:
        AdaptiveStrategyController instance
    """
    global _adaptive_controller
    if _adaptive_controller is None:
        _adaptive_controller = AdaptiveStrategyController()
    return _adaptive_controller


def adapt_strategy_for_regime(
    prices: pd.DataFrame,
    symbol: str = "UNKNOWN"
) -> tuple[StrategyType, Dict[str, Any], bool]:
    """
    Convenience function to adapt strategy for current regime
    
    Args:
        prices: DataFrame with OHLCV data
        symbol: Trading symbol
        
    Returns:
        Tuple of (selected_strategy, parameters, should_trade)
    """
    controller = get_adaptive_strategy_controller()
    
    # Detect current regime
    regime_info = controller.detect_market_regime(prices, symbol)
    
    # Select appropriate strategy
    strategy_type = controller.select_strategy_for_regime(regime_info)
    
    # Get adaptive parameters
    adaptive_params = controller.get_adaptive_parameters(regime_info)
    
    # Adapt specific strategy parameters
    params = controller.adapt_strategy_parameters(strategy_type, adaptive_params)
    
    # Determine if trading is advisable
    should_trade = controller.should_trade_in_current_regime(regime_info)
    
    return strategy_type, params, should_trade