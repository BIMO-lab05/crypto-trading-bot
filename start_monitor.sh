#!/bin/bash
# =============================================================================
# Confidence Monitor Launcher
# =============================================================================
# Starts the real-time trading confidence monitor
# Usage: ./start_monitor.sh [foreground|background]
# =============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Monitor script location
MONITOR_SCRIPT="monitor_confidence.py"
PID_FILE="/tmp/confidence_monitor.pid"
LOG_FILE="/tmp/confidence_monitor.log"

# =============================================================================
# Functions
# =============================================================================

start_foreground() {
    echo -e "${GREEN}Starting Confidence Monitor (foreground mode)...${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"
    python3 "$MONITOR_SCRIPT"
}

start_background() {
    # Check if already running
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Monitor already running with PID: $PID${NC}"
            echo -e "${BLUE}View logs: tail -f $LOG_FILE${NC}"
            echo -e "${BLUE}Stop monitor: ./start_monitor.sh stop${NC}"
            exit 0
        fi
    fi

    echo -e "${GREEN}Starting Confidence Monitor (background mode)...${NC}"
    nohup python3 "$MONITOR_SCRIPT" > "$LOG_FILE" 2>&1 &
    PID=$!
    echo $PID > "$PID_FILE"

    sleep 1

    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Monitor started successfully (PID: $PID)${NC}"
        echo -e "${BLUE}View logs:  tail -f $LOG_FILE${NC}"
        echo -e "${BLUE}Stop monitor: ./start_monitor.sh stop${NC}"
    else
        echo -e "${RED}✗ Failed to start monitor${NC}"
        rm -f "$PID_FILE"
        exit 1
    fi
}

stop_background() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}No monitor is running${NC}"
        exit 0
    fi

    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${YELLOW}Stopping monitor (PID: $PID)...${NC}"
        kill "$PID"
        rm -f "$PID_FILE"
        echo -e "${GREEN}✓ Monitor stopped${NC}"
    else
        echo -e "${YELLOW}Monitor not running (stale PID file removed)${NC}"
        rm -f "$PID_FILE"
    fi
}

show_status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Monitor is running (PID: $PID)${NC}"
            echo -e "${BLUE}Log file: $LOG_FILE${NC}"

            # Show last few lines of log
            if [ -f "$LOG_FILE" ]; then
                echo -e "\n${BLUE}Recent activity:${NC}"
                tail -n 5 "$LOG_FILE"
            fi
        else
            echo -e "${RED}✗ Monitor not running (stale PID file)${NC}"
            rm -f "$PID_FILE"
        fi
    else
        echo -e "${YELLOW}Monitor is not running${NC}"
    fi
}

show_help() {
    cat << EOF
${GREEN}Confidence Monitor - Usage Guide${NC}

${BLUE}Start monitor:${NC}
  ./start_monitor.sh                 # Foreground (see output in terminal)
  ./start_monitor.sh foreground      # Same as above
  ./start_monitor.sh background      # Background (runs in background)
  ./start_monitor.sh bg              # Short form

${BLUE}Control monitor:${NC}
  ./start_monitor.sh stop            # Stop background monitor
  ./start_monitor.sh status          # Check if monitor is running
  ./start_monitor.sh help            # Show this help

${BLUE}View logs (background mode):${NC}
  tail -f $LOG_FILE

${BLUE}What it does:${NC}
  - Monitors trading system logs in real-time
  - Alerts when confidence levels improve:
    ${YELLOW}⚠️  50%+ = Getting Interesting${NC}
    ${BLUE}🔔 60%+ = Getting Close to Trade${NC}
    ${GREEN}🚀 65%+ = TRADE WILL EXECUTE!${NC}
  - Notifies on market regime changes
  - Shows trade executions
  - Tracks highest confidence per symbol

${BLUE}Examples:${NC}
  # Watch in terminal (recommended for first time):
  ./start_monitor.sh

  # Run in background while you work:
  ./start_monitor.sh background
  tail -f $LOG_FILE

  # Check status:
  ./start_monitor.sh status

  # Stop background monitor:
  ./start_monitor.sh stop

EOF
}

# =============================================================================
# Main
# =============================================================================

# Check if monitor script exists
if [ ! -f "$MONITOR_SCRIPT" ]; then
    echo -e "${RED}Error: Monitor script not found: $MONITOR_SCRIPT${NC}"
    exit 1
fi

# Parse command
case "${1:-foreground}" in
    foreground|fg|"")
        start_foreground
        ;;
    background|bg)
        start_background
        ;;
    stop)
        stop_background
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        show_help
        exit 1
        ;;
esac
