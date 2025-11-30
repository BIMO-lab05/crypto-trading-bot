"""
Phase 1 Metrics Provider
Exposes Phase 1 monitoring data via API
Uses in-memory signal history with real filter data from CoreAggregator
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
from collections import deque

logger = logging.getLogger(__name__)


class Phase1MetricsProvider:
    """
    Provides Phase 1 performance metrics from real-time signal aggregation

    UPDATED: Now tracks actual filter results from CoreAggregator including:
    - Gatekeeper: trend blocking, trend types (bullish/bearish/neutral)
    - Validator: volume confirmation/rejection, volume strength
    - ATR: volatility levels (extreme/high/medium/low)
    - Vote counts: buy/sell/hold distribution
    """

    # Class-level signal storage (survives instance recreation)
    _signal_history: deque = deque(maxlen=1000)  # Store last 1000 signals
    _last_signal_time: Optional[datetime] = None
    _is_active: bool = True  # Assume system is active by default

    # Real-time aggregation statistics from CoreAggregator
    _gatekeeper_stats: Dict = {
        "blocks": 0,
        "passed": 0,
        "penalized": 0,
        "bullish_trends": 0,
        "bearish_trends": 0,
        "neutral_trends": 0
    }
    _validator_stats: Dict = {
        "confirmed": 0,
        "rejected": 0,
        "strength_distribution": {
            "STRONG": 0,
            "MODERATE": 0,
            "WEAK": 0,
            "MINIMAL": 0
        }
    }
    _atr_stats: Dict = {
        "extreme": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    }
    _stochastic_stats: Dict = {
        "overbought": 0,
        "oversold": 0
    }

    def __init__(self, log_file: str = "/tmp/trading-engine-phase1.log"):
        """
        Initialize metrics provider

        Args:
            log_file: Path to Phase 1 log file (legacy, kept for compatibility)
        """
        self.log_file = log_file

    @classmethod
    def record_signal(
        cls,
        action: str,
        confidence: float,
        filters: Dict = None,
        metadata: Dict = None
    ):
        """
        Record a signal for metrics tracking with real filter data

        UPDATED: Now accepts detailed filter results from CoreAggregator

        Args:
            action: Signal action (BUY, SELL, HOLD)
            confidence: Signal confidence score
            filters: Filter results with detailed gatekeeper/validator info:
                - gatekeeper: bool (passed/blocked)
                - gatekeeper_reason: str (reason for blocking/passing)
                - trend: str (BULLISH/BEARISH/NEUTRAL)
                - trend_confidence: float
                - validator: bool (confirmed/rejected)
                - validator_reason: str
                - volume_strength: str (STRONG/MODERATE/WEAK/MINIMAL)
                - volume_penalty: float
            metadata: Additional signal metadata (atr_data, vote_counts, etc.)
        """
        # Extract filter info with defaults
        filters = filters or {}
        metadata = metadata or {}

        # Extract gatekeeper details
        gatekeeper_passed = filters.get("gatekeeper", True)
        trend = filters.get("trend", "NEUTRAL")
        trend_blocked = filters.get("trend_blocked", False)

        # Extract validator details
        validator_confirmed = filters.get("validator", True)
        volume_strength = filters.get("volume_strength", "UNKNOWN")

        # Update gatekeeper stats
        if trend_blocked:
            cls._gatekeeper_stats["blocks"] += 1
        else:
            cls._gatekeeper_stats["passed"] += 1

        # Update trend type counts
        if trend == "BULLISH":
            cls._gatekeeper_stats["bullish_trends"] += 1
        elif trend == "BEARISH":
            cls._gatekeeper_stats["bearish_trends"] += 1
        else:
            cls._gatekeeper_stats["neutral_trends"] += 1

        # Update validator stats
        if validator_confirmed:
            cls._validator_stats["confirmed"] += 1
        else:
            cls._validator_stats["rejected"] += 1

        # Update volume strength distribution
        if volume_strength in cls._validator_stats["strength_distribution"]:
            cls._validator_stats["strength_distribution"][volume_strength] += 1

        # Update ATR stats if available
        # Note: technical-analysis returns UPPERCASE volatility (LOW, MEDIUM, HIGH, EXTREME)
        atr_data = metadata.get("atr", {})
        if atr_data:
            volatility = atr_data.get("volatility", "medium")
            # Convert to lowercase for consistent tracking
            volatility_lower = volatility.lower() if isinstance(volatility, str) else "medium"
            if volatility_lower in ["extreme", "high", "medium", "low"]:
                cls._atr_stats[volatility_lower] += 1

        # Update Stochastic stats if available
        # Note: technical-analysis returns UPPERCASE condition (OVERBOUGHT, OVERSOLD, NEUTRAL)
        stochastic_condition = metadata.get("stochastic_condition", "")
        if stochastic_condition:
            condition_lower = stochastic_condition.lower() if isinstance(stochastic_condition, str) else ""
            if condition_lower == "overbought":
                cls._stochastic_stats["overbought"] += 1
            elif condition_lower == "oversold":
                cls._stochastic_stats["oversold"] += 1

        # Store the signal with full details
        cls._signal_history.append({
            "timestamp": datetime.now().isoformat(),
            "action": action.upper() if isinstance(action, str) else action.value.upper(),
            "confidence": confidence,
            "filters": {
                "gatekeeper": gatekeeper_passed and not trend_blocked,
                "gatekeeper_reason": filters.get("gatekeeper_reason", ""),
                "trend_direction": trend,  # Actual trend direction (BULLISH/BEARISH/NEUTRAL)
                "trend_blocked": trend_blocked,
                "validator": validator_confirmed,
                "validator_reason": filters.get("validator_reason", ""),
                "volume_strength": volume_strength,
                "volume_penalty": filters.get("volume_penalty", 1.0),
                "atr": bool(atr_data),
                "trend": True  # For backward compatibility with dashboard
            },
            "metadata": {
                "buy_count": metadata.get("buy_count", 0),
                "sell_count": metadata.get("sell_count", 0),
                "hold_count": metadata.get("hold_count", 0),
                "consensus_count": metadata.get("consensus_count", 0),
                "meets_requirements": metadata.get("meets_requirements", False),
                "aggregated_score": metadata.get("aggregated_score", 0)
            }
        })
        cls._last_signal_time = datetime.now()
        cls._is_active = True

        logger.debug(
            f"Recorded signal: {action} (conf={confidence:.2f}, "
            f"gatekeeper={'BLOCKED' if trend_blocked else 'PASSED'}, "
            f"validator={'CONFIRMED' if validator_confirmed else 'REJECTED'})"
        )

    def get_metrics(self, hours: int = 24) -> Dict:
        """
        Get Phase 1 metrics for specified time period from in-memory history

        UPDATED: Uses real aggregation stats from CoreAggregator

        Args:
            hours: Number of hours to analyze

        Returns:
            Dictionary with real metrics from signal aggregation
        """
        # Initialize metrics with real stats from class-level counters
        metrics = {
            "period_hours": hours,
            "signals": {
                "total": 0,
                "buy": 0,
                "sell": 0,
                "hold": 0
            },
            # Use real gatekeeper stats
            "gatekeeper": {
                "blocks": self._gatekeeper_stats["blocks"],
                "passed": self._gatekeeper_stats["passed"],
                "penalized": self._gatekeeper_stats.get("penalized", 0),
                "bullish_trends": self._gatekeeper_stats["bullish_trends"],
                "bearish_trends": self._gatekeeper_stats["bearish_trends"],
                "neutral_trends": self._gatekeeper_stats["neutral_trends"]
            },
            # Use real validator stats
            "validator": {
                "confirmed": self._validator_stats["confirmed"],
                "rejected": self._validator_stats["rejected"],
                "strength_distribution": self._validator_stats.get("strength_distribution", {})
            },
            # Use real ATR stats
            "atr": {
                "extreme": self._atr_stats["extreme"],
                "high": self._atr_stats["high"],
                "medium": self._atr_stats["medium"],
                "low": self._atr_stats["low"]
            },
            # Use real stochastic stats
            "stochastic": {
                "overbought": self._stochastic_stats["overbought"],
                "oversold": self._stochastic_stats["oversold"]
            },
            "filtering": {
                "hold_rate": 0.0,
                "action_rate": 0.0,
                "reduction_rate": 0.0,
                "gatekeeper_block_rate": 0.0,
                "validator_rejection_rate": 0.0
            },
            "timeline": []
        }

        try:
            # Calculate cutoff time
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # Process in-memory signal history for time-filtered counts
            time_filtered_signals = {
                "total": 0, "buy": 0, "sell": 0, "hold": 0,
                "gatekeeper_blocks": 0, "validator_rejections": 0,
                "bullish": 0, "bearish": 0, "neutral": 0
            }

            for signal in self._signal_history:
                try:
                    signal_time = datetime.fromisoformat(signal["timestamp"])
                    if signal_time < cutoff_time:
                        continue

                    action = signal.get("action", "HOLD")
                    if hasattr(action, 'value'):
                        action = action.value
                    action = action.upper()

                    # Count signals
                    time_filtered_signals["total"] += 1
                    if action == "BUY":
                        time_filtered_signals["buy"] += 1
                    elif action == "SELL":
                        time_filtered_signals["sell"] += 1
                    else:
                        time_filtered_signals["hold"] += 1

                    # Extract real filter info from signal
                    filters = signal.get("filters", {})

                    # Count gatekeeper blocks (from real data)
                    if filters.get("trend_blocked", False):
                        time_filtered_signals["gatekeeper_blocks"] += 1

                    # Count trend types (use trend_direction for actual trend)
                    trend = filters.get("trend_direction", "NEUTRAL")
                    if trend == "BULLISH":
                        time_filtered_signals["bullish"] += 1
                    elif trend == "BEARISH":
                        time_filtered_signals["bearish"] += 1
                    else:
                        time_filtered_signals["neutral"] += 1

                    # Count validator rejections (from real data)
                    if not filters.get("validator", True):
                        time_filtered_signals["validator_rejections"] += 1

                    # Add to timeline with real filter data
                    metrics["timeline"].append({
                        "timestamp": signal["timestamp"],
                        "action": action,
                        "confidence": signal.get("confidence"),
                        "filters": {
                            "gatekeeper": filters.get("gatekeeper", True),
                            "validator": filters.get("validator", True),
                            "atr": filters.get("atr", False),
                            "trend": True  # Backward compatible
                        },
                        "details": {
                            "trend": filters.get("trend_direction", "NEUTRAL"),
                            "trend_blocked": filters.get("trend_blocked", False),
                            "volume_strength": filters.get("volume_strength", "UNKNOWN"),
                            "volume_penalty": filters.get("volume_penalty", 1.0)
                        },
                        "metadata": signal.get("metadata", {})
                    })

                except Exception as e:
                    logger.debug(f"Error processing signal: {e}")
                    continue

            # Update signal counts with time-filtered data
            metrics["signals"] = {
                "total": time_filtered_signals["total"],
                "buy": time_filtered_signals["buy"],
                "sell": time_filtered_signals["sell"],
                "hold": time_filtered_signals["hold"]
            }

            # Update time-filtered gatekeeper/validator counts
            if time_filtered_signals["total"] > 0:
                metrics["gatekeeper"]["blocks"] = time_filtered_signals["gatekeeper_blocks"]
                metrics["gatekeeper"]["bullish_trends"] = time_filtered_signals["bullish"]
                metrics["gatekeeper"]["bearish_trends"] = time_filtered_signals["bearish"]
                metrics["gatekeeper"]["neutral_trends"] = time_filtered_signals["neutral"]

            # Calculate filtering rates from real data
            total_signals = time_filtered_signals["total"]
            if total_signals > 0:
                metrics["filtering"]["hold_rate"] = (
                    time_filtered_signals["hold"] / total_signals
                ) * 100
                metrics["filtering"]["action_rate"] = (
                    (time_filtered_signals["buy"] + time_filtered_signals["sell"]) / total_signals
                ) * 100
                metrics["filtering"]["reduction_rate"] = metrics["filtering"]["hold_rate"]
                metrics["filtering"]["gatekeeper_block_rate"] = (
                    time_filtered_signals["gatekeeper_blocks"] / total_signals
                ) * 100
                metrics["filtering"]["validator_rejection_rate"] = (
                    time_filtered_signals["validator_rejections"] / total_signals
                ) * 100

            # Sort timeline by most recent first
            metrics["timeline"] = sorted(
                metrics["timeline"],
                key=lambda x: x["timestamp"],
                reverse=True
            )[:20]

            return metrics

        except Exception as e:
            logger.error(f"Error getting Phase 1 metrics: {e}")
            return metrics

    def _add_timeline_entry(self, metrics: Dict, timestamp: datetime, action: str, line: str):
        """Add entry to timeline"""
        entry = {
            "timestamp": timestamp.isoformat(),
            "action": action,
            "confidence": self._extract_confidence(line),
            "filters": self._extract_filters(line)
        }
        metrics["timeline"].append(entry)

    def _extract_confidence(self, line: str) -> Optional[float]:
        """Extract confidence score from log line"""
        match = re.search(r'confidence[:\s]+(\d+\.?\d*)', line, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def _extract_filters(self, line: str) -> Dict[str, bool]:
        """Extract filter pass/fail from log line"""
        return {
            "gatekeeper": "GATEKEEPER" in line and "PASSED" in line,
            "validator": "VALIDATOR" in line and "confirmed" in line,
            "atr": "ATR" in line,
            "trend": "Trend" in line
        }

    def get_latest_signal(self) -> Optional[Dict]:
        """Get the most recent signal"""
        metrics = self.get_metrics(hours=24)
        if metrics["timeline"]:
            return metrics["timeline"][0]
        return None

    def get_system_health(self) -> Dict:
        """
        Get Phase 1 system health status based on actual trading activity

        UPDATED: Shows real filter statistics and activity status
        """
        metrics = self.get_metrics(hours=1)  # Last hour

        # System is healthy if:
        # 1. Trading is marked as active, OR
        # 2. We have signals in the last hour, OR
        # 3. We have a recent last_signal_time
        has_recent_activity = (
            self._is_active or
            metrics["signals"]["total"] > 0 or
            (self._last_signal_time and
             (datetime.now() - self._last_signal_time).total_seconds() < 3600)
        )

        # Calculate total signals processed
        total_gatekeeper = (
            self._gatekeeper_stats["passed"] +
            self._gatekeeper_stats["blocks"] +
            self._gatekeeper_stats.get("penalized", 0)
        )
        total_validator = (
            self._validator_stats["confirmed"] +
            self._validator_stats["rejected"]
        )

        return {
            "status": "healthy" if has_recent_activity else "warning",
            "last_signal_time": (
                self._last_signal_time.isoformat() if self._last_signal_time
                else (metrics["timeline"][0]["timestamp"] if metrics["timeline"] else None)
            ),
            "signals_last_hour": metrics["signals"]["total"],
            "total_signals_processed": len(self._signal_history),
            "filters_active": {
                # Show actual filter activity based on real stats
                "gatekeeper": total_gatekeeper > 0 or self._is_active,
                "validator": total_validator > 0 or self._is_active,
                "atr": sum(self._atr_stats.values()) > 0 or self._is_active
            },
            # Add real-time filter statistics
            "filter_stats": {
                "gatekeeper": {
                    "total_processed": total_gatekeeper,
                    "blocks": self._gatekeeper_stats["blocks"],
                    "passed": self._gatekeeper_stats["passed"],
                    "block_rate": (
                        self._gatekeeper_stats["blocks"] / total_gatekeeper * 100
                        if total_gatekeeper > 0 else 0.0
                    )
                },
                "validator": {
                    "total_processed": total_validator,
                    "confirmed": self._validator_stats["confirmed"],
                    "rejected": self._validator_stats["rejected"],
                    "rejection_rate": (
                        self._validator_stats["rejected"] / total_validator * 100
                        if total_validator > 0 else 0.0
                    )
                },
                "trend_distribution": {
                    "bullish": self._gatekeeper_stats["bullish_trends"],
                    "bearish": self._gatekeeper_stats["bearish_trends"],
                    "neutral": self._gatekeeper_stats["neutral_trends"]
                }
            }
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
        cls._gatekeeper_stats = {
            "blocks": 0,
            "passed": 0,
            "penalized": 0,
            "bullish_trends": 0,
            "bearish_trends": 0,
            "neutral_trends": 0
        }
        cls._validator_stats = {
            "confirmed": 0,
            "rejected": 0,
            "strength_distribution": {
                "STRONG": 0,
                "MODERATE": 0,
                "WEAK": 0,
                "MINIMAL": 0
            }
        }
        cls._atr_stats = {
            "extreme": 0,
            "high": 0,
            "medium": 0,
            "low": 0
        }
        cls._stochastic_stats = {
            "overbought": 0,
            "oversold": 0
        }
        cls._signal_history.clear()
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
