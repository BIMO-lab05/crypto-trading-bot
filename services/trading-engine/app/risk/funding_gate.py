"""
Funding-Rate Gate for Perpetual Entries
Purpose: Reject perp entries that would pay persistent funding drag.

How perp funding works on Bybit (linear, USDT-margined):
    Funding settles every fundingInterval minutes (default 8h on most
    symbols → 3 settlements/day). The funding rate is signed:
        rate > 0 → longs pay shorts
        rate < 0 → shorts pay longs
    Rates are bounded to roughly ±0.05% per settlement.

Why this gate:
    A persistently-positive funding rate (~+5 bps/8h) costs a long
    position ~5.5%/yr in funding alone — enough to wipe out a marginal
    edge. Symmetric problem for shorts in negative funding regimes. We
    skip new entries when the live rate works strongly against the
    intended direction. Existing positions are NOT closed by this gate
    — only new entries are gated.

Reference:
- docs/strategy/research-2026-04-29/06-execution-sizing.md (item T2.3)
- docs/strategy/RESEARCH_PLAN_2026-04-29 T2.3
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


# Bybit caps funding at ~±0.75% per settlement on most linear pairs;
# anything above this is almost certainly a parsing or category error.
_FUNDING_RATE_SANITY_CAP = 0.05  # 5% per settlement → reject as bad data


@dataclass
class FundingGateConfig:
    """Configuration for the funding-rate gate."""

    threshold_bps: float = 5.0
    """
    Per-settlement funding rate above which a long entry is rejected
    (and below -threshold for a short). 5 bps/8h ≈ 5.5%/yr funding cost.
    """

    cache_ttl_seconds: int = 300
    """How long a fetched rate stays valid in the in-memory cache."""

    request_timeout_seconds: float = 5.0


@dataclass(frozen=True)
class FundingDecision:
    """Outcome of consulting the funding gate for one entry."""

    allow: bool
    rate_per_period: Optional[float]  # signed, decimal (0.0005 = 5 bps)
    reason: str

    @property
    def rate_bps(self) -> Optional[float]:
        if self.rate_per_period is None:
            return None
        return self.rate_per_period * 10_000.0


def funding_gate_decision(
    rate_per_period: Optional[float],
    is_long: bool,
    config: FundingGateConfig,
) -> FundingDecision:
    """
    Pure decision function. Given the current per-settlement funding rate
    and the intended side, decide whether to allow the entry.

    - rate_per_period None → allow (degraded — couldn't fetch; don't block).
    - rate magnitude > sanity cap → allow (suspicious data; don't block on it).
    - is_long and rate > +threshold → REJECT (long would pay funding).
    - not is_long and rate < -threshold → REJECT (short would pay funding).
    - otherwise → allow.
    """
    if rate_per_period is None:
        return FundingDecision(
            allow=True,
            rate_per_period=None,
            reason="no rate available; allowing (fail-open)",
        )
    if abs(rate_per_period) > _FUNDING_RATE_SANITY_CAP:
        return FundingDecision(
            allow=True,
            rate_per_period=rate_per_period,
            reason=f"rate {rate_per_period:.4f} fails sanity cap; allowing (fail-open)",
        )

    threshold = config.threshold_bps / 10_000.0
    if is_long and rate_per_period > threshold:
        return FundingDecision(
            allow=False,
            rate_per_period=rate_per_period,
            reason=f"long would pay funding: rate={rate_per_period * 10_000:.2f}bps > +{config.threshold_bps:.2f}bps",
        )
    if (not is_long) and rate_per_period < -threshold:
        return FundingDecision(
            allow=False,
            rate_per_period=rate_per_period,
            reason=f"short would pay funding: rate={rate_per_period * 10_000:.2f}bps < -{config.threshold_bps:.2f}bps",
        )
    return FundingDecision(
        allow=True,
        rate_per_period=rate_per_period,
        reason=f"funding ok: rate={rate_per_period * 10_000:.2f}bps",
    )


class FundingRateClient:
    """
    Thin TTL-cached client over bybit-connector's funding-rate-history endpoint.

    Why a TTL cache and not a request per trade:
        Funding settles every 8h on most symbols, so refreshing more
        than ~once per 5 min is wasted I/O and rate-limit pressure.
        Bybit also has read-rate limits and stale data is preferable
        to a request burst on every signal check.

    Failure mode:
        On any HTTP / parse error, the client returns None (cached as a
        miss with a short retry window). funding_gate_decision treats
        None as fail-open — the gate never blocks trading because the
        rate fetch itself broke.
    """

    def __init__(
        self,
        connector_base_url: str,
        config: FundingGateConfig,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._base_url = connector_base_url.rstrip("/")
        self._config = config
        # Cache: symbol -> (fetched_at_monotonic, rate_or_None)
        self._cache: Dict[str, Tuple[float, Optional[float]]] = {}
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(timeout=config.request_timeout_seconds)

    async def get_latest_rate(self, symbol: str) -> Optional[float]:
        """Return the latest signed funding rate for `symbol`, or None on error."""
        now = time.monotonic()
        cached = self._cache.get(symbol)
        if cached is not None and (now - cached[0]) < self._config.cache_ttl_seconds:
            return cached[1]

        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/market/funding-rate/history",
                params={"symbol": symbol, "category": "linear", "limit": 1},
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") or []
            if not data:
                rate: Optional[float] = None
            else:
                rate_str = data[0].get("fundingRate")
                rate = float(rate_str) if rate_str is not None else None
        except Exception as e:
            logger.warning(
                f"[FUNDING] Failed to fetch funding rate for {symbol}: {e}"
            )
            rate = None

        self._cache[symbol] = (now, rate)
        return rate

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()
