# Forward Paper Test

Host-runnable CLI harness for running each Tier-1 feature flag in isolation
against the live paper-trading engine, collecting per-trade returns, and
computing PSR with bootstrap confidence interval before allowing a
default-on flip in `services/trading-engine/app/config.py`.

## Purpose

Before any Tier-1 flag (vol targeting, maker orders, funding gate) can be
flipped to `default=True` in the trading-engine config, the operator must:

1. Run the flag in isolation for at least 7 wall-clock days.
2. Collect per-trade log-returns from the paper-trade log.
3. Compute PSR with bootstrap CI (`psr_ci_low > 0.0` gate).
4. Publish the `PSR_CI_PUBLISHED` marker file.
5. The pytest gate in `services/trading-engine/tests/test_config_default_on_gate.py`
   then passes, allowing the PR that flips `default=True` to merge.

See `docs/runbooks/forward-paper-test.md` for the full operator walkthrough.

## Tier-1 Flags

| Flag name | Env var | Description |
|---|---|---|
| `enable_vol_targeting` | `ENABLE_VOL_TARGETING` | Vol-parity position sizing (T1.2) |
| `prefer_maker_orders` | `PREFER_MAKER_ORDERS` | PostOnly maker limit entries (T1.3) |
| `enable_funding_gate` | `ENABLE_FUNDING_GATE` | Funding-rate gate for perp entries (T2.3) |

## Usage

### 1. Dry run (preview env overlay)

```bash
python -m scripts.forward_paper_test.run_isolation \
    --flag enable_vol_targeting \
    --duration-days 7 \
    --dry-run
```

Prints a JSON plan without touching docker or the filesystem.

### 2. Start an isolation run (live)

```bash
PAPER_TRADING_MODE=true python -m scripts.forward_paper_test.run_isolation \
    --flag enable_vol_targeting \
    --duration-days 7 \
    --paper-trade-log ./services/trading-engine/logs/paper_trades.log
```

This will:
- Check `PAPER_TRADING_MODE=true` and refuse if `TRADING_MODE=LIVE`.
- Create `.planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>/`.
- Write `meta.json` with run metadata.
- Launch `docker compose up -d trading-engine` with explicit env overrides.

### 3. Complete the run (after ≥7 days)

After the paper-trade window closes, extract returns and write `run.json`:

```bash
python -m scripts.forward_paper_test.run_isolation complete-run \
    --evidence-dir .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

Alternatively, write `run.json` by hand from analytics. The required schema is:

```json
{
  "run_id": "<string>",
  "flag": "enable_vol_targeting",
  "started_at_utc": "<ISO-8601>",
  "completed_at_utc": "<ISO-8601>",
  "returns": [0.0012, -0.0005, 0.0023, ...],
  "trades": [...],
  "notes": "<operator notes>",
  "git_sha": "<short SHA>"
}
```

Fields:
- `run_id` — unique identifier for this isolation run (UTC timestamp by default).
- `flag` — the Tier-1 flag name tested in this run.
- `started_at_utc` — ISO-8601 timestamp when the run started.
- `completed_at_utc` — ISO-8601 timestamp when the run ended.
- `returns` — array of per-trade log-returns (float). **Must have ≥30 elements.**
  Use per-trade returns (not per-day) to get sufficient observations over 7 days.
- `trades` — array of trade objects (raw, for audit trail).
- `notes` — operator notes about the run conditions.
- `git_sha` — git SHA of the trading-engine code used during the run.

The `returns` array feeds directly into `load_run_returns()` and then
`compute_psr_with_bootstrap_ci()`. It must be non-empty and contain no NaN values.

### 4. Compute PSR CI

```bash
python -m scripts.forward_paper_test.psr_ci \
    --evidence-dir .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

Writes `psr_ci.json` alongside `run.json`.

### 5. Publish evidence

```bash
python -m scripts.forward_paper_test.run_isolation publish-evidence \
    .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

Validates `run.json` + `psr_ci.json` and checks `psr_ci_low > 0.0`.
On success, writes `PSR_CI_PUBLISHED` marker.

## Evidence Directory Structure

```
.planning/evidence/forward_paper_test/
  enable_vol_targeting/
    <run_id>/
      meta.json           # Written at run start (run_isolation)
      run.json            # Written at run end (operator or complete_run)
      psr_ci.json         # Written after PSR CI computation
      PSR_CI_PUBLISHED    # Written by publish-evidence (gate key)
      force_override.txt  # Written only if --force was used
  prefer_maker_orders/
    ...
  enable_funding_gate/
    ...
```

## PSR CI Schema (psr_ci.json)

```json
{
  "psr_point": 0.72,
  "psr_ci_low": 0.05,
  "psr_ci_high": 0.91,
  "n_resamples": 10000,
  "n_resamples_valid": 9987,
  "block_size": 10,
  "seed": 42,
  "n_bars": 150
}
```

## Default-on Gate

`services/trading-engine/tests/test_config_default_on_gate.py` scans
`config.py` for `default=True` on any Tier-1 flag. If found, it asserts
that `.planning/evidence/forward_paper_test/<flag>/PSR_CI_PUBLISHED` exists.
If the marker is absent, the test fails — blocking the PR that flips
`default=True`.
