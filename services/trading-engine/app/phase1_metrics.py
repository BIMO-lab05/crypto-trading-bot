"""
Phase 1 Metrics Provider
Exposes Phase 1 monitoring data via API

HONESTY REWORK (2026-08-20): all counters now derive from ONE windowed
source — minute-resolution time buckets (`_window_buckets`) that are
pruned at 7 days and are NOT capped by the display deque. Previously the
endpoints mixed three sources (lifetime class counters, a LIMIT-1000
history deque, and per-endpoint rate formulas), which produced
byte-identical payloads for hours=1..168, counts frozen at 1000, and
contradictory rates between /metrics and /health.

Invariants:
- `get_metrics(hours)` and `get_system_health()` compute every counter
  from `_windowed_totals(hours)` — the single source of truth.
- Rates are computed by exactly one formula each (`_rate_pct`).
- All emitted timestamps are UTC-aware isoformat (with +00:00 offset),
  matching /api/config/safety-state. Naive inputs are treated as UTC
  and never shifted.
- `total_signals_processed` is a true monotonic lifetime count, not
  `len()` of a capped deque.
"""

import logging
import re
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Longest window the dashboard offers is 7d (168h); buckets older than
# this are pruned. Requests for larger windows are truncated to this.
WINDOW_RETENTION_HOURS = 168


