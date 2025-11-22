#!/bin/bash
# ==============================================================================
# Setup Weekly Performance Report Cron Job
# ==============================================================================
# This script installs a cron job to automatically generate weekly performance
# reports for the crypto trading bot.
#
# Usage:
#   ./setup_weekly_report_cron.sh [--day WEEKDAY] [--time TIME] [--remove]
#
# Examples:
#   ./setup_weekly_report_cron.sh
#   ./setup_weekly_report_cron.sh --day Monday --time "09:00"
#   ./setup_weekly_report_cron.sh --remove
#
# Author: Backend Developer Agent
# Date: 2025-11-19
# ==============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default configuration
DEFAULT_DAY="Monday"
DEFAULT_TIME="09:00"
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"
SCRIPT_PATH="$PROJECT_DIR/scripts/weekly_performance_report.py"
LOG_DIR="$PROJECT_DIR/logs"
CRON_LOG="$LOG_DIR/weekly_report_cron.log"
ERROR_LOG="$LOG_DIR/weekly_report_error.log"

# Parse command-line arguments
DAY="$DEFAULT_DAY"
TIME="$DEFAULT_TIME"
REMOVE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --day)
            DAY="$2"
            shift 2
            ;;
        --time)
            TIME="$2"
            shift 2
            ;;
        --remove)
            REMOVE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--day WEEKDAY] [--time TIME] [--remove]"
            echo ""
            echo "Options:"
            echo "  --day WEEKDAY    Day of week to run report (Monday-Sunday)"
            echo "  --time TIME      Time to run report (HH:MM format, 24-hour)"
            echo "  --remove         Remove existing cron job"
            echo "  --help           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                      # Use defaults"
            echo "  $0 --day Monday --time 09:00           # Run Monday at 9 AM"
            echo "  $0 --remove                             # Remove cron job"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Function to print colored messages
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to remove existing cron job
remove_cron_job() {
    print_info "Removing weekly performance report cron job..."

    # Get current crontab
    crontab -l > /tmp/current_cron 2>/dev/null || true

    # Remove lines containing weekly_performance_report
    grep -v "weekly_performance_report.py" /tmp/current_cron > /tmp/new_cron 2>/dev/null || true

    # Install new crontab
    crontab /tmp/new_cron

    # Clean up
    rm -f /tmp/current_cron /tmp/new_cron

    print_success "Cron job removed successfully"
}

# Function to convert day name to cron day number
day_to_cron_number() {
    case "$1" in
        Sunday|sunday|Sun|sun)
            echo "0"
            ;;
        Monday|monday|Mon|mon)
            echo "1"
            ;;
        Tuesday|tuesday|Tue|tue)
            echo "2"
            ;;
        Wednesday|wednesday|Wed|wed)
            echo "3"
            ;;
        Thursday|thursday|Thu|thu)
            echo "4"
            ;;
        Friday|friday|Fri|fri)
            echo "5"
            ;;
        Saturday|saturday|Sat|sat)
            echo "6"
            ;;
        *)
            print_error "Invalid day: $1"
            echo "Valid days: Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday"
            exit 1
            ;;
    esac
}

