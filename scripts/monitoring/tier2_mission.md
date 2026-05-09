# Tier 2 escalation mission

You were invoked because the tier-1 monitor reported failures. The failure
report is at `$FAILURE_JSON`. The repo root is `$REPO_ROOT`. You are running
non-interactively via `claude -p`.

## Hard constraints (do not violate)

- **Do not relax risk caps.** The 2% per-trade and 5% daily-loss limits in
  trading-engine are load-bearing (see CLAUDE.md). Don't touch them.
- **Do not silently re-add excluded symbols.** Validated symbols are SOL, BNB,
  ADA only. ETH/BTC/XRP/DOGE were excluded for paper-trading data reasons.
- **Do not flip `BYBIT_TESTNET` or `PAPER_TRADING_MODE`.** If the bug appears
  to require it, abort and open an issue instead.
- **Do not push to `main`.** Always work on `fix/auto-monitor-<unix-ts>`.
- **Do not auto-merge.** PRs are for human review.
- **Do not skip pre-commit hooks** (`--no-verify`).
- **Do not delete or rewrite `progress.md`, `docs/architecture/DECISIONS.md`,
  `.env`, or anything in `infrastructure/`.**

## Procedure

1. Read `$FAILURE_JSON`. Treat it as the symptom report, not the diagnosis.
2. Diagnose the root cause. Use service logs (`docker compose -f
   docker-compose.unified.yml logs --since 30m <service>`), recent commits
   (`git log --oneline -20`), and the relevant service code. Form a one-line
   hypothesis before changing anything.
3. Write a **failing regression test** that reproduces the issue at the right
   layer (service unit test under `services/<svc>/tests/` if local; repo
   integration test under `tests/` if cross-service). Confirm it fails on
   `main` before writing the fix.
4. Implement the **minimal** fix. Don't refactor surrounding code; don't add
   abstractions; don't fix unrelated nits.
5. Run the affected tests:
   - `pytest services/<svc>/tests/ -x` for unit-level
   - `pytest tests/ -x -k <relevant>` for integration
   - The new regression test must now pass.
6. Run the backtest gate:
   - `BACKTEST_CMD` is exported in the environment. It must accept a `--ref`
     flag pointing at a git ref to test, and print a final line in the form
     `SHARPE=<float>`.
   - Capture baseline: `git stash && $BACKTEST_CMD --ref main` → `SHARPE_BASE`.
     Then `git stash pop`.
   - Capture fix: `$BACKTEST_CMD --ref HEAD` → `SHARPE_FIX`.
   - If `SHARPE_FIX < SHARPE_BASE * 0.9`: **abort PR creation**. Instead, open
     a GitHub issue titled `auto-monitor: fix candidate regressed Sharpe by
     >10%` with both numbers, the diagnosis, and the diff as a code block.
     Then exit.
7. If the gate passes, commit in conventional style:
   `fix(<service>): <concise description>` — body explains the diagnosis and
   references `$FAILURE_JSON` content.
8. Push the branch and open a PR with `gh pr create`:
   - Title: `fix(<service>): <description> [auto-monitor]`
   - Label: `auto-monitor`
   - Body sections: **Symptom**, **Diagnosis**, **Fix**, **Evidence**
     (test names that now pass + `SHARPE_BASE` / `SHARPE_FIX`),
     **Backout** (`git revert <sha>`).
   - Last line of the body: `@claude please review this auto-generated fix.`
     This triggers the GitHub App for a second pass.

## Stop conditions

Abort and open an issue (don't open a PR) if any of these become true:

- The diagnosis points at config / secrets / exchange-side, not code.
- The fix would require changing more than ~5 files or >150 lines.
- You can't reproduce the failure with a test.
- The backtest gate fails.
- You hit `--max-turns`.

When opening the abort issue, label it `auto-monitor` and `needs-triage`.
