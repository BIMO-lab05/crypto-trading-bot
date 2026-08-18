# WS1-C / WS2: Research Layer + Edge Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the research layer's cost model and capital assumptions trustworthy, give the kill-funnel an append-only trial ledger so open-ended candidate iteration cannot quietly become p-hacking, and then run edge battery #2 over three pre-registered candidate families.

**Architecture:** Two small repairs to host-run research code, one new `edge_lab` module (the trial ledger) threaded through Gate 2 and the verdict renderers, then three new candidate modules registered against the existing battery. Nothing here touches a running service. The battery itself is network-free by contract: data is fetched beforehand into CSVs, and `run_battery.py` only reads them.

**Tech Stack:** Python 3.12 (host, not container), pandas 3.0.2, numpy 1.26.4, httpx 0.28.1, `Decimal` for money, pytest.

## Global Constraints

- **The account is $100.** Never write a capital literal. Host-run research code imports `from shared.account import ACCOUNT_EQUITY_USD` (or `PAPER_INITIAL_BALANCE`); `backtesting/**` is explicitly permitted to import repo-root `shared/`.
- **Run all tests in this plan from the repo root**, always with `--no-cov`:
  ```bash
  python3 -m pytest tests/edge_lab --no-cov -q
  python3 -m pytest tests/killtests --no-cov -q
  ```
  `tests/edge_lab/conftest.py` puts `backtesting/` on `sys.path`; there is no `__init__.py`, so tests import helpers as `from conftest import ...`.
- **Run the battery from the repo root.** Its CLI defaults (`--data-dir backtesting/data`, `--out .planning/evidence/killtests`) are repo-root-relative.
- **pandas 3.0.2 timestamp trap.** `pd.to_datetime` parses to `datetime64[us]`, so `.astype("int64") // 1e6` yields **seconds**, not milliseconds. Cast to `datetime64[ms]` first. `run_battery.read_kline_csv` exists to defuse exactly this — copy its cast in any new CSV-reading code.
- **`assert_shift_invariant` (`tests/edge_lab/conftest.py:48-80`) is mandatory for every new candidate.** It fails when the check would pass vacuously (commit `cca426c`), so pick cut points that actually close trades, or pass `allow_empty=True` explicitly and justify it.
- **Never re-pin the universe mid-battery.** Battery #2 reuses `backtesting/edge_lab/universe_2026-08-17.json` unchanged. If a new pin is ever needed, generate it with `universe.select_universe` + `write_pin` — never hand-author the JSON.
- **Never mutate `NUM_TRIALS_FLOOR`.** `config.py`'s docstring is explicit: changing a pinned value after verdicts exist invalidates them. The ledger layers *on top* via `run_gate2`'s existing `num_trials_floor` parameter.
- **`costs.py` is stdlib-only and nothing is fetched.** Do not add HTTP or Settings access to it.
- **Do not import trading-engine service code by `sys.path`.** `tests/security/conftest.py` already puts api-gateway's `app` package on `sys.path` in the same pytest session, and a second `app` collides. Spec-load the module instead — the pattern is `tests/test_account_config_sync.py:40-61`.
- **`git status` exceeds 60 seconds on this NTFS/WSL mount.** Never bare `git status`, never `git add -A`. Commit with explicit pathspecs.
- **Kline CSVs are gitignored** (`.gitignore:139` → `data/`); the 30 funding CSVs were force-added in `67656ff`. A fresh clone cannot re-run a battery without re-fetching the 60 kline files via `fetch.ensure_klines`.

---

## File Structure

| File | Responsibility | Tasks |
|---|---|---|
| `backtesting/screen.py` | Gate 1 cost screen. Holds a hand-copied slippage table inside `main()`. | 1 |
| `backtesting/run_phase1_backtest.py` | Research runner; `--capital` argparse default. | 2 |
| `backtesting/edge_lab/trial_ledger.py` | **NEW** — append-only trial record + effective-floor computation. | 3 |
| `backtesting/edge_lab/trial_ledger.json` | **NEW** — the ledger data, seeded retroactively. | 3 |
| `backtesting/edge_lab/gate2.py` | `Gate2Result`; DSR call where `num_trials` enters. | 4 |
| `backtesting/edge_lab/run_battery.py` | Registry, bundle loading, per-variant scoring, verdict writing. | 3, 4, 6, 7, 8 |
| `backtesting/edge_lab/verdicts.py` | Three sites that render the trials floor. | 4 |
| `backtesting/edge_lab/candidates/battery_2026-08-18_manifest.md` | **NEW** — pre-registration, committed before any candidate code. | 5 |
| `backtesting/edge_lab/candidates/pairs_statarb.py` | **NEW** candidate. | 7 |
| `backtesting/edge_lab/candidates/funding_carry.py` | Existing; gains variants. | 6 |
| `backtesting/edge_lab/candidates/lf_trend.py` | Existing; gains regime-gated variants. | 8 |

