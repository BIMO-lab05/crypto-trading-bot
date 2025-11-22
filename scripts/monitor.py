#!/usr/bin/env python3
"""
Crypto Trading Bot - Continuous Monitoring Script
Version: 1.0.0
Last Updated: 2025-11-14

Purpose: Continuous system health monitoring with alerting
Usage: python3 scripts/monitor.py [--interval 60] [--alert-threshold 3]

Features:
- Real-time service health monitoring
- Resource usage tracking (CPU, memory, disk)
- Trading performance metrics
- Automated alerting on failures
- Log aggregation and analysis
- Export metrics for external monitoring
"""

import asyncio
import sys
import argparse
import signal
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
import httpx
import json

# ANSI color codes
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
CYAN = '\033[0;36m'
NC = '\033[0m'

# Service configuration
SERVICES = {
    "api-gateway": {"port": 8000, "critical": True},
    "bybit-connector": {"port": 8001, "critical": True},
    "market-data": {"port": 8002, "critical": True},
    "portfolio-manager": {"port": 8003, "critical": True},
    "technical-analysis": {"port": 8004, "critical": False},
    "trading-engine": {"port": 8005, "critical": True},
    "notification-service": {"port": 8006, "critical": False},
    "ml-prediction": {"port": 8007, "critical": False},
    "sentiment-analysis": {"port": 8008, "critical": False},
    "risk-metrics": {"port": 8009, "critical": True}
}

# Alert thresholds
THRESHOLDS = {
    "service_failures": 3,      # Alert after N consecutive failures
    "critical_failures": 1,     # Alert immediately for critical services
    "response_time_ms": 1000,   # Alert if response > 1s
    "daily_loss_pct": 4.0,      # Alert at 4% daily loss (before 5% limit)
    "position_count": 5,        # Alert if positions exceed limit
    "error_rate": 0.1           # Alert if >10% requests fail
}


