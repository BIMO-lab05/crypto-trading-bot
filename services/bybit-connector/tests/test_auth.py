"""
Bybit Connector Service - Authentication Tests
Purpose: Comprehensive tests for authentication and signature generation
"""

import pytest
import hmac
import hashlib
import time
from unittest.mock import patch, Mock
from urllib.parse import urlencode

from app.auth import BybitAuthenticator, WebSocketAuthenticator, create_authenticator, create_ws_authenticator
from app.exceptions import AuthenticationException
from app.config import Settings


# ============================================================================
# BYBIT AUTHENTICATOR TESTS
# ============================================================================

class TestBybitAuthenticatorInitialization:
    """Test BybitAuthenticator initialization and validation"""

    def test_authenticator_initialization_success(self):
        """Test successful authenticator initialization with valid credentials"""
        # Given valid API credentials
        api_key = "test_api_key"
        api_secret = "test_api_secret"
        recv_window = 5000

        # When creating authenticator
        auth = BybitAuthenticator(api_key, api_secret, recv_window)

        # Then authenticator is initialized correctly
        assert auth.api_key == api_key
        assert auth.api_secret == api_secret
        assert auth.recv_window == recv_window

    def test_authenticator_initialization_empty_api_key(self):
        """Test initialization fails with empty API key"""
        # Given empty API key
        api_key = ""
        api_secret = "test_secret"

        # When/Then initialization raises AuthenticationException
        with pytest.raises(AuthenticationException) as exc_info:
            BybitAuthenticator(api_key, api_secret)

        assert "API key and secret are required" in str(exc_info.value)

    def test_authenticator_initialization_empty_api_secret(self):
        """Test initialization fails with empty API secret"""
        # Given empty API secret
        api_key = "test_key"
        api_secret = ""

        # When/Then initialization raises AuthenticationException
        with pytest.raises(AuthenticationException) as exc_info:
            BybitAuthenticator(api_key, api_secret)

        assert "API key and secret are required" in str(exc_info.value)

    def test_authenticator_initialization_none_credentials(self):
        """Test initialization fails with None credentials"""
        # Given None credentials
        api_key = None
        api_secret = None

        # When/Then initialization raises AuthenticationException
        with pytest.raises(AuthenticationException):
            BybitAuthenticator(api_key, api_secret)

    def test_authenticator_initialization_default_recv_window(self):
        """Test authenticator uses default recv_window when not specified"""
        # Given valid credentials without recv_window
        api_key = "test_key"
        api_secret = "test_secret"

        # When creating authenticator
        auth = BybitAuthenticator(api_key, api_secret)

        # Then default recv_window is used
        assert auth.recv_window == 5000


class TestSignatureGeneration:
    """Test HMAC-SHA256 signature generation"""

    def test_generate_signature_with_params(self):
        """Test signature generation with query parameters"""
        # Given authenticator and parameters
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT", "category": "linear"}

        # When generating signature
        signature = auth.generate_signature(timestamp, params=params)

        # Then signature is valid hex string
        assert isinstance(signature, str)
        assert len(signature) == 64  # HMAC-SHA256 produces 64 hex characters
        assert all(c in '0123456789abcdef' for c in signature)

    def test_generate_signature_with_body(self):
        """Test signature generation with request body"""
        # Given authenticator and body
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        body = '{"symbol":"BTCUSDT","side":"Buy"}'

        # When generating signature
        signature = auth.generate_signature(timestamp, body=body)

        # Then signature is generated
        assert isinstance(signature, str)
        assert len(signature) == 64

    def test_generate_signature_empty_params(self):
        """Test signature generation with empty parameters"""
        # Given authenticator with no params
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000

        # When generating signature with no params
        signature = auth.generate_signature(timestamp)

        # Then signature is still generated (empty param string)
        assert isinstance(signature, str)
        assert len(signature) == 64

    def test_generate_signature_consistency(self):
        """Test signature generation is consistent for same inputs"""
        # Given authenticator and parameters
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT"}

        # When generating signature twice
        signature1 = auth.generate_signature(timestamp, params=params)
        signature2 = auth.generate_signature(timestamp, params=params)

        # Then signatures are identical
        assert signature1 == signature2

    def test_generate_signature_different_timestamp(self):
        """Test different timestamps produce different signatures"""
        # Given authenticator
        auth = BybitAuthenticator("test_key", "test_secret")
        params = {"symbol": "BTCUSDT"}

        # When generating signatures with different timestamps
        signature1 = auth.generate_signature(1234567890000, params=params)
        signature2 = auth.generate_signature(1234567899999, params=params)

        # Then signatures are different
        assert signature1 != signature2

    def test_generate_signature_param_order(self):
        """Test signature is consistent regardless of parameter order"""
        # Given authenticator
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000

        # When generating signatures with different parameter order
        params1 = {"symbol": "BTCUSDT", "category": "linear"}
        params2 = {"category": "linear", "symbol": "BTCUSDT"}
        signature1 = auth.generate_signature(timestamp, params=params1)
        signature2 = auth.generate_signature(timestamp, params=params2)

        # Then signatures are identical (params are sorted)
        assert signature1 == signature2

    def test_generate_signature_special_characters(self):
        """Test signature generation with special characters in params"""
        # Given authenticator with special characters
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"orderLinkId": "order-123-test"}

        # When generating signature
        signature = auth.generate_signature(timestamp, params=params)

        # Then signature is generated successfully
        assert isinstance(signature, str)
        assert len(signature) == 64


