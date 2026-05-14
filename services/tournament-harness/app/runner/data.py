"""Klines loader (TimescaleDB read-only via tournament_reader role, D-09)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# D-08: testnet-flip bug fix landed 2026-04-25; rows before this are mixed-history.
CONTAMINATION_CUTOFF = datetime(2026, 4, 25, 0, 0, 0)
MIN_ROWS_FLOOR = 50_000  # D-07 hard floor


def _build_dsn() -> str:
    """Construct DSN from env (set by orchestrator on the experiment container)."""
    user = os.environ.get("TIMESCALE_USER", "tournament_reader")
    pwd = os.environ.get("TIMESCALE_PASSWORD", "")
    host = os.environ.get("TIMESCALE_HOST", "timescaledb")
    port = os.environ.get("TIMESCALE_PORT", "5432")
    db = os.environ.get("TIMESCALE_DB", "trading_bot")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def load_klines_from_timescale(
    symbol: str,
    interval: str,
    end_ts: datetime,
    days_back: int = 365,
) -> Tuple[pd.DataFrame, bool]:
    """Fetch is_mainnet klines for (symbol, interval) over [end_ts - days_back, end_ts].

    Returns (df, train_window_includes_contaminated).
    Raises:
        ConnectionError: DB unreachable (caller writes failure result.json with reason='db_unreachable')
        ValueError: row count below MIN_ROWS_FLOOR (caller writes 'train_diverged' or aborts)

    Note: `symbol` must be Bybit-convention quote-pair form (e.g. 'SOLUSDT'),
    NOT bare base ('SOL'). market-data-service writes klines.symbol in the
    USDT-suffixed form; bare base symbols would silently miss every row and
    trip the 50K floor on every cell. tournament_loader enforces this at YAML
    parse time (SYMBOL_RE), but the runner double-checks because experiment
    containers are isolated and a stale spec-json could slip through.
    """
    # Defense in depth: tournament_loader validates this at YAML load, but
    # runner is the last line before SQL — assert again so a bug in the
    # loader can never silently return zero rows.
    assert symbol.endswith("USDT"), (
        f"Tournament symbols must be Bybit-convention quote-pair form, got {symbol!r}"
    )

    import psycopg2  # imported lazily — error gets caught more cleanly than at module import

    start_ts = end_ts - timedelta(days=days_back)
    contaminated = start_ts < CONTAMINATION_CUTOFF

    sql = """
        SELECT timestamp, open, high, low, close, volume
        FROM klines
        WHERE symbol = %s
          AND interval = %s
          AND is_mainnet = TRUE
          AND timestamp BETWEEN %s AND %s
        ORDER BY timestamp ASC
    """
    try:
        conn = psycopg2.connect(_build_dsn())
    except psycopg2.OperationalError as e:
        raise ConnectionError(f"timescaledb unreachable: {e}") from e

    try:
        df = pd.read_sql(sql, conn, params=(symbol, interval, start_ts, end_ts))
    finally:
        conn.close()

    n = len(df)
    logger.info(
        "loaded %d klines for %s/%s in [%s, %s]; contaminated=%s",
        n,
        symbol,
        interval,
        start_ts,
        end_ts,
        contaminated,
    )
    if n < MIN_ROWS_FLOOR:
        raise ValueError(
            f"insufficient klines: {n} rows < {MIN_ROWS_FLOOR} floor "
            f"({symbol}/{interval} in window {start_ts}..{end_ts})"
        )
    return df, contaminated
