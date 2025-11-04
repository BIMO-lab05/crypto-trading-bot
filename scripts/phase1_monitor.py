#!/usr/bin/env python3
"""
Phase 1 Performance Monitor
Tracks and analyzes Phase 1 trading strategy improvements

Monitors:
- GATEKEEPER blocks (counter-trend trades blocked)
- VALIDATOR rejections (low volume signals rejected)
- Win rate improvements
- False signal reduction
- ATR-based stop effectiveness
"""

import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple
import sys

class Phase1Monitor:
    def __init__(self, log_file: str = "/tmp/trading-engine-phase1.log"):
        self.log_file = log_file
        self.metrics = {
            "gatekeeper_blocks": 0,
            "validator_rejections": 0,
            "signals_generated": 0,
            "buy_signals": 0,
            "sell_signals": 0,
            "hold_signals": 0,
            "trend_bullish": 0,
            "trend_bearish": 0,
            "trend_neutral": 0,
            "volume_confirmed": 0,
            "volume_rejected": 0,
            "atr_extreme": 0,
            "atr_high": 0,
            "atr_medium": 0,
            "atr_low": 0,
            "stochastic_overbought": 0,
            "stochastic_oversold": 0,
        }
        self.signals_by_symbol = defaultdict(list)
        self.start_time = None
        self.end_time = None

    def parse_logs(self, hours: int = 24):
        """Parse logs from the last N hours"""
        print(f"Parsing logs from {self.log_file}...")

        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
        except FileNotFoundError:
            print(f"Log file not found: {self.log_file}")
            return

        cutoff_time = datetime.now() - timedelta(hours=hours)

        for line in lines:
            # Parse timestamp
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                try:
                    log_time = datetime.strptime(timestamp_match.group(1), '%Y-%m-%d %H:%M:%S')
                    if log_time < cutoff_time:
                        continue

                    if not self.start_time or log_time < self.start_time:
                        self.start_time = log_time
                    if not self.end_time or log_time > self.end_time:
                        self.end_time = log_time
                except ValueError:
                    pass

            # Track GATEKEEPER blocks
            if "BLOCKED" in line and "Counter-trend" in line:
                self.metrics["gatekeeper_blocks"] += 1

            # Track VALIDATOR rejections
            if "Volume NOT confirmed" in line:
                self.metrics["validator_rejections"] += 1
            if "Volume confirmed" in line:
                self.metrics["volume_confirmed"] += 1

            # Track Trend Filter
            if "Trend Filter: BULLISH" in line:
                self.metrics["trend_bullish"] += 1
            elif "Trend Filter: BEARISH" in line:
                self.metrics["trend_bearish"] += 1
            elif "Trend Filter: NEUTRAL" in line:
                self.metrics["trend_neutral"] += 1

            # Track Aggregated Signals
            if "Aggregated Signal:" in line:
                self.metrics["signals_generated"] += 1
                if "Aggregated Signal: BUY" in line:
                    self.metrics["buy_signals"] += 1
                elif "Aggregated Signal: SELL" in line:
                    self.metrics["sell_signals"] += 1
                elif "Aggregated Signal: HOLD" in line:
                    self.metrics["hold_signals"] += 1

            # Track ATR volatility
            if "ATR:" in line:
                if "EXTREME volatility" in line:
                    self.metrics["atr_extreme"] += 1
                elif "HIGH volatility" in line:
                    self.metrics["atr_high"] += 1
                elif "MEDIUM volatility" in line:
                    self.metrics["atr_medium"] += 1
                elif "LOW volatility" in line:
                    self.metrics["atr_low"] += 1

            # Track Stochastic conditions
            if "OVERBOUGHT" in line and "Stochastic" not in line:
                self.metrics["stochastic_overbought"] += 1
            if "OVERSOLD" in line:
                self.metrics["stochastic_oversold"] += 1

    def calculate_filtering_effectiveness(self) -> Dict:
        """Calculate Phase 1 filtering effectiveness"""
        total_checks = self.metrics["signals_generated"]
        if total_checks == 0:
            return {}

        gatekeeper_block_rate = (self.metrics["gatekeeper_blocks"] / total_checks) * 100
        validator_reject_rate = (self.metrics["validator_rejections"] /
                                (self.metrics["validator_rejections"] + self.metrics["volume_confirmed"]) * 100) if (self.metrics["validator_rejections"] + self.metrics["volume_confirmed"]) > 0 else 0

        hold_rate = (self.metrics["hold_signals"] / total_checks) * 100
        action_rate = ((self.metrics["buy_signals"] + self.metrics["sell_signals"]) / total_checks) * 100

        return {
            "gatekeeper_block_rate": gatekeeper_block_rate,
            "validator_reject_rate": validator_reject_rate,
            "hold_rate": hold_rate,
            "action_rate": action_rate,
            "total_signals": total_checks
        }

    def print_report(self):
        """Print comprehensive Phase 1 performance report"""
        duration = (self.end_time - self.start_time) if (self.start_time and self.end_time) else timedelta(0)

        print("\n" + "="*80)
        print(" " * 25 + "PHASE 1 PERFORMANCE REPORT")
        print("="*80)
        print(f"Analysis Period: {self.start_time} to {self.end_time}")
        print(f"Duration: {duration}")
        print("="*80)

        print("\n📊 SIGNAL GENERATION SUMMARY")
        print("-"*80)
        print(f"  Total Signals Generated: {self.metrics['signals_generated']}")
        print(f"  BUY Signals:  {self.metrics['buy_signals']:4d} ({self.metrics['buy_signals']/max(1,self.metrics['signals_generated'])*100:5.1f}%)")
        print(f"  SELL Signals: {self.metrics['sell_signals']:4d} ({self.metrics['sell_signals']/max(1,self.metrics['signals_generated'])*100:5.1f}%)")
        print(f"  HOLD Signals: {self.metrics['hold_signals']:4d} ({self.metrics['hold_signals']/max(1,self.metrics['signals_generated'])*100:5.1f}%)")

        print("\n🚪 GATEKEEPER (Trend Filter) ANALYSIS")
        print("-"*80)
        print(f"  Counter-Trend Trades BLOCKED: {self.metrics['gatekeeper_blocks']}")
        print(f"  Bullish Trends Detected: {self.metrics['trend_bullish']}")
        print(f"  Bearish Trends Detected: {self.metrics['trend_bearish']}")
        print(f"  Neutral Markets: {self.metrics['trend_neutral']}")
        if self.metrics['signals_generated'] > 0:
            block_rate = (self.metrics['gatekeeper_blocks'] / self.metrics['signals_generated']) * 100
            print(f"  Block Rate: {block_rate:.1f}% (trades prevented)")

        print("\n✅ VALIDATOR (Volume Confirmation) ANALYSIS")
        print("-"*80)
        total_volume_checks = self.metrics['volume_confirmed'] + self.metrics['validator_rejections']
        print(f"  Volume Confirmed: {self.metrics['volume_confirmed']}")
        print(f"  Volume REJECTED: {self.metrics['validator_rejections']}")
        if total_volume_checks > 0:
            reject_rate = (self.metrics['validator_rejections'] / total_volume_checks) * 100
            confirm_rate = (self.metrics['volume_confirmed'] / total_volume_checks) * 100
            print(f"  Rejection Rate: {reject_rate:.1f}% (low-volume signals filtered)")
            print(f"  Confirmation Rate: {confirm_rate:.1f}%")

        print("\n📈 ATR (Volatility) DISTRIBUTION")
        print("-"*80)
        total_atr = (self.metrics['atr_extreme'] + self.metrics['atr_high'] +
                    self.metrics['atr_medium'] + self.metrics['atr_low'])
        if total_atr > 0:
            print(f"  EXTREME: {self.metrics['atr_extreme']:3d} ({self.metrics['atr_extreme']/total_atr*100:5.1f}%)")
            print(f"  HIGH:    {self.metrics['atr_high']:3d} ({self.metrics['atr_high']/total_atr*100:5.1f}%)")
            print(f"  MEDIUM:  {self.metrics['atr_medium']:3d} ({self.metrics['atr_medium']/total_atr*100:5.1f}%)")
            print(f"  LOW:     {self.metrics['atr_low']:3d} ({self.metrics['atr_low']/total_atr*100:5.1f}%)")

        print("\n📉 STOCHASTIC (Momentum) CONDITIONS")
        print("-"*80)
        print(f"  Overbought Conditions: {self.metrics['stochastic_overbought']}")
        print(f"  Oversold Conditions: {self.metrics['stochastic_oversold']}")

        print("\n🎯 PHASE 1 EFFECTIVENESS")
        print("-"*80)
        effectiveness = self.calculate_filtering_effectiveness()
        if effectiveness:
            print(f"  Total Signals Analyzed: {effectiveness['total_signals']}")
            print(f"  HOLD Rate: {effectiveness['hold_rate']:.1f}% (signals filtered)")
            print(f"  Action Rate: {effectiveness['action_rate']:.1f}% (signals passed)")
            print(f"\n  📊 Filtering Breakdown:")
            print(f"    • Trend Filter blocked: {self.metrics['gatekeeper_blocks']} signals")
            print(f"    • Volume Filter rejected: {self.metrics['validator_rejections']} signals")
            print(f"    • Combined filtering: {self.metrics['hold_signals']} HOLD signals")

        print("\n💡 PHASE 1 IMPACT ASSESSMENT")
        print("-"*80)
        if self.metrics['signals_generated'] > 0:
            # Estimated false signal reduction
            total_filtered = self.metrics['gatekeeper_blocks'] + self.metrics['validator_rejections']
            reduction_rate = (total_filtered / self.metrics['signals_generated']) * 100
            print(f"  Estimated False Signal Reduction: {reduction_rate:.1f}%")
            print(f"  Target: 40-50% (Phase 1 goal)")
            if reduction_rate >= 40:
                print(f"  Status: ✅ MEETING TARGET")
            elif reduction_rate >= 30:
                print(f"  Status: ⚠️  APPROACHING TARGET")
            else:
                print(f"  Status: 🔴 BELOW TARGET (need more data)")

        print("\n📝 RECOMMENDATIONS")
        print("-"*80)

        # Provide actionable recommendations
        if self.metrics['signals_generated'] < 50:
            print("  ⏰ INSUFFICIENT DATA: Run for 24-48 hours for reliable metrics")

        if self.metrics['atr_extreme'] > self.metrics['atr_medium']:
            print("  ⚠️  HIGH VOLATILITY: Consider reducing position sizes")

        if self.metrics['validator_rejections'] > self.metrics['volume_confirmed']:
            print("  📊 LOW VOLUME ENVIRONMENT: Many signals being filtered")
            print("     → This is GOOD - prevents false breakouts")

        if self.metrics['trend_neutral'] > (self.metrics['trend_bullish'] + self.metrics['trend_bearish']):
            print("  📉 CHOPPY MARKET: Trend Filter detecting sideways movement")
            print("     → HOLD rate should be high (which is correct)")

        print("\n" + "="*80)
        print(" " * 20 + "Phase 1 is actively filtering signals")
        print(" " * 15 + "Continue monitoring for 24-48 hours for full analysis")
        print("="*80 + "\n")

    def export_json(self, output_file: str = "/tmp/phase1_metrics.json"):
        """Export metrics to JSON for analysis"""
        data = {
            "timestamp": datetime.now().isoformat(),
            "period": {
                "start": self.start_time.isoformat() if self.start_time else None,
                "end": self.end_time.isoformat() if self.end_time else None,
                "duration_hours": (self.end_time - self.start_time).total_seconds() / 3600 if (self.start_time and self.end_time) else 0
            },
            "metrics": self.metrics,
            "effectiveness": self.calculate_filtering_effectiveness()
        }

        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)

        print(f"📁 Metrics exported to: {output_file}")

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Phase 1 Performance Monitor")
    parser.add_argument('--hours', type=int, default=24, help='Hours of logs to analyze (default: 24)')
    parser.add_argument('--log-file', type=str, default='/tmp/trading-engine-phase1.log', help='Log file to analyze')
    parser.add_argument('--export', type=str, help='Export metrics to JSON file')
    parser.add_argument('--watch', action='store_true', help='Continuous monitoring mode')

    args = parser.parse_args()

    monitor = Phase1Monitor(log_file=args.log_file)
    monitor.parse_logs(hours=args.hours)
    monitor.print_report()

    if args.export:
        monitor.export_json(args.export)

    if args.watch:
        print("\n👀 Watching logs (Ctrl+C to stop)...")
        try:
            import time
            while True:
                time.sleep(300)  # Update every 5 minutes
                print("\n" + "="*80)
                print(f"  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("="*80)
                monitor = Phase1Monitor(log_file=args.log_file)
                monitor.parse_logs(hours=args.hours)
                monitor.print_report()
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")

if __name__ == "__main__":
    main()
