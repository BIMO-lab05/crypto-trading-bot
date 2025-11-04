"""
Signal Aggregation Module
Purpose: Modular signal aggregation using Strangler Fig pattern
"""

from .gatekeeper import TrendGatekeeper
from .validator import VolumeValidator
from .voter import SignalVoter
from .aggregator_core import CoreAggregator

__all__ = [
    "TrendGatekeeper",
    "VolumeValidator",
    "SignalVoter",
    "CoreAggregator"
]
