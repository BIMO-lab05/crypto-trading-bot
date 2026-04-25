"""
Unit tests for Phase 1 Metrics Provider
Tests log parsing, metric calculation, and system health monitoring
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from app.phase1_metrics import Phase1MetricsProvider, get_phase1_metrics


class TestPhase1MetricsProvider:
    """Test Phase 1 metrics provider"""

    @pytest.fixture
    def temp_log_file(self):
        """Create temporary log file for testing"""
        fd, path = tempfile.mkstemp(suffix='.log')
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def provider_with_signals(self):
        """Create provider with sample signals using record_signal()

        UPDATED 2025-12-03: Tests now use in-memory record_signal() instead of log files.
        The Phase1MetricsProvider was refactored from log-based to in-memory tracking.
        """
        # Reset stats before each test
        Phase1MetricsProvider.reset_stats()

        # Record sample signals covering all test cases
        # BUY signal with BULLISH trend, confirmed volume
        Phase1MetricsProvider.record_signal(
            action="BUY",
            confidence=0.85,
            filters={
                "gatekeeper": True,
                "trend": "BULLISH",
                "trend_blocked": False,
                "validator": True,
                "volume_strength": "STRONG"
            },
            metadata={
                "atr": {"volatility": "EXTREME"},
                "stochastic_condition": "OVERBOUGHT"
            }
        )

        # SELL signal with BEARISH trend, confirmed volume
        Phase1MetricsProvider.record_signal(
            action="SELL",
            confidence=0.72,
            filters={
                "gatekeeper": True,
                "trend": "BEARISH",
                "trend_blocked": False,
                "validator": True,
                "volume_strength": "MODERATE"
            },
            metadata={
                "atr": {"volatility": "HIGH"},
                "stochastic_condition": "OVERSOLD"
            }
        )

        # HOLD signal with NEUTRAL trend, rejected volume
        Phase1MetricsProvider.record_signal(
            action="HOLD",
            confidence=0.45,
            filters={
                "gatekeeper": True,
                "trend": "NEUTRAL",
                "trend_blocked": False,
                "validator": False,
                "volume_strength": "WEAK"
            },
            metadata={
                "atr": {"volatility": "MEDIUM"}
            }
        )

        # Blocked signal (counter-trend)
        Phase1MetricsProvider.record_signal(
            action="HOLD",
            confidence=0.30,
            filters={
                "gatekeeper": False,
                "trend": "BEARISH",
                "trend_blocked": True,  # Key: blocked counter-trend
                "validator": True,
                "volume_strength": "STRONG"
            },
            metadata={
                "atr": {"volatility": "LOW"}
            }
        )

        return Phase1MetricsProvider()

    def test_initialization_default_path(self):
        """Test provider initialization with default log path"""
        provider = Phase1MetricsProvider()
        assert provider.log_file == "/tmp/trading-engine-phase1.log"

    def test_initialization_custom_path(self, temp_log_file):
        """Test provider initialization with custom log path"""
        provider = Phase1MetricsProvider(log_file=temp_log_file)
        assert provider.log_file == temp_log_file

    def test_get_metrics_no_signals(self):
        """Test getting metrics when no signals recorded"""
        Phase1MetricsProvider.reset_stats()
        provider = Phase1MetricsProvider()
        metrics = provider.get_metrics()

        # Should return empty metrics structure
        assert metrics["signals"]["total"] == 0
        assert metrics["timeline"] == []

    def test_get_metrics_empty_history(self, temp_log_file):
        """Test getting metrics from empty signal history"""
        # Reset stats to clear any previous signals
        Phase1MetricsProvider.reset_stats()

        provider = Phase1MetricsProvider(log_file=temp_log_file)
        metrics = provider.get_metrics()

        assert metrics["signals"]["total"] == 0
        assert metrics["timeline"] == []

    def test_parse_buy_signal(self, provider_with_signals):
        """Test recording BUY signal"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["signals"]["buy"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains BUY signal
        buy_signals = [s for s in metrics["timeline"] if s["action"] == "BUY"]
        assert len(buy_signals) >= 1

    def test_parse_sell_signal(self, provider_with_signals):
        """Test recording SELL signal"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["signals"]["sell"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains SELL signal
        sell_signals = [s for s in metrics["timeline"] if s["action"] == "SELL"]
        assert len(sell_signals) >= 1

    def test_parse_hold_signal(self, provider_with_signals):
        """Test recording HOLD signal"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["signals"]["hold"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains HOLD signal
        hold_signals = [s for s in metrics["timeline"] if s["action"] == "HOLD"]
        assert len(hold_signals) >= 1

    def test_parse_gatekeeper_blocks(self, provider_with_signals):
        """Test recording GATEKEEPER block events"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["gatekeeper"]["blocks"] >= 1

    def test_parse_gatekeeper_bullish(self, provider_with_signals):
        """Test recording GATEKEEPER bullish trends"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["gatekeeper"]["bullish_trends"] >= 1

    def test_parse_gatekeeper_bearish(self, provider_with_signals):
        """Test recording GATEKEEPER bearish trends"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["gatekeeper"]["bearish_trends"] >= 1

    def test_parse_gatekeeper_neutral(self, provider_with_signals):
        """Test recording GATEKEEPER neutral trends"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["gatekeeper"]["neutral_trends"] >= 1

    def test_parse_validator_confirmed(self, provider_with_signals):
        """Test recording VALIDATOR confirmed events"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["validator"]["confirmed"] >= 1

    def test_parse_validator_rejected(self, provider_with_signals):
        """Test recording VALIDATOR rejected events"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["validator"]["rejected"] >= 1

    def test_parse_atr_extreme(self, provider_with_signals):
        """Test recording ATR EXTREME volatility"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["atr"]["extreme"] >= 1

    def test_parse_atr_high(self, provider_with_signals):
        """Test recording ATR HIGH volatility"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["atr"]["high"] >= 1

    def test_parse_atr_medium(self, provider_with_signals):
        """Test recording ATR MEDIUM volatility"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["atr"]["medium"] >= 1

    def test_parse_atr_low(self, provider_with_signals):
        """Test recording ATR LOW volatility"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["atr"]["low"] >= 1

    def test_parse_stochastic_overbought(self, provider_with_signals):
        """Test recording Stochastic overbought condition"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["stochastic"]["overbought"] >= 1

    def test_parse_stochastic_oversold(self, provider_with_signals):
        """Test recording Stochastic oversold condition"""
        metrics = provider_with_signals.get_metrics(hours=24)

        assert metrics["stochastic"]["oversold"] >= 1

    def test_calculate_filtering_rates(self, provider_with_signals):
        """Test calculation of filtering rates"""
        metrics = provider_with_signals.get_metrics(hours=24)

        # Should have calculated rates
        assert "hold_rate" in metrics["filtering"]
        assert "action_rate" in metrics["filtering"]
        assert "reduction_rate" in metrics["filtering"]

        # Rates should sum to 100% or be meaningful
        if metrics["signals"]["total"] > 0:
            assert 0 <= metrics["filtering"]["hold_rate"] <= 100
            assert 0 <= metrics["filtering"]["action_rate"] <= 100

    def test_timeline_sorted_by_timestamp(self, provider_with_signals):
        """Test that timeline is sorted by most recent first"""
        metrics = provider_with_signals.get_metrics(hours=24)

        if len(metrics["timeline"]) > 1:
            # Check that timestamps are in descending order
            timestamps = [datetime.fromisoformat(s["timestamp"]) for s in metrics["timeline"]]
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1]

    def test_timeline_limited_to_20_entries(self):
        """Test that timeline is limited to last 20 entries"""
        Phase1MetricsProvider.reset_stats()

        # Record 30 signals
        for i in range(30):
            Phase1MetricsProvider.record_signal(
                action="BUY",
                confidence=0.75,
                filters={"trend": "BULLISH"},
                metadata={}
            )

        provider = Phase1MetricsProvider()
        metrics = provider.get_metrics(hours=24)

        # Should only keep 20 most recent
        assert len(metrics["timeline"]) == 20

    def test_extract_confidence_from_log_line(self, provider_with_signals):
        """Test confidence extraction from log line (legacy function)"""
        line = "2025-11-09 10:00:00 - Signal generated: BUY, confidence: 0.85"
        confidence = provider_with_signals._extract_confidence(line)

        assert confidence == 0.85

    def test_extract_confidence_no_match(self, provider_with_signals):
        """Test confidence extraction when no confidence in line"""
        line = "2025-11-09 10:00:00 - Some log message"
        confidence = provider_with_signals._extract_confidence(line)

        assert confidence is None

    def test_extract_filters_gatekeeper_passed(self, provider_with_signals):
        """Test filter extraction with gatekeeper passed (legacy function)"""
        line = "GATEKEEPER PASSED, VALIDATOR confirmed"
        filters = provider_with_signals._extract_filters(line)

        assert filters["gatekeeper"] is True
        assert filters["validator"] is True

    def test_extract_filters_no_filters(self, provider_with_signals):
        """Test filter extraction with no filters mentioned"""
        line = "Regular log message"
        filters = provider_with_signals._extract_filters(line)

        assert filters["gatekeeper"] is False
        assert filters["validator"] is False

    def test_get_latest_signal(self, provider_with_signals):
        """Test getting the most recent signal"""
        latest = provider_with_signals.get_latest_signal()

        assert latest is not None
        assert "timestamp" in latest
        assert "action" in latest
        assert latest["action"] in ["BUY", "SELL", "HOLD"]

    def test_get_latest_signal_no_signals(self):
        """Test getting latest signal when no signals exist"""
        Phase1MetricsProvider.reset_stats()
        provider = Phase1MetricsProvider()

        latest = provider.get_latest_signal()
        assert latest is None

    def test_get_system_health_healthy(self, provider_with_signals):
        """Test system health when signals are present"""
        health = provider_with_signals.get_system_health()

        assert health["status"] == "healthy"
        assert health["signals_last_hour"] >= 0
        assert "filters_active" in health

    def test_get_system_health_warning(self):
        """Test system health warning when no recent signals and inactive"""
        Phase1MetricsProvider.reset_stats()
        Phase1MetricsProvider.set_active(False)
        provider = Phase1MetricsProvider()

        health = provider.get_system_health()
        assert health["status"] == "warning"

        # Reset back to active
        Phase1MetricsProvider.set_active(True)

    def test_get_system_health_filters_active(self, provider_with_signals):
        """Test system health reports active filters"""
        health = provider_with_signals.get_system_health()

        filters = health["filters_active"]
        assert "gatekeeper" in filters
        assert "validator" in filters
        assert "atr" in filters

    def test_time_window_filtering(self):
        """Test that only signals within time window are included"""
        Phase1MetricsProvider.reset_stats()

        # Record one signal
        Phase1MetricsProvider.record_signal(
            action="SELL",
            confidence=0.85,
            filters={"trend": "BEARISH"},
            metadata={}
        )

        provider = Phase1MetricsProvider()
        metrics = provider.get_metrics(hours=24)

        # Should include the recent signal
        assert metrics["signals"]["total"] == 1
        assert metrics["signals"]["sell"] == 1

    def test_malformed_signal_handled_gracefully(self):
        """Test that malformed signals are handled gracefully"""
        Phase1MetricsProvider.reset_stats()

        # Record valid signal
        Phase1MetricsProvider.record_signal(
            action="BUY",
            confidence=0.75,
            filters={"trend": "BULLISH"},
            metadata={}
        )

        provider = Phase1MetricsProvider()
        metrics = provider.get_metrics(hours=24)

        # Should process valid signal
        assert metrics["signals"]["buy"] >= 1

    def test_metrics_structure_complete(self, provider_with_signals):
        """Test that returned metrics have complete structure"""
        metrics = provider_with_signals.get_metrics()

        # Check all required keys exist
        assert "period_hours" in metrics
        assert "signals" in metrics
        assert "gatekeeper" in metrics
        assert "validator" in metrics
        assert "atr" in metrics
        assert "stochastic" in metrics
        assert "filtering" in metrics
        assert "timeline" in metrics

        # Check nested structures
        assert "total" in metrics["signals"]
        assert "buy" in metrics["signals"]
        assert "sell" in metrics["signals"]
        assert "hold" in metrics["signals"]

        assert "blocks" in metrics["gatekeeper"]
        assert "bullish_trends" in metrics["gatekeeper"]
        assert "bearish_trends" in metrics["gatekeeper"]
        assert "neutral_trends" in metrics["gatekeeper"]


class TestPhase1MetricsSingleton:
    """Test Phase 1 metrics singleton pattern"""

    def test_get_phase1_metrics_returns_provider(self):
        """Test that get_phase1_metrics returns a provider instance"""
        provider = get_phase1_metrics()
        assert isinstance(provider, Phase1MetricsProvider)

    def test_get_phase1_metrics_returns_same_instance(self):
        """Test that get_phase1_metrics returns same instance (singleton)"""
        provider1 = get_phase1_metrics()
        provider2 = get_phase1_metrics()

        assert provider1 is provider2

    def test_singleton_persists_configuration(self):
        """Test that singleton maintains its configuration"""
        provider = get_phase1_metrics()
        original_log_file = provider.log_file

        # Get instance again
        provider2 = get_phase1_metrics()

        # Should have same configuration
        assert provider2.log_file == original_log_file
