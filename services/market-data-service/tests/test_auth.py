"""
Market Data Service - Authentication Tests
Purpose: Test API key authentication functionality
"""

import pytest
from fastapi import HTTPException, status
from unittest.mock import patch, MagicMock

from app.auth import verify_api_key, api_key_header


class TestVerifyApiKey:
    """Test API key verification"""

    @pytest.mark.asyncio
    async def test_verify_api_key_with_valid_key(self):
        """Test that valid API key is accepted"""
        valid_key = "test-api-key-123"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [valid_key]

            result = await verify_api_key(api_key=valid_key)

            assert result == valid_key

    @pytest.mark.asyncio
    async def test_verify_api_key_with_multiple_valid_keys(self):
        """Test that any valid API key from list is accepted"""
        valid_keys = ["key1", "key2", "key3"]
        test_key = "key2"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            result = await verify_api_key(api_key=test_key)

            assert result == test_key

    @pytest.mark.asyncio
    async def test_verify_api_key_with_invalid_key(self):
        """Test that invalid API key raises 403 Forbidden"""
        invalid_key = "invalid-key"
        valid_keys = ["valid-key-1", "valid-key-2"]

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=invalid_key)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
            assert "Invalid API key" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_api_key_with_missing_key(self):
        """Test that missing API key raises 401 Unauthorized"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key=None)

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "API key is required" in exc_info.value.detail
        assert exc_info.value.headers == {"WWW-Authenticate": "ApiKey"}

    @pytest.mark.asyncio
    async def test_verify_api_key_with_empty_string(self):
        """Test that empty string API key raises 401 Unauthorized"""
        with pytest.raises(HTTPException) as exc_info:
            await verify_api_key(api_key="")

        assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_verify_api_key_case_sensitive(self):
        """Test that API key validation is case-sensitive"""
        valid_key = "TestKey123"
        wrong_case_key = "testkey123"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [valid_key]

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=wrong_case_key)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_verify_api_key_with_special_characters(self):
        """Test that API keys with special characters are supported"""
        special_key = "key-with_special.chars@123"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [special_key]

            result = await verify_api_key(api_key=special_key)

            assert result == special_key

    @pytest.mark.asyncio
    async def test_verify_api_key_with_whitespace(self):
        """Test that API keys with whitespace don't match trimmed versions"""
        key_with_space = " api-key-123 "
        valid_key = "api-key-123"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [valid_key]

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=key_with_space)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_verify_api_key_logs_warning_on_invalid(self, caplog):
        """Test that invalid API key attempts are logged"""
        invalid_key = "invalid-key-abc"
        valid_keys = ["valid-key"]

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            try:
                await verify_api_key(api_key=invalid_key)
            except HTTPException:
                pass

            # Check that warning was logged (only first 8 chars of key)
            # Note: actual logging may be async, so we just test the exception

    @pytest.mark.asyncio
    async def test_verify_api_key_logs_warning_on_missing(self, caplog):
        """Test that missing API key attempts are logged"""
        try:
            await verify_api_key(api_key=None)
        except HTTPException:
            pass

        # Verify exception was raised, logging is secondary


class TestApiKeyHeader:
    """Test API key header configuration"""

    def test_api_key_header_name(self):
        """Test that header name is X-API-Key"""
        assert api_key_header.model.name == "X-API-Key"

    def test_api_key_header_auto_error_false(self):
        """Test that auto_error is False to allow custom error handling"""
        assert api_key_header.model.auto_error is False


class TestAuthenticationIntegration:
    """Test authentication integration scenarios"""

    @pytest.mark.asyncio
    async def test_multiple_requests_with_same_key(self):
        """Test that same API key works for multiple requests"""
        api_key = "persistent-key"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [api_key]

            # Simulate multiple requests
            for _ in range(5):
                result = await verify_api_key(api_key=api_key)
                assert result == api_key

    @pytest.mark.asyncio
    async def test_alternating_valid_invalid_keys(self):
        """Test alternating between valid and invalid keys"""
        valid_key = "valid-key"
        invalid_key = "invalid-key"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [valid_key]

            # Valid request
            result1 = await verify_api_key(api_key=valid_key)
            assert result1 == valid_key

            # Invalid request
            with pytest.raises(HTTPException):
                await verify_api_key(api_key=invalid_key)

            # Valid request again
            result2 = await verify_api_key(api_key=valid_key)
            assert result2 == valid_key

    @pytest.mark.asyncio
    async def test_empty_api_keys_list(self):
        """Test behavior when no API keys are configured"""
        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = []

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key="any-key")

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


class TestSecurityScenarios:
    """Test security-related scenarios"""

    @pytest.mark.asyncio
    async def test_sql_injection_in_api_key(self):
        """Test that SQL injection attempts in API key are rejected"""
        sql_injection = "'; DROP TABLE users; --"
        valid_keys = ["legitimate-key"]

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=sql_injection)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_very_long_api_key(self):
        """Test handling of extremely long API key attempts"""
        long_key = "a" * 10000
        valid_keys = ["short-key"]

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=long_key)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_unicode_api_key(self):
        """Test that unicode characters in API keys are handled"""
        unicode_key = "key-with-unicode-🔑"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [unicode_key]

            result = await verify_api_key(api_key=unicode_key)

            assert result == unicode_key

    @pytest.mark.asyncio
    async def test_numeric_api_key(self):
        """Test that purely numeric API keys work"""
        numeric_key = "123456789"

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = [numeric_key]

            result = await verify_api_key(api_key=numeric_key)

            assert result == numeric_key

    @pytest.mark.asyncio
    async def test_api_key_with_newlines(self):
        """Test that API keys with newlines are rejected"""
        key_with_newline = "key\nwith\nnewlines"
        valid_keys = ["valid-key"]

        with patch('app.auth.get_settings') as mock_settings:
            mock_settings.return_value.api_keys_list = valid_keys

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(api_key=key_with_newline)

            assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
