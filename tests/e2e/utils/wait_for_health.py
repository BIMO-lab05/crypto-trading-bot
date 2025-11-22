#!/usr/bin/env python3
"""
Health Check Utilities for E2E Testing

Utilities to wait for services to become healthy before running tests.
"""

import asyncio
import httpx
import time
from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class ServiceConfig:
    """Configuration for a service."""
    name: str
    port: int
    health_endpoint: str = "/health"
    timeout: int = 60  # seconds


# Service configurations
SERVICES = {
    "api-gateway": ServiceConfig("API Gateway", 8000),
    "bybit-connector": ServiceConfig("Bybit Connector", 8002),
    "market-data": ServiceConfig("Market Data Service", 8003),
    "technical-analysis": ServiceConfig("Technical Analysis", 8004),
    "trading-engine": ServiceConfig("Trading Engine", 8005),
    "portfolio-manager": ServiceConfig("Portfolio Manager", 8006),
    "ml-prediction": ServiceConfig("ML Prediction Service", 8007),
    "sentiment-analysis": ServiceConfig("Sentiment Analysis", 8008),
}


async def wait_for_service_health(
    service_name: str,
    port: Optional[int] = None,
    timeout: int = 60,
    check_interval: float = 1.0,
    base_url: str = "http://localhost"
) -> bool:
    """
    Wait for a service to become healthy.

    Args:
        service_name: Name of the service
        port: Port number (optional, will lookup from SERVICES if not provided)
        timeout: Maximum time to wait in seconds
        check_interval: Time between health checks in seconds
        base_url: Base URL for the service

    Returns:
        True if service became healthy, False if timeout

    Raises:
        ValueError: If service_name not found and port not provided
    """
    # Get service config
    if port is None:
        if service_name not in SERVICES:
            raise ValueError(f"Unknown service: {service_name}. Provide port explicitly.")
        service_config = SERVICES[service_name]
        port = service_config.port
        health_endpoint = service_config.health_endpoint
    else:
        health_endpoint = "/health"

    url = f"{base_url}:{port}{health_endpoint}"
    start_time = time.time()
    attempt = 0

    print(f"Waiting for {service_name} at {url} to become healthy...")

    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            attempt += 1
            elapsed = time.time() - start_time

            if elapsed >= timeout:
                print(f"❌ Timeout waiting for {service_name} (>{timeout}s)")
                return False

            try:
                response = await client.get(url)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        status = data.get("status", "unknown")

                        if status == "healthy":
                            print(f"✅ {service_name} is healthy (attempt {attempt}, {elapsed:.1f}s)")
                            return True
                        else:
                            print(f"⏳ {service_name} status: {status} (attempt {attempt})")
                    except Exception:
                        # Health endpoint might not return JSON
                        print(f"✅ {service_name} is responding (attempt {attempt}, {elapsed:.1f}s)")
                        return True
                else:
                    print(f"⏳ {service_name} returned {response.status_code} (attempt {attempt})")

            except httpx.ConnectError:
                if attempt == 1 or attempt % 10 == 0:  # Print every 10th attempt to reduce spam
                    print(f"⏳ {service_name} not reachable (attempt {attempt}, {elapsed:.1f}s)")

            except Exception as e:
                if attempt == 1 or attempt % 10 == 0:
                    print(f"⚠️  {service_name} error: {e} (attempt {attempt})")

            # Wait before next check
            await asyncio.sleep(check_interval)


async def wait_for_all_services(
    services: Optional[List[str]] = None,
    timeout: int = 120,
    fail_fast: bool = False
) -> Dict[str, bool]:
    """
    Wait for multiple services to become healthy.

    Args:
        services: List of service names (default: all services)
        timeout: Maximum time to wait for each service
        fail_fast: If True, stop waiting if any service fails

    Returns:
        Dictionary mapping service name to health status (True/False)
    """
    if services is None:
        services = list(SERVICES.keys())

    print(f"\n{'='*60}")
    print(f"Waiting for {len(services)} services to become healthy...")
    print(f"{'='*60}\n")

    results = {}

    # Wait for services concurrently
    tasks = [
        wait_for_service_health(service, timeout=timeout)
        for service in services
    ]

    service_results = await asyncio.gather(*tasks, return_exceptions=True)

    for service, result in zip(services, service_results):
        if isinstance(result, Exception):
            print(f"❌ {service} failed with error: {result}")
            results[service] = False
        else:
            results[service] = result

        if fail_fast and not result:
            print(f"\n⚠️  Failing fast due to {service} failure")
            break

    # Summary
    healthy_count = sum(1 for status in results.values() if status)
    total_count = len(results)

    print(f"\n{'='*60}")
    print(f"Service Health Summary: {healthy_count}/{total_count} healthy")
    print(f"{'='*60}")

    for service, is_healthy in results.items():
        status_icon = "✅" if is_healthy else "❌"
        print(f"  {status_icon} {service}")

    print()

    return results


async def wait_with_retry(
    service_name: str,
    port: int,
    max_retries: int = 3,
    retry_delay: int = 5
) -> bool:
    """
    Wait for service with retry logic.

    Args:
        service_name: Name of the service
        port: Port number
        max_retries: Maximum number of retry attempts
        retry_delay: Delay between retries in seconds

    Returns:
        True if service became healthy, False otherwise
    """
    for attempt in range(1, max_retries + 1):
        print(f"\n📍 Attempt {attempt}/{max_retries} for {service_name}")

        is_healthy = await wait_for_service_health(
            service_name=service_name,
            port=port,
            timeout=30
        )

        if is_healthy:
            return True

        if attempt < max_retries:
            print(f"⏱️  Waiting {retry_delay}s before retry...")
            await asyncio.sleep(retry_delay)

    print(f"\n❌ Failed to start {service_name} after {max_retries} attempts")
    return False


def check_service_health_sync(port: int, base_url: str = "http://localhost") -> bool:
    """
    Synchronous version of health check (for use in non-async contexts).

    Args:
        port: Port number
        base_url: Base URL

    Returns:
        True if healthy, False otherwise
    """
    import requests

    try:
        response = requests.get(f"{base_url}:{port}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("status") == "healthy"
    except Exception:
        pass

    return False


async def poll_until(
    condition_func,
    timeout: int = 30,
    interval: float = 0.5,
    error_message: str = "Condition not met within timeout"
) -> bool:
    """
    Poll until a condition function returns True.

    Args:
        condition_func: Async function that returns bool
        timeout: Maximum time to wait
        interval: Time between checks
        error_message: Error message if timeout

    Returns:
        True if condition met, False if timeout

    Example:
        async def check_position_exists():
            positions = await portfolio_client.get_positions()
            return len(positions) > 0

        success = await poll_until(check_position_exists, timeout=10)
    """
    start_time = time.time()

    while True:
        if await condition_func():
            return True

        elapsed = time.time() - start_time
        if elapsed >= timeout:
            print(f"⚠️  {error_message} ({elapsed:.1f}s)")
            return False

        await asyncio.sleep(interval)


if __name__ == "__main__":
    """Test health check utilities."""
    import sys

    async def main():
        if len(sys.argv) > 1:
            # Check specific service
            service = sys.argv[1]
            port = int(sys.argv[2]) if len(sys.argv) > 2 else None

            result = await wait_for_service_health(service, port=port)
            sys.exit(0 if result else 1)
        else:
            # Check all services
            results = await wait_for_all_services()
            all_healthy = all(results.values())
            sys.exit(0 if all_healthy else 1)

    asyncio.run(main())
