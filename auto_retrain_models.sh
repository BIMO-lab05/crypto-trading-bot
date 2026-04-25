#!/bin/bash
# Automated ML Model Retraining Script
# Purpose: Retrain all core ML models weekly to maintain prediction accuracy
# Recommended: Run via cron every Sunday at 2 AM
# Cron: 0 2 * * 0 /path/to/auto_retrain_models.sh >> /var/log/model_retrain.log 2>&1

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ML_SERVICE="http://localhost:8007"
LOOKBACK_DAYS=90
INTERVAL="60"
LOG_FILE="/mnt/d/Bimo_max/crypto-trading-bot/logs/model_retraining.log"

# Core trading symbols (update this list as needed)
CORE_SYMBOLS=(
    "BTCUSDT"
    "BNBUSDT"
    "SOLUSDT"
    "ADAUSDT"
    "AVAXUSDT"
    "LINKUSDT"
)

# Create log directory if it doesn't exist
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Function to retrain a single model
retrain_model() {
    local symbol=$1

    log_message "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_message "Retraining model: $symbol"

    # Make API call to retrain model
    response=$(curl -s -X POST "$ML_SERVICE/api/v1/models/train" \
        -H "Content-Type: application/json" \
        -d "{\"symbol\": \"$symbol\", \"interval\": \"$INTERVAL\", \"lookback_days\": $LOOKBACK_DAYS}" \
        --max-time 300)

    if [ $? -eq 0 ]; then
        # Parse response
        success=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('success', False))" 2>/dev/null)

        if [ "$success" = "True" ]; then
            accuracy=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"{data.get('model_info', {}).get('validation_accuracy', 0)*100:.1f}%\")" 2>/dev/null)
            duration=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('training_duration_seconds', 0))" 2>/dev/null)

            log_message "✅ SUCCESS: $symbol trained successfully"
            log_message "   Accuracy: $accuracy"
            log_message "   Duration: ${duration}s"
            return 0
        else
            error=$(echo "$response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null)
            log_message "❌ FAILED: $symbol training failed - $error"
            return 1
        fi
    else
        log_message "❌ FAILED: $symbol - API request failed (timeout or network error)"
        return 1
    fi
}

# Function to send notification (if notification service is available)
send_notification() {
    local title="$1"
    local message="$2"
    local level="${3:-info}"

    curl -s -X POST "http://localhost:8006/api/v1/notify/system" \
        -H "Content-Type: application/json" \
        -d "{\"title\": \"$title\", \"message\": \"$message\", \"level\": \"$level\"}" \
        --max-time 5 > /dev/null 2>&1
}

# Main execution
main() {
    log_message "╔═══════════════════════════════════════════════════════════════╗"
    log_message "║        AUTOMATED ML MODEL RETRAINING - WEEKLY SCHEDULE       ║"
    log_message "╔═══════════════════════════════════════════════════════════════╗"
    log_message ""

    # Check if ML service is available
    health_check=$(curl -s --max-time 5 "$ML_SERVICE/health" 2>/dev/null)
    if [ $? -ne 0 ]; then
        log_message "❌ CRITICAL: ML Prediction service is not available at $ML_SERVICE"
        send_notification "Model Retraining Failed" "ML service unavailable" "error"
        exit 1
    fi

    log_message "✅ ML Prediction service is healthy"
    log_message "Configuration:"
    log_message "  - Lookback days: $LOOKBACK_DAYS"
    log_message "  - Interval: ${INTERVAL}m"
    log_message "  - Models to retrain: ${#CORE_SYMBOLS[@]}"
    log_message ""

    # Track statistics
    total_models=${#CORE_SYMBOLS[@]}
    successful=0
    failed=0
    start_time=$(date +%s)

    # Retrain each model
    for symbol in "${CORE_SYMBOLS[@]}"; do
        if retrain_model "$symbol"; then
            ((successful++))
        else
            ((failed++))
        fi

        # Small delay between retraining to avoid overloading
        sleep 5
    done

    # Calculate duration
    end_time=$(date +%s)
    total_duration=$((end_time - start_time))

    log_message ""
    log_message "╔═══════════════════════════════════════════════════════════════╗"
    log_message "║                    RETRAINING SUMMARY                         ║"
    log_message "╚═══════════════════════════════════════════════════════════════╝"
    log_message "Total models: $total_models"
    log_message "✅ Successful: $successful"
    log_message "❌ Failed: $failed"
    log_message "⏱️  Total duration: ${total_duration}s"
    log_message ""

    # Send summary notification
    if [ $failed -eq 0 ]; then
        log_message "🎉 All models retrained successfully!"
        send_notification "Model Retraining Complete" "All $successful models trained successfully" "success"
        exit 0
    else
        log_message "⚠️  Some models failed to retrain. Check logs for details."
        send_notification "Model Retraining Partial" "$successful/$total_models models trained. $failed failed." "warning"
        exit 1
    fi
}

# Run main function
main