def _utc_now() -> datetime:
    """Current time, UTC-aware."""
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime) -> datetime:
    """Make a datetime UTC-aware.

    Naive datetimes are treated as UTC wall time (deployed DB and older
    in-memory records are naive-UTC) — attach the offset, never shift.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iso_utc(value) -> Optional[str]:
    """Serialize a datetime or isoformat string as UTC-aware isoformat.

    Always emits an explicit offset (+00:00) so JS `new Date()` parses
    it as UTC instead of local time.
    """
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value  # not a timestamp; pass through unchanged
    return _ensure_utc(value).isoformat()


def _new_bucket_counters() -> Dict:
    """Zeroed counter set for one time bucket."""
    return {
        "total": 0,
        "buy": 0,
        "sell": 0,
        "hold": 0,
        "gk_blocks": 0,
        "gk_passed": 0,
        "bullish": 0,
        "bearish": 0,
        "neutral": 0,
        "val_confirmed": 0,
        "val_rejected": 0,
        "strength": {"STRONG": 0, "MODERATE": 0, "WEAK": 0, "MINIMAL": 0},
        "atr": {"extreme": 0, "high": 0, "medium": 0, "low": 0},
        "stoch_overbought": 0,
        "stoch_oversold": 0,
    }


class Phase1MetricsProvider:
    """
    Provides Phase 1 performance metrics from real-time signal aggregation

    Tracks actual filter results from CoreAggregator including:
    - Gatekeeper: trend blocking, trend types (bullish/bearish/neutral)
    - Validator: volume confirmation/rejection, volume strength
    - ATR: volatility levels (extreme/high/medium/low)
    - Vote counts: buy/sell/hold distribution
    """

    # Display-only history (timeline / latest signal). Bounded — never
    # used for counting.
    _signal_history: deque = deque(maxlen=1000)

    # Single source of truth for all counters: minute buckets of
    # (bucket_start_utc, counters). Pruned at WINDOW_RETENTION_HOURS.
    _window_buckets: deque = deque()

    # True lifetime signal count (monotonic, uncapped).
    _lifetime_signals: int = 0

    _last_signal_time: Optional[datetime] = None
    _is_active: bool = True  # Assume system is active by default

    def __init__(self, log_file: str = "/tmp/trading-engine-phase1.log"):
        """
        Initialize metrics provider

        Args:
            log_file: Path to Phase 1 log file (legacy, kept for compatibility)
        """
        self.log_file = log_file

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    @classmethod
    def _bucket_for(cls, ts: datetime) -> Dict:
        """Get (creating if needed) the minute bucket for `ts`."""
        bucket_start = ts.replace(second=0, microsecond=0)
        if cls._window_buckets and cls._window_buckets[-1][0] == bucket_start:
            return cls._window_buckets[-1][1]
        counters = _new_bucket_counters()
        cls._window_buckets.append((bucket_start, counters))
        cls._prune_buckets(ts)
        return counters

    @classmethod
    def _prune_buckets(cls, now: datetime) -> None:
        """Drop buckets older than the retention window."""
        cutoff = now - timedelta(hours=WINDOW_RETENTION_HOURS)
        while cls._window_buckets and cls._window_buckets[0][0] < cutoff:
            cls._window_buckets.popleft()

    @classmethod
    def record_signal(
        cls,
        action: str,
        confidence: float,
        filters: Dict = None,
        metadata: Dict = None,
        recorded_at: Optional[datetime] = None,
    ):
        """
        Record a signal for metrics tracking with real filter data

        Args:
            action: Signal action (BUY, SELL, HOLD)
            confidence: Signal confidence score
            filters: Filter results with detailed gatekeeper/validator info:
                - gatekeeper: bool (passed/blocked)
                - gatekeeper_reason: str (reason for blocking/passing)
                - trend: str (BULLISH/BEARISH/NEUTRAL)
                - trend_confidence: float
                - trend_blocked: bool
                - validator: bool (confirmed/rejected)
                - validator_reason: str
                - volume_strength: str (STRONG/MODERATE/WEAK/MINIMAL)
                - volume_penalty: float
            metadata: Additional signal metadata (atr_data, vote_counts, etc.)
            recorded_at: Override the record timestamp (testing only).
                Naive values are treated as UTC.
        """
        filters = filters or {}
        metadata = metadata or {}
        now = _ensure_utc(recorded_at) if recorded_at else _utc_now()

        gatekeeper_passed = filters.get("gatekeeper", True)
        trend = filters.get("trend", "NEUTRAL")
        trend_blocked = filters.get("trend_blocked", False)
        validator_confirmed = filters.get("validator", True)
        volume_strength = filters.get("volume_strength", "UNKNOWN")

        action_str = action.upper() if isinstance(action, str) else action.value.upper()

        bucket = cls._bucket_for(now)

        # Signal action counts
        bucket["total"] += 1
        if action_str == "BUY":
            bucket["buy"] += 1
        elif action_str == "SELL":
            bucket["sell"] += 1
        else:
            bucket["hold"] += 1

        # Gatekeeper counts
        if trend_blocked:
            bucket["gk_blocks"] += 1
        else:
            bucket["gk_passed"] += 1

        # Trend distribution
        if trend == "BULLISH":
            bucket["bullish"] += 1
        elif trend == "BEARISH":
            bucket["bearish"] += 1
        else:
            bucket["neutral"] += 1

        # Validator counts
        if validator_confirmed:
            bucket["val_confirmed"] += 1
        else:
            bucket["val_rejected"] += 1

        # Volume strength distribution
        if volume_strength in bucket["strength"]:
            bucket["strength"][volume_strength] += 1

        # ATR stats (technical-analysis returns UPPERCASE volatility)
        atr_data = metadata.get("atr", {})
        if atr_data:
            volatility = atr_data.get("volatility", "medium")
            volatility_lower = volatility.lower() if isinstance(volatility, str) else "medium"
            if volatility_lower in bucket["atr"]:
                bucket["atr"][volatility_lower] += 1

        # Stochastic stats (UPPERCASE condition from technical-analysis)
        stochastic_condition = metadata.get("stochastic_condition", "")
        if stochastic_condition:
            condition_lower = (
                stochastic_condition.lower() if isinstance(stochastic_condition, str) else ""
            )
            if condition_lower == "overbought":
                bucket["stoch_overbought"] += 1
            elif condition_lower == "oversold":
                bucket["stoch_oversold"] += 1

        cls._lifetime_signals += 1

        # Store the signal for the timeline (display only, bounded)
        cls._signal_history.append(
            {
                "timestamp": now.isoformat(),
                "action": action_str,
                "confidence": confidence,
                "filters": {
                    "gatekeeper": gatekeeper_passed and not trend_blocked,
                    "gatekeeper_reason": filters.get("gatekeeper_reason", ""),
                    "trend_direction": trend,
                    "trend_blocked": trend_blocked,
                    "validator": validator_confirmed,
                    "validator_reason": filters.get("validator_reason", ""),
                    "volume_strength": volume_strength,
                    "volume_penalty": filters.get("volume_penalty", 1.0),
                    "atr": bool(atr_data),
                    "trend": True,  # Backward compatibility with dashboard
                },
                "metadata": {
                    "buy_count": metadata.get("buy_count", 0),
                    "sell_count": metadata.get("sell_count", 0),
                    "hold_count": metadata.get("hold_count", 0),
                    "consensus_count": metadata.get("consensus_count", 0),
                    "meets_requirements": metadata.get("meets_requirements", False),
                    "aggregated_score": metadata.get("aggregated_score", 0),
                },
            }
        )
        if cls._last_signal_time is None or now > cls._last_signal_time:
            cls._last_signal_time = now
        cls._is_active = True

        logger.debug(
            f"Recorded signal: {action_str} (conf={confidence:.2f}, "
            f"gatekeeper={'BLOCKED' if trend_blocked else 'PASSED'}, "
            f"validator="
            f"{'CONFIRMED' if validator_confirmed else 'REJECTED'})"
        )

    # ------------------------------------------------------------------
    # Single source of truth for windowed counts and rates
    # ------------------------------------------------------------------

    @classmethod
    def _windowed_totals(cls, hours: int) -> Dict:
        """Sum bucket counters for the last `hours` hours.

        This is the ONE windowed source every endpoint counter derives
        from. Windows larger than WINDOW_RETENTION_HOURS are truncated
        to retention.
        """
        # Prune only fires in record_signal; clamp so hours > retention
        # cannot count stale buckets when signal flow stops.
        hours = min(hours, WINDOW_RETENTION_HOURS)
        # Cutoff floors to the minute grid so the boundary bucket counts:
        # window is bucket-grid-aligned, may over-include up to 59s — never
        # undercounts.
        cutoff = (_utc_now() - timedelta(hours=hours)).replace(second=0, microsecond=0)
        totals = _new_bucket_counters()
        for bucket_start, counters in cls._window_buckets:
            if bucket_start < cutoff:
                continue
            for key, value in counters.items():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        totals[key][sub_key] += sub_value
                else:
                    totals[key] += value
        return totals

    @staticmethod
    def _rate_pct(part: int, whole: int) -> float:
        """THE rate formula: part/whole as a percent, 0.0 when empty.

        Used by both /metrics and /health so the same quantity can never
        be computed two different ways again.
        """
        return (part / whole * 100) if whole > 0 else 0.0

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    def get_metrics(self, hours: int = 24) -> Dict:
        """
        Get Phase 1 metrics for the specified time window.

        Every counter is derived from the same windowed bucket source,
        so signals/gatekeeper/validator/atr totals are mutually
        consistent and actually change with `hours`.

        Args:
            hours: Number of hours to analyze

        Returns:
            Dictionary with real, windowed metrics
        """
        totals = self._windowed_totals(hours)
        total_signals = totals["total"]

        metrics = {
            "period_hours": hours,
            "signals": {
                "total": total_signals,
                "buy": totals["buy"],
                "sell": totals["sell"],
                "hold": totals["hold"],
            },
            "gatekeeper": {
                "blocks": totals["gk_blocks"],
                "passed": totals["gk_passed"],
                "bullish_trends": totals["bullish"],
                "bearish_trends": totals["bearish"],
                "neutral_trends": totals["neutral"],
            },
            "validator": {
                "confirmed": totals["val_confirmed"],
                "rejected": totals["val_rejected"],
                "strength_distribution": dict(totals["strength"]),
            },
            "atr": dict(totals["atr"]),
            "stochastic": {
                "overbought": totals["stoch_overbought"],
                "oversold": totals["stoch_oversold"],
            },
            "filtering": {
                "hold_rate": self._rate_pct(totals["hold"], total_signals),
                "action_rate": self._rate_pct(totals["buy"] + totals["sell"], total_signals),
                "reduction_rate": self._rate_pct(totals["hold"], total_signals),
                "gatekeeper_block_rate": self._rate_pct(
                    totals["gk_blocks"],
                    totals["gk_blocks"] + totals["gk_passed"],
                ),
                "validator_rejection_rate": self._rate_pct(
                    totals["val_rejected"],
                    totals["val_rejected"] + totals["val_confirmed"],
                ),
            },
            "timeline": self._build_timeline(hours),
        }
        return metrics

    def _build_timeline(self, hours: int) -> list:
        """Recent-signal timeline (display only; capped at 20 entries)."""
        cutoff = _utc_now() - timedelta(hours=hours)
        timeline = []
        for signal in self._signal_history:
            try:
                signal_time = _ensure_utc(datetime.fromisoformat(signal["timestamp"]))
                if signal_time < cutoff:
                    continue
                filters = signal.get("filters", {})
                timeline.append(
                    {
                        "timestamp": signal_time.isoformat(),
                        "action": signal.get("action", "HOLD"),
                        "confidence": signal.get("confidence"),
                        "filters": {
                            "gatekeeper": filters.get("gatekeeper", True),
                            "validator": filters.get("validator", True),
                            "atr": filters.get("atr", False),
                            "trend": True,  # Backward compatible
                        },
                        "details": {
                            "trend": filters.get("trend_direction", "NEUTRAL"),
                            "trend_blocked": filters.get("trend_blocked", False),
                            "volume_strength": filters.get("volume_strength", "UNKNOWN"),
                            "volume_penalty": filters.get("volume_penalty", 1.0),
                        },
                        "metadata": signal.get("metadata", {}),
                    }
                )
            except Exception as e:
                logger.debug(f"Error processing signal: {e}")
                continue

        return sorted(timeline, key=lambda x: x["timestamp"], reverse=True)[:20]

    def _add_timeline_entry(self, metrics: Dict, timestamp: datetime, action: str, line: str):
        """Add entry to timeline (legacy log-parsing helper)."""
        entry = {
            "timestamp": _iso_utc(timestamp),
            "action": action,
            "confidence": self._extract_confidence(line),
            "filters": self._extract_filters(line),
        }
        metrics["timeline"].append(entry)

    def _extract_confidence(self, line: str) -> Optional[float]:
        """Extract confidence score from log line"""
        match = re.search(r"confidence[:\s]+(\d+\.?\d*)", line, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def _extract_filters(self, line: str) -> Dict[str, bool]:
        """Extract filter pass/fail from log line"""
        return {
            "gatekeeper": "GATEKEEPER" in line and "PASSED" in line,
            "validator": "VALIDATOR" in line and "confirmed" in line,
            "atr": "ATR" in line,
            "trend": "Trend" in line,
        }

    def get_latest_signal(self) -> Optional[Dict]:
        """Get the most recent signal"""
        timeline = self._build_timeline(hours=WINDOW_RETENTION_HOURS)
        if timeline:
            return timeline[0]
        return None

    def get_system_health(self) -> Dict:
        """
        Get Phase 1 system health status based on actual trading activity.

        filter_stats derive from the same windowed source as
        `get_metrics(hours=24)` (window declared in `window_hours`), so
        the two endpoints can never disagree on the same quantity.
        `signals_last_hour` is a true 1-hour count (not capped by the
        display deque); `total_signals_processed` is a true lifetime
        count.
        """
        signals_last_hour = self._windowed_totals(1)["total"]
        totals = self._windowed_totals(24)

        total_gatekeeper = totals["gk_passed"] + totals["gk_blocks"]
        total_validator = totals["val_confirmed"] + totals["val_rejected"]

        has_recent_activity = (
            self._is_active
            or signals_last_hour > 0
            or (
                self._last_signal_time is not None
                and (_utc_now() - _ensure_utc(self._last_signal_time)).total_seconds() < 3600
            )
        )

        latest = self._signal_history[-1] if self._signal_history else None

        return {
            "status": "healthy" if has_recent_activity else "warning",
            "last_signal_time": (
                _iso_utc(self._last_signal_time)
                if self._last_signal_time
                else (_iso_utc(latest["timestamp"]) if latest else None)
            ),
            "signals_last_hour": signals_last_hour,
            "total_signals_processed": self._lifetime_signals,
            "filters_active": {
                "gatekeeper": total_gatekeeper > 0 or self._is_active,
                "validator": total_validator > 0 or self._is_active,
                "atr": sum(totals["atr"].values()) > 0 or self._is_active,
            },
            "filter_stats": {
                "window_hours": 24,
                "gatekeeper": {
                    "total_processed": total_gatekeeper,
                    "blocks": totals["gk_blocks"],
                    "passed": totals["gk_passed"],
                    "block_rate": self._rate_pct(
                        totals["gk_blocks"],
                        totals["gk_blocks"] + totals["gk_passed"],
                    ),
                },
                "validator": {
                    "total_processed": total_validator,
                    "confirmed": totals["val_confirmed"],
                    "rejected": totals["val_rejected"],
                    "rejection_rate": self._rate_pct(totals["val_rejected"], total_validator),
                },
                "trend_distribution": {
                    "bullish": totals["bullish"],
                    "bearish": totals["bearish"],
                    "neutral": totals["neutral"],
                },
            },
        }

    @classmethod
    def set_active(cls, active: bool = True):
        """Set the system active status"""
        cls._is_active = active

    @classmethod
    def reset_stats(cls):
        """
        Reset all statistics counters

        Useful for testing or starting fresh monitoring session
        """
        cls._window_buckets.clear()
        cls._signal_history.clear()
        cls._lifetime_signals = 0
        cls._last_signal_time = None
        logger.info("Phase1MetricsProvider stats reset")


# Singleton instance
_provider: Optional[Phase1MetricsProvider] = None


def get_phase1_metrics() -> Phase1MetricsProvider:
    """Get Phase 1 metrics provider instance"""
    global _provider
    if _provider is None:
        _provider = Phase1MetricsProvider()
    return _provider
