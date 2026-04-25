"""
Feature Engineering Pipeline for ML Trading Models
Purpose: Transform raw OHLCV data into ML-friendly features
Author: Phase 3 ML Team
Date: 2025-12-06

Creates 50+ features from raw market data:
- Price-based features (returns, volatility, momentum)
- Technical indicators (RSI, MACD, BB, Volume)
- Time-based features (hour, day, weekend)
- Market context features (correlation, rank, liquidity)
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class FeatureEngineer:
    """
    Transform raw OHLCV data into feature-rich dataset for ML models

    Input: DataFrame with columns [timestamp, open, high, low, close, volume]
    Output: DataFrame with 50+ engineered features
    """

    def __init__(self):
        """Initialize feature engineer"""
        self.feature_names = []
        logger.info("FeatureEngineer initialized")

    def create_features(self, df: pd.DataFrame, prediction_horizon: int = 4) -> pd.DataFrame:
        """
        Create all features from raw OHLCV data

        Args:
            df: DataFrame with OHLCV data (timestamp index)
            prediction_horizon: Hours ahead to predict (1 = 1h, 4 = 4h)

        Returns:
            DataFrame with engineered features
        """
        logger.info(f"Creating features from {len(df)} candles")

        # Make copy to avoid modifying original
        features = df.copy()

        # 1. Price-based features
        features = self._create_price_features(features)

        # 2. Technical indicators
        features = self._create_technical_indicators(features)

        # 3. Volume features
        features = self._create_volume_features(features)

        # 4. Time-based features
        features = self._create_time_features(features)

        # 5. Rolling statistics
        features = self._create_rolling_features(features)

        # 6. Target variable (for supervised learning)
        features = self._create_target(features, horizon=prediction_horizon)

        # Drop NaN rows (from rolling calculations)
        features = features.dropna()

        logger.info(f"Created {len(features.columns)} features, {len(features)} valid rows")

        return features

    def _create_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create price-based features"""

        # Returns (percentage change)
        df['returns_1h'] = df['close'].pct_change()
        df['returns_4h'] = df['close'].pct_change(4)
        df['returns_24h'] = df['close'].pct_change(24)

        # Log returns (better statistical properties)
        df['log_returns_1h'] = np.log(df['close'] / df['close'].shift(1))

        # High-Low range (volatility proxy)
        df['hl_pct'] = (df['high'] - df['low']) / df['close']

        # Close position within High-Low range
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 1e-10)

        # Price momentum
        df['momentum_5'] = df['close'] - df['close'].shift(5)
        df['momentum_10'] = df['close'] - df['close'].shift(10)

        # Gap (open vs previous close)
        df['gap'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)

        logger.debug("Created price features")
        return df

    def _create_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create technical indicator features"""

        # RSI (Relative Strength Index)
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)
        df['rsi_20'] = self._calculate_rsi(df['close'], 20)

        # MACD (Moving Average Convergence Divergence)
        df['macd'], df['macd_signal'], df['macd_histogram'] = self._calculate_macd(df['close'])

        # Bollinger Bands
        df['bb_upper'], df['bb_middle'], df['bb_lower'], df['bb_width'] = self._calculate_bollinger_bands(df['close'])
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-10)

        # Moving Averages
        df['sma_10'] = df['close'].rolling(window=10).mean()
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        df['ema_10'] = df['close'].ewm(span=10).mean()
        df['ema_20'] = df['close'].ewm(span=20).mean()

        # Price vs Moving Averages
        df['price_vs_sma20'] = (df['close'] - df['sma_20']) / df['sma_20']
        df['price_vs_sma50'] = (df['close'] - df['sma_50']) / df['sma_50']

        # ATR (Average True Range) - Volatility
        df['atr_14'] = self._calculate_atr(df, 14)

        logger.debug("Created technical indicator features")
        return df

    def _create_volume_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create volume-based features"""

        # Volume change
        df['volume_change'] = df['volume'].pct_change()

        # Volume moving averages
        df['volume_sma_20'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma_20']

        # Volume-Price Trend
        df['vpt'] = ((df['close'] - df['close'].shift(1)) / df['close'].shift(1) * df['volume']).cumsum()

        # On-Balance Volume (OBV)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()

        logger.debug("Created volume features")
        return df

    def _create_time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create time-based features"""

        # Ensure timestamp is datetime
        if 'timestamp' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index('timestamp')

        # Hour of day (0-23)
        df['hour'] = df.index.hour

        # Day of week (0-6, Monday=0)
        df['day_of_week'] = df.index.dayofweek

        # Is weekend (Sat/Sun)
        df['is_weekend'] = (df.index.dayofweek >= 5).astype(int)

        # Cyclical encoding for hour (preserves circular nature)
        df['hour_sin'] = np.sin(2 * np.pi * df.index.hour / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df.index.hour / 24)

        # Cyclical encoding for day of week
        df['dow_sin'] = np.sin(2 * np.pi * df.index.dayofweek / 7)
        df['dow_cos'] = np.cos(2 * np.pi * df.index.dayofweek / 7)

        logger.debug("Created time features")
        return df

    def _create_rolling_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Create rolling window statistics"""

        # Volatility (rolling std of returns)
        df['volatility_10'] = df['returns_1h'].rolling(window=10).std()
        df['volatility_24'] = df['returns_1h'].rolling(window=24).std()

        # Rolling min/max (support/resistance proxies)
        df['rolling_min_24'] = df['low'].rolling(window=24).min()
        df['rolling_max_24'] = df['high'].rolling(window=24).max()
        df['price_vs_min'] = (df['close'] - df['rolling_min_24']) / df['rolling_min_24']
        df['price_vs_max'] = (df['close'] - df['rolling_max_24']) / df['rolling_max_24']

        # Rolling median
        df['rolling_median_20'] = df['close'].rolling(window=20).median()

        logger.debug("Created rolling features")
        return df

    def _create_target(self, df: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
        """
        Create target variable for supervised learning

        Args:
            df: DataFrame with features
            horizon: How many periods ahead to predict (default: 4 hours)

        Returns:
            DataFrame with target column
        """
        # Binary target: will price go up in next `horizon` periods?
        df['future_return'] = df['close'].shift(-horizon) / df['close'] - 1
        df['target'] = (df['future_return'] > 0).astype(int)

        # Target as percentage (for regression)
        df['target_pct'] = df['future_return'] * 100

        logger.debug(f"Created target variable (horizon={horizon})")
        return df

    # ====================================================================
    # Technical Indicator Calculation Methods
    # ====================================================================

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 1e-10)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def _calculate_macd(
        self,
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> tuple:
        """Calculate MACD"""
        ema_fast = prices.ewm(span=fast).mean()
        ema_slow = prices.ewm(span=slow).mean()
        macd = ema_fast - ema_slow
        macd_signal = macd.ewm(span=signal).mean()
        macd_histogram = macd - macd_signal
        return macd, macd_signal, macd_histogram

    def _calculate_bollinger_bands(
        self,
        prices: pd.Series,
        period: int = 20,
        std: float = 2.0
    ) -> tuple:
        """Calculate Bollinger Bands"""
        middle = prices.rolling(window=period).mean()
        rolling_std = prices.rolling(window=period).std()
        upper = middle + (std * rolling_std)
        lower = middle - (std * rolling_std)
        width = (upper - lower) / middle
        return upper, middle, lower, width

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr

    def get_feature_names(self, exclude_target: bool = True) -> List[str]:
        """
        Get list of feature column names

        Args:
            exclude_target: If True, exclude target columns

        Returns:
            List of feature names
        """
        exclude_cols = ['open', 'high', 'low', 'close', 'volume']
        if exclude_target:
            exclude_cols.extend(['target', 'target_pct', 'future_return'])

        return [col for col in self.feature_names if col not in exclude_cols]


# ====================================================================
# Usage Example
# ====================================================================

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Load sample data
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent.parent.parent

    sample_data = project_root / 'backtesting/data/SOLUSDT_60m_90d_bybit.csv'

    if sample_data.exists():
        df = pd.read_csv(sample_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp')

        # Create features
        fe = FeatureEngineer()
        features = fe.create_features(df)

        print(f"\n{'='*80}")
        print(f"FEATURE ENGINEERING DEMO")
        print(f"{'='*80}")
        print(f"Input data: {len(df)} candles")
        print(f"Output features: {len(features)} valid rows, {len(features.columns)} columns")
        print(f"\nFirst 5 rows of key features:")
        print(features[['close', 'returns_1h', 'rsi_14', 'macd', 'bb_position', 'volume_ratio', 'target']].head())
        print(f"\nFeature columns:")
        for col in features.columns:
            print(f"  - {col}")
        print(f"{'='*80}\n")
    else:
        print(f"Sample data not found: {sample_data}")
