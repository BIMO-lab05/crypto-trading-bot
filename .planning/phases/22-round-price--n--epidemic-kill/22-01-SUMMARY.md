---
phase: 22-round-price--n--epidemic-kill
plan: 01
subsystem: testing
tags: [price-precision, ast-guard, trading-engine, ada, tdd, PRICE-01, PRICE-02]

# Dependency graph
requires:
  - phase: 21-ta-aggregator-widening-leakage-net
    provides: "ATR threading into SimpleRSIStrategy, which moved the SL/TP rounding sites to :214-215 and made the ATR fraction a real producer contract"
  - phase: WS1-B (2026-08-17)
    provides: "tests/test_price_rounding_invariant.py — the AST guard, its ALLOW_MARKER opt-out, and the float()+PRICE-01-comment fix pattern at support_resistance_detector.py:629-643"
provides:
  - "Full-precision stop_loss/take_profit on the live ensemble path (SimpleRSIStrategy, leg 1)"
  - "ADA-scale two-sided precision regression at services/trading-engine/tests/test_sub_dollar_price_safety.py"
  - "AST guard coverage grown 6 -> 9 files; all three trading-engine residue files enrolled"
  - "Site-by-site unit classification of 26 banned rounding calls in the two serialization files"
affects: [22-02, any phase touching trading-engine serialization or the ensemble signal path]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Guard enrollment discipline: clean the file, THEN append to SCANNED_FILES"
    - "Marker placed on the physical line ast reports as node.lineno; wrap the call when the marker would push past 100 cols"
    - "Precision fixtures rebuild the producer's own arithmetic instead of copying a decimal constant"

key-files:
  created:
    - services/trading-engine/tests/test_sub_dollar_price_safety.py
  modified:
    - services/trading-engine/app/strategies/simple_rsi_strategy.py
    - services/trading-engine/app/analytics/post_trade_analysis.py
    - services/trading-engine/app/trading_enhancements/adaptive_rsi.py
    - tests/test_price_rounding_invariant.py

key-decisions:
  - "PRICE-02 satisfied by growing the existing AST guard, not by building the parallel grep gate REQUIREMENTS.md specifies — the AST guard is strictly stronger (six call shapes, per-line opt-out) and already precedent"
  - "PRICE-01 fixture asserts exact equality with the unrounded computation rather than tick-size conformance; tick quantization stays at order time in app/costs.py quantize_price"
  - "The ATR fraction in the test is read back from SimpleRSIStrategy._resolve_atr_fraction, not typed as 0.014043 — that literal is a different double from 1.4043/100.0, so a copied constant would have made GREEN unreachable"
  - "Of 29 banned rounding calls across the three files, exactly 4 are per-unit prices; the other 25 are USD aggregates, bps, ratios, percents, seconds or 0-1 scores and keep round() with a marker justified at the site"
  - "post_trade_analysis.py:150 uses a wrapped round( call so the marker lands on node.lineno; verified stable under black so a future format pass cannot silently orphan it"

patterns-established:
  - "Two-sided precision assertions: equal the unrounded value AND differ from its own N-dp rounding, so a coarser reintroduction also fails"
  - "Provenance comments record WHY a value is not a price (the arithmetic that multiplies by size/notional), so a later audit does not reopen the classification"

requirements-completed: [PRICE-01, PRICE-02]

# Metrics
duration: 42 min
completed: 2026-08-27
---

# Phase 22 Plan 01: round(price, N) Epidemic Kill — Live Path Summary

**Killed the 4dp SL/TP quantization on the live ensemble path (SimpleRSIStrategy leg 1), classified 29 banned rounding calls across three trading-engine files by unit, and grew the AST price-precision guard from 6 to 9 files.**

## Performance

- **Duration:** 42 min
- **Started:** 2026-08-27T13:26:00Z
- **Completed:** 2026-08-27T14:08:26Z
- **Tasks:** 3
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `SimpleRSIStrategy.generate_signal` now returns `stop_loss` / `take_profit` at full float precision. 4dp is *exactly* the ADAUSDT tick, so the previous code quantized every ADA stop onto one tick and destroyed the entire sub-tick component of the ATR offset. These values flow into `EnsembleSignal` unchanged — nothing downstream re-derives them.
- `post_trade_analysis.py` `price_improvement` is full-precision, so sub-1e-4 execution improvements stop being mis-reported (see the magnitude table below).
- `adaptive_rsi.py` `atr_value` is full-precision — ATR is an absolute price-unit range, not a percentage.
- The AST guard now covers all three files. A future reintroduction of `round(x, 2)` or `round(x, 4)` in any of them fails `tests/test_price_rounding_invariant.py` at CI rather than shipping.

