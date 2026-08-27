---
phase: 21-ta-aggregator-widening-leakage-net
plan: 08
subsystem: infra (build-context hygiene) + trading-engine/technical-analysis doc-and-dead-code correctness
tags: [dead-code, dockerignore, build-context, docstring-drift, capital-literal, adx, rsi, sqzmom, information-disclosure]

# Dependency graph
requires:
  - plan: 21-03
    provides: "the synthetic indicators['ATR'] injection (metadata carries atr/atr_pct/atr_fraction and deliberately no 'adx') — the reason the router's ATR-metadata fallback had to be deleted in this phase rather than left as harmless dead code; also the two capital-literal defaults this plan therefore does NOT re-fix"
  - plan: 21-07
    provides: "the current signal_aggregator.py state; confirmed no overlap with the fetch_rsi docstring touched here"
provides:
  - "HybridStrategyRouter.extract_adx has exactly one ADX source — the ADX leg — with the ATR-metadata fallback deleted before 21-03's ATR population could make it reachable"
  - "services/technical-analysis/.dockerignore excludes *.bak"
  - "services/technical-analysis/tests/test_build_context_hygiene.py — a two-assertion guard over the .bak class of build-context leak, with its own vacuity caveat documented in-file"
  - "advanced_position_sizing's usage docstring resolves capital from Settings.paper_initial_balance instead of advertising a literal"
  - "fetch_rsi's docstring states the thresholds the TA service actually applies (80/20, rsi.py:80-81)"
  - "Empirical finding: scripts/check_capital_literals.py blanks comments and docstrings by design (:219-242), so its exit-0 is a NON-SIGNAL for any docstring-literal fix"
affects: [21-09 phase gate (owes the TA image rebuild), phase-22 price precision]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Guard test that states its own vacuity: the .bak assertion is always-green in CI by construction and load-bearing only in the operator working copy — the docstring says so instead of letting a green run be read as proof"
    - "Deleted-identifier notes that do not repeat the identifier, so a doc guard grepping for the removed name stays green"
    - "Build-context exclusion paired with artifact deletion — both halves, with a test pinning each"

key-files:
  created:
    - services/technical-analysis/tests/test_build_context_hygiene.py
  modified:
    - services/trading-engine/app/strategies/hybrid_strategy_router.py
    - services/trading-engine/app/trading_enhancements/advanced_position_sizing.py
    - services/trading-engine/app/signal_aggregator.py
    - services/technical-analysis/app/strategies/squeeze_momentum_strategy.py
    - services/technical-analysis/.dockerignore
  deleted:
    - services/technical-analysis/app/main.py.bak (untracked + gitignored; deleted from the operator working copy, not from git history — see Deviation 1)

key-decisions:
  - "exhaustion_threshold was NOT deleted. The plan flagged it as a possible dead companion to the write-only counter; it is read at five sites in _check_momentum_exhaustion (:455, :459, :468, :478 plus the docstring at :359). Only the counter went."
  - "The .bak deletion targets the MAIN checkout absolute path, because the file is gitignored (.gitignore:185) and therefore never materialises in a linked worktree. Deleting 'it' from the worktree would have been a no-op reported as success."
  - "Two acceptance greps forbid strings that a faithful historical comment would naturally contain ('75/25', 'momentum_exhaustion_count'). Both comments were reworded to record the change WITHOUT repeating the banned token, and each says so in-line — a future reader who wants the old value goes to git history, not to a comment that re-seeds the grep."
  - "The guard's RED evidence was captured against the main checkout, not the worktree, because the worktree can never contain a .bak. Running the guard in-worktree and calling it proof would have been a false pass."
  - "check_capital_literals.py exit-0 is recorded as a NON-SIGNAL, not as evidence. Probed empirically: the pre-fix file passes the guard. Mechanism confirmed at :219-242 — comments and docstrings are tokenized out before scanning, on purpose."

patterns-established:
  - "Vacuity disclosure in guard docstrings: when an assertion is structurally always-green in one environment and load-bearing in another, the test says which is which, so the next reader cannot mistake coverage for protection."
  - "Evidence probing before citing a guard: run the guard against the PRE-fix content in a path it actually scans before claiming it as verification."

