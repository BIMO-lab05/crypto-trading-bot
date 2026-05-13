"""
Tests for the trading-engine /status handler's emergency_stop.mtime field.

Plan 06-02 Task 1: Surface the EMERGENCY_STOP file mtime to the api-gateway
so the dashboard can show "armed since: <ts>". Field must be:

- None when the file does not exist OR exists but is not a regular file
  (WSL bind-mount race — the path can be a directory). The CLAUDE.md gotcha
  block calls this out explicitly.
- ISO 8601 UTC string parseable by datetime.fromisoformat() when the file
  is a real regular file.
- None (not an exception) when Path.stat() races and raises OSError between
  is_file() and stat().

The existing keys (file_path, active, last_checked, auto_trader_running)
must remain present in unchanged shape.

References:
- CLAUDE.md: pathlib.Path.write_text / read_text / open bypass builtins.open;
  patch pathlib.Path.is_file / pathlib.Path.stat directly here.
- 06-PATTERNS.md lines 399-450 (full patch shape).
- StatusResponse.emergency_stop is Optional[Dict] (response.py:33) — no
  pydantic model edit required.
"""

import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch
from pathlib import Path

import pytest


def _run(coro):
    """Run an async coroutine synchronously for sync test bodies."""
    return asyncio.get_event_loop().run_until_complete(coro)


def _build_fake_auto_trader(tmp_path):
    """Construct a minimal stand-in for AutoTrader exposing only the
    attributes get_status reads."""
    at = MagicMock()
    at.emergency_stop_file = tmp_path / "EMERGENCY_STOP"
    at.emergency_stop_active = False
    at.emergency_stop_last_checked = None
    at.is_running = True
    return at


@pytest.fixture
def patched_get_status(tmp_path):
    """Yield (get_status, fake_auto_trader). Patches the in-handler deps
    so get_status can be exercised without booting the engine."""
    from app.handlers import health as health_handler

    fake_auto_trader = _build_fake_auto_trader(tmp_path)

    # Patch downstream singletons the handler reaches into. We do not
    # care about their return values for this test — only that
    # emergency_stop_state is built correctly.
    fake_position_manager = MagicMock()
    fake_position_manager.get_open_positions.return_value = []
    fake_paper_engine = MagicMock()
    fake_paper_engine.get_balance.return_value = 100000.0
    fake_health_monitor = MagicMock()
    fake_health_monitor.get_system_metrics.return_value = {}

    with (
        patch.object(
            health_handler, "get_position_manager", return_value=fake_position_manager
        ),
        patch.object(
            health_handler, "get_paper_engine", return_value=fake_paper_engine
        ),
        patch.object(
            health_handler, "get_health_monitor", return_value=fake_health_monitor
        ),
        patch("app.auto_trader.get_auto_trader", return_value=fake_auto_trader),
    ):
        yield health_handler.get_status, fake_auto_trader


def test_emergency_stop_mtime_is_none_when_path_is_directory(patched_get_status):
    """When EMERGENCY_STOP is a directory (WSL bind-mount race), is_file()
    returns False -> mtime must be None and no exception escapes."""
    get_status, fake_auto_trader = patched_get_status

    # Path exists as a directory — is_file() returns False.
    fake_auto_trader.emergency_stop_file.mkdir(parents=True, exist_ok=True)

    response = _run(get_status())
    es = response.emergency_stop
    assert es is not None, "emergency_stop dict must be present"
    assert "mtime" in es, "mtime key must be present even when file is a directory"
    assert es["mtime"] is None, "mtime must be None when path is not a regular file"
    # Existing keys preserved.
    for key in ("file_path", "active", "last_checked", "auto_trader_running"):
        assert key in es, f"existing key '{key}' must remain present"


def test_emergency_stop_mtime_is_iso_when_file_exists(patched_get_status):
    """When EMERGENCY_STOP is a real regular file, mtime is an ISO 8601 UTC
    string parseable by datetime.fromisoformat()."""
    get_status, fake_auto_trader = patched_get_status

    p = fake_auto_trader.emergency_stop_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("kill")

    response = _run(get_status())
    es = response.emergency_stop
    assert es["mtime"] is not None, "mtime must be populated when file is a real file"
    parsed = datetime.fromisoformat(es["mtime"])
    assert parsed.tzinfo is not None, "mtime must be timezone-aware (UTC)"


def test_emergency_stop_mtime_none_when_stat_raises(patched_get_status):
    """If Path.stat() races and raises OSError between is_file() and stat(),
    the mtime must be None and no exception escapes the handler."""
    get_status, fake_auto_trader = patched_get_status

    p = fake_auto_trader.emergency_stop_file
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("kill")

    # Force is_file() to True but stat() to raise — simulates the file
    # disappearing between the two calls (rare; documented for completeness).
    with (
        patch.object(Path, "is_file", return_value=True),
        patch.object(Path, "stat", side_effect=OSError("simulated race")),
    ):
        response = _run(get_status())
    es = response.emergency_stop
    assert es["mtime"] is None, "mtime must be None when stat() raises"


def test_emergency_stop_existing_keys_preserved(patched_get_status):
    """Adding mtime must not silently drop or rename pre-existing keys."""
    get_status, fake_auto_trader = patched_get_status

    response = _run(get_status())
    es = response.emergency_stop
    expected_keys = {
        "file_path",
        "active",
        "last_checked",
        "auto_trader_running",
        "mtime",
    }
    assert expected_keys.issubset(set(es.keys())), (
        f"emergency_stop must contain at least {expected_keys}; got {set(es.keys())}"
    )
    # active is still a bool, file_path is still a string.
    assert isinstance(es["active"], bool)
    assert isinstance(es["file_path"], str)
    assert isinstance(es["auto_trader_running"], bool)