---

# Part 1 — Trustworthy research inputs (Tasks 1–2)

## Task 1: Pin the screen's slippage table to the paper engine's

`backtesting/screen.py` carries a hand-copied slippage table inside `main()`. Its values currently **agree** with the canonical `DEFAULT_SLIPPAGE_BPS` in `services/trading-engine/app/paper_slippage.py` (5/5/5/10/10, fallback 10) — but nothing enforces that, and the canonical table is explicitly slated for recalibration (its own comments say *"SOLUSDT … calibrate first"*). A calibration update would silently leave every Gate 1 KILL/PASS verdict computed against stale costs.

The table is a local inside `main()`, invisible to any importer, so hoisting it to module scope is a prerequisite for testing it.

**Do not make `screen.py` import `paper_slippage`.** It must stay runnable standalone (`python backtesting/screen.py`) without a `services/` path hack. Agreement is enforced at test time — the same pattern `shared/account.py` uses.

**Files:**
- Modify: `backtesting/screen.py` (hoist to module scope after line ~50; update the two `screen_trades` kwargs)
- Create: `tests/killtests/test_slippage_table_sync.py`

**Interfaces:**
- Produces: `screen.SLIPPAGE_BPS_BY_SYMBOL: dict[str, Decimal]` and `screen.SLIPPAGE_FALLBACK_BPS: Decimal` at module scope.

- [ ] **Step 1: Hoist the table to module scope**

In `backtesting/screen.py`, add after the `MODELLED_FEE_RATE_PER_PAIR` constant:

```python
# Hand-maintained mirror of services/trading-engine/app/paper_slippage.py
# DEFAULT_SLIPPAGE_BPS / FALLBACK_SLIPPAGE_BPS (one-way basis points).
# screen.py must stay runnable standalone, so the values are restated rather
# than imported across the service boundary; agreement is enforced by
# tests/killtests/test_slippage_table_sync.py.
SLIPPAGE_BPS_BY_SYMBOL: dict[str, Decimal] = {
    "BTCUSDT": Decimal("5"),
    "ETHUSDT": Decimal("5"),
    "SOLUSDT": Decimal("5"),
    "BNBUSDT": Decimal("10"),
    "ADAUSDT": Decimal("10"),
}
SLIPPAGE_FALLBACK_BPS: Decimal = Decimal("10")
```

Then delete the local `slippage = {...}` dict in `main()` and change the `screen_trades` call to use `slippage_table=SLIPPAGE_BPS_BY_SYMBOL` and `slippage_fallback=SLIPPAGE_FALLBACK_BPS`.

- [ ] **Step 2: Write the drift guard**

Create `tests/killtests/test_slippage_table_sync.py`:

```python
"""
The research screen's cost model must equal the paper engine's.

screen.py restates the slippage table rather than importing it, so it stays
runnable standalone. Nothing enforced agreement, and paper_slippage.py is
explicitly slated for recalibration ("SOLUSDT ... calibrate first") - a
recalibration would silently leave every Gate 1 verdict on stale costs.

Loading technique: paper_slippage.py is spec-loaded under a unique module
name, NOT via sys.path. tests/security/conftest.py already places
api-gateway's `app` package on sys.path in the same pytest session, and a
second `app` would collide (see tests/test_account_config_sync.py:43-49).
This is safe here because paper_slippage.py imports only logging, decimal
and typing.
"""

import importlib.util
import sys
from pathlib import Path

import screen  # backtesting/ is on sys.path via tests/killtests/conftest.py

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_SLIPPAGE_PATH = (
    REPO_ROOT / "services" / "trading-engine" / "app" / "paper_slippage.py"
)


def _load_paper_slippage():
    name = "_slippage_sync_paper_slippage"
    spec = importlib.util.spec_from_file_location(name, PAPER_SLIPPAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_screen_slippage_table_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_BPS_BY_SYMBOL == paper.DEFAULT_SLIPPAGE_BPS, (
        "the research screen and the paper engine disagree on slippage; every "
        "Gate 1 verdict is computed against the screen's table"
    )


def test_screen_slippage_fallback_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_FALLBACK_BPS == paper.FALLBACK_SLIPPAGE_BPS
```

- [ ] **Step 3: Verify — and prove the guard has teeth**

```bash
python3 -m pytest tests/killtests/test_slippage_table_sync.py tests/killtests/test_screen.py --no-cov -q
```

