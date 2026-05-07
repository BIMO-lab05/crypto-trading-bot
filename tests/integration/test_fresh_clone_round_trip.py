"""Phase 2 INFRA-01 headline test.

Asserts the four ROADMAP success criteria in a single test path:
  1. All services healthy from a fresh clone (via bootstrap_stack)
  2. Recorded-tape prices flow (SOLUSDT ticker returns non-empty)
  3. Paper-trade round-trip in < 60s (force_signal -> position row)
  4. Notification delivers (record-mode log shows the trade)

DB poll uses POSTGRES_URL env var (defaults to compose out-of-the-box creds
from docker-compose.unified.yml: cryptobot:cryptobot_dev_password@localhost:5432/cryptobot).
[Rule 1 fix] The plan's code used postgres:postgres@.../crypto_trading — those are
NOT the compose defaults; corrected to match conftest.py Rule 1 fix.
"""

import asyncio
import os
import time
from typing import Any, Dict

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_fresh_clone_round_trip(
    bootstrap_stack,
    services_config,
    http_client,
    tape_reset,
    db_truncate,
    force_signal,
    notification_received,
):
    """ROADMAP Phase 2 success criterion 1 — full INFRA-01 round-trip.

    Asserts (in order):
      2. Recorded-tape prices flow — SOLUSDT ticker returns non-empty list
      3. Paper-trade round-trip in < 60s — position row lands in DB
      4. Notification delivered — mode-aware (record-mode log / live Telegram)
    (1) is implicit: bootstrap_stack already fails loudly if any service is unhealthy.
    """

    # --- 2. Recorded-tape prices flow ---
    tickers_url = f"{services_config['bybit_connector']}/api/v1/market/tickers"
    r = await http_client.get(
        tickers_url, params={"category": "linear", "symbol": "SOLUSDT"}
    )
    assert r.status_code == 200, f"ticker fetch failed: {r.status_code} {r.text}"
    body = r.json()
    # Bybit V5 envelope: success + result.list
    assert body.get("success") is True, f"ticker not success: {body}"
    ticker_list = body.get("result", {}).get("list", []) or body.get("data", {}).get(
        "list", []
    )
    assert ticker_list, f"ticker list empty — recorded tape not loaded: {body}"

    # --- 3. Paper-trade round-trip < 60s ---
    strategy_id = f"phase2-roundtrip-{int(time.time())}"
    payload: Dict[str, Any] = {
        "strategy_id": strategy_id,
        "symbol": "SOLUSDT",
        "direction": "long",
        "action": "buy",
        "strength": 0.8,
        "confidence": 0.7,
    }
    t0 = time.monotonic()
    result = await force_signal(payload)
    assert result.get("signal_id"), f"force_signal returned no signal_id: {result}"

    # Poll DB for position row at 250ms cadence, hard 60s deadline (CD-04).
    # Uses POSTGRES_URL env var — defaults match docker-compose.unified.yml out-of-the-box.
    postgres_url = os.getenv(
        "POSTGRES_URL",
        "postgresql://cryptobot:cryptobot_dev_password@localhost:5432/cryptobot",
    )
    deadline = t0 + 60.0
    pool = await asyncpg.create_pool(postgres_url, min_size=1, max_size=2)
    try:
        position_row = None
        while time.monotonic() < deadline:
            async with pool.acquire() as conn:
                position_row = await conn.fetchrow(
                    "SELECT created_at FROM positions "
                    "WHERE strategy_id = $1 "
                    "ORDER BY created_at DESC LIMIT 1",
                    strategy_id,
                )
            if position_row and position_row["created_at"] is not None:
                break
            await asyncio.sleep(0.25)
    finally:
        await pool.close()

    elapsed = time.monotonic() - t0
    assert position_row is not None, (
        f"No position row created within 60s for strategy_id={strategy_id} "
        f"(elapsed={elapsed:.2f}s)"
    )
    assert elapsed < 60.0, (
        f"paper-trade round-trip took {elapsed:.2f}s, exceeds 60s budget (CD-04)"
    )

    # --- 4. Notification delivered ---
    # mode-aware: tails tests/.notifications.log (record) or polls Telegram getUpdates (live).
    got_notification = await notification_received("SOLUSDT", timeout=10.0)
    assert got_notification, (
        "No notification matching 'SOLUSDT' received within 10s. "
        "In record mode, check tests/.notifications.log; in live mode, verify "
        "TEST_TELEGRAM_BOT_TOKEN is set and the bot is in the chat."
    )


@pytest.mark.asyncio
async def test_all_ten_services_healthy(bootstrap_stack, services_config, http_client):
    """ROADMAP Phase 2 success criterion 1 — explicit per-service /health=200 assertion.

    Belt-and-suspenders: bootstrap_stack already polls /health for each service, but
    a separate pytest assertion gives a clear, named failure in pytest output.
    """
    failures = []
    for svc, url in services_config.items():
        try:
            r = await http_client.get(f"{url}/health", timeout=5.0)
            if r.status_code != 200:
                failures.append(f"{svc}: HTTP {r.status_code}")
        except Exception as e:
            failures.append(f"{svc}: {type(e).__name__}: {e}")
    assert not failures, "Unhealthy services: " + ", ".join(failures)


@pytest.mark.asyncio
async def test_unknown_symbol_does_not_500(
    bootstrap_stack, services_config, http_client
):
    """Phase 1 contract — symbol not in 5-symbol tape returns 200 with empty list, not 500.

    XRPUSDT is excluded from paper-trading data scope (validated symbols: BTC, ETH, SOL,
    BNB, ADA only per CLAUDE.md). Tape replay returns empty list for unknowns (landmine §4).
    """
    url = f"{services_config['bybit_connector']}/api/v1/market/tickers"
    r = await http_client.get(url, params={"category": "linear", "symbol": "XRPUSDT"})
    assert r.status_code == 200, f"unknown symbol returned {r.status_code}: {r.text}"
    body = r.json()
    ticker_list = body.get("result", {}).get("list", []) or body.get("data", {}).get(
        "list", []
    )
    # Empty list is the expected shape for an unknown symbol — NOT 500.
    assert isinstance(ticker_list, list), f"ticker list not a list: {body}"
