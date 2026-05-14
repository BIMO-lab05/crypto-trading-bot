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
from typing import Any, AsyncGenerator, Dict

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

    WR-09 (Phase 2) — EMERGENCY_STOP coupling:
    bootstrap.sh:54 calls `touch EMERGENCY_STOP` (D-11), which the
    trading-engine's lifespan check at services/trading-engine/app/main.py:
    282-289 reads to refuse arming the auto-trader. This fixture
    intentionally does NOT remove the file — every test in this suite
    bypasses the auto-trader (test_fresh_clone_round_trip uses
    force_signal which calls orchestrator.submit_signal directly;
    test_notification_delivery_via_trade_endpoint POSTs to
    /api/v1/notify/trade directly). The auto-trader periodic loop is
    NOT exercised by this suite.

    Future tests that depend on the auto-trader actually firing periodic
    signals (or assume a "freshly-booted, ready-to-trade" stack) MUST
    either clear `tmp_fresh_clone / "EMERGENCY_STOP"` themselves before
    yielding, or mark themselves with a fixture that does so. Doing it
    here would change test isolation semantics for every downstream
    test and is intentionally out of scope.

    Worse trap (per services/trading-engine/app/main.py:267-272): if the
    WSL bind-mount race fires, Docker may create a *directory* at the
    EMERGENCY_STOP mount point — `is_file()` returns False, but the
    in-container check at line 282 still reports "present" via the
    bootstrap-created host file. If a future test sees auto-trader
    refusing to arm with EMERGENCY_STOP visibly absent, check the
    container's /app/EMERGENCY_STOP for directory-vs-file confusion
    before chasing other suspects.
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


# ---------------------------------------------------------------------------
# Task 3: function-scoped fixtures for per-test isolation
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
async def tape_reset(http_client, services_config, bootstrap_stack):
    """HTTP POST /admin/tape/reset before each test (D-04).
    Stack must be in tape mode (MARKET_DATA_SOURCE=tape).
    """
    url = f"{services_config['bybit_connector']}/admin/tape/reset"
    r = await http_client.post(url)
    assert r.status_code == 200, (
        f"tape/reset failed: status={r.status_code} body={r.text}. "
        "Stack must be in MARKET_DATA_SOURCE=tape mode."
    )
    yield


@pytest.fixture(scope="function")
def force_signal(http_client, services_config):
    """Helper for POSTing synthetic signals to trading-engine (CD-04).
    Returns an async callable; test bodies await it.
    """
    url = f"{services_config['trading_engine']}/api/v1/admin/force-signal"

    async def _send(payload: Dict[str, Any]) -> Dict[str, Any]:
        r = await http_client.post(url, json=payload)
        assert r.status_code == 200, f"force-signal failed: {r.status_code} {r.text}"
        return r.json()

    return _send


@pytest.fixture(scope="function")
async def db_truncate():
    """Clear klines, tickers, positions, orders between tests. Schema preserved.

    [Rule 1 fix] Plan defaults used postgres:postgres@.../crypto_trading and .../timescale
    but docker-compose.unified.yml shows user=cryptobot, pg_db=cryptobot, ts_db=market_data,
    ts_host_port=5433. Corrected here so defaults match compose out-of-the-box.
    Operator may override via POSTGRES_URL / TIMESCALE_URL env vars.
    """
    import asyncpg

    postgres_url = os.getenv(
        "POSTGRES_URL",
        "postgresql://cryptobot:cryptobot_dev_password@localhost:5432/cryptobot",
    )
    timescale_url = os.getenv(
        "TIMESCALE_URL",
        "postgresql://cryptobot:timescale_dev_password@localhost:5433/market_data",
    )
    async with asyncpg.create_pool(timescale_url, min_size=1, max_size=2) as ts_pool:
        async with ts_pool.acquire() as conn:
            await conn.execute(
                "TRUNCATE TABLE klines, tickers RESTART IDENTITY CASCADE"
            )
    async with asyncpg.create_pool(postgres_url, min_size=1, max_size=2) as pg_pool:
        async with pg_pool.acquire() as conn:
            await conn.execute(
                "TRUNCATE TABLE positions, orders RESTART IDENTITY CASCADE"
            )
    yield


