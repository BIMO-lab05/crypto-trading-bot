"""
Market Data Service - Authentication
Purpose: API key authentication for securing endpoints
"""

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

# API Key security scheme
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify API key from request header
    
    Args:
        api_key: API key from X-API-Key header
    
    Returns:
        The validated API key
    
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key:
        logger.warning("API key missing from request")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is required. Provide it in X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    settings = get_settings()
    valid_keys = settings.api_keys_list
    
    if api_key not in valid_keys:
        logger.warning(f"Invalid API key attempt: {api_key[:8]}...")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )
    
    logger.debug(f"API key validated: {api_key[:8]}...")
    return api_key
