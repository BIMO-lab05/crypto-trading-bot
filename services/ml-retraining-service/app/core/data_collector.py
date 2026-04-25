"""
Data Collection Pipeline for Model Retraining
Purpose: Fetch and validate historical market data for training GRU models
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import httpx
import pandas as pd
import numpy as np

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class DataCollector:
    """
    Collect and validate historical market data for model training

    Fetches last N days of kline data from market-data service
    Validates data quality and returns prepared dataset
    """

    def __init__(self):
        """Initialize data collector"""
        self.settings = get_settings()
        self.market_data_url = self.settings.market_data_url
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def collect_training_data(
        self,
        symbol: str,
        interval: str = "60",
        days: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Collect historical kline data for model training

        Args:
            symbol: Trading symbol (e.g., "SOLUSDT")
            interval: Kline interval in minutes (e.g., "60")
            days: Days of historical data to fetch (default from settings)

        Returns:
            Dict containing:
                - success: bool
                - data: pd.DataFrame with kline data
                - metrics: Data quality metrics
                - errors: List of validation errors if any

        Raises:
            Exception: If data collection fails
        """
        days = days or self.settings.retrain_data_days

        logger.info(f"Collecting {days} days of data for {symbol} ({interval}min)")

        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # Fetch data from market-data service
            klines_data = await self._fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_date,
                end_time=end_date
            )

            if not klines_data:
                return {
                    "success": False,
                    "data": None,
                    "metrics": None,
                    "errors": ["No data returned from market-data service"]
                }

            # Convert to DataFrame
            df = self._prepare_dataframe(klines_data)

            # Validate data quality
            validation_result = self._validate_data(df, symbol, interval, days)

            if not validation_result["is_valid"]:
                logger.warning(
                    f"Data validation failed for {symbol}: {validation_result['errors']}"
                )
                return {
                    "success": False,
                    "data": df,
                    "metrics": validation_result["metrics"],
                    "errors": validation_result["errors"]
                }

            logger.info(
                f"✅ Successfully collected {len(df)} data points for {symbol} "
                f"({validation_result['metrics']['data_completeness']:.2f}% complete)"
            )

            return {
                "success": True,
                "data": df,
                "metrics": validation_result["metrics"],
                "errors": []
            }

        except Exception as e:
            logger.error(f"❌ Data collection failed for {symbol}: {e}", exc_info=True)
            return {
                "success": False,
                "data": None,
                "metrics": None,
                "errors": [str(e)]
            }

    async def _fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """
        Fetch kline data from market-data service

        Args:
            symbol: Trading symbol
            interval: Kline interval in minutes
            start_time: Start date
            end_time: End date

        Returns:
            List of kline dictionaries

        Raises:
            Exception: If API call fails
        """
        # Calculate required data points
        interval_minutes = int(interval)
        total_minutes = (end_time - start_time).total_seconds() / 60
        expected_points = int(total_minutes / interval_minutes)

        logger.debug(
            f"Fetching ~{expected_points} klines for {symbol} "
            f"from {start_time} to {end_time}"
        )

        try:
            # Call market-data service API
            response = await self.client.get(
                f"{self.market_data_url}/api/v1/klines/{symbol}",
                params={
                    "interval": interval,
                    "limit": min(expected_points, 1000)  # API limit
                }
            )

            response.raise_for_status()

            response_data = response.json()

            # Handle nested response structure {success: true, data: [...]}
            if isinstance(response_data, dict) and "data" in response_data:
                klines = response_data["data"]
            else:
                klines = response_data

            logger.debug(f"Fetched {len(klines)} klines for {symbol}")

            return klines

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching klines: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            raise

    def _prepare_dataframe(self, klines_data: List[Dict]) -> pd.DataFrame:
        """
        Convert kline data to pandas DataFrame

        Args:
            klines_data: List of kline dictionaries

        Returns:
            pd.DataFrame with columns: timestamp, open, high, low, close, volume
        """
        if not klines_data:
            return pd.DataFrame()

        # Extract relevant fields
        df = pd.DataFrame([
            {
                "timestamp": k.get("timestamp", k.get("start_time")),
                "open": float(k.get("open", 0)),
                "high": float(k.get("high", 0)),
                "low": float(k.get("low", 0)),
                "close": float(k.get("close", 0)),
                "volume": float(k.get("volume", 0)),
            }
            for k in klines_data
        ])

        # Convert timestamp to datetime
        if "timestamp" in df.columns:
            if df["timestamp"].dtype == "int64":
                # Unix timestamp in milliseconds
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Sort by timestamp
        df = df.sort_values("timestamp").reset_index(drop=True)

        return df

    def _validate_data(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str,
        days: int
    ) -> Dict[str, Any]:
        """
        Validate data quality for training

        Checks:
        1. Sufficient data points (min 10,000 for 180 days)
        2. No missing values
        3. No price outliers (>50% price change)
        4. Data completeness (% of expected points)

        Args:
            df: DataFrame with kline data
            symbol: Trading symbol
            interval: Kline interval
            days: Expected days of data

        Returns:
            Dict with:
                - is_valid: bool
                - metrics: Quality metrics
                - errors: List of validation errors
        """
        errors = []
        metrics = {}

        # Check 1: Sufficient data points
        min_required_points = self.settings.retrain_data_days * 24 * (60 / int(interval))
        actual_points = len(df)

        metrics["data_points"] = actual_points
        metrics["min_required"] = int(min_required_points)

        if actual_points < min_required_points * 0.8:  # Allow 20% tolerance
            errors.append(
                f"Insufficient data: {actual_points} points, "
                f"need at least {int(min_required_points * 0.8)}"
            )

        # Check 2: Missing values
        missing_values = df.isnull().sum().sum()
        metrics["missing_values"] = int(missing_values)

        if missing_values > 0:
            errors.append(f"Found {missing_values} missing values")

        # Check 3: Price outliers (>50% single candle change)
        if len(df) > 0:
            price_changes = df["close"].pct_change().abs()
            outliers = (price_changes > 0.5).sum()
            metrics["price_outliers"] = int(outliers)

            if outliers > 0:
                errors.append(f"Found {outliers} extreme price changes (>50%)")

        # Check 4: Data completeness
        expected_points = days * 24 * (60 / int(interval))
        completeness = (actual_points / expected_points) * 100 if expected_points > 0 else 0
        metrics["data_completeness"] = round(completeness, 2)
        metrics["expected_points"] = int(expected_points)

        if completeness < 80:
            errors.append(
                f"Data only {completeness:.1f}% complete "
                f"({actual_points}/{int(expected_points)} points)"
            )

        # Check 5: Price range (sanity check)
        if len(df) > 0:
            price_min = df["close"].min()
            price_max = df["close"].max()
            metrics["price_min"] = float(price_min)
            metrics["price_max"] = float(price_max)
            metrics["price_range"] = float(price_max - price_min)

            if price_min <= 0:
                errors.append(f"Invalid price found: {price_min}")

        # Check 6: Volume sanity
        if len(df) > 0:
            zero_volume_count = (df["volume"] == 0).sum()
            metrics["zero_volume_candles"] = int(zero_volume_count)

            if zero_volume_count > actual_points * 0.1:  # >10% zero volume
                errors.append(
                    f"Too many zero-volume candles: {zero_volume_count} "
                    f"({zero_volume_count/actual_points*100:.1f}%)"
                )

        # Overall validation
        is_valid = len(errors) == 0

        return {
            "is_valid": is_valid,
            "metrics": metrics,
            "errors": errors
        }

    async def collect_all_symbols(
        self,
        symbols: Optional[List[str]] = None,
        interval: str = "60"
    ) -> Dict[str, Dict[str, Any]]:
        """
        Collect data for multiple symbols in parallel

        Args:
            symbols: List of symbols (default from settings)
            interval: Kline interval

        Returns:
            Dict mapping symbol to collection result
        """
        symbols = symbols or self.settings.retrain_data_symbols

        logger.info(f"Collecting data for {len(symbols)} symbols: {symbols}")

        results = {}

        for symbol in symbols:
            result = await self.collect_training_data(
                symbol=symbol,
                interval=interval
            )
            results[symbol] = result

        # Summary statistics
        successful = sum(1 for r in results.values() if r["success"])
        failed = len(results) - successful

        logger.info(
            f"Data collection complete: {successful} successful, {failed} failed"
        )

        return results
