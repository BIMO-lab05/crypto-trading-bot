---
phase: 21-ta-aggregator-widening-leakage-net
plan: 09
subsystem: testing (measurement + phase gate)
tags: [ablation, monkeypatch, admission, attribution, docker-rebuild, smoke, determinism, checkpoint]

# Dependency graph
requires:
  - plan: 21-03
    provides: "the +ATR arm's two oppositely-signed effects — the mean_reversion SMA-deviation unlock and the UNUSABLE_LEVEL-on-fetch-failure rejection"
  - plan: 21-05
    provides: "the MTF demote-to-HOLD all-leg gate and the behavioural threshold lock"
  - plan: 21-06
    provides: "the leg source-diversity guard and the five structured rejection causes the ablation groups on"
  - plan: 21-08
    provides: "the .dockerignore *.bak glob whose effect is only observable on rebuild"
provides:
  - "scripts/ablation_ensemble_admission.py — four-arm ablation from one tree via targeted monkeypatching, deterministic, with every patch asserted to have bound"
  - "The measured finding that +ATR's two effects cancel EXACTLY (signals 9->10, admitted 9->9)"
  - "The first deployment of phase 21 into the paper stack — every prior plan's summary said 'NOT in the running stack'"
  - "Live proof that the P21-1 unit trap is closed: BTC/ETH/BNB all carry atr_pct < 1.0 today and would have produced NEGATIVE stops"
  - "DEFER-21-02..05 in deferred-items.md, each with a re-verified file:line"
affects: [phase-22 price precision, any future ensemble-admission change, any plan citing signal_aggregator line numbers]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Four-arm ablation reconstructed from one tree by disabling each new behaviour, when no pre-phase checkout exists to run against"
    - "Assert every monkeypatch bound, behaviourally and not only by identity — a silently-unpatched arm reads as 'no delta', which is the failure mode the measurement exists to avoid"
    - "Reverse-order replay as the determinism check; same-order re-runs reproduce corpus contamination and pass regardless"
    - "Corpus as a factory plus deep-copy per arm, because one arm mutates the payload it is handed"
    - "Measure admission through the real downstream predicate (AutoTrader._ensemble_stops_are_consistent), not at the function under test — generate_signal EMITS an unusable stop rather than rejecting it"
    - "Enumerate every match of a forbidden-vocabulary grep in the document itself, so the criterion is checkable by reading rather than by trusting the regex"

key-files:
  created:
    - services/trading-engine/scripts/ablation_ensemble_admission.py
    - .planning/evidence/21-behavior-change-2026-08-26.md
    - .planning/evidence/21-phase-gate-2026-08-26.md
  modified:
    - .planning/phases/21-ta-aggregator-widening-leakage-net/deferred-items.md

key-decisions:
  - "The baseline arm relaxes `_atr_is_usable` as well as stubbing `_atr_indicator`. Plan 21-03 applied the predicate to `_atr_levels` too, so stubbing only the builder would have left the fetch-failure rejection active in ALL FOUR arms and the +ATR decrease would have measured exactly zero — the wrong answer, reported confidently."
  - "Admission is measured through AutoTrader._ensemble_stops_are_consistent, imported not re-implemented. A measurement stopping at generate_signal misses the ENTIRE +ATR decrease, because generate_signal emits a signal carrying stop_loss=0.0 rather than rejecting it."
  - "Constructed payloads, not scripts/backtest_ensemble.py: it cannot run (no psycopg2, and installs are excluded from Rule 3), it is a P&L replay that would produce exactly the figures the evidence must not contain, and its builder emits neither an MTF-demoted nor an ATR-failure payload."
  - "Corpus extended with `meanrev_alone_needs_atr` at RSI 50 after the first run could not show the +ATR increase at the top line. Every other RSI-route payload sits at RSI <= 30, which fires simple_rsi too, so mean_reversion joining could only change the leg SET — never whether a signal exists."
  - "Build and recreate split into two commands, with --no-deps on the recreate. The combined `up --build --force-recreate` walks the dependency graph, began rebuilding bybit-connector/market-data, and died on the WSL2 credential-helper failure; --no-deps also keeps postgres/timescaledb out of the blast radius of the known suspend bind-mount hazard."
  - "The operator's 'docstring capital literals' follow-up was recorded as CLOSED rather than accepted, because 21-08 already landed it and the grep proves it. Accepting a closed item as open work is how a phantom follow-up outlives the phase."

