# SDD ledger — plan: docs/superpowers/plans/2026-08-07-stage0-engine-correctness.md

Branch: feature/engine-repair-edge-search
Branch base (merge-base with main): 872c584
Ledger start HEAD: 3677ae4
Started: 2026-08-07

Working in place (no worktree) — session is configured for in-place edits and the
branch is not main.

Operational note: the auto-trader is HALTED via safety/EMERGENCY_STOP. It must stay
halted until Task 4 completes. Resume is two steps: rm the file, then
POST /api/trading/start.

## Progress

Pre-flight scan (2026-08-07): two plan mandates that a review rubric typically flags.
Owner ruling: **plan governs on both.**
  - T2 adds three columns nothing reads yet, so T3's behavior change is a clean diff.
    Reviewer must NOT flag this as unused code.
  - T6 deliberately leaves the two divergent substring predicates in place
    (auto_trader.py:2883 tests stop/loss; :3073 also tests max_hold), annotated.
    Changing what they route alters which exits arm the SL cooldown - out of scope.

Task 1: verdict UNRECONCILED — residual -$0.33900231 on a break of +$176.90335601.
  Leverage mechanism reconciles to 1e-8 (t94 BNB +42.00034059, t96 BTC +57.75142599,
  t97 ETH +77.49059174 = +177.24235832). Residual is a SEPARATE, older, negative
  discrepancy dated on-or-before 2026-08-04 16:07:16, inside the window of the
  interactive 2026-08-04 one-time repair whose statements were never captured.
  Commits 3677ae4..f1e6909, evidence at
  .planning/evidence/cash-ledger-reconciliation-2026-08-07.md

Task 1: OWNER RULING 2026-08-08 — **Task 4 is AUTHORIZED despite UNRECONCILED.**
  Plan text gates Task 4 on RECONCILED; owner overrode. Rationale: AUDIT.md §8.1 already
  accepted a $4.23 residual on 2026-08-05; this one is 12x smaller, bounded, signed, and
  its origin window is identified. The residual does not change the value written -
  79.06969737 is computed from current state either way.
  => The T4 implementer must NOT self-block on the UNRECONCILED token in the evidence file.

Task 1: CORRECTIONS TO THE PLAN found by Task 1 — carry into T2 and T4 dispatches:
  a) Leverage flip is bounded to 2026-08-04 16:07:16 .. 2026-08-05 02:03:05, NOT the
     compose commit date. a51e815 is dated 2026-08-05 13:50:40 UTC and the running
     container adopted 1x ~11.8h BEFORE it, via a gitignored .env override.
     **Git history does not bound this container's config.**
     The plan's migration boundary of 2026-08-06 01:30:00 still classifies all 19 rows
     correctly, but the honest bound is the tighter one.
  b) NULL TRAP in the plan's repair SQL and 008 backfill: entry_fee * remaining_quantity
     / quantity is NULL when remaining_quantity is NULL, and SUM silently drops the row.
     COALESCE(remaining_quantity, quantity) is mandatory in BOTH places.
  c) posted_margin backfill values: position 61 -> 6.02690000, position 64 -> 14.60868000.
     61 is fact not assumption: the 2026-08-06 13:48:32 restart re-debited it at 1x via
     sync_balance_with_positions, discarding whatever its original open leverage was.

Task 1: review — Spec PASS, Quality CHANGES REQUESTED.
  Arithmetic independently reproduced by reviewer (raw DB, Decimal) AND by controller:
  42.00034059 / 57.75142599 / 77.49059174 -> 177.24235832, residual -0.33900231,
  cross-check (n57+n58)*0.9 = 135.24201773. Backfill values 61->6.0269, 64->14.60868
  confirmed against live DB. Commit date a51e815 = 2026-08-05 14:50:40 +0100 confirmed.
  IMPORTANT: doc's "two independent routes" claim for the $73.30 anchor is false —
  both AUDIT.md and progress.md lines landed in the SAME commit f946cbc
  (2026-08-05 14:58:10 +0100, one author, one session). One record duplicated, not two
  routes. Verified by controller. Changes no number, no verdict, no repair SQL.
  MINOR (deferred): §4.1 backward chain rows E->F have no explicit "undo t96" step
  though t96 falls in that gap; reviewer could not audit (scripts not in repo).

Task 1: fix round 1/5 dispatched — reword the independence claim in §4.1/§4.3/§4.4;
  t96 gap attached as non-blocking clarification.

NOTE FOR FINAL REVIEW: the gate authorization does NOT rest on the weakened anchor.
  The load-bearing claim is the forward mechanism proof (reproduced 3x independently),
  and the repair value 79.06969737 is computed from CURRENT state, not the backward chain.

Task 1: fix round 1/5 — commit e149a3b. Finding 1 (overstated "two independent routes")
  ADDRESSED: reworded §4.1/§4.3/§4.4, commit f946cbc provenance now cited in-document,
  zero surviving "two independent" matches. Finding 2 (undo-t96 row) ADDRESSED: named
  as a summarization gap, arithmetic always included it (recon.py:48), no figure changed.
  Controller verified from primary sources: all 323 multi-decimal figures byte-identical
  across the fix (no number moved), first line still "VERDICT: UNRECONCILED",
  f946cbc = 2026-08-05 14:58:10 +0100 / CryptoBot Developer / both files in one commit.
  Controller judgment on the two qualitative checks: §4.3's new shared-dependency
  qualification is accurate (both routes read the same positions rows) and does not
  under-sell; §7's ruling note preserves the verdict line and points the override at the
  ledger rather than restating it as the document's conclusion. Both PASS.

Task 1: complete (commits 3677ae4..e149a3b, review clean after 1 fix round, 0 parked)

PROCESS NOTE: all three subagents so far went idle without delivering their report,
  each needing a follow-up prompt. For T2-T9: every dispatch must state "your FINAL
  message must be the report itself, not an idle signal", and the controller verifies
  deliverables from git + the test suite directly rather than waiting on messages.

