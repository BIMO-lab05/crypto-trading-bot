"""
API Handlers for ML Prediction Service
Purpose: FastAPI route handlers for various ML features
Author: Phase 6.1/6.2/6.3 ML Team
Date: 2025-12-11
"""

from app.handlers.orderbook import router as orderbook_router
from app.handlers.sentiment import router as sentiment_router
from app.handlers.regime import router as regime_router

__all__ = ["orderbook_router", "sentiment_router", "regime_router"]
