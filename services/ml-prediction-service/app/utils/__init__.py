# ML Prediction Service - Local Utils Module
# Provides fallback implementations when shared utils are not available

from .structured_logging import setup_logging, RequestContextLogger
from .graceful_shutdown import GracefulShutdownHandler

__all__ = ['setup_logging', 'RequestContextLogger', 'GracefulShutdownHandler']
