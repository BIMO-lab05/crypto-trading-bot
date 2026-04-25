#!/usr/bin/env python3
"""
Entry Signal Analysis - Compare LONG vs SHORT entry quality
Analyzes entry signals to understand performance differences
"""

import asyncio
import asyncpg

async def analyze_entry_signals():
    conn = await asyncpg.connect(
        host='crypto-bot-postgres',
        port=5432,
        database='cryptobot',
        user='cryptobot',
        password='cryptobot_dev_password'
    )

    # Analyze entry signal confidence for LONG vs SHORT
    query = '''
    SELECT
        side,
        COUNT(*) as total_positions,
        AVG(entry_signal_confidence) as avg_entry_confidence,
        MIN(entry_signal_confidence) as min_confidence,
        MAX(entry_signal_confidence) as max_confidence,
        AVG(CASE WHEN realized_pnl > 0 THEN entry_signal_confidence ELSE NULL END) as avg_winning_confidence,
        AVG(CASE WHEN realized_pnl < 0 THEN entry_signal_confidence ELSE NULL END) as avg_losing_confidence,
        AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE NULL END) as avg_win_amount,
        AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE NULL END) as avg_loss_amount
    FROM positions
    WHERE status = 'CLOSED'
    GROUP BY side
    ORDER BY side
    '''

    results = await conn.fetch(query)

    print('=' * 80)
    print('ENTRY SIGNAL QUALITY ANALYSIS')
    print('=' * 80)
    print()

    for row in results:
        side = row['side']
        total = row['total_positions']
        avg_conf = float(row['avg_entry_confidence'] or 0)
        min_conf = float(row['min_confidence'] or 0)
        max_conf = float(row['max_confidence'] or 0)
        win_conf = float(row['avg_winning_confidence'] or 0) if row['avg_winning_confidence'] else 0
        loss_conf = float(row['avg_losing_confidence'] or 0) if row['avg_losing_confidence'] else 0
        avg_win = float(row['avg_win_amount'] or 0) if row['avg_win_amount'] else 0
        avg_loss = float(row['avg_loss_amount'] or 0) if row['avg_loss_amount'] else 0

        print(f'📊 {side} POSITIONS:')
        print(f'  Total Positions: {total}')
        print(f'  Average Entry Confidence: {avg_conf:.4f}')
        print(f'  Confidence Range: {min_conf:.4f} - {max_conf:.4f}')
        print(f'  Avg Winning Signal Confidence: {win_conf:.4f}')
        print(f'  Avg Losing Signal Confidence: {loss_conf:.4f}')
        print(f'  Confidence Difference: {win_conf - loss_conf:.4f}')
        print(f'  Avg Win Amount: ${avg_win:.2f}')
        print(f'  Avg Loss Amount: ${avg_loss:.2f}')
        print()

        # Analysis
        if win_conf > loss_conf:
            print(f'  ✅ Winning {side} trades had HIGHER confidence ({win_conf:.4f} vs {loss_conf:.4f})')
            print(f'     → Signal confidence is a good predictor for {side} positions')
        else:
            print(f'  ⚠️ Winning {side} trades had LOWER confidence ({win_conf:.4f} vs {loss_conf:.4f})')
            print(f'     → Signal confidence may NOT be reliable for {side} positions')
        print()

    # Check distribution of entries by confidence level
    print('=' * 80)
    print('CONFIDENCE LEVEL DISTRIBUTION')
    print('=' * 80)
    print()

    dist_query = '''
    SELECT
        side,
        CASE
            WHEN entry_signal_confidence >= 0.70 THEN 'High (>=0.70)'
            WHEN entry_signal_confidence >= 0.60 THEN 'Medium-High (0.60-0.69)'
            WHEN entry_signal_confidence >= 0.55 THEN 'Medium (0.55-0.59)'
            ELSE 'Low (<0.55)'
        END as confidence_level,
        COUNT(*) as count,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losses,
        SUM(realized_pnl) as total_pnl
    FROM positions
    WHERE status = 'CLOSED'
    GROUP BY side, confidence_level
    ORDER BY side, confidence_level
    '''

    dist_results = await conn.fetch(dist_query)

    current_side = None
    for row in dist_results:
        if row['side'] != current_side:
            current_side = row['side']
            print(f'\n{current_side} POSITIONS:')
            print(f'{"Confidence Level":<25} {"Count":<8} {"Wins":<8} {"Losses":<8} {"Win Rate":<12} {"Total P&L":<12}')
            print('-' * 80)

        level = row['confidence_level']
        count = row['count']
        wins = row['wins']
        losses = row['losses']
        pnl = float(row['total_pnl'] or 0)
        win_rate = (wins / count * 100) if count > 0 else 0

        print(f'{level:<25} {count:<8} {wins:<8} {losses:<8} {win_rate:<11.1f}% ${pnl:<11.2f}')

    # Check strategy distribution
    print('\n' + '=' * 80)
    print('STRATEGY DISTRIBUTION')
    print('=' * 80)
    print()

    strategy_query = '''
    SELECT
        side,
        strategy,
        COUNT(*) as count,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(realized_pnl) as total_pnl,
        AVG(entry_signal_confidence) as avg_confidence
    FROM positions
    WHERE status = 'CLOSED'
    GROUP BY side, strategy
    ORDER BY side, count DESC
    '''

    strategy_results = await conn.fetch(strategy_query)

    current_side = None
    for row in strategy_results:
        if row['side'] != current_side:
            current_side = row['side']
            print(f'\n{current_side} POSITIONS:')
            print(f'{"Strategy":<30} {"Count":<8} {"Wins":<8} {"Win Rate":<12} {"Avg Conf":<12} {"Total P&L":<12}')
            print('-' * 80)

        strategy = row['strategy'] or 'unknown'
        count = row['count']
        wins = row['wins']
        pnl = float(row['total_pnl'] or 0)
        avg_conf = float(row['avg_confidence'] or 0)
        win_rate = (wins / count * 100) if count > 0 else 0

        print(f'{strategy:<30} {count:<8} {wins:<8} {win_rate:<11.1f}% {avg_conf:<11.4f} ${pnl:<11.2f}')

    # Check symbol performance by side
    print('\n' + '=' * 80)
    print('SYMBOL PERFORMANCE BY SIDE')
    print('=' * 80)
    print()

    symbol_query = '''
    SELECT
        side,
        symbol,
        COUNT(*) as count,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as wins,
        SUM(realized_pnl) as total_pnl,
        AVG(entry_signal_confidence) as avg_confidence
    FROM positions
    WHERE status = 'CLOSED'
    GROUP BY side, symbol
    HAVING COUNT(*) >= 3
    ORDER BY side, total_pnl DESC
    '''

    symbol_results = await conn.fetch(symbol_query)

    current_side = None
    for row in symbol_results:
        if row['side'] != current_side:
            current_side = row['side']
            print(f'\n{current_side} POSITIONS (min 3 trades):')
            print(f'{"Symbol":<15} {"Count":<8} {"Wins":<8} {"Win Rate":<12} {"Avg Conf":<12} {"Total P&L":<12}')
            print('-' * 80)

        symbol = row['symbol']
        count = row['count']
        wins = row['wins']
        pnl = float(row['total_pnl'] or 0)
        avg_conf = float(row['avg_confidence'] or 0)
        win_rate = (wins / count * 100) if count > 0 else 0

        print(f'{symbol:<15} {count:<8} {wins:<8} {win_rate:<11.1f}% {avg_conf:<11.4f} ${pnl:<11.2f}')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(analyze_entry_signals())
