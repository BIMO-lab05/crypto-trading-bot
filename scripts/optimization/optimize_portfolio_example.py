#!/usr/bin/env python3
"""
Portfolio Optimization Example Script

Demonstrates how to use the portfolio optimization API endpoints to:
1. Optimize portfolio allocation
2. Generate efficient frontier
3. Execute rebalancing

Usage:
    python optimize_portfolio_example.py
"""

import asyncio
import httpx
import json
from typing import Dict, List
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime


# Configuration
PORTFOLIO_MANAGER_URL = "http://localhost:8003"
PORTFOLIO_ID = "default"


async def optimize_for_max_sharpe() -> Dict:
    """
    Optimize portfolio for maximum Sharpe ratio

    Returns:
        Optimization result dictionary
    """
    print("\n" + "="*60)
    print("OPTIMIZING PORTFOLIO FOR MAXIMUM SHARPE RATIO")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{PORTFOLIO_MANAGER_URL}/api/v1/portfolio/optimize",
            params={
                "portfolio_id": PORTFOLIO_ID,
                "objective": "max_sharpe",
                "lookback_days": 90,
                "max_position_size": 0.40,  # Max 40% per position
                "min_position_size": 0.10,  # Min 10% per position
            }
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return {}

        result = response.json()

        # Display results
        opt_result = result['optimization_result']

        print(f"\nOptimization Time: {result['optimization_time']}")
        print(f"Constraints Met: {result['constraints_met']}")

        print("\n--- Optimal Allocation ---")
        for symbol, weight in opt_result['weights'].items():
            print(f"  {symbol:12s}: {weight:6.2%}")

        print("\n--- Performance Metrics ---")
        print(f"  Expected Return:    {float(opt_result['expected_return']):8.2%}")
        print(f"  Expected Volatility: {float(opt_result['expected_volatility']):8.2%}")
        print(f"  Sharpe Ratio:       {float(opt_result['sharpe_ratio']):8.4f}")

        if opt_result['value_at_risk_95']:
            print(f"  Value at Risk (95%): {float(opt_result['value_at_risk_95']):8.2%}")

        if opt_result['diversification_ratio']:
            print(f"  Diversification Ratio: {float(opt_result['diversification_ratio']):6.4f}")

        if opt_result['effective_num_assets']:
            print(f"  Effective # Assets: {float(opt_result['effective_num_assets']):8.2f}")

        # Display rebalancing trades
        if result['rebalancing_trades']:
            print("\n--- Required Rebalancing Trades ---")
            for trade in result['rebalancing_trades']:
                print(f"  {trade['action']:4s} {trade['symbol']:12s}: ${float(trade['amount_usd']):10.2f}")

        return result


async def generate_efficient_frontier() -> List[Dict]:
    """
    Generate efficient frontier points

    Returns:
        List of frontier points
    """
    print("\n" + "="*60)
    print("GENERATING EFFICIENT FRONTIER")
    print("="*60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            f"{PORTFOLIO_MANAGER_URL}/api/v1/portfolio/efficient-frontier",
            params={
                "portfolio_id": PORTFOLIO_ID,
                "num_points": 30,
                "lookback_days": 90
            }
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return []

        result = response.json()

        print(f"\nGenerated {result['num_points']} efficient frontier points")

        # Extract data for plotting
        points = result['frontier_points']

        # Create DataFrame for easier analysis
        df = pd.DataFrame([
            {
                'return': float(p['expected_return']),
                'volatility': float(p['expected_volatility']),
                'sharpe': float(p['sharpe_ratio']),
            }
            for p in points
        ])

        print("\n--- Efficient Frontier Statistics ---")
        print(f"  Min Volatility: {df['volatility'].min():.4f}")
        print(f"  Max Return:     {df['return'].max():.4f}")
        print(f"  Max Sharpe:     {df['sharpe'].max():.4f}")

        # Plot efficient frontier
        plot_efficient_frontier(df, points)

        return points


def plot_efficient_frontier(df: pd.DataFrame, points: List[Dict]):
    """
    Plot efficient frontier

    Args:
        df: DataFrame with frontier statistics
        points: List of frontier point dictionaries
    """
    plt.figure(figsize=(12, 8))

    # Plot frontier curve
    plt.plot(
        df['volatility'],
        df['return'],
        'b-',
        linewidth=2,
        label='Efficient Frontier'
    )

    # Highlight max Sharpe ratio point
    max_sharpe_idx = df['sharpe'].idxmax()
    plt.scatter(
        df.loc[max_sharpe_idx, 'volatility'],
        df.loc[max_sharpe_idx, 'return'],
        color='red',
        s=200,
        marker='*',
        label=f"Max Sharpe ({df.loc[max_sharpe_idx, 'sharpe']:.4f})",
        zorder=5
    )

    # Highlight min volatility point
    min_vol_idx = df['volatility'].idxmin()
    plt.scatter(
        df.loc[min_vol_idx, 'volatility'],
        df.loc[min_vol_idx, 'return'],
        color='green',
        s=200,
        marker='o',
        label='Min Volatility',
        zorder=5
    )

    plt.xlabel('Expected Volatility (Risk)', fontsize=12)
    plt.ylabel('Expected Return', fontsize=12)
    plt.title('Efficient Frontier - Crypto Portfolio', fontsize=14, fontweight='bold')
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)

    # Format axes as percentages
    ax = plt.gca()
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1%}'))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'{x:.1%}'))

    # Save plot
    plt.tight_layout()
    plt.savefig('efficient_frontier.png', dpi=300)
    print("\nPlot saved as 'efficient_frontier.png'")

    plt.show()


