#!/usr/bin/env python3
"""
Unit Tests for Weekly Performance Reporter

Tests all functionality of the performance reporting system including:
- Database connection and data fetching
- Metric calculations
- Report generation
- Chart generation
- Email delivery

Author: Backend Developer Agent
Date: 2025-11-19
Version: 1.0.0
"""

import unittest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import os
import json
import tempfile
import shutil

# Import the module to test
import sys
# tests/unit/X.py → parent.parent.parent is repo root → +/scripts
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent.parent.parent / "scripts"))
from weekly_performance_report import PerformanceReporter, load_config


class TestPerformanceReporter(unittest.TestCase):
    """Test suite for PerformanceReporter class"""

    def setUp(self):
        """Set up test fixtures before each test method"""
        self.start_date = datetime(2025, 11, 1)
        self.end_date = datetime(2025, 11, 7)

        self.db_config = {
            'host': 'localhost',
            'port': 5432,
            'user': 'test_user',
            'password': 'test_password',
            'database': 'test_db'
        }

        self.reporter = PerformanceReporter(
            db_config=self.db_config,
            start_date=self.start_date,
            end_date=self.end_date
        )

        # Create temporary directory for test outputs
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up after each test method"""
        # Remove temporary directory
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

        # Close any open connections
        if self.reporter.connection:
            self.reporter.close_database()

    def test_initialization(self):
        """Test PerformanceReporter initialization"""
        self.assertEqual(self.reporter.start_date, self.start_date)
        self.assertEqual(self.reporter.end_date, self.end_date)
        self.assertEqual(self.reporter.db_config, self.db_config)
        self.assertIsNone(self.reporter.connection)
        self.assertIsNone(self.reporter.trades_df)
        self.assertIsNone(self.reporter.positions_df)
        self.assertIsNone(self.reporter.snapshots_df)

    @patch('weekly_performance_report.psycopg2.connect')
    def test_connect_database_success(self, mock_connect):
        """Test successful database connection"""
        mock_connection = Mock()
        mock_connect.return_value = mock_connection

        self.reporter.connect_database()

        # Verify connection was created
        mock_connect.assert_called_once_with(
            host='localhost',
            port=5432,
            user='test_user',
            password='test_password',
            database='test_db'
        )
        self.assertEqual(self.reporter.connection, mock_connection)

    @patch('weekly_performance_report.psycopg2.connect')
    def test_connect_database_failure(self, mock_connect):
        """Test database connection failure handling"""
        mock_connect.side_effect = Exception("Connection failed")

        with self.assertRaises(Exception) as context:
            self.reporter.connect_database()

        self.assertIn("Connection failed", str(context.exception))

    def test_close_database(self):
        """Test database connection closing"""
        mock_connection = Mock()
        self.reporter.connection = mock_connection

        self.reporter.close_database()

        mock_connection.close.assert_called_once()

    @patch('weekly_performance_report.pd.read_sql_query')
    def test_fetch_trading_data(self, mock_read_sql):
        """Test fetching trades data from database"""
        # Create mock trades data
        mock_trades = pd.DataFrame({
            'trade_id': ['t1', 't2', 't3'],
            'symbol': ['BTCUSDT', 'ETHUSDT', 'BTCUSDT'],
            'action': ['BUY', 'SELL', 'BUY'],
            'quantity': [0.1, 1.0, 0.2],
            'price': [50000, 3000, 51000],
            'total_cost': [5000, 3000, 10200],
            'fee': [5, 3, 10.2],
            'executed_at': [datetime.now()] * 3,
            'realized_pnl': [None, 100, None]
        })

        mock_read_sql.return_value = mock_trades
        self.reporter.connection = Mock()

        result = self.reporter.fetch_trading_data()

        # Verify data was fetched
        self.assertEqual(len(result), 3)
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue('symbol' in result.columns)
        self.assertTrue('price' in result.columns)

    @patch('weekly_performance_report.pd.read_sql_query')
    def test_fetch_positions_data(self, mock_read_sql):
        """Test fetching positions data from database"""
        mock_positions = pd.DataFrame({
            'position_id': ['p1', 'p2'],
            'symbol': ['BTCUSDT', 'ETHUSDT'],
            'side': ['LONG', 'LONG'],
            'quantity': [0.1, 1.0],
            'entry_price': [50000, 3000],
            'exit_price': [51000, 3100],
            'realized_pnl': [100, 100],
            'status': ['CLOSED', 'CLOSED'],
            'opened_at': [datetime.now()] * 2,
            'closed_at': [datetime.now()] * 2
        })

        mock_read_sql.return_value = mock_positions
        self.reporter.connection = Mock()

        result = self.reporter.fetch_positions_data()

        self.assertEqual(len(result), 2)
        self.assertIsInstance(result, pd.DataFrame)

    @patch('weekly_performance_report.pd.read_sql_query')
    def test_fetch_portfolio_snapshots(self, mock_read_sql):
        """Test fetching portfolio snapshots"""
        mock_snapshots = pd.DataFrame({
            'snapshot_id': ['s1', 's2', 's3'],
            'total_value': [10000, 10100, 10200],
            'total_pnl': [0, 100, 200],
            'daily_return_pct': [0, 1.0, 0.99],
            'snapshot_time': pd.date_range(start='2025-11-01', periods=3, freq='D')
        })

        mock_read_sql.return_value = mock_snapshots
        self.reporter.connection = Mock()

        result = self.reporter.fetch_portfolio_snapshots()

        self.assertEqual(len(result), 3)
        self.assertIsInstance(result, pd.DataFrame)

    def test_calculate_metrics_no_data(self):
        """Test metric calculation with no trading data"""
        # Empty dataframes
        self.reporter.trades_df = pd.DataFrame()
        self.reporter.positions_df = pd.DataFrame(columns=['status', 'realized_pnl'])
        self.reporter.snapshots_df = pd.DataFrame()

        metrics = self.reporter.calculate_metrics()

        # Verify default metrics
        self.assertEqual(metrics['total_trades'], 0)
        self.assertEqual(metrics['win_rate'], 0)
        self.assertEqual(metrics['total_pnl'], 0)

    def test_calculate_metrics_with_data(self):
        """Test metric calculation with actual trading data"""
        # Create mock data
        self.reporter.trades_df = pd.DataFrame({
            'fee': [5, 3, 10],
            'executed_at': pd.date_range(start='2025-11-01', periods=3, freq='D')
        })

        self.reporter.positions_df = pd.DataFrame({
            'position_id': ['p1', 'p2', 'p3', 'p4'],
            'status': ['CLOSED', 'CLOSED', 'CLOSED', 'OPEN'],
            'realized_pnl': [100, -50, 150, None],
            'symbol': ['BTCUSDT', 'ETHUSDT', 'BTCUSDT', 'BTCUSDT'],
            'strategy': ['strategy1', 'strategy1', 'strategy2', 'strategy1'],
            'opened_at': pd.date_range(start='2025-11-01', periods=4, freq='D'),
            'closed_at': [
                datetime(2025, 11, 2),
                datetime(2025, 11, 2),
                datetime(2025, 11, 3),
                None
            ]
        })

        self.reporter.snapshots_df = pd.DataFrame({
            'total_value': [10000, 10100, 10050, 10200],
            'total_pnl': [0, 100, 50, 200],
            'total_return_pct': [0, 1.0, 0.5, 2.0],
            'daily_return_pct': [0, 1.0, -0.495, 1.493],
            'snapshot_time': pd.date_range(start='2025-11-01', periods=4, freq='D')
        })

        metrics = self.reporter.calculate_metrics()

        # Verify metrics
        self.assertEqual(metrics['total_trades'], 3)
        self.assertEqual(metrics['total_positions'], 3)  # Only closed positions
        self.assertEqual(metrics['winning_trades'], 2)
        self.assertEqual(metrics['losing_trades'], 1)
        self.assertAlmostEqual(metrics['win_rate'], 66.67, places=2)
        self.assertEqual(metrics['total_pnl'], 200)  # 100 - 50 + 150
        self.assertEqual(metrics['total_fees'], 18)  # 5 + 3 + 10
        self.assertGreater(metrics['profit_factor'], 0)
        self.assertIsNotNone(metrics['sharpe_ratio'])
        self.assertIsNotNone(metrics['max_drawdown'])

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation"""
        # Create snapshots with known returns
        self.reporter.trades_df = pd.DataFrame({'fee': [0]})
        self.reporter.positions_df = pd.DataFrame(columns=['status', 'realized_pnl'])

        # Daily returns: 1%, 1%, 1% (consistent positive returns)
        self.reporter.snapshots_df = pd.DataFrame({
            'total_value': [10000, 10100, 10201, 10303.01],
            'daily_return_pct': [0, 1.0, 1.0, 1.0],
            'total_return_pct': [0, 1.0, 2.01, 3.03],
            'snapshot_time': pd.date_range(start='2025-11-01', periods=4, freq='D')
        })

        metrics = self.reporter.calculate_metrics()

        # Sharpe should be positive for consistent positive returns
        self.assertGreater(metrics['sharpe_ratio'], 0)

    def test_calculate_max_drawdown(self):
        """Test maximum drawdown calculation"""
        self.reporter.trades_df = pd.DataFrame({'fee': [0]})
        self.reporter.positions_df = pd.DataFrame(columns=['status', 'realized_pnl'])

        # Simulate drawdown: 10000 -> 11000 -> 9000 -> 12000
        self.reporter.snapshots_df = pd.DataFrame({
            'total_value': [10000, 11000, 9000, 12000],
            'total_return_pct': [0, 10, -10, 20],
            'daily_return_pct': [0, 10, -18.18, 33.33],
            'snapshot_time': pd.date_range(start='2025-11-01', periods=4, freq='D')
        })

        metrics = self.reporter.calculate_metrics()

        # Max drawdown should be negative (from 11000 to 9000 = -18.18%)
        self.assertLess(metrics['max_drawdown'], 0)

    @patch('weekly_performance_report.plt.savefig')
    @patch('weekly_performance_report.plt.close')
    def test_generate_charts(self, mock_close, mock_savefig):
        """Test chart generation"""
        # Set up data
        self.reporter.trades_df = pd.DataFrame({
            'executed_at': pd.date_range(start='2025-11-01', periods=5, freq='D'),
            'total_cost': [1000, 2000, 1500, 3000, 2500],
            'fee': [1, 2, 1.5, 3, 2.5]
        })

        self.reporter.positions_df = pd.DataFrame({
            'status': ['CLOSED'] * 5,
            'symbol': ['BTCUSDT', 'ETHUSDT', 'BTCUSDT', 'BNBUSDT', 'ETHUSDT'],
            'realized_pnl': [100, -50, 75, 25, -25],
            'opened_at': pd.date_range(start='2025-11-01', periods=5, freq='D'),
            'closed_at': pd.date_range(start='2025-11-02', periods=5, freq='D')
        })

        self.reporter.snapshots_df = pd.DataFrame({
            'snapshot_time': pd.date_range(start='2025-11-01', periods=5, freq='D'),
            'total_pnl': [0, 50, 0, 75, 100],
            'realized_pnl': [0, 50, 0, 75, 100],
            'total_value': [10000, 10050, 10000, 10075, 10100],
            'total_return_pct': [0, 0.5, 0, 0.75, 1.0]
        })

        chart_paths = self.reporter.generate_charts(self.test_dir)

        # Verify charts were created
        self.assertIsInstance(chart_paths, list)
        self.assertGreater(len(chart_paths), 0)

        # Verify savefig was called (charts were generated)
        self.assertGreater(mock_savefig.call_count, 0)

    def test_create_markdown_report(self):
        """Test markdown report generation"""
        metrics = {
            'total_trades': 42,
            'total_positions': 21,
            'win_rate': 57.14,
            'winning_trades': 12,
            'losing_trades': 9,
            'total_pnl': 342.50,
            'roi_percentage': 3.43,
            'sharpe_ratio': 1.82,
            'max_drawdown': -4.23,
            'avg_win': 50.0,
            'avg_loss': -25.0,
            'profit_factor': 2.15,
            'best_trade': 150.0,
            'worst_trade': -75.0,
            'avg_trade_duration_hours': 18.5,
            'total_fees': 21.0,
            'initial_portfolio_value': 10000,
            'final_portfolio_value': 10343,
            'symbol_performance': {
                'BTCUSDT': {'sum': 200, 'count': 10, 'mean': 20},
                'ETHUSDT': {'sum': 142.50, 'count': 11, 'mean': 12.95}
            },
            'strategy_performance': {
                'strategy1': {'sum': 250, 'count': 15, 'mean': 16.67}
            }
        }

        chart_paths = [
            os.path.join(self.test_dir, 'chart1.png'),
            os.path.join(self.test_dir, 'chart2.png')
        ]

        markdown = self.reporter.create_markdown_report(metrics, chart_paths)

        # Verify markdown content
        self.assertIn('# Weekly Performance Report', markdown)
        self.assertIn('Total Trades', markdown)
        self.assertIn('57.14%', markdown)  # Win rate
        self.assertIn('$342.50', markdown)  # Total P&L
        self.assertIn('BTCUSDT', markdown)  # Symbol
        self.assertIn('strategy1', markdown)  # Strategy

    def test_create_html_report(self):
        """Test HTML report generation"""
        metrics = {
            'total_trades': 42,
            'total_positions': 21,
            'win_rate': 57.14,
            'winning_trades': 12,
            'losing_trades': 9,
            'total_pnl': 342.50,
            'roi_percentage': 3.43,
            'sharpe_ratio': 1.82,
            'max_drawdown': -4.23,
            'avg_win': 50.0,
            'avg_loss': -25.0,
            'profit_factor': 2.15,
            'best_trade': 150.0,
            'worst_trade': -75.0,
            'avg_trade_duration_hours': 18.5,
            'total_fees': 21.0,
            'symbol_performance': {},
            'strategy_performance': {}
        }

        chart_paths = []

        html = self.reporter.create_html_report(metrics, chart_paths)

        # Verify HTML content
        self.assertIn('<!DOCTYPE html>', html)
        self.assertIn('<html', html)
        self.assertIn('Weekly Performance Report', html)
        self.assertIn('57.1%', html)  # Win rate (HTML formats differently)

    def test_create_csv_export(self):
        """Test CSV export generation"""
        self.reporter.positions_df = pd.DataFrame({
            'status': ['CLOSED', 'CLOSED'],
            'symbol': ['BTCUSDT', 'ETHUSDT'],
            'side': ['LONG', 'SHORT'],
            'quantity': [0.1, 1.0],
            'entry_price': [50000, 3000],
            'exit_price': [51000, 2900],
            'realized_pnl': [100, 100],
            'strategy': ['strategy1', 'strategy2'],
            'opened_at': [datetime(2025, 11, 1), datetime(2025, 11, 2)],
            'closed_at': [datetime(2025, 11, 2), datetime(2025, 11, 3)]
        })

        metrics = {}

        csv_path = self.reporter.create_csv_export(metrics, self.test_dir)

        # Verify CSV was created
        self.assertTrue(os.path.exists(csv_path))

        # Read and verify CSV content
        df = pd.read_csv(csv_path)
        self.assertEqual(len(df), 2)
        self.assertIn('symbol', df.columns)
        self.assertIn('realized_pnl', df.columns)

    @patch('weekly_performance_report.PerformanceReporter.calculate_metrics')
    @patch('weekly_performance_report.PerformanceReporter.generate_charts')
    def test_save_reports(self, mock_generate_charts, mock_calculate_metrics):
        """Test saving all report formats"""
        mock_calculate_metrics.return_value = {
            'total_trades': 10,
            'total_positions': 5,
            'win_rate': 60.0,
            'winning_trades': 3,
            'losing_trades': 2,
            'total_pnl': 100,
            'roi_percentage': 1.0,
            'sharpe_ratio': 1.5,
            'max_drawdown': -2.0,
            'avg_win': 50,
            'avg_loss': -25,
            'profit_factor': 2.0,
            'best_trade': 75,
            'worst_trade': -50,
            'avg_trade_duration_hours': 12,
            'total_fees': 5,
            'symbol_performance': {},
            'strategy_performance': {}
        }

        mock_generate_charts.return_value = []

        # Set up minimal data
        self.reporter.positions_df = pd.DataFrame(columns=[
            'status', 'symbol', 'side', 'quantity', 'entry_price',
            'exit_price', 'realized_pnl', 'strategy', 'opened_at', 'closed_at'
        ])

        report_files = self.reporter.save_reports(
            output_dir=self.test_dir,
            formats=['json', 'markdown', 'html', 'csv']
        )

        # Verify all formats were generated
        self.assertIn('json', report_files)
        self.assertIn('markdown', report_files)
        self.assertIn('html', report_files)
        self.assertIn('csv', report_files)

        # Verify files exist
        for format_type, file_path in report_files.items():
            self.assertTrue(os.path.exists(file_path), f"{format_type} file not found")

    @patch('weekly_performance_report.smtplib.SMTP')
    def test_send_email_success(self, mock_smtp_class):
        """Test successful email sending"""
        mock_smtp = Mock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        smtp_config = {
            'server': 'smtp.gmail.com',
            'port': 587,
            'username': 'test@example.com',
            'password': 'test_password'
        }

        recipients = ['user1@example.com', 'user2@example.com']
        report_html = '<html><body>Test Report</body></html>'
        chart_paths = []

        result = self.reporter.send_email(
            smtp_config=smtp_config,
            recipients=recipients,
            report_html=report_html,
            chart_paths=chart_paths
        )

        # Verify email was sent
        self.assertTrue(result)
        mock_smtp.starttls.assert_called_once()
        mock_smtp.login.assert_called_once_with('test@example.com', 'test_password')
        mock_smtp.send_message.assert_called_once()

    @patch('weekly_performance_report.smtplib.SMTP')
    def test_send_email_failure(self, mock_smtp_class):
        """Test email sending failure handling"""
        mock_smtp_class.side_effect = Exception("SMTP connection failed")

        smtp_config = {
            'server': 'smtp.gmail.com',
            'port': 587,
            'username': 'test@example.com',
            'password': 'test_password'
        }

        result = self.reporter.send_email(
            smtp_config=smtp_config,
            recipients=['user@example.com'],
            report_html='<html>Test</html>',
            chart_paths=[]
        )

        # Verify failure was handled gracefully
        self.assertFalse(result)


