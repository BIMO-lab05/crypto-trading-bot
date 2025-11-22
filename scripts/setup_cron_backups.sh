#!/bin/bash
# Setup Cron Jobs for Automated Backups
# Runs daily at 2 AM

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Setting up cron jobs for automated backups..."

# Create cron job (runs daily at 2 AM)
(crontab -l 2>/dev/null | grep -v "backup_all.sh"; echo "0 2 * * * $SCRIPT_DIR/backup_all.sh >> /tmp/crypto_backup.log 2>&1") | crontab -

echo "✅ Cron job added: Daily backups at 2:00 AM"
echo "View scheduled jobs: crontab -l"
echo "View backup logs: tail -f /tmp/crypto_backup.log"
