---
phase: 22-round-price--n--epidemic-kill
plan: 02
subsystem: testing
tags: [price-precision, ast-guard, technical-analysis, sqzmom, ada, docker, PRICE-01, PRICE-02]

# Dependency graph
requires:
  - phase: 22-01
    provides: "AST guard grown 6 -> 9 files, the three trading-engine residue files cleaned, and the float()+PRICE-01-comment fix pattern applied at scale"
  - phase: WS1-B (2026-08-17)
    provides: "tests/test_price_rounding_invariant.py — the AST guard, ALLOW_MARKER opt-out, BANNED_NDIGITS {2,4}"
provides:
  - "Full-precision price-unit momentum on GET /api/v1/indicators/sqzmom/{symbol} and SqueezeMomentumIndicator.get_signal"
  - "The literal round(entry_price, 2) / round(exit_price, 2) 487d1bd pattern removed from the repo"
  - "AST guard coverage 9 -> 12 files; all six Phase 22 residue files enrolled"
  - "Guard docstring converted from a hand-maintained per-site enumeration to a regenerable rule + two scanned figures"
  - "Phase 22's source fixes deployed to the running crypto-bot-ta and crypto-bot-trading images"
affects: [any phase touching TA indicator serialization, sqzmom backtests, or the price-precision guard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Guard docstring states only figures a scan can regenerate; enumerations that must be hand-edited on every fix are banned"
    - "In-image verification asserts PRESENCE of the new token, never absence of the old one — round(price, 2) also appears in comments and in the guard's own prose"
    - "Edits applied by unique-string replacement before any comment insertion, so provenance comments cannot shift later targets"

key-files:
  created:
    - .planning/phases/22-round-price--n--epidemic-kill/22-02-SUMMARY.md
  modified:
    - services/technical-analysis/app/handlers/sqzmom.py
    - services/technical-analysis/app/indicators/squeeze_momentum.py
    - services/technical-analysis/backtesting/sqzmom_backtest.py
    - tests/test_price_rounding_invariant.py

key-decisions:
  - "SQZMOM momentum classified as a PRICE-unit quantity (a linear-regression residual on price), so all five momentum sites convert to float() rather than taking a marker — marking a price is the exact marker abuse the guard docstring warns against"
  - "All 27 non-price sites in sqzmom_backtest.py keep round() with a marker; they are USD aggregates, ratios, percents and counts. duration_hours at round(..., 1) is outside BANNED_NDIGITS and was left untouched and unmarked"
  - "The deleted per-site enumeration was ACCURATE (4 + 12 = 16 checked out), not false. It was removed because it is hand-maintained and had already rotted once into citing a moved line range"
  - "Docker proof set is five in-image files only; backtesting/sqzmom_backtest.py is proven ABSENT from the image with a positive test -f non-zero check, so its exclusion is demonstrated rather than assumed"

patterns-established:
  - "Pre-edit find_violations dump serves as RED evidence when the pre-existing guard is the test and clean-first discipline forbids an enroll-to-fail commit"
  - "Post-commit re-verification of find_violations on the on-disk file, because a reformatting hook could move a marked call off its marker line while the count() pin still passed"

requirements-completed: [PRICE-01, PRICE-02]

# Metrics
duration: 14 min
completed: 2026-08-27
---

# Phase 22 Plan 02: SQZMOM Precision Kill and Deployment Summary

**Removed the literal `round(entry_price, 2)` 487d1bd pattern from the sqzmom backtest serializer, converted five price-unit SQZMOM momentum sites to `float()`, grew the AST guard to 12 files with a docstring whose every figure is regenerable, and deployed the whole phase into the running containers — live ADAUSDT momentum now serves `0.0037248928571428554` where it previously served `0.0037`.**

## Performance

- **Duration:** 13.8 min
- **Started:** 2026-08-27T17:05:43Z
- **Completed:** 2026-08-27T17:19:29Z
- **Tasks:** 3 (2 with commits, 1 deployment/verification-only)
- **Files modified:** 4

## Accomplishments

- **The original defect pattern is gone from the repo.** `sqzmom_backtest.py:118,120` was the verbatim `round(entry_price, 2)` / `round(exit_price, 2)` that commit `487d1bd` was written to kill; it survived in the backtest serializer. Every sqzmom backtest ever run reported ADA entries snapped to a 1-cent grid.
- **`/api/v1/indicators/sqzmom/{symbol}` serves unrounded momentum.** SQZMOM momentum is a linear-regression residual on price, so it carries price units — 4dp is *exactly* the ADAUSDT tick, and ADA-scale momentum is ~1e-3, so `round(x, 4)` left it one to two significant digits.
- **AST guard at 12 files, 72 markers, zero violations.** All six Phase 22 residue files are enrolled.
- **Phase 22 is deployed, not just written.** 22-01's SUMMARY explicitly flagged that the running container still served 4dp SL/TP. Both services are now rebuilt and force-recreated, and the 22-01 fixes are proven present in the trading-engine image alongside 22-02's.

## Task Commits

1. **Task 1: Clean and enroll the two technical-analysis `app/` files** — `f0a7559` (fix)
2. **Task 2: Kill the backtest `round(entry_price, 2)`, enroll it, correct the guard docstring** — `0550770` (fix)
3. **Task 3: Rebuild and force-recreate both services; prove the fix is in the running images** — no commit (verification and deployment only; the plan specifies `<files>none`)

## RED evidence

Both tasks are marked `tdd="true"`, but neither creates a test — the pre-existing AST guard *is* the test, and the plan forbids in bold enrolling a file before cleaning it, so an enroll-to-fail RED commit was not available. See `## TDD Gate Compliance` below. The pre-edit detector dump is the RED artifact. Run at `ea26427` against the three target files, it reported **38 banned rounding calls at exactly the line numbers the plan predicted** — 6 / 3 / 29:

```
handlers/sqzmom.py 6
  109:                 "value": round(float(latest["sqz_momentum"]), 4),
  128:                 "confidence": round(float(latest["sqz_confidence"]), 2),
  358:                 "squeeze_on_pct": round(squeeze_on_count / total_bars * 100, 2)
  364:                 "avg_momentum": round(float(backtest_df["sqz_momentum"].mean()), 4)
  367:                 "max_momentum": round(float(backtest_df["sqz_momentum"].max()), 4)
  370:                 "min_momentum": round(float(backtest_df["sqz_momentum"].min()), 4)
squeeze_momentum.py 3
  496:         return round(confidence, 2)
  541:             "momentum": round(float(momentum), 4),
  543:             "strength": round(float(strength), 2),
sqzmom_backtest.py 29
  118:             'entry_price': round(self.entry_price, 2),
  120:             'exit_price': round(self.exit_price, 2) if self.exit_price else None,
  ... 27 more (position_size, pnl, pnl_pct, commission, net_pnl, and the
      :560-577 / :644-649 / :748 run-level aggregate blocks)
```

## Classification ledger

38 banned calls across the three files. **7 became `float()`; 31 kept `round()` with a marker.**

| File | Banned sites | → `float()` | Markers |
|---|---|---|---|
| `app/handlers/sqzmom.py` | 6 | `momentum.value`, `avg_momentum`, `max_momentum`, `min_momentum` | 2 (`confidence` 0-1, `squeeze_on_pct` percent) |
| `app/indicators/squeeze_momentum.py` | 3 | `get_signal()["momentum"]` | 2 (`_calculate_confidence` return, `strength` 0-1) |
| `backtesting/sqzmom_backtest.py` | 29 | `entry_price`, `exit_price` | 27 (USD aggregates, ratios, percents, counts) |

`duration_hours` uses `round(..., 1)`, which is outside `BANNED_NDIGITS` — left untouched and unmarked, as the plan directs.

The four `avg`/`max`/`min_momentum` sites were converted rather than marked. CONTEXT.md's discretion clause permitted either, but a marker is a claim that a value is *not a per-unit price*, and these are the same price-domain quantity as `momentum.value`. Marking them would have been a false claim recorded in the source.

## Live behavior change (measured, not predicted)

`GET http://localhost:8004/api/v1/indicators/sqzmom/ADAUSDT` after rebuild:

```json
{
  "symbol": "ADAUSDT",
  "interval": "60",
  "momentum": {
    "value": 0.0037248928571428554,
    "color": "green",
    "direction": "bullish"
  },
  "current_price": 0.2153
}
```

`round(0.0037248928571428554, 4)` is `0.0037` — what this endpoint served before this commit. At an ADA price of $0.2153 that is **two significant digits of a ~1e-3 quantity**, so any consumer comparing momentum against a threshold was comparing against a heavily quantized reading. SOLUSDT cross-check: served `4.913339285714285`, previously `4.9133`.

## Trade serialization change

Verified by instantiating the real `Trade` class at ADA scale:

| Field | Pre-fix served | Now served |
|---|---|---|
| `entry_price` | `0.61` | `0.61374829` |
| `exit_price` | `0.63` | `0.62918374` |
| `exit_price` (open trade) | `None` | `None` (conditional preserved) |
| `pnl` / `commission` / `duration_hours` | `15.44` / `0.68` / `24.0` | unchanged |

## PROVENANCE WARNING — sqzmom backtest artifacts

**Every sqzmom backtest artifact produced by `services/technical-analysis/backtesting/sqzmom_backtest.py` before commit `0550770` reported `entry_price` and `exit_price` on a 1-cent grid.** For sub-$1 symbols those figures are **wrong, not merely imprecise**: ADA's tick is 0.0001, so 2dp is a 100x loss of resolution and a fill at 0.6137 was recorded as 0.61. Do not compare pre-fix artifacts from this file against post-fix runs. This is recorded as a comment on `Trade.to_dict()` in the source so a future auditor finds it at the site.

## Technical-analysis suite: pre- vs post-change

Captured from `services/technical-analysis` with `--no-cov`:

| | Passed | Failed | Exit |
|---|---|---|---|
| Pre-change (at `ea26427`) | **711** | 0 | 0 |
| Post-change (at `f0a7559`) | **711** | 0 | 0 |

Identical. No new failure families and no test needed correcting — no existing TA test pinned a 4dp momentum value. `test_squeeze_momentum.py:285` and `test_enhanced_sqzmom_service.py:129` assert `isinstance(..., float)`, which `float()` still satisfies; `test_sqzmom_strategy_precision.py` covers `squeeze_momentum_strategy.py`, already enrolled and clean.

## Guard figures (regenerable — re-derive, do not re-litigate)

| Figure | Value | How to regenerate |
|---|---|---|
| Scanned files | **12** | `len(SCANNED_FILES)` |
| Violations across all enrolled | **0** | `find_violations` over `SCANNED_FILES` |
| Whole-repo markers | **72** | sum of `text.count("# non-price-round")` over `SCANNED_FILES` (was 41 pre-plan; +31 here) |
| Remaining uncovered | **14 across 7 files** | `find_violations` over unenrolled `app/indicators/*.py` |

The 14 break down as `adx.py` (6), `ichimoku.py` (2), `moving_averages.py` (2), `bollinger_bands.py` (1), `macd.py` (1), `rsi.py` (1), `rsi_divergence.py` (1). The pre-plan figure was 17; enrolling `squeeze_momentum.py` (3 sites) accounts for the difference exactly.

## Deployment proof

**Pre-flight capture (before touching any container):**

- All 14 containers `healthy`; `crypto-bot-trading` up 4h, `crypto-bot-ta` up 12h.
- `safety/EMERGENCY_STOP` **absent** — so the auto-trader loop self-resumes on boot. Expected per CLAUDE.md §5 and the operator `.env` `AUTO_TRADING_ENABLED=true`, not a regression.
- Open paper positions: **4** — ETHUSDT SHORT `af48f6cf`, BNBUSDT LONG `ba93f736`, BTCUSDT LONG `b60eee8e`, ADAUSDT SHORT `5589c83e`.
- `docker context` is `default`.

**Build and recreate:** `DOCKER_BUILDKIT=0` plus a fresh `DOCKER_CONFIG=$(mktemp -d)` (vsock credential workaround), `docker-compose.unified.yml`, `build technical-analysis trading-engine` then `up -d --no-deps --force-recreate technical-analysis trading-engine`. Both images rebuilt (`crypto-trading-bot-technical-analysis:latest` → `a5663f3db007`, `crypto-trading-bot-trading-engine:latest` → `8596c345c340`). No other service was rebuilt or recreated; the other 12 containers kept their original uptimes.

**In-image proofs** — presence of the new token, never absence of the old one:

| Assertion | Result |
|---|---|
| `crypto-bot-trading` `grep -c "stop_loss=float(stop_loss)"` `simple_rsi_strategy.py` | `1` |
| `crypto-bot-trading` `grep -c "take_profit=float(take_profit)"` `simple_rsi_strategy.py` | `1` |
| `crypto-bot-trading` `grep -c '"atr_value": float('` `adaptive_rsi.py` | `1` |
| `crypto-bot-trading` `grep -c '"price_improvement": float('` `post_trade_analysis.py` | `1` |
| `crypto-bot-ta` `grep -cF 'round(float(latest["sqz_momentum"]), 4)'` `handlers/sqzmom.py` | `0` |
| `crypto-bot-ta` `grep -cF 'float(latest["sqz_momentum"])'` `handlers/sqzmom.py` | `1` |
| `crypto-bot-ta` `grep -c '"momentum": float('` `indicators/squeeze_momentum.py` | `1` |
| `crypto-bot-ta` `test -f /app/backtesting/sqzmom_backtest.py` | **exit 1** (correctly absent) |

Both Dockerfiles were re-read to confirm the `COPY --chown=appuser:appuser app/ ./app/` scope (`technical-analysis/Dockerfile:60`, `trading-engine/Dockerfile:71`) before any in-image assertion was written. `backtesting/` is out of build context, which is why it is excluded from the proof set — demonstrated by the `test -f` check rather than assumed.

**Post-recreate reconciliation:**

- `GET :8004/health` → `200`, body `{"status":"healthy","service":"technical-analysis","market_data_connection":true,...}`
- `GET :8005/health` → `200`, body `{"status":"healthy","service":"trading-engine","technical_analysis_connection":true,"bybit_connector_connection":true,"database_connection":true,...}`
- `crypto-bot-ta` and `crypto-bot-trading` both `healthy`; all 14 containers healthy.
- Open positions: **4, identical symbols / sides / quantities / IDs** to the pre-flight capture. Positions live in the DB, so this confirms the recreate did not disturb state.

## Files Created/Modified

- `services/technical-analysis/app/handlers/sqzmom.py` — momentum `value` and the three backtest-summary momentum stats → `float()`; `confidence` and `squeeze_on_pct` keep `round()` with markers; PRICE-01 provenance comment above the momentum block.
- `services/technical-analysis/app/indicators/squeeze_momentum.py` — `get_signal()["momentum"]` → `float()`; `_calculate_confidence` return and `strength` keep `round()` with markers; PRICE-01 provenance comment.
- `services/technical-analysis/backtesting/sqzmom_backtest.py` — `entry_price` / `exit_price` → `float()`; 27 markers; PRICE-01 provenance comment on `Trade.to_dict()` naming `487d1bd` and the artifact-comparability warning.
- `tests/test_price_rounding_invariant.py` — `SCANNED_FILES` 9 → 12; the "Not yet covered" block folded into the docstring; the `roughly 17` figure corrected to 14 across 7 named files; the per-site marker enumeration replaced with the classification rule, the 72-marker total, and an explicit note that both figures are regenerable by scanning.

## Decisions Made

- **Edit ordering: all conversions and markers first, provenance comments last.** Inserting a comment above `handlers/sqzmom.py:109` would have shifted every subsequent target line. All edits were applied by unique-string replacement (asserting `count(old) == 1`) rather than by line number, and the comments went in only after `find_violations` returned `[]` for all three files.
- **`:358` `squeeze_on_pct` opens a multi-line conditional.** Its marker had to land on the physical line `ast` reports as `node.lineno`, and a comment inside an implicit line continuation is legal Python. Verified by re-running the detector after the edit rather than assuming — and again after the commit, in case a hook reformatted. The marked line is 98 columns, under the repo's 100.
- **Bash+pathlib used for every edit, never the Edit tool**, per the known ruff-at-88 format-hook hazard. `git diff --stat` shows 21 insertions / 10 deletions for Task 1 and exactly 29/29 for the backtest file — no reflow, no import churn.
- **The deleted enumeration was accurate, not wrong.** "Four such sites… twelve more" summed to 16, which checked out. It was removed because it is hand-maintained and had already rotted once into citing a line range that later moved. Saying so here so the next auditor does not go looking for a factual error that was never there.
- **Provenance comments deliberately avoid the literal `# non-price-round` string**, since the acceptance pins use `text.count()` and a prose mention would over-count. This constraint does not apply to the guard docstring, which is not in `SCANNED_FILES`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan's live-endpoint and positions URLs do not exist**

- **Found during:** Task 3 (deployment verification)
- **Issue:** Two URLs in the plan's acceptance criteria 404 against the running stack. `GET http://localhost:8004/indicators/sqzmom?symbol=ADAUSDT` returned `404` — the TA service mounts the route as a path parameter under an `/api/v1` prefix. `GET http://localhost:8003/api/portfolio/positions` returned `{"detail":"Not Found"}` — portfolio-manager exposes no positions route at all.
- **Fix:** Resolved both from the services' own `openapi.json` rather than guessing. Momentum check now uses `GET http://localhost:8004/api/v1/indicators/sqzmom/ADAUSDT`; positions use `GET http://localhost:8000/api/trading/positions` through the gateway (portfolio-manager's nearest local equivalent, `/api/v1/portfolio/holdings`, reports holdings rather than open positions and was used only as a cross-check).
- **Files modified:** None — verification commands only.
- **Verification:** Both corrected URLs return `200` with the expected payload shape; the two-sided momentum invariant passes on ADAUSDT first try, and SOLUSDT was run as an independent confirmation.
- **Committed in:** N/A (Task 3 commits no source)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** None on scope or substance. Both were stale URLs in verification criteria, not defects in the code under change. Every acceptance criterion was met against the corrected endpoints. No packages installed, no tick logic added at the signal or indicator layer.

