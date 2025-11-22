"""
Market Data Service - Circuit Breaker
Purpose: Resilience patterns for external service calls
"""

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
import httpx
import logging

logger = logging.getLogger(__name__)

# Circuit breaker decorator for Bybit Connector calls
bybit_connector_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    before_sleep=lambda retry_state: logger.warning(
        f"Retrying Bybit Connector call (attempt {retry_state.attempt_number})"
    ),
)
