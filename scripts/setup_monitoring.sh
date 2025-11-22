#!/bin/bash
# Complete Monitoring Setup Script
# Sets up all cron jobs for automation

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=========================================="
echo "Setting up automated monitoring and backups"
echo "=========================================="

# Remove existing cron jobs for this project
crontab -l 2>/dev/null | grep -v "crypto-trading-bot" | crontab -

# Add backup job (daily at 2 AM)
(crontab -l 2>/dev/null; echo "0 2 * * * $SCRIPT_DIR/backup_all.sh >> /tmp/crypto_backup.log 2>&1") | crontab -

# Add health monitoring (every 5 minutes)
(crontab -l 2>/dev/null; echo "*/5 * * * * $SCRIPT_DIR/health_monitor_cron.sh >> /tmp/health_monitor.log 2>&1") | crontab -

echo ""
echo "✅ Cron jobs configured:"
echo "   - Backups: Daily at 2:00 AM"
echo "   - Health monitoring: Every 5 minutes"
echo ""
echo "View scheduled jobs: crontab -l"
echo "View backup logs: tail -f /tmp/crypto_backup.log"
echo "View health logs: tail -f /tmp/health_monitor.log"
echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
