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
    def sample_log_content(self):
        """Generate sample log content for testing"""
        now = datetime.now()
        # Generate timestamps within last hour for testing
        t1 = (now - timedelta(minutes=59)).strftime('%Y-%m-%d %H:%M:%S')
        t2 = (now - timedelta(minutes=58)).strftime('%Y-%m-%d %H:%M:%S')
        t3 = (now - timedelta(minutes=57)).strftime('%Y-%m-%d %H:%M:%S')
        t4 = (now - timedelta(minutes=56)).strftime('%Y-%m-%d %H:%M:%S')
        t5 = (now - timedelta(minutes=55)).strftime('%Y-%m-%d %H:%M:%S')
        t6 = (now - timedelta(minutes=54)).strftime('%Y-%m-%d %H:%M:%S')
        t7 = (now - timedelta(minutes=53)).strftime('%Y-%m-%d %H:%M:%S')
        t8 = (now - timedelta(minutes=52)).strftime('%Y-%m-%d %H:%M:%S')
        t9 = (now - timedelta(minutes=51)).strftime('%Y-%m-%d %H:%M:%S')
        t10 = (now - timedelta(minutes=50)).strftime('%Y-%m-%d %H:%M:%S')
        t11 = (now - timedelta(minutes=49)).strftime('%Y-%m-%d %H:%M:%S')
        t12 = (now - timedelta(minutes=48)).strftime('%Y-%m-%d %H:%M:%S')
        t13 = (now - timedelta(minutes=47)).strftime('%Y-%m-%d %H:%M:%S')
        t14 = (now - timedelta(minutes=46)).strftime('%Y-%m-%d %H:%M:%S')
        t15 = (now - timedelta(minutes=45)).strftime('%Y-%m-%d %H:%M:%S')

        return f"""{t1} - Signal generated: BUY, confidence: 0.85
{t2} - Signal generated: SELL, confidence: 0.72
{t3} - Signal generated: HOLD, confidence: 0.45
{t4} - GATEKEEPER: BULLISH trend detected
{t5} - GATEKEEPER: Counter-trend BLOCKED
{t6} - VALIDATOR: Volume confirmed
{t7} - VALIDATOR: Volume NOT confirmed
{t8} - ATR: EXTREME volatility detected
{t9} - ATR: HIGH volatility
{t10} - ATR: MEDIUM volatility
{t11} - ATR: LOW volatility
{t12} - Stochastic: Overbought condition
{t13} - Stochastic: Oversold condition
{t14} - GATEKEEPER: BEARISH trend detected
{t15} - GATEKEEPER: NEUTRAL trend
"""

    @pytest.fixture
    def provider_with_log(self, temp_log_file, sample_log_content):
        """Create provider with sample log content"""
        with open(temp_log_file, 'w') as f:
            f.write(sample_log_content)
        return Phase1MetricsProvider(log_file=temp_log_file)

    def test_initialization_default_path(self):
        """Test provider initialization with default log path"""
        provider = Phase1MetricsProvider()
        assert provider.log_file == "/tmp/trading-engine-phase1.log"

    def test_initialization_custom_path(self, temp_log_file):
        """Test provider initialization with custom log path"""
        provider = Phase1MetricsProvider(log_file=temp_log_file)
        assert provider.log_file == temp_log_file

    def test_get_metrics_nonexistent_file(self):
        """Test getting metrics when log file doesn't exist"""
        provider = Phase1MetricsProvider(log_file="/nonexistent/file.log")
        metrics = provider.get_metrics()

        # Should return empty metrics structure
        assert metrics["signals"]["total"] == 0
        assert metrics["gatekeeper"]["blocks"] == 0
        assert metrics["validator"]["confirmed"] == 0

    def test_get_metrics_empty_file(self, temp_log_file):
        """Test getting metrics from empty log file"""
        # Create empty file
        Path(temp_log_file).touch()

        provider = Phase1MetricsProvider(log_file=temp_log_file)
        metrics = provider.get_metrics()

        assert metrics["signals"]["total"] == 0
        assert metrics["timeline"] == []

    def test_parse_buy_signal(self, provider_with_log):
        """Test parsing BUY signal from log"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["signals"]["buy"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains BUY signal
        buy_signals = [s for s in metrics["timeline"] if s["action"] == "BUY"]
        assert len(buy_signals) >= 1

    def test_parse_sell_signal(self, provider_with_log):
        """Test parsing SELL signal from log"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["signals"]["sell"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains SELL signal
        sell_signals = [s for s in metrics["timeline"] if s["action"] == "SELL"]
        assert len(sell_signals) >= 1

    def test_parse_hold_signal(self, provider_with_log):
        """Test parsing HOLD signal from log"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["signals"]["hold"] >= 1
        assert metrics["signals"]["total"] >= 1

        # Check timeline contains HOLD signal
        hold_signals = [s for s in metrics["timeline"] if s["action"] == "HOLD"]
        assert len(hold_signals) >= 1

    def test_parse_gatekeeper_blocks(self, provider_with_log):
        """Test parsing GATEKEEPER block events"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["gatekeeper"]["blocks"] >= 1

    def test_parse_gatekeeper_bullish(self, provider_with_log):
        """Test parsing GATEKEEPER bullish trends"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["gatekeeper"]["bullish_trends"] >= 1

    def test_parse_gatekeeper_bearish(self, provider_with_log):
        """Test parsing GATEKEEPER bearish trends"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["gatekeeper"]["bearish_trends"] >= 1

    def test_parse_gatekeeper_neutral(self, provider_with_log):
        """Test parsing GATEKEEPER neutral trends"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["gatekeeper"]["neutral_trends"] >= 1

    def test_parse_validator_confirmed(self, provider_with_log):
        """Test parsing VALIDATOR confirmed events"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["validator"]["confirmed"] >= 1

    def test_parse_validator_rejected(self, provider_with_log):
        """Test parsing VALIDATOR rejected events"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["validator"]["rejected"] >= 1

    def test_parse_atr_extreme(self, provider_with_log):
        """Test parsing ATR EXTREME volatility"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["atr"]["extreme"] >= 1

    def test_parse_atr_high(self, provider_with_log):
        """Test parsing ATR HIGH volatility"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["atr"]["high"] >= 1

    def test_parse_atr_medium(self, provider_with_log):
        """Test parsing ATR MEDIUM volatility"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["atr"]["medium"] >= 1

    def test_parse_atr_low(self, provider_with_log):
        """Test parsing ATR LOW volatility"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["atr"]["low"] >= 1

    def test_parse_stochastic_overbought(self, provider_with_log):
        """Test parsing Stochastic overbought condition"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["stochastic"]["overbought"] >= 1

    def test_parse_stochastic_oversold(self, provider_with_log):
        """Test parsing Stochastic oversold condition"""
        metrics = provider_with_log.get_metrics(hours=24)

        assert metrics["stochastic"]["oversold"] >= 1

    def test_calculate_filtering_rates(self, provider_with_log):
        """Test calculation of filtering rates"""
        metrics = provider_with_log.get_metrics(hours=24)

        # Should have calculated rates
        assert "hold_rate" in metrics["filtering"]
        assert "action_rate" in metrics["filtering"]
        assert "reduction_rate" in metrics["filtering"]

        # Rates should sum to 100% or be meaningful
        if metrics["signals"]["total"] > 0:
            assert 0 <= metrics["filtering"]["hold_rate"] <= 100
            assert 0 <= metrics["filtering"]["action_rate"] <= 100

    def test_timeline_sorted_by_timestamp(self, provider_with_log):
        """Test that timeline is sorted by most recent first"""
        metrics = provider_with_log.get_metrics(hours=24)

        if len(metrics["timeline"]) > 1:
            # Check that timestamps are in descending order
            timestamps = [datetime.fromisoformat(s["timestamp"]) for s in metrics["timeline"]]
            for i in range(len(timestamps) - 1):
                assert timestamps[i] >= timestamps[i + 1]

    def test_timeline_limited_to_20_entries(self, temp_log_file):
        """Test that timeline is limited to last 20 entries"""
        # Create log with 30 entries
        now = datetime.now()
        with open(temp_log_file, 'w') as f:
            for i in range(30):
                timestamp = (now - timedelta(minutes=i)).strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp} - Signal generated: BUY, confidence: 0.75\n")

        provider = Phase1MetricsProvider(log_file=temp_log_file)
        metrics = provider.get_metrics(hours=24)

        # Should only keep 20 most recent
        assert len(metrics["timeline"]) == 20

    def test_extract_confidence_from_log_line(self, provider_with_log):
        """Test confidence extraction from log line"""
        line = "2025-11-09 10:00:00 - Signal generated: BUY, confidence: 0.85"
        confidence = provider_with_log._extract_confidence(line)

        assert confidence == 0.85

    def test_extract_confidence_no_match(self, provider_with_log):
        """Test confidence extraction when no confidence in line"""
        line = "2025-11-09 10:00:00 - Some log message"
        confidence = provider_with_log._extract_confidence(line)

        assert confidence is None

    def test_extract_filters_gatekeeper_passed(self, provider_with_log):
        """Test filter extraction with gatekeeper passed"""
        line = "GATEKEEPER PASSED, VALIDATOR confirmed"
        filters = provider_with_log._extract_filters(line)

        assert filters["gatekeeper"] is True
        assert filters["validator"] is True

    def test_extract_filters_no_filters(self, provider_with_log):
        """Test filter extraction with no filters mentioned"""
        line = "Regular log message"
        filters = provider_with_log._extract_filters(line)

        assert filters["gatekeeper"] is False
        assert filters["validator"] is False

    def test_get_latest_signal(self, provider_with_log):
        """Test getting the most recent signal"""
        latest = provider_with_log.get_latest_signal()

        assert latest is not None
        assert "timestamp" in latest
        assert "action" in latest
        assert latest["action"] in ["BUY", "SELL", "HOLD"]

    def test_get_latest_signal_no_signals(self, temp_log_file):
        """Test getting latest signal when no signals exist"""
        Path(temp_log_file).touch()
        provider = Phase1MetricsProvider(log_file=temp_log_file)

        latest = provider.get_latest_signal()
        assert latest is None

    def test_get_system_health_healthy(self, provider_with_log):
        """Test system health when signals are present"""
        health = provider_with_log.get_system_health()

        assert health["status"] == "healthy"
        assert health["signals_last_hour"] >= 0
        assert "filters_active" in health

    def test_get_system_health_warning(self, temp_log_file):
        """Test system health warning when no recent signals"""
        Path(temp_log_file).touch()
        provider = Phase1MetricsProvider(log_file=temp_log_file)

        health = provider.get_system_health()
        assert health["status"] == "warning"

    def test_get_system_health_filters_active(self, provider_with_log):
        """Test system health reports active filters"""
        health = provider_with_log.get_system_health()

        filters = health["filters_active"]
        assert "gatekeeper" in filters
        assert "validator" in filters
        assert "atr" in filters

    def test_time_window_filtering(self, temp_log_file):
        """Test that only logs within time window are included"""
        now = datetime.now()
        old_time = (now - timedelta(hours=25)).strftime('%Y-%m-%d %H:%M:%S')
        recent_time = (now - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')

        with open(temp_log_file, 'w') as f:
            f.write(f"{old_time} - Signal generated: BUY, confidence: 0.75\n")
            f.write(f"{recent_time} - Signal generated: SELL, confidence: 0.85\n")

        provider = Phase1MetricsProvider(log_file=temp_log_file)
        metrics = provider.get_metrics(hours=24)

        # Should only include recent signal (within 24 hours)
        assert metrics["signals"]["total"] == 1
        assert metrics["signals"]["sell"] == 1
        assert metrics["signals"]["buy"] == 0  # Old signal excluded

    def test_malformed_log_lines_skipped(self, temp_log_file):
        """Test that malformed log lines are skipped gracefully"""
        now = datetime.now()
        valid_time = (now - timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')

        with open(temp_log_file, 'w') as f:
            f.write("INVALID LOG LINE\n")
            f.write(f"{valid_time} - Signal generated: BUY, confidence: 0.75\n")
            f.write("Another invalid line\n")

        provider = Phase1MetricsProvider(log_file=temp_log_file)
        metrics = provider.get_metrics(hours=24)

        # Should process valid line and skip invalid ones
        assert metrics["signals"]["buy"] >= 1

    def test_metrics_structure_complete(self, provider_with_log):
        """Test that returned metrics have complete structure"""
        metrics = provider_with_log.get_metrics()

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
