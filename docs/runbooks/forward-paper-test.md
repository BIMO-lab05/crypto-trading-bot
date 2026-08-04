# Forward Paper Test Runbook

**Audience:** Operator / developer enabling a new Tier-1 feature flag.
**Scope:** Evidence loop for one isolation run (one flag, ≥7 wall-clock days).
**Tooling:** `scripts/forward_paper_test/` (host-runnable, no Docker required for the harness itself).

> Merged from `docs/strategy/research-2026-04-29/T1.2-vol-parity-paper-test-runbook.md` on 2026-07-30: baseline-capture pre-flight, mid-run kill criterion (baseline-worse-by-0.5σ), mid-run discipline rules, and the day-7 baseline-comparison decision matrix.

---

## Goal

Produce published PSR-with-bootstrap-CI evidence that a Tier-1 feature flag
(vol targeting, maker orders, or funding gate) does not harm the trading edge
before flipping it `default=True` in `services/trading-engine/app/config.py`.

The code-level gate in `services/trading-engine/tests/test_config_default_on_gate.py`
enforces this: it fails in CI on any PR that flips a flag to `default=True`
without a `PSR_CI_PUBLISHED` marker in the corresponding evidence directory.

**Three flags, three independent runs required:**
- `enable_vol_targeting` → vol-parity position sizing (T1.2)
- `prefer_maker_orders` → PostOnly maker limit entries (T1.3)
- `enable_funding_gate` → funding-rate gate for perp entries (T2.3)

---

## Prerequisites

1. Docker Desktop running with context `default` (not `desktop-linux`).
   Verify: `docker context show` → should print `default`.

2. Paper-trading stack healthy: `docker compose -f docker-compose.unified.yml ps`
   shows all services Up. If not: `bash health_check.sh`.

3. Python environment on host has no extra deps needed for the harness
   (uses stdlib + numpy, which `services/risk-metrics-service/` already pulls in).

4. `PAPER_TRADING_MODE=true` in your shell or `.env`.
   **Never run this with `TRADING_MODE=LIVE`** — the launcher enforces this
   and will refuse with a non-zero exit.

   Belt-and-braces check inside the container (from the T1.2 runbook):
   ```bash
   docker compose -f docker-compose.unified.yml exec trading-engine \
     env | grep -E "PAPER_TRADING_MODE|TRADING_MODE|BYBIT_TESTNET"
   # expect: PAPER_TRADING_MODE=true, TRADING_MODE=PAPER, BYBIT_TESTNET=false
   ```

5. The repo is on a known-good commit (`git status` clean or stashed).
   The `git_sha` baked into `meta.json` should identify the code under test.

6. **Capture a baseline before flipping the flag** so the comparison has a
   control. Record Sharpe/Sortino/return/volatility over the last 7 closed
   days plus the closed-trade count, and write the numbers + the wall-clock
   timestamp into `progress.md` under the kickoff entry:
   ```bash
   curl -s http://localhost:8009/api/v1/portfolio/paper_trading/sharpe \
     | jq '{sharpe_ratio, sortino_ratio, total_return, volatility}'
   curl -s http://localhost:8005/api/v1/trades/history?limit=200 \
     | jq '[.trades[] | select(.status == "CLOSED")] | length' \
     > /tmp/baseline_closed_trades_count.txt
   ```
   > **Path note (2026-07-30):** these curls hit risk-metrics-service (:8009) and
   > trading-engine (:8005) directly and were authored 2026-04-29. The api-gateway
   > (:8000) dropped the `/v1` prefix — gateway routes are `/api/<domain>/...`
   > (e.g. `/api/risk/...`, `/api/trading/...`). If a direct-service `/api/v1/...`
   > path 404s, check the service's current route table (or go via the gateway).

---

## Step 1 — Start the isolation run

Choose a flag and launch. Example for `enable_vol_targeting`:

```bash
# Confirm paper mode
export PAPER_TRADING_MODE=true

# Preview (no side effects)
python -m scripts.forward_paper_test.run_isolation \
    --flag enable_vol_targeting \
    --duration-days 7 \
    --dry-run

# Live launch
python -m scripts.forward_paper_test.run_isolation \
    --flag enable_vol_targeting \
    --duration-days 7 \
    --paper-trade-log ./services/trading-engine/logs/paper_trades.log
```

The launcher will:
- Verify `PAPER_TRADING_MODE=true` and refuse if `TRADING_MODE=LIVE`.
- Create the evidence directory:
  `.planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>/`
