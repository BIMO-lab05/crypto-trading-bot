#!/usr/bin/env python3
"""
Real-Time Trading Confidence Monitor
=====================================
Monitors trading system logs and sends notifications when confidence levels improve.

Features:
- Real-time log monitoring
- Confidence level tracking per symbol
- Alert thresholds: 50%, 60%, 65%+ (trade execution)
- Market regime change detection
- Trade execution notifications
- Color-coded terminal output
- Sound alerts (optional)

Usage:
    python3 monitor_confidence.py

Author: Trading System
Date: 2026-01-08
"""

import subprocess
import re
import sys
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, Optional
import json

# ============================================================================
# CONFIGURATION
# ============================================================================

# Alert thresholds (confidence levels)
THRESHOLD_LOW = 0.50      # Warning: Getting interesting
THRESHOLD_MEDIUM = 0.60   # Alert: Getting close to trade
THRESHOLD_HIGH = 0.65     # Critical: Trade will execute!

# Container name
CONTAINER_NAME = "crypto-bot-trading"

# Notification settings
ENABLE_SOUND = True       # Beep on high confidence
ENABLE_COLORS = True      # Color-coded output

# Track highest confidence per symbol
highest_confidence: Dict[str, float] = defaultdict(float)
last_regime: Optional[str] = None

# ============================================================================
# TERMINAL COLORS (if enabled)
# ============================================================================

if ENABLE_COLORS:
    class Colors:
        RESET = '\033[0m'
        RED = '\033[91m'
        GREEN = '\033[92m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        MAGENTA = '\033[95m'
        CYAN = '\033[96m'
        WHITE = '\033[97m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'
else:
    class Colors:
        RESET = ''
        RED = ''
        GREEN = ''
        YELLOW = ''
        BLUE = ''
        MAGENTA = ''
        CYAN = ''
        WHITE = ''
        BOLD = ''
        UNDERLINE = ''

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def beep():
    """Play system beep (if enabled)"""
    if ENABLE_SOUND:
        try:
            print('\a', end='', flush=True)  # ASCII bell character
        except:
            pass

def format_timestamp() -> str:
    """Get formatted timestamp"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def print_header():
    """Print monitoring header"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}🔔 REAL-TIME TRADING CONFIDENCE MONITOR{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")
    print(f"{Colors.WHITE}Started: {format_timestamp()}{Colors.RESET}")
    print(f"{Colors.WHITE}Container: {CONTAINER_NAME}{Colors.RESET}")
    print(f"\n{Colors.BOLD}Alert Thresholds:{Colors.RESET}")
    print(f"  {Colors.YELLOW}⚠️  50%+ = Getting Interesting{Colors.RESET}")
    print(f"  {Colors.MAGENTA}🔔 60%+ = Getting Close to Trade{Colors.RESET}")
    print(f"  {Colors.GREEN}🚀 65%+ = TRADE WILL EXECUTE!{Colors.RESET}")
    print(f"\n{Colors.CYAN}{'-'*80}{Colors.RESET}\n")