Expected: all pass. This guard lands **green**, which is correct and matches the `test_account_config_sync.py` convention — a sync test must be green on the commit that introduces it.

Green proves nothing until you have seen it go red: temporarily change `SLIPPAGE_BPS_BY_SYMBOL["SOLUSDT"]` to `Decimal("7")`, re-run, confirm the failure names the mismatch, and revert.

- [ ] **Step 4: Commit**

```bash
git commit -- backtesting/screen.py tests/killtests/test_slippage_table_sync.py -m "test(research): pin the screen's slippage table to the paper engine's

screen.py restated the slippage table inside main(), invisible to any
importer and enforced by nothing. The values agree today, but paper_slippage
is explicitly slated for recalibration - a change there would silently leave
every Gate 1 KILL/PASS verdict computed against stale costs.

Hoisted to module scope and pinned by a drift guard. screen.py deliberately
still does not import across the service boundary: it must stay runnable
standalone, so agreement is enforced at test time, the same pattern
shared/account.py uses. paper_slippage is spec-loaded under a unique module
name because a second `app` package on sys.path would collide with the one
tests/security/conftest.py installs."
```

---

## Task 2: The Phase-1 runner defaults to the real account size

`backtesting/run_phase1_backtest.py:494` sets `--capital` to `default=10000.0`, and `main()` passes `initial_capital=args.capital` explicitly — so the already-corrected `PAPER_INITIAL_BALANCE` default in `backtesting/backtest_engine.py` is bypassed on every default invocation. The runner silently re-answers the $10,000 question the capital audit closed.

**The existing AST invariant cannot catch this**, and adding the file to its `SCANNED_FILES` would be a false guard: `add_argument` is not in `DEFAULT_CARRYING_CALLS`, the flag is the string `"--capital"` rather than an identifier, and `"capital"` alone is not in `CAPITAL_NAMES`. A bespoke test is required.

**Files:**
- Modify: `backtesting/run_phase1_backtest.py` (import after line 17; line 494)
- Create: `tests/test_phase1_runner_capital.py`

- [ ] **Step 1: Write the failing test**

```python
"""
The Phase-1 runner must default --capital to the declared account size.

main() passes initial_capital=args.capital explicitly, so the argparse default
overrides backtest_engine's already-corrected PAPER_INITIAL_BALANCE default on
every default invocation.

tests/test_account_size_invariant.py cannot catch this: add_argument is not in
DEFAULT_CARRYING_CALLS, the flag is the string "--capital" rather than an
identifier, and "capital" alone is not in CAPITAL_NAMES. Adding the file to
SCANNED_FILES would be a false guard, so this scans the source directly.

Importing the module is not viable - the parser is built inside main() and
import pulls pandas plus data_downloader.
"""

import ast
from pathlib import Path

from shared.account import DEFAULTS

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "backtesting" / "run_phase1_backtest.py"


def test_runner_has_no_ten_thousand_literal():
    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and not isinstance(node.value, bool)
        and isinstance(node.value, (int, float))
        and float(node.value) == 10000.0
    ]
    assert not offenders, (
        f"run_phase1_backtest.py lines {offenders}: the account is "
        f"${DEFAULTS['PAPER_INITIAL_BALANCE']:g}. Source --capital from "
        "shared.account.ACCOUNT_EQUITY_USD."
    )


def test_runner_sources_capital_from_shared_account():
    source = RUNNER.read_text(encoding="utf-8")
    assert "from shared.account import ACCOUNT_EQUITY_USD" in source
    assert "default=ACCOUNT_EQUITY_USD" in source
```

- [ ] **Step 2: Run, watch it fail, then fix**

```bash
python3 -m pytest tests/test_phase1_runner_capital.py --no-cov -q
```

Add after line 17 (below the existing `sys.path.insert` that already puts the repo root on the path):

```python
from shared.account import ACCOUNT_EQUITY_USD  # noqa: E402
```

Change line 494:

```python
        "--capital", type=float, default=ACCOUNT_EQUITY_USD, help="Initial capital"
```

**Autoflake has stripped `shared.account` imports before** (`backtesting/backtest_engine.py:36-40` documents the recurrence). The value is genuinely used here so `F401` should not fire, but `git diff` and confirm the import survived before committing.

- [ ] **Step 3: Verify and commit**

```bash
python3 -m pytest tests/test_phase1_runner_capital.py tests/test_account_size_invariant.py --no-cov -q
```