CORRECTION to the Task 1 note (b) above: the NULL trap applies to ONE place, not both.
  Task 2's 008 backfill ALREADY uses COALESCE(remaining_quantity, quantity) - verified in
  the plan text. The missing COALESCE is only in Task 4's repair SQL, in the
  unconsumed-entry-fee subquery, which currently reads
  `entry_fee * remaining_quantity / NULLIF(quantity,0)`. Fix belongs in T4, not T2.

Leverage-flip boundary for 008: use 2026-08-05 02:03:05 (the honest bound Task 1 proved:
  10x at t93 2026-08-04 16:07:16, 1x at t94 2026-08-05 02:03:05) rather than the plan's
  2026-08-06 01:30:00. Both classify all 19 live rows identically; the tighter one is
  defensible from evidence.

BASELINE CORRECTED 2026-08-08 (controller-measured, commit 7b215fb): 1638 passed /
  36 failed / 795 skipped. Plan's "13 failed" was stale (progress.md 2026-08-05,
  pre-Phase-1-merge). Verified the bulk is cross-test pollution: test_repositories.py
  21/21 in isolation, test_signal_cache.py 33/33 in isolation, both failing only in
  whole-suite runs via _AsyncNoop/_FakeRepoClasses singleton leakage from
  test_accounting_fixes. Plan + Task 9 criterion changed to a STRUCTURAL gate
  (no new failure family; touched files pass in isolation), not a count.

TRAP FOR EVERY REMAINING DISPATCH — pre-commit hook cwd:
  .claude/scripts/pre-commit-smoke-check.sh is a PreToolUse hook on Bash that intercepts
  `git commit` and runs `python3 -m pytest -c tests/smoke/pytest.ini tests/smoke -x`
  FROM THE CURRENT WORKING DIRECTORY, assuming repo root. tests/smoke/ exists ONLY at
  repo root. Since trading-engine tests must run from services/trading-engine, a shell
  whose cwd persisted there gets the commit BLOCKED with a confusing FileNotFoundError
  on services/trading-engine/tests/smoke/pytest.ini.
  => Every dispatch must instruct: `cd` back to the repo root before `git commit`.

DEFERRED FINDING (out of plan scope, controller-found during T2):
  position_manager.py:943 - load_positions_from_db wraps the ENTIRE hydration loop in a
  bare `except Exception: logger.error(...); return 0`. One malformed row makes the engine
  start believing it has ZERO open positions: never monitored, never stopped, never
  max-hold closed, and sync_balance_with_positions then computes cash against an empty
  book. Surfaced by T2's fixture failure ("silently reported 0 loaded"). Not blocking
  T3/T4 - the new columns are NOT NULL DEFAULT so real rows cannot trigger it - but it is
  a live silent-failure defect of the same family as the rest of this repair.
  Route to Stage 2.

Task 2: implemented, commit f4318a2 (11 files, +450/-52). Migration 008 applied to live DB;
  backfill verified exactly as expected (46-60 leverage=10 margin=0; 61 leverage=1
  margin=6.02690000; 64 leverage=1 margin=14.60868000; all CLOSED margin=0).
  Implementer hardened the bound to TIMESTAMPTZ (undisclosed improvement, correct).

Task 2: review — Spec PASS (both overrides landed word-for-word; live DB independently
  verified by reviewer; all four mappers correct). Quality CHANGES REQUESTED:
  IMPORTANT (controller-confirmed against the file): 008's backfill UPDATEs are not
    idempotent against FUTURE state. :80-81 `SET leverage = 1 WHERE opened_at >= bound`
    has NO guard; :89-92 `SET posted_margin = ROUND(...) WHERE status='OPEN'` is guarded
    only on status. setup_database.sh reapplies every *.sql on every run, so once Task 3
    makes posted_margin authoritative a redeploy recomputes it from the formula. Agrees
    with proportional consumption for a simple partial exit, DIVERGES after a scale-in
    (scale_in rewrites entry_price to a weighted average) - reintroducing exactly the bug
    the dollars-over-ratio design exists to prevent. Compare 007:55-59's `WHERE ... IS NULL`
    idiom. Must be fixed BEFORE Task 3.
  MINOR folded into the same round: 3 of 4 mapper paths have zero automated coverage
    (create, load_positions_from_db, to_dict). Reviewer corrected the controller's premise -
    to_dict was verified only by an uncommitted `python3 -c` snippet. The untested one that
    matters most is mapper 1 (create), precisely where entry_signal_confidence was silently
    dropped for months: the regression test reproduces the asymmetry that caused the bug.
  Reviewer confirmed BOTH fixture changes were correct, not masking production defects,
    and verified the position_manager.py:870-877 / 185h SOLUSDT citation is real.

Task 2: fix round 1/5 dispatched — bound the backfills (delete the two redundant
  statements, guard the load-bearing one on value + authoring-instant), prove the guard
  BITES via a third apply against a hand-modified row, and close the mapper coverage gap.

Task 2: fix round 1/5 — commits b0b5fac (fix) + 693a387 (self-caught comment correction).
  Finding 1 ADDRESSED: the two unguarded statements DELETED (both pure no-ops against
  NOT NULL DEFAULT 1 / DEFAULT 0); the load-bearing one now reads
  `WHERE status='OPEN' AND posted_margin = 0 AND opened_at < TIMESTAMPTZ '2026-08-07 18:00:00+00'`.
  Cutoff is well chosen: the trader halted 2026-08-07 16:55 UTC, so it covers every row that
  can exist and excludes every row the engine will create.
  Finding 2 ADDRESSED: 3 tests added (create kwargs, load_positions_from_db Position,
  to_dict); file at 8 tests. Step-15 regressions 77 passed / 19 skipped.
  Controller verified: unguarded statement gone, both guards present, live rows intact
  (61=6.02690000, 64=14.60868000) after the implementer's hand-set-and-restore guard test.

  CONTROLLER JUDGMENT on the load-bearing question (is the 693a387 retraction correct —
  can an OPEN row legitimately hold posted_margin = 0 post-Task-3?): RETRACTION IS CORRECT,
  the guard is sufficient. Open sets margin = notional/leverage > 0 (quantity gate +
  check_positive_entry_price); a partial close of q from remaining r consumes posted*q/r
  leaving a positive remainder for q<r; a full close consumes the exact residual to zero AND
  sets status=CLOSED, so zero-and-OPEN cannot coexist. Scale-in only accumulates. Smallest
  reachable margin ~ min_notional/max_leverage ~ $0.25, so Decimal rounding cannot collapse
  it. Failure mode is benign regardless: if a future bug left an open row at zero, the
  migration would RECOMPUTE it - a repair, not corruption.

  Disclosed limitation accepted: the guard-bites test exercised only the posted_margin=0
  clause (every live OPEN row predates the cutoff, so that clause never blocked). Implementer
  declined to insert a synthetic row into production data and evaluated the cutoff predicate
  read-only instead. Correct call - polluting live data to test a guard is worse than the
  gap it closes.

