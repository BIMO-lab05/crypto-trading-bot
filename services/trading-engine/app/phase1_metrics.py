"""
Phase 1 Metrics Provider
Exposes Phase 1 monitoring data via API
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Phase1MetricsProvider:
    """Provides Phase 1 performance metrics from logs"""

    def __init__(self, log_file: str = "/tmp/trading-engine-phase1.log"):
        """
        Initialize metrics provider

        Args:
            log_file: Path to Phase 1 log file
        """
        self.log_file = log_file

    def get_metrics(self, hours: int = 24) -> Dict:
        """
        Get Phase 1 metrics for specified time period

        Args:
            hours: Number of hours to analyze

        Returns:
            Dictionary with metrics
        """
        metrics = {
            "period_hours": hours,
            "signals": {
                "total": 0,
                "buy": 0,
                "sell": 0,
                "hold": 0
            },
            "gatekeeper": {
                "blocks": 0,
                "bullish_trends": 0,
                "bearish_trends": 0,
                "neutral_trends": 0
            },
            "validator": {
                "confirmed": 0,
                "rejected": 0
            },
            "atr": {
                "extreme": 0,
                "high": 0,
                "medium": 0,
                "low": 0
            },
            "stochastic": {
                "overbought": 0,
                "oversold": 0
            },
            "filtering": {
                "hold_rate": 0.0,
                "action_rate": 0.0,
                "reduction_rate": 0.0
            },
            "timeline": []  # Recent signals with timestamps
        }

        try:
            log_path = Path(self.log_file)
            if not log_path.exists():
                logger.warning(f"Log file not found: {self.log_file}")
                return metrics

            # Calculate cutoff time
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # Read and parse log file
            with open(self.log_file, 'r') as f:
                lines = f.readlines()

            for line in lines:
                try:
                    # Extract timestamp from log line
                    timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match:
                        continue

                    log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')

                    # Skip if outside time window
                    if log_time < cutoff_time:
                        continue

                    # Parse signal actions
                    if "Signal generated:" in line:
                        if "BUY" in line:
                            metrics["signals"]["buy"] += 1
                            metrics["signals"]["total"] += 1
                            self._add_timeline_entry(metrics, log_time, "BUY", line)
                        elif "SELL" in line:
                            metrics["signals"]["sell"] += 1
                            metrics["signals"]["total"] += 1
                            self._add_timeline_entry(metrics, log_time, "SELL", line)
                        elif "HOLD" in line:
                            metrics["signals"]["hold"] += 1
                            metrics["signals"]["total"] += 1
                            self._add_timeline_entry(metrics, log_time, "HOLD", line)

                    # Parse GATEKEEPER
                    if "GATEKEEPER" in line or "Trend Filter" in line:
                        if "BLOCKED" in line or "Counter-trend" in line:
                            metrics["gatekeeper"]["blocks"] += 1
                        if "BULLISH" in line:
                            metrics["gatekeeper"]["bullish_trends"] += 1
                        elif "BEARISH" in line:
                            metrics["gatekeeper"]["bearish_trends"] += 1
                        elif "NEUTRAL" in line:
                            metrics["gatekeeper"]["neutral_trends"] += 1

                    # Parse VALIDATOR
                    if "VALIDATOR" in line or "Volume" in line:
                        # Check for rejection first (before generic "confirmed")
                        if "NOT confirmed" in line or "rejected" in line.lower():
                            metrics["validator"]["rejected"] += 1
                        elif "confirmed" in line.lower():
                            metrics["validator"]["confirmed"] += 1

                    # Parse ATR volatility
                    if "ATR" in line:
                        if "EXTREME" in line:
                            metrics["atr"]["extreme"] += 1
                        elif "HIGH" in line:
                            metrics["atr"]["high"] += 1
                        elif "MEDIUM" in line:
                            metrics["atr"]["medium"] += 1
                        elif "LOW" in line:
                            metrics["atr"]["low"] += 1

                    # Parse Stochastic
                    if "Stochastic" in line:
                        if "overbought" in line.lower():
                            metrics["stochastic"]["overbought"] += 1
                        elif "oversold" in line.lower():
                            metrics["stochastic"]["oversold"] += 1

                except Exception as e:
                    logger.debug(f"Error parsing log line: {e}")
                    continue

            # Calculate filtering rates
            total_signals = metrics["signals"]["total"]
            if total_signals > 0:
                metrics["filtering"]["hold_rate"] = (metrics["signals"]["hold"] / total_signals) * 100
                metrics["filtering"]["action_rate"] = ((metrics["signals"]["buy"] + metrics["signals"]["sell"]) / total_signals) * 100
                metrics["filtering"]["reduction_rate"] = metrics["filtering"]["hold_rate"]

            # Sort timeline by most recent first
            metrics["timeline"] = sorted(
                metrics["timeline"],
                key=lambda x: x["timestamp"],
                reverse=True
            )[:20]  # Keep only last 20 signals

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
        """Get Phase 1 system health status"""
        metrics = self.get_metrics(hours=1)  # Last hour

        return {
            "status": "healthy" if metrics["signals"]["total"] > 0 else "warning",
            "last_signal_time": metrics["timeline"][0]["timestamp"] if metrics["timeline"] else None,
            "signals_last_hour": metrics["signals"]["total"],
            "filters_active": {
                "gatekeeper": metrics["gatekeeper"]["blocks"] > 0 or metrics["gatekeeper"]["bullish_trends"] > 0,
                "validator": metrics["validator"]["confirmed"] > 0 or metrics["validator"]["rejected"] > 0,
                "atr": sum(metrics["atr"].values()) > 0
            }
        }


# Singleton instance
_provider: Optional[Phase1MetricsProvider] = None


def get_phase1_metrics() -> Phase1MetricsProvider:
    """Get Phase 1 metrics provider instance"""
    global _provider
    if _provider is None:
        _provider = Phase1MetricsProvider()
    return _provider
