# Phase 21 — Deferred Items

Out-of-scope discoveries logged during execution. Not fixed here.

---

## DEFER-21-01: `EnhancedSqueezeMomentum.calculate` returns `None` on a duplicate index label

**Found:** 2026-08-27, during plan 21-01 (TA-AGG-04 leakage net).
**Status:** Pre-existing. **Not** introduced by this phase — verified against base `80e6074`.
**Severity:** Silent leg dropout in the live aggregate vote.

### What happens

Any input frame carrying a duplicate index label makes `EnhancedSqueezeMomentum.calculate`
raise internally and return `None`:

- `services/technical-analysis/app/indicators/sqzmom_enhanced.py:~903` —
  `prev_momentum.loc[row.name]` inside the `sqz_color` `apply`
- `services/technical-analysis/app/indicators/sqzmom_enhanced.py:~951` —
  `result_df.loc[:row.name, 'squeeze_on']` inside the confidence closure

A label lookup on a non-unique index returns a Series rather than a scalar; the
surrounding arithmetic then raises `ValueError: truth value of a Series is
ambiguous`, and the broad `except Exception` at the end of `calculate` swallows it
and returns `None`.

### Why it matters

`services/technical-analysis/app/handlers/analysis.py:118` guards
`if sqz_df is not None and not sqz_df.empty`, so the SQZMOM leg simply **vanishes
from the vote** with no error surfaced to the caller — the endpoint returns a
perfectly well-formed response computed from one fewer voter, and
`"sqzmom": null` is the only trace.

This is not theoretical: TimescaleDB kline history in this repo has a documented
record of holes and repairs (see `project_timescale_kline_holes_repair`), so a
duplicate timestamp reaching the indicator is a live possibility.

### Verification performed

```
index unique? False
PRE-FIX (base 80e6074) result is None on duplicate index: True
PRE-FIX on unique index is None: False
```

The post-fix module behaves identically, because the failure at `:~903` fires
before the confidence closure is ever reached.

### Why it was not fixed in 21-01

Outside the executor `SCOPE BOUNDARY` — plan 21-01's task changes did not cause it,
and its blast radius (every `.loc[row.name]` site in the module, plus a decision
about whether `calculate` should raise instead of returning `None` on an
unexpected input shape) is a separate piece of work. Plan 21-01 removed only its
*own* contribution to the pattern (commit `45ca914`, positional indexing).

No test was added: a duplicate-index test fails today, and `.claude/rules/testing.md`
forbids landing a red test or marking one as an expected failure without a tracking
requirement ID. This entry is the tracking record instead.

### Suggested fix when picked up

Index positionally throughout the module (the pattern `45ca914` establishes), or
reject a non-unique index at the top of `calculate` with an explicit error rather
than returning `None`. A silent `None` from a voting indicator is the harder
failure mode to notice.

---

## Operator decisions at the 21-09 checkpoint (2026-08-27)

The items below were presented to the operator at plan 21-09's blocking
checkpoint and **accepted as follow-ups**. They are recorded here rather than
fixed, per the operator's instruction. Verbatim response:

> 1. Phase gate evidence: **APPROVED**.
> 2. ATR-fetch-failure mechanism: **RATIFY the deployed full-signal rejection**
>    (fails safe/loud). No fallback variant.
> 3. Regime hard-block (signal_aggregator.py:1256-1280): **FOLLOW-UP item** —
>    record as a named follow-up (defer-items / evidence), do not fix in this
>    phase.
> 4. Residual deferred sites (3 non-CONTEXT mirrors at :135/:235/:356,
>    adx_period survivors in trend_following*.py, regime confidence 0.7,
>    docstring capital literals inventory): **ACCEPT as recorded follow-ups**.

**Every `file:line` below was re-read from source at 21-09 execution time.** The
plan text and several earlier summaries carry stale citations for these sites —
do not copy them forward without re-checking.

---

## DEFER-21-02: the regime hard-block does not gate `simple_rsi` / `mean_reversion`

**Found:** named by plan 21-05, re-confirmed and located at plan 21-09.
**Status:** OPEN. Operator decision at the 21-09 checkpoint: **follow-up, do not fix in this phase.**
**Location:** `services/trading-engine/app/signal_aggregator.py:1256-1280` — the
block sets `primary_signal.action = SignalAction.HOLD` at `:1280`.
**Severity:** Same defect class as P21-3. Two of three ensemble legs trade past a
system-level HOLD.

**Citation hygiene:** the 21-09 plan text says `:1158+`, plan 21-05's summary says
`:1206-1258`, and the comment inside `multi_strategy_ensemble.generate_signal`
says `:1206+`. **All three are stale.** `:1256-1280` is the location as of
`20fd333`.

### What happens

An ADX-based counter-trend block forces `primary_signal.action = HOLD`. As with
the MTF demotion that plan 21-05 fixed, `simple_rsi` and `mean_reversion` are
dispatched off the indicator dict and **never read `.action`**, so they are not
suppressed by it. Only `multi_indicator` honours it, and only incidentally
(its guard happens to read `aggregator_signal.action != SignalAction.HOLD`).

### Why it was not fixed in phase 21