## Issues Encountered

- **The `momentum.value != round(value, 4)` invariant is not safe against a legitimate `0.0`**, since `0.0 == round(0.0, 4)`. The plan anticipated this and prescribed retrying a second symbol. It did not fire — ADAUSDT returned `0.0037248928571428554` on the first call — but SOLUSDT was run anyway as an independent witness. Noting it because the sibling assertions in `test_sqzmom_strategy_precision.py` carry an explicit `or value == 0.0` escape and this one does not.
- **The build log tail initially showed only the trading-engine image**, making it look as though technical-analysis had not been rebuilt. It had: `docker images` shows `crypto-trading-bot-technical-analysis:latest` created before the engine image in the same run. The `tail -40` on the build output had simply cut the earlier half. Confirmed by image age and by the in-image greps, which only pass against the new layer.

## TDD Gate Compliance

Both tasks carry `tdd="true"`, and neither produced a `test(...)` commit. This is deliberate and does not indicate a skipped RED gate:

- The test for this behavior — `tests/test_price_rounding_invariant.py` — **already existed** and already detected all 38 sites. `files_modified` lists no new test file and no acceptance criterion references one.
- The only way to manufacture a failing-then-passing commit pair would be to append the three files to `SCANNED_FILES` *before* cleaning them. The plan forbids that in bold ("Clean first, enroll second"), and the guard's own docstring calls it out as the discipline violation that gets guards disabled instead of obeyed.