## Task Commits

1. **Task 1: RED — ADA-scale SL/TP precision regression** — `1497bf0` (test)
2. **Task 2: GREEN — float() SL/TP on the live path + enroll simple_rsi_strategy.py** — `e2df864` (fix)
3. **Task 3: Classify and clean the two serialization files, enroll both** — `112da5c` (fix)

## RED evidence (Task 1, required by the plan)

`cd services/trading-engine && python3 -m pytest tests/test_sub_dollar_price_safety.py --no-cov -q` at commit `1497bf0`, **exit 1**:

```
E   AssertionError: stop_loss 0.5965 != unrounded 0.5964636218; round(price, 4) quantized the ADA stop onto a single tick
tests/test_sub_dollar_price_safety.py:85: AssertionError
E   AssertionError: stop_loss 0.5965 is still quantized to 4dp - exactly the ADAUSDT tick
tests/test_sub_dollar_price_safety.py:101: AssertionError
E   AssertionError: stop_loss 0.6309 != unrounded 0.6309363782 on the short side
tests/test_sub_dollar_price_safety.py:119: AssertionError
FAILED tests/test_sub_dollar_price_safety.py::test_buy_stop_and_target_equal_the_unrounded_computation
FAILED tests/test_sub_dollar_price_safety.py::test_buy_stop_and_target_are_not_quantized_to_the_ada_tick
FAILED tests/test_sub_dollar_price_safety.py::test_sell_stop_and_target_survive_at_full_precision
3 failed, 1 passed in 2.05s
```

The one passing test is `test_four_decimal_rounding_is_a_real_loss_not_float_noise` — the defect-class witness, which is fix-independent by design and pins the premise that the fixture sits at a scale where 4dp actually bites. After `e2df864`: **4 passed, exit 0**.

## Magnitude of the live-path behavior change

**This commit changes served SL/TP values. It is a precision change, not a strategy change — do not read a P&L comparison across it as an edge result.**

At the ADA fixture (price 0.6137, ATR 1.4043%):

| Leg | Previously served (4dp) | Now served | Delta |
|---|---|---|---|
| BUY stop_loss | 0.5965 | 0.5964636218 | 3.64e-05 |
| BUY take_profit | 0.6482 | 0.6481727564 | 2.72e-05 |
| SELL stop_loss | 0.6309 | 0.6309363782 | 3.64e-05 |
| SELL take_profit | 0.5792 | 0.5792272436 | 2.72e-05 |

Deltas are **below tick for BTC / ETH / SOL / BNB** (ticks 0.10, 0.01, 0.010, 0.10) and **at tick for ADA** (0.0001) — so only ADA can see a different fill, and only by one tick. No ablation required per CONTEXT.md; stated explicitly here so a later P&L comparison across this commit is not misread.

`price_improvement` telemetry was worse than "off by a tick". Measured through the real `PostTradeAnalyzer.analyze_trade` on an ADA-scale fill:

| True improvement | 4dp served | Now served |
|---|---|---|
| 5.3425e-05 | 0.0001 (87% overstatement) | 5.3425e-05 |
| 4.0e-05 | 0.0 | 4.0e-05 |
| 1.5e-05 | 0.0 | 1.5e-05 |

The plan predicted flattening to `0.0`; that holds below 5e-5, while the upper half of the sub-1e-4 band was *overstated* instead. Both directions were wrong — execution-quality telemetry was unusable at ADA scale either way.

## Trading-engine suite: pre- vs post-change

Captured from `services/trading-engine` with `--no-cov`:

| | Passed | Skipped | Failed |
|---|---|---|---|
| Pre-change (at `473c874`) | 2122 | 795 | **0** |
| Post-change (at `112da5c`) | 2126 | 795 | **0** |

Delta is exactly +4 — the four new tests. **No new failure families.** Note the plan's expected pre-existing failure families (`test_repositories`, `test_pairs_trading`, `test_connector_contract`, `test_handler_endpoints`, `test_main`, per STATE.md OP-12) did **not** appear as failures: they are currently *skipped* ("stale tests after PR #86 refactor; needs rewrite"), so the baseline is clean rather than merely stable. Worth knowing before someone reads OP-12 as still-red.

## Classification ledger

29 banned calls across the three enrolled files. **4 became `float()`; 25 kept `round()` with a marker.**

| File | Banned sites | → `float()` | Markers |
|---|---|---|---|
| `simple_rsi_strategy.py` | 3 | `stop_loss`, `take_profit` | 1 (`confidence`, a 0-1 score) |
| `post_trade_analysis.py` | 22 | `price_improvement` | 21 |
| `adaptive_rsi.py` | 4 | `atr_value` | 3 (`rsi_value`, `atr_percentage`, `signal_strength`) |

