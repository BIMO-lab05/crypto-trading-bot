"""
Authentication utilities for Risk & Metrics Service
Provides simple API key authentication for admin endpoints
"""

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.config import settings

# API Key authentication scheme
api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def verify_admin_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify admin API key for protected endpoints

    Args:
        api_key: API key from X-Admin-Key header

    Returns:
        The validated API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )

    return api_key
