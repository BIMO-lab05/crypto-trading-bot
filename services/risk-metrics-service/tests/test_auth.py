"""
Unit tests for Authentication - API key authentication for admin endpoints
Tests authentication verification, error handling, and security
"""

import pytest
from fastapi import HTTPException
from app.auth import verify_admin_key
from app.config import settings


@pytest.mark.unit
@pytest.mark.auth
class TestAdminAuthentication:
    """Tests for admin API key authentication"""

    async def test_verify_admin_key_valid(self):
        """Test that valid API key is accepted"""
        valid_key = settings.admin_api_key

        # Should not raise exception
        result = await verify_admin_key(valid_key)
        assert result == valid_key

    async def test_verify_admin_key_invalid(self):
        """Test that invalid API key is rejected"""
        invalid_key = "invalid-key-12345"

        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_key(invalid_key)

        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()

    async def test_verify_admin_key_missing(self):
        """Test that missing API key is rejected"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_key(None)

        assert exc_info.value.status_code == 401
        assert "required" in exc_info.value.detail.lower()

    async def test_verify_admin_key_empty_string(self):
        """Test that empty string API key is rejected"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_admin_key("")

        assert exc_info.value.status_code == 403

    async def test_verify_admin_key_case_sensitive(self):
        """Test that API key validation is case-sensitive"""
        # Try uppercase version of valid key
        invalid_key = settings.admin_api_key.upper()

        # Should only pass if keys actually match
        if invalid_key != settings.admin_api_key:
            with pytest.raises(HTTPException):
                await verify_admin_key(invalid_key)

    async def test_verify_admin_key_whitespace(self):
        """Test that API key with extra whitespace is rejected"""
        key_with_whitespace = f" {settings.admin_api_key} "

        with pytest.raises(HTTPException):
            await verify_admin_key(key_with_whitespace)

    async def test_verify_admin_key_partial_match(self):
        """Test that partial key match is rejected"""
        partial_key = settings.admin_api_key[:10]  # Only first 10 chars

        with pytest.raises(HTTPException):
            await verify_admin_key(partial_key)
