"""
Bybit Connector Service - Authentication Module
Purpose: Handle API authentication and signature generation for Bybit API
"""

import hmac
import hashlib
import logging
import time
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from app.config import Settings
from app.exceptions import AuthenticationException

logger = logging.getLogger(__name__)


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
        # Offset (milliseconds) added to local time before signing requests so
        # we stay within Bybit's recv-window when the host clock has drifted.
        # Populated by sync_clock(); zero by default.
        self.clock_skew_ms: int = 0

    async def sync_clock(self, http_client, base_url: str) -> None:
        """
        Query Bybit's server time and store the skew vs. local time.

        Bybit rejects requests whose timestamp is outside ``recv_window`` from
        their server's clock with retCode=10004. On a host with drifted time
        every signed request fails. This calculates the offset once at
        startup so subsequent ``_get_timestamp()`` calls compensate.

        Args:
            http_client: An ``httpx.AsyncClient`` (or compatible) to issue the
                probe with. Reusing the client owned by ``BybitRestClient``
                avoids opening a second connection pool.
            base_url: REST base URL (testnet or mainnet); used only when the
                supplied client has no base_url configured.
        """
        try:
            # /v5/market/time is public and unauthenticated.
            response = await http_client.get(f"{base_url}/v5/market/time")
            response.raise_for_status()
            payload = response.json()
            server_ms = int(payload.get("result", {}).get("timeNano", 0)) // 1_000_000
            if server_ms == 0:
                # older field name on some response shapes
                server_ms = int(payload.get("time", 0))
            if server_ms == 0:
                logger.warning("clock-sync: server time missing from response, leaving skew=0")
                return
            local_ms = int(time.time() * 1000)
            self.clock_skew_ms = server_ms - local_ms
            logger.info(
                "clock-sync: applied skew",
                extra={"clock_skew_ms": self.clock_skew_ms},
            )
        except Exception as exc:
            logger.warning(f"clock-sync failed, leaving skew=0: {exc}")
    
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
    
    def _get_timestamp(self) -> int:
        """
        Get current Unix timestamp in milliseconds, adjusted by any
        previously-measured clock skew against Bybit's server time.

        Returns:
            Current timestamp in milliseconds
        """
        return int(time.time() * 1000) + self.clock_skew_ms
    
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