class SystemMonitor:
    """Continuous system health monitoring"""

    def __init__(self, interval: int = 60, alert_threshold: int = 3):
        self.interval = interval
        self.alert_threshold = alert_threshold
        self.running = True
        self.failure_counts: Dict[str, int] = defaultdict(int)
        self.last_alerts: Dict[str, datetime] = {}
        self.alert_cooldown = timedelta(minutes=5)  # Don't spam alerts
        self.metrics_history: List[Dict] = []
        self.start_time = datetime.now()

    def log(self, message: str, level: str = "INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        color = {
            "INFO": BLUE,
            "SUCCESS": GREEN,
            "WARNING": YELLOW,
            "ERROR": RED,
            "ALERT": f"{RED}\033[1m"  # Bold red
        }.get(level, NC)

        print(f"{color}[{timestamp}] {level}: {message}{NC}")

    def should_alert(self, alert_key: str) -> bool:
        """Check if we should send an alert (respects cooldown)"""
        last_alert = self.last_alerts.get(alert_key)

        if last_alert is None:
            return True

        if datetime.now() - last_alert > self.alert_cooldown:
            return True

        return False

    def send_alert(self, alert_key: str, message: str, severity: str = "WARNING"):
        """Send alert (log for now, can integrate with notification service)"""
        if not self.should_alert(alert_key):
            return

        self.log(f"ALERT ({severity}): {message}", "ALERT")
        self.last_alerts[alert_key] = datetime.now()

        # TODO: Integrate with notification-service to send Telegram alerts
        # asyncio.create_task(self.send_telegram_alert(message))

    async def check_service_health(self, name: str, config: Dict) -> Dict:
        """Check health of a single service"""
        port = config["port"]
        url = f"http://localhost:{port}/health"

        result = {
            "name": name,
            "port": port,
            "healthy": False,
            "response_time_ms": None,
            "status_code": None,
            "error": None
        }

        try:
            start_time = asyncio.get_event_loop().time()

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)

            end_time = asyncio.get_event_loop().time()
            response_time_ms = (end_time - start_time) * 1000

            result["response_time_ms"] = response_time_ms
            result["status_code"] = response.status_code
            result["healthy"] = response.status_code == 200

            # Check response time threshold
            if response_time_ms > THRESHOLDS["response_time_ms"]:
                self.send_alert(
                    f"slow_response_{name}",
                    f"{name} is slow: {response_time_ms:.0f}ms response time",
                    "WARNING"
                )

            # Reset failure count on success
            if result["healthy"]:
                self.failure_counts[name] = 0

        except Exception as e:
            result["error"] = str(e)
            result["healthy"] = False

            # Increment failure count
            self.failure_counts[name] += 1

            # Alert logic
            is_critical = config.get("critical", False)
            failure_count = self.failure_counts[name]

            if is_critical and failure_count >= THRESHOLDS["critical_failures"]:
                self.send_alert(
                    f"critical_failure_{name}",
                    f"CRITICAL: {name} is down! ({failure_count} consecutive failures)",
                    "CRITICAL"
                )
            elif failure_count >= THRESHOLDS["service_failures"]:
                self.send_alert(
                    f"service_failure_{name}",
                    f"{name} is down ({failure_count} consecutive failures)",
                    "WARNING"
                )

        return result

    async def check_all_services(self) -> List[Dict]:
        """Check health of all services"""
        tasks = [
            self.check_service_health(name, config)
            for name, config in SERVICES.items()
        ]

        results = await asyncio.gather(*tasks)
        return list(results)

    async def check_trading_metrics(self) -> Optional[Dict]:
        """Check trading performance metrics"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Get portfolio balance
                balance_response = await client.get("http://localhost:8003/api/v1/balance")

                if balance_response.status_code == 200:
                    balance_data = balance_response.json()

                    current_balance = balance_data.get("total_balance", 0)
                    initial_balance = balance_data.get("initial_balance", 10000)

                    # Calculate daily P&L
                    daily_pnl = current_balance - initial_balance
                    daily_pnl_pct = (daily_pnl / initial_balance * 100) if initial_balance > 0 else 0

                    # Alert if approaching daily loss limit
                    if daily_pnl_pct < -THRESHOLDS["daily_loss_pct"]:
                        self.send_alert(
                            "daily_loss_warning",
                            f"Daily loss at {daily_pnl_pct:.2f}% (${daily_pnl:.2f}) - approaching 5% limit!",
                            "WARNING"
                        )

                    # Get open positions
                    positions_response = await client.get("http://localhost:8005/api/v1/positions?status=open")

                    if positions_response.status_code == 200:
                        positions_data = positions_response.json()
                        positions = positions_data.get("positions", [])
                        position_count = len(positions)

                        # Alert if too many positions
                        if position_count >= THRESHOLDS["position_count"]:
                            self.send_alert(
                                "position_limit",
                                f"Position count at {position_count}/{THRESHOLDS['position_count']} limit",
                                "WARNING"
                            )

                        # Calculate total unrealized P&L
                        total_unrealized_pnl = sum(p.get("pnl", 0) for p in positions)

                        return {
                            "current_balance": current_balance,
                            "daily_pnl": daily_pnl,
                            "daily_pnl_pct": daily_pnl_pct,
                            "open_positions": position_count,
                            "unrealized_pnl": total_unrealized_pnl
                        }

        except Exception as e:
            self.log(f"Failed to fetch trading metrics: {e}", "ERROR")

        return None

    async def check_data_collection(self) -> Optional[Dict]:
        """Check if market data is being collected"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check recent data for BTCUSDT
                response = await client.get(
                    "http://localhost:8002/api/v1/klines/BTCUSDT?interval=60&limit=10"
                )

                if response.status_code == 200:
                    data = response.json()
                    candles = data.get("data", [])

                    if len(candles) > 0:
                        # Check if data is recent (within last hour)
                        latest_candle = candles[-1]
                        latest_timestamp = latest_candle.get("timestamp", "")

                        # Parse timestamp
                        try:
                            latest_dt = datetime.fromisoformat(latest_timestamp.replace('Z', '+00:00'))
                            data_age = datetime.now() - latest_dt.replace(tzinfo=None)

                            if data_age > timedelta(hours=2):
                                self.send_alert(
                                    "stale_data",
                                    f"Market data is stale: Last update {data_age.total_seconds()/3600:.1f} hours ago",
                                    "WARNING"
                                )

                            return {
                                "candle_count": len(candles),
                                "latest_timestamp": latest_timestamp,
                                "data_age_minutes": data_age.total_seconds() / 60
                            }
                        except:
                            pass

        except Exception as e:
            self.log(f"Failed to check data collection: {e}", "ERROR")

        return None

    def print_status_summary(self, services: List[Dict], trading: Optional[Dict], data: Optional[Dict]):
        """Print current system status"""
        # Clear screen (optional)
        # print("\033[H\033[J", end="")

        print("\n" + "=" * 70)
        print(f"{CYAN}System Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{NC}")
        print(f"Uptime: {datetime.now() - self.start_time}")
        print("=" * 70)

        # Service health summary
        healthy_count = sum(1 for s in services if s["healthy"])
        total_count = len(services)

        if healthy_count == total_count:
            status_color = GREEN
            status_text = "ALL OPERATIONAL"
        elif healthy_count >= total_count * 0.7:
            status_color = YELLOW
            status_text = "DEGRADED"
        else:
            status_color = RED
            status_text = "CRITICAL"

        print(f"\n{status_color}Services: {healthy_count}/{total_count} healthy - {status_text}{NC}")

        # Show unhealthy services
        unhealthy = [s for s in services if not s["healthy"]]
        if unhealthy:
            print(f"\n{RED}Unhealthy Services:{NC}")
            for service in unhealthy:
                failures = self.failure_counts[service["name"]]
                error = service.get("error", "Unknown error")
                print(f"  {RED}✗{NC} {service['name']}: {error} ({failures} failures)")

        # Trading metrics
        if trading:
            print(f"\n{CYAN}Trading Metrics:{NC}")
            pnl_color = GREEN if trading["daily_pnl"] >= 0 else RED
            print(f"  Balance: ${trading['current_balance']:.2f}")
            print(f"  Daily P&L: {pnl_color}${trading['daily_pnl']:.2f} ({trading['daily_pnl_pct']:.2f}%){NC}")
            print(f"  Open Positions: {trading['open_positions']}")
            print(f"  Unrealized P&L: ${trading['unrealized_pnl']:.2f}")

        # Data collection
        if data:
            print(f"\n{CYAN}Data Collection:{NC}")
            print(f"  Recent candles: {data['candle_count']}")
            print(f"  Data age: {data['data_age_minutes']:.1f} minutes")

        print("\n" + "=" * 70)
        print(f"Next check in {self.interval} seconds (Ctrl+C to stop)")

    async def export_metrics(self, services: List[Dict], trading: Optional[Dict]):
        """Export metrics in JSON format for external monitoring"""
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            "services": {
                s["name"]: {
                    "healthy": s["healthy"],
                    "response_time_ms": s["response_time_ms"],
                    "status_code": s["status_code"]
                }
                for s in services
            },
            "trading": trading,
            "alerts_sent": len(self.last_alerts)
        }

        # Store in history (keep last 100 data points)
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 100:
            self.metrics_history.pop(0)

        # Write to file for external monitoring tools
        try:
            with open("/tmp/crypto_bot_metrics.json", "w") as f:
                json.dump(metrics, f, indent=2)
        except Exception as e:
            self.log(f"Failed to export metrics: {e}", "ERROR")

    async def monitor_loop(self):
        """Main monitoring loop"""
        self.log(f"Starting system monitor (interval: {self.interval}s)", "INFO")
        self.log(f"Alert threshold: {self.alert_threshold} consecutive failures", "INFO")

        cycle_count = 0

        while self.running:
            try:
                cycle_count += 1

                # Check all services
                services = await self.check_all_services()

                # Check trading metrics
                trading = await self.check_trading_metrics()

                # Check data collection
                data = await self.check_data_collection()

                # Print status
                self.print_status_summary(services, trading, data)

                # Export metrics
                await self.export_metrics(services, trading)

                # Log milestone cycles
                if cycle_count % 10 == 0:
                    self.log(f"Completed {cycle_count} monitoring cycles", "INFO")

                # Wait for next interval
                await asyncio.sleep(self.interval)

            except asyncio.CancelledError:
                self.log("Monitor loop cancelled", "INFO")
                break
            except Exception as e:
                self.log(f"Monitoring error: {e}", "ERROR")
                await asyncio.sleep(self.interval)

    def stop(self):
        """Stop monitoring"""
        self.running = False
        self.log("Stopping monitor...", "INFO")


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print(f"\n{YELLOW}Received interrupt signal, shutting down...{NC}")
    sys.exit(0)


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Continuous monitoring for crypto trading bot"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Monitoring interval in seconds (default: 60)"
    )
    parser.add_argument(
        "--alert-threshold",
        type=int,
        default=3,
        help="Alert after N consecutive failures (default: 3)"
    )
    args = parser.parse_args()

    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Create and run monitor
    monitor = SystemMonitor(interval=args.interval, alert_threshold=args.alert_threshold)

    try:
        await monitor.monitor_loop()
    except KeyboardInterrupt:
        monitor.stop()
        print(f"\n{GREEN}Monitor stopped cleanly{NC}")
    except Exception as e:
        print(f"\n{RED}Monitor crashed: {e}{NC}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
