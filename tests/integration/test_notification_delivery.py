"""CD-01 notification-delivery tests — mode-aware via notification_received fixture (Plan 02-03)."""

import os
import re
import time

import pytest


@pytest.mark.asyncio
async def test_notification_delivery_via_trade_endpoint(
    bootstrap_stack, services_config, http_client, notification_received
):
    """ONE mode-aware test:
      - record mode: notification-service writes a JSON line to tests/.notifications.log
      - live  mode: notification-service POSTs to api.telegram.org; verify via getUpdates
    Both branches handled inside `notification_received` from conftest (Plan 02-03).
    Uses POST /api/v1/notify/trade (existing at services/notification-service/app/main.py:397)
    which accepts a TradeNotification body containing the symbol — the symbol becomes our search key.
    """
    unique_marker = f"PHASE2-{int(time.time())}"
    notification_url = f"{services_config['notification']}/api/v1/notify/trade"
    payload = {
        "symbol": f"SOLUSDT-{unique_marker}",
        "action": "buy",
        "quantity": 0.5,
        "entry_price": 100.0,
        "exit_price": 100.0,
        "pnl": 0.0,
        "trade_id": unique_marker,
    }
    r = await http_client.post(notification_url, json=payload)
    assert r.status_code == 200, f"notify/trade returned {r.status_code}: {r.text}"

    # Mode-aware assertion: record-mode tails the file; live-mode polls getUpdates.
    got = await notification_received(unique_marker, timeout=15.0)
    mode = os.getenv("NOTIFICATION_TEST_MODE", "record") or "record"
    assert got, (
        f"Notification not received in mode={mode!r} for marker {unique_marker!r}. "
        "In record mode, check tests/.notifications.log. "
        "In live mode, verify TEST_TELEGRAM_BOT_TOKEN+TEST_TELEGRAM_CHAT_ID are set and the bot is in the chat."
    )


def test_env_test_example_has_no_real_token():
    """Regression: .env.test.example MUST be placeholder-only — never a real token committed."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    p = os.path.join(repo_root, ".env.test.example")
    text_content = open(p, encoding="utf-8").read()
    bot_token_pat = re.compile(
        r"^TEST_TELEGRAM_BOT_TOKEN=\d{8,12}:[A-Za-z0-9_-]{30,}", re.MULTILINE
    )
    assert not bot_token_pat.search(text_content), (
        ".env.test.example contains what looks like a real Telegram bot token. "
        "This file is committed; it MUST contain placeholder values only."
    )
