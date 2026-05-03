#!/usr/bin/env python3
"""
Script to Close Positions in Excluded Symbols
Purpose: Close all open positions for symbols no longer in the active trading strategy
Author: Backend Developer
Date: 2025-12-13

Context:
- Config specifies ONLY 3 active symbols: SOLUSDT, BNBUSDT, ADAUSDT
- Database has 11 open positions, including 8 in excluded symbols
- This script will close positions in excluded symbols and update the database
"""

import asyncio
import asyncpg
import httpx
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional
from decimal import Decimal

# =============================================================================
# CONFIGURATION
# =============================================================================

# Active symbols from config.py (as of 2025-12-10)
ACTIVE_SYMBOLS = ["SOLUSDT", "BNBUSDT", "ADAUSDT"]

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5433,
    "database": "cryptobot",
    "user": "cryptobot",
    "password": "cryptobot_secure_2024"
}

# API endpoints
PORTFOLIO_MANAGER_URL = "http://localhost:8003"
MARKET_DATA_URL = "http://localhost:8002"

# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

async def get_open_positions_to_close(conn: asyncpg.Connection) -> List[Dict]:
    """
    Query database for all open positions in excluded symbols

    Args:
        conn: Database connection

    Returns:
        List of position records to close
    """
    query = """
        SELECT
            position_id,
            symbol,
            side,
            quantity,
            entry_price,
            opened_at,
            stop_loss,
            take_profit
        FROM positions
        WHERE status = 'OPEN'
        AND symbol NOT IN ($1, $2, $3)
        ORDER BY opened_at ASC
    """

    rows = await conn.fetch(query, *ACTIVE_SYMBOLS)

    positions = []
    for row in rows:
        positions.append({
            "position_id": str(row["position_id"]),
            "symbol": row["symbol"],
            "side": row["side"],
            "quantity": float(row["quantity"]),
            "entry_price": float(row["entry_price"]),
            "opened_at": row["opened_at"],
            "stop_loss": float(row["stop_loss"]) if row["stop_loss"] else None,
            "take_profit": float(row["take_profit"]) if row["take_profit"] else None,
        })

    return positions


async def update_position_as_closed(
    conn: asyncpg.Connection,
    position_id: str,
    exit_price: float,
    realized_pnl: float,
    exit_reason: str = "EXCLUDED_SYMBOL"
) -> None:
    """
    Update position status to CLOSED in database

    Args:
        conn: Database connection
        position_id: UUID of position to close
        exit_price: Price at which position was closed
        realized_pnl: Realized profit/loss
        exit_reason: Reason for closing (default: EXCLUDED_SYMBOL)
    """
    query = """
        UPDATE positions
        SET
            status = 'CLOSED',
            closed_at = $1,
            exit_price = $2,
            realized_pnl = $3,
            exit_reason = $4
        WHERE position_id = $5
    """

    await conn.execute(
        query,
        datetime.now(timezone.utc),
        Decimal(str(exit_price)),
        Decimal(str(realized_pnl)),
        exit_reason,
        position_id
    )


# =============================================================================
# PRICE FETCHING
# =============================================================================

async def get_current_price(client: httpx.AsyncClient, symbol: str) -> Optional[float]:
    """
    Get current market price for symbol from Market Data Service

    Args:
        client: HTTP client
        symbol: Trading symbol (e.g., BTCUSDT)

    Returns:
        Current price or None if unavailable
    """
    try:
        response = await client.get(
            f"{MARKET_DATA_URL}/api/v1/ticker/{symbol}",
            timeout=5.0
        )

        if response.status_code == 200:
            data = response.json()
            return float(data.get("last_price", 0))
        else:
            print(f"  ⚠️  Failed to get price for {symbol}: HTTP {response.status_code}")
            return None

    except Exception as e:
        print(f"  ⚠️  Error fetching price for {symbol}: {e}")
        return None


# =============================================================================
# POSITION CLOSING
# =============================================================================

async def close_position_via_api(
    client: httpx.AsyncClient,
    position_id: str,
    symbol: str
) -> bool:
    """
    Attempt to close position via Portfolio Manager API

    Args:
        client: HTTP client
        position_id: UUID of position to close
        symbol: Trading symbol

    Returns:
        True if successful, False otherwise
    """
    try:
        response = await client.post(
            f"{PORTFOLIO_MANAGER_URL}/api/v1/positions/{position_id}/close",
            json={"reason": "EXCLUDED_SYMBOL"},
            timeout=10.0
        )

        if response.status_code == 200:
            return True
        else:
            print(f"  ⚠️  API close failed for {symbol}: HTTP {response.status_code}")
            return False

    except Exception as e:
        print(f"  ⚠️  API close error for {symbol}: {e}")
        return False


def calculate_pnl(
    side: str,
    entry_price: float,
    exit_price: float,
    quantity: float
) -> float:
    """
    Calculate realized PnL for a position

    Args:
        side: Position side (LONG or SHORT)
        entry_price: Entry price
        exit_price: Exit price
        quantity: Position quantity

    Returns:
        Realized PnL in USDT
    """
    if side == "LONG":
        # LONG: PnL = (exit_price - entry_price) * quantity
        pnl = (exit_price - entry_price) * quantity
    else:  # SHORT
        # SHORT: PnL = (entry_price - exit_price) * quantity
        pnl = (entry_price - exit_price) * quantity

    return round(pnl, 2)


# =============================================================================
# MAIN CLOSING LOGIC
# =============================================================================

