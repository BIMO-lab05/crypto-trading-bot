#!/usr/bin/env python3
"""
Weekly Performance Report Generator
Analyzes trading performance and generates comprehensive reports

Purpose: Generate detailed weekly trading performance reports with metrics,
         visualizations, and multi-format output (JSON, Markdown, HTML, CSV)

Author: Backend Developer Agent
Date: 2025-11-19
Version: 1.0.0
"""

import argparse
import os
import sys
import json
import logging
import smtplib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parent.parent

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import psycopg2
from psycopg2.extras import RealDictCursor
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set plotting style for professional reports
sns.set_style("whitegrid")
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 10


class PerformanceReporter:
    """
    Comprehensive performance reporter for crypto trading bot

    Generates weekly performance reports with:
    - Trading metrics (win rate, P&L, ROI, Sharpe ratio, max drawdown)
    - Visualizations (P&L charts, performance comparisons)
    - Multi-format output (JSON, Markdown, HTML, CSV)
    - Email delivery capability

    Attributes:
        db_config: Database connection configuration
        start_date: Report period start date
        end_date: Report period end date
        connection: PostgreSQL database connection
        trades_df: DataFrame containing all trades in period
        positions_df: DataFrame containing all positions in period
        snapshots_df: DataFrame containing portfolio snapshots
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        start_date: datetime,
        end_date: datetime
    ) -> None:
        """
        Initialize reporter with database connection and date range

        Args:
            db_config: Database connection parameters (host, port, user, password, database)
            start_date: Start of reporting period
            end_date: End of reporting period
        """
        self.db_config = db_config
        self.start_date = start_date
        self.end_date = end_date
        self.connection = None
        self.trades_df = None
        self.positions_df = None
        self.snapshots_df = None

        logger.info(f"Initialized PerformanceReporter for period: {start_date} to {end_date}")

    def connect_database(self) -> None:
        """
        Establish connection to PostgreSQL database

        Raises:
            psycopg2.Error: If database connection fails
        """
        try:
            self.connection = psycopg2.connect(
                host=self.db_config['host'],
                port=self.db_config['port'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                database=self.db_config['database']
            )
            logger.info(f"Connected to database: {self.db_config['database']}")
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def close_database(self) -> None:
        """Close database connection gracefully"""
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

    def fetch_trading_data(self) -> pd.DataFrame:
        """
        Fetch all trades within the reporting period

        Returns:
            pd.DataFrame: Trades data with columns for analysis

        Raises:
            ValueError: If no trades found in period
        """
        logger.info("Fetching trades data from database...")

        query = """
        SELECT
            trade_id,
            portfolio_id,
            position_id,
            symbol,
            action,
            order_type,
            quantity,
            price,
            total_cost,
            fee,
            fee_currency,
            executed_at,
            strategy,
            signal_confidence,
            signal_indicators,
            realized_pnl,
            pnl_percentage,
            notes
        FROM trades
        WHERE executed_at >= %s AND executed_at < %s
        ORDER BY executed_at ASC
        """

        try:
            self.trades_df = pd.read_sql_query(
                query,
                self.connection,
                params=(self.start_date, self.end_date)
            )

            logger.info(f"Fetched {len(self.trades_df)} trades")

            if len(self.trades_df) == 0:
                logger.warning("No trades found in specified period")

            return self.trades_df

        except Exception as e:
            logger.error(f"Error fetching trades: {e}")
            raise

    def fetch_positions_data(self) -> pd.DataFrame:
        """
        Fetch all positions that were active during reporting period

        Returns:
            pd.DataFrame: Positions data including open and closed positions
        """
        logger.info("Fetching positions data from database...")

        query = """
        SELECT
            position_id,
            portfolio_id,
            symbol,
            side,
            quantity,
            entry_price,
            exit_price,
            cost_basis,
            unrealized_pnl,
            realized_pnl,
            stop_loss,
            take_profit,
            status,
            strategy,
            entry_signal_confidence,
            exit_reason,
            opened_at,
            closed_at,
            updated_at
        FROM positions
        WHERE opened_at <= %s
          AND (closed_at IS NULL OR closed_at >= %s)
        ORDER BY opened_at ASC
        """

        try:
            self.positions_df = pd.read_sql_query(
                query,
                self.connection,
                params=(self.end_date, self.start_date)
            )

            logger.info(f"Fetched {len(self.positions_df)} positions")
            return self.positions_df

        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            raise

    def fetch_portfolio_snapshots(self) -> pd.DataFrame:
        """
        Fetch portfolio snapshots for the reporting period

        Returns:
            pd.DataFrame: Portfolio state snapshots over time
        """
        logger.info("Fetching portfolio snapshots from database...")

        query = """
        SELECT
            snapshot_id,
            portfolio_id,
            cash_balance,
            positions_value,
            total_value,
            realized_pnl,
            unrealized_pnl,
            total_pnl,
            total_return_pct,
            daily_pnl,
            daily_return_pct,
            open_positions_count,
            snapshot_time,
            snapshot_type
        FROM portfolio_snapshots
        WHERE snapshot_time >= %s AND snapshot_time < %s
        ORDER BY snapshot_time ASC
        """

        try:
            self.snapshots_df = pd.read_sql_query(
                query,
                self.connection,
                params=(self.start_date, self.end_date)
            )

            logger.info(f"Fetched {len(self.snapshots_df)} portfolio snapshots")
            return self.snapshots_df

        except Exception as e:
            logger.error(f"Error fetching snapshots: {e}")
            raise

    def calculate_metrics(self) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics

        Returns:
            Dict containing all calculated metrics:
            - total_trades: Total number of trades executed
            - winning_trades: Number of profitable trades
            - losing_trades: Number of losing trades
            - win_rate: Percentage of winning trades
            - total_pnl: Total profit and loss
            - total_fees: Total trading fees paid
            - roi_percentage: Return on investment
            - sharpe_ratio: Risk-adjusted return metric
            - max_drawdown: Maximum portfolio drawdown
            - avg_trade_duration: Average time positions are held
            - avg_win: Average profit per winning trade
            - avg_loss: Average loss per losing trade
            - profit_factor: Ratio of gross profit to gross loss
            - best_trade: Largest winning trade
            - worst_trade: Largest losing trade
        """
        logger.info("Calculating performance metrics...")

        metrics = {}

        # Basic trade statistics
        closed_positions = self.positions_df[self.positions_df['status'] == 'CLOSED']

        metrics['total_trades'] = len(self.trades_df)
        metrics['total_positions'] = len(closed_positions)

        # Win/Loss analysis (only for closed positions with realized P&L)
        if len(closed_positions) > 0:
            winning_positions = closed_positions[closed_positions['realized_pnl'] > 0]
            losing_positions = closed_positions[closed_positions['realized_pnl'] < 0]

            metrics['winning_trades'] = len(winning_positions)
            metrics['losing_trades'] = len(losing_positions)
            metrics['win_rate'] = (len(winning_positions) / len(closed_positions) * 100) if len(closed_positions) > 0 else 0

            # P&L metrics
            metrics['total_pnl'] = float(closed_positions['realized_pnl'].sum())
            metrics['avg_win'] = float(winning_positions['realized_pnl'].mean()) if len(winning_positions) > 0 else 0
            metrics['avg_loss'] = float(losing_positions['realized_pnl'].mean()) if len(losing_positions) > 0 else 0

            # Best and worst trades
            metrics['best_trade'] = float(closed_positions['realized_pnl'].max()) if len(closed_positions) > 0 else 0
            metrics['worst_trade'] = float(closed_positions['realized_pnl'].min()) if len(closed_positions) > 0 else 0

            # Profit factor (gross profit / gross loss)
            gross_profit = float(winning_positions['realized_pnl'].sum()) if len(winning_positions) > 0 else 0
            gross_loss = abs(float(losing_positions['realized_pnl'].sum())) if len(losing_positions) > 0 else 0
            metrics['profit_factor'] = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        else:
            # No closed positions
            metrics['winning_trades'] = 0
            metrics['losing_trades'] = 0
            metrics['win_rate'] = 0
            metrics['total_pnl'] = 0
            metrics['avg_win'] = 0
            metrics['avg_loss'] = 0
            metrics['best_trade'] = 0
            metrics['worst_trade'] = 0
            metrics['profit_factor'] = 0

        # Fee analysis
        metrics['total_fees'] = float(self.trades_df['fee'].sum()) if len(self.trades_df) > 0 else 0

        # ROI calculation from portfolio snapshots
        if len(self.snapshots_df) > 0:
            first_snapshot = self.snapshots_df.iloc[0]
            last_snapshot = self.snapshots_df.iloc[-1]

            initial_value = float(first_snapshot['total_value'])
            final_value = float(last_snapshot['total_value'])

            metrics['roi_percentage'] = ((final_value - initial_value) / initial_value * 100) if initial_value > 0 else 0
            metrics['initial_portfolio_value'] = initial_value
            metrics['final_portfolio_value'] = final_value

            # Calculate Sharpe Ratio (annualized)
            # Using daily returns from snapshots
            if len(self.snapshots_df) > 1:
                daily_returns = self.snapshots_df['daily_return_pct'].dropna()
                if len(daily_returns) > 0:
                    avg_daily_return = daily_returns.mean()
                    std_daily_return = daily_returns.std()

                    # Annualize (assuming 365 trading days for crypto)
                    # Sharpe = (Average Return - Risk Free Rate) / Std Dev
                    # Assuming risk-free rate = 0 for simplicity
                    if std_daily_return > 0:
                        metrics['sharpe_ratio'] = (avg_daily_return / std_daily_return) * np.sqrt(365)
                    else:
                        metrics['sharpe_ratio'] = 0
                else:
                    metrics['sharpe_ratio'] = 0
            else:
                metrics['sharpe_ratio'] = 0

            # Calculate Maximum Drawdown
            cumulative_returns = (1 + self.snapshots_df['total_return_pct'] / 100).cumprod()
            running_max = cumulative_returns.cummax()
            drawdown = (cumulative_returns - running_max) / running_max * 100
            metrics['max_drawdown'] = float(drawdown.min()) if len(drawdown) > 0 else 0
        else:
            metrics['roi_percentage'] = 0
            metrics['initial_portfolio_value'] = 0
            metrics['final_portfolio_value'] = 0
            metrics['sharpe_ratio'] = 0
            metrics['max_drawdown'] = 0

        # Average trade duration (for closed positions)
        if len(closed_positions) > 0:
            closed_positions_copy = closed_positions.copy()
            closed_positions_copy['duration'] = (
                pd.to_datetime(closed_positions_copy['closed_at']) -
                pd.to_datetime(closed_positions_copy['opened_at'])
            )
            avg_duration = closed_positions_copy['duration'].mean()
            metrics['avg_trade_duration_hours'] = avg_duration.total_seconds() / 3600 if pd.notna(avg_duration) else 0
        else:
            metrics['avg_trade_duration_hours'] = 0

        # Symbol performance breakdown
        if len(closed_positions) > 0:
            symbol_performance = closed_positions.groupby('symbol')['realized_pnl'].agg(['sum', 'count', 'mean'])
            metrics['symbol_performance'] = symbol_performance.to_dict('index')
        else:
            metrics['symbol_performance'] = {}

        # Strategy performance breakdown
        if len(closed_positions) > 0:
            strategy_performance = closed_positions.groupby('strategy')['realized_pnl'].agg(['sum', 'count', 'mean'])
            metrics['strategy_performance'] = strategy_performance.to_dict('index')
        else:
            metrics['strategy_performance'] = {}

        logger.info(f"Metrics calculated: Win Rate={metrics['win_rate']:.2f}%, Total P&L={metrics['total_pnl']:.2f}")

        return metrics

    def generate_charts(self, output_dir: str) -> List[str]:
        """
        Generate visualization charts for the report

        Args:
            output_dir: Directory to save chart images

        Returns:
            List of file paths to generated chart images
        """
        logger.info(f"Generating charts in {output_dir}...")

        chart_paths = []
        os.makedirs(output_dir, exist_ok=True)

        # Chart 1: Cumulative P&L Over Time
        if len(self.snapshots_df) > 0:
            plt.figure(figsize=(12, 6))
            plt.plot(
                self.snapshots_df['snapshot_time'],
                self.snapshots_df['total_pnl'],
                linewidth=2,
                color='#2E86AB',
                label='Total P&L'
            )
            plt.plot(
                self.snapshots_df['snapshot_time'],
                self.snapshots_df['realized_pnl'],
                linewidth=1.5,
                color='#06A77D',
                linestyle='--',
                label='Realized P&L'
            )
            plt.axhline(y=0, color='red', linestyle='--', alpha=0.3)
            plt.xlabel('Date')
            plt.ylabel('P&L (USDT)')
            plt.title('Cumulative Profit & Loss Over Time')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            chart_path = os.path.join(output_dir, 'pnl_over_time.png')
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            chart_paths.append(chart_path)
            logger.info(f"Generated chart: {chart_path}")

        # Chart 2: Portfolio Value Over Time
        if len(self.snapshots_df) > 0:
            plt.figure(figsize=(12, 6))
            plt.plot(
                self.snapshots_df['snapshot_time'],
                self.snapshots_df['total_value'],
                linewidth=2,
                color='#9D4EDD',
                label='Total Portfolio Value'
            )
            plt.fill_between(
                self.snapshots_df['snapshot_time'],
                self.snapshots_df['total_value'],
                alpha=0.3,
                color='#9D4EDD'
            )
            plt.xlabel('Date')
            plt.ylabel('Portfolio Value (USDT)')
            plt.title('Portfolio Value Over Time')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()

            chart_path = os.path.join(output_dir, 'portfolio_value.png')
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            chart_paths.append(chart_path)
            logger.info(f"Generated chart: {chart_path}")

        # Chart 3: Win Rate Trend (rolling 10-trade window)
        closed_positions = self.positions_df[self.positions_df['status'] == 'CLOSED'].copy()
        if len(closed_positions) >= 10:
            closed_positions = closed_positions.sort_values('closed_at')
            closed_positions['is_win'] = (closed_positions['realized_pnl'] > 0).astype(int)
            closed_positions['rolling_win_rate'] = closed_positions['is_win'].rolling(window=10).mean() * 100

            plt.figure(figsize=(12, 6))
            plt.plot(
                range(len(closed_positions)),
                closed_positions['rolling_win_rate'],
                linewidth=2,
                color='#F72585'
            )
            plt.axhline(y=50, color='gray', linestyle='--', alpha=0.5, label='50% Win Rate')
            plt.xlabel('Trade Number')
            plt.ylabel('Win Rate (%)')
            plt.title('Rolling Win Rate (10-Trade Window)')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.ylim(0, 100)
            plt.tight_layout()

            chart_path = os.path.join(output_dir, 'win_rate_trend.png')
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            chart_paths.append(chart_path)
            logger.info(f"Generated chart: {chart_path}")

        # Chart 4: Symbol Performance Comparison
        if len(closed_positions) > 0:
            symbol_pnl = closed_positions.groupby('symbol')['realized_pnl'].sum().sort_values(ascending=False)

            if len(symbol_pnl) > 0:
                plt.figure(figsize=(10, 6))
                colors = ['#06A77D' if x > 0 else '#D62828' for x in symbol_pnl.values]
                plt.barh(symbol_pnl.index, symbol_pnl.values, color=colors)
                plt.xlabel('Total P&L (USDT)')
                plt.ylabel('Symbol')
                plt.title('Performance by Trading Symbol')
                plt.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
                plt.grid(True, alpha=0.3, axis='x')
                plt.tight_layout()

                chart_path = os.path.join(output_dir, 'symbol_performance.png')
                plt.savefig(chart_path, dpi=300, bbox_inches='tight')
                plt.close()
                chart_paths.append(chart_path)
                logger.info(f"Generated chart: {chart_path}")

        # Chart 5: Daily Trading Volume
        if len(self.trades_df) > 0:
            trades_with_date = self.trades_df.copy()
            trades_with_date['trade_date'] = pd.to_datetime(trades_with_date['executed_at']).dt.date
            daily_volume = trades_with_date.groupby('trade_date')['total_cost'].sum()

            plt.figure(figsize=(12, 6))
            plt.bar(
                range(len(daily_volume)),
                daily_volume.values,
                color='#4895EF',
                alpha=0.7
            )
            plt.xlabel('Day')
            plt.ylabel('Trading Volume (USDT)')
            plt.title('Daily Trading Volume')
            plt.xticks(range(len(daily_volume)), [str(d) for d in daily_volume.index], rotation=45, ha='right')
            plt.grid(True, alpha=0.3, axis='y')
            plt.tight_layout()

            chart_path = os.path.join(output_dir, 'daily_volume.png')
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()
            chart_paths.append(chart_path)
            logger.info(f"Generated chart: {chart_path}")

        logger.info(f"Generated {len(chart_paths)} charts")
        return chart_paths

    def create_markdown_report(self, metrics: Dict[str, Any], chart_paths: List[str]) -> str:
        """
        Generate markdown formatted report

        Args:
            metrics: Calculated performance metrics
            chart_paths: List of chart image file paths

        Returns:
            str: Markdown formatted report content
        """
        logger.info("Generating markdown report...")

        report = f"""# Weekly Performance Report
**Period:** {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Trades** | {metrics['total_trades']} |
| **Total Positions** | {metrics['total_positions']} |
| **Win Rate** | {metrics['win_rate']:.2f}% |
| **Total P&L** | ${metrics['total_pnl']:.2f} USDT |
| **ROI** | {metrics['roi_percentage']:.2f}% |
| **Sharpe Ratio** | {metrics['sharpe_ratio']:.4f} |
| **Max Drawdown** | {metrics['max_drawdown']:.2f}% |

---

## Trading Performance

### Win/Loss Statistics
- **Winning Trades:** {metrics['winning_trades']}
- **Losing Trades:** {metrics['losing_trades']}
- **Win Rate:** {metrics['win_rate']:.2f}%
- **Average Win:** ${metrics['avg_win']:.2f} USDT
- **Average Loss:** ${metrics['avg_loss']:.2f} USDT
- **Profit Factor:** {metrics['profit_factor']:.2f}

### Trade Quality
- **Best Trade:** ${metrics['best_trade']:.2f} USDT
- **Worst Trade:** ${metrics['worst_trade']:.2f} USDT
- **Average Trade Duration:** {metrics['avg_trade_duration_hours']:.1f} hours
- **Total Fees Paid:** ${metrics['total_fees']:.2f} USDT

---

## Portfolio Metrics

### Overall Performance
- **Initial Portfolio Value:** ${metrics.get('initial_portfolio_value', 0):.2f} USDT
- **Final Portfolio Value:** ${metrics.get('final_portfolio_value', 0):.2f} USDT
- **Total Return:** {metrics['roi_percentage']:.2f}%
- **Total P&L:** ${metrics['total_pnl']:.2f} USDT

### Risk Metrics
- **Sharpe Ratio:** {metrics['sharpe_ratio']:.4f}
- **Maximum Drawdown:** {metrics['max_drawdown']:.2f}%

---

## Performance by Symbol

"""

        # Add symbol performance table
        if metrics['symbol_performance']:
            report += "| Symbol | Total P&L | Trades | Avg P&L |\n"
            report += "|--------|-----------|--------|----------|\n"
            for symbol, perf in metrics['symbol_performance'].items():
                report += f"| {symbol} | ${perf['sum']:.2f} | {int(perf['count'])} | ${perf['mean']:.2f} |\n"
        else:
            report += "*No symbol data available*\n"

        report += "\n---\n\n## Performance by Strategy\n\n"

        # Add strategy performance table
        if metrics['strategy_performance']:
            report += "| Strategy | Total P&L | Trades | Avg P&L |\n"
            report += "|----------|-----------|--------|----------|\n"
            for strategy, perf in metrics['strategy_performance'].items():
                strategy_name = strategy if strategy else "Unknown"
                report += f"| {strategy_name} | ${perf['sum']:.2f} | {int(perf['count'])} | ${perf['mean']:.2f} |\n"
        else:
            report += "*No strategy data available*\n"

        report += "\n---\n\n## Visualizations\n\n"

        # Add chart references
        for chart_path in chart_paths:
            chart_name = os.path.basename(chart_path).replace('_', ' ').replace('.png', '').title()
            report += f"### {chart_name}\n![{chart_name}]({os.path.basename(chart_path)})\n\n"

        report += "\n---\n\n"
        report += f"*Report generated by Crypto Trading Bot Performance Analyzer v1.0*\n"
        report += f"*Report period: {(self.end_date - self.start_date).days} days*\n"

        logger.info("Markdown report generated")
        return report

    def create_html_report(self, metrics: Dict[str, Any], chart_paths: List[str]) -> str:
        """
        Generate HTML formatted report with embedded charts

        Args:
            metrics: Calculated performance metrics
            chart_paths: List of chart image file paths

        Returns:
            str: HTML formatted report content
        """
        logger.info("Generating HTML report...")

        # Convert chart paths to base64 for embedding (optional - for now use file references)
        chart_html = ""
        for chart_path in chart_paths:
            chart_name = os.path.basename(chart_path).replace('_', ' ').replace('.png', '').title()
            chart_html += f"""
            <div class="chart">
                <h3>{chart_name}</h3>
                <img src="{os.path.basename(chart_path)}" alt="{chart_name}" style="max-width: 100%; height: auto;">
            </div>
            """

        # Symbol performance HTML
        symbol_html = ""
        if metrics['symbol_performance']:
            symbol_html = "<table><tr><th>Symbol</th><th>Total P&L</th><th>Trades</th><th>Avg P&L</th></tr>"
            for symbol, perf in metrics['symbol_performance'].items():
                pnl_class = "positive" if perf['sum'] > 0 else "negative"
                symbol_html += f"""
                <tr>
                    <td>{symbol}</td>
                    <td class="{pnl_class}">${perf['sum']:.2f}</td>
                    <td>{int(perf['count'])}</td>
                    <td>${perf['mean']:.2f}</td>
                </tr>
                """
            symbol_html += "</table>"
        else:
            symbol_html = "<p>No symbol data available</p>"

        # Strategy performance HTML
        strategy_html = ""
        if metrics['strategy_performance']:
            strategy_html = "<table><tr><th>Strategy</th><th>Total P&L</th><th>Trades</th><th>Avg P&L</th></tr>"
            for strategy, perf in metrics['strategy_performance'].items():
                strategy_name = strategy if strategy else "Unknown"
                pnl_class = "positive" if perf['sum'] > 0 else "negative"
                strategy_html += f"""
                <tr>
                    <td>{strategy_name}</td>
                    <td class="{pnl_class}">${perf['sum']:.2f}</td>
                    <td>{int(perf['count'])}</td>
                    <td>${perf['mean']:.2f}</td>
                </tr>
                """
            strategy_html += "</table>"
        else:
            strategy_html = "<p>No strategy data available</p>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Weekly Performance Report - {self.start_date.strftime('%Y-%m-%d')}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2E86AB;
            border-bottom: 3px solid #2E86AB;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #06A77D;
            margin-top: 30px;
        }}
        h3 {{
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #2E86AB;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-card h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            color: rgba(255,255,255,0.9);
        }}
        .metric-card .value {{
            font-size: 32px;
            font-weight: bold;
            margin: 0;
        }}
        .positive {{
            color: #06A77D;
            font-weight: bold;
        }}
        .negative {{
            color: #D62828;
            font-weight: bold;
        }}
        .chart {{
            margin: 30px 0;
            padding: 20px;
            background-color: #f9f9f9;
            border-radius: 8px;
        }}
        .chart img {{
            display: block;
            margin: 0 auto;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #666;
            font-size: 14px;
        }}
        .summary-box {{
            background-color: #f0f8ff;
            border-left: 4px solid #2E86AB;
            padding: 15px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Weekly Performance Report</h1>
        <div class="summary-box">
            <strong>Period:</strong> {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}<br>
            <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        </div>

        <h2>Executive Summary</h2>
        <div class="metric-grid">
            <div class="metric-card">
                <h3>Total Trades</h3>
                <p class="value">{metrics['total_trades']}</p>
            </div>
            <div class="metric-card">
                <h3>Win Rate</h3>
                <p class="value">{metrics['win_rate']:.1f}%</p>
            </div>
            <div class="metric-card">
                <h3>Total P&L</h3>
                <p class="value {'positive' if metrics['total_pnl'] > 0 else 'negative'}">${metrics['total_pnl']:.2f}</p>
            </div>
            <div class="metric-card">
                <h3>ROI</h3>
                <p class="value {'positive' if metrics['roi_percentage'] > 0 else 'negative'}">{metrics['roi_percentage']:.2f}%</p>
            </div>
            <div class="metric-card">
                <h3>Sharpe Ratio</h3>
                <p class="value">{metrics['sharpe_ratio']:.3f}</p>
            </div>
            <div class="metric-card">
                <h3>Max Drawdown</h3>
                <p class="value">{metrics['max_drawdown']:.2f}%</p>
            </div>
        </div>

        <h2>Trading Performance</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Winning Trades</td>
                <td class="positive">{metrics['winning_trades']}</td>
            </tr>
            <tr>
                <td>Losing Trades</td>
                <td class="negative">{metrics['losing_trades']}</td>
            </tr>
            <tr>
                <td>Average Win</td>
                <td class="positive">${metrics['avg_win']:.2f}</td>
            </tr>
            <tr>
                <td>Average Loss</td>
                <td class="negative">${metrics['avg_loss']:.2f}</td>
            </tr>
            <tr>
                <td>Profit Factor</td>
                <td>{metrics['profit_factor']:.2f}</td>
            </tr>
            <tr>
                <td>Best Trade</td>
                <td class="positive">${metrics['best_trade']:.2f}</td>
            </tr>
            <tr>
                <td>Worst Trade</td>
                <td class="negative">${metrics['worst_trade']:.2f}</td>
            </tr>
            <tr>
                <td>Avg Trade Duration</td>
                <td>{metrics['avg_trade_duration_hours']:.1f} hours</td>
            </tr>
            <tr>
                <td>Total Fees</td>
                <td>${metrics['total_fees']:.2f}</td>
            </tr>
        </table>

        <h2>Performance by Symbol</h2>
        {symbol_html}

        <h2>Performance by Strategy</h2>
        {strategy_html}

        <h2>Visualizations</h2>
        {chart_html}

        <div class="footer">
            <p>Report generated by Crypto Trading Bot Performance Analyzer v1.0</p>
            <p>Report period: {(self.end_date - self.start_date).days} days</p>
        </div>
    </div>
</body>
</html>"""

        logger.info("HTML report generated")
        return html

    def create_csv_export(self, metrics: Dict[str, Any], output_dir: str) -> str:
        """
        Export performance data to CSV format for Excel analysis

        Args:
            metrics: Calculated performance metrics
            output_dir: Directory to save CSV file

        Returns:
            str: Path to generated CSV file
        """
        logger.info("Generating CSV export...")

        # Export closed positions to CSV
        csv_path = os.path.join(output_dir, 'trading_performance.csv')

        closed_positions = self.positions_df[self.positions_df['status'] == 'CLOSED'].copy()

        if len(closed_positions) > 0:
            # Select relevant columns for export
            export_df = closed_positions[[
                'symbol', 'side', 'quantity', 'entry_price', 'exit_price',
                'realized_pnl', 'strategy', 'opened_at', 'closed_at'
            ]].copy()

            # Calculate additional metrics
            export_df['duration_hours'] = (
                pd.to_datetime(export_df['closed_at']) - pd.to_datetime(export_df['opened_at'])
            ).dt.total_seconds() / 3600

            export_df['pnl_percentage'] = (
                (export_df['exit_price'] - export_df['entry_price']) / export_df['entry_price'] * 100
            )

            # Export to CSV
            export_df.to_csv(csv_path, index=False)
            logger.info(f"CSV exported to: {csv_path}")
        else:
            # Create empty CSV with headers
            pd.DataFrame(columns=[
                'symbol', 'side', 'quantity', 'entry_price', 'exit_price',
                'realized_pnl', 'strategy', 'opened_at', 'closed_at',
                'duration_hours', 'pnl_percentage'
            ]).to_csv(csv_path, index=False)
            logger.warning("No closed positions to export")

        return csv_path

    def save_reports(self, output_dir: str, formats: List[str] = None) -> Dict[str, str]:
        """
        Save all report formats to directory

        Args:
            output_dir: Directory to save all reports
            formats: List of formats to generate (json, markdown, html, csv)
                    If None, generates all formats

        Returns:
            Dict mapping format names to file paths
        """
        if formats is None:
            formats = ['json', 'markdown', 'html', 'csv']

        logger.info(f"Saving reports to {output_dir} in formats: {formats}")

        os.makedirs(output_dir, exist_ok=True)

        # Calculate metrics
        metrics = self.calculate_metrics()

        # Generate charts
        charts_dir = os.path.join(output_dir, 'charts')
        chart_paths = self.generate_charts(charts_dir)

        report_files = {}

        # JSON format
        if 'json' in formats:
            json_path = os.path.join(output_dir, 'performance_report.json')
            with open(json_path, 'w') as f:
                json.dump({
                    'period': {
                        'start': self.start_date.isoformat(),
                        'end': self.end_date.isoformat()
                    },
                    'metrics': metrics,
                    'generated_at': datetime.now().isoformat()
                }, f, indent=2, default=str)
            report_files['json'] = json_path
            logger.info(f"JSON report saved: {json_path}")

        # Markdown format
        if 'markdown' in formats:
            markdown_content = self.create_markdown_report(metrics, chart_paths)
            markdown_path = os.path.join(output_dir, 'performance_report.md')
            with open(markdown_path, 'w') as f:
                f.write(markdown_content)
            report_files['markdown'] = markdown_path
            logger.info(f"Markdown report saved: {markdown_path}")

        # HTML format
        if 'html' in formats:
            html_content = self.create_html_report(metrics, chart_paths)
            html_path = os.path.join(output_dir, 'performance_report.html')
            with open(html_path, 'w') as f:
                f.write(html_content)
            report_files['html'] = html_path
            logger.info(f"HTML report saved: {html_path}")

        # CSV format
        if 'csv' in formats:
            csv_path = self.create_csv_export(metrics, output_dir)
            report_files['csv'] = csv_path

        logger.info(f"All reports saved successfully to {output_dir}")
        return report_files

    def send_email(
        self,
        smtp_config: Dict[str, Any],
        recipients: List[str],
        report_html: str,
        chart_paths: List[str]
    ) -> bool:
        """
        Send report via email with HTML formatting and chart attachments

        Args:
            smtp_config: SMTP server configuration (server, port, username, password)
            recipients: List of email addresses to send report to
            report_html: HTML formatted report content
            chart_paths: List of chart image paths to attach

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        logger.info(f"Sending email report to {len(recipients)} recipient(s)...")

        try:
            # Create message
            msg = MIMEMultipart('related')
            msg['Subject'] = f"Weekly Performance Report - {self.start_date.strftime('%Y-%m-%d')} to {self.end_date.strftime('%Y-%m-%d')}"
            msg['From'] = smtp_config.get('from_email', smtp_config['username'])
            msg['To'] = ', '.join(recipients)

            # Attach HTML body
            html_part = MIMEText(report_html, 'html')
            msg.attach(html_part)

            # Attach charts as inline images
            for chart_path in chart_paths:
                if os.path.exists(chart_path):
                    with open(chart_path, 'rb') as f:
                        img = MIMEImage(f.read())
                        img.add_header('Content-ID', f'<{os.path.basename(chart_path)}>')
                        img.add_header('Content-Disposition', 'inline', filename=os.path.basename(chart_path))
                        msg.attach(img)

            # Send email
            with smtplib.SMTP(smtp_config['server'], smtp_config['port']) as server:
                server.starttls()
                server.login(smtp_config['username'], smtp_config['password'])
                server.send_message(msg)

            logger.info("Email sent successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Dict containing configuration parameters
    """
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config


def main():
    """
    Main entry point for weekly performance report script

    Supports command-line arguments for customization
    """
    parser = argparse.ArgumentParser(
        description='Generate weekly trading performance reports',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate report for last 7 days
  python weekly_performance_report.py

  # Generate report for specific date range
  python weekly_performance_report.py --start 2025-11-01 --end 2025-11-07

  # Generate only HTML and CSV formats
  python weekly_performance_report.py --formats html csv

  # Send report via email
  python weekly_performance_report.py --email --config /path/to/config.yaml

  # Dry run (no email, show what would be done)
  python weekly_performance_report.py --dry-run
        """
    )

    parser.add_argument(
        '--start',
        type=str,
        help='Start date (YYYY-MM-DD). Default: 7 days ago'
    )

    parser.add_argument(
        '--end',
        type=str,
        help='End date (YYYY-MM-DD). Default: today'
    )

    parser.add_argument(
        '--config',
        type=str,
        default=str(_REPO_ROOT / 'config/performance_report_config.yaml'),
        help='Path to configuration file'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=str(_REPO_ROOT / 'reports'),
        help='Output directory for reports'
    )

    parser.add_argument(
        '--formats',
        nargs='+',
        choices=['json', 'markdown', 'html', 'csv'],
        default=['json', 'markdown', 'html', 'csv'],
        help='Report formats to generate'
    )

    parser.add_argument(
        '--email',
        action='store_true',
        help='Send report via email'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (no email sent, show metrics only)'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Parse dates
    if args.end:
        end_date = datetime.strptime(args.end, '%Y-%m-%d')
    else:
        end_date = datetime.now()

    if args.start:
        start_date = datetime.strptime(args.start, '%Y-%m-%d')
    else:
        start_date = end_date - timedelta(days=7)

    logger.info(f"Generating performance report for {start_date} to {end_date}")

    # Load configuration
    try:
        config = load_config(args.config)
        logger.info(f"Loaded configuration from {args.config}")
    except FileNotFoundError:
        logger.error(f"Configuration file not found: {args.config}")
        logger.info("Using default configuration from environment variables")
        config = {
            'database': {
                'host': os.getenv('POSTGRES_HOST', 'localhost'),
                'port': int(os.getenv('POSTGRES_PORT', 5432)),
                'user': os.getenv('POSTGRES_USER', 'cryptobot'),
                'password': os.getenv('POSTGRES_PASSWORD', 'cryptobot_secure_2024'),
                'database': os.getenv('POSTGRES_DB', 'cryptobot')
            },
            'email': {},
            'report': {
                'output_directory': args.output,
                'formats': args.formats,
                'include_charts': True
            }
        }

    # Initialize reporter
    reporter = PerformanceReporter(
        db_config=config['database'],
        start_date=start_date,
        end_date=end_date
    )

    try:
        # Connect to database
        reporter.connect_database()

        # Fetch data
        reporter.fetch_trading_data()
        reporter.fetch_positions_data()
        reporter.fetch_portfolio_snapshots()

        if args.dry_run:
            # Just calculate and display metrics
            metrics = reporter.calculate_metrics()
            print("\n=== PERFORMANCE METRICS (DRY RUN) ===")
            print(json.dumps(metrics, indent=2, default=str))
            print("\n=== DRY RUN COMPLETE ===")
        else:
            # Generate and save reports
            report_files = reporter.save_reports(
                output_dir=config['report']['output_directory'],
                formats=args.formats
            )

            print("\n=== REPORTS GENERATED ===")
            for format_type, file_path in report_files.items():
                print(f"  {format_type.upper()}: {file_path}")

            # Send email if requested
            if args.email and 'email' in config:
                if 'html' in report_files:
                    with open(report_files['html'], 'r') as f:
                        html_content = f.read()

                    chart_paths = reporter.generate_charts(
                        os.path.join(config['report']['output_directory'], 'charts')
                    )

                    success = reporter.send_email(
                        smtp_config=config['email'],
                        recipients=config['email'].get('recipients', []),
                        report_html=html_content,
                        chart_paths=chart_paths
                    )

                    if success:
                        print("\n=== EMAIL SENT SUCCESSFULLY ===")
                    else:
                        print("\n=== EMAIL SENDING FAILED ===")
                else:
                    logger.warning("HTML format required for email, but not generated")

    except Exception as e:
        logger.error(f"Error generating report: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Clean up
        reporter.close_database()

    print("\n=== REPORT GENERATION COMPLETE ===")


if __name__ == "__main__":
    main()
