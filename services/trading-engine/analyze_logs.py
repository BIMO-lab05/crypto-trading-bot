#!/usr/bin/env python3
"""
Trading Log Analyzer
Purpose: Analyze historical trading logs to identify patterns, errors, and decision quality
Usage: python analyze_logs.py [--log-file logs/service.log] [--errors-only]
"""

import re
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from typing import Dict, List, Tuple


class LogAnalyzer:
    """Analyze trading engine logs"""

    def __init__(self, log_file: str):
        self.log_file = Path(log_file)
        self.signals_analyzed = []
        self.errors = []
        self.warnings = []
        self.http_requests = []
        self.indicator_results = defaultdict(list)

    def parse_log_file(self):
        """Parse the entire log file"""
        if not self.log_file.exists():
            print(f"❌ Log file not found: {self.log_file}")
            return False

        print(f"📖 Reading log file: {self.log_file}")
        print(f"   Size: {self.log_file.stat().st_size / 1024:.2f} KB\n")

        with open(self.log_file, 'r') as f:
            for line in f:
                self.parse_line(line)

        print(f"✅ Parsed {sum(len(v) for v in self.indicator_results.values())} log entries\n")
        return True

    def parse_line(self, line: str):
        """Parse a single log line"""
        # Extract timestamp
        timestamp_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
        if not timestamp_match:
            return

        timestamp = timestamp_match.group(1)

        # Categorize log entries
        if "ERROR" in line:
            self.errors.append((timestamp, line.strip()))
        elif "WARNING" in line or "⚠️" in line:
            self.warnings.append((timestamp, line.strip()))

        # Parse indicator results
        if "✓ RSI:" in line:
            signal_match = re.search(r'RSI: (\w+) \(conf: ([\d.]+)\)', line)
            if signal_match:
                self.indicator_results['RSI'].append({
                    'timestamp': timestamp,
                    'signal': signal_match.group(1),
                    'confidence': float(signal_match.group(2))
                })

        elif "✓ MACD:" in line:
            signal_match = re.search(r'MACD: (\w+) \(conf: ([\d.]+)\)', line)
            if signal_match:
                self.indicator_results['MACD'].append({
                    'timestamp': timestamp,
                    'signal': signal_match.group(1),
                    'confidence': float(signal_match.group(2))
                })

        elif "✓ BOLLINGER_BANDS:" in line:
            signal_match = re.search(r'BOLLINGER_BANDS: (\w+) \(conf: ([\d.]+)\)', line)
            if signal_match:
                self.indicator_results['BOLLINGER_BANDS'].append({
                    'timestamp': timestamp,
                    'signal': signal_match.group(1),
                    'confidence': float(signal_match.group(2))
                })

        elif "✓ SMA:" in line:
            signal_match = re.search(r'SMA: (\w+) \(conf: ([\d.]+)\)', line)
            if signal_match:
                self.indicator_results['SMA'].append({
                    'timestamp': timestamp,
                    'signal': signal_match.group(1),
                    'confidence': float(signal_match.group(2))
                })

        elif "✓ EMA:" in line:
            signal_match = re.search(r'EMA: (\w+) \(conf: ([\d.]+)\)', line)
            if signal_match:
                self.indicator_results['EMA'].append({
                    'timestamp': timestamp,
                    'signal': signal_match.group(1),
                    'confidence': float(signal_match.group(2))
                })

        # Parse aggregated signals
        elif "Aggregated Signal:" in line:
            agg_match = re.search(
                r'Aggregated Signal: (\w+) \(score: ([-\d.]+), conf: ([\d.]+), consensus: (\d+)/(\d+)\)',
                line
            )
            if agg_match:
                self.signals_analyzed.append({
                    'timestamp': timestamp,
                    'action': agg_match.group(1),
                    'score': float(agg_match.group(2)),
                    'confidence': float(agg_match.group(3)),
                    'consensus': int(agg_match.group(4)),
                    'total_indicators': int(agg_match.group(5))
                })

        # Parse HTTP requests
        elif "HTTP Request:" in line:
            http_match = re.search(r'GET (http://[^\s]+)', line)
            if http_match:
                url = http_match.group(1)
                self.http_requests.append({
                    'timestamp': timestamp,
                    'url': url
                })

    def print_summary(self):
        """Print analysis summary"""
        print("="*80)
        print("📊 LOG ANALYSIS SUMMARY")
        print("="*80)
        print()

        # General statistics
        print("📈 GENERAL STATISTICS:")
        print(f"   Signals Analyzed: {len(self.signals_analyzed)}")
        print(f"   HTTP Requests: {len(self.http_requests)}")
        print(f"   Errors: {len(self.errors)}")
        print(f"   Warnings: {len(self.warnings)}")
        print()

        # Signal distribution
        if self.signals_analyzed:
            print("🎯 SIGNAL DISTRIBUTION:")
            actions = [s['action'] for s in self.signals_analyzed]
            action_counts = Counter(actions)
            total = len(actions)

            for action, count in action_counts.most_common():
                percentage = (count / total) * 100
                print(f"   {action}: {count} ({percentage:.1f}%)")

            # Average confidence
            avg_confidence = sum(s['confidence'] for s in self.signals_analyzed) / len(self.signals_analyzed)
            print(f"\n   Average Confidence: {avg_confidence:.2%}")

            # Average score
            avg_score = sum(s['score'] for s in self.signals_analyzed) / len(self.signals_analyzed)
            print(f"   Average Score: {avg_score:+.3f}")

            # Consensus analysis
            avg_consensus = sum(s['consensus'] for s in self.signals_analyzed) / len(self.signals_analyzed)
            print(f"   Average Consensus: {avg_consensus:.1f} indicators")
            print()

        # Indicator performance
        if self.indicator_results:
            print("📊 INDICATOR PERFORMANCE:")
            print(f"{'Indicator':<20} {'Samples':<10} {'BUY':<8} {'SELL':<8} {'HOLD':<8} {'Avg Conf'}")
            print("-" * 80)

            for indicator, results in sorted(self.indicator_results.items()):
                if not results:
                    continue

                buy_count = sum(1 for r in results if r['signal'] == 'BUY')
                sell_count = sum(1 for r in results if r['signal'] == 'SELL')
                hold_count = sum(1 for r in results if r['signal'] == 'HOLD')
                avg_conf = sum(r['confidence'] for r in results) / len(results)

                print(
                    f"{indicator:<20} {len(results):<10} {buy_count:<8} {sell_count:<8} "
                    f"{hold_count:<8} {avg_conf:.2%}"
                )

            print()

        # Errors and warnings
        if self.errors:
            print(f"❌ ERRORS ({len(self.errors)}):")
            for timestamp, error in self.errors[-5:]:  # Show last 5
                # Truncate long error messages
                error_msg = error[:150] + "..." if len(error) > 150 else error
                print(f"   [{timestamp}] {error_msg}")
            print()

        if self.warnings:
            print(f"⚠️  WARNINGS ({len(self.warnings)}):")
            # Group warnings by type
            warning_types = defaultdict(int)
            for _, warning in self.warnings:
                if "Database connection failed" in warning:
                    warning_types["Database Connection"] += 1
                elif "Technical Analysis Service" in warning:
                    warning_types["TA Service"] += 1
                elif "Failed to persist" in warning:
                    warning_types["Persistence Failure"] += 1
                else:
                    warning_types["Other"] += 1

            for warning_type, count in warning_types.items():
                print(f"   {warning_type}: {count}")
            print()

        # API call patterns
        if self.http_requests:
            print("🌐 API CALL PATTERNS:")
            # Extract endpoint types
            endpoints = defaultdict(int)
            for req in self.http_requests:
                url = req['url']
                if '/health' in url:
                    endpoints['Health Check'] += 1
                elif '/indicators/rsi' in url:
                    endpoints['RSI'] += 1
                elif '/indicators/macd' in url:
                    endpoints['MACD'] += 1
                elif '/indicators/bollinger' in url:
                    endpoints['Bollinger Bands'] += 1
                elif '/indicators/sma' in url:
                    endpoints['SMA'] += 1
                elif '/indicators/ema' in url:
                    endpoints['EMA'] += 1
                else:
                    endpoints['Other'] += 1

            for endpoint, count in sorted(endpoints.items(), key=lambda x: x[1], reverse=True):
                print(f"   {endpoint}: {count}")
            print()

    def print_recent_signals(self, count: int = 5):
        """Print most recent trading signals"""
        if not self.signals_analyzed:
            print("No signals found in logs")
            return

        print(f"🕐 RECENT SIGNALS (last {count}):")
        print(f"{'Timestamp':<20} {'Action':<8} {'Score':<10} {'Confidence':<12} {'Consensus'}")
        print("-" * 80)

        for signal in self.signals_analyzed[-count:]:
            print(
                f"{signal['timestamp']:<20} "
                f"{signal['action']:<8} "
                f"{signal['score']:+.3f}     "
                f"{signal['confidence']:.2%}        "
                f"{signal['consensus']}/{signal['total_indicators']}"
            )
        print()

    def analyze_decision_quality(self):
        """Analyze quality of trading decisions"""
        if not self.signals_analyzed:
            return

        print("🎓 DECISION QUALITY ANALYSIS:")

        # High confidence signals (>=0.7)
        high_conf_signals = [s for s in self.signals_analyzed if s['confidence'] >= 0.7]
        print(f"   High Confidence (≥70%): {len(high_conf_signals)} ({len(high_conf_signals)/len(self.signals_analyzed)*100:.1f}%)")

        # Medium confidence signals (0.4-0.7)
        medium_conf_signals = [s for s in self.signals_analyzed if 0.4 <= s['confidence'] < 0.7]
        print(f"   Medium Confidence (40-70%): {len(medium_conf_signals)} ({len(medium_conf_signals)/len(self.signals_analyzed)*100:.1f}%)")

        # Low confidence signals (<0.4)
        low_conf_signals = [s for s in self.signals_analyzed if s['confidence'] < 0.4]
        print(f"   Low Confidence (<40%): {len(low_conf_signals)} ({len(low_conf_signals)/len(self.signals_analyzed)*100:.1f}%)")

        # Strong consensus (4+ indicators agree)
        strong_consensus = [s for s in self.signals_analyzed if s['consensus'] >= 4]
        print(f"\n   Strong Consensus (≥4): {len(strong_consensus)} ({len(strong_consensus)/len(self.signals_analyzed)*100:.1f}%)")

        # Weak consensus (2-3 indicators agree)
        weak_consensus = [s for s in self.signals_analyzed if 2 <= s['consensus'] <= 3]
        print(f"   Weak Consensus (2-3): {len(weak_consensus)} ({len(weak_consensus)/len(self.signals_analyzed)*100:.1f}%)")

        print()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Analyze trading engine logs"
    )
    parser.add_argument(
        "--log-file",
        default="logs/service.log",
        help="Path to log file (default: logs/service.log)"
    )
    parser.add_argument(
        "--errors-only",
        action="store_true",
        help="Show only errors"
    )
    parser.add_argument(
        "--recent",
        type=int,
        default=10,
        help="Number of recent signals to display (default: 10)"
    )

    args = parser.parse_args()

    # Create analyzer
    analyzer = LogAnalyzer(args.log_file)

    # Parse logs
    if not analyzer.parse_log_file():
        return 1

    # Display results
    if args.errors_only:
        if analyzer.errors:
            print(f"\n❌ ERRORS ({len(analyzer.errors)}):")
            for timestamp, error in analyzer.errors:
                print(f"[{timestamp}] {error}")
        else:
            print("✅ No errors found in logs")
    else:
        analyzer.print_summary()
        analyzer.print_recent_signals(args.recent)
        analyzer.analyze_decision_quality()

    return 0


if __name__ == "__main__":
    exit(main())
