#!/usr/bin/env python3
"""
Quick Database Connection Test
==============================
Purpose: Validate TimescaleDB connection and basic data availability
Author: Data Researcher Agent
Date: 2025-11-20
"""

import psycopg2
from datetime import datetime


def test_connection():
    """
    Test database connection and print basic statistics
    """
    # Connection parameters
    db_params = {
        'host': 'localhost',
        'port': 5433,
        'dbname': 'market_data',
        'user': 'cryptobot',
        'password': 'timescale_dev_password'
    }

    try:
        # Connect
        print("Testing connection to TimescaleDB...")
        conn = psycopg2.connect(**db_params)
        cursor = conn.cursor()

        # Test query
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✓ Connected successfully!")
        print(f"  Database version: {version[0][:50]}...")

        # Check klines table (timestamps are stored as bigint milliseconds)
        cursor.execute("""
            SELECT symbol, interval, COUNT(*) as count,
                   to_timestamp(MIN(timestamp)/1000) as earliest,
                   to_timestamp(MAX(timestamp)/1000) as latest,
                   ROUND((MAX(timestamp) - MIN(timestamp))::numeric / (1000*86400), 2) as days
            FROM klines
            GROUP BY symbol, interval
            ORDER BY symbol
        """)

        results = cursor.fetchall()

        print(f"\n{'='*90}")
        print("Current Data Summary:")
        print(f"{'='*90}")
        print(f"{'Symbol':<12} {'Interval':<10} {'Count':<10} {'Earliest':<20} {'Latest':<20} {'Days':<10}")
        print("-"*90)

        for row in results:
            symbol, interval, count, earliest, latest, days = row
            print(f"{symbol:<12} {interval:<10} {count:<10} {earliest.strftime('%Y-%m-%d %H:%M'):<20} {latest.strftime('%Y-%m-%d %H:%M'):<20} {float(days):<10.1f}")

        cursor.close()
        conn.close()

        print(f"\n✓ Connection test passed!")

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nTroubleshooting:")
        print("1. Check if TimescaleDB is running: docker ps")
        print("2. Verify connection parameters in db_params")
        print("3. Ensure database 'market_data' exists")
        print("4. Check if user 'cryptobot' has correct password")


if __name__ == '__main__':
    test_connection()