class TestConfigLoader(unittest.TestCase):
    """Test configuration loading functionality"""

    def setUp(self):
        """Set up test configuration file"""
        self.test_config_dir = tempfile.mkdtemp()
        self.test_config_path = os.path.join(self.test_config_dir, 'test_config.yaml')

        # Create test config
        test_config = """
database:
  host: localhost
  port: 5432
  user: test_user
  password: test_password
  database: test_db

email:
  server: smtp.test.com
  port: 587
  username: test@test.com
  password: test_pass
  recipients:
    - user1@test.com
    - user2@test.com

report:
  output_directory: /tmp/reports
  formats:
    - json
    - html
  include_charts: true
"""
        with open(self.test_config_path, 'w') as f:
            f.write(test_config)

    def tearDown(self):
        """Clean up test configuration"""
        if os.path.exists(self.test_config_dir):
            shutil.rmtree(self.test_config_dir)

    def test_load_config(self):
        """Test loading configuration from YAML file"""
        config = load_config(self.test_config_path)

        # Verify config structure
        self.assertIn('database', config)
        self.assertIn('email', config)
        self.assertIn('report', config)

        # Verify database config
        self.assertEqual(config['database']['host'], 'localhost')
        self.assertEqual(config['database']['port'], 5432)

        # Verify email config
        self.assertEqual(config['email']['server'], 'smtp.test.com')
        self.assertEqual(len(config['email']['recipients']), 2)

        # Verify report config
        self.assertEqual(config['report']['output_directory'], '/tmp/reports')
        self.assertTrue(config['report']['include_charts'])


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions"""

    def setUp(self):
        """Set up test environment"""
        self.reporter = PerformanceReporter(
            db_config={'host': 'localhost', 'port': 5432, 'user': 'test', 'password': 'test', 'database': 'test'},
            start_date=datetime(2025, 11, 1),
            end_date=datetime(2025, 11, 7)
        )

    def test_calculate_metrics_single_trade(self):
        """Test metric calculation with only one trade"""
        self.reporter.trades_df = pd.DataFrame({'fee': [5]})
        self.reporter.positions_df = pd.DataFrame({
            'status': ['CLOSED'],
            'realized_pnl': [100],
            'symbol': ['BTCUSDT'],
            'strategy': ['test'],
            'opened_at': [datetime.now()],
            'closed_at': [datetime.now()]
        })
        self.reporter.snapshots_df = pd.DataFrame({
            'total_value': [10000, 10100],
            'total_pnl': [0, 100],
            'total_return_pct': [0, 1.0],
            'daily_return_pct': [0, 1.0],
            'snapshot_time': pd.date_range(start='2025-11-01', periods=2, freq='D')
        })

        metrics = self.reporter.calculate_metrics()

        self.assertEqual(metrics['total_trades'], 1)
        self.assertEqual(metrics['winning_trades'], 1)
        self.assertEqual(metrics['losing_trades'], 0)
        self.assertEqual(metrics['win_rate'], 100.0)

    def test_calculate_metrics_all_losses(self):
        """Test metric calculation when all trades are losses"""
        self.reporter.trades_df = pd.DataFrame({'fee': [1, 2, 3]})
        self.reporter.positions_df = pd.DataFrame({
            'status': ['CLOSED', 'CLOSED', 'CLOSED'],
            'realized_pnl': [-50, -75, -100],
            'symbol': ['BTCUSDT'] * 3,
            'strategy': ['test'] * 3,
            'opened_at': pd.date_range(start='2025-11-01', periods=3, freq='D'),
            'closed_at': pd.date_range(start='2025-11-02', periods=3, freq='D')
        })
        self.reporter.snapshots_df = pd.DataFrame()

        metrics = self.reporter.calculate_metrics()

        self.assertEqual(metrics['winning_trades'], 0)
        self.assertEqual(metrics['losing_trades'], 3)
        self.assertEqual(metrics['win_rate'], 0)
        self.assertEqual(metrics['total_pnl'], -225)


def run_tests():
    """Run all tests and return results"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceReporter))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigLoader))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    # Run tests with verbose output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == '__main__':
    # Run tests
    result = run_tests()

    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)
