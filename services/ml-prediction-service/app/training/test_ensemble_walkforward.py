"""
Walk-Forward Validation Test for Ensemble Predictor
Tests ensemble performance across multiple time periods and symbols

Validation Strategy:
- Time-based train/test splits (no data leakage)
- Multiple validation windows (walk-forward)
- Compare ensemble vs individual components
- Calculate accuracy, precision, recall, F1-score
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from collections import defaultdict

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import ensemble predictor
from inference.ensemble import EnsemblePredictor, EnsembleSignal


class EnsembleWalkForwardValidator:
    """
    Walk-forward validation for ensemble predictor

    Tests ensemble predictions against actual market movements
    using time-based splits to prevent data leakage
    """

    def __init__(
        self,
        symbols: List[str] = ["BTCUSDT", "ETHUSDT"],
        interval: str = "60",
        validation_windows: int = 5,
        window_size_hours: int = 168  # 1 week
    ):
        """
        Initialize validator

        Args:
            symbols: Trading pairs to test
            interval: Timeframe in minutes
            validation_windows: Number of walk-forward windows
            window_size_hours: Size of each validation window in hours
        """
        self.symbols = symbols
        self.interval = interval
        self.validation_windows = validation_windows
        self.window_size_hours = window_size_hours

        # Initialize ensemble predictor
        self.ensemble = EnsemblePredictor(
            ta_weight=0.40,
            ml_weight=0.30,
            sentiment_weight=0.15,
            multi_tf_weight=0.15
        )

        # Results storage
        self.results = defaultdict(list)

    async def fetch_market_data(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> pd.DataFrame:
        """
        Fetch historical market data for validation period

        Args:
            symbol: Trading pair
            start_time: Start of validation window
            end_time: End of validation window

        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate number of candles needed
            hours_diff = (end_time - start_time).total_seconds() / 3600
            limit = int(hours_diff) + 10  # Extra buffer

            # Import httpx for API calls
            import httpx

            # Call market-data-service
            async with httpx.AsyncClient(timeout=30.0) as client:
                url = f"http://localhost:8002/api/v1/klines/{symbol}"
                params = {
                    "interval": self.interval,
                    "limit": limit
                }

                response = await client.get(url, params=params)

                if response.status_code != 200:
                    print(f"⚠️ Failed to fetch data for {symbol}: {response.status_code}")
                    return pd.DataFrame()

                result = response.json()

                # Extract data array from response
                if not result.get('success') or not result.get('data'):
                    print(f"⚠️ No data returned for {symbol}")
                    return pd.DataFrame()

                # Convert to DataFrame
                df = pd.DataFrame(result['data'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                # Filter by time range
                df = df[
                    (df['timestamp'] >= start_time) &
                    (df['timestamp'] <= end_time)
                ]

                return df

        except Exception as e:
            print(f"❌ Error fetching market data: {e}")
            return pd.DataFrame()

    def calculate_actual_direction(
        self,
        current_price: float,
        future_price: float,
        threshold: float = 0.003  # 0.3% threshold
    ) -> str:
        """
        Calculate actual price direction

        Args:
            current_price: Current price
            future_price: Price N candles ahead
            threshold: Minimum % change to count as directional move

        Returns:
            "BUY" (price went up), "SELL" (price went down), or "NEUTRAL"
        """
        price_change_pct = (future_price - current_price) / current_price

        if price_change_pct > threshold:
            return "BUY"
        elif price_change_pct < -threshold:
            return "SELL"
        else:
            return "NEUTRAL"

    def calculate_metrics(
        self,
        predictions: List[str],
        actuals: List[str]
    ) -> Dict[str, float]:
        """
        Calculate performance metrics

        Args:
            predictions: List of predicted directions
            actuals: List of actual directions

        Returns:
            Dict with accuracy, precision, recall, F1-score
        """
        # Convert to numpy arrays
        preds = np.array(predictions)
        acts = np.array(actuals)

        # Overall accuracy
        accuracy = (preds == acts).mean()

        # Direction-specific metrics
        metrics = {"accuracy": accuracy}

        for direction in ["BUY", "SELL", "NEUTRAL"]:
            # True positives
            tp = ((preds == direction) & (acts == direction)).sum()
            # False positives
            fp = ((preds == direction) & (acts != direction)).sum()
            # False negatives
            fn = ((preds != direction) & (acts == direction)).sum()

            # Precision
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            # Recall
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            # F1-score
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

            metrics[f"{direction.lower()}_precision"] = precision
            metrics[f"{direction.lower()}_recall"] = recall
            metrics[f"{direction.lower()}_f1"] = f1

        return metrics

    async def validate_window(
        self,
        symbol: str,
        window_start: datetime,
        window_end: datetime
    ) -> Dict[str, any]:
        """
        Validate ensemble on a single time window

        Args:
            symbol: Trading pair
            window_start: Start of validation window
            window_end: End of validation window

        Returns:
            Dict with validation results for this window
        """
        print(f"\n{'='*60}")
        print(f"Validating {symbol} from {window_start.date()} to {window_end.date()}")
        print(f"{'='*60}")

        # Fetch market data for this window
        df = await self.fetch_market_data(symbol, window_start, window_end)

        if df.empty or len(df) < 10:
            print(f"⚠️ Insufficient data for {symbol} in this window")
            return None

        print(f"✅ Fetched {len(df)} candles")

        # Track predictions and actuals
        predictions = []
        actuals = []
        confidence_scores = []
        component_availability = []

        # Test ensemble on each candle (except last 5 - need future data)
        for idx in range(len(df) - 5):
            try:
                current_candle = df.iloc[idx]
                future_candle = df.iloc[idx + 5]  # 5 candles ahead (5 hours for 60m)

                current_price = float(current_candle['close'])
                future_price = float(future_candle['close'])

                # Get ensemble prediction
                signal = await self.ensemble.predict(
                    symbol=symbol,
                    interval=self.interval,
                    ml_model="LSTM"
                )

                # Calculate actual direction
                actual_direction = self.calculate_actual_direction(
                    current_price,
                    future_price
                )

                # Store results
                predictions.append(signal.direction)
                actuals.append(actual_direction)
                confidence_scores.append(signal.confidence)
                component_availability.append(signal.components_used)

                # Progress indicator
                if (idx + 1) % 20 == 0:
                    print(f"  Tested {idx + 1}/{len(df) - 5} candles...")

            except Exception as e:
                print(f"⚠️ Error at candle {idx}: {e}")
                continue

        if not predictions:
            print(f"❌ No valid predictions for {symbol}")
            return None

        # Calculate metrics
        metrics = self.calculate_metrics(predictions, actuals)

        # Add metadata
        metrics['symbol'] = symbol
        metrics['window_start'] = window_start
        metrics['window_end'] = window_end
        metrics['total_predictions'] = len(predictions)
        metrics['avg_confidence'] = np.mean(confidence_scores)
        metrics['avg_components_used'] = np.mean(component_availability)

        # Print window results
        print(f"\n📊 Window Results:")
        print(f"   Total Predictions: {len(predictions)}")
        print(f"   Overall Accuracy: {metrics['accuracy']:.2%}")
        print(f"   Avg Confidence: {metrics['avg_confidence']:.2f}")
        print(f"   Avg Components Used: {metrics['avg_components_used']:.1f}/4")
        print(f"\n   BUY  - Precision: {metrics['buy_precision']:.2%}, Recall: {metrics['buy_recall']:.2%}, F1: {metrics['buy_f1']:.2%}")
        print(f"   SELL - Precision: {metrics['sell_precision']:.2%}, Recall: {metrics['sell_recall']:.2%}, F1: {metrics['sell_f1']:.2%}")

        return metrics

    async def run_validation(self) -> Dict[str, any]:
        """
        Run complete walk-forward validation

        Returns:
            Dict with aggregated results across all windows and symbols
        """
        print("\n" + "="*80)
        print("🧪 ENSEMBLE WALK-FORWARD VALIDATION TEST")
        print("="*80)
        print(f"Symbols: {', '.join(self.symbols)}")
        print(f"Interval: {self.interval}m")
        print(f"Validation Windows: {self.validation_windows}")
        print(f"Window Size: {self.window_size_hours} hours ({self.window_size_hours // 24} days)")
        print("="*80)

        all_results = []

        # Current time
        end_time = datetime.utcnow()

        # For each validation window
        for window_idx in range(self.validation_windows):
            window_end = end_time - timedelta(hours=window_idx * self.window_size_hours)
            window_start = window_end - timedelta(hours=self.window_size_hours)

            print(f"\n\n{'#'*80}")
            print(f"# VALIDATION WINDOW {window_idx + 1}/{self.validation_windows}")
            print(f"# Period: {window_start.date()} to {window_end.date()}")
            print(f"{'#'*80}")

            # Test each symbol
            for symbol in self.symbols:
                window_results = await self.validate_window(
                    symbol,
                    window_start,
                    window_end
                )

                if window_results:
                    all_results.append(window_results)

                # Small delay between symbols
                await asyncio.sleep(2)

        # Aggregate results
        if not all_results:
            print("\n❌ No validation results collected")
            return None

        # Convert to DataFrame for analysis
        results_df = pd.DataFrame(all_results)

        # Calculate overall statistics
        print("\n\n" + "="*80)
        print("📈 OVERALL VALIDATION RESULTS")
        print("="*80)

        print(f"\nTotal Validation Windows: {len(all_results)}")
        print(f"Total Predictions Made: {results_df['total_predictions'].sum()}")

        print(f"\n📊 Aggregated Metrics (Mean ± Std):")
        print(f"   Overall Accuracy: {results_df['accuracy'].mean():.2%} ± {results_df['accuracy'].std():.2%}")
        print(f"   Avg Confidence: {results_df['avg_confidence'].mean():.3f} ± {results_df['avg_confidence'].std():.3f}")
        print(f"   Avg Components Used: {results_df['avg_components_used'].mean():.2f}/4")

        print(f"\n   BUY Signals:")
        print(f"      Precision: {results_df['buy_precision'].mean():.2%} ± {results_df['buy_precision'].std():.2%}")
        print(f"      Recall:    {results_df['buy_recall'].mean():.2%} ± {results_df['buy_recall'].std():.2%}")
        print(f"      F1-Score:  {results_df['buy_f1'].mean():.2%} ± {results_df['buy_f1'].std():.2%}")

        print(f"\n   SELL Signals:")
        print(f"      Precision: {results_df['sell_precision'].mean():.2%} ± {results_df['sell_precision'].std():.2%}")
        print(f"      Recall:    {results_df['sell_recall'].mean():.2%} ± {results_df['sell_recall'].std():.2%}")
        print(f"      F1-Score:  {results_df['sell_f1'].mean():.2%} ± {results_df['sell_f1'].std():.2%}")

        print(f"\n   NEUTRAL Signals:")
        print(f"      Precision: {results_df['neutral_precision'].mean():.2%} ± {results_df['neutral_precision'].std():.2%}")
        print(f"      Recall:    {results_df['neutral_recall'].mean():.2%} ± {results_df['neutral_recall'].std():.2%}")
        print(f"      F1-Score:  {results_df['neutral_f1'].mean():.2%} ± {results_df['neutral_f1'].std():.2%}")

        # Per-symbol breakdown
        print(f"\n📊 Per-Symbol Results:")
        for symbol in self.symbols:
            symbol_results = results_df[results_df['symbol'] == symbol]
            if not symbol_results.empty:
                print(f"\n   {symbol}:")
                print(f"      Windows Tested: {len(symbol_results)}")
                print(f"      Accuracy: {symbol_results['accuracy'].mean():.2%} ± {symbol_results['accuracy'].std():.2%}")
                print(f"      Confidence: {symbol_results['avg_confidence'].mean():.3f}")

        # Save results to file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = f"/tmp/ensemble_walkforward_results_{timestamp}.csv"
        results_df.to_csv(results_file, index=False)
        print(f"\n💾 Detailed results saved to: {results_file}")

        # Final assessment
        overall_accuracy = results_df['accuracy'].mean()
        print(f"\n\n{'='*80}")
        print("🎯 VALIDATION ASSESSMENT")
        print("="*80)

        if overall_accuracy >= 0.60:
            print("✅ PASS: Ensemble accuracy >= 60% - Production Ready!")
            status = "PASS"
        elif overall_accuracy >= 0.55:
            print("⚠️ MARGINAL: Ensemble accuracy 55-60% - Needs improvement")
            status = "MARGINAL"
        else:
            print("❌ FAIL: Ensemble accuracy < 55% - Not production ready")
            status = "FAIL"

        print("="*80)

        # Close ensemble predictor
        await self.ensemble.close()

        return {
            'status': status,
            'overall_accuracy': overall_accuracy,
            'results_file': results_file,
            'results_df': results_df
        }


async def main():
    """Run ensemble walk-forward validation test"""

    # Create validator
    validator = EnsembleWalkForwardValidator(
        symbols=["BTCUSDT", "ETHUSDT"],
        interval="60",
        validation_windows=5,  # 5 weeks of validation
        window_size_hours=168  # 1 week per window
    )

    # Run validation
    results = await validator.run_validation()

    if results:
        print(f"\n✅ Validation complete. Status: {results['status']}")
        return results['status'] == "PASS"
    else:
        print("\n❌ Validation failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