- Write `meta.json` with run metadata (flag, start time, git SHA, env overrides).
- Restart `trading-engine` via docker compose with explicit env overrides:
  `ENABLE_VOL_TARGETING=true`, `PREFER_MAKER_ORDERS=false`, `ENABLE_FUNDING_GATE=false`.
  Only one flag is on per run — isolation guarantee.

Note the `run_id` printed to stdout (format: `YYYYMMDDTHHMMSSZ`). You will need
it in Steps 2 and 3.

Confirm the flag is live:
```bash
docker compose -f docker-compose.unified.yml logs trading-engine | grep -i VOL_PARITY
# Expected: [VOL_PARITY] enabled: target=...
```

For `enable_vol_targeting` specifically: the realized-vol estimator needs
~168 hourly bars (7 days) to be warm, so the **first day will fall back to
baseline sizing on most symbols — this is expected**, not a failed flag flip.

---

## Step 2 — Wait ≥7 days and collect returns

Leave the isolation run active for at least 7 wall-clock days. The trading
engine produces per-trade records in the database and the paper-trade log.

### Mid-run discipline and kill criteria

(From the T1.2 vol-parity runbook — these apply to any Tier-1 isolation run.)

- **Do not change strategy parameters mid-run.** A run with mid-run parameter
  changes is not comparable to its baseline; restart the run instead.
