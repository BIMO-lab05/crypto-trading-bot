---
phase: 22-round-price--n--epidemic-kill
verified: 2026-08-27T17:33:20Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
requirements_coverage:
  - id: PRICE-01
    status: satisfied
  - id: PRICE-02
    status: satisfied
---

# Phase 22: round(price, N) Epidemic Kill Verification Report

**Phase Goal:** Kill remaining price-domain fixed-precision rounding (11 price sites across 6 files), grow the AST guard (SCANNED_FILES 6→12, markers 16→72 per plan pins), land an ADA-scale SL/TP regression test (RED→GREEN), rebuild + docker-exec deployment proof.
**Verified:** 2026-08-27T17:33:20Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (source) | Status | Evidence |
|---|---|---|---|
| 1 | A `SimpleRSIStrategy` signal on a sub-$1 (ADA-scale) asset returns `stop_loss`/`take_profit` at full float precision, exactly equal to the unrounded computation (22-01) | VERIFIED | `cd services/trading-engine && python3 -m pytest tests/test_sub_dollar_price_safety.py --no-cov -q` → 4 passed. Read the test file in full: two-sided exact-equality + non-quantization assertions on BUY/SELL, no `pytest.approx` (grep = 0), no `capital=` literal in the `generate_signal(` call. |
| 2 | The three trading-engine residue files are enrolled in the AST guard and the guard is green (22-01) | VERIFIED | `SCANNED_FILES` includes `simple_rsi_strategy.py`, `post_trade_analysis.py`, `adaptive_rsi.py`; `find_violations([]`) for all three confirmed live via Python one-liner against on-disk source. |
| 3 | No `round(..., 2)`/`round(..., 4)` survives unclassified in the three enrolled trading-engine files (22-01) | VERIFIED | `python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q` → 16 passed, 0 violations across all 12 `SCANNED_FILES` (not just the 3). |
| 4 | `/indicators/sqzmom` payload serves price-unit momentum at full float precision (22-02) | VERIFIED | Live call: `curl http://localhost:8004/api/v1/indicators/sqzmom/ADAUSDT` → `momentum.value = 0.0037248928571428554`, `!= round(v,4)` (0.0037). On-disk: `handlers/sqzmom.py` `float(latest["sqz_momentum"])` at :114, plus `avg_momentum`/`max_momentum`/`min_momentum` all confirmed `float(...)` (grep, 3 lines); `squeeze_momentum.py` `"momentum": float(momentum)` at :545. |
| 5 | The sqzmom backtest serializes `entry_price`/`exit_price` at full precision — the literal `round(price, 2)` ADA-killer class is gone from the repo (22-02) | VERIFIED | `grep -n "float(self.entry_price)"` / `"float(self.exit_price)"` in `sqzmom_backtest.py` each return exactly 1 line (:125, :127); the conditional `if self.exit_price else None` preserved. |
| 6 | All six Phase 22 residue files are enrolled in the AST guard and the guard's docstring no longer names a covered file as uncovered (22-02) | VERIFIED | `len(SCANNED_FILES) == 12` confirmed live. Docstring rot-claims all absent: `"roughly 17"` → 0, `"Four such sites"` → 0, `"121-122"` → 0. Every one of the 12 `SCANNED_FILES` paths appears **exactly once** in the docstring text (the enrollment line only — no stale "uncovered" mention) via direct `text.count()` per path. Remaining-uncovered figure independently re-derived by scan: 14 across 7 indicator files, matches the docstring's stated number. |
| 7 | The `float()` change is present in the RUNNING trading-engine and technical-analysis images, not only on disk (22-02) | VERIFIED | Ran all 8 `docker exec` proof commands myself against live `crypto-bot-trading`/`crypto-bot-ta` containers (both `Up 12 minutes, healthy` at verification time — post-rebuild): `stop_loss=float(stop_loss)`→1, `take_profit=float(take_profit)`→1, `atr_value: float(`→1, `price_improvement: float(`→1, old-token absence for sqzmom momentum→0, new-token presence→1, `momentum: float(`→1, `backtesting/sqzmom_backtest.py` absent from image (`test -f` exit 1, correctly out of `COPY app/` scope). `GET :8004/health` and `:8005/health` both 200. |