patterns-established:
  - "Cancellation as a finding: when an arm holds two oppositely-signed effects, report BOTH columns (signals and admitted) — a single net number reports 'no change' for an arm in which two things genuinely changed"
  - "Re-read every file:line before handing it to an operator as a decision item; plan text and prior summaries drift as the file is edited"

requirements-completed: [P21-1, P21-2, P21-3]

# Metrics
duration: ~100 min
completed: 2026-08-27
---

# Phase 21 Plan 09: Four-Arm Admission Ablation, Phase Gate and Operator Sign-Off Summary

**The phase's admission change is measured in four attributed arms from a deterministic committed script — and the +ATR arm's two oppositely-signed effects cancel EXACTLY (signals 9→10, admitted 9→9), which is the measured proof that a single net number would have reported "no change" for an arm in which two things genuinely changed.**

## Performance

- **Duration:** ~100 min (excluding the operator checkpoint wait)
- **Tasks:** 3/3 (Task 3 = the blocking operator gate, now resolved)
- **Files:** 3 created, 1 modified
- **Commits:** 4

## Task Commits

| Task | Commit | What landed |
|---|---|---|
| 1 — Ablation harness + behaviour-change evidence | `7d9ec9f` | `ablation_ensemble_admission.py` (new), `21-behavior-change-2026-08-26.md` (new) |
| 2 — Phase gate record | `c3ccbb6` | `21-phase-gate-2026-08-26.md` (new) |
| 1b — Corpus refinement isolating the +ATR increase | `20fd333` | all three files |
| 3 — Operator decisions recorded | *this commit* | `deferred-items.md`, `21-phase-gate-2026-08-26.md`, `21-09-SUMMARY.md` |

## The measurement

Four arms over 12 constructed payloads, reconstructed from one tree by disabling
each new behaviour individually.

| arm | payloads | signals | admitted | diversity | mtf_demoted | no_directional_legs | prefill_stops | score_below |
|---|---|---|---|---|---|---|---|---|
| `baseline` | 12 | 9 | **9** | 0 | 0 | 2 | 0 | 1 |
| `+ATR` | 12 | **10** | **9** | 0 | 0 | 1 | 1 | 1 |
| `+gates` | 12 | 4 | **4** | 5 | 1 | 2 | 0 | 0 |
| `both` | 12 | 7 | **6** | 3 | 1 | 1 | 1 | 0 |

`admitted + sum(rejections) = 12` for every arm.

### The finding that justifies the whole exercise

**`+ATR` produces one MORE signal than baseline and admits exactly the SAME
number.** The `mean_reversion` SMA-deviation unlock adds one admission
(`meanrev_alone_needs_atr`), the ATR-fetch-failure rejection removes one
(`atr_fetch_failure_multi_leg`), and they cancel. 21-RESEARCH Pitfall 5 predicted
that the two P21-1 effects pull in opposite directions and warned that a plan
verifying P21-1 with "trade count unchanged" would be the failure mode. The trade
count **is** unchanged — and that is now demonstrably the wrong thing to look at,
rather than a reassuring result.

The direction check the operator was asked to perform lands on **two different
columns**: the increase is in `signals`, the decrease in `admitted`. Recorded
explicitly, because an operator checking only `admitted` would see no movement.

### Per-fix attribution

- **+ATR owns both ATR effects**, including the decrease. `atr_fetch_failure_multi_leg`
  is ADMITTED in `baseline` and `+gates`, PREFILL-REJ in `+ATR` and `both` — it
  moves with the ATR arm and is untouched by the gates arm. Filing it under
  +gates would have inverted the measured direction of both arms.