```bash
git commit -- backtesting/run_phase1_backtest.py tests/test_phase1_runner_capital.py -m "fix(research): Phase-1 runner defaults --capital to the real account size

The argparse default was 10000.0 and main() passes initial_capital=args.capital
explicitly, so backtest_engine's already-corrected PAPER_INITIAL_BALANCE
default was bypassed on every default invocation - the runner silently
re-answered the \$10,000 question the capital audit closed.

The AST account invariant is structurally blind to this construct
(add_argument is not a default-carrying call, the flag is a string literal),
so adding the file to SCANNED_FILES would be a false guard. Bespoke
source-scanning test instead."
```

---

# Part 2 — The anti-p-hacking rail (Tasks 3–4)

## Task 3: Append-only trial ledger

> ### State the limit honestly, in the code and in every report
> `gate2.py` computes `num_trials=max(num_trials_floor, n_paths)`, and `n_paths` reaches **45** at the pinned CPCV 10/2 configuration — the H4 verdict records `num_trials_used: 45`. **A ledger count changes nothing until it exceeds 45**, or when a short series yields few variance-valid paths.
>
> The rail is still correct and still worth building: it binds precisely where mining would otherwise be cheapest, and it makes the search space auditable. But "the bar rises every battery" is **false as a literal claim**. Do not write it in a docstring, a verdict doc, or a commit message.

**Files:**
- Create: `backtesting/edge_lab/trial_ledger.py`, `backtesting/edge_lab/trial_ledger.json`
- Create: `tests/edge_lab/test_edge_lab_trial_ledger.py`

**Interfaces (Task 4 consumes these exact names):**
- `ledger_path() -> Path` — default `backtesting/edge_lab/trial_ledger.json`
- `load_entries(path: Path | None = None) -> list[dict]`
- `distinct_variant_count(entries: list[dict]) -> int`
- `append_entries(entries: list[dict], path: Path | None = None) -> None` — read-modify-write, never rewrites or removes existing rows
- `effective_trials_floor(new_variant_count: int, path: Path | None = None, static_floor: int = NUM_TRIALS_FLOOR) -> int`

Entry schema (one dict per variant, per run):

```json
{"candidate": "funding_carry", "variant": "thresh_2x",
 "params": [["threshold_multiple", 2.0]], "date": "2026-08-17",
 "gate1_verdict": "PASS", "gate2_passed": false}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/edge_lab/test_edge_lab_trial_ledger.py` covering:

- `append_entries` preserves prior rows byte-for-byte (append-only) and appends the new ones.
- `distinct_variant_count` counts distinct `(candidate, variant)` pairs, so a re-run of one variant on a later date counts **once**.
- `effective_trials_floor` returns `max(static_floor, distinct_count + new_variant_count)`.
- A missing ledger file yields `[]` and a floor of exactly `static_floor` — never a crash.
- The committed seed contains at least the 8 variants from the 2026-08-17 battery.

- [ ] **Step 2: Implement the module**

```python
"""
Append-only record of every strategy variant ever put through the gates.

Why: the operator chose open-ended iteration - keep running batteries until
something passes. Unbounded candidate mining makes a lucky false positive
inevitable unless the selection bar accounts for every trial ever spent, so
DSR is deflated against the ledger count rather than the current battery's.

WHERE THIS ACTUALLY BINDS - read before quoting it as a guarantee:
gate2 uses num_trials = max(num_trials_floor, n_paths), and n_paths reaches 45
at the pinned CPCV 10/2 config (the H4 verdict records num_trials_used: 45).
A ledger-derived floor therefore changes nothing until it exceeds 45, or when
a short series yields few variance-valid paths. The rail binds where mining is
cheapest, but the bar does NOT rise on every battery. Do not claim it does.

Counting rule: a trial is a distinct (candidate, variant) pair. Re-running the
same variant on a later date is recorded as a second row but counts once - it
is the same hypothesis re-measured, not a new one drawn.
"""
```

Implement the five functions above. `append_entries` must create the file when missing, and must never reorder or drop existing rows. Keep the JSON as a top-level list, `indent=2`, so diffs are reviewable.

- [ ] **Step 3: Seed the ledger retroactively**

Seed with the 8 variants from the 2026-08-17 battery, taking names and params from the committed verdict JSONs (`.planning/evidence/killtests/*-verdict-20260817.json`) rather than retyping them:

| candidate | variants | Gate 1 | Gate 2 |
|---|---|---|---|
| `xs_momentum` | `lookback_7d`, `lookback_30d`, `lookback_90d` | KILL | — |
| `funding_carry` | `thresh_1.5x` (KILL), `thresh_2x` (PASS, ratio 2.603) | mixed | fail |
| `lf_trend` | `dc_20_10`, `dc_55_20` | PASS (4.85 / 15.511) | fail |
| `vol_breakout` | `sqz_default` | KILL (0.917) | — |