@pytest.fixture(scope="function")
async def notification_received():
    """Mode-aware notification verification (CD-01).

    Returns an async callable that tests use to assert a notification was emitted.
    Branches on NOTIFICATION_TEST_MODE env var:
      - "record" (default, local): tails tests/.notifications.log for the substring.
      - "live"   (CI):             polls https://api.telegram.org/bot{TOKEN}/getUpdates.

    Both paths return bool so test bodies are mode-agnostic.
    Uses pathlib.Path for file I/O (bypasses builtins.open mocking trap per
    feedback_pathlib_mocking.md in project memory).
    """
    mode = os.getenv("NOTIFICATION_TEST_MODE", "record") or "record"
    log_path = _repo_root() / "tests" / ".notifications.log"
    if mode == "record":
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("")  # truncate before each test

    async def _wait_for(text: str, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + timeout
        if mode == "record":
            while time.monotonic() < deadline:
                if log_path.exists():
                    if any(
                        text in ln
                        for ln in log_path.read_text().splitlines()
                        if ln.strip()
                    ):
                        return True
                await asyncio.sleep(0.25)
            return False
        # live mode: poll Telegram getUpdates
        bot_token = os.getenv("TEST_TELEGRAM_BOT_TOKEN", "")
        if not bot_token:
            pytest.fail(
                "NOTIFICATION_TEST_MODE=live requires TEST_TELEGRAM_BOT_TOKEN env var. "
                "Set it via CI secrets, or use NOTIFICATION_TEST_MODE=record locally."
            )
        tg_url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                try:
                    r = await client.get(tg_url, timeout=5.0)
                    if r.status_code == 200:
                        for upd in r.json().get("result", []):
                            m = upd.get("message", {}).get("text", "")
                            if text in m:
                                return True
                except httpx.RequestError:
                    pass
                await asyncio.sleep(1.0)
        return False

    yield _wait_for


# ---------------------------------------------------------------------------
# Phase 7 Plan 05: tournament smoke snapshot seed (D-08, W-3 Path A).
#
# Copies tests/fixtures/tournament/smoke-fixture{,.ensemble,.significance}.json
# into services/tournament-harness/data/snapshots/smoke-tape-fixture{,.ensemble,
# .significance}.json so the api-gateway RO bind-mount (/app/snapshots) sees a
# deterministic tournament. The committed smoke fixture is the source of truth
# in git; this fixture only stages it at the path the gateway reads from.
#
# Teardown deletes all 3 staged files; if any test fails, the host directory is
# gitignored so leftover dummy data is harmless. Per project memory
# (feedback_pathlib_mocking.md), pathlib.Path.read_text / write_text bypass
# builtins.open — the route uses Path.read_text, so a mock on open() in tests
# would silently no-op. This fixture does real filesystem I/O for that reason.
# ---------------------------------------------------------------------------
@pytest.fixture(scope="function")
def tournament_snapshot_seeded():
    """Seed smoke-tape-fixture (primary + 2 Phase 4 sidecars) into the
    api-gateway RO bind-mount source dir; clean up all 3 files on teardown.

    Yields the absolute Path to the primary snapshot file so callers can
    sanity-check existence; most tests only need the side effect (the
    gateway sees the files at /app/snapshots/ via the bind mount declared
    in docker-compose.unified.yml).
    """
    src_dir = _repo_root() / "tests" / "fixtures" / "tournament"
    dst_dir = _repo_root() / "services" / "tournament-harness" / "data" / "snapshots"
    dst_dir.mkdir(parents=True, exist_ok=True)
    mapping = {
        "smoke-fixture.json": "smoke-tape-fixture.json",
        "smoke-fixture.ensemble.json": "smoke-tape-fixture.ensemble.json",
        "smoke-fixture.significance.json": "smoke-tape-fixture.significance.json",
    }
    dst_paths: list[Path] = []
    for src_name, dst_name in mapping.items():
        src = src_dir / src_name
        dst = dst_dir / dst_name
        dst.write_text(src.read_text())
        dst_paths.append(dst)
    try:
        # Primary snapshot path — Playwright tests get this even if they
        # only need the side effect.
        yield dst_paths[0]
    finally:
        for p in dst_paths:
            p.unlink(missing_ok=True)
