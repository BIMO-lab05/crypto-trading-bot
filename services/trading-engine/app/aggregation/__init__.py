"""
Signal Aggregation Module
Purpose: Modular signal aggregation using Strangler Fig pattern
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
    AlignmentStrength
)

__all__ = [
    "TrendGatekeeper",
    "VolumeValidator",
    "SignalVoter",
    "CoreAggregator",
    "EnhancedAggregator",
    "MultiTimeframeAnalyzer",
    "get_multi_timeframe_analyzer",
    "reset_multi_timeframe_analyzer",
    "TimeframeSignal",
    "MultiTimeframeAnalysis",
    "AlignmentStrength"
]