async def compare_optimization_strategies() -> None:
    """
    Compare different optimization strategies
    """
    print("\n" + "="*60)
    print("COMPARING OPTIMIZATION STRATEGIES")
    print("="*60)

    strategies = [
        "max_sharpe",
        "min_volatility",
        "risk_parity",
        "max_diversification"
    ]

    results = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for strategy in strategies:
            print(f"\nOptimizing for: {strategy}")

            response = await client.post(
                f"{PORTFOLIO_MANAGER_URL}/api/v1/portfolio/optimize",
                params={
                    "portfolio_id": PORTFOLIO_ID,
                    "objective": strategy,
                    "lookback_days": 60
                }
            )

            if response.status_code == 200:
                result = response.json()
                results[strategy] = result['optimization_result']
            else:
                print(f"  Error: {response.status_code}")

    # Create comparison table
    if results:
        comparison_data = []

        for strategy, result in results.items():
            comparison_data.append({
                'Strategy': strategy,
                'Return': float(result['expected_return']),
                'Volatility': float(result['expected_volatility']),
                'Sharpe': float(result['sharpe_ratio'])
            })

        df = pd.DataFrame(comparison_data)
        df = df.set_index('Strategy')

        print("\n--- Strategy Comparison ---")
        print(df.to_string())

        # Plot comparison
        plot_strategy_comparison(df)


def plot_strategy_comparison(df: pd.DataFrame):
    """
    Plot strategy comparison

    Args:
        df: DataFrame with strategy comparison data
    """
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    # Plot returns
    df['Return'].plot(kind='bar', ax=axes[0], color='green', alpha=0.7)
    axes[0].set_title('Expected Returns')
    axes[0].set_ylabel('Annual Return')
    axes[0].yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1%}'))
    axes[0].grid(True, alpha=0.3)

    # Plot volatility
    df['Volatility'].plot(kind='bar', ax=axes[1], color='red', alpha=0.7)
    axes[1].set_title('Expected Volatility')
    axes[1].set_ylabel('Annual Volatility')
    axes[1].yaxis.set_major_formatter(plt.FuncFormatter(lambda y, _: f'{y:.1%}'))
    axes[1].grid(True, alpha=0.3)

    # Plot Sharpe ratio
    df['Sharpe'].plot(kind='bar', ax=axes[2], color='blue', alpha=0.7)
    axes[2].set_title('Sharpe Ratio')
    axes[2].set_ylabel('Sharpe Ratio')
    axes[2].grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('strategy_comparison.png', dpi=300)
    print("\nComparison plot saved as 'strategy_comparison.png'")

    plt.show()


async def execute_rebalancing(target_weights: Dict[str, float], execute: bool = False) -> None:
    """
    Execute or simulate portfolio rebalancing

    Args:
        target_weights: Dictionary of target weights {symbol: weight}
        execute: Whether to actually execute trades (default: False for dry run)
    """
    print("\n" + "="*60)
    print(f"{'EXECUTING' if execute else 'SIMULATING'} PORTFOLIO REBALANCING")
    print("="*60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{PORTFOLIO_MANAGER_URL}/api/v1/portfolio/rebalance",
            params={"execute": execute},
            json={"target_weights": target_weights}
        )

        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            print(response.text)
            return

        result = response.json()

        print(f"\nPortfolio ID: {result['portfolio_id']}")
        print(f"Executed: {result['executed']}")

        print("\n--- Current vs Target Allocation ---")
        current = result['current_weights']
        target = result['target_weights']

        for symbol in target.keys():
            current_weight = current.get(symbol, 0.0)
            target_weight = target[symbol]
            drift = (target_weight - current_weight) * 100

            print(f"  {symbol:12s}: {current_weight:6.2%} -> {target_weight:6.2%} (drift: {drift:+6.2f}%)")

        print(f"\n--- {'Executed' if execute else 'Planned'} Trades ---")
        for trade in result['trades']:
            print(f"  {trade['action']:4s} {trade['symbol']:12s}: ${float(trade['amount_usd']):10.2f}")

        if execute and result.get('executed_trades'):
            print("\n--- Execution Results ---")
            for trade in result['executed_trades']:
                status = "SUCCESS" if trade['success'] else "FAILED"
                print(f"  [{status}] {trade['action']} {trade['symbol']}: {trade['message']}")


async def main():
    """
    Main execution function
    """
    print("\n" + "="*80)
    print(" " * 20 + "PORTFOLIO OPTIMIZATION EXAMPLE")
    print("="*80)
    print(f"\nTimestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Portfolio Manager URL: {PORTFOLIO_MANAGER_URL}")
    print(f"Portfolio ID: {PORTFOLIO_ID}")

    try:
        # 1. Optimize for maximum Sharpe ratio
        sharpe_result = await optimize_for_max_sharpe()

        # 2. Generate efficient frontier
        frontier_points = await generate_efficient_frontier()

        # 3. Compare different strategies
        await compare_optimization_strategies()

        # 4. Simulate rebalancing (dry run)
        if sharpe_result and 'optimization_result' in sharpe_result:
            optimal_weights = sharpe_result['optimization_result']['weights']
            await execute_rebalancing(optimal_weights, execute=False)

        print("\n" + "="*80)
        print(" " * 20 + "OPTIMIZATION COMPLETE")
        print("="*80)

    except Exception as e:
        print(f"\nError occurred: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