**Score:** 7/7 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `services/trading-engine/tests/test_sub_dollar_price_safety.py` | ADA-scale SL/TP precision regression | VERIFIED | Exists, 4 substantive tests, imports `SimpleRSIStrategy` directly, wired via `generate_signal` call, passes at HEAD |
| `services/trading-engine/app/strategies/simple_rsi_strategy.py` | `stop_loss=float(` / `take_profit=float(` on live path | VERIFIED | Both conversions present at :219-220, each grep to exactly 1 line |
| `tests/test_price_rounding_invariant.py` | AST guard covering 12 files, docstring accurate | VERIFIED | `SCANNED_FILES` len 12, 0 violations, 72 total markers, rot-claims absent |
| `services/technical-analysis/backtesting/sqzmom_backtest.py` | full-precision trade serialization | VERIFIED | `float(self.entry_price)` / `float(self.exit_price)` present, `duration_hours` (1dp, out of `BANNED_NDIGITS`) untouched |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `tests/test_price_rounding_invariant.py` | `simple_rsi_strategy.py` | `SCANNED_FILES` tuple membership | WIRED | Confirmed via live import + membership check |
| `services/trading-engine/tests/test_sub_dollar_price_safety.py` | `simple_rsi_strategy.py` | direct import + `generate_signal` call | WIRED | `from app.strategies.simple_rsi_strategy import SimpleRSISignal, SimpleRSIStrategy`; test calls `strategy.generate_signal(indicators, ADA_PRICE)` — a real contract check, not a mock |
| `tests/test_price_rounding_invariant.py` | `services/technical-analysis/app/handlers/sqzmom.py` | `SCANNED_FILES` tuple membership | WIRED | Confirmed |
| `running crypto-bot-ta container` | `services/technical-analysis/app/handlers/sqzmom.py` | docker exec grep of rebuilt image layer | WIRED | Independently re-run by verifier against the live container, not inherited from SUMMARY |

### Numeric Pins (goal-critical — independently re-derived, not read from SUMMARY)