requirements-completed: [P21-8]

# Metrics
duration: ~65 min
completed: 2026-08-27
---

# Phase 21 Plan 08: Hygiene Batch Residue Summary

**A dead ADX branch was deleted in the one phase where it was about to stop being dead, a nine-month-old `main.py.bak` that shipped a credentialed CORS wildcard into every locally built image is gone and glob-excluded behind a guard, and two docstrings now state what the code actually does.**

## Performance

- **Duration:** ~65 min
- **Tasks:** 2/2
- **Files:** 1 created, 5 modified, 1 deleted (untracked)
- **Tests added:** 2
- **Behavior change:** none intended, none observed (see Verification)

## Task Commits

| Task | Commit | What landed |
|---|---|---|
| 1 — Engine hygiene | `f780dda` | `hybrid_strategy_router.py`, `advanced_position_sizing.py`, `signal_aggregator.py` |
| 2 — TA hygiene + build-context guard | `ea1c41e` | `squeeze_momentum_strategy.py`, `.dockerignore`, `tests/test_build_context_hygiene.py` (new) |

## What actually changed

### 1. The dead ADX fallback (`hybrid_strategy_router.py`)

Deleted:

```python
        if adx_value is None:
            atr_signal = indicators.get("ATR")
            if atr_signal and getattr(atr_signal, "metadata", None):
                adx_value = atr_signal.metadata.get("adx")
```

**Why it mattered now and not before.** No production writer has ever set an `adx` key on an ATR signal, so the branch has been unreachable-in-effect since 2026-05-06. Plan 21-03 changed the premise: `indicators["ATR"]` is now *populated* with a synthetic `IndicatorSignal` whose metadata carries `atr` / `atr_pct` / `atr_fraction`. The branch's guard (`atr_signal and getattr(atr_signal, "metadata", None)`) would have started evaluating true, and the `.get("adx")` inside it would have started executing — against a key that still does not exist. The observable result would still be `None`, so this is not a bug that would have fired; it is a latent read against a live object that a future ATR metadata addition could silently arm.

The `:99-102` no-default docstring survives verbatim and is extended with a dated note recording the deletion and why an ATR-nested ADX source must not be re-added. The `classify()` history comment (now `:141-148`) is extended rather than rewritten — it was already past-tense and accurate — with one dated line saying the residual branch is now gone, so it reads as history instead of as a description of live code.

### 2. The money docstring (`advanced_position_sizing.py`)

`capital=10000` → `capital=get_settings().paper_initial_balance`, with a comment stating the inversion trap explicitly: the number is *numerically correct* for the $10,000 account since ADR-029 and is a defect anyway, because it bypasses the declared config. `price=50000` is left alone — it is a price, not an account size.

Location routing per `.claude/rules/money.md`: `app/trading_enhancements/**` runs **in-container**, so the example names `Settings.paper_initial_balance` and the comment explicitly forbids `import shared.account`. money.md's literal sentence recommends `ACCOUNT_EQUITY_USD` in docstring examples, but that is the host-run form and the location table wins for a `services/*/app/**` file.

### 3. The stale RSI thresholds (`signal_aggregator.py:143`)

The line claimed a research pair that **no code in either service has ever applied**. The TA service applies 80/20. Verified beyond the plan's citation: there is no `default_rsi_overbought` / `default_rsi_oversold` field in TA's `config.py`, `handlers/indicators.py` never mentions the thresholds, and all three `RSICalculator(...)` construction sites pass `period=` only —

```
app/handlers/analysis.py:51        RSICalculator(period=settings.default_rsi_period)
app/handlers/analysis.py:312       RSICalculator(period=settings.default_rsi_period)
app/services/indicator_service.py:48   RSICalculator(period=period)
```

— so `rsi.py:80-81`'s constructor defaults are the only source, and the endpoint this method calls really does apply 80/20. Without that check the fix would have replaced one stale claim with another, which is T-21-08-04 in a different costume.

### 4. Dead code in `squeeze_momentum_strategy.py`

