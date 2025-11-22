#!/bin/bash
# Crypto Trading Bot - Database Optimization Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Optimize TimescaleDB for performance
# Usage: ./scripts/optimize_database.sh [--vacuum] [--analyze] [--reindex] [--all]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
RUN_VACUUM=false
RUN_ANALYZE=false
RUN_REINDEX=false
RUN_ALL=false
CONTAINER_NAME="crypto-trading-bot-timescaledb-1"
DB_NAME="crypto_trading"
DB_USER="crypto_user"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --vacuum)
            RUN_VACUUM=true
            shift
            ;;
        --analyze)
            RUN_ANALYZE=true
            shift
            ;;
        --reindex)
            RUN_REINDEX=true
            shift
            ;;
        --all)
            RUN_ALL=true
            RUN_VACUUM=true
            RUN_ANALYZE=true
            RUN_REINDEX=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--vacuum] [--analyze] [--reindex] [--all]"
            exit 1
            ;;
    esac
done

# If no flags, show usage
if ! $RUN_VACUUM && ! $RUN_ANALYZE && ! $RUN_REINDEX; then
    echo "Usage: $0 [--vacuum] [--analyze] [--reindex] [--all]"
    echo ""
    echo "Options:"
    echo "  --vacuum    Run VACUUM to reclaim storage"
    echo "  --analyze   Update statistics for query planner"
    echo "  --reindex   Rebuild indexes for performance"
    echo "  --all       Run all optimizations (recommended weekly)"
    echo ""
    echo "Examples:"
    echo "  $0 --analyze                  # Quick daily optimization"
    echo "  $0 --vacuum --analyze         # Weekly maintenance"
    echo "  $0 --all                      # Full monthly optimization"
    exit 0
fi

# Log function
log() {
    local level=$1
    shift
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $level:${NC} $@"
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Database Optimization                                     ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Check database connection
check_database() {
    log INFO "Checking database connection..."

    if docker exec "$CONTAINER_NAME" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; then
        log SUCCESS "Database is ready"
        return 0
    else
        log ERROR "Database is not accessible"
        return 1
    fi
}

# Get database size before optimization
get_database_size_before() {
    log INFO "Getting current database size..."

    local size_query="SELECT pg_size_pretty(pg_database_size('$DB_NAME'));"
    DB_SIZE_BEFORE=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$size_query" 2>/dev/null | xargs)

    log INFO "Current database size: $DB_SIZE_BEFORE"
}

# Get table sizes
show_table_sizes() {
    log INFO "Analyzing table sizes..."

    local tables_query="
    SELECT
        schemaname || '.' || tablename AS table_name,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
        pg_size_pretty(pg_relation_size(schemaname||'.'||tablename)) AS table_size,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename) - pg_relation_size(schemaname||'.'||tablename)) AS indexes_size
    FROM pg_tables
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema', '_timescaledb_internal')
    ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
    LIMIT 10;
    "

    echo ""
    echo -e "${CYAN}Top 10 Tables by Size:${NC}"
    echo "────────────────────────────────────────────────────────────"
    docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "$tables_query" 2>/dev/null
    echo ""
}

# VACUUM operation
run_vacuum() {
    log INFO "Running VACUUM to reclaim storage..."
    echo ""

    local start_time=$(date +%s)

    # Get list of tables
    local tables=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT tablename FROM pg_tables
        WHERE schemaname NOT IN ('pg_catalog', 'information_schema', '_timescaledb_internal')
    " 2>/dev/null)

    local table_count=0
    local success_count=0

    while IFS= read -r table; do
        table=$(echo "$table" | xargs)  # Trim whitespace
        if [ ! -z "$table" ]; then
            ((table_count++))
            echo -ne "  [${table_count}] Vacuuming: $table..."

            if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "VACUUM VERBOSE $table;" >/dev/null 2>&1; then
                echo -e " ${GREEN}✓${NC}"
                ((success_count++))
            else
                echo -e " ${YELLOW}⚠${NC}"
            fi
        fi
    done <<< "$tables"

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    log SUCCESS "VACUUM completed: $success_count/$table_count tables (${duration}s)"
}

# ANALYZE operation
run_analyze() {
    log INFO "Running ANALYZE to update statistics..."
    echo ""

    local start_time=$(date +%s)

    # Run ANALYZE on entire database
    if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "ANALYZE VERBOSE;" 2>&1 | grep -i "analyzing" | while read line; do
        echo "  $line"
    done; then
        local end_time=$(date +%s)
        local duration=$((end_time - start_time))
        echo ""
        log SUCCESS "ANALYZE completed (${duration}s)"
        return 0
    else
        log ERROR "ANALYZE failed"
        return 1
    fi
}

# REINDEX operation
run_reindex() {
    log INFO "Running REINDEX to rebuild indexes..."
    echo ""

    local start_time=$(date +%s)

    # Get list of indexes
    local indexes_query="
    SELECT
        schemaname || '.' || indexname AS index_name
    FROM pg_indexes
    WHERE schemaname NOT IN ('pg_catalog', 'information_schema', '_timescaledb_internal')
    ORDER BY indexname;
    "

    local indexes=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$indexes_query" 2>/dev/null)

    local index_count=0
    local success_count=0

    while IFS= read -r index; do
        index=$(echo "$index" | xargs)  # Trim whitespace
        if [ ! -z "$index" ]; then
            ((index_count++))
            echo -ne "  [${index_count}] Reindexing: $index..."

            # Extract just the index name without schema
            local index_name=$(echo "$index" | cut -d'.' -f2)

            if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "REINDEX INDEX $index_name;" >/dev/null 2>&1; then
                echo -e " ${GREEN}✓${NC}"
                ((success_count++))
            else
                echo -e " ${YELLOW}⚠${NC}"
            fi
        fi
    done <<< "$indexes"

    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    log SUCCESS "REINDEX completed: $success_count/$index_count indexes (${duration}s)"
}

