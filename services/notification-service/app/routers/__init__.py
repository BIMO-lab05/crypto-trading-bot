"""
API Routers Package
FastAPI routers for notification service endpoints
"""

from .alerts import router as alerts_router

__all__ = ["alerts_router"]