| Site | Verdict | Action |
|---|---|---|
| `:15` `from app.models import SignalType` | unused in the file; no other module imports `SignalType` *from* this module | deleted |
| `:87` write-only exhaustion counter | one hit in the entire service — the assignment itself | deleted |
| `:88` `exhaustion_threshold` | **NOT dead** — 4 code reads + 1 docstring reference in `_check_momentum_exhaustion` | **kept** |
| `:145` `no_squeeze` local | never read | deleted |

**The `no_squeeze` deletion is provably inert, not merely test-green.** `squeeze_momentum.py:353-360` writes `squeeze_on`, `squeeze_off` and `no_squeeze` unconditionally in the same block, with `no_squeeze` defined as `~squeeze_on & ~squeeze_off`. A DataFrame carrying the first two but not the third cannot be produced by this indicator, and no test in the suite constructs one. The `else: squeeze_state = 'TRANSITIONAL'` branch below already derives exactly that complement.

### 5. The `.bak` — both halves

`app/main.py.bak`, 32,865 bytes, mtime 2025-11-10. Its CORS block was read before deleting:

| | `main.py.bak` | live `app/main.py` |
|---|---|---|
| `allow_origins` | `["*"]` (`:91`) | `["*"]` (`:236`) |
| `allow_credentials` | **`True`** (`:92`) | `False` (`:237`, closed by `e091826`) |

So the threat register's claim (T-21-08-01) is confirmed rather than assumed: the stale file froze the credentialed wildcard and a local `docker build` copied it into the image via `COPY app/`. Runtime-inert — nothing imports a `.bak` — but a shipped layer advertising a hole the running code no longer has is an information-disclosure surface.

`*.bak` added to `.dockerignore` as an exact standalone line, with the pre-existing globs untouched.

## The guard, and the thing it cannot prove

`tests/test_build_context_hygiene.py` asserts (1) no `*.bak` exists under the service, and (2) `.dockerignore` carries the `*.bak` glob as an active line (not merely as substring text inside a comment — asserted against parsed non-comment lines).

**Assertion 1 is vacuous in CI, in a fresh clone, and in this worktree.** Repo-root `.gitignore:185` excludes `*.bak`, so no `.bak` has ever been tracked and none is materialised by a checkout. Its teeth are in the operator's working copy — which is exactly where `docker build` reads from. The module docstring states this at length, including an instruction to delete the whole file rather than half of it if someone later decides the always-green assertion is noise.

Because a green in-worktree run proves nothing about the deletion, RED/GREEN was captured by driving the guard's own `_bak_files()` against the **main checkout**:

```
RED capture — guard applied to the MAIN checkout (operator working copy):
 offenders = ['app/main.py.bak']
 worktree offenders = []

GREEN capture — guard re-applied to the MAIN checkout after deletion:
 offenders = []
```

Independently confirmed: `test -e /mnt/.../services/technical-analysis/app/main.py.bak` → exit 1; `find services/technical-analysis -name '*.bak'` → no output.

**The exclusion is declared, not applied.** `.dockerignore` takes effect only on the next image build. The TA image has NOT been rebuilt — this executor runs in an isolated worktree and touching the shared stack would collide with sibling agents. Plan 21-09's phase gate owes that rebuild. Until then, every already-built layer still contains the file.

## Verification results

| Check | Baseline | After | Verdict |
|---|---|---|---|
| TA `pytest tests/ --no-cov -q` | 709 passed, 0 failed | **711 passed, 0 failed** | PASS (+2 = exactly the new guard) |
| engine `pytest tests/ --no-cov -q` | 2119 passed, 3 failed, 795 skipped (see note) | **2122 passed, 0 failed, 795 skipped** | PASS |
| repo-root `test_account_size_invariant` + `test_account_config_sync` + `test_price_rounding_invariant` | — | **40 passed** | PASS |
| `python3 scripts/check_capital_literals.py` | exit 0 | exit 0 | PASS — **but a non-signal, see below** |
| `requirements.txt` in diff | — | **0 files** | PASS (T-21-SC: zero package installs) |
| `round(` count in `squeeze_momentum_strategy.py` | **2** | **2** | PASS (Phase 22 sites untouched) |

**Arithmetic.** Engine baseline non-skipped total = 2119 + 3 = 2122. After = 2122 + 0 = 2122. This plan added no engine tests, so the totals must match — and they do.

