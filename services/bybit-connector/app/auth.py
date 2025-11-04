"""
Bybit Connector Service - Authentication Module
Purpose: Handle API authentication and signature generation for Bybit API
"""

import hmac
import hashlib
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from app.config import Settings
from app.exceptions import AuthenticationException


class BybitAuthenticator:
    """
    Handles authentication for Bybit API requests
    Implements HMAC-SHA256 signature generation as per Bybit API docs
    """
    
    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5000):
        """
        Initialize authenticator with API credentials
        
        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
            recv_window: Request validity window in milliseconds
        
        Raises:
            AuthenticationException: If credentials are invalid
        """
        # Validate credentials
        if not api_key or not api_secret:
            raise AuthenticationException(
                message="API key and secret are required",
                details={"api_key_provided": bool(api_key), "api_secret_provided": bool(api_secret)}
            )
        
        self.api_key = api_key
        self.api_secret = api_secret
        self.recv_window = recv_window
    
    def generate_signature(
        self,
        timestamp: int,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None
    ) -> str:
        """
        Generate HMAC-SHA256 signature for API request
        
        Bybit V5 signature format:
        HMAC_SHA256(api_secret, timestamp + api_key + recv_window + query_string)
        
        Args:
            timestamp: Unix timestamp in milliseconds
            params: Query parameters (for GET requests)
            body: Request body (for POST requests)
        
        Returns:
            Hexadecimal signature string
        
        Example:
            >>> auth = BybitAuthenticator("key", "secret")
            >>> sig = auth.generate_signature(1234567890000, {"symbol": "BTCUSDT"})
        """
        # Build parameter string
        if params:
            # Sort parameters alphabetically for consistent signature
            param_str = urlencode(sorted(params.items()))
        elif body:
            param_str = body
        else:
            param_str = ""
        
        # Construct signature payload
        # Format: timestamp + api_key + recv_window + param_str
        payload = f"{timestamp}{self.api_key}{self.recv_window}{param_str}"
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def get_headers(
        self,
        timestamp: Optional[int] = None,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Generate authentication headers for API request
        
        Args:
            timestamp: Unix timestamp in milliseconds (auto-generated if None)
            params: Query parameters (for GET requests)
            body: Request body (for POST requests)
        
        Returns:
            Dictionary of authentication headers
        
        Headers include:
            - X-BAPI-API-KEY: API key
            - X-BAPI-TIMESTAMP: Request timestamp
            - X-BAPI-SIGN: Request signature
            - X-BAPI-RECV-WINDOW: Receive window
            - Content-Type: application/json
        
        Example:
            >>> auth = BybitAuthenticator("key", "secret")
            >>> headers = auth.get_headers(params={"symbol": "BTCUSDT"})
        """
        # Generate timestamp if not provided
        if timestamp is None:
            timestamp = self._get_timestamp()
        
        # Generate signature
        signature = self.generate_signature(timestamp, params, body)
        
        # Build headers
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": str(timestamp),
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": str(self.recv_window),
            "Content-Type": "application/json"
        }
        
        return headers
    
    def verify_signature(
        self,
        signature: str,
        timestamp: int,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[str] = None
    ) -> bool:
        """
        Verify a signature is valid (useful for testing)
        
        Args:
            signature: Signature to verify
            timestamp: Timestamp used in signature
            params: Parameters used in signature
            body: Body used in signature
        
        Returns:
            True if signature is valid, False otherwise
        """
        expected_signature = self.generate_signature(timestamp, params, body)
        return signature == expected_signature
    
    @staticmethod
    def _get_timestamp() -> int:
        """
        Get current Unix timestamp in milliseconds
        
        Returns:
            Current timestamp in milliseconds
        """
        return int(time.time() * 1000)
    
    @staticmethod
    def validate_timestamp(timestamp: int, recv_window: int = 5000) -> bool:
        """
        Validate timestamp is within acceptable window
        
        Args:
            timestamp: Timestamp to validate (milliseconds)
            recv_window: Acceptable time window (milliseconds)
        
        Returns:
            True if timestamp is valid, False otherwise
        """
        current_time = int(time.time() * 1000)
        time_diff = abs(current_time - timestamp)
        return time_diff <= recv_window


class WebSocketAuthenticator:
    """
    Handles authentication for Bybit WebSocket connections
    WebSocket authentication uses similar signature but different format
    """
    
    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize WebSocket authenticator
        
        Args:
            api_key: Bybit API key
            api_secret: Bybit API secret
        """
        if not api_key or not api_secret:
            raise AuthenticationException(
                message="API key and secret required for WebSocket authentication"
            )
        
        self.api_key = api_key
        self.api_secret = api_secret
    
    def generate_auth_message(self, expires: Optional[int] = None) -> Dict[str, Any]:
        """
        Generate WebSocket authentication message
        
        Args:
            expires: Expiration timestamp (default: current time + 10 seconds)
        
        Returns:
            Authentication message dict to send over WebSocket
        
        Format:
            {
                "op": "auth",
                "args": [api_key, expires, signature]
            }
        """
        # Generate expiration timestamp (10 seconds from now if not provided)
        if expires is None:
            expires = int(time.time() * 1000) + 10000
        
        # Generate signature: HMAC_SHA256(api_secret, "GET/realtime" + expires)
        signature_payload = f"GET/realtime{expires}"
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            signature_payload.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Build authentication message
        auth_message = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }
        
        return auth_message
    
    def generate_subscription_message(self, channel: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate WebSocket subscription message
        
        Args:
            channel: Channel to subscribe to (e.g., "orderbook", "trade", "ticker")
            symbol: Trading symbol (e.g., "BTCUSDT")
        
        Returns:
            Subscription message dict
        
        Example:
            >>> auth = WebSocketAuthenticator("key", "secret")
            >>> msg = auth.generate_subscription_message("ticker", "BTCUSDT")
            {"op": "subscribe", "args": ["tickers.BTCUSDT"]}
        """
        # Build topic string
        if symbol:
            topic = f"{channel}.{symbol}"
        else:
            topic = channel
        
        # Build subscription message
        sub_message = {
            "op": "subscribe",
            "args": [topic]
        }
        
        return sub_message
    
    def generate_unsubscribe_message(self, channel: str, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate WebSocket unsubscribe message
        
        Args:
            channel: Channel to unsubscribe from
            symbol: Trading symbol
        
        Returns:
            Unsubscribe message dict
        """
        # Build topic string
        if symbol:
            topic = f"{channel}.{symbol}"
        else:
            topic = channel
        
        # Build unsubscribe message
        unsub_message = {
            "op": "unsubscribe",
            "args": [topic]
        }
        
        return unsub_message


# Factory functions for convenience
def create_authenticator(settings: Settings) -> BybitAuthenticator:
    """
    Create BybitAuthenticator from settings
    
    Args:
        settings: Application settings
    
    Returns:
        Configured BybitAuthenticator instance
    """
    return BybitAuthenticator(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret,
        recv_window=settings.bybit_recv_window
    )


def create_ws_authenticator(settings: Settings) -> WebSocketAuthenticator:
    """
    Create WebSocketAuthenticator from settings
    
    Args:
        settings: Application settings
    
    Returns:
        Configured WebSocketAuthenticator instance
    """
    return WebSocketAuthenticator(
        api_key=settings.bybit_api_key,
        api_secret=settings.bybit_api_secret
    )
