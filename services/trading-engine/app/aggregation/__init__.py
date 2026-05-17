"""
Signal Aggregation Module
Purpose: Modular signal aggregation using Strangler Fig pattern

Components:
- TrendGatekeeper: Blocks counter-trend trades using trend filter
- VolumeValidator: Filters low-volume signals with adaptive weighting
- SignalVoter: Calculates weighted votes from indicators
- CoreAggregator: Orchestrates the signal aggregation pipeline
- EnhancedAggregator: Extended aggregator with advanced features
- MultiTimeframeAnalyzer: Analyzes signals across multiple timeframes
- MarketRegimeDetector: Detects market regime using ADX for strategy optimization
"""

from .gatekeeper import TrendGatekeeper
from .validator import VolumeValidator
from .voter import SignalVoter
from .aggregator_core import CoreAggregator
from .enhanced_aggregator import EnhancedAggregator
from .multi_timeframe import (
    MultiTimeframeAnalyzer,
    get_multi_timeframe_analyzer,
    reset_multi_timeframe_analyzer,
    TimeframeSignal,
    MultiTimeframeAnalysis,
    AlignmentStrength,
)
from .market_regime import (
    MarketRegimeDetector,
    MarketRegime,
    TrendDirection,
    RegimeAnalysis,
    get_market_regime_detector,
    reset_market_regime_detector,
)
from .ml_gate_reasons import (
    MLGateReason,
    ML_GATE_REASONS,
    log_ml_disabled,
    record_ml_gate_event,
    snapshot_reasons,
    reset_counter,
    set_current_reason,
    get_current_reason,
)

__all__ = [
    # Core aggregation components
    "TrendGatekeeper",
    "VolumeValidator",
    "SignalVoter",
    "CoreAggregator",
    "EnhancedAggregator",
    # Multi-timeframe analysis
    "MultiTimeframeAnalyzer",
    "get_multi_timeframe_analyzer",
    "reset_multi_timeframe_analyzer",
    "TimeframeSignal",
    "MultiTimeframeAnalysis",
    "AlignmentStrength",
    # Market regime detection
    "MarketRegimeDetector",
    "MarketRegime",
    "TrendDirection",
    "RegimeAnalysis",
    "get_market_regime_detector",
    "reset_market_regime_detector",
    # MLGATE-03 reason enum + cross-plan reason-state cache (Plan 09-03)
    "MLGateReason",
    "ML_GATE_REASONS",
    "log_ml_disabled",
    "record_ml_gate_event",
    "snapshot_reasons",
    "reset_counter",
    "set_current_reason",
    "get_current_reason",
]