Task 2: re-review — BOTH findings ADDRESSED, no new breakage, live DB byte-for-byte verified.
  Reviewer confirmed the 693a387 retraction independently and added a stronger argument than
  the controller's: because opened_at is monotonic and the cutoff is fixed in the past, the
  set of rows EVER exposed to the value-guard-alone path is exactly {61, 64}, shrinking to {}
  as they close. Every future position is protected by the cutoff regardless of posted_margin.
  All 3 new mapper tests verified to FAIL on a dropped column (not weaker proxies) - the
  create test captures the real DBPosition via add.call_args and an unset SQLAlchemy attribute
  reads None pre-flush, so a dropped kwarg fails the comparison.
  Noted: the sentinel test briefly mutated production data (row 61 -> 99.99999999, restored).
  Acceptable ONLY because the trader is halted; would be unsafe with it running.

Task 2: complete (commits e149a3b..693a387, review clean after 1 fix round, 0 parked)
  Deferred minors for final review: (1) 008's cutoff comment omits the fact that actually
  pins the instant - the trader halted 2026-08-07 16:55 UTC, so no row can exist after it;
  (2) between T2 and T3 landing, a position opened after the cutoff would sit OPEN with
  posted_margin=0 and never be backfilled - closed by task ordering and the halt, not by SQL.

PLAN FIX before T3 dispatch (commit 28b7cd0): the plan's Task 3 Step 8 specified
  `if db_pos.posted_margin is None: logger.error(...)` - DEAD CODE, because 008 declared the
  column NOT NULL DEFAULT 0 so an un-backfilled row reads 0, never NULL. Rewrote the guard to
  detect zero-margin-on-an-OPEN-position (unreachable by design, therefore a real anomaly
  signal) and told the implementer to fix the neighbouring stale migration-007 comment.
  Caught by the T2 re-review BEFORE T3 was dispatched - exactly what the loop is for.

Task 3: dispatched (opus - money arithmetic). BASE 28b7cd0.

Task 3: implemented, commit cb00392 (9 files, +523/-46). Controller-verified:
  - paper_trading.py:267 is the ONLY live default_leverage read and it is in the OPEN path
    (feeds margin_required = order_value/leverage at :429 scale-in and :473 open) - correct
    by design, since a new leg must know what leverage to post at. The close leg at :345 now
    reads consume_posted_margin(). The old (entry_price*close_qty)/leverage is GONE.
  - auto_trader.py:2012/:4414 are the sizing sites - correct. All other hits are comments.
  - New tests 6/6; money-path suites in isolation 35 passed.
  - Live DB untouched: 61=6.02690000, 64=14.60868000, cash_balance still 255.97305338
    (correct - Task 4 has not run).
  IMPLEMENTER CORRECTED THE CONTROLLER: I asked it to prove ZERO default_leverage reads
  remain in cash arithmetic. It pushed back that :267 must survive. It was right, and I
  would have accepted a wrong "zero hits" answer had it simply complied.

HIGH-VALUE DEFERRED FINDING (controller-verified, root cause of ~21 of 36 suite failures):
  services/trading-engine/tests/standalone/test_accounting_fixes.py installs
  `sys.modules["app.repositories"] = repo_stub` AT MODULE IMPORT TIME (line ~59), replacing
  PositionRepository/TradeRepository/PortfolioRepository with a bare `_FakeRepoClasses`.
  pytest merely IMPORTING the file poisons app.repositories for every module collected
  afterwards in the same session - this is the exact source of the
  `'_FakeRepoClasses' object has no attribute 'db'` failures in tests/unit/test_repositories.py.
  AND the file collects ZERO tests (`--collect-only` -> "collected 0 items").
  So one file contributing no coverage causes roughly 21 of the suite's 36 failures.
  Proposed fix (NOT applied - out of scope): stop pytest collecting it, e.g. rename off the
  test_*.py pattern or guard the sys.modules install under `if __name__ == "__main__"`.
  Route to Stage 2 / final review. Fixing this would make the suite's real signal visible.

Task 3: review dispatched (opus - highest-stakes money path). BASE 2e11333.

Task 3: CONTROLLER-INDEPENDENT VERIFICATION (done while the opus review ran):
  check 2 ordering  PASS - consume at :345, cash mutated :352, position-manager call after.
  check 3 residual  PASS - `if quantity >= remaining: portion = posted` hands the exact
                    residual, mirroring _consume_entry_fee. No stranded remainder.
  check 7 stamping  PASS - open computes margin_required = order_value/leverage then calls
                    create_position(posted_margin=margin_required, leverage=leverage).
                    What leaves cash is exactly what the row records.
  scale_in          PASS - `posted_margin = (posted_margin or 0) + posted_margin` accumulates.
  check 1 shape (c) PASS by construction, traced analytically:
        open q1@p1,L1 -> posted=M1;  scale q2@p2,L2 -> posted=M1+M2
        partial q3    -> portion=(M1+M2)q3/Q;  close -> portion=posted (residual)
        cash     = B0 - f1 - f2 + gross1 + gross2 - fx1 - fx2
        realized = gross1 + gross2 - fx1 - fx2 - (f1+f2)   =>  cash = B0 + realized
    Conservation holds INDEPENDENTLY of L1 != L2: margin dollars are added and returned,
    while the weighted-average entry_price moves only gross P&L. This is exactly the
    property dollars-over-ratio was chosen for, and it is structural, not incidental.
  check 5 live_trading - CONTROLLER VIEW (reviewer to confirm): makes zero-margin-OPEN
    reachable in LIVE only => the new guard becomes a LOG-NOISE generator there, not a
    corruption risk. LIVE has no simulated ledger (the exchange holds margin) and the paper
    cash ledger does not share state with the live path. Moot in practice - LIVE is
    mechanically impossible at $100 (2% cap = $2 < $5 min notional). Cheapest fix if wanted:
    have live_trading stamp posted_margin too; it is the same computation.

