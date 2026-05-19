"""
Authentication utilities for Notification Service.

Provides simple API key authentication for admin endpoints. Mirrors the
risk-metrics-service auth pattern (services/risk-metrics-service/app/auth.py):
shared X-Admin-Key header verified against settings.admin_api_key.

Phase 9 T-09-03-05 remediation: closes the spoofing gap on
POST /api/v1/alerts/daily-summary, where any reachable process on port 8006
could POST a forged ml_gate_reason_counts payload and trigger a misleading
Telegram digest.
"""

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from .config import config

api_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def verify_admin_key(api_key: str = Security(api_key_header)) -> str:
    """
    Verify admin API key for protected endpoints.

    Args:
        api_key: API key from X-Admin-Key header.

    Returns:
        The validated API key.

    Raises:
        HTTPException: 401 if header missing, 403 if invalid, 500 if the
        service was deployed without an ADMIN_API_KEY configured (refuse to
        accept any caller against an empty server-side secret).
    """
    if not config.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Admin API key is not configured on the server",
        )

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin API key is required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != config.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid admin API key",
        )

    return api_key