21-CONTEXT authorises the **MTF** route only (P21-3). Widening the gate to cover
the regime block is a larger admission change than any plan in this phase was
allowed to make, and plan 21-05 pinned the narrowness deliberately:
`test_regime_hard_block_hold_is_not_recorded_as_an_mtf_demotion` drives a
*surviving* directional consensus through consolidation and asserts
`demoted_to_hold is False` while `result.action == HOLD`. A HOLD from the regime
path is therefore provably outside the P21-3 gate — by design, and test-pinned.

### Suggested approach when picked up

Mirror plan 21-05's shape rather than gating on the bare action: have the regime
block write an observable, structured flag (as `demoted_to_hold` /
`consolidated_action` were added for MTF), then key an ensemble gate on that
flag with an identity check and a fail-open container guard. Gating on
`action == HOLD` directly would also suppress a genuinely-HOLD raw consensus and
the per-timeframe requirements gate in `aggregator_core` — four upstream causes
collapsed into one, which is exactly what 21-05 refused to do.

---

## DEFER-21-03: three non-CONTEXT mirror literals in `signal_aggregator.py`

**Found:** plan 21-07 (T-21-07-05 names them as deliberately out of scope).
**Status:** OPEN. Operator decision at the 21-09 checkpoint: **accepted as a recorded follow-up.**
**Severity:** Config-drift class — the same defect P21-7 closed at its own five sites.

| Site | Current line | Literal |
|---|---|---|
| Bollinger std-dev on the outbound request | **`:235`** | `"std_dev": 2.5` |
| RSI period default | **`:135`** | `period: int = 9` |
| Trend-filter kline limit | **`:356`** | `params = {"interval": interval, "limit": 300}` |

**Citation hygiene:** the 21-09 plan text cites `:226` for `std_dev` and `:324`
for the trend-filter limit. Both are stale; `:135` is correct. Verified against
`20fd333`.

These sit outside 21-CONTEXT's P21-7 site list, and plan 21-07's threat register
entry T-21-07-05 exists specifically to prevent silently widening into them. The
resolution pattern is established by P21-7: route each through the engine's own
`Settings`, or read the value from what technical-analysis already returns.

---

## DEFER-21-04: `adx_period` survivors that still send a TA-owned parameter

**Found:** plan 21-07 (recorded in its summary as out-of-scope survivors).
**Status:** OPEN. Operator decision at the 21-09 checkpoint: **accepted as a recorded follow-up.**

- `services/trading-engine/app/strategies/trend_following.py:70, 111, 239`
- `services/trading-engine/app/strategies/trend_following_strategy.py:366, 377, 385, 402, 1551`

`:1551` is the load-bearing one: it still sends `"period": self.adx_period` on
its own ADX request, which technical-analysis already declares in its own
`Settings` (`default_adx_period = 14`). Plan 21-07 removed the equivalent send
from `market_regime.py` and deleted the constructor parameter, so these are the
same defect in files outside its mandate.

**Scope note carried forward from 21-07:** the claim "the engine no longer sends
an ADX period that TA Settings already own" is true for the **P21-7 site list**,
not repo-wide. `trend_following_strategy.py:1551` is the counterexample a
verifier grepping the repo would find.

---

## DEFER-21-05: regime `confidence` is hardcoded 0.7 while TA returns a real one

**Found:** plan 21-07.
**Status:** OPEN. Operator decision at the 21-09 checkpoint: **accepted as a recorded follow-up.**
**Location:** `_fetch_market_regime` in `services/trading-engine/app/handlers/signals.py`.

technical-analysis computes and returns a genuine regime-classification
confidence on the same response
(`adx.py::ADXCalculator._calculate_confidence`, surfaced as the `confidence` key
that `fetch_adx` already reads). The engine ignores it and reports a fixed 0.7.

Adopting TA's value is a **numeric behaviour change** — it feeds
`_calculate_enhanced_signal`'s risk weight — which is why plan 21-07 declined to
make it under a correctness-only mandate. Whoever picks it up should treat it as
a behaviour change needing its own before/after measurement, not as a cleanup.

---

## CLOSED, not deferred: the docstring capital-literal inventory

The operator's item 4 listed "docstring capital literals inventory" among the
residual sites. **Verified closed at 21-09 execution time — nothing to carry
forward:**

- `advanced_position_sizing`'s usage docstring already resolves capital from
  `Settings.paper_initial_balance`; plan 21-08 landed it. The file is at
  `services/trading-engine/app/trading_enhancements/advanced_position_sizing.py`
  (21-CONTEXT's P21-8 text implies `app/risk/`, which does not exist).
- `grep -n 'capital=10000'` on that file returns nothing.
- `python3 scripts/check_capital_literals.py` **from the repo root** exits 0.

**One trap worth recording, since it cost a diagnostic detour here.** The guard
lives at repo-root `scripts/check_capital_literals.py`, **not** under
`services/trading-engine/scripts/`. Plan 21-03's summary shows it being invoked
from the service directory; run there, `python3` exits **2** (file not found),
which is easy to misread as a guard failure. Run it from the repo root.

Separately, plan 21-08 established that `check_capital_literals.py` **blanks
comments and docstrings by design** (`:219-242`), so its exit-0 is a **non-signal**
for any docstring-literal fix. The docstring closure above is evidenced by the
grep, not by the guard.
