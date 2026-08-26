"""
Indicator Rolling-Confidence Registry
=====================================
Purpose: Per-indicator rolling-confidence telemetry + re-enablement gate.

Why this exists
---------------
One TA indicator is commented out in ``signal_aggregator.py``:

* ``RSI_DIVERGENCE`` — DISABLED: stuck at 0.20 confidence
* ``SQZMOM_ENHANCED`` — re-enabled 2026-08-17 (its "stuck at 0.50 HOLD"
  root cause was fixed 2026-05-05; it votes again)

Today the disabled one lives as a raw ``#`` comment. A future refactor
or "enable everything" toggle could silently re-add it with no evidence
it has improved. This module adds:

1. A bounded ring buffer (last 200 calls) of confidences per indicator.
2. A ``record(name, confidence, was_voted)`` API. ``was_voted=False`` is
   the **shadow-mode** hook — it lets a follow-up PR compute disabled
   indicators passively and still record their confidence without
   counting their vote. Calling shadow-mode is **not** wired up in this
   PR; the parameter exists so wiring it later is non-breaking.
3. ``rolling_average(name)`` — returns ``None`` until the indicator has
   at least 30 samples (avoids gating on noise).
4. ``assert_eligible(name, threshold)`` — raises
   ``IndicatorBelowThresholdError`` when an indicator's rolling average
   is below the configured threshold. Operator-facing endpoints that
   flip an indicator from disabled→enabled wrap the enable path with
   this gate, so a previously-disabled indicator cannot be re-enabled
   on a hunch.
5. A Prometheus gauge ``indicator_rolling_confidence{indicator}`` for
   live ops dashboards.

Concurrency
-----------
``signal_aggregator`` is async. ``deque.append`` with ``maxlen`` is
GIL-atomic in CPython, but ``rolling_average`` iterates the deque
(``sum`` / ``len``) and would otherwise observe torn state during a
concurrent append. An ``asyncio.Lock`` per call serialises
record/read/gauge-update. Hold time is microseconds — non-issue for the
30 s auto-trader cycle.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from prometheus_client import Gauge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum samples retained per indicator.
DEFAULT_WINDOW: int = 200

#: Minimum samples before ``rolling_average`` returns a value (rather than
#: ``None``). Below this, we treat the average as too noisy to gate on.
MIN_SAMPLES_FOR_AVG: int = 30

#: Default rolling-confidence threshold for ``assert_eligible``. Mirrors
#: ``Settings.min_indicator_confidence`` default — kept here so the registry
#: stays usable in isolation (e.g. unit tests).
DEFAULT_THRESHOLD: float = 0.55


# ---------------------------------------------------------------------------
# Prometheus gauge
# ---------------------------------------------------------------------------

# Module-level so ``Gauge`` is registered exactly once. Re-import (e.g. in
# tests) reuses the same metric.
INDICATOR_ROLLING_CONFIDENCE: Gauge = Gauge(
    "indicator_rolling_confidence",
    "Rolling average confidence (last N calls) per technical-analysis indicator",
    labelnames=["indicator"],
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IndicatorBelowThresholdError(Exception):
    """Raised when an indicator's rolling-confidence is below the threshold.

    Carries structured attributes so callers can render a useful HTTP
    response without re-parsing the message.

    Attributes:
        name: Indicator identifier (e.g. ``"RSI_DIVERGENCE"``).
        current_avg: Current rolling average. ``None`` if there are
            fewer than :data:`MIN_SAMPLES_FOR_AVG` samples.
        threshold: Threshold the indicator failed to clear.
    """

    def __init__(
        self,
        name: str,
        current_avg: Optional[float],
        threshold: float,
    ) -> None:
        self.name = name
        self.current_avg = current_avg
        self.threshold = threshold
        avg_str = "no-data" if current_avg is None else f"{current_avg:.3f}"
        super().__init__(
            f"Indicator {name!r} rolling confidence {avg_str} is below "
            f"threshold {threshold:.3f}; refuse to enable."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class IndicatorRegistry:
    """Bounded per-indicator rolling-confidence store.

    Thread/async-safe via a single ``asyncio.Lock`` shared across all
    indicators. The lock guards the deque iteration in
    :meth:`rolling_average` and the read-then-set of the Prometheus
    gauge in :meth:`record`. Lock hold time is dominated by the deque
    sum, which is O(window) — a few microseconds at the default
    window of 200.
    """

    def __init__(self, window: int = DEFAULT_WINDOW) -> None:
        if window <= 0:
            raise ValueError(f"window must be positive, got {window}")
        self._window = window
        # ``defaultdict`` so first-touch creates a deque with the right maxlen.
        # We bind ``maxlen`` via the factory closure.
        self._buffers: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self._window)
        )
        # Tally of how many records were counted as actual votes vs shadow.
        # Useful for ops dashboards and future drift analysis.
        self._vote_counts: Dict[str, int] = defaultdict(int)
        self._shadow_counts: Dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    async def record(
        self,
        name: str,
        confidence: float,
        was_voted: bool,
    ) -> None:
        """Append ``confidence`` to the indicator's ring buffer.

        Args:
            name: Indicator identifier (e.g. ``"RSI"``, ``"MACD"``).
            confidence: Confidence value in ``[0.0, 1.0]``. Out-of-range
                values are clamped — we never want a buggy upstream
                response to corrupt the rolling stats.
            was_voted: ``True`` if the indicator's vote was counted in
                the aggregated signal. ``False`` is the **shadow-mode
                hook**: the indicator was computed for telemetry only.
                In this PR every caller passes ``True``; the
                ``False`` branch exists for a follow-up.
        """
        # Clamp to [0, 1] defensively — TA service has historically
        # returned 1.5 / -0.1 on edge cases; we don't want one bad
        # response to skew a 200-sample window.
        if confidence < 0.0:
            confidence = 0.0
        elif confidence > 1.0:
            confidence = 1.0

        async with self._lock:
            buf = self._buffers[name]
            buf.append(float(confidence))
            if was_voted:
                self._vote_counts[name] += 1
            else:
                self._shadow_counts[name] += 1

            # Update the Prometheus gauge while holding the lock so we
            # don't race against another coroutine recording a stale
            # average. ``_rolling_average_locked`` requires the lock to
            # be held by the caller.
            avg = self._rolling_average_locked(name)
            if avg is not None:
                INDICATOR_ROLLING_CONFIDENCE.labels(indicator=name).set(avg)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def rolling_average(
        self,
        name: str,
        window: int = DEFAULT_WINDOW,
    ) -> Optional[float]:
        """Return the rolling-mean confidence for ``name``.

        Args:
            name: Indicator identifier.
            window: How many of the most-recent samples to average over.
                Capped by the underlying buffer's ``maxlen``.

        Returns:
            Mean confidence, or ``None`` if fewer than
            :data:`MIN_SAMPLES_FOR_AVG` samples have been recorded.
        """
        async with self._lock:
            return self._rolling_average_locked(name, window=window)

    def _rolling_average_locked(
        self,
        name: str,
        window: int = DEFAULT_WINDOW,
    ) -> Optional[float]:
        """Lock-free read; caller MUST hold ``self._lock``."""
        buf = self._buffers.get(name)
        if buf is None or len(buf) < MIN_SAMPLES_FOR_AVG:
            return None
        # ``deque`` does not support negative slicing; use itertools-free
        # path: convert tail via list indexing.
        if window >= len(buf):
            samples = buf
        else:
            # Build a tail view without copying the whole deque.
            tail_start = len(buf) - window
            samples = list(buf)[tail_start:]
        return sum(samples) / len(samples)

    async def sample_count(self, name: str) -> int:
        """Return how many samples have been recorded (capped at window)."""
        async with self._lock:
            buf = self._buffers.get(name)
            return 0 if buf is None else len(buf)

    async def stats(self, name: str) -> Dict[str, Optional[float]]:
        """Return a snapshot of registry stats for the given indicator."""
        async with self._lock:
            buf = self._buffers.get(name)
            count = 0 if buf is None else len(buf)
            avg = self._rolling_average_locked(name)
            return {
                "indicator": name,
                "sample_count": count,
                "rolling_avg": avg,
                "votes_counted": self._vote_counts.get(name, 0),
                "shadow_observations": self._shadow_counts.get(name, 0),
            }

    # ------------------------------------------------------------------
    # Gate
    # ------------------------------------------------------------------

    async def assert_eligible(
        self,
        name: str,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        """Raise if ``name`` is not eligible for re-enablement.

        Eligibility = at least :data:`MIN_SAMPLES_FOR_AVG` samples
        recorded **and** their rolling mean ≥ ``threshold``. Either
        condition failing raises :class:`IndicatorBelowThresholdError`.

        Args:
            name: Indicator identifier.
            threshold: Minimum acceptable rolling-mean confidence
                (``[0.0, 1.0]``).

        Raises:
            IndicatorBelowThresholdError: If ineligible.
        """
        avg = await self.rolling_average(name)
        if avg is None or avg < threshold:
            raise IndicatorBelowThresholdError(
                name=name,
                current_avg=avg,
                threshold=threshold,
            )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[IndicatorRegistry] = None


def get_indicator_registry() -> IndicatorRegistry:
    """Return the process-wide :class:`IndicatorRegistry` singleton.

    Lazy so importing this module doesn't allocate before the event
    loop is running. The singleton lives for the lifetime of the
    process; on test isolation, call :func:`reset_indicator_registry`
    in a fixture.
    """
    global _registry
    if _registry is None:
        _registry = IndicatorRegistry()
        logger.info(
            "IndicatorRegistry initialized (window=%d, min_samples=%d)",
            DEFAULT_WINDOW,
            MIN_SAMPLES_FOR_AVG,
        )
    return _registry


def reset_indicator_registry() -> None:
    """Drop the singleton. Intended for tests only.

    Note: this does **not** unregister the Prometheus gauge — gauges
    are process-global by design. Tests that assert on gauge values
    should use unique indicator names per case to avoid bleed.
    """
    global _registry
    _registry = None