- **+gates owns the MTF suppression and the diversity block**, both single-signed
  decreases, each with a positive control on the identical payload shape
  (`mtf_not_demoted_control`, `multi_indicator_alone`, `rsi_plus_bollinger_route`).
- **The arms are not additive.** `both` admits 6 against `+gates`' 4, because the
  ATR work supplies the second indicator category the diversity guard demands.
- **Order-dependence made visible.** `opposed_legs_below_threshold` is rejected in
  every arm, as `score_below_threshold` without the gates and
  `insufficient_category_diversity` with them. The evaluation did not change; the
  attribution did. This is why only `signals` and `admitted` are cross-arm deltas.

## Phase gate

| Check | Result |
|---|---|
| `services/technical-analysis` `pytest tests/ --no-cov -q` | **711 passed**, exit 0 |
| `services/trading-engine` `pytest tests/ --no-cov -q` | **2122 passed, 795 skipped, 0 failed** |
| repo-root account/price guards | **40 passed** (6+24+10 collected), exit 0 |
| `pytest tests/ -k threshold_lock` | **2 passed**, exit 0 |
| `scripts/check_capital_literals.py` (from repo root) | exit 0 |

**Zero failures, therefore zero new failures.** The progression across the phase
is 2052 → 2091 → 2122 passed, rising monotonically as each plan added tests. The
documented wall-clock flake in `tests/unit/test_signal_cache.py` did not fire on
this run; it remains nondeterministic rather than fixed.

**Rebuild.** Both services rebuilt and force-recreated on
`docker-compose.unified.yml`, with fresh **container and image** IDs
(`da6da7cca30d`→`7bef28c0fcb9`, `c185ca819582`→`80453f914f78`), both healthy.
`docker exec crypto-bot-ta test -e /app/app/main.py.bak` went **exit=0 → exit=1**,
proving 21-08's `.dockerignore` change took rather than a cached layer being
reused. Phase-21 markers and all four locked thresholds were read **from inside
the running container**.

**Smoke** (labelled smoke, not behaviour proof — the funnel has been HOLD since
2026-08-16). All five symbols HTTP 200 with `metadata['atr']` present and stop
distances 1.12%–2.79%. **BTCUSDT (0.5589), ETHUSDT (0.7745) and BNBUSDT (0.5729)
all carry `atr_pct < 1.0` today**, so all three fall in the pre-phase broken
branch and would have produced **negative stop prices** (−9,283 / −1,368 / −102).
Mainnet URL captured (`https://api.bybit.com/v5/...`); CLAUDE.md §7 items 2 and 3
declared N/A **with reasons**.

## Deployment status — CHANGED

**Every prior summary in this phase says "NOT in the running stack". As of this
plan that is no longer true.** The rebuild is the deployment 21-03/21-05/21-06/21-07
each deferred to 21-09. ATR threading, the unit contract, the ATR-fetch-failure
rejection, the MTF all-leg gate, the diversity guard and the per-cause telemetry
are all in force in the paper stack now.

`AUTO_TRADING_ENABLED=true` and the kill switch is absent, so the auto-trader
loop runs against this code — at `PAPER_TRADING_MODE=true` / `Trading Mode: PAPER`,
with three of the four deliberate LIVE steps absent. **Neither the arming state
nor the kill switch was changed by this plan.**

## Operator sign-off — verbatim

> 1. Phase gate evidence: **APPROVED**.
> 2. ATR-fetch-failure mechanism: **RATIFY the deployed full-signal rejection**
>    (fails safe/loud). No fallback variant.
> 3. Regime hard-block (signal_aggregator.py:1256-1280): **FOLLOW-UP item** —
>    record as a named follow-up (defer-items / evidence), do not fix in this
>    phase.
> 4. Residual deferred sites (3 non-CONTEXT mirrors at :135/:235/:356,
>    adx_period survivors in trend_following*.py, regime confidence 0.7,
>    docstring capital literals inventory): **ACCEPT as recorded follow-ups**.