async def close_excluded_positions():
    """
    Main function to close all positions in excluded symbols
    """
    print("\n" + "=" * 80)
    print("CLOSING POSITIONS IN EXCLUDED SYMBOLS")
    print("=" * 80)
    print(f"Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Active symbols: {', '.join(ACTIVE_SYMBOLS)}")
    print("=" * 80 + "\n")

    # Connect to database
    print("📊 Connecting to database...")
    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        # Get positions to close
        print("🔍 Querying open positions in excluded symbols...")
        positions_to_close = await get_open_positions_to_close(conn)

        if not positions_to_close:
            print("✅ No positions to close - all positions are in active symbols!")
            return

        print(f"Found {len(positions_to_close)} positions to close:\n")

        # Display positions to close
        for pos in positions_to_close:
            days_open = (datetime.now(timezone.utc) - pos["opened_at"].replace(tzinfo=timezone.utc)).days
            print(f"  • {pos['symbol']:12} {pos['side']:5} | "
                  f"Qty: {pos['quantity']:15.8f} | "
                  f"Entry: ${pos['entry_price']:10.2f} | "
                  f"Opened: {days_open} days ago")

        print("\n" + "-" * 80 + "\n")

        # Create HTTP client
        async with httpx.AsyncClient() as client:
            closed_count = 0
            total_pnl = 0.0
            results = []

            # Process each position
            for i, pos in enumerate(positions_to_close, 1):
                print(f"[{i}/{len(positions_to_close)}] Processing {pos['symbol']} {pos['side']}...")

                position_id = pos["position_id"]
                symbol = pos["symbol"]
                side = pos["side"]
                quantity = pos["quantity"]
                entry_price = pos["entry_price"]

                # Try to close via API first
                api_success = await close_position_via_api(client, position_id, symbol)

                if api_success:
                    print(f"  ✅ Closed via API")
                    closed_count += 1
                    results.append({
                        "symbol": symbol,
                        "side": side,
                        "method": "API",
                        "status": "success"
                    })
                    continue

                # If API fails, close manually via database
                print(f"  ⚙️  Closing manually via database...")

                # Get current price
                current_price = await get_current_price(client, symbol)

                if current_price is None:
                    # Use entry price as fallback
                    current_price = entry_price
                    print(f"  ⚠️  Using entry price as fallback: ${current_price:.2f}")
                else:
                    print(f"  💰 Current price: ${current_price:.2f}")

                # Calculate PnL
                pnl = calculate_pnl(side, entry_price, current_price, quantity)
                total_pnl += pnl

                print(f"  📊 Realized PnL: ${pnl:+.2f}")

                # Update database
                await update_position_as_closed(
                    conn,
                    position_id,
                    current_price,
                    pnl,
                    "EXCLUDED_SYMBOL_MANUAL_CLOSE"
                )

                closed_count += 1
                results.append({
                    "symbol": symbol,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": current_price,
                    "pnl": pnl,
                    "method": "DATABASE",
                    "status": "success"
                })

                print(f"  ✅ Position closed successfully\n")

            # Summary report
            print("=" * 80)
            print("CLOSING SUMMARY")
            print("=" * 80)
            print(f"Total positions closed: {closed_count}/{len(positions_to_close)}")
            print(f"Total realized PnL: ${total_pnl:+.2f}")
            print("\nClosed positions by symbol:")

            # Group by symbol
            symbol_summary = {}
            for result in results:
                symbol = result["symbol"]
                if symbol not in symbol_summary:
                    symbol_summary[symbol] = {"count": 0, "pnl": 0.0}
                symbol_summary[symbol]["count"] += 1
                symbol_summary[symbol]["pnl"] += result.get("pnl", 0.0)

            for symbol, data in sorted(symbol_summary.items()):
                print(f"  • {symbol:12} - {data['count']} position(s) | PnL: ${data['pnl']:+.2f}")

            print("\n" + "=" * 80)

            # Save detailed report
            report = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "active_symbols": ACTIVE_SYMBOLS,
                "total_closed": closed_count,
                "total_pnl": total_pnl,
                "positions": results
            }

            # Resolve report directory from this script's location (was hardcoded WSL path).
            from pathlib import Path as _Path
            _project_root = _Path(__file__).resolve().parent
            report_file = str(_project_root / f"closed_positions_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)

            print(f"\n📄 Detailed report saved to: {report_file}")

    finally:
        await conn.close()
        print("\n✅ Database connection closed")


# =============================================================================
# VERIFICATION
# =============================================================================

async def verify_remaining_positions():
    """
    Verify that only active symbols have open positions
    """
    print("\n" + "=" * 80)
    print("VERIFICATION: Remaining Open Positions")
    print("=" * 80 + "\n")

    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        query = """
            SELECT symbol, side, COUNT(*) as count
            FROM positions
            WHERE status = 'OPEN'
            GROUP BY symbol, side
            ORDER BY symbol
        """

        rows = await conn.fetch(query)

        if not rows:
            print("✅ No open positions remaining")
        else:
            print("Open positions by symbol:")
            for row in rows:
                status_icon = "✅" if row["symbol"] in ACTIVE_SYMBOLS else "⚠️ "
                print(f"  {status_icon} {row['symbol']:12} {row['side']:5} - {row['count']} position(s)")

            # Check for any excluded symbols
            excluded_open = [row for row in rows if row["symbol"] not in ACTIVE_SYMBOLS]
            if excluded_open:
                print(f"\n⚠️  WARNING: {len(excluded_open)} excluded symbol(s) still have open positions!")
            else:
                print(f"\n✅ All open positions are in active symbols only")

        print("\n" + "=" * 80)

    finally:
        await conn.close()


# =============================================================================
# ENTRY POINT
# =============================================================================

async def main():
    """
    Main entry point
    """
    try:
        # Close excluded positions
        await close_excluded_positions()

        # Verify results
        await verify_remaining_positions()

        print("\n✅ Script completed successfully!\n")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
