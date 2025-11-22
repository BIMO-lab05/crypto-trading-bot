#!/bin/bash
# Crypto Trading Bot - Automated Scheduling Setup
# Version: 1.0.0
# Last Updated: 2025-11-14
#
# Purpose: Setup automated cron jobs and systemd services
# Usage: ./scripts/setup_automation.sh [--install] [--uninstall] [--preview]

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Configuration
ACTION="preview"
PROJECT_DIR="/mnt/d/Bimo_max/crypto-trading-bot"
USER=$(whoami)

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --install)
            ACTION="install"
            shift
            ;;
        --uninstall)
            ACTION="uninstall"
            shift
            ;;
        --preview)
            ACTION="preview"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--install] [--uninstall] [--preview]"
            exit 1
            ;;
    esac
done

# Log function
log() {
    local level=$1
    shift
    echo -e "${BLUE}[$(date '+%H:%M:%S')] $level:${NC} $@"
}

# Print header
print_header() {
    echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Automation Setup                                          ║${NC}"
    echo -e "${CYAN}║  $(date '+%Y-%m-%d %H:%M:%S')                                       ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log INFO "Action: $ACTION"
}

# Generate cron configuration
generate_cron_config() {
    cat <<EOF
# Crypto Trading Bot - Automated Schedule
# Generated: $(date '+%Y-%m-%d %H:%M:%S')
# User: $USER

# ═══════════════════════════════════════════════════════════
# DAILY TRADING OPERATIONS
# ═══════════════════════════════════════════════════════════

# Morning startup (9:00 AM, Monday-Friday)
0 9 * * 1-5 cd $PROJECT_DIR && ./scripts/daily_startup.sh >> /tmp/cron_startup.log 2>&1

# Quick health checks (Every 30 minutes during trading hours: 9 AM - 6 PM, Mon-Fri)
*/30 9-17 * * 1-5 cd $PROJECT_DIR && ./scripts/quick_check.sh >> /tmp/cron_quickcheck.log 2>&1

# Evening shutdown (6:00 PM, Monday-Friday)
0 18 * * 1-5 cd $PROJECT_DIR && ./scripts/daily_shutdown.sh >> /tmp/cron_shutdown.log 2>&1

# ═══════════════════════════════════════════════════════════
# MAINTENANCE TASKS
# ═══════════════════════════════════════════════════════════

# Daily backup (11:00 PM every day)
0 23 * * * cd $PROJECT_DIR && ./scripts/backup.sh --full >> /tmp/cron_backup.log 2>&1

# Daily database optimization (2:00 AM every day)
0 2 * * * cd $PROJECT_DIR && ./scripts/optimize_database.sh --analyze >> /tmp/cron_optimize.log 2>&1

# Weekly log cleanup (Sunday 3:00 AM)
0 3 * * 0 cd $PROJECT_DIR && ./scripts/cleanup_logs.sh --days 7 >> /tmp/cron_cleanup.log 2>&1

# Weekly database maintenance (Sunday 4:00 AM)
0 4 * * 0 cd $PROJECT_DIR && ./scripts/optimize_database.sh --vacuum --analyze >> /tmp/cron_db_maintenance.log 2>&1

# Monthly full optimization (1st of month, 5:00 AM)
0 5 1 * * cd $PROJECT_DIR && ./scripts/optimize_database.sh --all >> /tmp/cron_monthly_optimize.log 2>&1

# ═══════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════

# Daily performance report (8:00 PM every day)
0 20 * * * cd $PROJECT_DIR && ./scripts/generate_performance_report.sh --period daily --format html >> /tmp/cron_daily_report.log 2>&1

# Weekly performance report (Sunday 8:00 PM)
0 20 * * 0 cd $PROJECT_DIR && ./scripts/generate_performance_report.sh --period weekly --format html >> /tmp/cron_weekly_report.log 2>&1

# Daily system status report (8:00 AM every day)
0 8 * * * cd $PROJECT_DIR && ./scripts/system_status_report.sh --save /tmp/status_report.txt >> /tmp/cron_status.log 2>&1

# Monthly performance report (1st of month, 9:00 PM)
0 21 1 * * cd $PROJECT_DIR && ./scripts/generate_performance_report.sh --period monthly --format html >> /tmp/cron_monthly_report.log 2>&1

# ═══════════════════════════════════════════════════════════
# MONITORING
# ═══════════════════════════════════════════════════════════

# Health check (Every hour)
0 * * * * cd $PROJECT_DIR && ./scripts/health_check.sh >> /tmp/cron_health.log 2>&1

# Risk validation (Every 6 hours)
0 */6 * * * cd $PROJECT_DIR && python3 scripts/validate_risk_limits.py >> /tmp/cron_risk.log 2>&1

EOF
}

# Generate systemd service for monitoring
generate_systemd_service() {
    cat <<EOF
[Unit]
Description=Crypto Trading Bot Continuous Monitoring
After=network.target docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=/usr/bin/python3 $PROJECT_DIR/scripts/monitor.py --interval 60
Restart=always
RestartSec=10

# Logging
StandardOutput=append:/tmp/monitor_service.log
StandardError=append:/tmp/monitor_service_error.log

[Install]
WantedBy=multi-user.target
EOF
}