### The 3 baseline engine failures were 1 known flake and 2 self-inflicted measurement artifacts

The baseline run was started in the background and my Task 1 edits landed **while it was still running**. Two of the three failures are a direct consequence:

- `tests/test_sqzmom_leg_enabled.py::test_sqzmom_enhanced_is_in_the_fetch_set`
- `tests/test_sqzmom_leg_enabled.py::test_rsi_divergence_stays_disabled`

Both call `inspect.getsource(SignalAggregator.fetch_all_indicators)`, which re-reads the source file from disk using line offsets frozen in the code object at import time. My docstring edit inserted 9 lines above that method, so `getsource` returned a shifted slice. Isolated re-run immediately after: **3 passed**. Clean full run after all edits: **0 failed**. Not a regression, and not a real baseline failure either — the true pre-plan baseline is **1 failed** (`test_pairs_trading.py::TestRecalibration::test_needs_recalibration_after_period`, the `time.sleep(4)`-against-3.6s wall-clock flake documented in the 21-02/21-03/21-05/21-07 summaries), which also passed on the clean run.

**Lesson worth carrying:** do not run a "baseline" suite concurrently with edits to the files it scans. Source-reading tests (`inspect.getsource`, AST guards) turn that into phantom failures that look like regressions.

### `check_capital_literals.py` exiting 0 proves nothing here — probed, not assumed

The threat register cites this guard as mitigation evidence for T-21-08-03. It is not evidence for a **docstring** fix. Probed empirically by materialising the pre-fix file content at a path the guard actually scans (`services/trading-engine/app/`) and running it:

```
PRE-FIX PROBE exit=0
```

The unfixed file **passed**. Mechanism confirmed at `scripts/check_capital_literals.py:219-242`: the scanner tokenizes the file and blanks `tokenize.COMMENT` and docstring `tokenize.STRING` tokens before matching, deliberately — its own comment says *"Comments and docstrings quote the old value ON PURPOSE"*. The file was also not in `scripts/capital_literals_baseline.txt`, so this is not a suppression.

The real evidence for this fix is the grep (`capital\s*=\s*10000` → no matches; `paper_initial_balance` → 2 hits), and the standing implication is larger than this plan: **`.claude/rules/money.md`'s docstring rule has no automated enforcement.** Recorded under Deferred Issues.

## Acceptance criteria — per-task evidence

### Task 1

| Criterion | Result |
|---|---|
| `grep -n 'atr_signal' hybrid_strategy_router.py` → no match inside `extract_adx` | **PASS**, with a recorded out-of-scope hit: one match remains at `:144`, inside the `classify()` *history comment*. `extract_adx` now spans `:95-131` and contains zero hits. |
| `:99-102` no-default docstring intact; `grep -c 'default'` non-zero | **5** — PASS; the docstring text is unmodified in the diff, extended only |
| `grep -nE 'capital\s*=\s*10000' advanced_position_sizing.py` → none | exit 1 — PASS |
| `grep -c 'paper_initial_balance' advanced_position_sizing.py` ≥ 1 | **2** — PASS |
| `grep -n '75/25' signal_aggregator.py` → none | exit 1 — PASS (required a second edit, see Deviation 2) |
| `grep -n '80/20' signal_aggregator.py` ≥ 1, with `rsi.py` on the same or an adjacent line | `:144` carries `80/20`, `:145` carries `app/indicators/rsi.py:80-81` — PASS |
| `git diff signal_aggregator.py` shows only comment/docstring lines | 1 deletion + 10 insertions, all inside the `fetch_rsi` docstring — PASS |
| repo-root account invariant + config-sync; `check_capital_literals.py` | 30 passed; exit 0 — PASS (the latter recorded as a non-signal) |
| engine `pytest tests/` no new failures vs baseline | 0 failed vs a true baseline of 1 flake — PASS |

### Task 2

