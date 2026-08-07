# Review: Task 13 Killtests Diff

**Scope:** test_golden_parity.py, h3_atr_replay.py, test_h3_atr_replay.py, specs document, .gitignore, untracked files (README.md, db-repair-2026-08-06.md)

**Findings:** no findings.

**Verification checklist passed:**

- ✓ KILLTESTS_DATA_DIR env override correctly implemented (uses os.environ.get with fallback)
- ✓ Client factory pattern: saved_client correctly preserved before any modification; restoration in finally block executes immediately after asyncio.run() returns (single-threaded, no window for closed-client access)
- ✓ load_entries_from_series(): NaN/None filtering correct (uses .notna() for ens_action, dual pd.isna() + None checks for size_pct, pd.isna() for confidence)
- ✓ SELL→SHORT mapping: fired filter keeps only non-None rows (BUY/"SELL"/not-None per offline_ensemble.py line behavior: ens.action.value or None); conditional correctly maps "SELL" to "SHORT"
- ✓ Division safety: close validated > 0 at line 152, before quantity calculation at line 164
- ✓ Verdict-id separation: H3-verdict-*.json vs H3-secondary-verdict-*.json glob patterns are disjoint; h4_information.py:181 reads only test_id="H3"
- ✓ No capital literals: quantity formula uses imported PAPER_INITIAL_BALANCE (line 164); test also imports and uses it (test_h3_atr_replay.py line 119)
- ✓ Test coverage: load_entries_from_series tested for filters (BUY/SELL→LONG/SHORT, HOLD dropped), missing size (rejected), non-positive close (rejected), confidence NaN handling

---

**Assessment:** Code is defensive, logically sound, and safe for container deployment. No regressions detected; gate isolation is sound.