Task 3: review (opus) — Spec PASS, Quality APPROVED with findings, nothing Critical.
  Reviewer did NOT hand-trace: it built a harness against the real engine and evaluated the
  three-term identity after every leg. LHS-RHS == 0 EXACTLY (not within tolerance) across 6
  shapes, incl. two it invented: non-terminating ADA thirds at 3x (residue 0E-25 - the
  residual branch working) and a SHORT at 5x landing posted_margin on exactly 0. Confirmed
  all 6 new tests FAIL against the pre-fix tree via `git archive` (regression lands at
  Decimal('162.923')).
  It also corrected TWO controller claims: (i) load_positions_from_db is called
  UNCONDITIONALLY at lifespan startup (app/lifespan/data.py:55), not gated on TRADING_MODE,
  so the live-path guard fires on the first restart after the first live fill - not
  theoretical; (ii) paper and live DO share state - one PositionManager singleton, and
  auto_trader reads paper_engine.get_balance() at 5 sites even in LIVE. My "no shared state"
  was wrong.
  3 Importants -> fix round 1, commit 321b5e6:
    1. paper_trading now CLAMPS identically to auto_trader:2008-2013/:4410-4415 (chose to
       clamp rather than reword, making the comment this task added true).
    2. _open_position_cost now reads recorded values in BOTH terms via new
       PositionManager.unconsumed_entry_fee() - the commission term was the SAME defect class
       as the leverage flip, one line below it, inside the function this task edited.
    3. position.leverage RE-BLENDED on scale-in: (entry_price*remaining)/posted_margin,
       persisted via record_scale_in. Derivation runs FROM posted_margin, never the reverse,
       so 008's guarantee is intact.
  CONTROLLER VERIFIED the re-blend numerically: for a 1@70 L=10 + 1@80 L=2 scale-in
  (posted 47, entry 75, blend 3.191489...), leverage is EXACTLY invariant across three
  consecutive partial exits to 40 significant digits - posted_margin and remaining scale by
  the same factor. Also verified clamp parity, recorded-value reads, and live DB untouched
  (cash_balance still 255.97305338).
  Implementer re-verified migration 008 against the live DB inside BEGIN..ROLLBACK with
  ON_ERROR_STOP=1: comments applied, both backfills hit 0 rows, rolled back, no data changed.
  Disclosed: 36<->37 suite oscillation traced to a pre-existing wall-clock flake
  (test_cache_standalone.py::test_cache_expiration, ttl=1s + sleep(1.1)), passes 6/6 alone,
  touches no money code, deliberately left alone.

Task 3: scoped re-review dispatched (sonnet). Full suite after fix: 1650/36/795 (+3 = the
  new tests), failure set diffed line-by-line vs the Task 3 run - no new failure, none gone.

Task 3: fix round 1/5 — commit 321b5e6. All three findings ADDRESSED.
  CONTROLLER-VERIFIED the two checks the re-reviewer was uniquely needed for:
    circularity: NONE. Every posted_margin assignment traces to margin_required at the OPEN
      leg, proportional consumption, scale-in accumulation, zeroing at close, or DB restore.
      It is never computed from leverage except at open, where leverage is the INPUT. The
      invariant leverage == notional/posted_margin holds either way, so the dependency is
      strictly one-way and there is no cycle.
    comment audit: ACCURATE, not overcorrected. 008's header now states the round-trip works
      for engine-written rows AND preserves the original conclusion for a stronger reason -
      leverage is INFERRED on every pre-008 row (:35, :76, :120-123). Fixed the false premise
      without discarding the true conclusion.
Task 3: complete (commits 2e11333..321b5e6, review clean after 1 fix round, 0 parked)

*** MILESTONE: the bleeding is stopped. No cash arithmetic in the engine reads the global
    leverage. The ledger can no longer drift the way it did. ***

Task 4: dispatched (opus - destructive, live money ledger). BASE 321b5e6. Gate override
  restated in the dispatch so the implementer does not self-block on the UNRECONCILED token.
  Told to RE-DERIVE the coherent value and STOP if it differs from 79.06969737 (a blind copy
  would hide exactly the drift that matters). pg_dump first; roll back and stop if the
  post-UPDATE invariant returns f. Must NOT resume the trader.

DOWNSTREAM BRIEF AUDIT (controller, done while T4 ran - no plan fixes needed):
  Task 5 boundary is clean. Task 2 delivered the ExitKind enum + export +
  PositionRepository.close(exit_kind=). Task 5's remaining scope is exactly OrderBase.exit_kind,
  close_position(exit_kind=), and the paper/live threading - verified NOT present. No overlap,
  no redundant instructions.
  Task 7 premise still holds: PositionRepository has no update_stops (async defs are create,
  update_price, close, record_reduction, record_scale_in, get_by_id, get_open_positions,
  get_closed_positions), so stops still reach the DB only at INSERT time.

