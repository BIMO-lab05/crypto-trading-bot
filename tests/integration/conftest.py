"""
Integration Test Configuration
Shared fixtures and utilities for integration tests
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Dict

import httpx
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def services_config() -> Dict[str, str]:
    """Service URLs configuration. Ports per crypto-trading-bot/CLAUDE.md and bootstrap.sh:67-78.
    Phase 2 fix: prior version inverted bybit_connector (8001) and trading_engine (8005).
    """
    return {
        "api_gateway": os.getenv("API_GATEWAY_URL", "http://localhost:8000"),
        "bybit_connector": os.getenv("BYBIT_CONNECTOR_URL", "http://localhost:8001"),
        "market_data": os.getenv("MARKET_DATA_URL", "http://localhost:8002"),
        "portfolio": os.getenv("PORTFOLIO_URL", "http://localhost:8003"),
        "technical_analysis": os.getenv("TA_URL", "http://localhost:8004"),
        "trading_engine": os.getenv("TRADING_ENGINE_URL", "http://localhost:8005"),
        "notification": os.getenv("NOTIFICATION_URL", "http://localhost:8006"),
        "ml_prediction": os.getenv("ML_PREDICTION_URL", "http://localhost:8007"),
        "sentiment": os.getenv("SENTIMENT_URL", "http://localhost:8008"),
        "risk_metrics": os.getenv("RISK_METRICS_URL", "http://localhost:8009"),
    }


@pytest.fixture(scope="session")
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API calls"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


def _repo_root() -> Path:
    """Walk up from this file to find the git repo root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    raise RuntimeError("Could not locate git repo root from conftest.py")


@pytest.fixture(scope="session")
def tmp_fresh_clone(request) -> Path:
    """Create /tmp/cb-test-<sha> via git clone (D-05). Delete on success (D-08)."""
    repo_root = _repo_root()
    sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tmp = Path(tempfile.gettempdir()) / f"cb-test-{sha}"
    if tmp.exists():
        shutil.rmtree(tmp)
    subprocess.run(
        ["git", "clone", f"file://{repo_root}", str(tmp)],
        check=True,
        capture_output=True,
    )
    # D-06: empty .env at bootstrap entry
    (tmp / ".env").write_text("")

    yield tmp

    # D-08: only delete if no test failures
    if request.session.testsfailed == 0:
        shutil.rmtree(tmp, ignore_errors=True)
    else:
        print(f"\n[D-08] keeping tmp clone for post-mortem: {tmp}")


@pytest.fixture(scope="session")
def bootstrap_stack(tmp_fresh_clone, services_config):
    """Shell out to bootstrap.sh in tmp clone (D-01, D-03). Single boot, shared.
    Pytest runs on host (D-02), bootstrap brings up docker compose stack.
    """
    result = subprocess.run(
        ["./bootstrap.sh"],
        cwd=tmp_fresh_clone,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        print(f"\n=== bootstrap.sh stdout (last 50) ===\n{result.stdout[-5000:]}")
        print(f"\n=== bootstrap.sh stderr (last 50) ===\n{result.stderr[-5000:]}")
        pytest.fail(
            f"bootstrap.sh failed (exit={result.returncode}) in {tmp_fresh_clone}. "
            f"Per D-08, tmp clone preserved at: {tmp_fresh_clone}"
        )

    # Re-poll /health for each service (paranoid double-check across the network seam)
    deadline = time.monotonic() + 60.0
    for svc, url in services_config.items():
        ok = False
        while time.monotonic() < deadline:
            try:
                r = httpx.get(f"{url}/health", timeout=2.0)
                if r.status_code == 200:
                    ok = True
                    break
            except httpx.RequestError:
                pass
            time.sleep(1.0)
        if not ok:
            pytest.fail(f"Service {svc} at {url} did not return 200 within 60s")

    yield tmp_fresh_clone


@pytest.fixture(scope="session")
def wait_for_services(bootstrap_stack):
    """Backward-compat alias. New tests should depend on bootstrap_stack directly."""
    return bootstrap_stack


@pytest.fixture(scope="function")
def test_symbol():
    """Test trading symbol"""
    return "BTCUSDT"


@pytest.fixture(scope="function")
def test_portfolio_id():
    """Test portfolio ID"""
    return "test_portfolio"