# Compress old hypertable chunks (TimescaleDB specific)
compress_chunks() {
    log INFO "Compressing old TimescaleDB chunks..."
    echo ""

    # Check if compression is enabled
    local compression_check=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "
        SELECT count(*) FROM timescaledb_information.hypertables WHERE compression_enabled = true;
    " 2>/dev/null | xargs)

    if [ "$compression_check" -gt 0 ]; then
        # Compress chunks older than 7 days
        local compress_query="
        SELECT compress_chunk(chunk_schema || '.' || chunk_name)
        FROM timescaledb_information.chunks
        WHERE NOT is_compressed
        AND range_end < NOW() - INTERVAL '7 days';
        "

        local compressed=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$compress_query" 2>/dev/null | wc -l)

        if [ "$compressed" -gt 0 ]; then
            log SUCCESS "Compressed $compressed chunks"
        else
            log INFO "No chunks to compress"
        fi
    else
        log INFO "Compression not enabled on hypertables"
    fi

    echo ""
}

# Drop old continuous aggregates (if configured)
cleanup_old_data() {
    log INFO "Checking for old data cleanup policies..."

    # Check retention policies
    local retention_query="
    SELECT
        hypertable_name,
        drop_after
    FROM timescaledb_information.drop_chunks_policies;
    "

    local has_policies=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$retention_query" 2>/dev/null)

    if [ ! -z "$has_policies" ]; then
        echo ""
        echo -e "${CYAN}Active Retention Policies:${NC}"
        docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "$retention_query" 2>/dev/null
        echo ""
    else
        log INFO "No retention policies configured"
    fi
}

# Show query performance statistics
show_slow_queries() {
    log INFO "Analyzing slow queries..."

    local slow_queries="
    SELECT
        substring(query, 1, 60) AS query_snippet,
        calls,
        round(total_exec_time::numeric, 2) AS total_time_ms,
        round(mean_exec_time::numeric, 2) AS avg_time_ms,
        round((100 * total_exec_time / sum(total_exec_time) OVER ())::numeric, 2) AS pct_total
    FROM pg_stat_statements
    WHERE query NOT LIKE '%pg_stat_statements%'
    ORDER BY total_exec_time DESC
    LIMIT 10;
    "

    # Check if pg_stat_statements extension is enabled
    if docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements';" 2>/dev/null | grep -q 1; then
        echo ""
        echo -e "${CYAN}Top 10 Slowest Queries:${NC}"
        echo "────────────────────────────────────────────────────────────"
        docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "$slow_queries" 2>/dev/null || log WARNING "Query stats not available"
        echo ""
    else
        log INFO "pg_stat_statements extension not enabled"
    fi
}

# Get database size after optimization
get_database_size_after() {
    log INFO "Getting optimized database size..."

    local size_query="SELECT pg_size_pretty(pg_database_size('$DB_NAME'));"
    DB_SIZE_AFTER=$(docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -t -c "$size_query" 2>/dev/null | xargs)

    log INFO "New database size: $DB_SIZE_AFTER"
}

# Print summary
print_summary() {
    local exit_code=$1

    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Optimization Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✓ Optimization completed successfully${NC}"
    else
        echo -e "${YELLOW}⚠ Optimization completed with warnings${NC}"
    fi

    echo ""
    echo "Operations performed:"
    $RUN_VACUUM && echo "  ✓ VACUUM - Reclaimed storage"
    $RUN_ANALYZE && echo "  ✓ ANALYZE - Updated statistics"
    $RUN_REINDEX && echo "  ✓ REINDEX - Rebuilt indexes"

    echo ""
    echo "Database size:"
    echo "  Before: $DB_SIZE_BEFORE"
    echo "  After:  $DB_SIZE_AFTER"

    echo ""
    echo -e "${CYAN}Recommendations:${NC}"
    echo "  • Run --analyze daily for optimal query performance"
    echo "  • Run --vacuum weekly to reclaim storage"
    echo "  • Run --all monthly for complete maintenance"
    echo "  • Monitor slow queries and add indexes as needed"

    echo ""
    echo -e "${BLUE}Optimization completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Main execution
main() {
    local start_time=$(date +%s)

    print_header

    # Check database
    echo ""
    if ! check_database; then
        log ERROR "Cannot proceed - database not accessible"
        exit 1
    fi

    # Get initial metrics
    echo ""
    get_database_size_before
    show_table_sizes

    # Run operations
    if $RUN_VACUUM; then
        echo ""
        run_vacuum
    fi

    if $RUN_ANALYZE; then
        echo ""
        run_analyze
    fi

    if $RUN_REINDEX; then
        echo ""
        run_reindex
    fi

    # TimescaleDB specific optimizations
    if $RUN_ALL; then
        echo ""
        compress_chunks
        cleanup_old_data
    fi

    # Get final metrics
    echo ""
    get_database_size_after

    # Show performance insights
    if $RUN_ALL; then
        show_slow_queries
    fi

    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    log INFO "Total optimization time: ${duration}s"

    # Print summary
    print_summary 0
}

# Run main function
main
