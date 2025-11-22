"""
Authentication Middleware
Provides dependency injection for route protection and user authentication
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from app.auth_models import (
    User,
    TokenData,
    verify_token,
    get_user,
    update_user_last_login
)

# HTTP Bearer token security scheme
security = HTTPBearer()


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


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to get current active user

    Args:
        current_user: User from get_current_user dependency

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
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency to get current admin user (for admin-only endpoints)

    Args:
        current_user: User from get_current_user dependency

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