The four `post_trade_analysis.py` fields that *look* like prices — `market_impact`, `spread_cost`, `timing_cost`, `total_slippage` — are USD costs, because `_calculate_slippage` multiplies every component through by size or notional first (`slippage_cost = raw_slippage * size`; `spread_cost = spread_bps / 10000 * notional / 2`). That provenance is now recorded in a comment above the `SlippageBreakdown.to_dict()` return so the classification is not reopened by a future audit. The 8dp `expected_price` / `execution_price` sites are outside `BANNED_NDIGITS`, non-destructive at every supported tick, and were left untouched per CONTEXT.md.

## Files Created/Modified

- `services/trading-engine/tests/test_sub_dollar_price_safety.py` *(created)* — four ADA-scale tests: BUY exact-equality, BUY two-sided non-quantization, SELL both, and a fix-independent defect-class witness.
- `services/trading-engine/app/strategies/simple_rsi_strategy.py` — `stop_loss` / `take_profit` → `float()`; `confidence` keeps `round()` with a marker; PRICE-01 provenance comment above the `SimpleRSISignal(` construction.
- `services/trading-engine/app/analytics/post_trade_analysis.py` — `price_improvement` → `float()`; 21 markers; USD-cost provenance comment on `SlippageBreakdown.to_dict()`.
- `services/trading-engine/app/trading_enhancements/adaptive_rsi.py` — `atr_value` → `float()`; 3 markers.
- `tests/test_price_rounding_invariant.py` — `SCANNED_FILES` 6 → 9; stale debt comment naming `simple_rsi_strategy.py` at the wrong line range (`:121-122`) deleted; module docstring's marker inventory extended past WS1-B without naming any file (the enrollment entry must remain each path's only mention).

## Decisions Made

- **Marker placement under the column limit.** Appending the 19-char marker pushed `post_trade_analysis.py:150` from 88 to 107 columns, past the repo's 100. Since `ast.Call.lineno` is the line where `round(` *starts*, a formatter wrapping that call would move the node off the marker line — the guard would then report a violation while the marker-count pin still passed. Resolved by wrapping the call myself with the marker on the `round(` line, and verified by piping both files through `black` and re-running `find_violations` on the output: 0 violations, 21 and 3 markers intact. No other line crossed 100.
- **Both files were already black-nonconforming at HEAD**, so black is not enforced on them; the stability check above is belt-and-braces, not a gate.
- **Provenance comments deliberately avoid the literal marker string**, since the acceptance pins use `text.count()` and a prose mention would over-count.

## Deviations from Plan

None — plan executed exactly as written. All per-line dispositions in the plan matched the source on verification (22 / 4 / 3 banned sites at exactly the line numbers listed).

Two plan statements were refined rather than contradicted, both recorded above: the `price_improvement` distortion is an overstatement rather than a flattening in the upper half of the sub-1e-4 band, and the OP-12 failure families are currently skipped rather than failing.

**Total deviations:** 0
**Impact on plan:** None. No scope creep, no packages installed, no tick logic added at the signal layer.

## Issues Encountered

- **`0.014043 != 1.4043 / 100.0` as doubles.** Caught before writing the fixture. Had the test hardcoded the decimal literal, the exact-equality assertion in Task 1 could never have gone green in Task 2, and the failure would have looked like a bug in `simple_rsi_strategy.py`. The fixture calls `SimpleRSIStrategy._resolve_atr_fraction` instead, making it bit-identical by construction — and, as a bonus, a contract check rather than a copied constant. It also keeps the token `100` out of a file whose acceptance criteria ban balance literals.
- Multiplication order in the fixture matches `simple_rsi_strategy.py:198` exactly; float multiplication is not associative, so reordering would break bit-equality.

## Known Stubs

None.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes. All five edits are in-tree Python.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- **Ready for 22-02**, which owns the remaining two "Not yet covered" entries in the guard: `services/technical-analysis/app/handlers/sqzmom.py` and the other `app/indicators/*.py` modules (~17 sites). Both lines were left in place deliberately.
- **Deployment is NOT done.** CONTEXT.md requires a rebuild plus `--force-recreate` of trading-engine and a `docker exec` proof that the `float()` change is in the running image. That was out of scope for this plan's tasks and has not been performed — the running container still serves 4dp SL/TP. Per CLAUDE.md §7, this plan is verified at the source and test level only.
- The guard is the only mechanical barrier to reintroduction. Removing a file from `SCANNED_FILES` to make it green is a discipline violation the docstring calls out explicitly.

---
*Phase: 22-round-price--n--epidemic-kill*
*Completed: 2026-08-27*
