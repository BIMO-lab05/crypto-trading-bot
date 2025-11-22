#!/bin/bash
# Crypto Trading Bot - Log Cleanup & Rotation Script
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Clean old logs and rotate current logs
# Usage: ./scripts/cleanup_logs.sh [--days 7] [--dry-run]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
DAYS_TO_KEEP=7
DRY_RUN=false
LOG_DIR="/tmp"
ARCHIVE_DIR="/tmp/crypto-bot-logs-archive"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --days)
            DAYS_TO_KEEP=$2
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--days N] [--dry-run]"
            exit 1
            ;;
    esac
done

# Create archive directory
mkdir -p "$ARCHIVE_DIR"

log() {
    local level=$1
    shift
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $level:${NC} $@"
}

print_header() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║  Log Cleanup & Rotation                                    ║${NC}"
    echo -e "${BLUE}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    if $DRY_RUN; then
        echo -e "${YELLOW}DRY RUN MODE - No files will be deleted${NC}"
    fi

    echo "Retention: ${DAYS_TO_KEEP} days"
    echo ""
}

# Clean monitor logs
cleanup_monitor_logs() {
    log INFO "Cleaning monitor logs older than ${DAYS_TO_KEEP} days..."

    local count=0
    local size=0

    while IFS= read -r logfile; do
        local file_size=$(stat -f%z "$logfile" 2>/dev/null || stat -c%s "$logfile" 2>/dev/null)
        size=$((size + file_size))

        if $DRY_RUN; then
            echo "  Would delete: $(basename $logfile) ($(du -h "$logfile" | cut -f1))"
        else
            rm -f "$logfile"
        fi
        ((count++))
    done < <(find "$LOG_DIR" -name "monitor_*.log" -mtime +${DAYS_TO_KEEP} 2>/dev/null)

    if [ $count -gt 0 ]; then
        local size_mb=$((size / 1024 / 1024))
        log SUCCESS "Cleaned $count monitor log(s) (~${size_mb}MB)"
    else
        log INFO "No old monitor logs to clean"
    fi
}

# Clean startup logs
cleanup_startup_logs() {
    log INFO "Cleaning startup logs older than ${DAYS_TO_KEEP} days..."

    local count=0

    while IFS= read -r logfile; do
        if $DRY_RUN; then
            echo "  Would delete: $(basename $logfile)"
        else
            rm -f "$logfile"
        fi
        ((count++))
    done < <(find "$LOG_DIR" -name "startup_*.log" -mtime +${DAYS_TO_KEEP} 2>/dev/null)

    if [ $count -gt 0 ]; then
        log SUCCESS "Cleaned $count startup log(s)"
    else
        log INFO "No old startup logs to clean"
    fi
}

# Clean shutdown logs
cleanup_shutdown_logs() {
    log INFO "Cleaning shutdown logs older than ${DAYS_TO_KEEP} days..."

    local count=0

    while IFS= read -r logfile; do
        if $DRY_RUN; then
            echo "  Would delete: $(basename $logfile)"
        else
            rm -f "$logfile"
        fi
        ((count++))
    done < <(find "$LOG_DIR" -name "shutdown_*.log" -mtime +${DAYS_TO_KEEP} 2>/dev/null)

    if [ $count -gt 0 ]; then
        log SUCCESS "Cleaned $count shutdown log(s)"
    else
        log INFO "No old shutdown logs to clean"
    fi
}

# Archive current logs
archive_current_logs() {
    log INFO "Archiving current logs..."

    local TODAY=$(date +%Y%m%d)
    local archive_file="${ARCHIVE_DIR}/logs_${TODAY}.tar.gz"

    # Find all current logs
    local log_files=$(find "$LOG_DIR" -maxdepth 1 \( -name "monitor_*.log" -o -name "startup_*.log" -o -name "shutdown_*.log" -o -name "dashboard_*.log" \) -mtime -1 2>/dev/null)

    if [ ! -z "$log_files" ]; then
        if $DRY_RUN; then
            echo "  Would archive to: $archive_file"
            echo "$log_files" | while read log; do
                echo "    - $(basename $log)"
            done
        else
            echo "$log_files" | tar -czf "$archive_file" -T - 2>/dev/null || true

            if [ -f "$archive_file" ]; then
                local size=$(du -h "$archive_file" | cut -f1)
                log SUCCESS "Archived current logs to $archive_file ($size)"
            fi
        fi
    else
        log INFO "No current logs to archive"
    fi
}

# Rotate Docker logs
rotate_docker_logs() {
    log INFO "Rotating Docker logs..."

    if $DRY_RUN; then
        echo "  Would rotate Docker logs"
    else
        # Save current Docker logs
        local log_file="${LOG_DIR}/docker_logs_$(date +%Y%m%d).txt"
        docker-compose logs --tail 10000 > "$log_file" 2>/dev/null || true

        if [ -f "$log_file" ]; then
            local size=$(du -h "$log_file" | cut -f1)
            log SUCCESS "Docker logs saved ($size)"
        fi
    fi
}

# Clean Docker system
clean_docker_system() {
    log INFO "Cleaning Docker system..."

    if $DRY_RUN; then
        echo "  Would run: docker system prune -f"
    else
        # Clean up unused Docker resources
        local cleaned=$(docker system prune -f 2>&1 | grep "Total reclaimed space" || echo "No space reclaimed")
        log SUCCESS "Docker cleaned: $cleaned"
    fi
}

# Clean old archives
cleanup_old_archives() {
    log INFO "Cleaning old archives (older than ${DAYS_TO_KEEP} days)..."

    local count=0

    while IFS= read -r archive; do
        if $DRY_RUN; then
            echo "  Would delete: $(basename $archive)"
        else
            rm -f "$archive"
        fi
        ((count++))
    done < <(find "$ARCHIVE_DIR" -name "logs_*.tar.gz" -mtime +${DAYS_TO_KEEP} 2>/dev/null)

    if [ $count -gt 0 ]; then
        log SUCCESS "Cleaned $count old archive(s)"
    else
        log INFO "No old archives to clean"
    fi
}

# Print summary
print_summary() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}Cleanup Summary${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""

    if $DRY_RUN; then
        echo -e "${YELLOW}DRY RUN - No changes were made${NC}"
    else
        echo -e "${GREEN}Cleanup completed successfully${NC}"
    fi

    echo ""
    echo "Log directory usage:"
    du -sh "$LOG_DIR" 2>/dev/null | awk '{print "  " $1}' || echo "  N/A"

    echo ""
    echo "Archive directory usage:"
    du -sh "$ARCHIVE_DIR" 2>/dev/null | awk '{print "  " $1}' || echo "  N/A"

    echo ""
    echo "Docker system usage:"
    docker system df 2>/dev/null | tail -n +2 || echo "  N/A"

    echo ""
    echo -e "${BLUE}Cleanup completed at $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo ""
}

# Main execution
main() {
    print_header

    echo ""
    cleanup_monitor_logs

    echo ""
    cleanup_startup_logs

    echo ""
    cleanup_shutdown_logs

    echo ""
    archive_current_logs

    echo ""
    rotate_docker_logs

    echo ""
    clean_docker_system

    echo ""
    cleanup_old_archives

    print_summary
}

# Run main function
main
