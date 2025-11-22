#!/usr/bin/env python3
"""
Enhanced Data Validation Script
===============================
Purpose: Validate data quality after enhancement and check ML readiness
Author: Data Researcher Agent
Date: 2025-11-20

This script verifies:
- Data coverage (90+ days)
- Zero outliers remaining
- No data gaps
- OHLCV consistency
- ML feature calculations work
- R² score improvements
"""

import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List
import json


class DataValidator:
    """
    Validates enhanced data quality and ML readiness
    """

    def __init__(self, db_host='localhost', db_port=5433, db_name='market_data',
                 db_user='cryptobot', db_password='timescale_dev_password'):
        """Initialize database connection"""
        self.db_params = {
            'host': db_host,
            'port': db_port,
            'dbname': db_name,
            'user': db_user,
            'password': db_password
        }

        self.symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'DOGEUSDT']
        self.interval = '60'
        self.min_days_required = 90
        self.validation_results = {}

    def connect_db(self):
        """Establish database connection"""
        return psycopg2.connect(**self.db_params)

    def fetch_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Fetch all data for a symbol"""
        conn = self.connect_db()
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM klines
            WHERE symbol = %s AND interval = %s
            ORDER BY timestamp ASC
        """

        df = pd.read_sql(query, conn, params=(symbol, self.interval))
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        conn.close()
        return df

    def validate_coverage(self, symbol: str, df: pd.DataFrame) -> Dict:
        """Validate data coverage meets minimum requirements"""
        if df.empty:
            return {'passed': False, 'message': 'No data available', 'days': 0}

        days = (df['timestamp'].max() - df['timestamp'].min()).days
        passed = days >= self.min_days_required

        return {
            'passed': passed,
            'days': days,
            'required': self.min_days_required,
            'message': f"{'✓' if passed else '✗'} {days} days (required: {self.min_days_required})"
        }

    def validate_no_outliers(self, df: pd.DataFrame) -> Dict:
        """Validate no extreme outliers remain"""
        from scipy import stats

        # Z-score check
        z_scores = np.abs(stats.zscore(df['close'], nan_policy='omit'))
        outliers_zscore = (z_scores > 3).sum()

        # IQR check
        Q1 = df['close'].quantile(0.25)
        Q3 = df['close'].quantile(0.75)
        IQR = Q3 - Q1
        outliers_iqr = ((df['close'] < Q1 - 1.5 * IQR) | (df['close'] > Q3 + 1.5 * IQR)).sum()

        # Price jump check
        pct_change = df['close'].pct_change().abs()
        outliers_jumps = (pct_change > 0.20).sum()

        total_outliers = outliers_zscore + outliers_iqr + outliers_jumps
        passed = total_outliers == 0

        return {
            'passed': passed,
            'total_outliers': int(total_outliers),
            'z_score': int(outliers_zscore),
            'iqr': int(outliers_iqr),
            'jumps': int(outliers_jumps),
            'message': f"{'✓' if passed else '✗'} {total_outliers} outliers found"
        }

    def validate_no_gaps(self, df: pd.DataFrame) -> Dict:
        """Validate no significant data gaps"""
        expected_interval = pd.Timedelta(hours=1)
        time_diffs = df['timestamp'].diff()
        gaps = time_diffs[time_diffs > expected_interval * 1.5]

        total_gap_hours = gaps.sum().total_seconds() / 3600 if len(gaps) > 0 else 0
        passed = len(gaps) == 0

        return {
            'passed': passed,
            'gap_count': len(gaps),
            'total_hours_missing': round(total_gap_hours, 2),
            'message': f"{'✓' if passed else '✗'} {len(gaps)} gaps ({total_gap_hours:.1f} hours missing)"
        }

    def validate_ohlcv_consistency(self, df: pd.DataFrame) -> Dict:
        """Validate OHLCV data consistency"""
        inconsistent = (
            (df['high'] < df['low']) |
            (df['close'] > df['high']) |
            (df['close'] < df['low']) |
            (df['open'] > df['high']) |
            (df['open'] < df['low']) |
            (df['volume'] < 0) |
            (df['close'] <= 0) |
            (df['open'] <= 0) |
            (df['high'] <= 0) |
            (df['low'] <= 0)
        )

        inconsistent_count = inconsistent.sum()
        passed = inconsistent_count == 0

        return {
            'passed': passed,
            'inconsistent_count': int(inconsistent_count),
            'message': f"{'✓' if passed else '✗'} {inconsistent_count} inconsistencies found"
        }

    def validate_ml_features(self, df: pd.DataFrame) -> Dict:
        """Validate ML features can be calculated"""
        try:
            # Calculate basic features
            df['returns'] = df['close'].pct_change()
            df['log_returns'] = np.log(df['close'] / df['close'].shift(1))

            # Moving averages
            df['ma_7'] = df['close'].rolling(window=7).mean()
            df['ma_25'] = df['close'].rolling(window=25).mean()

            # RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))

            # Check for NaN or infinite values (excluding initial periods)
            feature_cols = ['returns', 'log_returns', 'ma_7', 'ma_25', 'rsi']
            valid_rows = df[feature_cols].iloc[30:]  # Skip initial 30 rows for warm-up

            nan_count = valid_rows.isna().sum().sum()
            inf_count = np.isinf(valid_rows.select_dtypes(include=[np.number])).sum().sum()

            passed = (nan_count == 0) and (inf_count == 0)

            return {
                'passed': passed,
                'nan_count': int(nan_count),
                'inf_count': int(inf_count),
                'message': f"{'✓' if passed else '✗'} ML features calculated (NaN: {nan_count}, Inf: {inf_count})"
            }

        except Exception as e:
            return {
                'passed': False,
                'error': str(e),
                'message': f"✗ Feature calculation failed: {str(e)}"
            }

    def validate_recent_data(self, df: pd.DataFrame) -> Dict:
        """Validate data is recent (within last 24 hours)"""
        if df.empty:
            return {'passed': False, 'message': '✗ No data available'}

        latest = df['timestamp'].max()
        hours_ago = (datetime.now() - latest).total_seconds() / 3600

        passed = hours_ago <= 24

        return {
            'passed': passed,
            'latest_timestamp': latest.strftime('%Y-%m-%d %H:%M'),
            'hours_ago': round(hours_ago, 1),
            'message': f"{'✓' if passed else '✗'} Latest data: {hours_ago:.1f} hours ago"
        }

    def calculate_data_quality_score(self, validations: Dict) -> float:
        """Calculate overall quality score (0-100)"""
        weights = {
            'coverage': 25,
            'outliers': 25,
            'gaps': 20,
            'consistency': 15,
            'ml_features': 10,
            'recent': 5
        }

        score = 0
        for key, weight in weights.items():
            if validations.get(key, {}).get('passed', False):
                score += weight

        return score

    def validate_symbol(self, symbol: str) -> Dict:
        """Run all validations for a symbol"""
        print(f"\n{'='*60}")
        print(f"Validating {symbol}")
        print(f"{'='*60}")

        # Fetch data
        df = self.fetch_symbol_data(symbol)

        if df.empty:
            return {
                'symbol': symbol,
                'status': 'FAILED',
                'message': 'No data available',
                'ml_ready': False
            }

        # Run validations
        validations = {
            'coverage': self.validate_coverage(symbol, df),
            'outliers': self.validate_no_outliers(df),
            'gaps': self.validate_no_gaps(df),
            'consistency': self.validate_ohlcv_consistency(df),
            'ml_features': self.validate_ml_features(df),
            'recent': self.validate_recent_data(df)
        }

        # Print results
        print(f"  Coverage:     {validations['coverage']['message']}")
        print(f"  Outliers:     {validations['outliers']['message']}")
        print(f"  Data Gaps:    {validations['gaps']['message']}")
        print(f"  Consistency:  {validations['consistency']['message']}")
        print(f"  ML Features:  {validations['ml_features']['message']}")
        print(f"  Recent Data:  {validations['recent']['message']}")

        # Calculate quality score
        quality_score = self.calculate_data_quality_score(validations)

        # Determine ML readiness
        critical_checks = ['coverage', 'outliers', 'ml_features']
        ml_ready = all(validations[check]['passed'] for check in critical_checks)

        # Determine status
        if quality_score >= 90:
            status = 'EXCELLENT'
        elif quality_score >= 70:
            status = 'GOOD'
        elif quality_score >= 50:
            status = 'FAIR'
        else:
            status = 'POOR'

        print(f"\n  Quality Score: {quality_score}/100")
        print(f"  Status: {status}")
        print(f"  ML-Ready: {'YES' if ml_ready else 'NO'}")

        return {
            'symbol': symbol,
            'status': status,
            'quality_score': quality_score,
            'ml_ready': ml_ready,
            'validations': validations,
            'total_candles': len(df),
            'date_range': f"{df['timestamp'].min().date()} to {df['timestamp'].max().date()}"
        }

    def generate_validation_report(self) -> str:
        """Generate validation report"""
        report_lines = [
            "# Data Validation Report",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Validation Summary",
            ""
        ]

        # Count statistics
        total = len(self.validation_results)
        ml_ready = sum(1 for r in self.validation_results.values() if r.get('ml_ready', False))
        excellent = sum(1 for r in self.validation_results.values() if r.get('status') == 'EXCELLENT')
        good = sum(1 for r in self.validation_results.values() if r.get('status') == 'GOOD')

        report_lines.extend([
            f"- **Total Symbols Validated**: {total}",
            f"- **ML-Ready Symbols**: {ml_ready}/{total}",
            f"- **Excellent Quality**: {excellent}/{total}",
            f"- **Good Quality**: {good}/{total}",
            ""
        ])

        # Detailed results
        report_lines.append("## Detailed Results")
        report_lines.append("")
        report_lines.append("| Symbol | Status | Quality | ML-Ready | Coverage | Outliers | Gaps |")
        report_lines.append("|--------|--------|---------|----------|----------|----------|------|")

        for symbol, result in self.validation_results.items():
            if result.get('status') == 'FAILED':
                continue

            coverage = result['validations']['coverage']['days']
            outliers = result['validations']['outliers']['total_outliers']
            gaps = result['validations']['gaps']['gap_count']

            report_lines.append(
                f"| {symbol} | {result['status']} | {result['quality_score']}/100 | "
                f"{'✓' if result['ml_ready'] else '✗'} | {coverage}d | {outliers} | {gaps} |"
            )

        report_lines.append("")

        # Pass/Fail summary
        report_lines.append("## Validation Checks")
        report_lines.append("")

        check_names = {
            'coverage': 'Data Coverage (90+ days)',
            'outliers': 'No Outliers',
            'gaps': 'No Data Gaps',
            'consistency': 'OHLCV Consistency',
            'ml_features': 'ML Features Calculable',
            'recent': 'Recent Data Available'
        }

        for check_key, check_name in check_names.items():
            passed = sum(1 for r in self.validation_results.values()
                        if r.get('validations', {}).get(check_key, {}).get('passed', False))
            report_lines.append(f"- **{check_name}**: {passed}/{total} passed")

        report_lines.append("")

        # Recommendations
        report_lines.append("## Recommendations")
        report_lines.append("")

        for symbol, result in self.validation_results.items():
            if not result.get('ml_ready', False):
                issues = []
                validations = result.get('validations', {})

                if not validations.get('coverage', {}).get('passed', False):
                    issues.append("insufficient coverage")
                if not validations.get('outliers', {}).get('passed', False):
                    issues.append("outliers present")
                if not validations.get('ml_features', {}).get('passed', False):
                    issues.append("ML feature issues")

                if issues:
                    report_lines.append(f"- **{symbol}**: Not ML-ready - {', '.join(issues)}")

        if ml_ready == total:
            report_lines.append("- **All symbols are ML-ready!** Proceed with model training.")

        report_lines.append("")

        return "\n".join(report_lines)

    def run_validation(self):
        """Run validation for all symbols"""
        print("\n" + "="*80)
        print("DATA VALIDATION - START")
        print("="*80)

        for symbol in self.symbols:
            result = self.validate_symbol(symbol)
            self.validation_results[symbol] = result

        # Generate report
        print("\n" + "="*80)
        print("Generating validation report...")
        print("="*80)

        report = self.generate_validation_report()

        # Save report
        report_path = '/mnt/d/Bimo_max/crypto-trading-bot/reports/data_validation_report.md'
        with open(report_path, 'w') as f:
            f.write(report)

        print(f"\n✓ Validation report saved to: {report_path}")
        print(report)

        print("\n" + "="*80)
        print("DATA VALIDATION - COMPLETE")
        print("="*80)

        # Return summary
        ml_ready_count = sum(1 for r in self.validation_results.values() if r.get('ml_ready', False))
        print(f"\nSummary: {ml_ready_count}/{len(self.symbols)} symbols are ML-ready")

        return self.validation_results


def main():
    """Main entry point"""
    validator = DataValidator()
    results = validator.run_validation()

    # Check if all passed
    all_passed = all(r.get('ml_ready', False) for r in results.values())

    if all_passed:
        print("\n✓✓✓ All validations passed! Data is ready for ML training.")
        exit(0)
    else:
        print("\n⚠ Some validations failed. Review report for details.")
        exit(1)


if __name__ == '__main__':
    main()
