#!/usr/bin/env python3
"""
Backtest Visualization Module
Generates charts and visual reports for backtest comparisons
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path
import json


class BacktestVisualizer:
    """
    Create visualizations for backtest results
    Generates HTML reports with embedded charts using Chart.js
    """

    @staticmethod
    def generate_html_report(
        phase1_result,
        phase3_result,
        symbol: str,
        interval: str,
        test_params: Dict
    ) -> str:
        """
        Generate comprehensive HTML report with interactive charts

        Args:
            phase1_result: Phase 1 backtest result
            phase3_result: Phase 3 backtest result
            symbol: Trading pair
            interval: Timeframe
            test_params: Test configuration

        Returns:
            HTML report as string
        """
        # Prepare data for charts
        equity_data = BacktestVisualizer._prepare_equity_data(phase1_result, phase3_result)
        drawdown_data = BacktestVisualizer._prepare_drawdown_data(phase1_result, phase3_result)
        monthly_data = BacktestVisualizer._prepare_monthly_data(phase1_result, phase3_result)
        trade_distribution = BacktestVisualizer._prepare_trade_distribution(phase1_result, phase3_result)

        # Calculate summary stats
        phase1_stats = BacktestVisualizer._calculate_summary_stats(phase1_result)
        phase3_stats = BacktestVisualizer._calculate_summary_stats(phase3_result)

        # Build HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Comparison: {symbol} - Phase 1 vs Phase 3</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            color: #333;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
        }}

        .header .subtitle {{
            font-size: 1.2em;
            opacity: 0.9;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            padding: 40px;
            background: #f8f9fa;
        }}

        .stat-card {{
            background: white;
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 20px rgba(0,0,0,0.15);
        }}

        .stat-card h3 {{
            font-size: 0.9em;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }}

        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 8px;
        }}

        .stat-comparison {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #e9ecef;
        }}

        .phase-label {{
            font-size: 0.85em;
            color: #6c757d;
        }}

        .phase1-value {{
            color: #e74c3c;
            font-weight: 600;
        }}

        .phase3-value {{
            color: #2ecc71;
            font-weight: 600;
        }}

        .improvement {{
            font-size: 0.9em;
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: 600;
        }}

        .improvement.positive {{
            background: #d4edda;
            color: #155724;
        }}

        .improvement.negative {{
            background: #f8d7da;
            color: #721c24;
        }}

        .chart-section {{
            padding: 40px;
        }}

        .chart-container {{
            position: relative;
            height: 400px;
            margin-bottom: 40px;
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}

        .chart-title {{
            font-size: 1.5em;
            font-weight: 600;
            margin-bottom: 20px;
            color: #2c3e50;
        }}

        .comparison-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}

        .comparison-table th {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px;
            text-align: left;
            font-weight: 600;
        }}

        .comparison-table td {{
            padding: 14px 16px;
            border-bottom: 1px solid #e9ecef;
        }}

        .comparison-table tr:last-child td {{
            border-bottom: none;
        }}

        .comparison-table tr:hover {{
            background: #f8f9fa;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: 600;
        }}

        .badge.success {{
            background: #d4edda;
            color: #155724;
        }}

        .badge.danger {{
            background: #f8d7da;
            color: #721c24;
        }}

        .badge.warning {{
            background: #fff3cd;
            color: #856404;
        }}

        .footer {{
            background: #2c3e50;
            color: white;
            text-align: center;
            padding: 20px;
            font-size: 0.9em;
        }}

        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: 1fr;
            }}

            .chart-container {{
                height: 300px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>{symbol} Backtest Comparison</h1>
            <div class="subtitle">Phase 1 (Technical Analysis) vs Phase 3 (AI-Enhanced)</div>
            <div class="subtitle" style="margin-top: 10px; font-size: 0.9em;">
                {phase1_result.start_date.strftime('%Y-%m-%d')} to {phase1_result.end_date.strftime('%Y-%m-%d')}
            </div>
        </div>

        <!-- Summary Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Return</h3>
                <div class="stat-value">{phase3_result.total_profit_loss_pct:.2f}%</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">{phase1_result.total_profit_loss_pct:.2f}%</span></span>
                    <span class="improvement {'positive' if phase3_result.total_profit_loss_pct > phase1_result.total_profit_loss_pct else 'negative'}">
                        {(phase3_result.total_profit_loss_pct - phase1_result.total_profit_loss_pct):+.2f}%
                    </span>
                </div>
            </div>

            <div class="stat-card">
                <h3>Win Rate</h3>
                <div class="stat-value">{phase3_result.win_rate:.1f}%</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">{phase1_result.win_rate:.1f}%</span></span>
                    <span class="improvement {'positive' if phase3_result.win_rate > phase1_result.win_rate else 'negative'}">
                        {(phase3_result.win_rate - phase1_result.win_rate):+.1f}%
                    </span>
                </div>
            </div>

            <div class="stat-card">
                <h3>Sharpe Ratio</h3>
                <div class="stat-value">{phase3_result.sharpe_ratio:.3f}</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">{phase1_result.sharpe_ratio:.3f}</span></span>
                    <span class="improvement {'positive' if phase3_result.sharpe_ratio > phase1_result.sharpe_ratio else 'negative'}">
                        {(phase3_result.sharpe_ratio - phase1_result.sharpe_ratio):+.3f}
                    </span>
                </div>
            </div>

            <div class="stat-card">
                <h3>Max Drawdown</h3>
                <div class="stat-value">{phase3_result.max_drawdown_pct:.2f}%</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">{phase1_result.max_drawdown_pct:.2f}%</span></span>
                    <span class="improvement {'positive' if phase3_result.max_drawdown_pct < phase1_result.max_drawdown_pct else 'negative'}">
                        {(phase1_result.max_drawdown_pct - phase3_result.max_drawdown_pct):+.2f}%
                    </span>
                </div>
            </div>

            <div class="stat-card">
                <h3>Total Trades</h3>
                <div class="stat-value">{phase3_result.total_trades}</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">{phase1_result.total_trades}</span></span>
                    <span class="improvement {'positive' if phase3_result.total_trades < phase1_result.total_trades else 'negative'}">
                        {(phase3_result.total_trades - phase1_result.total_trades):+d}
                    </span>
                </div>
            </div>

            <div class="stat-card">
                <h3>Final Capital</h3>
                <div class="stat-value">${phase3_result.final_capital:,.0f}</div>
                <div class="stat-comparison">
                    <span class="phase-label">Phase 1: <span class="phase1-value">${phase1_result.final_capital:,.0f}</span></span>
                    <span class="improvement {'positive' if phase3_result.final_capital > phase1_result.final_capital else 'negative'}">
                        ${(phase3_result.final_capital - phase1_result.final_capital):+,.0f}
                    </span>
                </div>
            </div>
        </div>

        <!-- Charts -->
        <div class="chart-section">
            <!-- Equity Curve -->
            <div class="chart-title">Equity Curve Comparison</div>
            <div class="chart-container">
                <canvas id="equityChart"></canvas>
            </div>

            <!-- Drawdown Chart -->
            <div class="chart-title">Drawdown Analysis</div>
            <div class="chart-container">
                <canvas id="drawdownChart"></canvas>
            </div>

            <!-- Monthly Returns -->
            <div class="chart-title">Monthly Returns</div>
            <div class="chart-container">
                <canvas id="monthlyReturnsChart"></canvas>
            </div>

            <!-- Trade Distribution -->
            <div class="chart-title">Profit/Loss Distribution</div>
            <div class="chart-container">
                <canvas id="tradeDistributionChart"></canvas>
            </div>
        </div>

        <!-- Detailed Comparison Table -->
        <div style="padding: 40px;">
            <div class="chart-title">Detailed Metrics Comparison</div>
            <table class="comparison-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>Phase 1</th>
                        <th>Phase 3</th>
                        <th>Winner</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td><strong>Profitability</strong></td>
                        <td>${phase1_result.total_profit_loss:,.2f}</td>
                        <td>${phase3_result.total_profit_loss:,.2f}</td>
                        <td><span class="badge {'success' if phase3_result.total_profit_loss > phase1_result.total_profit_loss else 'danger'}">
                            {'Phase 3' if phase3_result.total_profit_loss > phase1_result.total_profit_loss else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Avg Profit/Trade</strong></td>
                        <td>${phase1_result.avg_profit_per_trade:,.2f}</td>
                        <td>${phase3_result.avg_profit_per_trade:,.2f}</td>
                        <td><span class="badge {'success' if phase3_result.avg_profit_per_trade > phase1_result.avg_profit_per_trade else 'danger'}">
                            {'Phase 3' if phase3_result.avg_profit_per_trade > phase1_result.avg_profit_per_trade else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Win Rate</strong></td>
                        <td>{phase1_result.win_rate:.2f}%</td>
                        <td>{phase3_result.win_rate:.2f}%</td>
                        <td><span class="badge {'success' if phase3_result.win_rate > phase1_result.win_rate else 'danger'}">
                            {'Phase 3' if phase3_result.win_rate > phase1_result.win_rate else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Profit Factor</strong></td>
                        <td>{phase1_result.profit_factor:.2f}</td>
                        <td>{phase3_result.profit_factor:.2f}</td>
                        <td><span class="badge {'success' if phase3_result.profit_factor > phase1_result.profit_factor else 'danger'}">
                            {'Phase 3' if phase3_result.profit_factor > phase1_result.profit_factor else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Max Drawdown</strong></td>
                        <td>{phase1_result.max_drawdown_pct:.2f}%</td>
                        <td>{phase3_result.max_drawdown_pct:.2f}%</td>
                        <td><span class="badge {'success' if phase3_result.max_drawdown_pct < phase1_result.max_drawdown_pct else 'danger'}">
                            {'Phase 3' if phase3_result.max_drawdown_pct < phase1_result.max_drawdown_pct else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Best Trade</strong></td>
                        <td>${phase1_result.best_trade:,.2f}</td>
                        <td>${phase3_result.best_trade:,.2f}</td>
                        <td><span class="badge {'success' if phase3_result.best_trade > phase1_result.best_trade else 'danger'}">
                            {'Phase 3' if phase3_result.best_trade > phase1_result.best_trade else 'Phase 1'}
                        </span></td>
                    </tr>
                    <tr>
                        <td><strong>Worst Trade</strong></td>
                        <td>${phase1_result.worst_trade:,.2f}</td>
                        <td>${phase3_result.worst_trade:,.2f}</td>
                        <td><span class="badge {'success' if phase3_result.worst_trade > phase1_result.worst_trade else 'danger'}">
                            {'Phase 3' if phase3_result.worst_trade > phase1_result.worst_trade else 'Phase 1'}
                        </span></td>
                    </tr>
                </tbody>
            </table>
        </div>

        <!-- Footer -->
        <div class="footer">
            <p>Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <p style="margin-top: 10px; opacity: 0.8;">Crypto Trading Bot - Backtest Comparison Report</p>
        </div>
    </div>

    <script>
        // Equity Curve Chart
        const equityCtx = document.getElementById('equityChart').getContext('2d');
        new Chart(equityCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(equity_data['labels'])},
                datasets: [
                    {{
                        label: 'Phase 1 (TA Only)',
                        data: {json.dumps(equity_data['phase1'])},
                        borderColor: 'rgb(231, 76, 60)',
                        backgroundColor: 'rgba(231, 76, 60, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }},
                    {{
                        label: 'Phase 3 (AI Enhanced)',
                        data: {json.dumps(equity_data['phase3'])},
                        borderColor: 'rgb(46, 204, 113)',
                        backgroundColor: 'rgba(46, 204, 113, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top',
                    }},
                    tooltip: {{
                        mode: 'index',
                        intersect: false,
                        callbacks: {{
                            label: function(context) {{
                                let label = context.dataset.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += '$' + context.parsed.y.toFixed(2);
                                return label;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: false,
                        ticks: {{
                            callback: function(value) {{
                                return '$' + value.toFixed(0);
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // Drawdown Chart
        const drawdownCtx = document.getElementById('drawdownChart').getContext('2d');
        new Chart(drawdownCtx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(drawdown_data['labels'])},
                datasets: [
                    {{
                        label: 'Phase 1 Drawdown',
                        data: {json.dumps(drawdown_data['phase1'])},
                        borderColor: 'rgb(231, 76, 60)',
                        backgroundColor: 'rgba(231, 76, 60, 0.2)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }},
                    {{
                        label: 'Phase 3 Drawdown',
                        data: {json.dumps(drawdown_data['phase3'])},
                        borderColor: 'rgb(46, 204, 113)',
                        backgroundColor: 'rgba(46, 204, 113, 0.2)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top',
                    }},
                    tooltip: {{
                        mode: 'index',
                        intersect: false,
                        callbacks: {{
                            label: function(context) {{
                                let label = context.dataset.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += context.parsed.y.toFixed(2) + '%';
                                return label;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        reverse: true,
                        ticks: {{
                            callback: function(value) {{
                                return value.toFixed(1) + '%';
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // Monthly Returns Chart
        const monthlyCtx = document.getElementById('monthlyReturnsChart').getContext('2d');
        new Chart(monthlyCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(monthly_data['labels'])},
                datasets: [
                    {{
                        label: 'Phase 1',
                        data: {json.dumps(monthly_data['phase1'])},
                        backgroundColor: 'rgba(231, 76, 60, 0.7)',
                        borderColor: 'rgb(231, 76, 60)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Phase 3',
                        data: {json.dumps(monthly_data['phase3'])},
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',
                        borderColor: 'rgb(46, 204, 113)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top',
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                let label = context.dataset.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += context.parsed.y.toFixed(2) + '%';
                                return label;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        ticks: {{
                            callback: function(value) {{
                                return value.toFixed(1) + '%';
                            }}
                        }}
                    }}
                }}
            }}
        }});

        // Trade Distribution Chart
        const distCtx = document.getElementById('tradeDistributionChart').getContext('2d');
        new Chart(distCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(trade_distribution['labels'])},
                datasets: [
                    {{
                        label: 'Phase 1',
                        data: {json.dumps(trade_distribution['phase1'])},
                        backgroundColor: 'rgba(231, 76, 60, 0.7)',
                        borderColor: 'rgb(231, 76, 60)',
                        borderWidth: 1
                    }},
                    {{
                        label: 'Phase 3',
                        data: {json.dumps(trade_distribution['phase3'])},
                        backgroundColor: 'rgba(46, 204, 113, 0.7)',
                        borderColor: 'rgb(46, 204, 113)',
                        borderWidth: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        display: true,
                        position: 'top',
                    }},
                    tooltip: {{
                        callbacks: {{
                            label: function(context) {{
                                let label = context.dataset.label || '';
                                if (label) {{
                                    label += ': ';
                                }}
                                label += context.parsed.y + ' trades';
                                return label;
                            }}
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        beginAtZero: true,
                        ticks: {{
                            stepSize: 1
                        }}
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>"""

        return html

    @staticmethod
    def _prepare_equity_data(phase1_result, phase3_result) -> Dict:
        """Prepare equity curve data for charting"""
        # Normalize equity curves to same length
        max_len = max(len(phase1_result.equity_curve), len(phase3_result.equity_curve))

        # Create labels (time indices)
        labels = list(range(max_len))

        # Pad shorter curve with last value
        phase1_equity = phase1_result.equity_curve.copy()
        phase3_equity = phase3_result.equity_curve.copy()

        if len(phase1_equity) < max_len:
            phase1_equity.extend([phase1_equity[-1]] * (max_len - len(phase1_equity)))

        if len(phase3_equity) < max_len:
            phase3_equity.extend([phase3_equity[-1]] * (max_len - len(phase3_equity)))

        return {
            'labels': labels,
            'phase1': [float(x) for x in phase1_equity],
            'phase3': [float(x) for x in phase3_equity]
        }

    @staticmethod
    def _prepare_drawdown_data(phase1_result, phase3_result) -> Dict:
        """Prepare drawdown data for charting"""
        def calculate_drawdown_series(equity_curve):
            """Calculate drawdown at each point"""
            drawdowns = []
            peak = equity_curve[0]
            for value in equity_curve:
                if value > peak:
                    peak = value
                dd = ((peak - value) / peak * 100) if peak > 0 else 0
                drawdowns.append(dd)
            return drawdowns

        phase1_dd = calculate_drawdown_series(phase1_result.equity_curve)
        phase3_dd = calculate_drawdown_series(phase3_result.equity_curve)

        # Normalize lengths
        max_len = max(len(phase1_dd), len(phase3_dd))
        labels = list(range(max_len))

        if len(phase1_dd) < max_len:
            phase1_dd.extend([phase1_dd[-1]] * (max_len - len(phase1_dd)))

        if len(phase3_dd) < max_len:
            phase3_dd.extend([phase3_dd[-1]] * (max_len - len(phase3_dd)))

        return {
            'labels': labels,
            'phase1': [float(x) for x in phase1_dd],
            'phase3': [float(x) for x in phase3_dd]
        }

    @staticmethod
    def _prepare_monthly_data(phase1_result, phase3_result) -> Dict:
        """Prepare monthly returns data"""
        def get_monthly_returns(trades):
            """Calculate returns by month"""
            monthly = {}
            for trade in trades:
                month_key = trade.entry_time.strftime('%Y-%m')
                if month_key not in monthly:
                    monthly[month_key] = []
                monthly[month_key].append(trade.profit_loss)

            # Calculate percentage returns
            returns = {}
            for month, profits in monthly.items():
                total_profit = sum(profits)
                # Assume initial capital (simplified)
                returns[month] = (total_profit / phase1_result.initial_capital) * 100

            return returns

        phase1_monthly = get_monthly_returns(phase1_result.trades)
        phase3_monthly = get_monthly_returns(phase3_result.trades)

        # Get all unique months
        all_months = sorted(set(list(phase1_monthly.keys()) + list(phase3_monthly.keys())))

        return {
            'labels': all_months,
            'phase1': [float(phase1_monthly.get(m, 0)) for m in all_months],
            'phase3': [float(phase3_monthly.get(m, 0)) for m in all_months]
        }

    @staticmethod
    def _prepare_trade_distribution(phase1_result, phase3_result) -> Dict:
        """Prepare profit/loss distribution data"""
        def get_distribution(trades):
            """Categorize trades by profit/loss"""
            bins = {
                'Loss > -5%': 0,
                '-5% to -2%': 0,
                '-2% to 0%': 0,
                '0% to 2%': 0,
                '2% to 5%': 0,
                'Profit > 5%': 0
            }

            for trade in trades:
                pct = trade.profit_loss_pct
                if pct < -5:
                    bins['Loss > -5%'] += 1
                elif pct < -2:
                    bins['-5% to -2%'] += 1
                elif pct < 0:
                    bins['-2% to 0%'] += 1
                elif pct < 2:
                    bins['0% to 2%'] += 1
                elif pct < 5:
                    bins['2% to 5%'] += 1
                else:
                    bins['Profit > 5%'] += 1

            return bins

        phase1_dist = get_distribution(phase1_result.trades)
        phase3_dist = get_distribution(phase3_result.trades)

        labels = list(phase1_dist.keys())

        return {
            'labels': labels,
            'phase1': [phase1_dist[label] for label in labels],
            'phase3': [phase3_dist[label] for label in labels]
        }

    @staticmethod
    def _calculate_summary_stats(result) -> Dict:
        """Calculate summary statistics"""
        return {
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'total_return': result.total_profit_loss_pct,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown_pct,
            'profit_factor': result.profit_factor
        }


if __name__ == "__main__":
    print("Backtest Visualization Module")
    print("This module provides HTML report generation for backtest comparisons")
    print("Usage: Import BacktestVisualizer and call generate_html_report()")