# Function to validate time format
validate_time() {
    if ! [[ "$1" =~ ^([0-1][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
        print_error "Invalid time format: $1"
        echo "Time must be in HH:MM format (24-hour), e.g., 09:00 or 14:30"
        exit 1
    fi
}

# Main installation function
install_cron_job() {
    print_info "Installing weekly performance report cron job..."

    # Validate inputs
    validate_time "$TIME"
    DAY_NUMBER=$(day_to_cron_number "$DAY")

    # Parse hour and minute
    HOUR=$(echo "$TIME" | cut -d: -f1)
    MINUTE=$(echo "$TIME" | cut -d: -f2)

    # Remove leading zeros to avoid octal interpretation
    HOUR=$((10#$HOUR))
    MINUTE=$((10#$MINUTE))

    print_info "Configuration:"
    echo "  Day: $DAY (cron day: $DAY_NUMBER)"
    echo "  Time: $TIME (hour: $HOUR, minute: $MINUTE)"
    echo "  Script: $SCRIPT_PATH"
    echo "  Log: $CRON_LOG"
    echo ""

    # Verify script exists
    if [ ! -f "$SCRIPT_PATH" ]; then
        print_error "Script not found: $SCRIPT_PATH"
        exit 1
    fi

    # Make script executable
    chmod +x "$SCRIPT_PATH"
    print_success "Script is executable"

    # Create log directory if it doesn't exist
    mkdir -p "$LOG_DIR"
    print_success "Log directory created: $LOG_DIR"

    # Create cron job command
    # Cron format: minute hour day-of-month month day-of-week command
    CRON_COMMAND="$MINUTE $HOUR * * $DAY_NUMBER cd $PROJECT_DIR && /usr/bin/python3 $SCRIPT_PATH --email >> $CRON_LOG 2>> $ERROR_LOG"

    print_info "Cron command:"
    echo "  $CRON_COMMAND"
    echo ""

    # Get current crontab
    crontab -l > /tmp/current_cron 2>/dev/null || true

    # Remove any existing weekly_performance_report entries
    grep -v "weekly_performance_report.py" /tmp/current_cron > /tmp/new_cron 2>/dev/null || true

    # Add new cron job with comments
    echo "" >> /tmp/new_cron
    echo "# ===================================================================" >> /tmp/new_cron
    echo "# Crypto Trading Bot - Weekly Performance Report" >> /tmp/new_cron
    echo "# Runs every $DAY at $TIME" >> /tmp/new_cron
    echo "# Installed: $(date)" >> /tmp/new_cron
    echo "# ===================================================================" >> /tmp/new_cron
    echo "$CRON_COMMAND" >> /tmp/new_cron
    echo "" >> /tmp/new_cron

    # Install new crontab
    crontab /tmp/new_cron

    # Clean up
    rm -f /tmp/current_cron /tmp/new_cron

    print_success "Cron job installed successfully!"
    echo ""
    print_info "The report will run:"
    echo "  - Every $DAY at $TIME"
    echo "  - Logs will be written to: $CRON_LOG"
    echo "  - Errors will be logged to: $ERROR_LOG"
    echo ""
    print_info "To view installed cron jobs:"
    echo "  crontab -l"
    echo ""
    print_info "To view recent logs:"
    echo "  tail -f $CRON_LOG"
    echo ""
}

# Function to test the report generation
test_report() {
    print_info "Testing report generation..."

    if [ ! -f "$SCRIPT_PATH" ]; then
        print_error "Script not found: $SCRIPT_PATH"
        return 1
    fi

    print_info "Running dry-run test..."
    cd "$PROJECT_DIR"

    if /usr/bin/python3 "$SCRIPT_PATH" --dry-run 2>&1; then
        print_success "Test completed successfully!"
        return 0
    else
        print_error "Test failed!"
        return 1
    fi
}

# Function to show current cron jobs
show_cron_jobs() {
    print_info "Current cron jobs related to performance reports:"
    echo ""

    if crontab -l 2>/dev/null | grep -q "weekly_performance_report"; then
        crontab -l | grep -A 0 -B 4 "weekly_performance_report"
    else
        print_warning "No performance report cron jobs found"
    fi

    echo ""
}

# Function to create notification script for errors
create_error_notification() {
    print_info "Creating error notification script..."

    ERROR_NOTIFY_SCRIPT="$PROJECT_DIR/scripts/notify_report_error.sh"

    cat > "$ERROR_NOTIFY_SCRIPT" << 'EOF'
#!/bin/bash
# Notify on weekly report errors

ERROR_LOG="/mnt/d/Bimo_max/crypto-trading-bot/logs/weekly_report_error.log"

# Check if error log has recent errors (last 24 hours)
if [ -f "$ERROR_LOG" ]; then
    RECENT_ERRORS=$(find "$ERROR_LOG" -mtime -1 2>/dev/null)

    if [ ! -z "$RECENT_ERRORS" ]; then
        # Send notification (example using mail command)
        # mail -s "Weekly Report Error" admin@example.com < "$ERROR_LOG"

        echo "Error detected in weekly report generation"
        tail -n 50 "$ERROR_LOG"
    fi
fi
EOF

    chmod +x "$ERROR_NOTIFY_SCRIPT"
    print_success "Error notification script created: $ERROR_NOTIFY_SCRIPT"
}

# Function to backup old reports
setup_report_cleanup() {
    print_info "Setting up automatic report cleanup..."

    CLEANUP_SCRIPT="$PROJECT_DIR/scripts/cleanup_old_reports.sh"

    cat > "$CLEANUP_SCRIPT" << 'EOF'
#!/bin/bash
# Cleanup old performance reports (older than 90 days)

REPORTS_DIR="/mnt/d/Bimo_max/crypto-trading-bot/reports"
RETENTION_DAYS=90

echo "Cleaning up reports older than $RETENTION_DAYS days..."

# Find and remove old reports
find "$REPORTS_DIR" -type f -name "*.html" -mtime +$RETENTION_DAYS -delete
find "$REPORTS_DIR" -type f -name "*.md" -mtime +$RETENTION_DAYS -delete
find "$REPORTS_DIR" -type f -name "*.json" -mtime +$RETENTION_DAYS -delete
find "$REPORTS_DIR" -type f -name "*.csv" -mtime +$RETENTION_DAYS -delete
find "$REPORTS_DIR" -type f -name "*.png" -mtime +$RETENTION_DAYS -delete

# Remove empty directories
find "$REPORTS_DIR" -type d -empty -delete

echo "Cleanup complete"
EOF

    chmod +x "$CLEANUP_SCRIPT"
    print_success "Cleanup script created: $CLEANUP_SCRIPT"

    # Add monthly cleanup to cron
    print_info "Adding monthly cleanup to cron..."

    crontab -l > /tmp/current_cron 2>/dev/null || true

    # Remove existing cleanup entries
    grep -v "cleanup_old_reports.sh" /tmp/current_cron > /tmp/new_cron 2>/dev/null || true

    # Add cleanup job (runs first day of month at 2 AM)
    echo "# Crypto Trading Bot - Cleanup old reports (monthly)" >> /tmp/new_cron
    echo "0 2 1 * * $CLEANUP_SCRIPT >> $LOG_DIR/report_cleanup.log 2>&1" >> /tmp/new_cron

    crontab /tmp/new_cron
    rm -f /tmp/current_cron /tmp/new_cron

    print_success "Monthly cleanup job installed"
}

# Main execution
main() {
    echo ""
    echo "=========================================="
    echo "  Weekly Performance Report Cron Setup"
    echo "=========================================="
    echo ""

    # Check if cron is available
    if ! command -v crontab &> /dev/null; then
        print_error "crontab command not found. Please install cron."
        exit 1
    fi

    # Check if Python is available
    if ! command -v python3 &> /dev/null; then
        print_error "python3 command not found. Please install Python 3."
        exit 1
    fi

    # Execute requested action
    if [ "$REMOVE" = true ]; then
        remove_cron_job
        show_cron_jobs
    else
        # Show current jobs first
        show_cron_jobs

        # Test the report
        if ! test_report; then
            print_warning "Report test failed, but continuing with installation..."
            print_warning "You may need to fix configuration before reports will work"
        fi

        # Install cron job
        install_cron_job

        # Create additional scripts
        create_error_notification
        setup_report_cleanup

        # Show updated jobs
        echo ""
        show_cron_jobs
    fi

    echo ""
    echo "=========================================="
    echo "  Setup Complete"
    echo "=========================================="
    echo ""
}

# Run main function
main