Then add the H-series killtests as rows: `H3` (20260805), `H3-secondary` (2 variants, 20260806), `H4` (20260806 and 20260809 — two rows, one distinct variant).

Read each verdict JSON to confirm variant names and params before writing the seed. Do not invent a row.

- [ ] **Step 4: Verify and commit**

```bash
python3 -m pytest tests/edge_lab/test_edge_lab_trial_ledger.py --no-cov -q
```

```bash
git commit -- backtesting/edge_lab/trial_ledger.py backtesting/edge_lab/trial_ledger.json tests/edge_lab/test_edge_lab_trial_ledger.py -m "feat(edge-lab): append-only trial ledger

The operator chose open-ended iteration - keep running batteries until
something passes. Unbounded candidate mining makes a lucky false positive
inevitable unless the selection bar accounts for every trial ever spent, so
DSR must deflate against the cumulative count.

Seeded retroactively with the 8 variants of the 2026-08-17 battery (names and
params read from the committed verdict JSONs) plus the H-series killtests. A
trial is a distinct (candidate, variant) pair; a re-run is recorded but counts
once.

Honest scope: gate2 uses max(floor, n_paths) and n_paths reaches 45 at the
pinned CPCV config, so this binds only above 45 or when a short series yields
few valid paths. It does not raise the bar on every battery, and the module
docstring says so."
```

---

## Task 4: Thread the effective floor through Gate 2 and the verdict renderers

Today `run_battery` never passes `num_trials_floor`, so the config default applies; `Gate2Result` has **no field** recording the trials count actually used; and `verdicts.py` imports `NUM_TRIALS_FLOOR` directly at three render sites. A ledger-derived floor that is not threaded through would make every future verdict doc state `16` while Gate 2 deflated against something else — and those docs claim, in their own text, that every threshold is *"read live from `edge_lab.config`, not transcribed."*

**Files:** `backtesting/edge_lab/gate2.py`, `backtesting/edge_lab/run_battery.py`, `backtesting/edge_lab/verdicts.py`; test `tests/edge_lab/test_edge_lab_trials_threading.py`

**Interfaces:**
- `Gate2Result` gains `num_trials_used: int`.
- `score_gate2(...)` gains a `num_trials_floor: int` parameter.
- `render_verdict`, `render_summary`, `write_verdict_json` gain `num_trials_floor: int = NUM_TRIALS_FLOOR`.
- `TRIALS_CAVEAT` becomes a function `trials_caveat(n: int) -> str`.
- **Add fields, never rename or remove.** The 2026-08-17 verdict JSONs are committed evidence and downstream readers key on their shape.

- [ ] **Step 1: Write the failing tests**

Cover: (a) `run_gate2` with an explicit `num_trials_floor` above the path count records that value in `num_trials_used` — pass a floor `> 45` so it actually binds; (b) DSR is monotonically non-increasing as the floor rises; (c) a rendered verdict `.md` contains the effective floor, not the constant `16`, when they differ; (d) the JSON `thresholds.num_trials_floor` matches the effective floor; (e) every key present in a committed `*-verdict-20260817.json` is still present in a freshly rendered one.

- [ ] **Step 2: Implement the threading**

1. `gate2.py`: add `num_trials_used: int` to `Gate2Result`, and populate it with the same `max(num_trials_floor, int(dist["n_paths"]))` expression the DSR call uses. When `n_paths < 2` and DSR is `nan`, still record the floor that would have applied.
2. `run_battery.py`: before the candidate loop, compute the floor once —
   ```python
   effective_floor = trial_ledger.effective_trials_floor(total_new_variants)
   ```
   where `total_new_variants` is the count of variants this battery will score. Thread it into `score_gate2` → `run_gate2(returns, horizon, num_trials_floor=effective_floor)`, and into the record dict as `num_trials_used`.
3. `verdicts.py`: convert `TRIALS_CAVEAT` to `trials_caveat(n)`, and take the floor as a parameter at the criterion line and in the JSON `thresholds` block.
4. `run_battery.py`: append one ledger entry per variant **after** each candidate's record is assembled, alongside the existing `write_verdict` calls — per candidate, not per battery, so a battery that dies on candidate 3 still ledgers candidates 1–2. Cover **all three** variant states: `NO_TRADES`, Gate-1 `KILL`, and `PASS`. Wrap the ledger write the same way verdict writes are wrapped: a failure is logged and recorded, never fatal to the battery.

- [ ] **Step 3: Verify and commit**

```bash
python3 -m pytest tests/edge_lab --no-cov -q
```

Expected: the full `tests/edge_lab` suite green (74 tests as of `cca426c`, plus the new ones).