The pre-edit `find_violations` dump reproduced above is the RED artifact; the post-edit green guard run is the GREEN gate. Both commits are typed `fix(...)` rather than `feat(...)` because this is a defect-class removal, not new behavior.

## Known Stubs

None.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes. All edits are in-tree Python; the rebuild uses the existing pinned `requirements.txt` (T-22-SC disposition `accept` holds — no package was installed).

## Threat model dispositions

| Threat ID | Disposition | Status |
|---|---|---|
| T-22-05 (backtest data integrity) | mitigate | **Done** — `float()` at `:118,120`; provenance warning recorded in source and above |
| T-22-06 (false momentum telemetry) | mitigate | **Done** — five sites converted; live ADAUSDT response asserted >4dp |
| T-22-02 (guard docstring rot) | mitigate | **Done** — `len == 12`, 72 markers, 14-across-7 regenerated by scan; `roughly 17`, `Four such sites` and `121-122` all absent |
| T-22-07 (restart DoS) | accept | Bounded — two services only, `--no-deps`, position count reconciled 4 → 4 |
| T-22-08 (self-invalidating grep) | mitigate | **Done** — presence assertions only; `backtesting/` absence proven by `test -f` |
| T-22-SC (supply chain) | accept | No packages installed |

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Phase 22 is complete and deployed.** All six residue files are cleaned, enrolled, and (for the five in-image ones) proven live in the running containers. 22-01's "Deployment is NOT done" caveat is now closed.
- **14 sites remain uncovered** across seven `app/indicators/*.py` modules (`adx.py` 6, `ichimoku.py` 2, `moving_averages.py` 2, `bollinger_bands.py` 1, `macd.py` 1, `rsi.py` 1, `rsi_divergence.py` 1). These are the next PRICE-02 tranche. The guard docstring names them, so a future planner does not need to re-derive the list — but should re-run the scan anyway, since the docstring now explicitly says both its figures are regenerable.
- **No STATE.md or ROADMAP.md writes were made** — the orchestrator owns them.

