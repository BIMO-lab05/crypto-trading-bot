#!/usr/bin/env python3
"""
Data Quality Analysis and Enhancement Script
============================================
Purpose: Analyze, clean, and extend historical market data for ML training
Author: Data Researcher Agent
Date: 2025-11-20

This script performs:
1. Data quality analysis (outlier detection, statistical validation)
2. Data cleaning (remove/interpolate outliers)
3. Historical data fetching (extend from 30 to 90-180 days)
4. Validation and reporting

Database: TimescaleDB (PostgreSQL extension)
Target: 7 trading pairs (BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, XRPUSDT, ADAUSDT, DOGEUSDT)
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
import requests
from scipy import stats
import warnings
warnings.filterwarnings('ignore')


class DataQualityEnhancer:
    """
    Handles data quality analysis, cleaning, and historical data fetching
    """

    def __init__(self, db_host='localhost', db_port=5433, db_name='market_data',
                 db_user='cryptobot', db_password='timescale_dev_password'):
        """
        Initialize database connection and configuration

        Args:
            db_host: Database host address
            db_port: Database port
            db_name: Database name
            db_user: Database username
            db_password: Database password
        """
        # Database connection parameters
        self.db_params = {
            'host': db_host,
            'port': db_port,
            'dbname': db_name,
            'user': db_user,
            'password': db_password
        }

        # Trading symbols to analyze
        self.symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']

        # Data quality thresholds
        self.z_score_threshold = 3.0  # Standard deviations for outlier detection
        self.iqr_multiplier = 1.5     # IQR multiplier for outlier detection
        self.max_price_jump = 0.20    # Maximum 20% price change in single candle

        # Target historical data depth
        self.target_days = 120  # 120 days (4 months) for better ML training
        self.interval = '60'    # 1-hour candles

        # Bybit API configuration
        self.bybit_base_url = 'https://api.bybit.com'

        # Quality report storage
        self.quality_reports = {}

    def connect_db(self):
        """
        Establish connection to TimescaleDB

        Returns:
            psycopg2.connection: Database connection object
        """
        try:
            conn = psycopg2.connect(**self.db_params)
            print(f"✓ Connected to TimescaleDB at {self.db_params['host']}:{self.db_params['port']}")
            return conn
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            raise

    def fetch_symbol_data(self, symbol: str) -> pd.DataFrame:
        """
        Fetch all existing data for a symbol from database

        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')

        Returns:
            pd.DataFrame: Candle data with columns [timestamp, open, high, low, close, volume]
        """
        conn = self.connect_db()
        # Convert bigint timestamp (milliseconds) to TIMESTAMP for pandas compatibility
        query = """
            SELECT to_timestamp(timestamp/1000.0) as timestamp,
                   open, high, low, close, volume
            FROM klines
            WHERE symbol = %s AND interval = %s
            ORDER BY timestamp ASC
        """

        try:
            df = pd.read_sql(query, conn, params=(symbol, self.interval))
            # Timestamp already converted in SQL, just ensure it's datetime type
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            conn.close()
            print(f"  Fetched {len(df)} candles for {symbol}")
            return df
        except Exception as e:
            print(f"  ✗ Error fetching data for {symbol}: {e}")
            conn.close()
            return pd.DataFrame()

    def detect_outliers_zscore(self, series: pd.Series) -> pd.Series:
        """
        Detect outliers using Z-score method

        Args:
            series: Price series (close prices)

        Returns:
            pd.Series: Boolean mask where True indicates outlier
        """
        z_scores = np.abs(stats.zscore(series, nan_policy='omit'))
        return z_scores > self.z_score_threshold

    def detect_outliers_iqr(self, series: pd.Series) -> pd.Series:
        """
        Detect outliers using Interquartile Range (IQR) method

        Args:
            series: Price series (close prices)

        Returns:
            pd.Series: Boolean mask where True indicates outlier
        """
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1

        lower_bound = Q1 - self.iqr_multiplier * IQR
        upper_bound = Q3 + self.iqr_multiplier * IQR

        return (series < lower_bound) | (series > upper_bound)

    def detect_price_jumps(self, df: pd.DataFrame) -> pd.Series:
        """
        Detect sudden price jumps (>20% change in single candle)

        Args:
            df: DataFrame with OHLCV data

        Returns:
            pd.Series: Boolean mask where True indicates abnormal jump
        """
        # Calculate percentage change between consecutive closes
        pct_change = df['close'].pct_change().abs()

        # Also check open-to-close within same candle
        intra_candle_change = ((df['close'] - df['open']) / df['open']).abs()

        # Flag if either exceeds threshold
        return (pct_change > self.max_price_jump) | (intra_candle_change > self.max_price_jump)

    def detect_ohlcv_inconsistencies(self, df: pd.DataFrame) -> pd.Series:
        """
        Detect OHLCV data inconsistencies (High < Low, Close > High, etc.)

        Args:
            df: DataFrame with OHLCV data

        Returns:
            pd.Series: Boolean mask where True indicates inconsistency
        """
        inconsistent = (
            (df['high'] < df['low']) |           # High should be >= Low
            (df['close'] > df['high']) |         # Close should be <= High
            (df['close'] < df['low']) |          # Close should be >= Low
            (df['open'] > df['high']) |          # Open should be <= High
            (df['open'] < df['low']) |           # Open should be >= Low
            (df['volume'] < 0) |                 # Volume should be positive
            (df['close'] <= 0) |                 # Prices should be positive
            (df['open'] <= 0) |
            (df['high'] <= 0) |
            (df['low'] <= 0)
        )

        return inconsistent

    def analyze_data_quality(self, symbol: str) -> Dict:
        """
        Perform comprehensive data quality analysis for a symbol

        Args:
            symbol: Trading pair symbol

        Returns:
            Dict: Quality metrics and outlier information
        """
        print(f"\n{'='*60}")
        print(f"Analyzing data quality for {symbol}")
        print(f"{'='*60}")

        # Fetch data
        df = self.fetch_symbol_data(symbol)

        if df.empty:
            return {
                'symbol': symbol,
                'status': 'NO_DATA',
                'message': 'No data found in database'
            }

        # Basic statistics
        total_candles = len(df)
        date_range = f"{df['timestamp'].min()} to {df['timestamp'].max()}"
        days_coverage = (df['timestamp'].max() - df['timestamp'].min()).days

        # Detect outliers using multiple methods
        outliers_zscore = self.detect_outliers_zscore(df['close'])
        outliers_iqr = self.detect_outliers_iqr(df['close'])
        outliers_jumps = self.detect_price_jumps(df)
        outliers_inconsistent = self.detect_ohlcv_inconsistencies(df)

        # Combine all outlier detection methods
        combined_outliers = outliers_zscore | outliers_iqr | outliers_jumps | outliers_inconsistent

        # Count outliers
        zscore_count = outliers_zscore.sum()
        iqr_count = outliers_iqr.sum()
        jump_count = outliers_jumps.sum()
        inconsistent_count = outliers_inconsistent.sum()
        total_outliers = combined_outliers.sum()

        # Check for missing timestamps (gaps)
        expected_interval = pd.Timedelta(hours=1)
        time_diffs = df['timestamp'].diff()
        gaps = time_diffs[time_diffs > expected_interval * 1.5]  # Allow 50% tolerance

        # Statistical summary
        price_stats = {
            'mean': df['close'].mean(),
            'std': df['close'].std(),
            'min': df['close'].min(),
            'max': df['close'].max(),
            'median': df['close'].median(),
            'q1': df['close'].quantile(0.25),
            'q3': df['close'].quantile(0.75)
        }

        # Calculate data quality score (0-100)
        quality_score = 100
        quality_score -= (total_outliers / total_candles) * 100  # Penalize outliers
        quality_score -= (len(gaps) / total_candles) * 100        # Penalize gaps
        quality_score = max(0, quality_score)

        # Determine status
        if quality_score >= 90:
            status = 'EXCELLENT'
        elif quality_score >= 70:
            status = 'GOOD'
        elif quality_score >= 50:
            status = 'FAIR'
        else:
            status = 'POOR'

        # Create report
        report = {
            'symbol': symbol,
            'status': status,
            'quality_score': round(quality_score, 2),
            'total_candles': total_candles,
            'date_range': date_range,
            'days_coverage': days_coverage,
            'target_days': self.target_days,
            'needs_more_data': days_coverage < self.target_days,
            'outliers': {
                'total': int(total_outliers),
                'z_score': int(zscore_count),
                'iqr': int(iqr_count),
                'price_jumps': int(jump_count),
                'inconsistencies': int(inconsistent_count),
                'percentage': round((total_outliers / total_candles) * 100, 2)
            },
            'gaps': {
                'count': len(gaps),
                'total_hours_missing': round(gaps.sum().total_seconds() / 3600, 2)
            },
            'price_statistics': {k: round(v, 2) for k, v in price_stats.items()},
            'outlier_indices': df[combined_outliers].index.tolist()
        }

        # Print summary
        print(f"  Status: {status} (Quality Score: {quality_score:.2f}/100)")
        print(f"  Coverage: {days_coverage} days ({total_candles} candles)")
        print(f"  Outliers: {total_outliers} ({report['outliers']['percentage']:.2f}%)")
        print(f"    - Z-score method: {zscore_count}")
        print(f"    - IQR method: {iqr_count}")
        print(f"    - Price jumps: {jump_count}")
        print(f"    - Inconsistencies: {inconsistent_count}")
        print(f"  Data gaps: {len(gaps)} gaps ({report['gaps']['total_hours_missing']:.1f} hours missing)")
        print(f"  Price range: ${price_stats['min']:.2f} - ${price_stats['max']:.2f}")
        print(f"  Needs more data: {'YES' if report['needs_more_data'] else 'NO'}")

        return report

    def clean_data(self, symbol: str, report: Dict) -> int:
        """
        Clean data by removing/interpolating outliers

        Args:
            symbol: Trading pair symbol
            report: Quality analysis report containing outlier information

        Returns:
            int: Number of records cleaned
        """
        if report['outliers']['total'] == 0:
            print(f"  ✓ No outliers to clean for {symbol}")
            return 0

        print(f"\n  Cleaning {report['outliers']['total']} outliers for {symbol}...")

        # Fetch data
        df = self.fetch_symbol_data(symbol)

        # Get outlier indices
        outlier_indices = report['outlier_indices']

        # Strategy: Interpolate outliers using linear interpolation
        # This is safer than deletion as it preserves timestamp continuity
        df_clean = df.copy()

        for col in ['open', 'high', 'low', 'close', 'volume']:
            # Mark outliers as NaN
            df_clean.loc[outlier_indices, col] = np.nan

            # Interpolate using linear method
            df_clean[col] = df_clean[col].interpolate(method='linear', limit_direction='both')

        # Update database with cleaned data
        conn = self.connect_db()
        cursor = conn.cursor()

        cleaned_count = 0
        for idx in outlier_indices:
            row = df_clean.iloc[idx]

            # Convert timestamp to bigint (Unix milliseconds) for WHERE clause
            update_query = """
                UPDATE klines
                SET open = %s, high = %s, low = %s, close = %s, volume = %s
                WHERE symbol = %s AND interval = %s AND timestamp = %s
            """

            try:
                # Convert datetime timestamp to bigint milliseconds
                timestamp_ms = int(row['timestamp'].timestamp() * 1000)

                cursor.execute(update_query, (
                    float(row['open']),
                    float(row['high']),
                    float(row['low']),
                    float(row['close']),
                    float(row['volume']),
                    symbol,
                    self.interval,
                    timestamp_ms  # Pass as bigint
                ))
                cleaned_count += 1
            except Exception as e:
                print(f"    ✗ Error updating record at {row['timestamp']}: {e}")

        conn.commit()
        cursor.close()
        conn.close()

        print(f"  ✓ Cleaned {cleaned_count} records for {symbol}")
        return cleaned_count

    def fetch_historical_data_bybit(self, symbol: str, start_date: datetime, end_date: datetime) -> List[Dict]:
        """
        Fetch historical candle data from Bybit API

        Args:
            symbol: Trading pair symbol
            start_date: Start date for historical data
            end_date: End date for historical data

        Returns:
            List[Dict]: List of candle data dictionaries
        """
        print(f"\n  Fetching historical data from Bybit API...")
        print(f"    Date range: {start_date.date()} to {end_date.date()}")

        all_candles = []
        current_start = start_date

        # Bybit API limits to 200 candles per request
        max_candles_per_request = 200
        interval_minutes = 60

        while current_start < end_date:
            # Calculate end timestamp for this batch
            current_end = min(
                current_start + timedelta(hours=max_candles_per_request * interval_minutes / 60),
                end_date
            )

            # Bybit expects timestamps in milliseconds
            start_ts = int(current_start.timestamp() * 1000)
            end_ts = int(current_end.timestamp() * 1000)

            # Build API request
            endpoint = f"{self.bybit_base_url}/v5/market/kline"
            params = {
                'category': 'spot',
                'symbol': symbol,
                'interval': self.interval,
                'start': start_ts,
                'end': end_ts,
                'limit': max_candles_per_request
            }

            try:
                response = requests.get(endpoint, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()

                if data['retCode'] == 0 and 'result' in data and 'list' in data['result']:
                    candles = data['result']['list']

                    # Parse candles (Bybit returns: [timestamp, open, high, low, close, volume, turnover])
                    for candle in candles:
                        all_candles.append({
                            'timestamp': datetime.fromtimestamp(int(candle[0]) / 1000),
                            'open': float(candle[1]),
                            'high': float(candle[2]),
                            'low': float(candle[3]),
                            'close': float(candle[4]),
                            'volume': float(candle[5])
                        })

                    print(f"    Fetched {len(candles)} candles (up to {current_end.date()})")
                else:
                    print(f"    ✗ API error: {data.get('retMsg', 'Unknown error')}")
                    break

            except Exception as e:
                print(f"    ✗ Request failed: {e}")
                break

            # Move to next batch
            current_start = current_end

        print(f"  ✓ Total fetched: {len(all_candles)} candles")
        return all_candles

    def insert_historical_data(self, symbol: str, candles: List[Dict]) -> int:
        """
        Insert historical data into database (skip duplicates)

        Args:
            symbol: Trading pair symbol
            candles: List of candle data dictionaries

        Returns:
            int: Number of records inserted
        """
        if not candles:
            return 0

        print(f"\n  Inserting historical data into database...")

        conn = self.connect_db()
        cursor = conn.cursor()

        # Convert timestamps to bigint (Unix milliseconds) for database
        insert_query = """
            INSERT INTO klines (symbol, interval, timestamp, open, high, low, close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, interval, timestamp) DO NOTHING
        """

        inserted_count = 0
        for candle in candles:
            try:
                # Convert datetime to bigint milliseconds
                timestamp_ms = int(candle['timestamp'].timestamp() * 1000)

                cursor.execute(insert_query, (
                    symbol,
                    self.interval,
                    timestamp_ms,  # Pass as bigint
                    candle['open'],
                    candle['high'],
                    candle['low'],
                    candle['close'],
                    candle['volume']
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
            except Exception as e:
                print(f"    ✗ Error inserting candle at {candle['timestamp']}: {e}")

        conn.commit()
        cursor.close()
        conn.close()

        print(f"  ✓ Inserted {inserted_count} new candles (skipped {len(candles) - inserted_count} duplicates)")
        return inserted_count

    def extend_historical_data(self, symbol: str, current_days: int) -> Dict:
        """
        Extend historical data to reach target days

        Args:
            symbol: Trading pair symbol
            current_days: Current days of coverage

        Returns:
            Dict: Summary of data extension
        """
        if current_days >= self.target_days:
            print(f"  ✓ {symbol} already has {current_days} days (target: {self.target_days})")
            return {'status': 'SUFFICIENT', 'fetched': 0, 'inserted': 0}

        print(f"\n{'='*60}")
        print(f"Extending historical data for {symbol}")
        print(f"  Current: {current_days} days | Target: {self.target_days} days")
        print(f"{'='*60}")

        # Calculate date range to fetch
        df = self.fetch_symbol_data(symbol)
        earliest_date = df['timestamp'].min()

        # Fetch data from target_days ago to earliest_date
        target_start = datetime.now() - timedelta(days=self.target_days)
        fetch_start = target_start
        fetch_end = earliest_date - timedelta(hours=1)  # Stop 1 hour before existing data

        if fetch_end <= fetch_start:
            print(f"  ✓ No gap to fill")
            return {'status': 'NO_GAP', 'fetched': 0, 'inserted': 0}

        # Fetch from Bybit
        candles = self.fetch_historical_data_bybit(symbol, fetch_start, fetch_end)

        # Insert into database
        inserted = self.insert_historical_data(symbol, candles)

        return {
            'status': 'EXTENDED',
            'fetched': len(candles),
            'inserted': inserted,
            'date_range': f"{fetch_start.date()} to {fetch_end.date()}"
        }

    def generate_final_report(self) -> str:
        """
        Generate comprehensive final report

        Returns:
            str: Markdown-formatted report
        """
        report_lines = [
            "# Data Quality Enhancement Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Executive Summary",
            ""
        ]

        # Summary statistics
        total_symbols = len(self.quality_reports)
        ml_ready = sum(1 for r in self.quality_reports.values()
                       if r.get('status') in ['EXCELLENT', 'GOOD'] and not r.get('needs_more_data', True))

        report_lines.extend([
            f"- **Total Symbols Analyzed**: {total_symbols}",
            f"- **ML-Ready Symbols**: {ml_ready}/{total_symbols}",
            f"- **Target Historical Depth**: {self.target_days} days",
            ""
        ])

        # Per-symbol details
        report_lines.append("## Symbol-by-Symbol Analysis")
        report_lines.append("")

        for symbol, report in self.quality_reports.items():
            if 'status' not in report or report['status'] == 'NO_DATA':
                continue

            report_lines.extend([
                f"### {symbol}",
                f"- **Status**: {report['status']}",
                f"- **Quality Score**: {report['quality_score']}/100",
                f"- **Coverage**: {report['days_coverage']} days ({report['total_candles']} candles)",
                f"- **Outliers Detected**: {report['outliers']['total']} ({report['outliers']['percentage']}%)",
                f"  - Z-score method: {report['outliers']['z_score']}",
                f"  - IQR method: {report['outliers']['iqr']}",
                f"  - Price jumps: {report['outliers']['price_jumps']}",
                f"  - Inconsistencies: {report['outliers']['inconsistencies']}",
                f"- **Data Gaps**: {report['gaps']['count']} gaps ({report['gaps']['total_hours_missing']} hours)",
                f"- **Price Range**: ${report['price_statistics']['min']} - ${report['price_statistics']['max']}",
                f"- **ML-Ready**: {'YES' if not report['needs_more_data'] and report['quality_score'] >= 70 else 'NO'}",
                ""
            ])

        # Recommendations
        report_lines.extend([
            "## Recommendations",
            ""
        ])

        for symbol, report in self.quality_reports.items():
            if 'status' not in report or report['status'] == 'NO_DATA':
                report_lines.append(f"- **{symbol}**: No data available in database")
            elif report['needs_more_data']:
                report_lines.append(f"- **{symbol}**: Extend data to {self.target_days} days (currently {report['days_coverage']} days)")
            elif report['quality_score'] < 70:
                report_lines.append(f"- **{symbol}**: Improve data quality (current score: {report['quality_score']}/100)")
            else:
                report_lines.append(f"- **{symbol}**: Ready for ML training")

        report_lines.append("")

        return "\n".join(report_lines)

    def run_full_enhancement(self):
        """
        Run complete data quality enhancement workflow

        This is the main entry point that orchestrates:
        1. Data quality analysis
        2. Data cleaning
        3. Historical data extension
        4. Final validation
        5. Report generation
        """
        print("\n" + "="*80)
        print("DATA QUALITY ENHANCEMENT - START")
        print("="*80)

        for symbol in self.symbols:
            # Step 1: Analyze current data quality
            report = self.analyze_data_quality(symbol)
            self.quality_reports[symbol] = report

            if report.get('status') == 'NO_DATA':
                continue

            # Step 2: Clean outliers
            if report['outliers']['total'] > 0:
                cleaned = self.clean_data(symbol, report)
                print(f"  ✓ Cleaned {cleaned} outliers")

            # Step 3: Extend historical data if needed
            if report['needs_more_data']:
                extension_result = self.extend_historical_data(symbol, report['days_coverage'])
                print(f"  ✓ Extended data: {extension_result.get('inserted', 0)} new candles")

            # Step 4: Re-analyze after cleaning
            print(f"\n  Re-analyzing {symbol} after enhancements...")
            updated_report = self.analyze_data_quality(symbol)
            self.quality_reports[symbol] = updated_report

        # Generate final report
        print("\n" + "="*80)
        print("Generating final report...")
        print("="*80)

        final_report = self.generate_final_report()

        # Save report to file
        report_path = '/mnt/d/Bimo_max/crypto-trading-bot/reports/data_quality_report.md'
        with open(report_path, 'w') as f:
            f.write(final_report)

        print(f"\n✓ Report saved to: {report_path}")
        print(final_report)

        print("\n" + "="*80)
        print("DATA QUALITY ENHANCEMENT - COMPLETE")
        print("="*80)


def main():
    """
    Main entry point for data quality enhancement
    """
    # Initialize enhancer
    enhancer = DataQualityEnhancer(
        db_host='localhost',
        db_port=5433,
        db_name='market_data',
        db_user='cryptobot',
        db_password='timescale_dev_password'
    )

    # Run full enhancement workflow
    enhancer.run_full_enhancement()


if __name__ == '__main__':
    main()