| Pin | Claimed | Independently verified |
|---|---|---|
| Price sites killed | 11 across 6 files | `simple_rsi_strategy.py` (2) + `handlers/sqzmom.py` (4: `value`,`avg_momentum`,`max_momentum`,`min_momentum`) + `squeeze_momentum.py` (1) + `sqzmom_backtest.py` (2) + `adaptive_rsi.py` (1) + `post_trade_analysis.py` (1) = **11**, confirmed by direct grep on each site |
| `SCANNED_FILES` growth | 6 → 12 | Pre-phase-22 tuple extracted from commit `8168ae4` = 6; current = 12 |
| Marker growth | 16 → 72 | Pre-phase-22 marker sum over the 6 pre-existing files = 16; current sum over all 12 = 72 |
| RED before GREEN | `1497bf0` precedes `e2df864` | `git log --oneline` confirms commit order |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Repo-root AST guard suite | `python3 -m pytest tests/test_price_rounding_invariant.py --no-cov -q` | 16 passed | PASS |
| Trading-engine ADA regression + strategies suite | `cd services/trading-engine && python3 -m pytest tests/test_sub_dollar_price_safety.py tests/strategies/ --no-cov -q` | 198 passed | PASS |
| Technical-analysis full suite | `cd services/technical-analysis && python3 -m pytest tests/ --no-cov -q` | 711 passed | PASS (matches SUMMARY's pre/post 711→711 claim exactly) |
| Live sqzmom momentum precision | `curl :8004/api/v1/indicators/sqzmom/ADAUSDT` + two-sided invariant | `0.0037248928571428554 != round(v,4)` | PASS |
| Both service health | `curl :8004/health`, `:8005/health` | both 200 | PASS |
| In-image token presence (8 assertions) | `docker exec` against `crypto-bot-trading`/`crypto-bot-ta` | all 8 match plan pins exactly | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| PRICE-01 | 22-01, 22-02 | Price-domain rounding sites replaced with `float()`/tick-derived precision + regression fixture | SATISFIED | 11/11 sites converted and independently confirmed; regression test green. Deviation from REQUIREMENTS.md's literal wording (multi-strategy $0.20-$0.99 sweep, tick-size match) is a **documented override** in 22-CONTEXT.md's Phase Boundary ("the one live-path site") and the "full-precision equality over tick-match" override — not a gap. |
| PRICE-02 | 22-01, 22-02 | CI gate preventing reintroduction | SATISFIED | AST guard (`tests/test_price_rounding_invariant.py`) grown to 12 files, 0 violations, docstring accurate. Deviation from REQUIREMENTS.md's literal `tests/ci/test_no_price_rounding.py` grep-gate wording is a **documented override** in 22-CONTEXT.md (AST guard is strictly stronger and already precedent) — not a gap. |

### Anti-Patterns Found

None. Scanned all 8 phase-touched files (`test_sub_dollar_price_safety.py`, `simple_rsi_strategy.py`, `post_trade_analysis.py`, `adaptive_rsi.py`, `test_price_rounding_invariant.py`, `handlers/sqzmom.py`, `squeeze_momentum.py`, `sqzmom_backtest.py`) for `TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER` — zero matches.

### Human Verification Required

None. Neither PLAN contains a `<verify><human-check>` block on any task — both use `<automated>` verification exclusively. No Step 8 "always needs human" category applies to this phase: no visual/UI surface was touched, no user-facing flow, no external service integration beyond the already-verified live HTTP endpoints (`/api/v1/indicators/sqzmom/ADAUSDT`, `/health` ×2), which this verifier queried directly rather than trusting SUMMARY's paste. Status is `passed`, consistent with an empty human-verification section per the decision tree.

### Info Notes (non-blocking)

1. **REQUIREMENTS.md wording drift (PRICE-01/02).** REQUIREMENTS.md's literal text ("each strategy," "$0.20–$0.99" sweep, "tick size" match, new `tests/ci/test_no_price_rounding.py` grep gate) does not match what was implemented. Both deviations are explicit, pre-planning overrides recorded in `22-CONTEXT.md` ("Source-artifact overrides in force") and repeated verbatim in both PLAN frontmatters. Not a gap.
2. **REQUIREMENTS.md tracking table still shows PRICE-01/PRICE-02 as `Pending` (lines 192-193) with unchecked `[ ]` boxes**, while `ROADMAP.md:80` already carries `[x] Phase 22 ... (completed 2026-08-27)` with an accurate description. Both SUMMARYs explicitly state "No STATE.md or ROADMAP.md writes were made — the orchestrator owns them," and ROADMAP.md was in fact updated (presumably by the orchestrator) but REQUIREMENTS.md's own checkbox/table was not. This is an administrative bookkeeping lag, not evidence the phase goal was unmet — Step 6 grades requirements on implementation evidence, which is present. Flagging so the orchestrator can reconcile REQUIREMENTS.md's checkboxes in its own pass.
3. **22-02 Task 3's "open position count 4 → 4" deployment-safety criterion** is point-in-time and not re-verifiable post-hoc by this verifier (positions have since changed with live trading). It is a deployment-safety check, not one of the 7 must-have truths, and does not affect status.
4. The known pre-existing `tests/unit/test_signal_cache.py` `time.sleep` flake was not encountered — that file is outside this phase's touched-file set entirely.

### Gaps Summary

None. All 7 merged must-have truths (3 from 22-01 PLAN frontmatter, 4 from 22-02 PLAN frontmatter) independently verified against live code, live test runs, and live running containers — not inherited from SUMMARY.md narrative. All numeric pins the phase goal names explicitly (11 sites / 6 files, SCANNED_FILES 6→12, markers 16→72, RED-before-GREEN commit order, docker-exec deployment proof) were independently re-derived by the verifier rather than trusted from SUMMARY.

---
*Verified: 2026-08-27T17:33:20Z*
*Verifier: Claude (gsd-verifier)*
