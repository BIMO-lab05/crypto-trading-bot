#!/usr/bin/env python3
"""
ML Training Data Validation Script
===================================
Validates the quality of collected ML training data
"""
import os
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def validate_csv(csv_file: Path) -> dict:
    """
    Validate one CSV file

    Returns dict with validation results
    """
    try:
        # Read CSV
        df = pd.read_csv(csv_file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Sort by timestamp
        df = df.sort_values('timestamp').reset_index(drop=True)

        # Check columns
        required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            return {
                'file': csv_file.name,
                'status': 'FAILED',
                'error': f'Missing columns: {missing_cols}'
            }

        # Check data quality
        total_rows = len(df)

        # Check for NaN values
        nan_count = df[required_cols].isna().sum().sum()

        # Check for zero volume
        zero_volume = (df['volume'] == 0).sum()

        # Check price consistency (high >= low, high >= open/close, low <= open/close)
        invalid_prices = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        ).sum()

        # Check for time gaps
        df['time_diff'] = df['timestamp'].diff()

        # Expected time diff based on filename
        if '_1H_' in csv_file.name:
            expected_diff = timedelta(hours=1)
            tolerance = timedelta(hours=2)
        elif '_4H_' in csv_file.name:
            expected_diff = timedelta(hours=4)
            tolerance = timedelta(hours=8)
        elif '_1D_' in csv_file.name:
            expected_diff = timedelta(days=1)
            tolerance = timedelta(days=2)
        else:
            expected_diff = timedelta(hours=1)
            tolerance = timedelta(hours=2)

        gaps = df[df['time_diff'] > tolerance]
        gap_count = len(gaps)

        # Calculate completeness
        start_date = df['timestamp'].min()
        end_date = df['timestamp'].max()
        total_expected_periods = int((end_date - start_date) / expected_diff)
        completeness_pct = (total_rows / total_expected_periods * 100) if total_expected_periods > 0 else 0

        # Overall status
        if nan_count > 0 or invalid_prices > 0:
            status = 'FAILED'
        elif gap_count > 10 or zero_volume > (total_rows * 0.1):
            status = 'WARNING'
        elif completeness_pct < 95:
            status = 'WARNING'
        else:
            status = 'OK'

        return {
            'file': csv_file.name,
            'status': status,
            'rows': total_rows,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'completeness': round(completeness_pct, 1),
            'nan_count': int(nan_count),
            'zero_volume': int(zero_volume),
            'invalid_prices': int(invalid_prices),
            'gaps': gap_count,
            'file_size_kb': round(csv_file.stat().st_size / 1024, 1)
        }

    except Exception as e:
        return {
            'file': csv_file.name,
            'status': 'ERROR',
            'error': str(e)
        }


def main():
    """Validate all ML training data"""
    print("\n" + "="*80)
    print("ML TRAINING DATA VALIDATION")
    print("="*80)

    # Data directory
    data_dir = Path(__file__).parent.parent / 'data' / 'ml_training'

    if not data_dir.exists():
        print(f"❌ Data directory not found: {data_dir}")
        return

    # Find all CSV files
    csv_files = sorted(data_dir.glob('*_20251208.csv'))

    if not csv_files:
        print(f"❌ No CSV files found in {data_dir}")
        return

    print(f"\nFound {len(csv_files)} CSV files to validate")
    print(f"Directory: {data_dir}\n")

    # Validate each file
    results = []
    for csv_file in csv_files:
        result = validate_csv(csv_file)
        results.append(result)

        # Print result
        status_icon = {
            'OK': '✅',
            'WARNING': '⚠️',
            'FAILED': '❌',
            'ERROR': '🔥'
        }.get(result['status'], '?')

        print(f"{status_icon} {result['file'][:40]:40} - {result['status']}")

        if result['status'] == 'OK':
            print(f"   Rows: {result['rows']:,} | Completeness: {result['completeness']}% | Gaps: {result['gaps']}")
        elif 'error' in result:
            print(f"   Error: {result['error']}")

    # Summary
    print(f"\n{'='*80}")
    print("VALIDATION SUMMARY")
    print(f"{'='*80}")

    total_files = len(results)
    ok_count = len([r for r in results if r['status'] == 'OK'])
    warning_count = len([r for r in results if r['status'] == 'WARNING'])
    failed_count = len([r for r in results if r['status'] in ['FAILED', 'ERROR']])

    print(f"\nTotal files: {total_files}")
    print(f"✅ OK: {ok_count} ({ok_count/total_files*100:.1f}%)")
    print(f"⚠️  Warnings: {warning_count} ({warning_count/total_files*100:.1f}%)")
    print(f"❌ Failed: {failed_count} ({failed_count/total_files*100:.1f}%)")

    if ok_count > 0:
        ok_results = [r for r in results if r['status'] == 'OK']
        total_rows = sum(r['rows'] for r in ok_results)
        avg_completeness = sum(r['completeness'] for r in ok_results) / len(ok_results)
        total_size = sum(r['file_size_kb'] for r in ok_results)

        print(f"\nData Quality (OK files):")
        print(f"  Total candles: {total_rows:,}")
        print(f"  Avg completeness: {avg_completeness:.1f}%")
        print(f"  Total size: {total_size/1024:.1f} MB")

    # Recommendations
    print(f"\n{'='*80}")
    print("RECOMMENDATIONS")
    print(f"{'='*80}")

    if failed_count > 0:
        print("\n❌ CRITICAL: Some files failed validation")
        print("   Action: Review failed files and re-collect if needed")
    elif warning_count > 5:
        print("\n⚠️  WARNING: Multiple files have quality issues")
        print("   Action: Review files with warnings, may need re-collection")
    elif ok_count >= 28:  # 28 out of 30 is good enough
        print("\n✅ EXCELLENT: Data quality is good!")
        print("   Action: Ready to proceed with ML training")
        print(f"\n   Next steps:")
        print("   1. Fix ML training pipeline import errors")
        print("   2. Update data paths in training scripts")
        print("   3. Begin ML model training")
    else:
        print("\n⚠️  Insufficient good quality data")
        print(f"   Action: Need at least 28 OK files (have {ok_count})")

    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