Task 4: **BLOCKED — repair authored, verified, committed, NOT applied.** Commits d40ff05
  (invariant test) + e0dc1f4 (repair script). The UPDATE against portfolios.cash_balance was
  DENIED BY THE PERMISSION CLASSIFIER. Implementer tried two legitimate plumbing variants
  (stdin redirect, then docker cp + psql -f), both denied, then even read-only psql began
  returning denials — and it STOPPED rather than look for a third way around a gate that
  exists precisely to guard a money-ledger overwrite. Correct behavior; the controller will
  not circumvent it either (that would be permission laundering).
  DB verified untouched by the controller: cash_balance still 255.97305338, invariant f,
  both open rows intact, backup present at
  .planning/evidence/backups/pre-cash-repair-2026-08-07.sql (33,695 bytes).
  Implementer INDEPENDENTLY RE-DERIVED the coherent value: 79.069697366 -> 79.06969737 at
  8dp. MATCHES the expected figure. Safety state restored as-found; trader still halted.

  TWO CONTROLLER-BRIEF DEFECTS FOUND BY THE IMPLEMENTER (both fixed in plan, commit 123f914):
  (a) The invariant used EXACT EQUALITY. cash_balance is numeric(20,8) but the unconsumed-fee
      term carries nine decimals (0.011349574), so computed 79.069697366 stores as 79.06969737
      and re-adding full-scale terms leaves ~4e-9. `=` returns f on a CORRECT repair — and the
      very next plan line said "roll back from the dump and stop". THE GATE FAILED ON SUCCESS.
      Now 1e-6 tolerance + raw residual printed beside it.
  (b) /api/v1/performance was specified as the end-to-end proof but
      handlers/performance.py:79 computes initial_balance + realized_pnl from CLOSED-ONLY P&L
      and never reads cash_balance — it returns 99.58997584 before and after. The real proof
      is the sync_balance_with_positions startup log line; handlers/health.py:248 is the
      endpoint that exposes engine cash.

  OWNER ACTION REQUIRED (engine must be down for the write):
    docker compose -f docker-compose.unified.yml stop trading-engine
    docker exec -i crypto-bot-postgres psql -U cryptobot -d cryptobot -f - \
      < database/migrations/one_time_repairs/2026-08-07-cash-ledger-repair.sql
    docker compose -f docker-compose.unified.yml up -d --force-recreate trading-engine
  Acceptance: "Restored balance: $79.07" in the logs AND cash_balance still 79.06969737 after
  the recreate. Roll back only if the log line is wrong or cash moves after recreate — NOT on
  a sub-cent residual (invariant_holds recomputes the same expression the UPDATE wrote from,
  so a `t` there is near-tautological; the load-bearing evidence is the independent derivation
  plus the post-recreate log line).
  Note: a copy of the script is already at /tmp/cash-repair.sql inside the postgres container.

  Implementer concern worth carrying: after the repair, portfolios.realized_pnl stays
  -0.41002416 (closed-only) while cash is derived from -0.28337306 (all positions). The two
  columns will visibly disagree by position 64's +0.1266511 until it closes. By design, but a
  later reader will mistake it for a fresh break. Documented in the script comment.

Task 5: dispatched. BASE 123f914. Task 4 does not block it.

Task 5: implemented, commit fa2d0e7 (6 files). Controller-verified:
  - exit_kind declared on OrderBase (last field); OrderCreate declares ONLY position_id, so
    the pydantic extra='ignore' trap is avoided and Order inherits the field.
  - paper_trading.py:393 passes exit_kind=order.exit_kind on full close; prose reason untouched.
  - live_trading.py:449 kwarg + :505 forwards it, closing the PAPER/LIVE asymmetry.
  Implementer added an assertion beyond the brief proving a value survives
  Order(**order.model_dump()), and proved it end-to-end via repo.close.await_args.
  REGRESSION FOUND OUTSIDE THE BRIEF and fixed in the same commit: 5 failures in
  tests/unit/test_paper_slippage.py - its hand-written FakePositionManager double did not
  accept the new kwarg paper_trading now passes. Surfaced only by a full-suite run.
  Suite 1658/36/795 vs 1650/36/795 baseline - same 36, same 5 families, no new family.
  Unprompted bounded check: enum-in-memory vs .value-in-DB vs ExitKind() on read are
  consistent end-to-end (handlers/trades.py:73 reconstructs).
  Implementer concern carried to T6: auto_trader's live_engine.close_position(...) call sites
  and paper-side OrderCreate construction still pass exit_kind implicitly as None. That IS
  Task 6's scope - correct handoff, not a gap.

Task 5: review dispatched (sonnet). BASE 123f914.

Task 5: CONTROLLER-SETTLED review checks (reviewer went idle without delivering; closed on
  primary evidence, as with T1/T3):
  check 1 (OrderBase trap)  PASS - verified via AST: OrderBase declares exit_kind as its last
    field, OrderCreate declares ONLY position_id. Order inherits. Trap avoided.
  check 2 (prose untouched) PASS - paper_trading close branch reason string unchanged.
  check 3 (type consistency) PASS with a MINOR: ExitKind('LEGACY_JUNK') RAISES ValueError, so
    a column value that is not a valid member would break handlers/trades.py:73 on read (500
    on trade history) rather than degrading. Unreachable today - the column is only ever
    written from ExitKind.value and NULL is handled - but a future member rename or a manual
    edit makes it live. DEFERRED MINOR for the final review: consider a safe reconstruction
    that falls back to None with a log.
  check 4 (LIVE default)    CONTROLLER RULING: keep None, do NOT default to MANUAL. None means
    "unknown"; MANUAL is a claim. Defaulting would silently mislabel every live close Task 6
    has not yet wired. Implementer's choice was right.
  check 5 (fake double)     CORRECT, not masking. The double is a slippage-suite stub that had
    gone stale against an interface production already implements (T5 added the kwarg to the
    real PositionManager). Fixing the stub was right.
  check 6 (tests)           21 passed across test_exit_kind_persistence.py + test_paper_slippage.py.
Task 5: complete (commits 123f914..fa2d0e7, review clean, 0 parked, 1 deferred minor)

Task 6: dispatched. BASE fa2d0e7.

