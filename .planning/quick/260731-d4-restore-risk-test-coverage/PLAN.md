---
id: 260731-d4
slug: restore-risk-test-coverage
date: 2026-07-31
status: in-progress
---

# Restore risk-manager and paper-trading test coverage (audit D-4)

## Why this, and why now

`tests/unit/test_risk_manager.py:15` and `tests/unit/test_paper_trading.py:15`
each carried a module-wide `pytestmark = pytest.mark.skip(...)`, disabling
**47 tests** across the two modules that the project's core value statement
rests on: "every trade goes through enforced risk caps backed by code that
actually runs."

Two things made this the right next move rather than T-1 or T-4:

1. `22285ae` (DL-2) changed `paper_trading.sync_balance_with_positions` — in a
   module whose unit tests were switched off. Shipping accounting changes into
   an untested module is how the original defects got in.
2. **T-2 — the deployed ensemble path enforces no per-trade cap — is the
   largest money risk in the audit.** Changing risk caps with zero risk-manager
   coverage is not defensible. This is the prerequisite for that work.

Zero deployment risk: test-only change.

## What the skip was actually hiding

Removing both markers and running gave **36 passed / 11 failed**. The blanket
skip was disabling 36 working tests to hide 11 broken ones — and none of the 11
was a bug in production code:

| Cause | Count | Detail |
|---|---|---|
| Stale $10,000 scaling | 6 | balances/amounts migrated to $100, expectations left at the $10,000 answers |
| Fixture predates leverage | 4 | `mock_settings` had no `default_leverage`, so `Decimal(str(Mock))` raised `InvalidOperation` |
| Obsolete long-only assertion | 1 | asserted SELL-with-no-position fails; SHORT enforcement (`380a674`) made that wrong |

The clearest example: `test_calculate_position_size_basic` passes
`account_balance=100.00` but asserted `0.02 BTC` — the answer for a $10,000
account. The risk manager returned `0.0002`, correctly. Same story for the
daily-loss tests, which fed a $200 loss to a $100 account (200%) and then
asserted the breaker had *not* fired.

## Changes

- Rescale stale expectations to the $100 account, each with a comment naming
  the migration that stranded it.
- Add `default_leverage` to the `mock_settings` fixture.
- Replace the obsolete long-only test with two that cover current intent:
  a plain SELL opens a SHORT, and a `reduce_only` SELL with no position is
  **rejected** — the property that stops a stop-loss exit flipping into a new
  counter-trade.
- Remove both skip markers, replacing them with a note on what was found.

## Out of scope

Production code. Not one line changed — every failure was in the tests.

## Verification

Baseline 36 failed / 1456 passed / 842 skipped. Expect the same 36 failures,
+47 passed, -47 skipped.
