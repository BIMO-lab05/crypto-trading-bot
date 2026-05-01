# Autonomous monitor (tiered)

Two-tier monitor for the trading bot. Tier 1 runs every 15 min and is cheap.
Tier 2 only fires on tier-1 failures and uses `claude -p` to diagnose, write a
regression test, fix the bug, gate on a backtest, and open a PR.

```
run_monitor.sh   # cron entry, single global flock
 ├── tier1_monitor.py     # health, Prom alerts, price divergence, notifications
 ├── tier2_escalate.sh    # invokes `claude -p` (only on tier-1 fail)
 │    └── tier2_mission.md   # the mission prompt fed to claude
 └── auto_pr_janitor.sh   # closes stale auto-monitor PRs
```

## What tier 1 checks

| Check | Source | Failure mode |
|---|---|---|
| 11 service `/health` endpoints | `localhost:8000–8009` | unreachable / not `healthy` |
| Prometheus firing alerts | `:9090/api/v1/alerts` | any non-`Watchdog` alert firing |
| Price divergence | bot ticker vs CoinGecko BTC | `>PRICE_DIVERGENCE_PCT` (default 1%) |
| Notifications in last hour | `notifications_sent_total[1h]` → docker logs fallback | count == 0 |

Exit codes: `0` green, `1` real failure (escalate), `2` monitor self-errored
(do **not** escalate).

## Install

```bash
chmod +x scripts/monitoring/run_monitor.sh \
         scripts/monitoring/tier2_escalate.sh \
         scripts/monitoring/auto_pr_janitor.sh
```

Pick a `BACKTEST_CMD`. It must:
- accept `--ref <git-ref>` and check out / use that ref's code,
- print exactly one line of the form `SHARPE=<float>` to stdout,
- finish in < 10 minutes (cron pacing — see "Why not 24h" below).

Cron line (every 15 min):

```cron
*/15 * * * * cd /mnt/d/Bimo_max/crypto-trading-bot && \
  BACKTEST_CMD="scripts/run_quick_backtest.sh" \
  PATH="/home/moha/.local/bin:/usr/local/bin:/usr/bin:/bin" \
  ./scripts/monitoring/run_monitor.sh >> logs/monitor_cron.log 2>&1
```

The `PATH` line matters — cron's default `PATH` does not include
`~/.local/bin` where `claude` lives.

## GitHub App wiring

The repo already has `.github/workflows/claude.yml` (responds to `@claude`).
The tier-2 mission ends every PR body with `@claude please review this
auto-generated fix.` — that triggers the existing GitHub App for a second
pass. **No workflow changes required.**

## Guardrails

- **Single-flight** (`flock`): cron ticks never overlap.
- **Daily budget cap** (`DAILY_BUDGET`, default 8): max tier-2 invocations per
  UTC day. Exceeding it opens an issue instead.
- **Open-PR cap** (`MAX_OPEN_AUTO_PRS`, default 1): if there's already an open
  `auto-monitor` PR, new failures are appended as a comment to that PR.
- **Stale-PR auto-close** (`STALE_HOURS`, default 24): janitor closes
  `auto-monitor` PRs not reviewed in 24h.
- **Backtest gate**: tier 2 aborts PR creation (and opens an issue instead) if
  `SHARPE_FIX < SHARPE_BASE * 0.9`.
- **No auto-merge.** PRs are for human review only.
- **No `--no-verify`.** Pre-commit hooks run.
- **Branch convention**: `fix/auto-monitor-<unix-ts>`. Never pushes to `main`.

## Why not "24h backtest" as you specified

A 24h-of-market-data backtest typically completes in seconds-to-minutes of
wall clock if your runner is configured well — but the cron is on a 15-min
cadence. If a real backtest takes ~10 min, you have headroom; if it takes
hours, escalations queue forever and the lock starves. Keep `BACKTEST_CMD`
fast (resampled / partial replay is fine); the *gate* is what prevents
regressions, not the duration of the simulation.

## Tuning

| Env var | Default | Purpose |
|---|---|---|
| `PROMETHEUS_URL` | `http://localhost:9090` | Prometheus base URL |
| `COINGECKO_URL` | CoinGecko BTC simple-price | public ticker for cross-check |
| `PRICE_DIVERGENCE_PCT` | `1.0` | divergence threshold (%) |
| `CURL_TIMEOUT` | `5` | per-request timeout (s) |
| `COMPOSE_FILE` | `docker-compose.unified.yml` | fallback log source |
| `CLAUDE_BIN` | `claude` | path to claude CLI |
| `CLAUDE_MAX_TURNS` | `40` | hard cap on agent turns |
| `DAILY_BUDGET` | `8` | max tier-2 runs / UTC day |
| `MAX_OPEN_AUTO_PRS` | `1` | concurrent open auto-PRs |
| `STALE_HOURS` | `24` | janitor close cutoff |
| `BACKTEST_CMD` | (unset) | **required** for tier-2 to fire |

## Disable

```bash
crontab -e   # remove or comment the line
```

To pause without removing cron: `touch logs/MONITOR_DISABLED`. *(Not yet
honored — add a check in `run_monitor.sh` if you want this knob.)*

## Logs

- `logs/monitor_tier1.log` — one line per cron tick (OK / FAIL summary)
- `logs/monitor_tier2.log` — full claude session output when tier 2 fires
- `logs/monitor_janitor.log` — janitor activity
- `logs/monitor_cron.log` — raw cron stdout/stderr (set in your crontab line)

## What's deliberately NOT here

- **Auto-merge** — never. You review.
- **Post-merge rollback** — out of scope for cron. The backtest gate is a
  pre-merge check; for post-merge regressions you'd want a canary or CI step.
- **24h wall-clock backtests** — incompatible with 15-min cron. See above.
- **Modifying `claude.yml`** — the existing `@claude` mention path is reused.
