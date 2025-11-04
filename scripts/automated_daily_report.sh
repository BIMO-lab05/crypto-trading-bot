#!/bin/bash
# Automated Daily Report Generator
# Runs daily report and saves to logs with timestamp

# Set working directory
cd /mnt/d/Bimo_max/crypto-trading-bot

# Create reports directory if it doesn't exist
mkdir -p logs/daily_reports

# Generate timestamp
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
REPORT_FILE="logs/daily_reports/report_${TIMESTAMP}.txt"

# Generate report
echo "Generating daily trading report..."
python3 scripts/daily_report.py > "$REPORT_FILE" 2>&1

# Check if report was generated successfully
if [ $? -eq 0 ]; then
    echo "✅ Report generated successfully: $REPORT_FILE"

    # Keep only last 30 days of reports (cleanup)
    find logs/daily_reports -name "report_*.txt" -mtime +30 -delete

    # Optional: Send email notification (uncomment if configured)
    # mail -s "Trading Bot Daily Report" your-email@example.com < "$REPORT_FILE"
else
    echo "❌ Report generation failed"
    exit 1
fi