def print_confidence_alert(symbol: str, confidence: float, signal: str, score: float, consensus: str):
    """Print formatted confidence alert"""
    timestamp = format_timestamp()
    conf_pct = confidence * 100

    # Determine alert level and color
    if confidence >= THRESHOLD_HIGH:
        level = f"{Colors.GREEN}{Colors.BOLD}🚀 TRADE READY"
        color = Colors.GREEN
        beep()  # Alert on trade-ready confidence
    elif confidence >= THRESHOLD_MEDIUM:
        level = f"{Colors.MAGENTA}{Colors.BOLD}🔔 HIGH CONFIDENCE"
        color = Colors.MAGENTA
    elif confidence >= THRESHOLD_LOW:
        level = f"{Colors.YELLOW}{Colors.BOLD}⚠️  MEDIUM CONFIDENCE"
        color = Colors.YELLOW
    else:
        level = f"{Colors.WHITE}ℹ️  Low Confidence"
        color = Colors.WHITE

    # Check if this is a new high for this symbol
    prev_high = highest_confidence[symbol]
    is_new_high = confidence > prev_high

    if is_new_high:
        highest_confidence[symbol] = confidence
        new_high_marker = f" {Colors.BOLD}📈 NEW HIGH!{Colors.RESET}"
    else:
        new_high_marker = ""

    # Print alert
    print(f"{Colors.BOLD}[{timestamp}] {level}{Colors.RESET}")
    print(f"  {color}Symbol:{Colors.RESET}     {Colors.BOLD}{symbol}{Colors.RESET}")
    print(f"  {color}Confidence:{Colors.RESET} {Colors.BOLD}{conf_pct:.1f}%{Colors.RESET}{new_high_marker}")
    print(f"  {color}Signal:{Colors.RESET}     {signal} (score: {score:.2f})")
    print(f"  {color}Consensus:{Colors.RESET}  {consensus}")

    if confidence >= THRESHOLD_HIGH:
        print(f"  {Colors.GREEN}{Colors.BOLD}>>> SYSTEM WILL EXECUTE TRADE AT 65%+ <<<{Colors.RESET}")

    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}\n")

def print_regime_change(old_regime: str, new_regime: str):
    """Print market regime change notification"""
    timestamp = format_timestamp()
    print(f"{Colors.BOLD}{Colors.BLUE}[{timestamp}] 🔄 MARKET REGIME CHANGE{Colors.RESET}")
    print(f"  {Colors.WHITE}From:{Colors.RESET} {old_regime}")
    print(f"  {Colors.WHITE}To:{Colors.RESET}   {Colors.BOLD}{new_regime}{Colors.RESET}")
    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}\n")

