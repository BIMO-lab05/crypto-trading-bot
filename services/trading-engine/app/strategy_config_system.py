"""
Strategic Configuration System for Market Condition-Based Strategy Selection
========================================================================

This module provides a comprehensive configuration system that selects and configures
trading strategies based on real-time market conditions. It integrates all the
improvements implemented in the previous modules to create an adaptive trading system.

Features:
1. Dynamic strategy selection based on market conditions
2. Real-time parameter adaptation
3. Multi-criteria decision making
4. Configuration persistence and management
5. Performance-based strategy switching
6. Risk-adjusted strategy selection
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import os
from enum import Enum

# Import all the modules we've created
from strategies.enhanced_mean_reversion_strategy import EnhancedMeanReversionConfig, create_enhanced_mean_reversion_strategy
from strategies.enhanced_breakout_strategy import EnhancedBreakoutConfig, create_enhanced_breakout_strategy
from adaptive_strategy_controller import AdaptiveStrategyController, adapt_strategy_for_regime
from multi_timeframe_tester import MultiTimeframeTester, Timeframe
from ensemble_strategy import EnsembleStrategy, EnsembleConfig, create_ensemble_strategy

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """Types of strategies supported by the configuration system"""
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    TREND_FOLLOWING = "trend_following"
    ENSEMBLE = "ensemble"
    ADAPTIVE = "adaptive"


class MarketCondition(Enum):
    """Market conditions that influence strategy selection"""
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    CHOPPY = "choppy"
    BULLISH = "bullish"
    BEARISH = "bearish"
    UNCERTAIN = "uncertain"


@dataclass
class StrategySelectionCriteria:
    """Criteria for selecting strategies based on market conditions"""
    # Market condition weights (0-1)
    high_volatility_weight: float = 0.1
    low_volatility_weight: float = 0.1
    trending_up_weight: float = 0.1
    trending_down_weight: float = 0.1
    ranging_weight: float = 0.1
    choppy_weight: float = 0.1
    bullish_weight: float = 0.1
    bearish_weight: float = 0.1
    uncertain_weight: float = 0.1
    
    # Performance criteria
    minimum_sharpe_ratio: float = 0.5
    maximum_drawdown: float = 0.15
    minimum_win_rate: float = 0.40
    
    # Risk criteria
    maximum_position_size: float = 0.05  # 5% of portfolio
    maximum_risk_per_trade: float = 0.02  # 2% risk per trade
    
    # Timeframe preferences
    preferred_timeframes: List[Timeframe] = None
    
    def __post_init__(self):
        if self.preferred_timeframes is None:
            self.preferred_timeframes = [Timeframe.HOUR_1, Timeframe.HOUR_4, Timeframe.DAY_1]


@dataclass
class StrategyConfiguration:
    """Complete configuration for a trading strategy"""
    strategy_type: StrategyType
    market_conditions: List[MarketCondition]
    parameters: Dict[str, Any]
    priority: int = 1  # Lower number = higher priority
    enabled: bool = True
    performance_thresholds: Dict[str, float] = None
    
    def __post_init__(self):
        if self.performance_thresholds is None:
            self.performance_thresholds = {
                'sharpe_ratio': 0.5,
                'win_rate': 0.4,
                'profit_factor': 1.5,
                'max_drawdown': 0.15
            }


@dataclass
class MarketState:
    """Current market state with all relevant indicators"""
    volatility: float
    trend_strength: float
    trend_direction: float  # -1 to 1, where -1 is strong down, 1 is strong up
    momentum: float
    volume_trend: float
    regime_type: str  # From Hurst exponent
    regime_confidence: float
    correlation_regime: str  # High, Medium, Low correlation
    market_regime: str  # Bull, Bear, Sideways
    volatility_regime: str  # High, Normal, Low volatility
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class StrategyConfigurationSystem:
    """
    Strategic Configuration System for Market Condition-Based Strategy Selection
    
    This system intelligently selects and configures trading strategies based on
    real-time market conditions, integrating all the improvements made in the
    previous phases. It considers:
    
    1. Current market regime (trending, ranging, volatile, etc.)
    2. Risk tolerance and portfolio constraints
    3. Historical performance of strategies in similar conditions
    4. Multi-timeframe analysis
    5. ML-based ensemble predictions
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """Initialize the configuration system"""
        self.controller = AdaptiveStrategyController()
        self.ensemble = create_ensemble_strategy()
        
        # Default configurations
        self.default_configs: Dict[StrategyType, StrategyConfiguration] = self._create_default_configs()
        
        # Active configurations
        self.active_configs: List[StrategyConfiguration] = []
        
        # Selection criteria
        self.selection_criteria = StrategySelectionCriteria()
        
        # Performance tracking
        self.strategy_performance: Dict[StrategyType, List[Dict[str, Any]]] = {
            StrategyType.MEAN_REVERSION: [],
            StrategyType.BREAKOUT: [],
            StrategyType.ENSEMBLE: [],
            StrategyType.ADAPTIVE: []
        }
        
        # Load configuration if provided
        if config_file and os.path.exists(config_file):
            self.load_configuration(config_file)
        
        logger.info("StrategyConfigurationSystem initialized")
    
    def _create_default_configs(self) -> Dict[StrategyType, StrategyConfiguration]:
        """Create default configurations for all strategy types"""
        configs = {}
        
        # Mean Reversion Configuration
        configs[StrategyType.MEAN_REVERSION] = StrategyConfiguration(
            strategy_type=StrategyType.MEAN_REVERSION,
            market_conditions=[MarketCondition.RANGING, MarketCondition.CHOPPY, MarketCondition.LOW_VOLATILITY],
            parameters={
                'bb_period': 20,
                'bb_std': 2.0,
                'rsi_period': 14,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'max_stop_loss_pct': 1.5,
                'take_profit_ratio': 2.0,
                'use_dynamic_stops': True
            },
            priority=2,
            enabled=True
        )
        
        # Breakout Configuration
        configs[StrategyType.BREAKOUT] = StrategyConfiguration(
            strategy_type=StrategyType.BREAKOUT,
            market_conditions=[MarketCondition.TRENDING_UP, MarketCondition.TRENDING_DOWN, MarketCondition.HIGH_VOLATILITY],
            parameters={
                'consolidation_lookback': 20,
                'volume_spike_multiplier': 2.0,
                'default_stop_loss_pct': 1.5,
                'take_profit_ratio': 3.0,
                'enable_dynamic_stops': True,
                'require_momentum_confirmation': True
            },
            priority=2,
            enabled=True
        )
        
        # Ensemble Configuration
        configs[StrategyType.ENSEMBLE] = StrategyConfiguration(
            strategy_type=StrategyType.ENSEMBLE,
            market_conditions=[MarketCondition.BULLISH, MarketCondition.BEARISH, MarketCondition.UNCERTAIN],
            parameters={
                'mean_reversion_weight': 0.3,
                'breakout_weight': 0.3,
                'trend_following_weight': 0.2,
                'adaptive_weight': 0.2
            },
            priority=1,  # Highest priority
            enabled=True
        )
        
        # Adaptive Configuration
        configs[StrategyType.ADAPTIVE] = StrategyConfiguration(
            strategy_type=StrategyType.ADAPTIVE,
            market_conditions=[MarketCondition.HIGH_VOLATILITY, MarketCondition.LOW_VOLATILITY, MarketCondition.TRENDING_UP, MarketCondition.TRENDING_DOWN],
            parameters={},
            priority=1,  # Highest priority
            enabled=True
        )
        
        return configs
    
    def assess_market_state(self, data: Dict[str, Any]) -> MarketState:
        """
        Assess current market state based on provided data
        
        Args:
            data: Dictionary containing market data (OHLCV, indicators, etc.)
            
        Returns:
            MarketState object with current market conditions
        """
        # Extract data
        closes = data.get('closes', [])
        highs = data.get('highs', [])
        lows = data.get('lows', [])
        volumes = data.get('volumes', [])
        
        if len(closes) < 50:
            # Not enough data, return default state
            return MarketState(
                volatility=0.02,
                trend_strength=0.0,
                trend_direction=0.0,
                momentum=0.0,
                volume_trend=0.0,
                regime_type="random_walk",
                regime_confidence=0.5,
                correlation_regime="medium",
                market_regime="sideways",
                volatility_regime="normal"
            )
        
        # Calculate volatility (20-period standard deviation of returns)
        import numpy as np
        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns[-20:]) if len(returns) >= 20 else 0.02
        
        # Calculate trend strength (using 20 and 50 period EMAs)
        import pandas as pd
        close_series = pd.Series(closes)
        ema_20 = close_series.ewm(span=20).mean()
        ema_50 = close_series.ewm(span=50).mean()
        
        if len(ema_20) > 0 and len(ema_50) > 0:
            trend_strength = abs(ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1] if ema_50.iloc[-1] != 0 else 0.0
            trend_direction = 1.0 if ema_20.iloc[-1] > ema_50.iloc[-1] else -1.0
        else:
            trend_strength = 0.0
            trend_direction = 0.0
        
        # Calculate momentum (10-period ROC)
        momentum = (closes[-1] - closes[-11]) / closes[-11] if len(closes) >= 11 else 0.0
        
        # Calculate volume trend
        if len(volumes) >= 20:
            vol_sma = sum(volumes[-20:]) / 20
            current_vol = volumes[-1]
            volume_trend = (current_vol - vol_sma) / vol_sma if vol_sma != 0 else 0.0
        else:
            volume_trend = 0.0
        
        # Determine market regime based on trend and volatility
        if abs(trend_direction) > 0.5 and trend_strength > 0.02:
            market_regime = "bullish" if trend_direction > 0 else "bearish"
        elif trend_strength < 0.01:
            market_regime = "sideways"
        else:
            market_regime = "trending"
        
        # Determine volatility regime
        if volatility > 0.03:
            volatility_regime = "high"
        elif volatility < 0.01:
            volatility_regime = "low"
        else:
            volatility_regime = "normal"
        
        # For regime type, we'll use a placeholder - in reality this would come from Hurst exponent
        regime_type = "trending" if trend_strength > 0.02 else "mean_reverting"
        regime_confidence = min(trend_strength * 50, 1.0)  # Scale trend strength to confidence
        
        return MarketState(
            volatility=volatility,
            trend_strength=trend_strength,
            trend_direction=trend_direction,
            momentum=momentum,
            volume_trend=volume_trend,
            regime_type=regime_type,
            regime_confidence=regime_confidence,
            correlation_regime="medium",  # Placeholder
            market_regime=market_regime,
            volatility_regime=volatility_regime
        )
    
    def select_strategies(self, market_state: MarketState) -> List[StrategyConfiguration]:
        """
        Select appropriate strategies based on market state
        
        Args:
            market_state: Current market state
            
        Returns:
            List of StrategyConfiguration objects in priority order
        """
        selected_configs = []
        
        # Evaluate each strategy against market conditions
        for strategy_type, config in self.default_configs.items():
            if not config.enabled:
                continue
            
            # Calculate compatibility score based on market conditions
            compatibility_score = self._calculate_compatibility_score(config, market_state)
            
            # Check if strategy meets performance thresholds
            if self._meets_performance_thresholds(strategy_type, compatibility_score):
                # Adjust parameters based on market state
                adjusted_config = self._adjust_config_for_market_state(config, market_state)
                selected_configs.append(adjusted_config)
        
        # Sort by priority (lower number = higher priority) and then by compatibility score
        selected_configs.sort(key=lambda x: (x.priority, -self._calculate_compatibility_score(x, market_state)))
        
        logger.info(f"Selected {len(selected_configs)} strategies for current market state")
        
        return selected_configs
    
    def _calculate_compatibility_score(self, config: StrategyConfiguration, market_state: MarketState) -> float:
        """Calculate how compatible a strategy is with current market state"""
        score = 0.0
        
        # Weight different market conditions
        condition_weights = {
            MarketCondition.HIGH_VOLATILITY: 0.15,
            MarketCondition.LOW_VOLATILITY: 0.15,
            MarketCondition.TRENDING_UP: 0.15,
            MarketCondition.TRENDING_DOWN: 0.15,
            MarketCondition.RANGING: 0.2,
            MarketCondition.CHOPPY: 0.1,
            MarketCondition.BULLISH: 0.05,
            MarketCondition.BEARISH: 0.05
        }
        
        # Evaluate each condition in the configuration
        for condition in config.market_conditions:
            weight = condition_weights.get(condition, 0.1)
            
            # Score based on market state
            if condition == MarketCondition.HIGH_VOLATILITY and market_state.volatility > 0.025:
                score += weight
            elif condition == MarketCondition.LOW_VOLATILITY and market_state.volatility < 0.015:
                score += weight
            elif condition == MarketCondition.TRENDING_UP and market_state.trend_direction > 0.3:
                score += weight
            elif condition == MarketCondition.TRENDING_DOWN and market_state.trend_direction < -0.3:
                score += weight
            elif condition == MarketCondition.RANGING and market_state.trend_strength < 0.01:
                score += weight
            elif condition == MarketCondition.CHOPPY and market_state.volatility > 0.03 and market_state.trend_strength < 0.01:
                score += weight
            elif condition == MarketCondition.BULLISH and market_state.market_regime == "bullish":
                score += weight
            elif condition == MarketCondition.BEARISH and market_state.market_regime == "bearish":
                score += weight
        
        # Additional scoring based on regime compatibility
        if config.strategy_type == StrategyType.MEAN_REVERSION and market_state.regime_type == "mean_reverting":
            score += 0.2
        elif config.strategy_type == StrategyType.BREAKOUT and market_state.regime_type == "trending":
            score += 0.2
        elif config.strategy_type == StrategyType.ENSEMBLE:
            # Ensemble strategies work well in most conditions
            score += 0.15
        
        # Adjust for regime confidence
        score *= market_state.regime_confidence
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _meets_performance_thresholds(self, strategy_type: StrategyType, compatibility_score: float) -> bool:
        """Check if strategy meets performance thresholds"""
        # For now, just check compatibility score
        # In a real system, this would check historical performance
        return compatibility_score > 0.3
    
    def _adjust_config_for_market_state(self, config: StrategyConfiguration, market_state: MarketState) -> StrategyConfiguration:
        """Adjust strategy configuration based on market state"""
        # Create a copy of the config to modify
        adjusted_config = StrategyConfiguration(
            strategy_type=config.strategy_type,
            market_conditions=config.market_conditions,
            parameters=config.parameters.copy(),
            priority=config.priority,
            enabled=config.enabled,
            performance_thresholds=config.performance_thresholds.copy()
        )
        
        # Adjust parameters based on market conditions
        if market_state.volatility_regime == "high":
            # In high volatility, use wider stops and smaller position sizes
            if 'max_stop_loss_pct' in adjusted_config.parameters:
                adjusted_config.parameters['max_stop_loss_pct'] *= 1.5
            if 'take_profit_ratio' in adjusted_config.parameters:
                adjusted_config.parameters['take_profit_ratio'] *= 1.2
        elif market_state.volatility_regime == "low":
            # In low volatility, use tighter stops and potentially larger positions
            if 'max_stop_loss_pct' in adjusted_config.parameters:
                adjusted_config.parameters['max_stop_loss_pct'] *= 0.8
            if 'take_profit_ratio' in adjusted_config.parameters:
                adjusted_config.parameters['take_profit_ratio'] *= 0.9
        
        # Adjust for trending vs ranging markets
        if market_state.market_regime == "trending":
            # For trending markets, favor strategies that work well in trends
            if config.strategy_type == StrategyType.MEAN_REVERSION:
                # Reduce mean reversion parameters in trending markets
                if 'rsi_oversold' in adjusted_config.parameters:
                    adjusted_config.parameters['rsi_oversold'] = max(20, adjusted_config.parameters['rsi_oversold'] - 5)
                if 'rsi_overbought' in adjusted_config.parameters:
                    adjusted_config.parameters['rsi_overbought'] = min(80, adjusted_config.parameters['rsi_overbought'] + 5)
        elif market_state.market_regime == "sideways":
            # For ranging markets, favor mean reversion strategies
            if config.strategy_type == StrategyType.MEAN_REVERSION:
                # Make mean reversion more sensitive in ranging markets
                if 'rsi_oversold' in adjusted_config.parameters:
                    adjusted_config.parameters['rsi_oversold'] = min(35, adjusted_config.parameters['rsi_oversold'] + 5)
                if 'rsi_overbought' in adjusted_config.parameters:
                    adjusted_config.parameters['rsi_overbought'] = max(65, adjusted_config.parameters['rsi_overbought'] - 5)
        
        # Adjust position sizing based on risk
        risk_factor = min(market_state.volatility * 50, 2.0)  # Scale risk based on volatility
        if 'position_size_multiplier' in adjusted_config.parameters:
            adjusted_config.parameters['position_size_multiplier'] /= risk_factor
        else:
            adjusted_config.parameters['position_size_multiplier'] = 1.0 / risk_factor
        
        return adjusted_config
    
    def get_active_strategies(self, market_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get active strategies for current market conditions
        
        Args:
            market_data: Dictionary containing current market data
            
        Returns:
            List of dictionaries with strategy information
        """
        # Assess market state
        market_state = self.assess_market_state(market_data)
        
        # Select strategies
        selected_configs = self.select_strategies(market_state)
        
        # Create strategy instances with their configurations
        active_strategies = []
        for config in selected_configs:
            strategy_info = {
                'strategy_type': config.strategy_type.value,
                'configuration': config.parameters,
                'priority': config.priority,
                'compatibility_score': self._calculate_compatibility_score(config, market_state),
                'market_conditions': [cond.value for cond in config.market_conditions],
                'timestamp': datetime.now().isoformat()
            }
            
            # Add additional info based on strategy type
            if config.strategy_type == StrategyType.MEAN_REVERSION:
                strategy_info['strategy_class'] = 'EnhancedMeanReversionStrategy'
                strategy_info['instance'] = create_enhanced_mean_reversion_strategy(**config.parameters)
            elif config.strategy_type == StrategyType.BREAKOUT:
                strategy_info['strategy_class'] = 'EnhancedBreakoutStrategy'
                # For breakout, we need to create the strategy differently
                strategy_info['instance'] = create_enhanced_breakout_strategy()
            elif config.strategy_type == StrategyType.ENSEMBLE:
                strategy_info['strategy_class'] = 'EnsembleStrategy'
                strategy_info['instance'] = self.ensemble
            elif config.strategy_type == StrategyType.ADAPTIVE:
                strategy_info['strategy_class'] = 'AdaptiveStrategy'
                # Use the adaptive controller to get appropriate strategy
                strategy_type, params, should_trade = adapt_strategy_for_regime(
                    market_data.get('df', None),  # Assuming dataframe is provided
                    market_data.get('symbol', 'UNKNOWN')
                )
                strategy_info['adaptive_selection'] = strategy_type.value
                strategy_info['adaptive_params'] = params
                strategy_info['should_trade'] = should_trade
            
            active_strategies.append(strategy_info)
        
        # Update active configurations
        self.active_configs = selected_configs
        
        logger.info(f"Activated {len(active_strategies)} strategies for current market conditions")
        
        return active_strategies
    
    def update_performance(self, strategy_type: StrategyType, performance_metrics: Dict[str, Any]):
        """Update performance tracking for a strategy"""
        self.strategy_performance[strategy_type].append({
            'timestamp': datetime.now(),
            'metrics': performance_metrics,
            'sharpe_ratio': performance_metrics.get('sharpe_ratio', 0),
            'win_rate': performance_metrics.get('win_rate', 0),
            'max_drawdown': performance_metrics.get('max_drawdown', 0),
            'total_return': performance_metrics.get('total_return', 0)
        })
        
        # Keep only recent performance data (last 30 records)
        if len(self.strategy_performance[strategy_type]) > 30:
            self.strategy_performance[strategy_type] = self.strategy_performance[strategy_type][-30:]
    
    def optimize_strategy_selection(self):
        """Optimize strategy selection based on historical performance"""
        # Analyze performance data to adjust selection criteria
        for strategy_type, performance_records in self.strategy_performance.items():
            if not performance_records:
                continue
            
            # Calculate average performance metrics
            avg_sharpe = np.mean([rec['sharpe_ratio'] for rec in performance_records])
            avg_win_rate = np.mean([rec['win_rate'] for rec in performance_records])
            avg_drawdown = np.mean([rec['max_drawdown'] for rec in performance_records])
            
            # Adjust selection criteria based on performance
            # This is a simplified example - in reality, this would be more sophisticated
            if avg_sharpe > 1.0:
                # If strategy performs well, increase its priority in certain conditions
                logger.info(f"{strategy_type.value} performing well: Sharpe={avg_sharpe:.2f}")
            elif avg_sharpe < 0.3:
                # If strategy performs poorly, consider reducing its priority
                logger.info(f"{strategy_type.value} underperforming: Sharpe={avg_sharpe:.2f}")
    
    def save_configuration(self, filepath: str):
        """Save current configuration to file"""
        config_data = {
            'selection_criteria': asdict(self.selection_criteria),
            'default_configs': {
                strategy_type.value: {
                    'strategy_type': config.strategy_type.value,
                    'market_conditions': [cond.value for cond in config.market_conditions],
                    'parameters': config.parameters,
                    'priority': config.priority,
                    'enabled': config.enabled,
                    'performance_thresholds': config.performance_thresholds
                } for strategy_type, config in self.default_configs.items()
            },
            'active_configs': [
                {
                    'strategy_type': config.strategy_type.value,
                    'market_conditions': [cond.value for cond in config.market_conditions],
                    'parameters': config.parameters,
                    'priority': config.priority,
                    'enabled': config.enabled,
                    'performance_thresholds': config.performance_thresholds
                } for config in self.active_configs
            ],
            'timestamp': datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(config_data, f, indent=2, default=str)
        
        logger.info(f"Configuration saved to {filepath}")
    
    def load_configuration(self, filepath: str):
        """Load configuration from file"""
        with open(filepath, 'r') as f:
            config_data = json.load(f)
        
        # Load selection criteria
        criteria_data = config_data.get('selection_criteria', {})
        self.selection_criteria = StrategySelectionCriteria(**{
            k: v for k, v in criteria_data.items() 
            if k in [field.name for field in StrategySelectionCriteria.__dataclass_fields__.values()]
        })
        
        # Load default configurations
        if 'default_configs' in config_data:
            for strategy_type_str, config_dict in config_data['default_configs'].items():
                strategy_type = StrategyType(strategy_type_str)
                market_conditions = [MarketCondition(cond) for cond in config_dict['market_conditions']]
                
                config = StrategyConfiguration(
                    strategy_type=StrategyType(config_dict['strategy_type']),
                    market_conditions=market_conditions,
                    parameters=config_dict['parameters'],
                    priority=config_dict['priority'],
                    enabled=config_dict['enabled'],
                    performance_thresholds=config_dict['performance_thresholds']
                )
                
                self.default_configs[StrategyType(strategy_type_str)] = config
        
        # Load active configurations
        if 'active_configs' in config_data:
            self.active_configs = []
            for config_dict in config_data['active_configs']:
                market_conditions = [MarketCondition(cond) for cond in config_dict['market_conditions']]
                
                config = StrategyConfiguration(
                    strategy_type=StrategyType(config_dict['strategy_type']),
                    market_conditions=market_conditions,
                    parameters=config_dict['parameters'],
                    priority=config_dict['priority'],
                    enabled=config_dict['enabled'],
                    performance_thresholds=config_dict['performance_thresholds']
                )
                
                self.active_configs.append(config)
        
        logger.info(f"Configuration loaded from {filepath}")
    
    def get_recommendation(self, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get strategy recommendation based on market data
        
        Args:
            market_data: Dictionary containing market data
            
        Returns:
            Dictionary with strategy recommendation
        """
        # Get active strategies
        active_strategies = self.get_active_strategies(market_data)
        
        if not active_strategies:
            return {
                'action': 'HOLD',
                'reason': 'No suitable strategies identified for current market conditions',
                'confidence': 0.0,
                'recommended_strategies': [],
                'market_state': asdict(self.assess_market_state(market_data))
            }
        
        # Select the highest priority strategy with highest compatibility
        best_strategy = max(active_strategies, key=lambda x: (1/x['priority'], x['compatibility_score']) if x['priority'] > 0 else (0, x['compatibility_score']))
        
        # Determine action based on the recommended strategy
        action = 'HOLD'  # Default action
        confidence = best_strategy['compatibility_score']
        
        # In a real implementation, this would generate actual trading signals
        # For now, we'll just return the recommended strategy
        
        return {
            'action': action,
            'reason': f"Selected {best_strategy['strategy_type']} strategy based on current market conditions",
            'confidence': confidence,
            'recommended_strategy': best_strategy['strategy_type'],
            'strategy_parameters': best_strategy['configuration'],
            'recommended_strategies': active_strategies[:3],  # Top 3 strategies
            'market_state': asdict(self.assess_market_state(market_data)),
            'timestamp': datetime.now().isoformat()
        }


def create_strategy_configuration_system(config_file: Optional[str] = None) -> StrategyConfigurationSystem:
    """Factory function to create a strategy configuration system"""
    return StrategyConfigurationSystem(config_file)


def get_market_regime_from_data(data: Dict[str, Any]) -> str:
    """
    Helper function to determine market regime from data
    
    Args:
        data: Market data dictionary
        
    Returns:
        String representing the market regime
    """
    # This would typically use the Hurst exponent or other advanced methods
    # For now, we'll use a simple approach based on trend and volatility
    
    closes = data.get('closes', [])
    if len(closes) < 50:
        return "uncertain"
    
    import numpy as np
    import pandas as pd
    
    # Calculate trend strength
    close_series = pd.Series(closes)
    ema_20 = close_series.ewm(span=20).mean()
    ema_50 = close_series.ewm(span=50).mean()
    
    if len(ema_20) > 0 and len(ema_50) > 0:
        trend_strength = abs(ema_20.iloc[-1] - ema_50.iloc[-1]) / ema_50.iloc[-1] if ema_50.iloc[-1] != 0 else 0.0
        
        # Calculate volatility
        returns = np.diff(closes) / closes[:-1]
        volatility = np.std(returns[-20:]) if len(returns) >= 20 else 0.02
        
        if trend_strength > 0.02 and volatility < 0.02:
            return "trending"
        elif trend_strength < 0.01 and volatility > 0.025:
            return "mean_reverting"
        else:
            return "random_walk"
    else:
        return "uncertain"


# Global instance
_config_system: Optional[StrategyConfigurationSystem] = None


def get_strategy_configuration_system() -> StrategyConfigurationSystem:
    """Get the global strategy configuration system instance"""
    global _config_system
    if _config_system is None:
        _config_system = StrategyConfigurationSystem()
    return _config_system