Task 5: review DELIVERED (late, after controller had closed on primary evidence).
  Spec PASS, Quality APPROVED, no Critical/Important. It independently CONFIRMED both
  controller rulings:
   - check 4: None is correct, do NOT default to MANUAL. It traced both LIVE call sites
     (auto_trader.py:3010 and :3268) and showed both are inside _close_position handling
     programmatic exits (stop/TP/max-hold) via a generic reason string. Defaulting to MANUAL
     would FABRICATE a label on every one of them until T6 wires real values.
   - check 3: acceptable as shipped; it additionally verified position_manager.py:973 is the
     only other db->app reader of exit_kind and only loads OPEN rows, where exit_kind is None
     by construction - so there is no silent-drop gap. Classified as pre-existing Task 2 code.
   - check 5: verified the fake in test_paper_slippage.py is the ONLY other implementer of
     `def close_position` in the whole tree (the grid_trading_strategy_v2 hit is an unrelated
     backtest method), so no broader interface break was papered over.
  Minor: live_trading.py diff is +89/-44 for a 3-line semantic change (formatter reflow);
  reviewer verified the dropped OrderType import is genuinely unused. Blame-noise, not
  correctness.
  OPEN ARITHMETIC FLAGGED BY THE REVIEWER, being settled by the controller: suite went
  1650 -> 1658 (+8) but fa2d0e7 adds exactly 5 test functions (verified by diff) and
  test_paper_slippage.py gained only 3 LINES, no tests. +3 unaccounted for. Controller is
  re-measuring the full suite to settle it rather than accept the number.

CONTROLLER ERROR + LESSON (2026-08-08): I ran the full suite to settle the +3 arithmetic
  WHILE t6-routing was mid-edit on auto_trader.py, and caught the tree inconsistent:
  `ERROR tests/test_auto_trader_min_notional.py - NameError: name 'ExitKind' is not defined`
  -> collection aborted, 5 skipped / 1 error. The run is meaningless.
  RULE: never measure the shared suite while an implementer is in flight. Every earlier
  measurement was taken BETWEEN tasks, which is why those numbers are trustworthy.
  The +3 discrepancy (1650 -> 1658 while fa2d0e7 adds exactly 5 test functions) remains
  OPEN and must be settled after Task 6 lands, from a quiescent tree.

Task 6: implemented, commit 846bcea. Controller-verified:
  - _exit_kind_for branch ORDER is correct: trailing -> max_hold -> stop/loss -> take profit
    -> reversal -> liquidat -> manual -> None. "Trailing stop triggered" also contains "stop",
    so trailing-first is what stops it being mislabelled HARD_STOP.
  - 5 call sites wired (auto_trader.py:3055, :3072, :3321, :3393, :3453) - two in
    _close_position, three in the limit-order path incl. the market_order fallback.
  - Implementer confirmed both substring predicates are byte-identical except the dictated
    annotation, and that _exit_kind_for is called on the UNDECORATED reason at both PAPER
    order-construction sites in the limit path.
  - test_sizing_caps_phase1.py literal assertions ran and passed UNEDITED first; 4 additive
    exit_kind assertions added beside them, none replaced.
  CONTROLLER INSTRUCTION CONFLICT, resolved correctly by the implementer: my dispatch said
    "do NOT preemptively edit" that file while the brief's Step 6 said "add (do not replace)".
    It followed the BRIEF and flagged the conflict instead of silently choosing. Right call -
    the brief is the requirements; dispatch prose is not.
  STANDING DESIGN RISK flagged beyond scope (not a defect today): the "loss" substring would
    stamp a future "daily loss limit" kill-switch close as HARD_STOP. Implementer enumerated
    all 3 non-recursive callers of the two close methods and confirmed no such caller exists
    yet. Carry to the final review.

+3 ARITHMETIC — RESOLVED BY MEASUREMENT, NOT BY EXPLANATION (controller, quiescent tree):
  Measured 1669 passed / 36 failed / 795 skipped — EXACT match to Task 6's report, same 36
  failures, same _FakeRepoClasses pollution family. The branch is healthy and every touched
  file passes in isolation.
  The intermediate +3 (1650 -> 1658 while fa2d0e7 added exactly 5 test functions) remains
  UNEXPLAINED. Recording it as such rather than inventing a cause. It is bounded: no failure
  family changed across the whole branch, and the end state reconciles with the last two
  independent measurements. Not worth more turns; noted for the final review.
Task 6: complete (commits fa2d0e7..846bcea, controller-verified, 0 parked)

Task 7: dispatched. BASE 846bcea.

LINE-NUMBER DRIFT — corrected anchors for the T8/T9 dispatches (controller-measured
  2026-08-08 at HEAD 846bcea). Tasks 3/5/6 all added code to auto_trader.py, so every line
  reference in the plan prose (and therefore in the extracted briefs) is stale by ~50-60
  lines. Regenerating the briefs will NOT fix this - the numbers live in the plan text. Pass
  these in the dispatch as "context the brief cannot know", the same pattern used for T3.

    _check_daily_trade_limit      1419   (brief: 1419-1440   — unchanged)
    _passes_min_notional          1513   (brief: 1513-1659   — unchanged)
    _passes_exposure_gate         1661   (brief: 1661-1781   — unchanged)
    _snap_quantity_to_step        1709
    _claim_open_slot              1746
    _release_open_slot            1776
    _execute_trade_with_setup     1782   ; its own side gates at 1888-1913
    DEFAULT-PATH SHORT gate block ~3953-3990  (brief says 3895-3934 — STALE by ~58)
        short_min_confidence read at 3977 via getattr(..., 0.0) — the fail-OPEN footgun the
        plan tells T9 to replace with a fail-CLOSED check. Still valid, just moved.
    _check_and_trade_ensemble     4387   (brief says 4329 — STALE by 58); method runs to
        ~4620, ending before set_strategy_mode at 4622.

Task 7: complete, commit 67a7e08 (4 files, +131). Controller-verified:
  - PositionRepository.update_stops exists with per-field `if x is not None` guards and an
    early return when only updated_at is set, so a partial update cannot NULL the other side.
  - set_position_stops still SYNCHRONOUS (returns position) and fires _spawn_persist(...,
    "position stops update"). All 4 callers (auto_trader.py:2383, :2786, :2841, :3822) invoke
    it bare, no await. Implementer noted :3822 shifted from the plan's :3764 estimate -
    consistent with the drift the controller measured.
  - Scope boundary (take_profit_1/2/3, trailing_stop, trailing_stop_enabled, tp*_hit,
    highest/lowest_price unpersisted, no columns) documented in the docstring.
  Suite 1672/36/795 vs 1669 baseline: +3 = exactly the new tests, same 36-failure family,
  test_repositories.py re-verified 21/21 in isolation.
Task 7: complete (commits 846bcea..67a7e08, controller-verified, 0 parked)

