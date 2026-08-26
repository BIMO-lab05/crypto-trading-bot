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