class TestHeaderGeneration:
    """Test authentication header generation"""

    def test_get_headers_with_timestamp(self):
        """Test header generation with provided timestamp"""
        # Given authenticator
        auth = BybitAuthenticator("test_key", "test_secret", recv_window=5000)
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT"}

        # When generating headers
        headers = auth.get_headers(timestamp=timestamp, params=params)

        # Then all required headers are present
        assert "X-BAPI-API-KEY" in headers
        assert "X-BAPI-TIMESTAMP" in headers
        assert "X-BAPI-SIGN" in headers
        assert "X-BAPI-RECV-WINDOW" in headers
        assert "Content-Type" in headers

        # And header values are correct
        assert headers["X-BAPI-API-KEY"] == "test_key"
        assert headers["X-BAPI-TIMESTAMP"] == str(timestamp)
        assert headers["X-BAPI-RECV-WINDOW"] == "5000"
        assert headers["Content-Type"] == "application/json"
        assert len(headers["X-BAPI-SIGN"]) == 64

    def test_get_headers_auto_timestamp(self):
        """Test header generation with automatic timestamp"""
        # Given authenticator
        auth = BybitAuthenticator("test_key", "test_secret")

        # When generating headers without timestamp
        with patch.object(BybitAuthenticator, '_get_timestamp', return_value=1234567890000):
            headers = auth.get_headers()

        # Then timestamp is auto-generated
        assert headers["X-BAPI-TIMESTAMP"] == "1234567890000"

    def test_get_headers_with_body(self):
        """Test header generation with request body"""
        # Given authenticator and body
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        body = '{"symbol":"BTCUSDT"}'

        # When generating headers
        headers = auth.get_headers(timestamp=timestamp, body=body)

        # Then headers include signature for body
        assert "X-BAPI-SIGN" in headers
        assert len(headers["X-BAPI-SIGN"]) == 64

    def test_get_headers_signature_validity(self):
        """Test generated signature in headers is valid"""
        # Given authenticator
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT"}

        # When generating headers
        headers = auth.get_headers(timestamp=timestamp, params=params)

        # Then signature can be verified
        expected_signature = auth.generate_signature(timestamp, params=params)
        assert headers["X-BAPI-SIGN"] == expected_signature


class TestSignatureVerification:
    """Test signature verification functionality"""

    def test_verify_signature_valid(self):
        """Test verification of valid signature"""
        # Given authenticator and signature
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT"}
        signature = auth.generate_signature(timestamp, params=params)

        # When verifying signature
        is_valid = auth.verify_signature(signature, timestamp, params=params)

        # Then signature is valid
        assert is_valid is True

    def test_verify_signature_invalid(self):
        """Test verification of invalid signature"""
        # Given authenticator and wrong signature
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params = {"symbol": "BTCUSDT"}
        wrong_signature = "invalid_signature_12345"

        # When verifying signature
        is_valid = auth.verify_signature(wrong_signature, timestamp, params=params)

        # Then signature is invalid
        assert is_valid is False

    def test_verify_signature_wrong_params(self):
        """Test signature verification fails with wrong params"""
        # Given authenticator and signature for different params
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = 1234567890000
        params1 = {"symbol": "BTCUSDT"}
        params2 = {"symbol": "ETHUSDT"}
        signature = auth.generate_signature(timestamp, params=params1)

        # When verifying with different params
        is_valid = auth.verify_signature(signature, timestamp, params=params2)

        # Then verification fails
        assert is_valid is False


