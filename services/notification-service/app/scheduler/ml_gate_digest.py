"""ML-gate reason-counts scheduled fetcher (Plan 09-03 MLGATE-03 D-09-03-07).

Pulls the trading-engine's in-process ML-gate reason counter via httpx and
forwards the result to ``alert_manager.send_daily_summary`` so the daily
Telegram digest aggregates the disabled-event reasons.

Closes ROADMAP Phase 9 SC#4 cross-service delivery clause (checker Blocker 2,
Path A locked recommendation). HTTP-pull pattern matches the notification
service's existing inbound integration shape (telegram_notifier.py:96 + the
TelegramClient httpx usage at channels/telegram_client.py:135).

Graceful degradation discipline (Phase 8):
- On non-200 / timeout / connection error: log warning, dispatch the digest
  with ``ml_gate_reason_counts=None`` so the daily summary still ships, just
  without the ML-gate section.

v1.1 scope: stub the rest of the daily-summary payload with zeros
(total_pnl=0.0, total_trades=0, win_rate=0.0, balance=0.0). v1.2 follow-up
wires real values from the trading-engine balance / P&L endpoints via the
same HTTP pattern.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — kept module-level for easy patching in tests + override via env.
# ---------------------------------------------------------------------------
_DEFAULT_TRADING_ENGINE_URL = "http://trading-engine:8005"
_FETCH_TIMEOUT_SECONDS = 5.0
_ENDPOINT_PATH = "/api/preflight/ml-gate-reason-counts"


def _resolve_trading_engine_url(override: Optional[str] = None) -> str:
    """Resolve the trading-engine base URL.

    Precedence: explicit ``override`` argument > ``TRADING_ENGINE_URL`` env >
    docker-compose default.
    """
    if override is not None:
        return override
    return os.environ.get("TRADING_ENGINE_URL", _DEFAULT_TRADING_ENGINE_URL)


async def _fetch_reason_counts(
    base_url: str,
    *,
    timeout_seconds: float = _FETCH_TIMEOUT_SECONDS,
) -> Optional[dict]:
    """Fetch the ML-gate reason counts from the trading-engine.

    Returns the parsed dict on 200, or None on any non-200 / connection
    error. Never raises (graceful-degradation discipline).
    """
    url = f"{base_url.rstrip('/')}{_ENDPOINT_PATH}"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url)
    except (httpx.TimeoutException, httpx.RequestError) as e:
        logger.warning(
            "ml-gate-reason-counts fetch failed: %s (url=%s)",
            type(e).__name__,
            url,
        )
        return None
    if response.status_code != 200:
        logger.warning(
            "ml-gate-reason-counts fetch returned non-200 status=%s (url=%s)",
            response.status_code,
            url,
        )
        return None
    try:
        body = response.json()
    except ValueError as e:
        logger.warning("ml-gate-reason-counts JSON parse failed: %s", e)
        return None
    if not isinstance(body, dict):
        logger.warning(
            "ml-gate-reason-counts response not a dict: type=%s",
            type(body).__name__,
        )
        return None
    return body


async def fetch_and_dispatch_digest(
    *,
    trading_engine_url: Optional[str] = None,
    alert_manager=None,
) -> dict:
    """Fetch ML-gate reason counts and dispatch the daily digest.

    Args:
        trading_engine_url: Optional override for the trading-engine base URL.
            Defaults to ``TRADING_ENGINE_URL`` env or docker-compose hostname.
        alert_manager: Optional alert_manager instance. When None, imports
            the module-global ``alert_manager`` lazily (so tests can pass a
            mock without paying the import cost at module load).

    Returns:
        A dispatch-summary dict:
        ``{"reason_counts": dict | None, "fetch_status": "ok" | "error", "dispatched": bool}``.
    """
    base_url = _resolve_trading_engine_url(trading_engine_url)
    reason_counts = await _fetch_reason_counts(base_url)
    fetch_status = "ok" if reason_counts is not None else "error"

    if alert_manager is None:
        # Lazy import keeps test isolation cheap.
        from app.alert_manager import alert_manager as _alert_manager

        alert_manager = _alert_manager

    dispatched = False
    try:
        await alert_manager.send_daily_summary(
            total_pnl=0.0,
            total_trades=0,
            win_rate=0.0,
            balance=0.0,
            ml_gate_reason_counts=reason_counts,
        )
        dispatched = True
    except Exception as e:  # pragma: no cover — defensive
        logger.error(
            "daily-digest dispatch failed: %s",
            type(e).__name__,
            exc_info=True,
        )

    return {
        "reason_counts": reason_counts,
        "fetch_status": fetch_status,
        "dispatched": dispatched,
    }


async def _scheduler_loop(period_seconds: int) -> None:
    """Inner loop: dispatch the digest, sleep, repeat."""
    logger.info(
        "ml-gate-digest scheduler started (period_seconds=%s, endpoint=%s)",
        period_seconds,
        _ENDPOINT_PATH,
    )
    try:
        while True:
            try:
                summary = await fetch_and_dispatch_digest()
                logger.info(
                    "ml-gate-digest tick summary=%s",
                    summary,
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:  # pragma: no cover — defensive
                logger.error(
                    "ml-gate-digest tick failed: %s",
                    type(e).__name__,
                    exc_info=True,
                )
            await asyncio.sleep(period_seconds)
    except asyncio.CancelledError:
        logger.info("ml-gate-digest scheduler cancelled")
        raise


async def start_scheduler(*, period_seconds: int = 86400) -> asyncio.Task:
    """Spawn the scheduler loop as an asyncio task; return the task handle.

    Defaults to a 24h cadence. Caller (the notification-service lifespan
    hook) is responsible for cancelling the task at shutdown.

    No apscheduler dependency — a plain ``asyncio.create_task`` loop is
    sufficient for the daily cadence in v1.1.
    """
    task = asyncio.create_task(
        _scheduler_loop(period_seconds),
        name="ml_gate_digest_scheduler",
    )
    return task