## Self-Check: PASSED

- All 4 modified files present on disk; `22-02-SUMMARY.md` created.
- Both task commits present in `git log`: `f0a7559`, `0550770`. Branch verified `fix/ta-signal-path-phase-21` before each commit. Neither commit deleted a tracked file (`git diff --diff-filter=D` empty for both).
- Every `<acceptance_criteria>` from all three tasks re-run and green, including the exact pins: `len(SCANNED_FILES) == 12`; marker counts 2 / 2 / 27 via `text.count()`; whole-repo total 72; `find_violations == []` for all 12 enrolled files; `float(self.entry_price)` and `float(self.exit_price)` each grep to exactly 1; `round(self.duration_hours, 1)` intact at 1; `grep -cE "14 (further |remaining |uncovered )?sites"` returns 1; `roughly 17`, `Four such sites` and `121-122` all return 0; all eight `docker exec` assertions; both `/health` endpoints 200 with healthy bodies; position count 4 → 4.
- Plan-level `<verification>` 1-5 all green: guard suite passes with 12 files scanned; TA suite 711 → 711 passed with zero failures; `services/trading-engine/tests/test_sub_dollar_price_safety.py` still 4 passed; whole-repo scan over enrolled files returns zero violations; in-image proof complete on all five files with both services healthy.
- Acceptance criteria re-verified on-disk *after* each commit landed, guarding against a reformatting hook moving a marked call off its marker line.

---
*Phase: 22-round-price--n--epidemic-kill*
*Completed: 2026-08-27*
