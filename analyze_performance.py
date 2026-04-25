#!/usr/bin/env python3
"""
Performance Analysis Script - LONG vs SHORT positions
Analyzes trading performance by position direction
"""

import asyncio
import asyncpg

async def analyze_performance():
    # Connect to database using container environment
    conn = await asyncpg.connect(
        host='crypto-bot-postgres',
        port=5432,
        database='cryptobot',
        user='cryptobot',
        password='cryptobot_dev_password'
    )

    # Get all closed positions grouped by side
    query = '''
    SELECT
        side,
        COUNT(*) as total_trades,
        SUM(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
        SUM(CASE WHEN realized_pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
        SUM(CASE WHEN realized_pnl = 0 THEN 1 ELSE 0 END) as breakeven_trades,
        SUM(realized_pnl) as total_pnl,
        AVG(realized_pnl) as avg_pnl,
        MAX(realized_pnl) as best_trade,
        MIN(realized_pnl) as worst_trade,
        AVG(CASE WHEN realized_pnl > 0 THEN realized_pnl ELSE NULL END) as avg_win,
        AVG(CASE WHEN realized_pnl < 0 THEN realized_pnl ELSE NULL END) as avg_loss
    FROM positions
    WHERE status = 'CLOSED'
    GROUP BY side
    ORDER BY side
    '''

    results = await conn.fetch(query)

    print('=' * 80)
    print('LONG vs SHORT POSITION PERFORMANCE ANALYSIS')
    print('=' * 80)
    print()

    total_long_pnl = 0
    total_short_pnl = 0
    long_data = None
    short_data = None

    for row in results:
        side = row['side']
        total = row['total_trades']
        wins = row['winning_trades']
        losses = row['losing_trades']
        breakeven = row['breakeven_trades']
        total_pnl = float(row['total_pnl'] or 0)
        avg_pnl = float(row['avg_pnl'] or 0)
        best = float(row['best_trade'] or 0)
        worst = float(row['worst_trade'] or 0)
        avg_win = float(row['avg_win'] or 0) if row['avg_win'] else 0
        avg_loss = float(row['avg_loss'] or 0) if row['avg_loss'] else 0

        if side == 'LONG':
            total_long_pnl = total_pnl
            long_data = (total, wins, losses)
        else:
            total_short_pnl = total_pnl
            short_data = (total, wins, losses)

        win_rate = (wins / total * 100) if total > 0 else 0
        profit_factor = abs(wins * avg_win / (losses * avg_loss)) if (losses > 0 and avg_loss != 0) else 0

        print(f'📊 {side} POSITIONS:')
        print(f'  Total Trades: {total}')
        print(f'  Winning: {wins} ({win_rate:.1f}%)')
        print(f'  Losing: {losses} ({(losses/total*100) if total > 0 else 0:.1f}%)')
        print(f'  Breakeven: {breakeven}')
        print(f'  Total P&L: ${total_pnl:.2f}')
        print(f'  Average P&L: ${avg_pnl:.2f}')
        print(f'  Best Trade: ${best:.2f}')
        print(f'  Worst Trade: ${worst:.2f}')
        print(f'  Average Win: ${avg_win:.2f}')
        print(f'  Average Loss: ${avg_loss:.2f}')
        print(f'  Profit Factor: {profit_factor:.2f}')
        print()

    # Get open positions
    open_query = '''
    SELECT side, symbol, entry_price, current_price, quantity, unrealized_pnl
    FROM positions
    WHERE status = 'OPEN'
    ORDER BY side, symbol
    '''

    open_positions = await conn.fetch(open_query)

    print('=' * 80)
    print('CURRENT OPEN POSITIONS')
    print('=' * 80)
    print()

    if open_positions:
        long_unrealized = 0
        short_unrealized = 0
        long_count = 0
        short_count = 0

        for pos in open_positions:
            unrealized = float(pos['unrealized_pnl'] or 0)
            if pos['side'] == 'LONG':
                long_unrealized += unrealized
                long_count += 1
            else:
                short_unrealized += unrealized
                short_count += 1

            entry = float(pos['entry_price'])
            current = float(pos['current_price']) if pos['current_price'] else entry
            print(f'{pos["side"]:5} {pos["symbol"]:10} Entry: ${entry:,.2f} Current: ${current:,.2f} P&L: ${unrealized:>8.2f}')

        print()
        print(f'Total Unrealized LONG P&L:  ${long_unrealized:>10.2f} ({long_count} positions)')
        print(f'Total Unrealized SHORT P&L: ${short_unrealized:>10.2f} ({short_count} positions)')
        print()
    else:
        print('No open positions')
        print()
        long_unrealized = 0
        short_unrealized = 0

    # Summary
    print('=' * 80)
    print('OVERALL SUMMARY')
    print('=' * 80)
    print()
    print(f'LONG Positions:')
    print(f'  Realized P&L:   ${total_long_pnl:>10.2f}')
    print(f'  Unrealized P&L: ${long_unrealized:>10.2f}')
    print(f'  Total P&L:      ${total_long_pnl + long_unrealized:>10.2f}')
    print()
    print(f'SHORT Positions:')
    print(f'  Realized P&L:   ${total_short_pnl:>10.2f}')
    print(f'  Unrealized P&L: ${short_unrealized:>10.2f}')
    print(f'  Total P&L:      ${total_short_pnl + short_unrealized:>10.2f}')
    print()
    print(f'Grand Total P&L:  ${total_long_pnl + total_short_pnl + long_unrealized + short_unrealized:>10.2f}')
    print()

    # Comparison
    if long_data and short_data:
        print('=' * 80)
        print('LONG vs SHORT COMPARISON')
        print('=' * 80)
        print()

        long_total, long_wins, long_losses = long_data
        short_total, short_wins, short_losses = short_data

        long_win_rate = (long_wins / long_total * 100) if long_total > 0 else 0
        short_win_rate = (short_wins / short_total * 100) if short_total > 0 else 0

        long_avg = total_long_pnl / long_total if long_total > 0 else 0
        short_avg = total_short_pnl / short_total if short_total > 0 else 0

        print(f'Win Rate:      LONG {long_win_rate:>5.1f}% vs SHORT {short_win_rate:>5.1f}%')
        print(f'Avg P&L:       LONG ${long_avg:>7.2f} vs SHORT ${short_avg:>7.2f}')
        print(f'Total Trades:  LONG {long_total:>5} vs SHORT {short_total:>5}')
        print(f'Total P&L:     LONG ${total_long_pnl:>8.2f} vs SHORT ${total_short_pnl:>8.2f}')
        print()

        if total_long_pnl > total_short_pnl:
            print('🏆 LONG positions are outperforming SHORT positions')
        elif total_short_pnl > total_long_pnl:
            print('🏆 SHORT positions are outperforming LONG positions')
        else:
            print('📊 LONG and SHORT positions are performing equally')

    await conn.close()

if __name__ == '__main__':
    asyncio.run(analyze_performance())
