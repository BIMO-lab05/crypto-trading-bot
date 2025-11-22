"""
Tests for Authentication Middleware
Tests JWT authentication, user authorization, and access control
"""

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from unittest.mock import Mock, patch
from datetime import datetime

from app.auth_middleware import (
    get_current_user,
    get_current_active_user,
    get_current_admin_user,
    optional_auth
)
from app.auth_models import User, UserInDB, TokenData, create_access_token


class TestGetCurrentUser:
    """Test get_current_user dependency"""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user"""
        return UserInDB(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow(),
            last_login=None
        )

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self, mock_user):
        """Test getting current user with valid token"""
        # Create valid token
        token = create_access_token(data={"sub": "testuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=mock_user):
            user = await get_current_user(credentials)

        assert user.username == "testuser"
        assert user.user_id == "user_1"
        assert user.is_active is True
        # Password should not be in returned user
        assert not hasattr(user, 'hashed_password')

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test with invalid JWT token"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token.here"
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Could not validate credentials" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_token_without_username(self, mock_user):
        """Test token without username in payload"""
        # Create token without 'sub' claim
        token = create_access_token(data={"user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # Mock verify_token to return TokenData without username
        with patch('app.auth_middleware.verify_token', return_value=TokenData(username=None)):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self):
        """Test when user doesn't exist in database"""
        token = create_access_token(data={"sub": "nonexistent", "user_id": "user_999"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_current_user_inactive_user(self):
        """Test with inactive user account"""
        inactive_user = UserInDB(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=False,  # Inactive
            is_admin=False,
            created_at=datetime.utcnow(),
            last_login=None
        )

        token = create_access_token(data={"sub": "testuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=inactive_user):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Inactive user" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_updates_last_login(self, mock_user):
        """Test that last login is updated"""
        token = create_access_token(data={"sub": "testuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=mock_user):
            with patch('app.auth_middleware.update_user_last_login') as mock_update:
                user = await get_current_user(credentials)

                mock_update.assert_called_once_with("testuser")


class TestGetCurrentActiveUser:
    """Test get_current_active_user dependency"""

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self):
        """Test getting active user"""
        active_user = User(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow()
        )

        result = await get_current_active_user(active_user)

        assert result == active_user
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self):
        """Test with inactive user"""
        inactive_user = User(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            is_active=False,
            is_admin=False,
            created_at=datetime.utcnow()
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(inactive_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Inactive user" in exc_info.value.detail


class TestGetCurrentAdminUser:
    """Test get_current_admin_user dependency"""

    @pytest.mark.asyncio
    async def test_get_current_admin_user_success(self):
        """Test getting admin user"""
        admin_user = User(
            user_id="user_1",
            username="admin",
            email="admin@example.com",
            is_active=True,
            is_admin=True,
            created_at=datetime.utcnow()
        )

        result = await get_current_admin_user(admin_user)

        assert result == admin_user
        assert result.is_admin is True

    @pytest.mark.asyncio
    async def test_get_current_admin_user_not_admin(self):
        """Test with non-admin user"""
        regular_user = User(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow()
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_admin_user(regular_user)

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Admin access required" in exc_info.value.detail


class TestOptionalAuth:
    """Test optional_auth dependency"""

    def test_optional_auth_with_valid_token(self):
        """Test optional auth with valid credentials"""
        mock_user = UserInDB(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_admin=False,
            created_at=datetime.utcnow(),
            last_login=None
        )

        token = create_access_token(data={"sub": "testuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=mock_user):
            user = optional_auth(credentials)

        assert user is not None
        assert user.username == "testuser"

    def test_optional_auth_with_no_credentials(self):
        """Test optional auth without credentials"""
        user = optional_auth(None)

        assert user is None

    def test_optional_auth_with_invalid_token(self):
        """Test optional auth with invalid token"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid.token"
        )

        user = optional_auth(credentials)

        # Should return None instead of raising exception
        assert user is None

    def test_optional_auth_with_nonexistent_user(self):
        """Test optional auth when user doesn't exist"""
        token = create_access_token(data={"sub": "nonexistent", "user_id": "user_999"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=None):
            user = optional_auth(credentials)

        assert user is None

    def test_optional_auth_with_inactive_user(self):
        """Test optional auth with inactive user"""
        inactive_user = UserInDB(
            user_id="user_1",
            username="testuser",
            email="test@example.com",
            hashed_password="hashed_password",
            is_active=False,
            is_admin=False,
            created_at=datetime.utcnow(),
            last_login=None
        )

        token = create_access_token(data={"sub": "testuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=inactive_user):
            user = optional_auth(credentials)

        # Should return None for inactive user
        assert user is None

    def test_optional_auth_exception_handling(self):
        """Test that exceptions are caught and return None"""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="token"
        )

        with patch('app.auth_middleware.verify_token', side_effect=Exception("Unexpected error")):
            user = optional_auth(credentials)

        # Should not raise exception, just return None
        assert user is None


class TestAuthMiddlewareIntegration:
    """Integration tests for authentication middleware"""

    @pytest.mark.asyncio
    async def test_authentication_flow(self):
        """Test complete authentication flow"""
        # Create user
        mock_user = UserInDB(
            user_id="user_1",
            username="integrationtest",
            email="integration@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_admin=True,
            created_at=datetime.utcnow(),
            last_login=None
        )

        # Generate token
        token = create_access_token(data={"sub": "integrationtest", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=mock_user):
            with patch('app.auth_middleware.update_user_last_login'):
                # Get current user
                user = await get_current_user(credentials)
                assert user.username == "integrationtest"

                # Check active user
                active_user = await get_current_active_user(user)
                assert active_user.is_active is True

                # Check admin user
                admin_user = await get_current_admin_user(user)
                assert admin_user.is_admin is True

    @pytest.mark.asyncio
    async def test_non_admin_cannot_access_admin_endpoints(self):
        """Test that non-admin users can't access admin endpoints"""
        mock_user = UserInDB(
            user_id="user_1",
            username="regularuser",
            email="regular@example.com",
            hashed_password="hashed_password",
            is_active=True,
            is_admin=False,  # Not admin
            created_at=datetime.utcnow(),
            last_login=None
        )

        token = create_access_token(data={"sub": "regularuser", "user_id": "user_1"})
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        with patch('app.auth_middleware.get_user', return_value=mock_user):
            with patch('app.auth_middleware.update_user_last_login'):
                user = await get_current_user(credentials)

                # Should raise exception when trying to get admin user
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_admin_user(user)

                assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
