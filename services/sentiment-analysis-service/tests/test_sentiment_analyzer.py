"""
Tests for Sentiment Analyzer
Tests lexicon-based and ML-based sentiment analysis
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from app.analyzers.sentiment_analyzer import SentimentAnalyzer


@pytest.fixture
def analyzer_lexicon_only():
    """
    Creates sentiment analyzer with only lexicon-based analysis
    """
    return SentimentAnalyzer(use_ml=False)


@pytest.fixture
def analyzer_with_ml():
    """
    Creates sentiment analyzer with ML enabled
    """
    with patch('app.analyzers.sentiment_analyzer.TRANSFORMERS_AVAILABLE', True):
        with patch('app.analyzers.sentiment_analyzer.pipeline') as mock_pipeline:
            mock_pipeline.return_value = MagicMock()
            return SentimentAnalyzer(use_ml=True)


class TestSentimentAnalyzerInitialization:
    """Tests for sentiment analyzer initialization"""

    def test_init_lexicon_only(self, analyzer_lexicon_only):
        """
        Test initialization with lexicon-based analysis only
        """
        assert analyzer_lexicon_only.use_ml == False
        assert analyzer_lexicon_only.ml_analyzer is None
        assert len(analyzer_lexicon_only.bullish_keywords) > 0
        assert len(analyzer_lexicon_only.bearish_keywords) > 0

    def test_init_with_ml(self, analyzer_with_ml):
        """
        Test initialization with ML-based analysis
        """
        assert analyzer_with_ml.use_ml == True
        assert analyzer_with_ml.ml_analyzer is not None

    def test_keyword_lists_not_empty(self, analyzer_lexicon_only):
        """
        Test that bullish and bearish keyword lists are populated
        """
        assert len(analyzer_lexicon_only.bullish_keywords) >= 30
        assert len(analyzer_lexicon_only.bearish_keywords) >= 30

    def test_keywords_are_lowercase(self, analyzer_lexicon_only):
        """
        Test that all keywords are lowercase for consistent matching
        """
        for keyword in analyzer_lexicon_only.bullish_keywords:
            assert keyword == keyword.lower()
        for keyword in analyzer_lexicon_only.bearish_keywords:
            assert keyword == keyword.lower()


class TestLexiconBasedSentiment:
    """Tests for lexicon-based sentiment analysis"""

    def test_analyze_bullish_text(self, analyzer_lexicon_only):
        """
        Test analysis of clearly bullish text
        Should return positive sentiment
        """
        text = "Bitcoin is surging to new highs! Strong bullish momentum with excellent gains."
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert result.score > 0  # Positive score
        assert result.label in ['BULLISH', 'POSITIVE']
        assert 0 <= result.confidence <= 1.0

    def test_analyze_bearish_text(self, analyzer_lexicon_only):
        """
        Test analysis of clearly bearish text
        Should return negative sentiment
        """
        text = "Bitcoin is crashing! Massive dump, selling pressure increasing. Very bearish."
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert result.score < 0  # Negative score
        assert result.label in ['BEARISH', 'NEGATIVE']
        assert 0 <= result.confidence <= 1.0

    def test_analyze_neutral_text(self, analyzer_lexicon_only):
        """
        Test analysis of neutral text
        Should return neutral sentiment
        """
        text = "Bitcoin price is at $50,000. Trading volume is average today."
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert -0.2 <= result.score <= 0.2  # Near zero
        assert result.label == 'NEUTRAL'

    def test_analyze_empty_text(self, analyzer_lexicon_only):
        """
        Test analysis of empty text
        Should return neutral sentiment
        """
        result = analyzer_lexicon_only.analyze_text("")

        assert result.score == 0.0
        assert result.label == 'NEUTRAL'
        assert result.confidence == 0.0

    def test_analyze_mixed_sentiment(self, analyzer_lexicon_only):
        """
        Test analysis of text with mixed signals
        Should average out the sentiment
        """
        text = "Bitcoin rallied earlier but now facing resistance. Bulls and bears in battle."
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        # Should be somewhat neutral due to mixed signals
        assert -0.5 <= result.score <= 0.5

    def test_case_insensitive_matching(self, analyzer_lexicon_only):
        """
        Test that keyword matching is case-insensitive
        """
        text1 = "BULLISH trend continues"
        text2 = "bullish trend continues"
        text3 = "Bullish Trend Continues"

        result1 = analyzer_lexicon_only.analyze_text(text1)
        result2 = analyzer_lexicon_only.analyze_text(text2)
        result3 = analyzer_lexicon_only.analyze_text(text3)

        # All should have same sentiment
        assert result1.label == result2.label == result3.label
        assert abs(result1.score - result2.score) < 0.1

    def test_multiple_keyword_detection(self, analyzer_lexicon_only):
        """
        Test that multiple keywords increase sentiment strength
        """
        text_single = "Bitcoin is bullish"
        text_multiple = "Bitcoin is bullish with strong uptrend and excellent momentum"

        result_single = analyzer_lexicon_only.analyze_text(text_single)
        result_multiple = analyzer_lexicon_only.analyze_text(text_multiple)

        # Multiple keywords should give stronger signal
        assert result_multiple.score >= result_single.score
        assert result_multiple.confidence >= result_single.confidence


class TestMLBasedSentiment:
    """Tests for ML-based sentiment analysis (FinBERT)"""

    def test_analyze_with_ml_bullish(self, analyzer_with_ml):
        """
        Test ML-based analysis of bullish text
        """
        # Mock FinBERT response
        analyzer_with_ml.ml_analyzer.return_value = [{
            'label': 'positive',
            'score': 0.85
        }]

        text = "Strong Bitcoin rally expected with institutional buying"
        result = analyzer_with_ml.analyze_text(text)

        assert result.score > 0
        assert result.label in ['BULLISH', 'POSITIVE']
        assert result.confidence > 0.7

    def test_analyze_with_ml_bearish(self, analyzer_with_ml):
        """
        Test ML-based analysis of bearish text
        """
        # Mock FinBERT response
        analyzer_with_ml.ml_analyzer.return_value = [{
            'label': 'negative',
            'score': 0.90
        }]

        text = "Bitcoin faces significant downside risk and bearish pressure"
        result = analyzer_with_ml.analyze_text(text)

        assert result.score < 0
        assert result.label in ['BEARISH', 'NEGATIVE']
        assert result.confidence > 0.7

    def test_ml_fallback_on_error(self, analyzer_with_ml):
        """
        Test that ML analysis falls back to lexicon if ML fails
        """
        # Mock ML analyzer to raise exception
        analyzer_with_ml.ml_analyzer.side_effect = Exception("Model error")

        text = "Bitcoin is bullish"
        result = analyzer_with_ml.analyze_text(text)

        # Should still return result from lexicon analysis
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert result[0] != 0  # Got some sentiment from lexicon


# TestSentimentResultModel class removed - SentimentResult model doesn't exist
# The analyzer returns tuples (score, label) instead of a model object

class TestBatchAnalysis:
    """Tests for batch sentiment analysis"""

    def test_analyze_multiple_texts(self, analyzer_lexicon_only):
        """
        Test analyzing multiple texts at once
        """
        texts = [
            "Bitcoin is surging to new highs",
            "Market is crashing badly",
            "Sideways movement today"
        ]

        results = [analyzer_lexicon_only.analyze_text(text) for text in texts]

        assert len(results) == 3
        assert results[0].label == 'BULLISH'
        assert results[1].label == 'BEARISH'
        assert results[2].label == 'NEUTRAL'

    def test_average_sentiment_calculation(self, analyzer_lexicon_only):
        """
        Test calculating average sentiment from multiple results
        """
        texts = [
            "Very bullish market with strong momentum",
            "Slightly bullish trend continues",
            "Bearish pressure building"
        ]

        results = [analyzer_lexicon_only.analyze_text(text) for text in texts]
        avg_score = sum(r.score for r in results) / len(results)

        # Should be slightly bullish (2 bullish, 1 bearish)
        assert avg_score > 0


class TestSymbolSpecificAnalysis:
    """Tests for symbol-specific sentiment analysis"""

    def test_symbol_mention_increases_relevance(self, analyzer_lexicon_only):
        """
        Test that mentioning the symbol increases relevance
        """
        text_with_symbol = "Bitcoin is extremely bullish right now"
        text_without_symbol = "The market is extremely bullish right now"

        result_with = analyzer_lexicon_only.analyze_text(
            text_with_symbol,
            symbol="BTC"
        )
        result_without = analyzer_lexicon_only.analyze_text(
            text_without_symbol,
            symbol="BTC"
        )

        # Result with symbol mention should have higher confidence
        assert result_with.confidence >= result_without.confidence

    def test_symbol_variations_detected(self, analyzer_lexicon_only):
        """
        Test that different symbol variations are detected
        """
        texts = [
            "BTC is bullish",
            "Bitcoin is bullish",
            "BTCUSDT is bullish"
        ]

        results = [
            analyzer_lexicon_only.analyze_text(text, symbol="BTC")
            for text in texts
        ]

        # All should be detected as relevant to BTC
        assert all(r.label == 'BULLISH' for r in results)


class TestSentimentConfidence:
    """Tests for sentiment confidence scoring"""

    def test_confidence_increases_with_keywords(self, analyzer_lexicon_only):
        """
        Test that confidence increases with more keywords
        """
        text_weak = "Slightly bullish"
        text_strong = "Very bullish, strongly bullish, extremely bullish"

        result_weak = analyzer_lexicon_only.analyze_text(text_weak)
        result_strong = analyzer_lexicon_only.analyze_text(text_strong)

        assert result_strong.confidence > result_weak.confidence

    def test_confidence_decreases_with_mixed_signals(self, analyzer_lexicon_only):
        """
        Test that confidence decreases with conflicting signals
        """
        text_clear = "Very bullish, strong uptrend"
        text_mixed = "Bullish but facing bearish resistance"

        result_clear = analyzer_lexicon_only.analyze_text(text_clear)
        result_mixed = analyzer_lexicon_only.analyze_text(text_mixed)

        assert result_clear.confidence > result_mixed.confidence


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_very_long_text(self, analyzer_lexicon_only):
        """
        Test analyzing very long text
        Should handle gracefully
        """
        text = "Bitcoin is bullish. " * 1000  # Very long text
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert result.label == 'BULLISH'

    def test_special_characters(self, analyzer_lexicon_only):
        """
        Test text with special characters and emojis
        """
        text = "Bitcoin 🚀🚀🚀 bullish AF!!! 📈 #crypto $BTC"
        result = analyzer_lexicon_only.analyze_text(text)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], str)
        assert result.label == 'BULLISH'

    def test_non_english_text(self, analyzer_lexicon_only):
        """
        Test non-English text (should return neutral)
        """
        text = "ビットコインは上昇しています"  # Japanese
        result = analyzer_lexicon_only.analyze_text(text)

        # Should default to neutral for non-English
        assert result.label == 'NEUTRAL'

    def test_numeric_only_text(self, analyzer_lexicon_only):
        """
        Test text with only numbers
        """
        text = "50000 51000 52000"
        result = analyzer_lexicon_only.analyze_text(text)

        assert result.label == 'NEUTRAL'


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