| Criterion | Result |
|---|---|
| `test -e services/technical-analysis/app/main.py.bak` non-zero; `find ... -name '*.bak'` empty | exit 1; no output — PASS (checked against the MAIN checkout, the only place it existed) |
| `grep -c '^\*\.bak$' .dockerignore` = 1 | **1** — PASS |
| `grep -c 'tests/standalone/' .dockerignore` = 1 (pre-existing globs survive) | **1** — PASS; the guard additionally pins `logs/` and `**/__pycache__/` |
| `grep -nE '^\s*from app\.models import SignalType'` → none | exit 1 — PASS |
| `grep -c 'momentum_exhaustion_count'` = 0 | **0** — PASS (required a comment reword, see Deviation 3) |
| `grep -c 'no_squeeze ='` = 0 | **0** — PASS |
| `round(` count unchanged | **2 → 2** — PASS |
| `git diff --stat` on the strategy file: small, deletion-only, no reflow/import churn | 9 insertions / 5 deletions, all three deletions plus their replacement comments; no unrelated line moved — PASS |
| Guard file exists with both assertions | 2 tests, 2 passed — PASS |
| TA `pytest tests/ --no-cov -q` exits 0 | **711 passed** — PASS |

## Deviations from Plan

### 1. [Rule 3 — Blocking] The plan's commit-2 pathspec cannot include `main.py.bak`

- **Found during:** Task 2, before committing.
- **Issue:** the `<output>` block specifies `git commit -- ... services/technical-analysis/app/main.py.bak ...`. That path is untracked (`git ls-files` → empty) and gitignored (`.gitignore:185` → `*.bak`), so it has never existed in git and does not exist in a linked worktree at all. The pathspec would have aborted the commit with *"did not match any file(s) known to git"*.
- **Fix:** dropped it from the pathspec. Commit 2 carries the three real paths. The deletion itself was performed with a plain `rm` against the **main-checkout absolute path**, which the orchestrator explicitly authorised for this one operator-working-copy file.
- **Rollback insurance:** the file was copied to the session scratchpad before deletion. Its live counterpart (`app/main.py`) is tracked, so nothing unique was lost.
- **Verification:** `test -e` exit 1; `find` empty; guard RED→GREEN against the main checkout.
- **Committed in:** `ea1c41e`

### 2. [Rule 1 — Self-correction] The historical note re-seeded the banned `75/25` string

- **Found during:** Task 1 acceptance verification.
- **Issue:** my first `fetch_rsi` docstring rewrite recorded the correction faithfully — *"this line previously claimed 75/25"* — which put the exact string the acceptance criterion forbids back into the file. `grep -n '75/25'` returned a hit. The criterion is not pedantry: a doc guard that greps for a stale number cannot distinguish a claim from a confession, and a future reader skimming for "75/25" would find it and re-propagate it.
- **Fix:** reworded to record the correction without repeating the numbers, and said so in-line (*"the stale numbers are deliberately not repeated here — a doc guard greps for them"*) so the omission reads as deliberate rather than as a gap.
- **Verification:** `grep -n '75/25'` → exit 1.
- **Committed in:** `f780dda`

### 3. [Rule 1 — Self-correction] Same failure, second instance: the deleted-attribute name

- **Found during:** Task 2 acceptance verification.
- **Issue:** identical shape. My replacement comment named the removed attribute, so `grep -c 'momentum_exhaustion_count'` returned 1 against a required 0.
- **Fix:** reworded to *"a write-only exhaustion counter used to sit beside this threshold … its name is deliberately not repeated — a doc guard greps for it"*, and stated positively that `exhaustion_threshold` stays because `_check_momentum_exhaustion` reads it at five sites.
- **Verification:** `grep -c 'momentum_exhaustion_count'` → 0.
- **Committed in:** `ea1c41e`

### 4. [Scope discipline — Rule 2 adjacent] `exhaustion_threshold` was investigated and deliberately kept

- **Found during:** Task 2.
- **Issue:** the plan instructed *"its companion `exhaustion_threshold` at `:88` may also be dead; delete it too only if nothing reads it"*. It is read at `:455`, `:459`, `:468`, `:478` and referenced in the `should_exit` docstring at `:359`. Deleting it would have raised `AttributeError` on the first exhaustion check.
- **Fix:** kept, and the replacement comment states why so the next reader does not repeat the investigation.
- **Verification:** `grep -n exhaustion_threshold` → 5 hits; TA suite 711 passed.

### 5. [Tooling] Every source edit applied via Bash + `pathlib`, never the Edit tool