# Preview automation setup
preview_automation() {
    echo ""
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Automation Preview${NC}"
    echo -e "${CYAN}═══════════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${YELLOW}Cron Jobs to be installed:${NC}"
    echo ""

    echo "Daily Operations:"
    echo "  • 09:00 - Morning startup (Mon-Fri)"
    echo "  • 09:00-18:00 - Health checks every 30 minutes (Mon-Fri)"
    echo "  • 18:00 - Evening shutdown (Mon-Fri)"
    echo ""

    echo "Maintenance:"
    echo "  • 23:00 - Daily backup"
    echo "  • 02:00 - Daily database optimization"
    echo "  • Sunday 03:00 - Weekly log cleanup"
    echo "  • Sunday 04:00 - Weekly database maintenance"
    echo "  • 1st of month 05:00 - Monthly full optimization"
    echo ""

    echo "Reporting:"
    echo "  • 20:00 - Daily performance report"
    echo "  • Sunday 20:00 - Weekly performance report"
    echo "  • 08:00 - Daily system status report"
    echo "  • 1st of month 21:00 - Monthly performance report"
    echo ""

    echo "Monitoring:"
    echo "  • Every hour - Health check"
    echo "  • Every 6 hours - Risk validation"
    echo ""

    echo -e "${YELLOW}Systemd Service:${NC}"
    echo "  • crypto-bot-monitor.service - Continuous monitoring (60s interval)"
    echo ""

    echo -e "${CYAN}Log Files:${NC}"
    echo "  • /tmp/cron_*.log - Cron job execution logs"
    echo "  • /tmp/monitor_service.log - Monitor service log"
    echo ""
}

# Install cron jobs
install_cron() {
    log INFO "Installing cron jobs..."

    # Backup existing crontab
    local backup_file="/tmp/crontab_backup_$(date +%Y%m%d_%H%M%S).txt"
    crontab -l > "$backup_file" 2>/dev/null || true

    if [ -s "$backup_file" ]; then
        log INFO "Backed up existing crontab to: $backup_file"
    fi

    # Generate new cron config
    local cron_file="/tmp/crypto_bot_cron.txt"
    generate_cron_config > "$cron_file"

    # Append to existing crontab or create new
    if [ -s "$backup_file" ]; then
        cat "$backup_file" > /tmp/new_crontab.txt
        echo "" >> /tmp/new_crontab.txt
        cat "$cron_file" >> /tmp/new_crontab.txt
    else
        cat "$cron_file" > /tmp/new_crontab.txt
    fi

    # Install new crontab
    crontab /tmp/new_crontab.txt

    if [ $? -eq 0 ]; then
        log SUCCESS "Cron jobs installed successfully"
        echo ""
        echo "Verify with: crontab -l"
    else
        log ERROR "Failed to install cron jobs"
        return 1
    fi

    # Cleanup
    rm -f "$cron_file" /tmp/new_crontab.txt
}

# Install systemd service
install_systemd() {
    log INFO "Installing systemd monitoring service..."

    # Check if we have sudo
    if ! sudo -n true 2>/dev/null; then
        log WARNING "Sudo access required for systemd service installation"
        log INFO "Skipping systemd service installation"
        echo ""
        echo "To install manually:"
        echo "  1. Generate service file: ./scripts/setup_automation.sh --preview > /tmp/crypto-bot-monitor.service"
        echo "  2. sudo cp /tmp/crypto-bot-monitor.service /etc/systemd/system/"
        echo "  3. sudo systemctl daemon-reload"
        echo "  4. sudo systemctl enable crypto-bot-monitor"
        echo "  5. sudo systemctl start crypto-bot-monitor"
        return 0
    fi

    # Generate service file
    local service_file="/tmp/crypto-bot-monitor.service"
    generate_systemd_service > "$service_file"

    # Install service
    sudo cp "$service_file" /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable crypto-bot-monitor
    sudo systemctl start crypto-bot-monitor

    if [ $? -eq 0 ]; then
        log SUCCESS "Systemd service installed and started"
        echo ""
        echo "Service status: sudo systemctl status crypto-bot-monitor"
        echo "View logs:      sudo journalctl -u crypto-bot-monitor -f"
    else
        log ERROR "Failed to install systemd service"
        return 1
    fi

    # Cleanup
    rm -f "$service_file"
}

# Uninstall cron jobs
uninstall_cron() {
    log INFO "Uninstalling cron jobs..."

    # Backup current crontab
    local backup_file="/tmp/crontab_before_uninstall_$(date +%Y%m%d_%H%M%S).txt"
    crontab -l > "$backup_file" 2>/dev/null || true

    if [ ! -s "$backup_file" ]; then
        log INFO "No crontab found"
        return 0
    fi

    log INFO "Backed up current crontab to: $backup_file"

    # Remove crypto bot entries
    grep -v "Crypto Trading Bot" "$backup_file" | \
    grep -v "$PROJECT_DIR" > /tmp/cleaned_crontab.txt || true

    # Install cleaned crontab
    if [ -s /tmp/cleaned_crontab.txt ]; then
        crontab /tmp/cleaned_crontab.txt
        log SUCCESS "Crypto bot cron jobs removed"
    else
        crontab -r
        log SUCCESS "Crontab cleared (no other entries found)"
    fi

    # Cleanup
    rm -f /tmp/cleaned_crontab.txt
}