Decision 2 closes the phase's one discretionary mechanism: what 21-03 landed for
`atr.py::_default_response()` is a full-signal *rejection*, while 21-CONTEXT's
P21-1 clause describes a *fallback*. It is now ratified rather than merely
shipped. No code change follows — the running stack already implements it.

Decisions 3 and 4 are recorded as **DEFER-21-02 … DEFER-21-05** in
`deferred-items.md`, each with a re-verified `file:line` and a suggested approach.

**One element of item 4 was recorded as CLOSED rather than accepted as open.**
The "docstring capital literals inventory" was already landed by 21-08:
`grep -n 'capital=10000'` on
`app/trading_enhancements/advanced_position_sizing.py` returns nothing and the
repo-root guard exits 0. Accepting a closed item as open work is how a phantom
follow-up outlives its phase.

## Every operator-facing line number was stale — and is now corrected

This is worth stating loudly, because four separate documents disagreed:

| Item | Cited as | **Actual** |
|---|---|---|
| Regime hard-block | `:1158+` (21-09 plan), `:1206-1258` (21-05 summary), `:1206+` (code comment) | **`:1256-1280`** |
| `std_dev: 2.5` | `:226` (21-09 plan) | **`:235`** |
| RSI `period: int = 9` | `:135` (21-09 plan) | `:135` — correct |
| Trend-filter `limit: 300` | `:324` (21-09 plan) | **`:356`** |

Plan 21-05 edited `signal_aggregator.py` after those citations were written.
Handing an operator a decision list with stale references is a real failure mode:
they cannot verify the item they are approving.

## Decisions Made

1. **Relax `_atr_is_usable` in the ATR-off arms, not just stub `_atr_indicator`.**
   The single highest-leverage decision here. 21-03 applied the shared predicate
   to `_atr_levels` (`:416`) as well, so stubbing only the builder leaves the
   fetch-failure rejection live in every arm and the +ATR decrease measures zero.
2. **Measure admission through `AutoTrader._ensemble_stops_are_consistent`**,
   imported rather than re-implemented. `generate_signal` does not reject an
   `UNUSABLE_LEVEL` stop — it emits a signal carrying `0.0`.
3. **Constructed payloads over `backtest_ensemble.py`.** It cannot run
   (`ModuleNotFoundError: psycopg2`), it is a P&L replay, and its builder emits
   neither an MTF-demoted nor an ATR-failure payload.
4. **`meanrev_alone_needs_atr` added after the first run.** See Deviation 1.
5. **Two-step build/recreate with `--no-deps`.** See Deviation 2.
6. **Weights pinned two ways** — `STATE_PATH` repointed before construction *and*
   `_win_rates` set explicitly — with the live file digested before and after
   regardless, and a non-zero exit if it moves.

## Deviations from Plan

### 1. [Rule 1 — Correctness] The corpus could not show the +ATR increase; one scenario added

- **Found during:** Task 1, reviewing the first four-arm run.
- **Issue:** the first corpus (11 payloads) produced `+ATR` signals = 9, identical
  to baseline. I initially wrote this up as "the unlock's admission value is only
  realised in the presence of the gates" — which is **true of those payloads but
  not structurally true**, and would have handed the operator a direction check
  that read as contradicting 21-03's stated increase. The real cause: every
  RSI-route payload sat at RSI ≤ 30, and `simple_rsi` uses the same 30/70
  thresholds, so it fired on all of them too — `mean_reversion` joining could only
  change the leg *set*, never whether a signal existed.
- **Fix:** added `meanrev_alone_needs_atr` at RSI 50, where `simple_rsi` returns
  `None` and `mean_reversion` must reach `MIN_INDICATORS_ALIGNED = 2` from
  `BB_LOWER` (0.25) + `PRICE_BELOW_SMA` (0.15) = 0.40 — the second of which exists
  only with a usable ATR.
- **Verification:** baseline REJ `no_directional_legs` → +ATR **ADMIT** carried by
  `mean_reversion` alone. Top-line signals 9 → 10, and the exact cancellation
  against the fetch-failure rejection became visible.
