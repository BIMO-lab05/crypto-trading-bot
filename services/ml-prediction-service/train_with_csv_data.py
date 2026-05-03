#!/usr/bin/env python3
"""
Train ML Models with 24-Month CSV Data
Purpose: Train LSTM and GRU models using comprehensive historical data
Target: R² score > 0.99 with 100 epochs and 24 months of data

Symbols: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT, APTUSDT, DOTUSDT, LTCUSDT, AVAXUSDT, ARBUSDT
Models per symbol: LSTM + GRU = 20 total models
Data source: CSV files in data/ml_training/ (24 months of hourly data)
"""

import asyncio
import pandas as pd
from datetime import datetime
from typing import List, Dict, Optional
import logging
import sys
import os
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
import json
import time

# Set epochs to 100 via environment variable BEFORE importing models
os.environ['EPOCHS'] = '100'

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
        logging.FileHandler('training_24month.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Settings
settings = get_settings()

# Data directory
DATA_DIR = (_REPO_ROOT / 'data/ml_training')

# Symbols to train (those with 24-month CSV files)
SYMBOLS = [
    'BTCUSDT',
    'ETHUSDT',
    'BNBUSDT',
    'SOLUSDT',
    'ADAUSDT',
    'APTUSDT',
    'DOTUSDT',
    'LTCUSDT',
    'AVAXUSDT',
    'ARBUSDT'
]

# Training configuration
INTERVAL = '60'  # 60 minute candles (1H)
EPOCHS = 100  # Train for 100 epochs for better convergence
MIN_SAMPLES_REQUIRED = 1000  # Minimum data points needed for training
TARGET_R2_SCORE = 0.99  # Target R² score for production


class CSVModelTrainer:
    """Handles training of all ML models using CSV data"""

    def __init__(self):
        """Initialize trainer"""
        self.training_results: Dict = {}

    def load_csv_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """
        Load historical candle data from CSV file

        Args:
            symbol: Trading symbol (e.g., BTCUSDT)

        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
        """
        try:
            # Construct CSV file path
            csv_file = DATA_DIR / f"{symbol}_1H_24months_20251208.csv"

            logger.info(f"Loading data for {symbol} from {csv_file}")

            # Check if file exists
            if not csv_file.exists():
                logger.error(f"CSV file not found: {csv_file}")
                return None

            # Load CSV data
            df = pd.read_csv(csv_file)

            # Verify required columns
            required_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            if not all(col in df.columns for col in required_columns):
                logger.error(f"Missing required columns in {csv_file}")
                logger.error(f"Found columns: {df.columns.tolist()}")
                return None

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Convert price/volume columns to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)

            logger.info(f"Loaded {len(df)} candles for {symbol}")
            logger.info(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            logger.info(f"Price range: ${df['close'].min():.2f} - ${df['close'].max():.2f}")

            return df

        except Exception as e:
            logger.error(f"Error loading CSV data for {symbol}: {e}", exc_info=True)
            return None

    async def train_lstm_model(self, symbol: str, data: pd.DataFrame, epochs: int = 100) -> Dict:
        """
        Train LSTM model for a symbol

        Args:
            symbol: Trading symbol
            data: Historical price data
            epochs: Number of training epochs

        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training LSTM model for {symbol} ({len(data)} samples, {epochs} epochs)")
            logger.info(f"{'='*60}")

            start_time = time.time()

            # Initialize LSTM predictor
            predictor = LSTMPricePredictor(symbol=symbol, interval=INTERVAL)

            # Train model with specified epochs
            # Note: The train method uses internal epoch configuration
            # We'll need to modify it if we want to override epochs
            model_info = await predictor.train(data)

            training_time = time.time() - start_time

            # Extract results
            result = {
                'model_type': 'LSTM',
                'symbol': symbol,
                'status': 'SUCCESS',
                'r2_score': model_info.validation_r2_score,
                'mae': model_info.validation_mae,
                'rmse': model_info.validation_rmse,
                'training_samples': model_info.training_samples,
                'total_samples': len(data),
                'training_duration': training_time,
                'model_version': model_info.model_version,
                'epochs_configured': epochs,
                'meets_target': model_info.validation_r2_score >= TARGET_R2_SCORE
            }

            # Log results
            logger.info(f"\nLSTM Training Results for {symbol}:")
            logger.info(f"  R² Score: {result['r2_score']:.6f} {'✓' if result['meets_target'] else '✗'}")
            logger.info(f"  MAE: {result['mae']:.4f}")
            logger.info(f"  RMSE: {result['rmse']:.4f}")
            logger.info(f"  Training samples: {result['training_samples']}/{result['total_samples']}")
            logger.info(f"  Duration: {result['training_duration']:.2f}s")

            return result

        except Exception as e:
            logger.error(f"LSTM training failed for {symbol}: {e}", exc_info=True)
            return {
                'model_type': 'LSTM',
                'symbol': symbol,
                'status': 'FAILED',
                'error': str(e),
                'total_samples': len(data),
                'meets_target': False
            }

    async def train_gru_model(self, symbol: str, data: pd.DataFrame, epochs: int = 100) -> Dict:
        """
        Train GRU model for a symbol

        Args:
            symbol: Trading symbol
            data: Historical price data
            epochs: Number of training epochs

        Returns:
            Dictionary with training results
        """
        try:
            logger.info(f"\n{'='*60}")
            logger.info(f"Training GRU model for {symbol} ({len(data)} samples, {epochs} epochs)")
            logger.info(f"{'='*60}")

            start_time = time.time()

            # Initialize GRU predictor
            predictor = GRUPricePredictor(symbol=symbol, interval=INTERVAL)

            # Train model
            model_info = await predictor.train(data)

            training_time = time.time() - start_time

            # Extract results
            result = {
                'model_type': 'GRU',
                'symbol': symbol,
                'status': 'SUCCESS',
                'r2_score': model_info.validation_r2_score,
                'mae': model_info.validation_mae,
                'rmse': model_info.validation_rmse,
                'training_samples': model_info.training_samples,
                'total_samples': len(data),
                'training_duration': training_time,
                'model_version': model_info.model_version,
                'epochs_configured': epochs,
                'meets_target': model_info.validation_r2_score >= TARGET_R2_SCORE
            }

            # Log results
            logger.info(f"\nGRU Training Results for {symbol}:")
            logger.info(f"  R² Score: {result['r2_score']:.6f} {'✓' if result['meets_target'] else '✗'}")
            logger.info(f"  MAE: {result['mae']:.4f}")
            logger.info(f"  RMSE: {result['rmse']:.4f}")
            logger.info(f"  Training samples: {result['training_samples']}/{result['total_samples']}")
            logger.info(f"  Duration: {result['training_duration']:.2f}s")

            return result

        except Exception as e:
            logger.error(f"GRU training failed for {symbol}: {e}", exc_info=True)
            return {
                'model_type': 'GRU',
                'symbol': symbol,
                'status': 'FAILED',
                'error': str(e),
                'total_samples': len(data),
                'meets_target': False
            }

    async def train_all_models(self, train_lstm: bool = True, train_gru: bool = True):
        """
        Train all models for all symbols

        Args:
            train_lstm: Whether to train LSTM models
            train_gru: Whether to train GRU models
        """
        try:
            logger.info(f"\n{'#'*80}")
            logger.info("Starting ML Model Training Pipeline with 24-Month CSV Data")
            logger.info(f"Symbols: {', '.join(SYMBOLS)}")
            logger.info(f"Epochs: {EPOCHS}")
            logger.info(f"Target R² Score: {TARGET_R2_SCORE}")
            logger.info(f"Train LSTM: {train_lstm}, Train GRU: {train_gru}")
            logger.info(f"{'#'*80}\n")

            # Training results storage
            all_results = []
            total_start_time = time.time()

            # Train models for each symbol
            for symbol in SYMBOLS:
                logger.info(f"\n{'*'*80}")
                logger.info(f"Processing {symbol}")
                logger.info(f"{'*'*80}")

                # Load CSV data
                data = self.load_csv_data(symbol)

                if data is None or len(data) < MIN_SAMPLES_REQUIRED:
                    logger.warning(f"Insufficient data for {symbol} (need {MIN_SAMPLES_REQUIRED}, got {len(data) if data is not None else 0})")
                    all_results.append({
                        'symbol': symbol,
                        'status': 'SKIPPED',
                        'reason': 'Insufficient data'
                    })
                    continue

                # Train LSTM model
                if train_lstm:
                    lstm_result = await self.train_lstm_model(symbol, data, epochs=EPOCHS)
                    all_results.append(lstm_result)

                    # Small delay between models
                    await asyncio.sleep(1)

                # Train GRU model
                if train_gru:
                    gru_result = await self.train_gru_model(symbol, data, epochs=EPOCHS)
                    all_results.append(gru_result)

                # Delay between symbols
                await asyncio.sleep(2)

            total_time = time.time() - total_start_time

            # Store results
            self.training_results = {
                'timestamp': datetime.utcnow().isoformat(),
                'data_source': 'CSV files (24 months)',
                'epochs': EPOCHS,
                'total_symbols': len(SYMBOLS),
                'total_models_attempted': len(all_results),
                'total_training_time_seconds': total_time,
                'results': all_results
            }

            # Generate summary report
            self.generate_summary_report()

            # Save results to file
            self.save_results()

        except Exception as e:
            logger.error(f"Training pipeline failed: {e}", exc_info=True)
            raise

    def generate_summary_report(self):
        """Generate and display training summary"""
        results = self.training_results.get('results', [])
        total_time = self.training_results.get('total_training_time_seconds', 0)

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
            avg_samples = sum(r.get('training_samples', 0) for r in successful) / len(successful)
        else:
            avg_r2 = avg_mae = avg_rmse = avg_duration = avg_samples = 0

        # Print summary
        logger.info(f"\n{'#'*80}")
        logger.info("TRAINING SUMMARY - 24 MONTH CSV DATA")
        logger.info(f"{'#'*80}")
        logger.info(f"\nTotal symbols processed: {len(SYMBOLS)}")
        logger.info(f"Total models attempted: {len(results)}")
        logger.info(f"Successful: {len(successful)} ✓")
        logger.info(f"Failed: {len(failed)} ✗")
        logger.info(f"Skipped: {len(skipped)} -")
        logger.info(f"Meeting target (R² ≥ {TARGET_R2_SCORE}): {len(meets_target)}/{len(successful)}")
        logger.info(f"Total training time: {total_time:.2f}s ({total_time/60:.2f} minutes)")

        if successful:
            logger.info(f"\nAverage Metrics (Successful Models):")
            logger.info(f"  Average R² Score: {avg_r2:.6f}")
            logger.info(f"  Average MAE: {avg_mae:.4f}")
            logger.info(f"  Average RMSE: {avg_rmse:.4f}")
            logger.info(f"  Average Training Samples: {avg_samples:.0f}")
            logger.info(f"  Average Duration: {avg_duration:.2f}s")

        # Per-symbol breakdown
        logger.info(f"\n{'='*80}")
        logger.info("PER-SYMBOL BREAKDOWN")
        logger.info(f"{'='*80}")

        for symbol in SYMBOLS:
            symbol_results = [r for r in results if r.get('symbol') == symbol]

            if not symbol_results:
                continue

            logger.info(f"\n{symbol}:")
            for result in symbol_results:
                model_type = result.get('model_type', 'Unknown')
                status = result.get('status', 'Unknown')

                if status == 'SUCCESS':
                    r2 = result.get('r2_score', 0)
                    samples = result.get('training_samples', 0)
                    duration = result.get('training_duration', 0)
                    target_met = '✓' if result.get('meets_target', False) else '✗'
                    logger.info(f"  {model_type}: R²={r2:.6f} {target_met} ({samples} samples, {duration:.1f}s)")
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
                gap = TARGET_R2_SCORE - r2
                logger.info(f"  {symbol} ({model_type}): R²={r2:.6f} (gap: {gap:.4f})")

        # Models meeting target
        if meets_target:
            logger.info(f"\n{'='*80}")
            logger.info("PRODUCTION-READY MODELS (Meeting Target)")
            logger.info(f"{'='*80}")

            for result in meets_target:
                symbol = result.get('symbol')
                model_type = result.get('model_type')
                r2 = result.get('r2_score', 0)
                logger.info(f"  ✓ {symbol} ({model_type}): R²={r2:.6f}")

        logger.info(f"\n{'#'*80}\n")

    def save_results(self):
        """Save training results to JSON file"""
        try:
            # Save to models directory
            results_file = Path(settings.models_dir) / 'training_results_24month.json'
            results_file.parent.mkdir(parents=True, exist_ok=True)

            with open(results_file, 'w') as f:
                json.dump(self.training_results, f, indent=2)

            logger.info(f"Training results saved to: {results_file}")

        except Exception as e:
            logger.error(f"Failed to save results: {e}")


async def main():
    """Main training pipeline"""
    try:
        # Create trainer
        trainer = CSVModelTrainer()

        # Train all models (both LSTM and GRU)
        await trainer.train_all_models(train_lstm=True, train_gru=True)

        logger.info("\nTraining pipeline completed successfully!")
        logger.info("Check training_24month.log for detailed logs")
        logger.info("Check models/training_results_24month.json for results")

    except KeyboardInterrupt:
        logger.info("\nTraining interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Training pipeline failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    # Run training pipeline
    asyncio.run(main())