```bash
git commit -- backtesting/edge_lab/gate2.py backtesting/edge_lab/run_battery.py backtesting/edge_lab/verdicts.py tests/edge_lab/test_edge_lab_trials_threading.py -m "feat(edge-lab): thread the effective trials floor into Gate 2 and verdicts

run_battery never passed num_trials_floor, Gate2Result had no field recording
the trials count actually used, and verdicts.py imported NUM_TRIALS_FLOOR at
three render sites. A ledger-derived floor that was not threaded through would
have made every future verdict doc state 16 while Gate 2 deflated against
something else - in docs that claim every threshold is read live from
edge_lab.config rather than transcribed.

Gate2Result gains num_trials_used; the renderers take the floor as a
parameter; run_battery computes it once from the ledger and appends one entry
per variant per candidate, covering NO_TRADES, Gate-1 KILL and PASS alike.

NUM_TRIALS_FLOOR stays pinned at 16 as the static lower bound - changing a
pinned value would invalidate existing verdicts. All existing JSON keys are
preserved; fields are added, never renamed."
```

---

# Part 3 — Battery #2 (Tasks 5–9)

## Task 5: Pre-register battery #2 — **commit this before writing any candidate code**

The protocol exists so that candidates cannot be quietly reshaped after seeing results. Pre-registration is not paperwork; it is the thing that makes a later PASS mean anything.

**Files:** create `backtesting/edge_lab/candidates/battery_2026-08-18_manifest.md`

- [ ] **Step 1: Write the manifest**

For each of the three candidate families, state — before any implementation:

1. **Hypothesis**, in one falsifiable sentence.
2. **Economic mechanism** — why should this edge exist, and *who pays it*? A candidate with no answer here is a data-mining expedition and should be cut now rather than after Gate 2.
3. **Variants and their exact parameters**, enumerated. No variant may be added after the run starts.
4. **Bundle inputs** (`daily` / `h4` / `funding`) and the **label horizon** in days.
5. **Prior**, stated honestly, including the 2026-08-17 result that motivates it.

The three families, with the evidence that motivates each:

| Family | Motivation | Prior |
|---|---|---|
| **Funding-carry refinements** | Best survivor of battery #1: `thresh_2x` cleared Gate 1 at ratio 2.603, died at Gate 2 (DSR 5.8e-10, positive-path fraction 0.444). Mechanism is real and identifiable: perpetual funding is a payment from crowded longs to shorts. | Highest |
| **Pairs / stat-arb** | The one classic family no battery has tested. Mechanism: cointegrated pairs mean-revert around a stable hedge ratio. | Medium |
| **Regime-gated trend** | `lf_trend` cleared Gate 1 decisively (ratios 4.85 and 15.511) but failed Gate 2 with pooled PF ≈ 1.0 — its profit was a handful of outliers, not a distribution. The gate tries to turn outliers into a distribution. | **Low — state this plainly.** A filter that merely removes losing periods in-sample is overfitting, and the DSR is designed to catch exactly that. |

Also record: the universe pin (`universe_2026-08-17.json`, unchanged), the data cutoff `--date`, the gate thresholds in force, and the ledger count going in.

- [ ] **Step 2: Commit before writing any candidate code**

```bash
git commit -- backtesting/edge_lab/candidates/battery_2026-08-18_manifest.md -m "docs(edge-lab): pre-register battery #2

Three families with hypothesis, economic mechanism, exact variant parameters,
bundle inputs, label horizons and honestly-stated priors - committed before
any candidate implementation, so nothing can be reshaped after seeing results.

Funding-carry refinements carry the highest prior (best survivor of battery
#1). Pairs/stat-arb is the one classic family never tested here.
Regime-gated trend carries a deliberately low prior: lf_trend's Gate 1 pass
came from a few outliers, and a filter that merely removes losing periods
in-sample is overfitting - which is what the DSR exists to catch."
```

---

## Task 6: Funding-carry refinement variants

**Files:** modify `backtesting/edge_lab/candidates/funding_carry.py` (extend `VARIANTS`); `backtesting/edge_lab/run_battery.py` (`LABEL_HORIZONS` already has `funding_carry: 10`); test `tests/edge_lab/test_edge_lab_funding_carry_variants.py`

- [ ] **Step 1: Read the existing candidate end to end**

```bash
sed -n '1,200p' backtesting/edge_lab/candidates/funding_carry.py
```

Understand how `thresh_2x` selects entries and exits before adding variants. New variants must reuse the existing `generate_trades` and differ **only** by `Variant.params` — if a variant needs different logic, it belongs in a different candidate module.

- [ ] **Step 2: Add exactly the variants named in the manifest**