- **Committed in:** `20fd333`

### 2. [Rule 3 — Blocking] WSL2 credential-helper failure during the rebuild

- **Found during:** Task 2.
- **Issue:** `up -d --build --force-recreate technical-analysis trading-engine`
  walks the dependency graph, began rebuilding `bybit-connector` and
  `market-data`, and died with
  `UtilAcceptVsock:271: accept4 failed 110` / `error listing credentials`.
- **Fix:** the documented bypass — point Docker at an empty config
  (`DOCKER_CONFIG` → `{"auths":{}}`) so no helper is invoked — and split into
  `build` then `up -d --no-deps --force-recreate`. `--no-deps` additionally keeps
  `postgres`/`timescaledb` out of the blast radius of the known suspend
  bind-mount hazard.
- **Verification:** `BUILD_EXIT=0`, both containers recreated and healthy with
  fresh container and image IDs.
- **Committed in:** n/a (operational; recorded in the phase-gate evidence)

### 3. [Rule 1 — Correctness] Stale `file:line` citations in the operator decision list

- **Found during:** Task 2/3 preparation.
- **Issue:** three of the four sites the plan asks the operator to decide on
  carried stale line numbers, and the regime hard-block was cited three different
  ways across the plan, 21-05's summary and a production code comment.
- **Fix:** every reference re-read from source at `20fd333` and corrected in the
  checkpoint report, `deferred-items.md` and this summary, with the stale values
  recorded beside them so the drift is traceable.
- **Committed in:** this commit

### 4. [Tooling] `git status` and the guard-script cwd trap

- **Issue A:** `scripts/check_capital_literals.py` lives at the **repo root**, not
  under `services/trading-engine/scripts/`. Run from the service directory,
  `python3` exits **2** (file not found), which reads as a guard failure. Plan
  21-03's summary shows it invoked from the service directory.
- **Issue B:** the repo-root pytest config suppresses the `-q` summary line, so
  the guard count was confirmed with `--collect-only` rather than asserted from
  the dot count.
- **Fix:** both recorded in `deferred-items.md` and the phase-gate evidence.

---

**Total deviations:** 4 (1 correctness on the measurement itself, 1 blocking,
1 correctness on citations, 1 tooling).
**Impact:** Deviation 1 changed the headline result — without it the plan's own
`must_haves` truth "the admission delta is attributed per fix" would have been
satisfied only in the weak sense, and the operator would have been asked to
confirm a direction the table appeared to contradict. No file outside the plan's
declared set was modified.

## Threat register dispositions

| Threat ID | Disposition | Evidence |
|---|---|---|
| T-21-09-01 (measuring against a dead funnel) | **mitigated** | Ablation runs on constructed payloads; the live pull is labelled smoke throughout; "signals unchanged" is named as the failure mode and then shown to be exactly what the naive read would report |
| T-21-09-02 (attributing the delta to the wrong fix) | **mitigated** | Four arms from one tree; the `UNUSABLE_LEVEL` rejection assigned to +ATR and shown to move with that arm only; every patch asserted to have bound, behaviourally |
| T-21-09-03 (persisted weights masquerading as a code delta) | **mitigated** | `STATE_PATH` repointed before construction, `_win_rates` pinned, live file digested before/after (absent/absent), non-zero exit if it moves; all four arms report 1/3 weights |
| T-21-09-04 (declaring success on an HTTP 200 over stale code) | **mitigated** | Fresh container **and** image IDs; `main.py.bak` exit=0 → exit=1; phase-21 markers and locked thresholds read inside the container; §7 items 2/3 declared N/A with reasons |
| T-21-09-05 (an admission measurement read as an edge claim) | **mitigated** | Explicit non-claim; all 10 vocabulary-grep matches enumerated in the document itself so the criterion is checkable by reading |
| T-21-09-06 (checkpoint altering live trading config) | **mitigated** | `git status --porcelain` empty for both `docker-compose.unified.yml` and `.env`; no flag, cap or kill-switch touched |
| T-21-09-07 (bind-mount hazard mid-gate) | **accepted, did not fire** | `--no-deps` kept postgres/timescaledb out of the recreate; no `exit=127` occurred |
| T-21-SC (package installs) | **n/a** | Zero. `psycopg2` was deliberately **not** installed — the corpus fell back to constructed payloads instead |