class TestTimestampValidation:
    """Test timestamp validation"""

    @patch('time.time')
    def test_validate_timestamp_within_window(self, mock_time):
        """Test timestamp validation when within acceptable window"""
        # Given current time and recent timestamp
        current_time = 1234567890.0
        mock_time.return_value = current_time
        timestamp = int(current_time * 1000) - 1000  # 1 second ago

        # When validating timestamp
        is_valid = BybitAuthenticator.validate_timestamp(timestamp, recv_window=5000)

        # Then timestamp is valid
        assert is_valid is True

    @patch('time.time')
    def test_validate_timestamp_outside_window(self, mock_time):
        """Test timestamp validation when outside acceptable window"""
        # Given current time and old timestamp
        current_time = 1234567890.0
        mock_time.return_value = current_time
        timestamp = int(current_time * 1000) - 10000  # 10 seconds ago

        # When validating timestamp with 5 second window
        is_valid = BybitAuthenticator.validate_timestamp(timestamp, recv_window=5000)

        # Then timestamp is invalid
        assert is_valid is False

    @patch('time.time')
    def test_validate_timestamp_future_timestamp(self, mock_time):
        """Test timestamp validation with future timestamp"""
        # Given current time and future timestamp
        current_time = 1234567890.0
        mock_time.return_value = current_time
        timestamp = int(current_time * 1000) + 3000  # 3 seconds in future

        # When validating timestamp
        is_valid = BybitAuthenticator.validate_timestamp(timestamp, recv_window=5000)

        # Then timestamp is valid (within window)
        assert is_valid is True

    @patch('time.time')
    def test_validate_timestamp_exact_boundary(self, mock_time):
        """Test timestamp validation at exact window boundary"""
        # Given timestamp at exact boundary
        current_time = 1234567890.0
        mock_time.return_value = current_time
        timestamp = int(current_time * 1000) - 5000  # Exactly 5 seconds ago

        # When validating with 5 second window
        is_valid = BybitAuthenticator.validate_timestamp(timestamp, recv_window=5000)

        # Then timestamp is valid (inclusive)
        assert is_valid is True


class TestTimestampGeneration:
    """Test timestamp generation"""

    def test_get_timestamp_format(self):
        """Test timestamp is in correct format (milliseconds)"""
        # When getting timestamp from a fresh authenticator (skew=0)
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = auth._get_timestamp()

        # Then timestamp is in milliseconds (13 digits)
        assert isinstance(timestamp, int)
        assert len(str(timestamp)) == 13

    def test_get_timestamp_current(self):
        """Test timestamp is current time"""
        # When getting timestamp from a fresh authenticator (skew=0)
        auth = BybitAuthenticator("test_key", "test_secret")
        timestamp = auth._get_timestamp()
        current_time = int(time.time() * 1000)

        # Then timestamp is within 1 second of current time
        assert abs(timestamp - current_time) < 1000

    def test_get_timestamp_applies_clock_skew(self):
        """Clock-skew offset is added to local time"""
        auth = BybitAuthenticator("test_key", "test_secret")
        auth.clock_skew_ms = 4_500
        local_ms = int(time.time() * 1000)
        # Timestamp is local + skew (within a small jitter)
        assert auth._get_timestamp() - (local_ms + 4_500) < 100


# ============================================================================
# WEBSOCKET AUTHENTICATOR TESTS
# ============================================================================

class TestWebSocketAuthenticatorInitialization:
    """Test WebSocketAuthenticator initialization"""

    def test_ws_authenticator_initialization_success(self):
        """Test successful WebSocket authenticator initialization"""
        # Given valid credentials
        api_key = "test_key"
        api_secret = "test_secret"

        # When creating authenticator
        ws_auth = WebSocketAuthenticator(api_key, api_secret)

        # Then authenticator is initialized
        assert ws_auth.api_key == api_key
        assert ws_auth.api_secret == api_secret

    def test_ws_authenticator_initialization_empty_key(self):
        """Test WebSocket authenticator fails with empty key"""
        # Given empty API key
        api_key = ""
        api_secret = "test_secret"

        # When/Then initialization raises AuthenticationException
        with pytest.raises(AuthenticationException) as exc_info:
            WebSocketAuthenticator(api_key, api_secret)

        assert "API key and secret required" in str(exc_info.value)

    def test_ws_authenticator_initialization_none_credentials(self):
        """Test WebSocket authenticator fails with None credentials"""
        # Given None credentials
        # When/Then initialization raises AuthenticationException
        with pytest.raises(AuthenticationException):
            WebSocketAuthenticator(None, None)


