# Decision Note — T0.1.x Experiment: t0_1_x_horizon_sweep

**Date:** 2026-05-13
**Experiment:** different_horizon sweep
**Tournament ID:** t0_1_x_horizon_sweep
**Plan:** Phase 05, Plan 02 (MLCL-02)

---

## Experiment Summary

This experiment ran the pre-confirmed `different_horizon` selection from
`05-02-DECISION.md`. The hypothesis: sweep prediction horizons [3, 5, 7, 10] bars
across the three v1 validated symbols (SOLUSDT, BNBUSDT, ADAUSDT) using a minimal
GRU hyperparameter grid to determine whether the V0 negative result (chance-level
on log-returns at horizon=5) generalises across prediction horizons.

Tournament config: `services/tournament-harness/app/config/t0_1_x_experiment.yaml`
Tournament ID: `t0_1_x_horizon_sweep`
Grid size: 12 experiments (4 horizons × 3 symbols × 1 target_mode)
Architecture: GRU only (units=[64], dropout=0.2, lr=0.001, batch=32, lookback=60)
Target mode: log_returns (honest post-fix evaluation; no price-level leakage)

---

## Run Attempt

The tournament-harness Docker container was successfully started. The experiment
YAML was parsed and 12 experiments were enumerated by the orchestrator. The run
was terminated before any training experiments executed with the following error:

```
RuntimeError: TIMESCALE_PASSWORD is unset or still the placeholder;
follow RUNBOOK.md tournament-harness first-time setup before running.
```

The container environment shows `TIMESCALE_PASSWORD=` (empty string). The
tournament-harness launcher validates database credentials at startup and refuses
to proceed when the password is blank, because the TimescaleDB klines table
(source of training data) would be unreachable.

No significance test was run. No leaderboard rows were produced.

---

## Evidence

- Tournament run log: attempt made via `docker exec crypto-bot-tournament-harness
  python -m app.cli run /app/app/config/t0_1_x_experiment.yaml --allow-dirty`
- Result: `RuntimeError: TIMESCALE_PASSWORD is unset` — training never started
- Snapshot file: `services/tournament-harness/data/snapshots/t0_1_x_horizon_sweep.json`
  does NOT exist (no data to snapshot)
- open-pr confirmation: `docker exec ... python -m app.cli open-pr t0_1_x_horizon_sweep
  --dry-run` returned `snapshot not found` — confirming no run completed

The leaderboard_row.md in this evidence directory contains a schema-only stub (no
actual results rows) per the INSUFFICIENT_DATA documentation convention.

---

## Blocker

**Root cause:** `TIMESCALE_PASSWORD` is empty in the tournament-harness container
environment at execution time. This is the credential the launcher requires to read
klines from TimescaleDB for model training.

**Why it is empty:** The `.env` file at repository root (gitignored per CLAUDE.md
project rules) contains the actual database credentials. The `docker-compose.unified.yml`
tournament profile reads credentials from this `.env` file. When the orchestrator
agent ran the compose command, the credential did not propagate into the container
environment — either the `.env` file does not contain `TIMESCALE_PASSWORD`, or the
compose environment injection for the tournament profile does not source it.

**Operator remediation (two steps, in order):**

Step 1 — Verify `.env` contains `TIMESCALE_PASSWORD`:
```bash
grep TIMESCALE_PASSWORD /mnt/d/Bimo_max/crypto-trading-bot/.env
```
If missing or empty, set it to the TimescaleDB password configured in
`docker-compose.unified.yml` under the `timescaledb` service (look for
`POSTGRES_PASSWORD` on the timescaledb service; tournament_reader uses the same DB).

Step 2 — Recreate the tournament-harness container to pick up the new env:
```bash
docker compose -f docker-compose.unified.yml --profile tournament up -d --force-recreate tournament-harness
```

Step 3 — Confirm the password is now set:
```bash
docker exec crypto-bot-tournament-harness env | grep TIMESCALE_PASSWORD
```
It must return a non-empty value.

Step 4 — Re-run the tournament:
```bash
docker exec crypto-bot-tournament-harness python -m app.cli run /app/app/config/t0_1_x_experiment.yaml --allow-dirty 2>&1 | tee .planning/evidence/t0_1_x/run.log
```
Note: training 12 GRU experiments will take approximately 20-60 minutes depending
on the host GPU/CPU resources available to the container.

Step 5 — After the run completes, run open-pr in dry-run mode:
```bash
docker exec crypto-bot-tournament-harness python -m app.cli open-pr t0_1_x_horizon_sweep --dry-run --allow-dirty
```
This writes the significance.json and leaderboard.md artifacts next to the snapshot.

Step 6 — Replace the stub leaderboard_row.md with the actual leaderboard markdown:
```bash
cp services/tournament-harness/data/snapshots/t0_1_x_horizon_sweep.leaderboard.md \
   .planning/evidence/t0_1_x/leaderboard_row.md
```

Step 7 — Update this decision_note.md with the actual verdict (EDGE_FOUND or
NO_EDGE_FOUND), bootstrap p-values, and lift values from the significance.json.
Remove the INSUFFICIENT_DATA terminal line and replace with the correct verdict.

**Phase follow-up plan:** This blocker is an operator credential configuration
issue, not a code defect. No new code plan is required. The fix is a `.env`
configuration check + container recreation. This should be completed before
Phase 5 can be marked fully verified against MLCL-02.

---

## Operator's Next Action

Configured `TIMESCALE_PASSWORD`, recreate tournament-harness container, re-run the
12-experiment horizon sweep (expected ~20-60 min), then update this file with the
actual EDGE_FOUND or NO_EDGE_FOUND verdict and the supporting bootstrap statistics.
The YAML config (`t0_1_x_experiment.yaml`) and integration test are in place; only
the execution and evidence update remain.

INSUFFICIENT_DATA