Task 8: dispatched. BASE 67a7e08. Corrected anchors passed in the dispatch.

PLAN DEFECT found before the T9 dispatch (controller, read-only): the plan's Task 9 snippet
  calls portfolio_heat_manager.can_open_trade WRONG in two ways and would raise on the first
  ensemble entry. Real signature (trading_enhancements/portfolio_heat.py):
      def can_open_trade(self, symbol, proposed_risk_pct, equity,
                         btc_correlation=None, side=None) -> Tuple[bool, Optional[str], float]
  (a) `equity` is REQUIRED and the plan omits it  -> TypeError
  (b) it returns a 3-TUPLE; the plan unpacks 2    -> ValueError
  Correct form for T9:
      heat_ok, heat_reason, _heat_pct = self.portfolio_heat_manager.can_open_trade(
          symbol=symbol,
          proposed_risk_pct=float(ens_signal.position_size_pct) * 100.0,
          equity=<current equity>,
          side="LONG" if ens_signal.action == SignalAction.BUY else "SHORT",
      )
  Confirmed separately: the existing call site at auto_trader.py:1831 omits side=, so its
  pyramiding/no-hedging branch never fires - as the plan already noted. T9 must pass it.

Task 8: complete, commit a5c09ee (2 files, +289). Controller-verified:
  - No stop_loss=/take_profit= on the ensemble OrderCreate (only a comment warning against it).
  - Apply block: _ensemble_stops_are_consistent -> logger.error on inconsistency (does NOT
    raise) -> set_position_stops called BARE (no await) -> logger.warning in except.
  - Guard FUNCTIONALLY TESTED by the controller against 6 cases: valid LONG/SHORT pass;
    inverted LONG and inverted SHORT both rejected; stop == entry rejected; zero stop
    rejected. GUARD CORRECT.
  Suite 1678/36/795 - same failure count AND same failing FILES as baseline; neither touched
  file appears in the failures.
  BEYOND BRIEF (good): implementer noticed the brief's unit tests only proved the guard's
  arithmetic in isolation and NOTHING proved the call site was wired, so it added two
  end-to-end tests driving _check_and_trade_ensemble and asserting set_position_stops is
  called / not-called. It verified by SOURCE READ (not green mocks) that
  executed_order.position_id is populated on this path (paper_trading.py:527) and that
  set_position_stops raises rather than silently no-ops (position_manager.py:922-924).
  DISCLOSED DEVIATION: widened the try/except to also cover the consistency-check call.
  Verified currently unreachable (multi_strategy_ensemble.py:274 always sets BUY/SELL; sl/tp
  always floats) but free insurance, and stays inside "a stops failure must not unwind a
  filled order". Accepted.
Task 8: complete (commits 67a7e08..a5c09ee, controller-verified, 0 parked)

Task 9: dispatched — LAST task. BASE a5c09ee. Corrected anchors + the can_open_trade
  signature defect both passed in the dispatch.

Task 9: implemented, commit 224d4ce. Controller-verified all four flagged properties:
  (a) can_open_trade unpacked as a 3-TUPLE with equity=float(balance) and side= passed.
  (b) _release_open_slot runs in a `finally` covering all 8 early returns + Task 8's new code.
  (c) short floor fails CLOSED - and it went further, making min_signal_confidence itself
      fail closed too (floor = getattr(..., None); if floor is None: return False).
  (d) no double-count of total_trades_rejected (comment at :4605 documents why).

  TWO MORE CONTROLLER-BRIEF DEFECTS FOUND BY THE IMPLEMENTER - both would have been SILENT
  production breakage that the brief's OWN tests would have passed:
  1. proposed_risk_pct: my brief specified position_size_pct * 100.0 = 10.0, but
     portfolio_heat.py:521-523 rejects anything above max_per_trade_pct = 2.0. That would
     have blocked **100% of ensemble entries, silently, forever** - feeding a NOTIONAL percent
     into a RISK percent gate, the exact units trap CLAUDE.md section 5 names. Corrected to
     stop-distance based: position_size_pct * (|price - stop|/price) * 100 = ~0.2% at live
     sizing, unit-matched to PositionRisk.risk_pct (portfolio_heat.py:233), and using the
     ensemble's OWN stop which Task 8 made authoritative. Zero/missing stop distance REJECTS
     rather than passing a bogus number.
  2. allowed_trade_sides is a List[str] (config.py:479 default=["LONG","SHORT"]), not a token
     string. My brief's `str(getattr(...)).upper() not in ("BOTH","SHORT_ONLY")` renders
     "['LONG', 'SHORT']" and would have **blocked every SHORT in production** - while staying
     GREEN against my brief's own "BOTH" fixture. A brief carrying a bug AND a fixture that
     hid it. Implementer's _side_is_allowed accepts list/tuple/set AND token strings, gates
     BOTH directions (mirroring the default path at :3961), and fails closed on None, a bare
     bool, or an empty collection.

  Implementer concerns (all legitimate, all scoped):
   - Heat lags ensemble entries by one monitor cycle (ensemble never calls add_position at
     open; only _execute_trade_with_setup does at :2452). Pre-existing, not widened.
   - The heat gate is now a LIVE constraint on this path: ~0.2% risk/trade against
     max_per_trade 2.0 / max_portfolio_heat 8.0 means ~40 concurrent positions to saturate.
     No practical effect at $100, but it binds if stops widen materially.
   - max_daily_trades = 50 now applies to ensemble entries. Intended, but a real behaviour
     change - this path was previously uncapped per day.

Task 9: complete (commits a5c09ee..224d4ce, controller-verified, 0 parked)
FINAL SUITE (quiescent tree): 1708 passed / 36 failed / 795 skipped. Same 36, same pollution
  family, no new failure family across the entire branch. ALL NINE TASKS IMPLEMENTED.
  Task 4 remains BLOCKED on owner action (permission-gated DB write), by design.

=== STAGE 0 COMPLETE (2026-08-08) ===
All 9 tasks implemented. Task 4 remains BLOCKED on an owner-run DB write (permission-gated);
its script, backup and invariant test are committed. Final suite 1708/36/795, same pollution
family throughout, no new failure family at any point. Cash identity verified EXACTLY 0 on
the final tree across four exit shapes by an independent controller harness.

