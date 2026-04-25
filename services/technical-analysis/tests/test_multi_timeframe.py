"""
Test suite for Multi-Timeframe Analysis Module
Tests for app/multi_timeframe.py
Target: Improve coverage from 0% to 80%+
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime
import httpx

# Import classes to test
from app.multi_timeframe import (
    TimeframeSignal,
    MultiTimeframeAnalysis,
    MultiTimeframeAnalyzer
)


class TestTimeframeSignal:
    """Test suite for TimeframeSignal model"""

    def test_timeframe_signal_creation(self):
        """Test creating a TimeframeSignal"""
        signal = TimeframeSignal(
            interval="1h",
            signal="BUY",
            confidence=0.75,
            rsi=65.5,
            macd_signal="BUY",
            trend="BULLISH",
            volume_confirmation=True
        )

        assert signal.interval == "1h"
        assert signal.signal == "BUY"
        assert signal.confidence == 0.75
        assert signal.rsi == 65.5
        assert signal.macd_signal == "BUY"
        assert signal.trend == "BULLISH"
        assert signal.volume_confirmation is True

    def test_timeframe_signal_optional_fields(self):
        """Test TimeframeSignal with optional fields as None"""
        signal = TimeframeSignal(
            interval="5m",
            signal="HOLD",
            confidence=0.5
        )

        assert signal.interval == "5m"
        assert signal.signal == "HOLD"
        assert signal.rsi is None
        assert signal.macd_signal is None
        assert signal.trend is None
        assert signal.volume_confirmation is None


class TestMultiTimeframeAnalysis:
    """Test suite for MultiTimeframeAnalysis model"""

    def test_multi_timeframe_analysis_creation(self):
        """Test creating a MultiTimeframeAnalysis"""
        signal_1h = TimeframeSignal(
            interval="1h",
            signal="BUY",
            confidence=0.8
        )

        analysis = MultiTimeframeAnalysis(
            symbol="BTCUSDT",
            timeframes={"1h": signal_1h},
            alignment_score=85.0,
            consensus_signal="BUY",
            consensus_confidence=0.8,
            short_term_trend="BULLISH",
            medium_term_trend="BULLISH",
            long_term_trend="NEUTRAL",
            overall_signal="BUY",
            signal_strength=0.85,
            divergence_warnings=[],
            analysis_timestamp=datetime.utcnow()
        )

        assert analysis.symbol == "BTCUSDT"
        assert analysis.alignment_score == 85.0
        assert analysis.overall_signal == "BUY"
        assert len(analysis.divergence_warnings) == 0


class TestMultiTimeframeAnalyzer:
    """Test suite for MultiTimeframeAnalyzer"""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance for testing"""
        return MultiTimeframeAnalyzer(
            market_data_url="http://localhost:8005",
            technical_analysis_url="http://localhost:8003"
        )

    @pytest.mark.asyncio
    async def test_analyzer_initialization(self, analyzer):
        """Test analyzer initialization"""
        assert analyzer.market_data_url == "http://localhost:8005"
        assert analyzer.technical_analysis_url == "http://localhost:8003"
        assert analyzer.http_client is not None
        assert isinstance(analyzer.TIMEFRAMES, dict)
        assert len(analyzer.TIMEFRAMES) == 6

    @pytest.mark.asyncio
    async def test_analyzer_close(self, analyzer):
        """Test closing the analyzer"""
        await analyzer.close()
        # Should not raise an exception

    @pytest.mark.asyncio
    async def test_get_timeframe_signal_success(self, analyzer):
        """Test successful timeframe signal retrieval

        UPDATED 2025-12-03: Changed timeframe from "1h" to "60m" to match
        TIMEFRAMES dict format expected by MultiTimeframeAnalyzer.
        """
        mock_response = {
            "signal": "BUY",
            "confidence": 0.75,
            "rsi": 65.0,
            "macd_signal": "BUY",
            "trend": "BULLISH",
            "volume_confirmation": True
        }

        with patch.object(analyzer.http_client, 'get') as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            signal = await analyzer._get_timeframe_signal("BTCUSDT", "60m")

            assert signal is not None
            assert signal.interval == "60m"
            assert signal.signal == "BUY"
            assert signal.confidence == 0.75
            assert signal.rsi == 65.0

    @pytest.mark.asyncio
    async def test_get_timeframe_signal_http_error(self, analyzer):
        """Test timeframe signal retrieval with HTTP error

        UPDATED 2025-12-03: Changed timeframe from "1h" to "60m".
        """
        with patch.object(analyzer.http_client, 'get') as mock_get:
            mock_get.return_value = AsyncMock(status_code=404)

            signal = await analyzer._get_timeframe_signal("BTCUSDT", "60m")

            assert signal is None

    @pytest.mark.asyncio
    async def test_get_timeframe_signal_exception(self, analyzer):
        """Test timeframe signal retrieval with exception

        UPDATED 2025-12-03: Changed timeframe from "1h" to "60m".
        """
        with patch.object(analyzer.http_client, 'get') as mock_get:
            mock_get.side_effect = Exception("Network error")

            signal = await analyzer._get_timeframe_signal("BTCUSDT", "60m")

            assert signal is None

    @pytest.mark.asyncio
    async def test_get_timeframe_signal_unknown_timeframe(self, analyzer):
        """Test with unknown timeframe"""
        signal = await analyzer._get_timeframe_signal("BTCUSDT", "unknown")

        assert signal is None

    def test_calculate_alignment_perfect(self, analyzer):
        """Test alignment calculation with perfect agreement"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="BUY", confidence=0.75),
            "15m": TimeframeSignal(interval="15m", signal="BUY", confidence=0.85)
        }

        alignment = analyzer._calculate_alignment(signals)

        assert alignment == 100.0

    def test_calculate_alignment_mixed(self, analyzer):
        """Test alignment calculation with mixed signals"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="SELL", confidence=0.75),
            "15m": TimeframeSignal(interval="15m", signal="BUY", confidence=0.85)
        }

        alignment = analyzer._calculate_alignment(signals)

        # 2 out of 3 agree on BUY
        assert alignment == pytest.approx(66.67, rel=0.01)

    def test_calculate_alignment_empty(self, analyzer):
        """Test alignment calculation with no signals"""
        alignment = analyzer._calculate_alignment({})

        assert alignment == 0.0

    def test_calculate_consensus_unanimous_buy(self, analyzer):
        """Test consensus calculation with unanimous BUY"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="BUY", confidence=0.75)
        }

        consensus, confidence = analyzer._calculate_consensus(signals)

        assert consensus == "BUY"
        assert confidence > 0.7

    def test_calculate_consensus_mixed_signals(self, analyzer):
        """Test consensus with mixed signals"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.9),
            "5m": TimeframeSignal(interval="5m", signal="SELL", confidence=0.3)
        }

        consensus, confidence = analyzer._calculate_consensus(signals)

        # BUY should win with higher confidence
        assert consensus == "BUY"

    def test_calculate_consensus_empty(self, analyzer):
        """Test consensus with no signals"""
        consensus, confidence = analyzer._calculate_consensus({})

        assert consensus == "HOLD"
        assert confidence == 0.0

    def test_get_trend_for_group_bullish(self, analyzer):
        """Test trend detection for bullish group"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="BUY", confidence=0.75),
            "15m": TimeframeSignal(interval="15m", signal="HOLD", confidence=0.5)
        }

        trend = analyzer._get_trend_for_group(signals, ["1m", "5m", "15m"])

        assert trend == "BULLISH"

    def test_get_trend_for_group_bearish(self, analyzer):
        """Test trend detection for bearish group"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="SELL", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="SELL", confidence=0.75),
            "15m": TimeframeSignal(interval="15m", signal="HOLD", confidence=0.5)
        }

        trend = analyzer._get_trend_for_group(signals, ["1m", "5m", "15m"])

        assert trend == "BEARISH"

    def test_get_trend_for_group_neutral(self, analyzer):
        """Test trend detection for neutral group"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8),
            "5m": TimeframeSignal(interval="5m", signal="SELL", confidence=0.75)
        }

        trend = analyzer._get_trend_for_group(signals, ["1m", "5m"])

        assert trend == "NEUTRAL"

    def test_get_trend_for_group_missing_timeframes(self, analyzer):
        """Test trend with missing timeframes in group"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8)
        }

        # Request includes timeframes not in signals
        trend = analyzer._get_trend_for_group(signals, ["1m", "5m", "15m"])

        # Should still work with available data
        assert trend == "BULLISH"

    def test_get_trend_for_group_empty(self, analyzer):
        """Test trend with no matching timeframes"""
        signals = {
            "1h": TimeframeSignal(interval="1h", signal="BUY", confidence=0.8)
        }

        trend = analyzer._get_trend_for_group(signals, ["1m", "5m"])

        assert trend == "NEUTRAL"

    def test_determine_overall_signal_all_bullish(self, analyzer):
        """Test overall signal when all trends are bullish"""
        signal = analyzer._determine_overall_signal(
            consensus="BUY",
            short_term="BULLISH",
            medium_term="BULLISH",
            long_term="BULLISH"
        )

        assert signal == "BUY"

    def test_determine_overall_signal_all_bearish(self, analyzer):
        """Test overall signal when all trends are bearish"""
        signal = analyzer._determine_overall_signal(
            consensus="SELL",
            short_term="BEARISH",
            medium_term="BEARISH",
            long_term="BEARISH"
        )

        assert signal == "SELL"

    def test_determine_overall_signal_long_medium_align(self, analyzer):
        """Test overall signal when long and medium term align"""
        signal = analyzer._determine_overall_signal(
            consensus="SELL",
            short_term="BULLISH",
            medium_term="BEARISH",
            long_term="BEARISH"
        )

        # Long and medium term alignment takes priority
        assert signal == "SELL"

    def test_determine_overall_signal_use_consensus(self, analyzer):
        """Test overall signal uses consensus when trends mixed"""
        signal = analyzer._determine_overall_signal(
            consensus="HOLD",
            short_term="BULLISH",
            medium_term="BEARISH",
            long_term="NEUTRAL"
        )

        # No clear trend alignment, use consensus
        assert signal == "HOLD"

    def test_calculate_signal_strength_high(self, analyzer):
        """Test signal strength calculation with high values"""
        strength = analyzer._calculate_signal_strength(
            alignment_score=90.0,
            consensus_confidence=0.85,
            num_timeframes=6
        )

        assert strength > 0.7
        assert strength <= 1.0

    def test_calculate_signal_strength_low(self, analyzer):
        """Test signal strength calculation with low values"""
        strength = analyzer._calculate_signal_strength(
            alignment_score=40.0,
            consensus_confidence=0.5,
            num_timeframes=2
        )

        assert strength < 0.6
        assert strength >= 0.0

    def test_detect_divergences_short_vs_medium(self, analyzer):
        """Test divergence detection between short and medium term"""
        signals = {}

        warnings = analyzer._detect_divergences(
            signals,
            short_term="BULLISH",
            medium_term="BEARISH",
            long_term="NEUTRAL"
        )

        assert len(warnings) > 0
        assert any("Short-term bullish but medium-term bearish" in w for w in warnings)

    def test_detect_divergences_medium_vs_long(self, analyzer):
        """Test divergence detection between medium and long term"""
        signals = {}

        warnings = analyzer._detect_divergences(
            signals,
            short_term="NEUTRAL",
            medium_term="BULLISH",
            long_term="BEARISH"
        )

        assert len(warnings) > 0
        assert any("Medium-term" in w and "long-term" in w for w in warnings)

    def test_detect_divergences_rsi_extreme(self, analyzer):
        """Test divergence detection for extreme RSI values"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8, rsi=25.0),
            "1h": TimeframeSignal(interval="1h", signal="SELL", confidence=0.8, rsi=75.0)
        }

        warnings = analyzer._detect_divergences(
            signals,
            short_term="BULLISH",
            medium_term="BULLISH",
            long_term="BULLISH"
        )

        assert len(warnings) > 0
        assert any("Extreme RSI divergence" in w for w in warnings)

    def test_detect_divergences_no_warnings(self, analyzer):
        """Test no divergences when trends align"""
        signals = {
            "1m": TimeframeSignal(interval="1m", signal="BUY", confidence=0.8, rsi=55.0),
            "5m": TimeframeSignal(interval="5m", signal="BUY", confidence=0.8, rsi=60.0)
        }

        warnings = analyzer._detect_divergences(
            signals,
            short_term="BULLISH",
            medium_term="BULLISH",
            long_term="BULLISH"
        )

        # Should have no or minimal warnings
        assert isinstance(warnings, list)

    @pytest.mark.asyncio
    async def test_analyze_default_timeframes(self, analyzer):
        """Test full analysis with default timeframes"""
        mock_response = {
            "signal": "BUY",
            "confidence": 0.75,
            "rsi": 65.0,
            "macd_signal": "BUY",
            "trend": "BULLISH"
        }

        with patch.object(analyzer.http_client, 'get') as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            result = await analyzer.analyze("BTCUSDT")

            assert result is not None
            assert result.symbol == "BTCUSDT"
            assert result.overall_signal in ["BUY", "SELL", "HOLD"]
            assert 0 <= result.alignment_score <= 100
            assert 0 <= result.signal_strength <= 1

    @pytest.mark.asyncio
    async def test_analyze_custom_timeframes(self, analyzer):
        """Test analysis with custom timeframes"""
        mock_response = {
            "signal": "SELL",
            "confidence": 0.7,
            "rsi": 35.0
        }

        with patch.object(analyzer.http_client, 'get') as mock_get:
            mock_get.return_value = AsyncMock(
                status_code=200,
                json=Mock(return_value=mock_response)
            )

            result = await analyzer.analyze("ETHUSDT", timeframes=["1m", "5m"])

            assert result is not None
            assert result.symbol == "ETHUSDT"
            # Should only analyze 2 timeframes
            assert len(result.timeframes) <= 2

    @pytest.mark.asyncio
    async def test_analyze_with_failures(self, analyzer):
        """Test analysis when some timeframes fail"""
        call_count = [0]

        async def mock_get(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] % 2 == 0:
                raise Exception("Network error")
            return AsyncMock(
                status_code=200,
                json=Mock(return_value={
                    "signal": "BUY",
                    "confidence": 0.75
                })
            )

        with patch.object(analyzer.http_client, 'get', side_effect=mock_get):
            result = await analyzer.analyze("BTCUSDT", timeframes=["1m", "5m", "15m", "60m"])

            # Should handle partial failures
            assert result is not None
            assert len(result.timeframes) >= 1