Append to `VARIANTS`, matching the manifest exactly. Every variant's parameters must be reachable from `variant.params` inside `generate_trades`; extend the parameter handling rather than branching on variant names.

- [ ] **Step 3: Test, including the mandatory look-ahead guard**

The test must call `assert_shift_invariant` from `tests/edge_lab/conftest.py`. Pick cut points that actually close trades — the guard fails a vacuous check by design. Also assert every emitted `Trade` has `exit_ts_ms > entry_ts_ms` and positive prices (the frozen dataclass enforces this, so a construction error surfaces as a `ValueError`, not a silent bad row).

- [ ] **Step 4: Verify and commit**

```bash
python3 -m pytest tests/edge_lab/test_edge_lab_funding_carry_variants.py tests/edge_lab/test_edge_lab_funding_carry.py --no-cov -q
```

---

## Task 7: Pairs / stat-arb candidate

A new candidate module. `services/trading-engine/app/strategies/pairs_trading.py` and `app/utils/statistical/cointegration.py` are **prior art only** — reuse the math shape (OLS hedge ratio, Engle–Granger ADF on the spread with MacKinnon critical values, z-score entries and exits), never the imports. Those modules drag in `statsmodels` and `scipy`, which the battery stack does not require, and `pairs_trading.py` is on the account-size offender list.

**Two constraints that will otherwise sink this:**

1. **`Trade` is single-symbol and single-leg.** A pair position must be emitted as **two** `Trade` rows — one LONG, one SHORT, sharing entry and exit timestamps. Gate 2's equal-weight divisor (open positions per day) then halves each leg's contribution naturally.
2. **Calibration must be causal.** The hedge ratio and the spread's mean and standard deviation must be estimated **only** from bars strictly before the entry bar, re-estimated on a pinned cadence. `assert_shift_invariant` is designed to catch a violation here, and this is the single most likely place in the whole plan for look-ahead to creep in.

**Files:** create `backtesting/edge_lab/candidates/pairs_statarb.py`; modify `run_battery.py` (`_CANDIDATE_SPECS` row with `("daily",)` inputs, `LABEL_HORIZONS` entry); test `tests/edge_lab/test_edge_lab_pairs_statarb.py`

- [ ] **Step 1: Read an existing candidate as the template**

```bash
sed -n '1,120p' backtesting/edge_lab/candidates/xs_momentum.py
```

The contract is exactly two module-level names: `VARIANTS: list[Variant]` and `generate_trades(<bundle frames...>, variant) -> list[Trade]`.

- [ ] **Step 2: Implement with numpy only**

Hedge ratio via `np.polyfit(x, y, 1)` or `np.linalg.lstsq` — not `scipy.stats.linregress`. If a stationarity test is wanted, either use a numpy half-life bound on the spread, or declare `statsmodels` as a new **host** dependency explicitly in the manifest and the commit message. Do not add a dependency silently.

Force-close or discard positions still open at the data end — nothing downstream does it for you, and `Trade` requires an exit.

- [ ] **Step 3: Register it**

Add a `_CANDIDATE_SPECS` row (`("pairs_statarb", "edge_lab.candidates.pairs_statarb", ("daily",))`) and a `LABEL_HORIZONS` entry in the **same commit** as the module. A missing horizon silently falls back to 7 days with only a `logger.warning`.

- [ ] **Step 4: Test**

Synthesize a cointegrated pair as a common random walk plus stationary AR(1) noise, following `tests/edge_lab/conftest.py`'s `make_daily` fixture shape. Assert: two rows per pair position with matching timestamps and opposite sides; `assert_shift_invariant` passes; and a **negative control** — two independent random walks must produce few or no trades, or produce trades that Gate 1 kills. A candidate that trades enthusiastically on noise is detecting nothing.

- [ ] **Step 5: Verify and commit**

```bash
python3 -m pytest tests/edge_lab/test_edge_lab_pairs_statarb.py tests/edge_lab/test_edge_lab_battery.py --no-cov -q
```

---

## Task 8: Regime-gated trend variants

**State the prior honestly in the code comments:** `lf_trend`'s Gate 1 pass came from a few outliers rather than a distribution (pooled PF ≈ 1.0 at Gate 2). A regime filter that merely removes losing periods in-sample is overfitting, and the DSR exists to catch it. This candidate is expected to fail; running it is how we find out cheaply.

**Files:** modify `backtesting/edge_lab/candidates/lf_trend.py`; test `tests/edge_lab/test_edge_lab_lf_trend_regime.py`

- [ ] **Step 1: Add exactly the manifest's variants**, parameterized through `Variant.params`, with the regime filter computed **causally** — using only bars strictly before the entry bar.
- [ ] **Step 2: Test**, including `assert_shift_invariant` and an assertion that the regime filter reduces trade count relative to the ungated variant (if it does not, it is not filtering anything).
- [ ] **Step 3: Verify and commit.**