- **Kill criterion:** abort the run early if realized daily P&L is worse than
  the captured baseline by **more than 0.5σ** (σ of the baseline's daily P&L).
  The 2% per-trade / 5% daily-loss caps already bound the downside, so a
  sustained >0.5σ shortfall is signal, not noise. On kill: flip the flag off,
  restart trading-engine, and record the negative result in the evidence
  directory and `progress.md`.
- **If the risk kill switch trips mid-run:** document the trigger in
  `progress.md`, then disable the flag under test (e.g.
  `ENABLE_VOL_TARGETING=false`) **before** re-arming the auto-trader.
- **Cheap daily monitoring** (run from host, once a day):
  ```bash
  curl -s http://localhost:8009/api/v1/portfolio/paper_trading/sharpe | jq
  curl -s http://localhost:8005/api/v1/trading/status | jq '.kill_switch_active'
  # Open positions + realised PnL roll-up:
  curl -s http://localhost:8003/api/portfolio/paper_trading/performance | jq
  ```
  > Same path caveat as in Prerequisites: `/api/v1/...` examples are direct
  > service routes from 2026-04-29; the gateway (:8000) uses `/api/<domain>/...`
  > with no `/v1`.

### Stop and extract

After ≥7 days, stop the run:
```bash
docker compose -f docker-compose.unified.yml stop trading-engine
```

Then extract per-trade log-returns and write `run.json`. The recommended path
is `complete-run` (extracts returns from the paper-trade log automatically):

```bash
python -m scripts.forward_paper_test.run_isolation complete-run \
    --evidence-dir .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

Or write `run.json` manually from analytics. Required schema:

```json
{
  "run_id": "<run_id>",
  "flag": "enable_vol_targeting",
  "started_at_utc": "2026-01-01T00:00:00+00:00",
  "completed_at_utc": "2026-01-08T00:00:00+00:00",
  "returns": [0.0012, -0.0005, 0.0023, ...],
  "trades": [],
  "notes": "Normal market conditions. BTC/ETH/SOL/BNB/ADA active.",
  "git_sha": "<sha>"
}
```

**Use per-trade returns, not per-day.** A 7-day run on 5 symbols typically
yields 50-200 trades, giving enough observations for a meaningful CI.
Per-day returns give only 7 observations — too few for PSR CI (minimum 30).

Each return is `log(exit_price / entry_price)` accounting for commission.

---

## Step 3 — Compute PSR CI and publish

Compute PSR with bootstrap confidence interval:

```bash
python -m scripts.forward_paper_test.psr_ci \
    --evidence-dir .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

This reads `run.json`, calls `compute_psr_with_bootstrap_ci` (10 000 block-bootstrap
resamples), and writes `psr_ci.json`. Check the output:
- `psr_point` — point PSR estimate.
- `psr_ci_low`, `psr_ci_high` — 95% bootstrap CI.
- `n_resamples_valid` — should be close to `n_resamples`; a large gap means
  many resamples hit zero-std windows (see Troubleshooting).

If `psr_ci_low > 0.0`, the CI does not bracket zero — there is statistical
evidence of positive edge. Publish:

```bash
python -m scripts.forward_paper_test.run_isolation publish-evidence \
    .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>
```

This writes `PSR_CI_PUBLISHED` marker. The default-on gate now passes for
this flag. Commit the evidence directory:

```bash
git add .planning/evidence/forward_paper_test/enable_vol_targeting/<run_id>/
git commit -m "evidence(enable_vol_targeting): publish PSR CI for <run_id>"
```

Then open the PR that flips `enable_vol_targeting: bool = Field(default=True, ...)`.

### Baseline-comparison gate (in addition to the CI gate)

The bootstrap CI shows the flagged run has positive edge in isolation; it does
not show the flag *beats the baseline you captured in Prerequisites step 6*.
Both periods should be compared with Probabilistic Sharpe Ratio — same trade
universe, adjacent periods, so PSR is the right test:

```bash
# Risk-metrics service exposes the PSR/DSR module from T0.2 (commit `6ebebdc`).
curl -s "http://localhost:8009/api/v1/portfolio/paper_trading/probabilistic-sharpe?benchmark=0.0" | jq
```

Decision matrix (from the T1.2 runbook):

| Outcome | Action |
|--|--|
| PSR(flag-on) > PSR(baseline) at p < 0.10 | Promote: keep flag on, publish evidence, document in `docs/strategy/`. |
| PSR(flag-on) ≈ PSR(baseline) (overlap) | Inconclusive. Run another 7 days OR (vol targeting only) enlarge `vol_target_cap_multiplier` to 1.5 and rerun. |
| PSR(flag-on) < PSR(baseline) at p < 0.10 | Reject: flip flag off, write the negative result into `docs/strategy/` (link the commit), do not publish. |

---

## Default-on gate

`services/trading-engine/tests/test_config_default_on_gate.py` contains
`test_tier1_flag_default_on_requires_published_evidence`. It:

1. Reads `services/trading-engine/app/config.py` with a regex.
2. For each of `{enable_vol_targeting, prefer_maker_orders, enable_funding_gate}`,
   checks if the field has `default=True`.
3. If `default=True` found, asserts that
   `.planning/evidence/forward_paper_test/<flag>/PSR_CI_PUBLISHED` exists.
4. If the marker is missing, the test FAILS — blocking the PR in CI.

This gate is filesystem-based and deterministic. It does not depend on the
canonical kernels or any network call.

**Rationale:** Each Tier-1 flag changes trading behaviour in ways that can
affect realized edge. The GRU models previously had look-ahead leakage that
inflated reported performance; we do not want a repeat where a flag is enabled
by default before it is validated. The 7-day paper-trade window with PSR CI
is the minimum credible evidence bar.

---

## Troubleshooting

**"TRADING_MODE=LIVE is set" error on launch**

The launcher refuses to run if TRADING_MODE=LIVE. Unset it:
```bash
unset TRADING_MODE
export PAPER_TRADING_MODE=true
```

**"PAPER_TRADING_MODE=false" error**

Set the env var before running:
```bash
export PAPER_TRADING_MODE=true
```

**"got fewer than 30 observations" from psr_ci.py**

The `run.json` returns array has < 30 elements. Causes:
- Run ended too early (< 7 days, few trades).
- Per-day returns used instead of per-trade returns (7 days = 7 observations).
- Paper-trade log not parsed correctly.

Fix: Ensure `run.json` contains per-trade returns. If the run genuinely
produced fewer than 30 trades, extend the run duration or add more symbols.

**"n_resamples_valid < 0.9 * n_resamples" warning from psr_ci.py**

Many bootstrap resamples hit zero-std windows. This often means returns are
very sparse or close to zero. Check that the trading engine actually traded
during the run: `SELECT COUNT(*) FROM trades WHERE created_at > '<start>';`

**"psr_ci_low <= 0.0" refusal from publish-evidence**

The CI brackets zero — no statistical evidence of positive edge. Options:
1. Extend the run to get more observations and recompute.
2. Investigate if the flag actually helps (check per-trade P&L).
3. Force-publish with `--force` if you want to proceed despite no evidence
   (writes `force_override.txt` for audit trail).

**publish-evidence exits non-zero: "run.json not found"**

The `complete-run` step was skipped. Either run `complete-run` or write
`run.json` manually (schema above).

**Default-on gate fails in CI despite PSR_CI_PUBLISHED existing**

Check the marker file path exactly:
`.planning/evidence/forward_paper_test/<flag_name>/PSR_CI_PUBLISHED`
The `<flag_name>` must match the Python field name exactly (e.g.,
`enable_vol_targeting`, not `ENABLE_VOL_TARGETING`).
