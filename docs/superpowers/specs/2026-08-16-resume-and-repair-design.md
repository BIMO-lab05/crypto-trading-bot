# Resume and Repair — 2026-08-16

## Context

Docker Desktop was down (found 2026-08-16); the whole 17-service stack was offline for some
window after the 2026-08-12 clean-data epoch resume. Operator asked to resume the system and
fix whatever is broken. Scope approved 2026-08-16: **boot + fix current breakage only** —
deferred backlog (29 profit-path minors, OP-14, pre-existing test debt) stays untouched.
Auto-trader resumes after health checks pass (kill-switch clear, `AUTO_TRADING_ENABLED=true`,
same state operator approved 2026-08-12).

Observed at session start: containers auto-restarted via restart policy once the daemon came
up — 14/14 healthy. So "boot" collapsed to verification; no compose invocation was needed.

## Design

**A. Boot.** Docker daemon up; containers restarted from existing images (no rebuild by
default). Verify running images postdate the 2026-08-12 repaired code — technical-analysis
must contain the kline-cache fix `43e5c5f`; trading-engine must contain `65a817e`. Rebuild
only images proven stale, `DOCKER_BUILDKIT=0`.

**B. Health.** 9/9 service probes green. TimescaleDB `max_connections=100` in effect
(`5fc5b5b`). WSL bind-mount race check — `PermissionError` on `/app/logs` means
`--force-recreate` that service. Known `/ready` 404s on api-gateway and portfolio-manager are
documented overclaims, not failures.

**C. Data integrity.** Determine outage window from last candle timestamp before the gap.
Check kline gap over the outage; backfill via market-data collect endpoints only if TA
lookback windows need it. Verify position book hydrates (fail-loud path `63595b0`); max-hold
sweeps anything held >48h. Ledger identity: cash accounting must be exact against closed
positions. No trades during outage = absence, not contamination — clean-data epoch
2026-08-12T13:47:20Z stands.

**D. Fix loop.** Each breakage found → systematic-debugging, fixed as a GSD quick task,
conventional commit, §7 four-proof verification (live URL in logs, downstream effect, DB row,
restarted service). If ≥3 independent breakages surface → escalate to parallel Workflow
triage.

**E. Resume trading.** Probes green + integrity checks pass → trader runs (arms itself;
kill-switch already clear). Watch one full signal cycle: signals computed, rejections log
reasons, no 500 bursts, TimescaleDB CPU sane.

**F. Hygiene.** Commit untracked `.planning/evidence/killtests/rescore-2026-08-09/` +
`carry_ins.json` timestamp bump. Reconcile STATE.md (stale at 2026-08-04 — still claims
260730-vwn uncommitted; wrong since `d5d31c6`/`1c21eac`). progress.md entry for this session.

## Constraints

Risk caps, paper mode, validated symbols (BTC/ETH/SOL/BNB/ADA) untouched throughout.
$100 account invariant per `shared/account.py`. No LIVE-flip work.

## Success criteria

1. All services healthy, probes green, images current with repaired code.
2. Outage window measured and recorded; kline continuity restored or gap shown harmless.
3. Auto-trader running with correct behavior visible in logs (sizing ≤10%, rejections reasoned).
4. Working tree clean: evidence committed, STATE.md truthful, progress.md updated.
5. Any new defect found is either fixed+verified or filed with an ID and a reason.