## Known Stubs

None. The harness contains no placeholder data path: it drives the real
`MultiStrategyEnsemble` with the real `SimpleRSIStrategy` and
`MeanReversionStrategy` legs, and imports the real pre-fill admission predicate.
Stubbing the legs would have made the ATR unlock unmeasurable, which is the whole
point of the +ATR arm.

## Threat Flags

None. No new network endpoint, auth path, file access pattern, or schema change
at a trust boundary. The one new file is a host-run measurement script that opens
no socket and writes only where `--json` points.

## Issues Encountered

- **The first corpus measured the right thing and answered the wrong question.**
  See Deviation 1. The lesson generalises: an ablation arm can be correctly
  constructed and still be unable to *express* the effect it is meant to isolate,
  if every payload in the corpus is carried by a different leg.
- **`git status` bare is unusable here** (3.2 GB over an NTFS/WSL mount). All
  status checks used explicit pathspecs.

## User Setup Required

None — no external service configuration. Paper mode only; no credentials
touched, no live order possible.

## Next Phase Readiness

- **Phase 21 is complete and deployed.** All three of this plan's requirements
  (P21-1, P21-2, P21-3) are measured, attributed and operator-ratified, and the
  code is running in the paper stack rather than sitting committed-but-unshipped.
- **Four named follow-ups are queued** as DEFER-21-02 … DEFER-21-05, each with a
  verified `file:line`. DEFER-21-02 (the regime hard-block) is the substantive
  one — same defect class as P21-3, and 21-05's suggested shape (write an
  observable structured flag, then gate on it) is recorded with it.
- **Phase 22 (price precision, PRICE-01/02) is unblocked.**
  `simple_rsi_strategy.py:121-122`'s `round(..., 4)` SL/TP rounding was
  deliberately not asserted on by 21-03 and remains Phase 22's.
- **A standing repo hazard worth one cheap task:** the wall-clock flakes in
  `tests/unit/test_signal_cache.py` and `tests/strategies/test_pairs_trading.py`
  have now cost five consecutive plans a diagnostic detour. Both are `time.sleep`
  against a short TTL; freezing the clock would fix both families.
- **No profitability or edge claim is made anywhere in this phase.** Phase 21 was
  correctness-only. Admission moved; whether that is worth anything is a question
  for a DSR/CPCV-gated measurement that was not performed and is not implied.

## Self-Check: PASSED

Files verified present on disk:
- `services/trading-engine/scripts/ablation_ensemble_admission.py` — FOUND
- `.planning/evidence/21-behavior-change-2026-08-26.md` — FOUND
- `.planning/evidence/21-phase-gate-2026-08-26.md` — FOUND
- `.planning/phases/21-ta-aggregator-widening-leakage-net/deferred-items.md` — FOUND
- `.planning/phases/21-ta-aggregator-widening-leakage-net/21-09-SUMMARY.md` — FOUND

Commits verified in `git log`:
- `7d9ec9f` `test(trading-engine)` — FOUND
- `c3ccbb6` `docs(21-09)` — FOUND
- `20fd333` `test(trading-engine)` — FOUND

No deletions in any commit (`git diff --diff-filter=D --name-only 5d108ad..HEAD`
is empty). No untracked strays under `services/trading-engine/scripts/`. Plan-level
`<verification>` re-run: TA 711 passed, engine 2122 passed / 0 failed, repo-root
guards 40 passed, `-k threshold_lock` 2 passed.

**STATE.md and ROADMAP.md deliberately NOT modified** — the orchestrator owns
those writes.

---
*Phase: 21-ta-aggregator-widening-leakage-net*
*Completed: 2026-08-27*
