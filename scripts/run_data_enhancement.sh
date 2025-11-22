#!/bin/bash
# Data Quality Enhancement - Quick Start Script
# Purpose: Automated execution with progress logging
# Date: 2025-11-20

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directories
SCRIPT_DIR="/mnt/d/Bimo_max/crypto-trading-bot/scripts"
REPORT_DIR="/mnt/d/Bimo_max/crypto-trading-bot/reports"
LOG_DIR="/mnt/d/Bimo_max/crypto-trading-bot/logs"

# Create directories if they don't exist
mkdir -p "$REPORT_DIR"
mkdir -p "$LOG_DIR"

# Log file
LOG_FILE="$LOG_DIR/data_enhancement_$(date +%Y%m%d_%H%M%S).log"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Data Quality Enhancement Process${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to log messages
log() {
    echo -e "$1" | tee -a "$LOG_FILE"
}

log "${YELLOW}[Step 1/5] Checking prerequisites...${NC}"

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    log "${RED}✗ Python 3 not found. Please install Python 3.${NC}"
    exit 1
fi
log "${GREEN}✓ Python 3 found${NC}"

# Check if pip is available
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    log "${RED}✗ pip not found. Please install pip.${NC}"
    exit 1
fi
log "${GREEN}✓ pip found${NC}"

log ""
log "${YELLOW}[Step 2/5] Installing dependencies...${NC}"

# Install dependencies
if [ -f "$SCRIPT_DIR/requirements_data_enhancement.txt" ]; then
    pip3 install -q -r "$SCRIPT_DIR/requirements_data_enhancement.txt"
    log "${GREEN}✓ Dependencies installed${NC}"
else
    log "${RED}✗ Requirements file not found: $SCRIPT_DIR/requirements_data_enhancement.txt${NC}"
    exit 1
fi

log ""
log "${YELLOW}[Step 3/5] Testing database connection...${NC}"

# Test database connection
if python3 "$SCRIPT_DIR/test_db_connection.py" >> "$LOG_FILE" 2>&1; then
    log "${GREEN}✓ Database connection successful${NC}"
else
    log "${RED}✗ Database connection failed. Check logs: $LOG_FILE${NC}"
    log "${YELLOW}  Troubleshooting:${NC}"
    log "  1. Ensure TimescaleDB is running: docker ps"
    log "  2. Verify connection parameters in data_quality_enhancement.py"
    log "  3. Check if port 5433 is accessible"
    exit 1
fi

log ""
log "${YELLOW}[Step 4/5] Running data quality enhancement...${NC}"
log "${BLUE}This may take 5-10 minutes. Please wait...${NC}"
log ""

# Run main enhancement script
START_TIME=$(date +%s)

if python3 "$SCRIPT_DIR/data_quality_enhancement.py" 2>&1 | tee -a "$LOG_FILE"; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    log ""
    log "${GREEN}✓ Data enhancement completed in ${DURATION} seconds${NC}"
else
    log "${RED}✗ Enhancement failed. Check logs: $LOG_FILE${NC}"
    exit 1
fi

log ""
log "${YELLOW}[Step 5/5] Generating summary...${NC}"

# Check if report was generated
REPORT_FILE="$REPORT_DIR/data_quality_report.md"
if [ -f "$REPORT_FILE" ]; then
    log "${GREEN}✓ Quality report generated: $REPORT_FILE${NC}"

    # Display summary
    log ""
    log "${BLUE}========================================${NC}"
    log "${BLUE}  Enhancement Summary${NC}"
    log "${BLUE}========================================${NC}"

    # Extract ML-ready count from report
    if grep -q "ML-Ready Symbols" "$REPORT_FILE"; then
        ML_READY=$(grep "ML-Ready Symbols" "$REPORT_FILE" | head -n 1)
        log "$ML_READY"
    fi

    log ""
    log "${GREEN}✓ All steps completed successfully!${NC}"
    log ""
    log "${BLUE}Next steps:${NC}"
    log "  1. Review report: cat $REPORT_FILE"
    log "  2. Retrain ML models: python3 services/ml-prediction-service/train_models.py"
    log "  3. Validate improvements: check R² scores"
    log ""
    log "${BLUE}Logs saved to: $LOG_FILE${NC}"
else
    log "${YELLOW}⚠ Report file not found (may have been generated elsewhere)${NC}"
fi

log ""
log "${BLUE}========================================${NC}"
log "${BLUE}  Process Complete${NC}"
log "${BLUE}========================================${NC}"

exit 0