# Uninstall systemd service
uninstall_systemd() {
    log INFO "Uninstalling systemd service..."

    # Check if service exists
    if ! systemctl list-unit-files | grep -q crypto-bot-monitor; then
        log INFO "Systemd service not installed"
        return 0
    fi

    # Check sudo access
    if ! sudo -n true 2>/dev/null; then
        log WARNING "Sudo access required to uninstall systemd service"
        echo ""
        echo "To uninstall manually:"
        echo "  1. sudo systemctl stop crypto-bot-monitor"
        echo "  2. sudo systemctl disable crypto-bot-monitor"
        echo "  3. sudo rm /etc/systemd/system/crypto-bot-monitor.service"
        echo "  4. sudo systemctl daemon-reload"
        return 0
    fi

    # Stop and disable service
    sudo systemctl stop crypto-bot-monitor 2>/dev/null || true
    sudo systemctl disable crypto-bot-monitor 2>/dev/null || true
    sudo rm -f /etc/systemd/system/crypto-bot-monitor.service
    sudo systemctl daemon-reload

    log SUCCESS "Systemd service uninstalled"
}

# Create log rotation config
setup_log_rotation() {
    log INFO "Setting up log rotation..."

    local logrotate_config="/tmp/crypto-bot-logrotate.conf"

    cat > "$logrotate_config" <<EOF
# Crypto Trading Bot Log Rotation
# Copy to /etc/logrotate.d/crypto-bot

/tmp/cron_*.log /tmp/monitor_*.log /tmp/startup_*.log /tmp/shutdown_*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 $USER $USER
}
EOF

    log INFO "Logrotate config created: $logrotate_config"
    echo ""
    echo "To install logrotate config:"
    echo "  sudo cp $logrotate_config /etc/logrotate.d/crypto-bot"
}

# Print installation summary
print_installation_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Installation Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${GREEN}✓ Automation installed successfully${NC}"
    echo ""

    echo "Verification Commands:"
    echo "  • List cron jobs:        crontab -l"
    echo "  • Monitor service:       sudo systemctl status crypto-bot-monitor"
    echo "  • View monitor logs:     tail -f /tmp/monitor_service.log"
    echo "  • View cron logs:        ls -la /tmp/cron_*.log"
    echo ""

    echo "Management Commands:"
    echo "  • Edit cron jobs:        crontab -e"
    echo "  • Restart monitor:       sudo systemctl restart crypto-bot-monitor"
    echo "  • Stop monitor:          sudo systemctl stop crypto-bot-monitor"
    echo "  • Disable automation:    $0 --uninstall"
    echo ""

    echo "Next Steps:"
    echo "  1. Verify cron jobs are scheduled: crontab -l"
    echo "  2. Check monitor service is running: sudo systemctl status crypto-bot-monitor"
    echo "  3. Review logs after first execution: ls /tmp/cron_*.log"
    echo "  4. Adjust schedule if needed: crontab -e"
    echo ""
}

# Print uninstallation summary
print_uninstallation_summary() {
    echo ""
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${CYAN}Uninstallation Summary${NC}"
    echo -e "${CYAN}════════════════════════════════════════════════════════════${NC}"
    echo ""

    echo -e "${GREEN}✓ Automation removed successfully${NC}"
    echo ""

    echo "Verification:"
    echo "  • Cron jobs:             crontab -l"
    echo "  • Systemd service:       systemctl list-unit-files | grep crypto-bot"
    echo ""

    echo "Backups:"
    echo "  • Crontab backups:       ls /tmp/crontab_backup_*.txt"
    echo ""

    echo "To reinstall:"
    echo "  $0 --install"
    echo ""
}

# Main execution
main() {
    print_header

    case $ACTION in
        preview)
            echo ""
            preview_automation

            echo ""
            echo -e "${YELLOW}To install this automation:${NC}"
            echo "  $0 --install"
            echo ""
            echo -e "${YELLOW}To save cron config to file:${NC}"
            echo "  $0 --preview > crypto-bot-cron.txt"
            ;;

        install)
            echo ""
            preview_automation

            echo ""
            log INFO "Installing automation..."
            echo ""

            # Install cron jobs
            install_cron

            # Install systemd service
            echo ""
            install_systemd

            # Setup log rotation
            echo ""
            setup_log_rotation

            # Print summary
            print_installation_summary
            ;;

        uninstall)
            echo ""
            log INFO "Uninstalling automation..."
            echo ""

            # Uninstall cron jobs
            uninstall_cron

            # Uninstall systemd service
            echo ""
            uninstall_systemd

            # Print summary
            print_uninstallation_summary
            ;;

        *)
            log ERROR "Unknown action: $ACTION"
            exit 1
            ;;
    esac
}

# Run main function
main