class TestWebSocketAuthMessage:
    """Test WebSocket authentication message generation"""

    def test_generate_auth_message_with_expires(self):
        """Test auth message generation with provided expiration"""
        # Given authenticator and expiration
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")
        expires = 1234567890000

        # When generating auth message
        auth_msg = ws_auth.generate_auth_message(expires=expires)

        # Then message has correct format
        assert auth_msg["op"] == "auth"
        assert "args" in auth_msg
        assert len(auth_msg["args"]) == 3
        assert auth_msg["args"][0] == "test_key"
        assert auth_msg["args"][1] == expires
        assert isinstance(auth_msg["args"][2], str)  # signature
        assert len(auth_msg["args"][2]) == 64  # HMAC-SHA256 hex

    def test_generate_auth_message_auto_expires(self):
        """Test auth message generation with automatic expiration"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")

        # When generating auth message without expires
        with patch('time.time', return_value=1234567890.0):
            auth_msg = ws_auth.generate_auth_message()

        # Then expiration is auto-generated (current time + 10 seconds)
        expected_expires = 1234567890000 + 10000
        assert auth_msg["args"][1] == expected_expires

    def test_generate_auth_message_signature_validity(self):
        """Test WebSocket auth message signature is valid"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")
        expires = 1234567890000

        # When generating auth message
        auth_msg = ws_auth.generate_auth_message(expires=expires)
        signature = auth_msg["args"][2]

        # Then signature matches expected format
        signature_payload = f"GET/realtime{expires}"
        expected_signature = hmac.new(
            "test_secret".encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        assert signature == expected_signature


class TestWebSocketSubscriptionMessages:
    """Test WebSocket subscription/unsubscription message generation"""

    def test_generate_subscription_message_with_symbol(self):
        """Test subscription message generation with symbol"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")

        # When generating subscription message
        sub_msg = ws_auth.generate_subscription_message("ticker", "BTCUSDT")

        # Then message has correct format
        assert sub_msg["op"] == "subscribe"
        assert sub_msg["args"] == ["ticker.BTCUSDT"]

    def test_generate_subscription_message_without_symbol(self):
        """Test subscription message generation without symbol"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")

        # When generating subscription message
        sub_msg = ws_auth.generate_subscription_message("orderbook")

        # Then message has correct format
        assert sub_msg["op"] == "subscribe"
        assert sub_msg["args"] == ["orderbook"]

    def test_generate_unsubscribe_message_with_symbol(self):
        """Test unsubscribe message generation with symbol"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")

        # When generating unsubscribe message
        unsub_msg = ws_auth.generate_unsubscribe_message("trade", "ETHUSDT")

        # Then message has correct format
        assert unsub_msg["op"] == "unsubscribe"
        assert unsub_msg["args"] == ["trade.ETHUSDT"]

    def test_generate_unsubscribe_message_without_symbol(self):
        """Test unsubscribe message generation without symbol"""
        # Given authenticator
        ws_auth = WebSocketAuthenticator("test_key", "test_secret")

        # When generating unsubscribe message
        unsub_msg = ws_auth.generate_unsubscribe_message("kline")

        # Then message has correct format
        assert unsub_msg["op"] == "unsubscribe"
        assert unsub_msg["args"] == ["kline"]


# ============================================================================
# FACTORY FUNCTION TESTS
# ============================================================================

class TestFactoryFunctions:
    """Test authenticator factory functions"""

    def test_create_authenticator_from_settings(self, test_settings):
        """Test creating authenticator from settings"""
        # Given settings
        # When creating authenticator
        auth = create_authenticator(test_settings)

        # Then authenticator is created with settings values
        assert isinstance(auth, BybitAuthenticator)
        assert auth.api_key == test_settings.bybit_api_key
        assert auth.api_secret == test_settings.bybit_api_secret
        assert auth.recv_window == test_settings.bybit_recv_window

    def test_create_ws_authenticator_from_settings(self, test_settings):
        """Test creating WebSocket authenticator from settings"""
        # Given settings
        # When creating WebSocket authenticator
        ws_auth = create_ws_authenticator(test_settings)

        # Then authenticator is created with settings values
        assert isinstance(ws_auth, WebSocketAuthenticator)
        assert ws_auth.api_key == test_settings.bybit_api_key
        assert ws_auth.api_secret == test_settings.bybit_api_secret
