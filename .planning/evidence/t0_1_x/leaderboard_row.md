# T0.1.x Leaderboard Evidence — tournament_id: t0_1_x_horizon_sweep

**Status:** INSUFFICIENT_DATA — tournament did not complete. See `decision_note.md`.

No leaderboard rows were produced because the tournament run failed at the infrastructure
layer before any training experiments were executed. The failure occurred at
`run_tournament()` in `app/orchestrator/launcher.py` with:

```
RuntimeError: TIMESCALE_PASSWORD is unset or still the placeholder;
follow RUNBOOK.md tournament-harness first-time setup before running.
```

The container was started successfully (tournament-harness image pulled from cache,
service healthy on port 8010), and the experiment YAML was parsed correctly (12
experiments enumerated). The failure occurred when the launcher validated the
TimescaleDB connection parameters and found `TIMESCALE_PASSWORD` empty.

## Expected leaderboard schema (for operator reference)

When the tournament runs successfully, each row will contain:

| symbol | architecture | horizon | target_mode | r2_returns | dir_acc_corrected | oos_sharpe | psr | dsr | cpcv_dsr | train_seconds | git_sha |
|--------|-------------|---------|-------------|------------|-------------------|------------|-----|-----|----------|---------------|---------|
| SOLUSDT | gru | 3 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| SOLUSDT | gru | 5 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| SOLUSDT | gru | 7 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| SOLUSDT | gru | 10 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| BNBUSDT | gru | 3 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| BNBUSDT | gru | 5 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| BNBUSDT | gru | 7 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| BNBUSDT | gru | 10 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| ADAUSDT | gru | 3 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| ADAUSDT | gru | 5 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| ADAUSDT | gru | 7 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |
| ADAUSDT | gru | 10 | log_returns | (float) | (float) | (float) | (float) | (float) | (float) | (int) | (sha) |

The dsr column is what the significance test gates on (p<0.05 vs persistence baseline).
Once TIMESCALE_PASSWORD is configured and the run completes, execute:

```bash
docker compose -f docker-compose.unified.yml --profile tournament exec tournament-harness \
  python -m app.cli leaderboard list --tournament-id t0_1_x_horizon_sweep --by dsr
```

to retrieve the actual rows.