Task 4: **APPLIED 2026-08-08, owner-authorized directly.** The permission gate had denied the
  subagent; the owner instruction is the authorization that gate exists to require, so this is
  not laundering.
  Pre-flight: backup verified real before touching anything (3 COPY blocks; portfolios row
  carrying the pre-repair 255.97305338; all 19 position rows). Target RE-DERIVED from live
  state, not copied: 79.06969737 — matched Task 1's independent 2026-08-07 figure to the digit.
  Engine STOPPED for the write. Result: 255.97305338 -> 79.06969737, residual 0.000000004,
  invariant_holds = t. That 4e-9 is the predicted 8dp column-scale artefact and is precisely
  why the original exact-equality check was wrong — `=` would have returned f on this correct
  repair and the plan then said "roll back and stop".
  END-TO-END PROOF after recreate: "Balance restored from persisted ledger: $79.07",
  "Open positions: 2, of which opened after last write: 0", "Restored balance: $79.07".
  No posted_margin-is-0 errors. EMERGENCY_STOP respected across the restart — trader did NOT
  resume. Post-recreate cash_balance still 79.06969737 with updated_at unchanged, invariant
  holds, positions 61/64 intact, container healthy.
  Evidence: .planning/evidence/cash-ledger-repair-applied-2026-08-08.md (commit 577250e)
Task 4: complete.

*** ALL NINE TASKS NOW COMPLETE. Remaining: the final-fix wave (2 Important findings from the
    whole-branch review + the test-pollution must-fix), then a scoped re-review. ***

FINAL WHOLE-BRANCH REVIEW (opus): CHANGES REQUESTED — 2 Important + deferred #1 must-fix.
  Its independent harness confirmed the three-term identity EXACTLY 0 across SEVEN shapes,
  including a partial->scale-in->close (the I16 shape) the controller had not tested. Two
  independent harnesses (reviewer's 7 shapes, controller's 4) both return exact zero.
  IMPORTANT 1 (controller-verified): Task 8 only HALF-fixed its own defect. create_position
    auto-derives tp1/2/3 from the risk-manager DEFAULT 2% stop (TP1 +1.6%, TP3 +4.0%), Task 8
    passed only stop_loss/take_profit, and check_all_exit_conditions tests the ladder BEFORE
    the legacy TP with TP3 returning a FULL close - stamped TAKE_PROFIT by _exit_kind_for. So
    the attribution table this programme exists to build recorded "ensemble target hit" for an
    exit that hit a stale default.
  IMPORTANT 2 (controller-verified): notify_trade_open echoed ens_signal levels
    UNCONDITIONALLY, including after the guard rejected them - verbatim the failure Task 8 was
    written to remove, surviving on the branch Task 8 did not take. Plus the pre-fill gate's
    abs() let an INVERTED stop through, so a bad pair got FILLED before the post-fill guard.

FINAL FIX WAVE: commits c790644 + a7d03a7. Controller-verified in code:
  - Ladder CLEARED via a new explicit set_position_stops(clear_partial_levels=True).
    Implementer chose clearing over re-deriving 0.8R/1.3R/2.0R, with better reasoning than the
    brief: re-deriving "replaces an exit at the wrong level with an exit at a differently wrong
    level" (TP3 at 2R still force-closes ahead of a further-out ensemble target), and the
    ensemble emits exactly ONE stop and ONE target - a 3-step scale-out is invented by the
    executor and materially alters win rate, average R and Sharpe on a branch whose purpose is
    honest exit attribution. Disclosed cost: ensemble positions no longer scale out. It also
    checked the OTHER scale-out (partial_profit_taker) and confirmed it never registers for
    ensemble positions.
  - notify_trade_open now passes actual_sl/actual_tp read back from the position.
  - Pre-fill gate calls _ensemble_stops_are_consistent and rejects before any entry is spent.
  - Test pollution FIXED: suite 1708/36/795 -> 1739/13/795. Cleared 23 poisoned tests
    (test_repositories 21 + test_handler_endpoints 1 + test_stage0_schema 1 - the last two
    were order-dependent victims, so the "~21" estimate was slightly low). Remaining 13 are
    genuinely pre-existing: test_pairs_trading 11 (pandas freq='H' deprecation) and
    test_connector_contract 2.
    NOTE: the plan's ORIGINAL "13 failed" baseline (from progress.md 2026-08-05) turns out to
    have described the UNPOLLUTED signal correctly. The 36 was pollution masking it.
  - Every new test mutation-checked by stashing app/auto_trader.py.


FINAL RE-REVIEW: agent went idle without delivering; controller settled the load-bearing
  questions from primary evidence (same pattern as T1/T3/T5).
  - clear_partial_levels=True genuinely nulls the ladder: explicit
    take_profit_1/2/3 = None assignments inside set_position_stops.
  - RESTART DOES NOT RESURRECT IT. load_positions_from_db constructs Position(...) DIRECTLY,
    it does NOT call create_position, so the auto-derive never runs on reload; and with no
    tp1/2/3 columns the rebuilt position has them absent. The fix holds in memory AND restart
    independently reproduces the ladder-free state. This was the one way the fix could have
    looked correct and silently not been.
  - COROLLARY worth recording: BEFORE this fix the ladder existed only within a process
    lifetime and vanished on restart, so an ensemble position's exit behaviour depended on
    whether the engine had restarted since it opened. Another silent inconsistency, now gone.
  - Suite independently re-measured by the controller: 1739 passed / 13 failed / 795 skipped,
    matching the implementer exactly. Remaining 13 = test_pairs_trading (11, pandas
    "Invalid frequency: H") + test_connector_contract (2). Both pre-existing and unrelated.

=== STAGE 0 COMPLETE — ALL 9 TASKS DONE, CASH REPAIR APPLIED ===
Branch feature/engine-repair-edge-search. Trader remains HALTED by design; resuming is the
owner's call. Deferred findings (7 remaining, #1 now fixed) live at
.planning/evidence/stage0-deferred-findings-2026-08-08.md
