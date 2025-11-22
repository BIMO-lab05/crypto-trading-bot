#!/usr/bin/env python3
"""
Database Query Optimization Tool
Analyzes slow queries, suggests indexes, and optimizes database performance

Features:
- Slow query detection
- Missing index identification
- Query EXPLAIN ANALYZE
- Index recommendation
- Query statistics
"""

import asyncio
import asyncpg
import time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class SlowQuery:
    """Represents a slow database query"""
    query: str
    mean_exec_time_ms: float
    calls: int
    total_exec_time_ms: float
    rows: int
    query_type: str  # SELECT, INSERT, UPDATE, DELETE


@dataclass
class MissingIndex:
    """Represents a potentially missing index"""
    table: str
    column: str
    n_distinct: int
    correlation: float
    reason: str


@dataclass
class IndexRecommendation:
    """Recommendation for creating an index"""
    table: str
    columns: List[str]
    index_name: str
    reason: str
    priority: str  # 'high', 'medium', 'low'
    estimated_benefit: str
    create_statement: str


class DatabaseOptimizer:
    """
    Database optimization and analysis tool
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "trading_bot",
        user: str = "postgres",
        password: str = "password"
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn: Optional[asyncpg.Connection] = None

    async def connect(self):
        """Establish database connection"""
        try:
            self.conn = await asyncpg.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            print(f"✅ Connected to {self.database} at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"❌ Failed to connect to database: {e}")
            print(f"   Host: {self.host}:{self.port}")
            print(f"   Database: {self.database}")
            print(f"   Note: Ensure PostgreSQL is running and credentials are correct")
            return False

    async def close(self):
        """Close database connection"""
        if self.conn:
            await self.conn.close()

    async def enable_pg_stat_statements(self) -> bool:
        """
        Enable pg_stat_statements extension for query statistics

        Returns True if enabled successfully
        """
        try:
            # Check if extension exists
            result = await self.conn.fetchrow(
                "SELECT * FROM pg_extension WHERE extname = 'pg_stat_statements'"
            )

            if not result:
                print("Creating pg_stat_statements extension...")
                await self.conn.execute("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
                print("✅ pg_stat_statements enabled")
            else:
                print("✅ pg_stat_statements already enabled")

            return True

        except Exception as e:
            print(f"⚠️  Could not enable pg_stat_statements: {e}")
            print("   Note: This requires PostgreSQL superuser privileges")
            print("   You may need to add 'shared_preload_libraries = pg_stat_statements'")
            print("   to postgresql.conf and restart PostgreSQL")
            return False

    async def get_slow_queries(
        self,
        min_exec_time_ms: float = 100,
        limit: int = 20
    ) -> List[SlowQuery]:
        """
        Find slow queries using pg_stat_statements

        Args:
            min_exec_time_ms: Minimum average execution time in milliseconds
            limit: Maximum number of queries to return

        Returns:
            List of slow queries
        """
        try:
            query = """
                SELECT
                    query,
                    mean_exec_time,
                    calls,
                    total_exec_time,
                    rows,
                    CASE
                        WHEN query ILIKE 'SELECT%' THEN 'SELECT'
                        WHEN query ILIKE 'INSERT%' THEN 'INSERT'
                        WHEN query ILIKE 'UPDATE%' THEN 'UPDATE'
                        WHEN query ILIKE 'DELETE%' THEN 'DELETE'
                        ELSE 'OTHER'
                    END AS query_type
                FROM pg_stat_statements
                WHERE mean_exec_time > $1
                    AND query NOT LIKE '%pg_stat_statements%'
                    AND query NOT LIKE '%pg_catalog%'
                ORDER BY mean_exec_time DESC
                LIMIT $2
            """

            rows = await self.conn.fetch(query, min_exec_time_ms, limit)

            slow_queries = [
                SlowQuery(
                    query=row['query'][:200],  # Truncate long queries
                    mean_exec_time_ms=row['mean_exec_time'],
                    calls=row['calls'],
                    total_exec_time_ms=row['total_exec_time'],
                    rows=row['rows'],
                    query_type=row['query_type']
                )
                for row in rows
            ]

            return slow_queries

        except Exception as e:
            print(f"⚠️  Could not fetch slow queries: {e}")
            return []

    async def get_table_statistics(self) -> List[Dict]:
        """Get statistics for all tables"""
        try:
            query = """
                SELECT
                    schemaname,
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS total_size,
                    pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes,
                    n_tup_ins AS inserts,
                    n_tup_upd AS updates,
                    n_tup_del AS deletes,
                    n_live_tup AS live_tuples,
                    n_dead_tup AS dead_tuples,
                    last_vacuum,
                    last_autovacuum,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """

            rows = await self.conn.fetch(query)

            return [dict(row) for row in rows]

        except Exception as e:
            print(f"⚠️  Could not fetch table statistics: {e}")
            return []

    async def get_missing_indexes(self) -> List[MissingIndex]:
        """
        Identify columns that might benefit from indexes

        Based on:
        - Low correlation (table scans are inefficient)
        - High n_distinct (good index selectivity)
        - Frequently used in WHERE clauses
        """
        try:
            query = """
                SELECT
                    schemaname,
                    tablename,
                    attname AS column_name,
                    n_distinct,
                    correlation
                FROM pg_stats
                WHERE schemaname = 'public'
                    AND n_distinct > 100
                    AND correlation < 0.3
                ORDER BY n_distinct DESC, correlation ASC
                LIMIT 20
            """

            rows = await self.conn.fetch(query)

            missing_indexes = []
            for row in rows:
                missing_indexes.append(MissingIndex(
                    table=f"{row['schemaname']}.{row['tablename']}",
                    column=row['column_name'],
                    n_distinct=row['n_distinct'],
                    correlation=row['correlation'],
                    reason=f"High cardinality ({row['n_distinct']} distinct values) with low correlation ({row['correlation']:.2f})"
                ))

            return missing_indexes

        except Exception as e:
            print(f"⚠️  Could not analyze missing indexes: {e}")
            return []

    async def get_unused_indexes(self) -> List[Dict]:
        """Find indexes that are never used"""
        try:
            query = """
                SELECT
                    schemaname,
                    tablename,
                    indexname,
                    idx_scan AS index_scans,
                    idx_tup_read AS tuples_read,
                    idx_tup_fetch AS tuples_fetched,
                    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                    AND schemaname = 'public'
                ORDER BY pg_relation_size(indexrelid) DESC
            """

            rows = await self.conn.fetch(query)
            return [dict(row) for row in rows]

        except Exception as e:
            print(f"⚠️  Could not fetch unused indexes: {e}")
            return []

    async def analyze_query(self, query: str) -> str:
        """
        Run EXPLAIN ANALYZE on a query

        Returns the query execution plan
        """
        try:
            explain_query = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
            result = await self.conn.fetchval(explain_query)

            # Parse JSON result
            plan = json.loads(result)[0]

            return json.dumps(plan, indent=2)

        except Exception as e:
            return f"Error analyzing query: {e}"

    def generate_index_recommendations(
        self,
        slow_queries: List[SlowQuery],
        missing_indexes: List[MissingIndex]
    ) -> List[IndexRecommendation]:
        """
        Generate index recommendations based on analysis

        Args:
            slow_queries: List of slow queries
            missing_indexes: List of potentially missing indexes

        Returns:
            List of index recommendations
        """
        recommendations = []

        # Recommend indexes for slow query columns
        for slow_query in slow_queries[:5]:  # Top 5 slow queries
            if slow_query.query_type == 'SELECT' and 'WHERE' in slow_query.query.upper():
                # Extract table name (basic parsing)
                query_upper = slow_query.query.upper()
                if ' FROM ' in query_upper:
                    try:
                        table_part = query_upper.split(' FROM ')[1].split()[0]
                        table_name = table_part.strip('"').strip("'")

                        recommendations.append(IndexRecommendation(
                            table=table_name,
                            columns=["<analyze query to identify>"],
                            index_name=f"idx_{table_name}_query_opt",
                            reason=f"Slow SELECT query ({slow_query.mean_exec_time_ms:.2f}ms avg)",
                            priority='high',
                            estimated_benefit=f"May reduce query time from {slow_query.mean_exec_time_ms:.2f}ms",
                            create_statement=f"-- Analyze WHERE clause to identify column(s)\n-- CREATE INDEX idx_{table_name}_query_opt ON {table_name} (column_name);"
                        ))
                    except Exception:
                        pass

        # Recommend indexes for missing index candidates
        for missing_index in missing_indexes[:10]:
            recommendations.append(IndexRecommendation(
                table=missing_index.table,
                columns=[missing_index.column],
                index_name=f"idx_{missing_index.table.replace('.', '_')}_{missing_index.column}",
                reason=missing_index.reason,
                priority='medium',
                estimated_benefit=f"Improve lookups on high-cardinality column",
                create_statement=f"CREATE INDEX idx_{missing_index.table.replace('.', '_')}_{missing_index.column} ON {missing_index.table} ({missing_index.column});"
            ))

        return recommendations

    def print_slow_queries_report(self, slow_queries: List[SlowQuery]):
        """Print formatted slow queries report"""
        print(f"\n{'='*100}")
        print("SLOW QUERIES REPORT")
        print(f"{'='*100}")

        if not slow_queries:
            print("✅ No slow queries detected (all queries < 100ms avg)")
            print(f"{'='*100}\n")
            return

        print(f"{'Query Type':<12} {'Avg Time':<12} {'Calls':<10} {'Total Time':<15} {'Query':<50}")
        print("─" * 100)

        for sq in slow_queries:
            print(
                f"{sq.query_type:<12} "
                f"{sq.mean_exec_time_ms:<12.2f} "
                f"{sq.calls:<10} "
                f"{sq.total_exec_time_ms:<15.2f} "
                f"{sq.query[:50]}"
            )

        print(f"{'='*100}\n")

    def print_table_statistics_report(self, stats: List[Dict]):
        """Print table statistics report"""
        print(f"\n{'='*100}")
        print("TABLE STATISTICS")
        print(f"{'='*100}")

        if not stats:
            print("No tables found")
            print(f"{'='*100}\n")
            return

        print(f"{'Table':<30} {'Size':<15} {'Live Rows':<12} {'Dead Rows':<12} {'Last Vacuum':<20}")
        print("─" * 100)

        for stat in stats[:10]:  # Show top 10 tables
            last_vacuum = stat['last_vacuum'].strftime('%Y-%m-%d %H:%M') if stat['last_vacuum'] else 'Never'
            print(
                f"{stat['tablename']:<30} "
                f"{stat['total_size']:<15} "
                f"{stat['live_tuples']:<12} "
                f"{stat['dead_tuples']:<12} "
                f"{last_vacuum:<20}"
            )

        print(f"{'='*100}\n")

    def print_index_recommendations(self, recommendations: List[IndexRecommendation]):
        """Print index recommendations"""
        print(f"\n{'='*100}")
        print("INDEX RECOMMENDATIONS")
        print(f"{'='*100}")

        if not recommendations:
            print("✅ No index recommendations")
            print(f"{'='*100}\n")
            return

        for i, rec in enumerate(recommendations, 1):
            priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
            emoji = priority_emoji.get(rec.priority, '⚪')

            print(f"\n{i}. {emoji} {rec.priority.upper()} PRIORITY")
            print(f"   Table: {rec.table}")
            print(f"   Columns: {', '.join(rec.columns)}")
            print(f"   Reason: {rec.reason}")
            print(f"   Benefit: {rec.estimated_benefit}")
            print(f"   SQL:\n   {rec.create_statement}")

        print(f"\n{'='*100}\n")

    async def run_full_analysis(self):
        """Run complete database optimization analysis"""
        if not await self.connect():
            return

        print("\n" + "="*100)
        print(" DATABASE OPTIMIZATION ANALYSIS")
        print("="*100 + "\n")

        # Enable pg_stat_statements if possible
        await self.enable_pg_stat_statements()

        # Get slow queries
        print("\n🔍 Analyzing slow queries...")
        slow_queries = await self.get_slow_queries(min_exec_time_ms=50)
        self.print_slow_queries_report(slow_queries)

        # Get table statistics
        print("\n🔍 Analyzing table statistics...")
        table_stats = await self.get_table_statistics()
        self.print_table_statistics_report(table_stats)

        # Get missing indexes
        print("\n🔍 Analyzing potential missing indexes...")
        missing_indexes = await self.get_missing_indexes()

        # Get unused indexes
        print("\n🔍 Finding unused indexes...")
        unused_indexes = await self.get_unused_indexes()

        if unused_indexes:
            print(f"\n{'='*100}")
            print("UNUSED INDEXES (Consider Dropping)")
            print(f"{'='*100}")
            print(f"{'Table':<30} {'Index Name':<30} {'Size':<15} {'Scans':<10}")
            print("─" * 100)

            for idx in unused_indexes:
                print(
                    f"{idx['tablename']:<30} "
                    f"{idx['indexname']:<30} "
                    f"{idx['index_size']:<15} "
                    f"{idx['index_scans']:<10}"
                )

            print(f"{'='*100}\n")

        # Generate recommendations
        recommendations = self.generate_index_recommendations(slow_queries, missing_indexes)
        self.print_index_recommendations(recommendations)

        await self.close()

        # Summary
        print("\n" + "="*100)
        print(" SUMMARY")
        print("="*100)
        print(f"Slow Queries Found:       {len(slow_queries)}")
        print(f"Tables Analyzed:          {len(table_stats)}")
        print(f"Missing Index Candidates: {len(missing_indexes)}")
        print(f"Unused Indexes:           {len(unused_indexes)}")
        print(f"Recommendations:          {len(recommendations)}")
        print("="*100 + "\n")


async def main():
    """Main entry point"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Database Query Optimizer")
    parser.add_argument("--host", default="localhost", help="Database host")
    parser.add_argument("--port", type=int, default=5432, help="Database port")
    parser.add_argument("--database", default="trading_bot", help="Database name")
    parser.add_argument("--user", default="postgres", help="Database user")
    parser.add_argument("--password", default=os.getenv("DB_PASSWORD", "password"), help="Database password")

    args = parser.parse_args()

    optimizer = DatabaseOptimizer(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )

    await optimizer.run_full_analysis()


if __name__ == "__main__":
    asyncio.run(main())
