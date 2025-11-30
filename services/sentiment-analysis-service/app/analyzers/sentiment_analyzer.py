"""
Sentiment Analyzer
Analyzes text sentiment using lexicon-based and ML approaches
"""

import logging
from typing import Tuple, Dict, List, NamedTuple
from datetime import datetime
from dataclasses import dataclass
import re


@dataclass
class SentimentResult:
    """
    Structured result from sentiment analysis

    Attributes:
        score: Sentiment score from -1.0 (bearish) to 1.0 (bullish)
        label: Sentiment label (POSITIVE, NEGATIVE, NEUTRAL)
        confidence: Confidence in the analysis (0.0 to 1.0)
        method: Analysis method used (lexicon, ml, finbert)
    """
    score: float
    label: str
    confidence: float = 0.5
    method: str = "lexicon"

# Try to import transformers for advanced sentiment analysis
try:
    from transformers import pipeline
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logging.warning("Transformers not available. Using basic sentiment analysis.")

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """
    Sentiment analyzer using multiple approaches:
    1. Lexicon-based (fast, simple)
    2. Transformer-based (slow, accurate) - if available
    """

    def __init__(self, use_ml: bool = True):
        """
        Initialize sentiment analyzer

        Args:
            use_ml: Whether to use ML-based sentiment analysis (requires transformers)
        """
        import os
        import threading

        # Initialize lexicon keywords first (always available)
        self._init_lexicon_keywords()

        # Check environment variable to skip ML for faster startup
        skip_ml = os.environ.get('SKIP_ML_MODEL', 'false').lower() == 'true'
        self.use_ml = use_ml and TRANSFORMERS_AVAILABLE and not skip_ml

        # Initialize ML model if available
        self.ml_analyzer = None
        self._ml_loading = False

        if self.use_ml:
            # Load model in background thread to not block startup
            self._ml_loading = True
            threading.Thread(target=self._load_ml_model, daemon=True).start()
            logger.info("ML model loading started in background thread")
        else:
            if skip_ml:
                logger.info("ML model loading skipped (SKIP_ML_MODEL=true)")
            else:
                logger.info("Using lexicon-based analysis (transformers not available)")

    def _load_ml_model(self):
        """Load ML model in background thread"""
        try:
            # Use FinBERT for financial sentiment analysis
            logger.info("Loading sentiment analysis model (FinBERT)...")
            self.ml_analyzer = pipeline(
                "sentiment-analysis",
                model="ProsusAI/finbert",
                max_length=512,
                truncation=True
            )
            logger.info("Sentiment analysis model loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load ML model: {e}. Using lexicon-based analysis.")
            self.use_ml = False
        finally:
            self._ml_loading = False

    def _init_lexicon_keywords(self):
        """Initialize lexicon-based sentiment keywords"""
        # Lexicon-based sentiment keywords
        self.bullish_keywords = {
            # Positive price action
            'bullish', 'moon', 'rocket', 'pump', 'surge', 'rally', 'breakout',
            'bull run', 'green', 'gains', 'profit', 'up', 'rise', 'climbing',

            # Positive sentiment
            'buy', 'long', 'hodl', 'accumulate', 'undervalued', 'opportunity',
            'strong', 'momentum', 'optimistic', 'confident', 'positive',

            # Technical positives
            'support', 'golden cross', 'oversold', 'bounce', 'reversal upward',

            # Market sentiment
            'adoption', 'institutional', 'partnership', 'upgrade', 'launch',
            'innovation', 'breakthrough', 'success', 'growth', 'expansion'
        }

        self.bearish_keywords = {
            # Negative price action
            'bearish', 'dump', 'crash', 'drop', 'fall', 'plunge', 'decline',
            'bear market', 'red', 'loss', 'losses', 'down', 'falling', 'sinking',

            # Negative sentiment
            'sell', 'short', 'overvalued', 'bubble', 'scam', 'rug pull',
            'weak', 'bearish', 'pessimistic', 'concerned', 'worried', 'fear',

            # Technical negatives
            'resistance', 'death cross', 'overbought', 'rejection', 'breakdown',

            # Market sentiment
            'regulation', 'ban', 'hack', 'vulnerability', 'lawsuit', 'investigation',
            'failure', 'collapse', 'fraud', 'risk', 'warning', 'concern'
        }

    def analyze_text(self, text: str) -> Tuple[float, str]:
        """
        Analyze sentiment of a text

        Args:
            text: Text to analyze

        Returns:
            (sentiment_score, sentiment_label)
            - sentiment_score: -1.0 (very bearish) to 1.0 (very bullish)
            - sentiment_label: "POSITIVE", "NEGATIVE", or "NEUTRAL"
        """
        if not text or len(text.strip()) == 0:
            return 0.0, "NEUTRAL"

        # Try ML-based analysis first
        if self.use_ml and self.ml_analyzer:
            try:
                result = self.ml_analyzer(text[:512])[0]  # Limit text length
                label = result['label'].upper()
                score = result['score']

                # Convert FinBERT labels to our format
                if label == 'POSITIVE':
                    sentiment_score = score  # 0.0 to 1.0
                    sentiment_label = "POSITIVE"
                elif label == 'NEGATIVE':
                    sentiment_score = -score  # -1.0 to 0.0
                    sentiment_label = "NEGATIVE"
                else:  # NEUTRAL
                    sentiment_score = 0.0
                    sentiment_label = "NEUTRAL"

                return sentiment_score, sentiment_label

            except Exception as e:
                logger.warning(f"ML analysis failed: {e}. Falling back to lexicon.")

        # Fallback to lexicon-based analysis
        return self._lexicon_analysis(text)

    def _lexicon_analysis(self, text: str) -> Tuple[float, str]:
        """
        Simple lexicon-based sentiment analysis

        Counts bullish/bearish keywords and calculates score
        """
        # Clean and lowercase text
        text_lower = text.lower()

        # Remove URLs and special characters
        text_clean = re.sub(r'http\S+|www\S+|@\w+|#\w+', '', text_lower)

        # Count keyword occurrences
        bullish_count = sum(1 for keyword in self.bullish_keywords if keyword in text_clean)
        bearish_count = sum(1 for keyword in self.bearish_keywords if keyword in text_clean)

        # Calculate sentiment score
        total_keywords = bullish_count + bearish_count

        if total_keywords == 0:
            return 0.0, "NEUTRAL"

        # Sentiment score: -1 (all bearish) to +1 (all bullish)
        sentiment_score = (bullish_count - bearish_count) / total_keywords

        # Determine label
        if sentiment_score > 0.2:
            sentiment_label = "POSITIVE"
        elif sentiment_score < -0.2:
            sentiment_label = "NEGATIVE"
        else:
            sentiment_label = "NEUTRAL"

        return sentiment_score, sentiment_label

    def analyze_batch(self, texts: list[str]) -> list[Tuple[float, str]]:
        """
        Analyze sentiment for multiple texts

        More efficient than analyzing one by one
        """
        if self.use_ml and self.ml_analyzer:
            try:
                # Truncate texts
                truncated = [text[:512] for text in texts]

                # Batch analysis
                results = self.ml_analyzer(truncated)

                # Convert results
                sentiments = []
                for result in results:
                    label = result['label'].upper()
                    score = result['score']

                    if label == 'POSITIVE':
                        sentiment_score = score
                        sentiment_label = "POSITIVE"
                    elif label == 'NEGATIVE':
                        sentiment_score = -score
                        sentiment_label = "NEGATIVE"
                    else:
                        sentiment_score = 0.0
                        sentiment_label = "NEUTRAL"

                    sentiments.append((sentiment_score, sentiment_label))

                return sentiments

            except Exception as e:
                logger.warning(f"Batch ML analysis failed: {e}")

        # Fallback to lexicon-based
        return [self._lexicon_analysis(text) for text in texts]

    def calculate_weighted_sentiment(
        self,
        sentiments: list[float],
        weights: list[float]
    ) -> float:
        """
        Calculate weighted average sentiment

        Args:
            sentiments: List of sentiment scores
            weights: List of weights (e.g., based on engagement, recency)

        Returns:
            Weighted average sentiment score
        """
        if not sentiments or not weights or len(sentiments) != len(weights):
            return 0.0

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s * w for s, w in zip(sentiments, weights))
        return weighted_sum / total_weight

    def get_sentiment_distribution(self, sentiments: list[float]) -> Dict[str, int]:
        """
        Get distribution of sentiments (positive, negative, neutral)

        Args:
            sentiments: List of sentiment scores

        Returns:
            Dictionary with counts for each category
        """
        distribution = {
            'positive': 0,
            'negative': 0,
            'neutral': 0
        }

        for score in sentiments:
            if score > 0.2:
                distribution['positive'] += 1
            elif score < -0.2:
                distribution['negative'] += 1
            else:
                distribution['neutral'] += 1

        return distribution