def print_trade_execution(symbol: str, action: str):
    """Print trade execution notification"""
    timestamp = format_timestamp()
    beep()
    beep()  # Double beep for trade execution
    print(f"{Colors.BOLD}{Colors.GREEN}[{timestamp}] 💰 TRADE EXECUTED!{Colors.RESET}")
    print(f"  {Colors.GREEN}Symbol:{Colors.RESET} {Colors.BOLD}{symbol}{Colors.RESET}")
    print(f"  {Colors.GREEN}Action:{Colors.RESET} {Colors.BOLD}{action}{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

def print_summary():
    """Print summary of highest confidence levels seen"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}📊 CONFIDENCE SUMMARY{Colors.RESET}")
    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}")

    if not highest_confidence:
        print(f"{Colors.WHITE}No signals detected yet...{Colors.RESET}\n")
        return

    # Sort by confidence (highest first)
    sorted_symbols = sorted(highest_confidence.items(), key=lambda x: x[1], reverse=True)

    for symbol, conf in sorted_symbols:
        conf_pct = conf * 100

        # Color based on confidence level
        if conf >= THRESHOLD_HIGH:
            color = Colors.GREEN
            marker = "🚀"
        elif conf >= THRESHOLD_MEDIUM:
            color = Colors.MAGENTA
            marker = "🔔"
        elif conf >= THRESHOLD_LOW:
            color = Colors.YELLOW
            marker = "⚠️ "
        else:
            color = Colors.WHITE
            marker = "ℹ️ "

        print(f"  {marker} {color}{symbol:10s}{Colors.RESET} - Highest: {color}{Colors.BOLD}{conf_pct:5.1f}%{Colors.RESET}")

    print(f"{Colors.CYAN}{'-'*80}{Colors.RESET}\n")

# ============================================================================
# LOG PARSING
# ============================================================================

def parse_signal_line(line: str) -> Optional[Dict]:
    """
    Parse a 'Final Signal' log line

    Example input:
    "Final Signal: BUY (score: 0.85, conf: 0.72, consensus: 6/7)"

    Returns:
    {
        'signal': 'BUY',
        'score': 0.85,
        'confidence': 0.72,
        'consensus': '6/7'
    }
    """
    # Pattern: Final Signal: <SIGNAL> (score: <float>, conf: <float>, consensus: <x>/<y>)
    pattern = r'Final Signal:\s*(\w+)\s*\(score:\s*([-\d.]+),\s*conf:\s*([\d.]+),\s*consensus:\s*(\d+/\d+)\)'
    match = re.search(pattern, line)

    if match:
        return {
            'signal': match.group(1),
            'score': float(match.group(2)),
            'confidence': float(match.group(3)),
            'consensus': match.group(4)
        }
    return None

def extract_symbol(line: str) -> Optional[str]:
    """
    Extract symbol from log line

    Example: "[RESEARCH] Checking signal for BTCUSDT"
    Returns: "BTCUSDT"
    """
    # Try multiple patterns
    patterns = [
        r'Checking signal for\s+(\w+)',
        r'No valid trade setup for\s+(\w+)',
        r'Opening position for\s+(\w+)',
        r'signal for\s+(\w+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return match.group(1)

    return None

def parse_regime(line: str) -> Optional[str]:
    """
    Parse market regime from log line

    Example: "Market regime: TRENDING"
    Returns: "TRENDING"
    """
    pattern = r'Market regime:\s*(\w+)'
    match = re.search(pattern, line)
    if match:
        return match.group(1)
    return None

def detect_trade_execution(line: str) -> Optional[Dict]:
    """
    Detect trade execution in logs

    Example: "Opening position for BTCUSDT: BUY"
    Returns: {'symbol': 'BTCUSDT', 'action': 'BUY'}
    """
    patterns = [
        r'Opening position for\s+(\w+):\s*(\w+)',
        r'EXECUTING\s+(\w+)\s+for\s+(\w+)',
        r'Trade executed:\s+(\w+)\s+(\w+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, line)
        if match:
            return {
                'symbol': match.group(1),
                'action': match.group(2)
            }

    return None

# ============================================================================
# MAIN MONITORING LOOP
# ============================================================================

def monitor_logs():
    """Main monitoring loop - tail docker logs and parse in real-time"""
    global last_regime

    print_header()

    try:
        # Start docker logs process
        cmd = ['docker', 'logs', '-f', '--tail', '0', CONTAINER_NAME]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        print(f"{Colors.WHITE}Monitoring logs... (Press Ctrl+C to stop){Colors.RESET}\n")

        current_symbol = None

        # Process each log line in real-time
        for line in process.stdout:
            line = line.strip()

            if not line:
                continue

            # Extract symbol from current line
            symbol = extract_symbol(line)
            if symbol:
                current_symbol = symbol

            # Check for final signal
            signal_data = parse_signal_line(line)
            if signal_data and current_symbol:
                conf = signal_data['confidence']

                # Only alert if confidence is >= 50% (to reduce noise)
                if conf >= THRESHOLD_LOW:
                    print_confidence_alert(
                        current_symbol,
                        conf,
                        signal_data['signal'],
                        signal_data['score'],
                        signal_data['consensus']
                    )

            # Check for market regime change
            regime = parse_regime(line)
            if regime and regime != last_regime:
                if last_regime is not None:  # Don't alert on first detection
                    print_regime_change(last_regime, regime)
                last_regime = regime

            # Check for trade execution
            trade = detect_trade_execution(line)
            if trade:
                print_trade_execution(trade['symbol'], trade['action'])

    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Monitoring stopped by user{Colors.RESET}")
        print_summary()
    except FileNotFoundError:
        print(f"{Colors.RED}Error: Docker command not found. Is Docker installed?{Colors.RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")
        sys.exit(1)

# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    # Check if docker container is running
    try:
        result = subprocess.run(
            ['docker', 'ps', '--filter', f'name={CONTAINER_NAME}', '--format', '{{.Names}}'],
            capture_output=True,
            text=True,
            check=True
        )

        if CONTAINER_NAME not in result.stdout:
            print(f"{Colors.RED}Error: Container '{CONTAINER_NAME}' is not running{Colors.RESET}")
            print(f"{Colors.YELLOW}Start it with: docker-compose up -d trading-engine{Colors.RESET}")
            sys.exit(1)
    except Exception as e:
        print(f"{Colors.RED}Error checking Docker: {e}{Colors.RESET}")
        sys.exit(1)

    # Start monitoring
    monitor_logs()
