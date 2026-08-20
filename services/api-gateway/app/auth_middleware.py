"""
Authentication Middleware
Provides dependency injection for route protection and user authentication
"""

import logging
import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.auth_models import (
    User,
    TokenData,
    verify_token,
    get_user,
    update_user_last_login,
)

logger = logging.getLogger(__name__)

# HTTP Bearer token security scheme
security = HTTPBearer()

# ============================================================================
# MODE-GATED API AUTH (added 2026-07-29, operator choice: "gate auth by mode")
# ============================================================================
# The trading control endpoints (start/stop/buy/sell/emergency-stop/circuit-
# breaker reset/train) are auth-guarded. In LIVE / non-paper / production /
# staging the guard is ENFORCED (fails closed). In local PAPER mode the guard
# is OPEN by default so the single-user dashboard — which has no login flow —
# keeps working without a token. This is deliberate and reversible:
#   * Force enforcement anywhere:  REQUIRE_API_AUTH=true
#   * Force open anywhere (NOT for real money): REQUIRE_API_AUTH=false
# When unset, enforcement auto-tracks the trading mode.


def api_auth_required() -> bool:
    """Return True when the newly-guarded control endpoints must enforce auth.

    Precedence:
    1. Explicit REQUIRE_API_AUTH env (true/false) wins.
    2. Otherwise enforce whenever this is real-money-adjacent or a hosted env:
       TRADING_MODE=LIVE, PAPER_TRADING_MODE=false, or ENVIRONMENT in
       {production, staging}.
    Read fresh each call so tests / runtime env flips are honored.
    """
    explicit = os.environ.get("REQUIRE_API_AUTH")
    if explicit is not None:
        return explicit.strip().lower() in ("1", "true", "yes", "on")

    environment = os.environ.get("ENVIRONMENT", "development").lower()
    trading_mode = os.environ.get("TRADING_MODE", "PAPER").upper()
    paper_trading = os.environ.get("PAPER_TRADING_MODE", "true").lower() == "true"

    if environment in ("production", "staging"):
        return True
    if trading_mode == "LIVE":
        return True
    if not paper_trading:
        return True
    return False


# Synthetic principal used only when auth is gated OPEN in local paper mode,
# so downstream handlers that read current_user.* still have a valid object.
_LOCAL_PAPER_PRINCIPAL = User(
    user_id="local-paper",
    username="local-paper-operator",
    email="local@paper.invalid",
    full_name="Local Paper Operator",
    is_active=True,
    is_admin=True,
    created_at=datetime.now(timezone.utc),
)

_optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Dependency to get current authenticated user from JWT token

    Args:
        credentials: HTTP Bearer token from Authorization header

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If token is invalid or user not found
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Extract token from credentials
    token = credentials.credentials

    # Verify and decode token
    token_data: Optional[TokenData] = verify_token(token)

    if token_data is None or token_data.username is None:
        raise credentials_exception

    # Get user from database
    user = get_user(username=token_data.username)

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    # Update last login timestamp
    update_user_last_login(user.username)

    # Return user without password hash
    return User(**user.dict(exclude={'hashed_password'}))


async def get_current_user_gated(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_optional_security),
) -> User:
    """Resolve the current principal, honoring the mode gate.

    - Auth NOT required (local paper): a valid token still resolves the real
      user; a missing token falls back to the synthetic local-paper principal
      so the tokenless dashboard keeps working. An INVALID token is always
      rejected (a bad token is never acceptable, in any mode).
    - Auth required (LIVE / prod / staging / REQUIRE_API_AUTH=true): a valid
      token is mandatory; missing/invalid → 401.

    Always returns a ``User`` (real or synthetic) so downstream active/admin
    dependencies keep their original ``User``-typed contract.
    """
    enforced = api_auth_required()

    if credentials is None:
        if enforced:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return _LOCAL_PAPER_PRINCIPAL  # gated open in local paper mode

    # A token was supplied: validate it in BOTH modes.
    token_data: Optional[TokenData] = verify_token(credentials.credentials)
    if token_data is None or token_data.username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user(username=token_data.username)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    update_user_last_login(user.username)
    return User(**user.dict(exclude={"hashed_password"}))


async def get_current_active_user(
    current_user: User = Depends(get_current_user_gated),
) -> User:
    """
    Dependency to get current active user.

    Mode-gated (2026-07-29): in local paper mode a missing token yields the
    synthetic local-paper principal (active); in LIVE/prod a valid token is
    required. See ``api_auth_required``.

    Args:
        current_user: User from the gated resolver

    Returns:
        Current active user

    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user_gated),
) -> User:
    """
    Dependency to get current admin user (for admin-only endpoints).

    Mode-gated (2026-07-29): in local paper mode a missing token yields the
    synthetic local-paper principal (admin), so operator control endpoints
    stay reachable from the tokenless dashboard; in LIVE/prod a valid admin
    token is required. See ``api_auth_required``.

    Args:
        current_user: User from the gated resolver

    Returns:
        Current admin user

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


async def get_current_active_user_strict(
    current_user: User = Depends(get_current_user),
) -> User:
    """Strict active-user dependency — ALWAYS requires a valid token.

    Used by identity/session endpoints (``/auth/me``, ``/auth/logout``) where
    returning a synthetic principal makes no sense: "who am I" must reflect a
    real authenticated user regardless of the trading-mode gate. ``get_current_user``
    uses HTTPBearer(auto_error=True), so a missing header yields 401 and an
    invalid token yields 401 — the contract these endpoints test.

    NOTE: missing-credentials used to yield 403. FastAPI changed
    ``HTTPBearer(auto_error=True)`` to raise 401 (RFC 7235: no credentials =
    Unauthorized, not Forbidden); this service picked the new behaviour up
    with the fastapi 0.109.2 -> 0.141.1 bump. An *inactive* user is still a
    genuine 403 below — authenticated but not permitted.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    return current_user


def optional_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[User]:
    """
    Optional authentication dependency
    Returns user if authenticated, None if not

    Args:
        credentials: Optional HTTP Bearer token

    Returns:
        User if authenticated, None otherwise
    """
    if credentials is None:
        return None

    try:
        token = credentials.credentials
        token_data = verify_token(token)

        if token_data is None or token_data.username is None:
            return None

        user = get_user(username=token_data.username)
        if user is None or not user.is_active:
            return None

        return User(**user.dict(exclude={'hashed_password'}))

    except Exception:
        return None
