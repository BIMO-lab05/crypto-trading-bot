#!/usr/bin/env python3
"""
Train All ML Models for Cryptocurrency Price Prediction
Purpose: Train LSTM and GRU models for all 7 trading symbols
Target: R² score > 0.99 for production readiness

Symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT
Models per symbol: LSTM + GRU = 14 total models
Data source: TimescaleDB (localhost:5433, database: market_data)
"""

import asyncio
import asyncpg
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import sys
from pathlib import Path
import json

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from app.ml_models.gru_model import GRUPricePredictor
from app.predictor import LSTMPricePredictor
from app.config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('training.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': 5433,
    'database': 'market_data',
    'user': 'cryptobot',
    'password': 'timescale_dev_password'
}

# Symbols to train
SYMBOLS = [
    'BTCUSDT',
    'ETHUSDT',
    'BNBUSDT',
    'SOLUSDT',
    'XRPUSDT',
    'ADAUSDT',
    'DOGEUSDT'
]

# Training configuration
INTERVAL = '60'  # 60 minute candles
MIN_SAMPLES_REQUIRED = 200  # Minimum data points needed for training
TARGET_R2_SCORE = 0.99  # Target R² score for production


class ModelTrainer:
    """Handles training of all ML models"""

    def __init__(self):
        """Initialize trainer"""
        self.db_pool: Optional[asyncpg.Pool] = None
        self.training_results: Dict = {}

    async def connect_database(self):
        """Connect to TimescaleDB"""
        try:
            logger.info(f"Connecting to TimescaleDB at {DB_CONFIG['host']}:{DB_CONFIG['port']}")

            self.db_pool = await asyncpg.create_pool(
                host=DB_CONFIG['host'],
                port=DB_CONFIG['port'],
                database=DB_CONFIG['database'],
                user=DB_CONFIG['user'],
                password=DB_CONFIG['password'],
                min_size=1,
                max_size=5,
                timeout=30
            )

            logger.info("Successfully connected to TimescaleDB")

            # Test connection
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval('SELECT COUNT(*) FROM market_data.candles')
                logger.info(f"Database contains {result} total candles")

        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def close_database(self):
        """Close database connection"""
        if self.db_pool:
            await self.db_pool.close()
            logger.info("Closed database connection")

    async def fetch_historical_data(
        self,
        symbol: str,
        interval: str = '60',
        days: int = 30
    ) -> Optional[pd.DataFrame]:
        """
        Fetch historical candle data from TimescaleDB

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)
            interval: Candle interval in minutes
            days: Number of days of historical data to fetch

        Returns:
            DataFrame with columns [time as timestamp, open, high, low, close, volume]
        """
        try:
            logger.info(f"Fetching {days} days of {interval}m candles for {symbol}")

            # Calculate time range
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            # Query database
            query = """
                SELECT
                    time as timestamp,
                    open,
                    high,
                    low,
                    close,
                    volume
                FROM market_data.candles
                WHERE symbol = $1
                    AND interval = $2
                    AND time >= $3
                    AND time <= $4
                ORDER BY time ASC
            """

            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    query,
                    symbol,
                    interval,
                    start_time,
                    end_time
                )

            if not rows:
                logger.warning(f"No data found for {symbol}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Convert to appropriate types
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['open'] = df['open'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['close'] = df['close'].astype(float)
            df['volume'] = df['volume'].astype(float)

            logger.info(f"Fetched {len(df)} candles for {symbol}")
            logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            logger.info(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

            return df

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    async def train_lstm_model(self, symbol: str, data: pd.DataFrame) -> Dict:
        """
        Train LSTM model for a symbol

        Args:
            symbol: Trading symbol
            data: Historical price data

        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training LSTM model for {symbol}")
            logger.info(f"{'='*60}")

            # Initialize LSTM predictor
            predictor = LSTMPricePredictor(symbol=symbol, interval=INTERVAL)

            # Train model
            model_info = await predictor.train(data)

            # Extract results
            result = {
                'model_type': 'LSTM',
                'symbol': symbol,
                'status': 'SUCCESS',
                'r2_score': model_info.validation_r2_score,
                'mae': model_info.validation_mae,
                'rmse': model_info.validation_rmse,
                'training_samples': model_info.training_samples,
                'training_duration': model_info.training_duration_seconds,
                'model_version': model_info.model_version,
                'meets_target': model_info.validation_r2_score >= TARGET_R2_SCORE
            }

            # Log results
            logger.info(f"\nLSTM Training Results for {symbol}:")
            logger.info(f"  R² Score: {result['r2_score']:.6f} {'✓' if result['meets_target'] else '✗'}")
            logger.info(f"  MAE: {result['mae']:.4f}")
            logger.info(f"  RMSE: {result['rmse']:.4f}")
            logger.info(f"  Training samples: {result['training_samples']}")
            logger.info(f"  Duration: {result['training_duration']:.2f}s")

            return result

        except Exception as e:
            logger.error(f"LSTM training failed for {symbol}: {e}", exc_info=True)
            return {
                'model_type': 'LSTM',
                'symbol': symbol,
                'status': 'FAILED',
                'error': str(e),
                'meets_target': False
            }

    async def train_gru_model(self, symbol: str, data: pd.DataFrame) -> Dict:
        """
        Train GRU model for a symbol

        Args:
            symbol: Trading symbol
            data: Historical price data

        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training GRU model for {symbol}")
            logger.info(f"{'='*60}")

            # Initialize GRU predictor
            predictor = GRUPricePredictor(symbol=symbol, interval=INTERVAL)

            # Train model
            model_info = await predictor.train(data)

            # Extract results
            result = {
                'model_type': 'GRU',
                'symbol': symbol,
                'status': 'SUCCESS',
                'r2_score': model_info.validation_r2_score,
                'mae': model_info.validation_mae,
                'rmse': model_info.validation_rmse,
                'training_samples': model_info.training_samples,
                'training_duration': model_info.training_duration_seconds,
                'model_version': model_info.model_version,
                'meets_target': model_info.validation_r2_score >= TARGET_R2_SCORE
            }

            # Log results
            logger.info(f"\nGRU Training Results for {symbol}:")
            logger.info(f"  R² Score: {result['r2_score']:.6f} {'✓' if result['meets_target'] else '✗'}")
            logger.info(f"  MAE: {result['mae']:.4f}")
            logger.info(f"  RMSE: {result['rmse']:.4f}")
            logger.info(f"  Training samples: {result['training_samples']}")
            logger.info(f"  Duration: {result['training_duration']:.2f}s")

            return result

        except Exception as e:
            logger.error(f"GRU training failed for {symbol}: {e}", exc_info=True)
            return {
                'model_type': 'GRU',
                'symbol': symbol,
                'status': 'FAILED',
                'error': str(e),
                'meets_target': False
            }

    async def train_all_models(self):
        """Train all models for all symbols"""
        try:
            logger.info(f"\n{'#'*80}")
            logger.info("Starting ML Model Training Pipeline")
            logger.info(f"Symbols: {', '.join(SYMBOLS)}")
            logger.info(f"Target R² Score: {TARGET_R2_SCORE}")
            logger.info(f"{'#'*80}\n")

            # Connect to database
            await self.connect_database()

            # Training results storage
            all_results = []

            # Train models for each symbol
            for symbol in SYMBOLS:
                logger.info(f"\n{'*'*80}")
                logger.info(f"Processing {symbol}")
                logger.info(f"{'*'*80}")

                # Fetch historical data
                data = await self.fetch_historical_data(symbol, interval=INTERVAL, days=30)

                if data is None or len(data) < MIN_SAMPLES_REQUIRED:
                    logger.warning(f"Insufficient data for {symbol} (need {MIN_SAMPLES_REQUIRED}, got {len(data) if data is not None else 0})")
                    all_results.append({
                        'symbol': symbol,
                        'status': 'SKIPPED',
                        'reason': 'Insufficient data'
                    })
                    continue

                # Train LSTM model
                lstm_result = await self.train_lstm_model(symbol, data)
                all_results.append(lstm_result)

                # Small delay between models
                await asyncio.sleep(1)

                # Train GRU model
                gru_result = await self.train_gru_model(symbol, data)
                all_results.append(gru_result)

                # Delay between symbols
                await asyncio.sleep(2)

            # Store results
            self.training_results = {
                'timestamp': datetime.utcnow().isoformat(),
                'total_symbols': len(SYMBOLS),
                'total_models_attempted': len(all_results),
                'results': all_results
            }

            # Generate summary report
            self.generate_summary_report()

            # Save results to file
            self.save_results()

        except Exception as e:
            logger.error(f"Training pipeline failed: {e}", exc_info=True)
            raise
        finally:
            await self.close_database()

    def generate_summary_report(self):
        """Generate and display training summary"""
        results = self.training_results.get('results', [])

        # Calculate statistics
        successful = [r for r in results if r.get('status') == 'SUCCESS']
        failed = [r for r in results if r.get('status') == 'FAILED']
        skipped = [r for r in results if r.get('status') == 'SKIPPED']
        meets_target = [r for r in successful if r.get('meets_target', False)]

        # Calculate average metrics for successful models
        if successful:
            avg_r2 = sum(r.get('r2_score', 0) for r in successful) / len(successful)
            avg_mae = sum(r.get('mae', 0) for r in successful) / len(successful)
            avg_rmse = sum(r.get('rmse', 0) for r in successful) / len(successful)
            avg_duration = sum(r.get('training_duration', 0) for r in successful) / len(successful)
        else:
            avg_r2 = avg_mae = avg_rmse = avg_duration = 0

        # Print summary
        logger.info(f"\n{'#'*80}")
        logger.info("TRAINING SUMMARY")
        logger.info(f"{'#'*80}")
        logger.info(f"\nTotal symbols processed: {len(SYMBOLS)}")
        logger.info(f"Total models attempted: {len(results)}")
        logger.info(f"Successful: {len(successful)} ✓")
        logger.info(f"Failed: {len(failed)} ✗")
        logger.info(f"Skipped: {len(skipped)} -")
        logger.info(f"Meeting target (R² ≥ {TARGET_R2_SCORE}): {len(meets_target)}/{len(successful)}")

        if successful:
            logger.info(f"\nAverage Metrics (Successful Models):")
            logger.info(f"  Average R² Score: {avg_r2:.6f}")
            logger.info(f"  Average MAE: {avg_mae:.4f}")
            logger.info(f"  Average RMSE: {avg_rmse:.4f}")
            logger.info(f"  Average Duration: {avg_duration:.2f}s")

        # Per-symbol breakdown
        logger.info(f"\n{'='*80}")
        logger.info("PER-SYMBOL BREAKDOWN")
        logger.info(f"{'='*80}")

        for symbol in SYMBOLS:
            symbol_results = [r for r in results if r.get('symbol') == symbol]

            logger.info(f"\n{symbol}:")
            for result in symbol_results:
                model_type = result.get('model_type', 'Unknown')
                status = result.get('status', 'Unknown')

                if status == 'SUCCESS':
                    r2 = result.get('r2_score', 0)
                    target_met = '✓' if result.get('meets_target', False) else '✗'
                    logger.info(f"  {model_type}: R²={r2:.6f} {target_met}")
                elif status == 'FAILED':
                    error = result.get('error', 'Unknown error')
                    logger.info(f"  {model_type}: FAILED - {error}")
                else:
                    reason = result.get('reason', 'Unknown reason')
                    logger.info(f"  SKIPPED - {reason}")

        # Models not meeting target
        if successful and len(meets_target) < len(successful):
            logger.info(f"\n{'='*80}")
            logger.info("MODELS NOT MEETING TARGET (Require Attention)")
            logger.info(f"{'='*80}")

            below_target = [r for r in successful if not r.get('meets_target', False)]
            for result in below_target:
                symbol = result.get('symbol')
                model_type = result.get('model_type')
                r2 = result.get('r2_score', 0)
                logger.info(f"  {symbol} ({model_type}): R²={r2:.6f} (target: {TARGET_R2_SCORE})")

        logger.info(f"\n{'#'*80}\n")

    def save_results(self):
        """Save training results to JSON file"""
        try:
            # Save to trained_models directory
            results_file = Path(settings.models_dir) / 'training_results.json'
            results_file.parent.mkdir(parents=True, exist_ok=True)

            with open(results_file, 'w') as f:
                json.dump(self.training_results, f, indent=2)

            logger.info(f"Training results saved to: {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    async def verify_models(self):
        """Verify that trained models exist and can be loaded"""
        logger.info(f"\n{'='*80}")
        logger.info("VERIFYING TRAINED MODELS")
        logger.info(f"{'='*80}\n")

        models_dir = Path(settings.models_dir)

        for symbol in SYMBOLS:
            # Check LSTM model
            lstm_path = models_dir / f"{symbol}_{INTERVAL}m_lstm.keras"
            lstm_exists = lstm_path.exists()

            # Check GRU model
            gru_path = models_dir / f"{symbol}_{INTERVAL}m_gru.keras"
            gru_exists = gru_path.exists()

            logger.info(f"{symbol}:")
            logger.info(f"  LSTM: {'✓ Found' if lstm_exists else '✗ Missing'}")
            logger.info(f"  GRU:  {'✓ Found' if gru_exists else '✗ Missing'}")

        logger.info(f"\n{'='*80}\n")


async def main():
    """Main training pipeline"""
    try:
        # Create trainer
        trainer = ModelTrainer()

        # Train all models
        await trainer.train_all_models()

        # Verify models exist
        await trainer.verify_models()

        logger.info("Training pipeline completed successfully!")

    except KeyboardInterrupt:
        logger.info("\nTraining interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Training pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run training pipeline
    asyncio.run(main())