- **Found during:** before the first write, from the 21-02/21-03/21-05/21-07 summaries, which each lost a cycle to this.
- **Issue:** the repo's PostToolUse format hook runs ruff/autoflake at 88 columns against a 100-column codebase. Both files edited here are hostile to it: `squeeze_momentum_strategy.py` carries several >88-column log lines (`:258`, `:314`, `:441`, `:468`, `:478`) and `advanced_position_sizing.py` has column-aligned inline comments throughout its enum and dataclasses. Either would have produced exactly the reflow churn the acceptance criteria forbid, and Task 2's very first edit *removes an import* — precisely the autoflake interaction that bit 21-03.
- **Fix:** every edit applied through `python3` + `pathlib` with `assert count == 1` anchors, including the new test file. Zero reverts were needed.
- **Verification:** `git diff --stat` across the plan — 191 insertions / 11 deletions over six files, of which 142 are the new test file. No reflow anywhere; no import other than the intended one moved.

### 6. [Measurement] The baseline engine run was contaminated by concurrent edits

- **Found during:** reading the background baseline output.
- **Issue:** documented in full under Verification. Two `inspect.getsource`-based tests failed because the source file grew 9 lines mid-run.
- **Fix:** re-ran the file in isolation (3 passed) and re-ran the full engine suite cleanly after all edits (2122 passed, 0 failed). No fix-attempt budget spent on the tests themselves — nothing was wrong with them.

---

**Total deviations:** 6 (1 blocking, 2 self-correction, 1 scope-discipline, 1 tooling, 1 measurement). **Impact:** no scope creep — only the plan's six declared files were touched (the seventh, `main.py.bak`, was deleted). Deviations 2 and 3 are the same latent trap in two places: a faithful historical comment and a grep-based doc guard are in direct tension, and the resolution adopted here (record the change, name the guard, omit the token) is the pattern to reuse.

## Threat register dispositions

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-21-08-01 (`.bak` baked into the image with pre-fix credentialed-wildcard CORS) | **mitigated (declared; applied on rebuild)** | Wildcard+credentials confirmed at `main.py.bak:91-92` vs live `:236-237`. File deleted; `*.bak` glob added; both pinned by the new guard. **Rebuild owed by 21-09** — every existing layer still carries it. |
| T-21-08-02 (dead ADX fallback becoming live once 21-03 populates `indicators["ATR"]`) | **mitigated** | Branch deleted after 21-03 landed; the deletion and the reason are recorded in the surviving docstring |
| T-21-08-03 (account-size literal propagating from a docstring) | **mitigated** | `capital=10000` → `Settings.paper_initial_balance`. **Correction to the register's stated evidence:** `check_capital_literals.py` does not and cannot flag a docstring (`:219-242` blanks them by design; probed pre-fix → exit 0). The grep is the evidence. |
| T-21-08-04 (documentation stating thresholds the code does not apply) | **mitigated** | 80/20 with an `rsi.py:80-81` citation, verified against all three `RSICalculator` construction sites and the absence of any Settings override |
| T-21-08-05 (format hook producing unrelated churn) | **mitigated** | Edit tool never used on source; `git diff --stat` shows no reflow |
| T-21-08-06 (scope leak into Phase 22 rounding sites) | **mitigated** | `round(` count 2 → 2; both sites (`:202` comment, `:209` `# non-price-round` call) untouched; `test_price_rounding_invariant.py` passes |
| T-21-SC (package installs) | **n/a** | Zero installs; no `requirements` file in `git diff --stat` |

## Threat Flags

None. No new network endpoint, auth path, file-access pattern, or schema change at a trust boundary. The one security-relevant change is a *reduction* in shipped surface.

## Known Stubs

None. No hardcoded empty values, placeholder text, or unwired data sources were introduced.

## Corrections to the plan's own line references

Recorded so a verifier reading the diff against the plan does not conclude work is missing.

