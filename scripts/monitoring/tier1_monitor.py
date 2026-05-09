#!/usr/bin/env python3
"""Tier 1 monitor: cheap, deterministic checks. No LLM calls. Cron-safe.

Exit codes:
    0  all green
    1  at least one check failed (tier 2 should escalate)
    2  monitor itself errored (config/network) — tier 2 must NOT escalate

Writes a JSON report to stdout and a one-line summary to logs/monitor_tier1.log.
Tier 2 reads the JSON report from --out path.
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = REPO_ROOT / "logs"

SERVICES = {
    "api-gateway": 8000,
    "bybit-connector": 8001,
    "market-data-service": 8002,
    "portfolio-manager": 8003,
    "technical-analysis": 8004,
    "trading-engine": 8005,
    "notification-service": 8006,
    "ml-prediction-service": 8007,
    "sentiment-analysis-service": 8008,
    "risk-metrics-service": 8009,
}

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://localhost:9090")
COINGECKO_URL = os.environ.get(
    "COINGECKO_URL",
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
)
PRICE_DIVERGENCE_PCT = float(os.environ.get("PRICE_DIVERGENCE_PCT", "1.0"))
CURL_TIMEOUT = float(os.environ.get("CURL_TIMEOUT", "5"))
COMPOSE_FILE = os.environ.get("COMPOSE_FILE", str(REPO_ROOT / "docker-compose.unified.yml"))

BOT_PRICE_URLS = [
    "http://localhost:8000/api/market/ticker/BTCUSDT",
    "http://localhost:8002/api/v1/ticker/BTCUSDT",
]


def http_json(url: str, timeout: float = CURL_TIMEOUT) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception:
        return None


def dig(obj, *path):
    cur = obj
    for k in path:
        try:
            cur = cur[k]
        except (KeyError, IndexError, TypeError):
            return None
    return cur


def check_service_health() -> tuple[str, str] | None:
    bad = []
    for svc, port in SERVICES.items():
        body = http_json(f"http://localhost:{port}/health")
        if body is None:
            bad.append(f"{svc}:unreachable")
            continue
        status = (body.get("status") or "").lower()
        if status not in ("healthy", "ok", "up"):
            bad.append(f"{svc}:{status or 'unknown'}")
    return ("service_health", ",".join(bad)) if bad else None


def check_prometheus_alerts() -> tuple[str, str] | None:
    body = http_json(f"{PROMETHEUS_URL}/api/v1/alerts")
    if body is None:
        return ("prometheus_unreachable", PROMETHEUS_URL)
    alerts = dig(body, "data", "alerts") or []
    firing = [
        a["labels"].get("alertname", "?")
        for a in alerts
        if a.get("state") == "firing" and a.get("labels", {}).get("alertname") != "Watchdog"
    ]
    return ("prometheus_firing", ",".join(firing)) if firing else None


def get_bot_price() -> float | None:
    for url in BOT_PRICE_URLS:
        body = http_json(url)
        if not body:
            continue
        for path in (
            ("price",),
            ("last_price",),
            ("data", "price"),
            ("data", "last_price"),
            ("result", "list", 0, "lastPrice"),
        ):
            v = dig(body, *path)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
    return None


def check_price_divergence() -> tuple[str, str] | None:
    bot = get_bot_price()
    if bot is None:
        return ("bot_price_unavailable", ",".join(BOT_PRICE_URLS))
    pub_body = http_json(COINGECKO_URL)
    pub = dig(pub_body, "bitcoin", "usd")
    if pub is None:
        return ("public_ticker_unavailable", COINGECKO_URL)
    diff_pct = abs(bot - float(pub)) / float(pub) * 100.0
    if diff_pct > PRICE_DIVERGENCE_PCT:
        return ("price_divergence", f"bot={bot} public={pub} diff_pct={diff_pct:.3f}")
    return None


def check_notifications_recent() -> tuple[str, str] | None:
    q = "increase(notifications_sent_total[1h])"
    url = f"{PROMETHEUS_URL}/api/v1/query?query={urllib.parse.quote(q)}"
    body = http_json(url)
    total = None
    if body and dig(body, "status") == "success":
        results = dig(body, "data", "result") or []
        if results:
            total = sum(float(r["value"][1]) for r in results)

    if total is None:
        # Fallback: count log lines from notification-service in the last hour.
        try:
            out = subprocess.run(
                ["docker", "compose", "-f", COMPOSE_FILE, "logs",
                 "--since", "1h", "notification-service"],
                capture_output=True, text=True, timeout=15,
            )
            if out.returncode == 0:
                total = sum(
                    1 for ln in out.stdout.splitlines()
                    if any(s in ln for s in ("telegram_sent", "email_sent", "notification sent"))
                )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if total is None:
        return ("notifications_check_skipped", "no metric, no docker logs available")
    if total == 0:
        return ("no_notifications_1h", "count=0")
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", help="write JSON report here in addition to stdout")
    args = parser.parse_args()

    failures = []
    checks = (
        check_service_health,
        check_prometheus_alerts,
        check_price_divergence,
        check_notifications_recent,
    )
    monitor_errors = 0
    for fn in checks:
        try:
            res = fn()
        except Exception as e:
            monitor_errors += 1
            failures.append({"check": f"{fn.__name__}_internal_error", "detail": repr(e)})
            continue
        if res is not None:
            failures.append({"check": res[0], "detail": res[1]})

    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "failures": failures,
        "failure_count": len(failures),
    }
    out = json.dumps(report, indent=2)
    print(out)
    if args.out:
        Path(args.out).write_text(out)

    LOG_DIR.mkdir(exist_ok=True)
    with (LOG_DIR / "monitor_tier1.log").open("a") as f:
        if failures:
            summary = ";".join(f"{x['check']}={x['detail']}" for x in failures)
            f.write(f"{report['timestamp']} FAIL {summary}\n")
        else:
            f.write(f"{report['timestamp']} OK\n")

    if monitor_errors and len(failures) == monitor_errors:
        return 2
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
