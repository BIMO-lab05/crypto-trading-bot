"""
Trading Engine Utilities Module
Purpose: Utility functions and classes for the trading engine

Available Utilities:
- SupportResistanceDetector: Detect support and resistance levels from price data

Updated: 2025-12-07
"""

from .support_resistance_detector import (
    SupportResistanceDetector,
    SupportLevel,
    ResistanceLevel,
    LevelStrength,
)

__all__ = [
    # Support/Resistance Detection
    "SupportResistanceDetector",
    "SupportLevel",
    "ResistanceLevel",
    "LevelStrength",
]