| Plan claim | Verified reality |
|---|---|
| `squeeze_momentum_strategy.py:203-205` carries price-domain `round(..., 2)` sites belonging to Phase 22 | Those lines are the **comment explaining why price fields are NOT rounded**. The file's only `round(` call is `:209` (`confidence`, dimensionless, carrying the `# non-price-round` allow marker). The Phase 22 rounding work in this file appears to have already landed — nothing here to leave alone beyond the two lines counted. |
| `exhaustion_threshold` "may also be dead" | It is read at five sites. Not dead. |
| Task verify commands are anchored at `/mnt/d/Bimo_max/crypto-trading-bot/services/...` | That is the **main checkout**, not this worktree. All test runs were executed from the worktree paths instead; running the plan's literal commands would have tested unmodified code and reported a false pass. |

## Deployment status — NOT in the running stack

**Committed and unit-verified only. Neither service was rebuilt or `--force-recreate`d.** This executor runs in an isolated worktree; touching the shared stack would collide with sibling agents, and this plan's `<verification>` block is pytest-only by design.

This matters concretely for the `.dockerignore` change, which is *inert until a rebuild*: the stale layer content is unchanged in every existing image. The code changes are comment-only or dead-code deletions, so nothing else is pending.

21-CONTEXT `<specifics>` still owes the before/after signal comparison on BTC/ETH/SOL/BNB/ADA **through the running stack**; CLAUDE.md §7 forbids any end-to-end claim without it. That debt belongs to 21-09.

## Deferred Issues

- **`.claude/rules/money.md`'s docstring rule has no automated enforcement.** `check_capital_literals.py` blanks docstrings on purpose (`:219-242`), so the exact failure mode money.md names — *"a docstring showing `initial_capital=10000.0` is how the wrong number keeps propagating back into new code"* — is invisible to the only guard that exists. Fixing this is not free: the same tokenizer step exists to stop the ~15 fix-provenance comments that legitimately quote the old value from failing the build. A narrower rule (flag a capital literal inside a *code-shaped* docstring line such as `capital=10000`, allow it in prose) would be the shape. Worth a standalone task.
- **`test_pairs_trading.py` / `test_signal_cache.py` wall-clock flakes** — unchanged, out of scope, now cited by five consecutive plans. One task freezing the clock fixes both families.
- **`main.py.bak` was recoverable only from the operator's disk.** It is now gone from the only copy that existed (a scratchpad copy survives for this session only). Nothing unique was in it — its live counterpart is tracked — but the class of artifact is worth noting: gitignored files have no undo.

## User Setup Required

None. No external service configuration, no credentials touched, paper mode only.

## Next Phase Readiness

- **Ready for 21-09**, with one concrete debt handed over: **the technical-analysis image must be rebuilt** for the `*.bak` exclusion to take effect. Until then T-21-08-01 is mitigated in the source tree and unmitigated in every built layer.
- **Zero admission delta expected in the 21-09 ablation.** Every change here is a comment correction, a deletion of code that could not execute, or a build-context exclusion. If the ablation measures a signal-admission change attributable to this plan, that is a finding worth investigating, not noise.
- **No blockers for sibling plans.** Only the plan's declared files were touched. `STATE.md` and `ROADMAP.md` deliberately NOT modified — parallel worktree mode; the orchestrator owns those writes after the wave merges.

## Self-Check: PASSED

Files verified present on disk:
- `services/technical-analysis/tests/test_build_context_hygiene.py` — FOUND (created)
- `services/technical-analysis/.dockerignore` — FOUND
- `services/technical-analysis/app/strategies/squeeze_momentum_strategy.py` — FOUND
- `services/trading-engine/app/strategies/hybrid_strategy_router.py` — FOUND
- `services/trading-engine/app/trading_enhancements/advanced_position_sizing.py` — FOUND
- `services/trading-engine/app/signal_aggregator.py` — FOUND
- `services/technical-analysis/app/main.py.bak` — **ABSENT, as intended** (`test -e` exit 1 against the main checkout)

Commits verified in `git log`: `f780dda`, `ea1c41e`.

Working tree clean; no untracked artifacts left behind (the temporary probe file used to test `check_capital_literals.py` was removed and never staged).

All task `<acceptance_criteria>` re-run and passing; plan-level `<verification>` re-run with both full-suite captures recorded above. Every `file:line` cited in this summary was re-read from source during execution.

---
*Phase: 21-ta-aggregator-widening-leakage-net*
*Completed: 2026-08-27*