---

## Task 9: Run battery #2, write verdicts, checkpoint

- [ ] **Step 1: Confirm the data is present**

The battery is network-free and reads CSVs only. Kline CSVs are gitignored, so confirm they exist before running:

```bash
ls backtesting/data/*_1440m_730d_bybit.csv | wc -l   # expect 30
ls backtesting/data/*_240m_365d_bybit.csv | wc -l    # expect 30
ls backtesting/data/funding/*_funding.csv | wc -l    # expect 30
```

If any set is missing, re-fetch with `fetch.ensure_klines` / `fetch.ensure_funding` as a **separate pre-battery step**. Never add a network call inside `run_battery`.

- [ ] **Step 2: Run the battery**

```bash
python3 backtesting/edge_lab/run_battery.py \
  --pin backtesting/edge_lab/universe_2026-08-17.json \
  --date 2026-08-18
```

Exit code 1 means at least one candidate produced an `ERROR` verdict — that is a bug in the candidate, **not** a REJECT. Fix it and re-run. Never let an import failure or an empty fetch be filed as a rejection; that mistake was caught once already during the battery's own construction.

- [ ] **Step 3: Read the verdicts before writing a word of summary**

```bash
cat .planning/evidence/killtests/battery-summary-20260818.md
```

For each candidate, read its `*-verdict-20260818.md` and `.json`. Check specifically:

- `num_trials_used` in the JSON — confirm the ledger floor was applied and matches the value in the rendered `.md`. If they disagree, the Task 4 threading is broken and every number in the doc is suspect.
- `funding_missing` and `notional_provenance` — a candidate scored against missing funding is not scored.
- `gate2_trades_dropped_no_daily` — a large drop means the trade set and the price data disagree.

- [ ] **Step 4: Hostile review of any PASS**

If **any** candidate reaches `PASS`, do not celebrate and do not proceed to implementation. Dispatch the `quant-skeptic` agent against the verdict — its default position is *no edge*, and a genuine PASS must survive it. Look-ahead, in-sample parameter selection, survivorship, and cost understatement are the standing suspects.

If every candidate REJECTs, that is the expected outcome and a complete deliverable. Write it up plainly.

- [ ] **Step 5: Commit the evidence**

```bash
git commit -- .planning/evidence/killtests/ backtesting/edge_lab/trial_ledger.json -m "data(edge-lab): battery #2 verdicts 2026-08-18

<one line per candidate: verdict, best ratio_taker, gate1/gate2 counts>

Trial ledger updated: <N> distinct variants recorded, effective trials floor
<F> applied at Gate 2."
```

- [ ] **Step 6: Report to the operator and stop**

Batteries never auto-loop. Report per candidate: the verdict, the number that decided it, and what it rules out. Then state the ledger count and the effective floor now in force, and **ask which direction battery #3 should take, or whether to stop.** Do not begin battery #3 without that answer.

---

## Plan C completion checklist

- [ ] `python3 -m pytest tests/edge_lab tests/killtests --no-cov -q` green from the repo root.
- [ ] `python3 -m pytest tests/test_phase1_runner_capital.py tests/test_account_size_invariant.py --no-cov -q` green.
- [ ] The slippage drift guard has been *seen* to fail on a deliberate mismatch.
- [ ] `trial_ledger.json` contains the 8 seeded battery-#1 variants plus the H-series, and grew by battery #2's variants — including its `NO_TRADES` and Gate-1 `KILL` variants.
- [ ] Every rendered verdict doc's `num_trials_used` matches its JSON.
- [ ] Verdict docs and the battery summary are committed under `.planning/evidence/killtests/`.
- [ ] The operator has been given the per-candidate verdicts and asked to direct battery #3.

## Standing rules for every future battery

1. Pre-register before implementing. No variant is added after a run starts.
2. Universe stays pinned. Re-pinning mid-battery is forbidden.
3. Every variant gets a ledger row — including `NO_TRADES` and Gate-1 deaths. They were still trials.
4. `ERROR` is never filed as `REJECT`.
5. A PASS goes through `quant-skeptic` before anything is implemented, and then through the promotion path in the design spec (`StrategyBase` contract, ATR stops, cap-honoring sizing, the venue-floor check — a $10 cap against a $5 minimum notional confines candidates to SOL/BNB/ADA-class notionals — backtest re-confirmation through the repaired engine, and one paper trade observed end to end from `signals` row to `orders` row to notification).
6. REJECT is a complete deliverable. Write it up and stop.
