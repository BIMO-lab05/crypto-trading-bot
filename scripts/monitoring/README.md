# Monitoring (tier-1 only)

Lightweight cron-based health monitor for the trading bot. Runs every 15 minutes and
logs failures. **No `claude` invocation. No `gh` invocation. No `git` write.**

Tier-2 (autonomous agentic diagnosis + auto-PR via the Claude CLI print-mode flag) was
deleted in Phase 5 (MLCL-03, ADR-011, 2026-05-13). This directory now contains only the
tier-1 health checker and operator helpers.

```
run_monitor.sh       # cron entry — runs tier1_monitor.py, notifies on failure
tier1_monitor.py     # health checks (curl, Prometheus, price divergence)
start_monitoring.sh  # operator helper: install cron entry
stop_monitoring.sh   # operator helper: remove cron entry
monitoring_logs.sh   # operator helper: tail tier-1 logs
monitoring_status.sh # operator helper: show last known status
```

## What tier-1 checks

| Check | Source | Failure mode |
|---|---|---|
| 11 service `/health` endpoints | `localhost:8000–8009` | unreachable or not `healthy` |
| Prometheus firing alerts | `:9090/api/v1/alerts` | any non-`Watchdog` alert firing |
| Price divergence | bot ticker vs CoinGecko BTC | `>PRICE_DIVERGENCE_PCT` (default 1%) |
| Notifications in last hour | `notifications_sent_total[1h]` → docker logs fallback | count == 0 |

Exit codes from `tier1_monitor.py`: `0` green, `1` real failure (notify operator), `2`
monitor self-errored (do **not** notify — avoid alert spam on transient network issues).

## Blast-radius bounds

**What the tier-1 system CAN do:**

| Action | Where | Notes |
|--------|-------|-------|
| `curl` / HTTP GET | `localhost:800x` (service health), `:9090` (Prometheus), CoinGecko public API | read-only; no auth headers |
| Read docker logs | `docker compose logs --since 1h notification-service` | read-only; requires docker socket |
| Append to log files | `logs/monitor_tier1.log`, `logs/monitor_tier1_failures.jsonl` | local filesystem only |
| HTTP POST | `TELEGRAM_WEBHOOK_URL` (if set by operator) | optional notification; no credentials beyond the webhook URL |

**What the tier-1 system CANNOT do:**

- Invoke `claude` or any other LLM CLI (the agentic tier-2 path was in the deleted files)
- Run `gh pr create`, `gh pr merge`, or any GitHub CLI command
- `git commit`, `git push`, or modify any file in the repository
- Spawn additional processes beyond `python3 tier1_monitor.py` and optional `curl`
- Read `.env`, API keys, or any secret outside its own log directory

**How the operator removes tier-1 entirely:**

```bash
./scripts/monitoring/stop_monitoring.sh   # removes cron entry
# or manually:
crontab -e   # remove the crypto-bot monitor line
```

## Install

```bash
chmod +x scripts/monitoring/run_monitor.sh
./scripts/monitoring/start_monitoring.sh  # installs cron entry
```

Cron line (every 15 min):

```cron
*/15 * * * * cd /mnt/d/Bimo_max/crypto-trading-bot && \
  PATH="/home/moha/.local/bin:/usr/local/bin:/usr/bin:/bin" \
  ./scripts/monitoring/run_monitor.sh >> logs/monitor_cron.log 2>&1
```

The `PATH` line matters — cron's default `PATH` does not include `~/.local/bin`.

## Failure behavior

When tier-1 detects failures (`exit 1`), `run_monitor.sh`:

1. Appends a structured JSON line to `logs/monitor_tier1_failures.jsonl`:
   ```json
   {"timestamp": "2026-05-13T12:00:00Z", "report": {"failures": [...], "failure_count": 2}}
   ```
2. Optionally POSTs a plain-text notification to `TELEGRAM_WEBHOOK_URL` if set.

**Operator action required.** No autonomous fix is attempted. The operator reviews the
failure log and decides what to do.

## Environment variables

| Env var | Default | Purpose |
|---|---|---|
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus base URL |
| `COINGECKO_URL` | CoinGecko BTC simple-price endpoint | Public ticker for cross-check |
| `PRICE_DIVERGENCE_PCT` | `1.0` | Divergence threshold (%) |
| `CURL_TIMEOUT` | `5` | Per-request timeout (s) |
| `COMPOSE_FILE` | `docker-compose.unified.yml` | Fallback log source |
| `TELEGRAM_WEBHOOK_URL` | (unset) | Optional Telegram notification webhook |

## Logs

- `logs/monitor_tier1.log` — one line per cron tick (OK / FAIL summary)
- `logs/monitor_tier1_failures.jsonl` — structured JSONL of all tier-1 failure events
- `logs/monitor_cron.log` — raw cron stdout/stderr

## What is NOT here (by design, per ADR-011)

- **`tier2_escalate.sh`** — deleted. Invoked the Claude CLI in autonomous mode.
  High attack surface (STRIDE T-05-03-01..06). See ADR-011.
- **`tier2_mission.md`** — deleted. Was the mission prompt fed to the claude subprocess.
- **`auto_pr_janitor.sh`** — deleted. Was the stale-PR janitor using `gh` CLI.
- **Auto-merge** — never was, never will be. You review.
- **Autonomous LLM invocation of any kind** — confirmed absent. The grep gate at
  `tests/security/test_no_unattended_claude_p_in_ci.py` enforces this invariant in CI.

See `docs/decisions/ADR-011-monitoring-disposition.md` for the full disposition record and
the threat analysis that motivated it.
