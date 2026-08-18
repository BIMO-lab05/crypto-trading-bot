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
| `backtesting/screen.py` | `screen_trades`, the shared Gate 1 cost engine. Its `main()` additionally holds a hand-copied slippage table that **only the standalone CLI** reads. | 1 |
| `backtesting/edge_lab/config.py` | Pinned battery constants, including the `SLIPPAGE_BPS` / `SLIPPAGE_FALLBACK_BPS` copy that **every battery Gate 1 verdict is computed against** (via `gate1.py:44-45`). **Read-only in this plan** — Task 1's guard pins it; no task edits it. | 1 (guarded, never modified) |
| `backtesting/run_phase1_backtest.py` | Research runner; `--capital` argparse default. | 2 |
| `backtesting/edge_lab/trial_ledger.py` | **NEW** — append-only trial record + effective-floor computation. | 3 |
| `backtesting/edge_lab/trial_ledger.json` | **NEW** — the ledger data, seeded retroactively. | 3 |
| `backtesting/edge_lab/gate2.py` | `Gate2Result`; DSR call where `num_trials` enters. | 4 |
| `backtesting/edge_lab/run_battery.py` | Registry, bundle loading, per-variant scoring, verdict writing, trades-CSV path. | 4 (floor threading + ledger appends), 7 (`_CANDIDATE_SPECS` + `LABEL_HORIZONS` row for the new candidate), 9 Step 1b (dated trades directory). Tasks 3, 6 and 8 do **not** touch it — 6 and 8 only extend existing candidates' `VARIANTS`. |
| `backtesting/edge_lab/verdicts.py` | Three sites that render the trials floor: `TRIALS_CAVEAT` (`:54`, emitted through the shared `_caveats` helper at `:179`), the criterion line (`:249`), the JSON `thresholds` block (`:407`). | 4 |
| `backtesting/edge_lab/candidates/battery_2026-08-18_manifest.md` | **NEW** — pre-registration, committed before any candidate code. | 5 |
| `backtesting/edge_lab/candidates/pairs_statarb.py` | **NEW** candidate. | 7 |
| `backtesting/edge_lab/candidates/funding_carry.py` | Existing; gains variants. | 6 |
| `backtesting/edge_lab/candidates/lf_trend.py` | Existing; gains regime-gated variants. | 8 |

---

# Part 1 — Trustworthy research inputs (Tasks 1–2)

## Task 1: Pin both research slippage tables to the paper engine's

There are **three** copies of the slippage table in this repo, and only one of them is canonical:

| Copy | Who reads it |
|---|---|
| `services/trading-engine/app/paper_slippage.py:92-103` — `DEFAULT_SLIPPAGE_BPS` / `FALLBACK_SLIPPAGE_BPS` | **Canonical.** The paper engine. |
| `backtesting/edge_lab/config.py:16-25` — `SLIPPAGE_BPS` / `SLIPPAGE_FALLBACK_BPS` | **Every battery Gate 1 verdict.** `gate1.py:22` imports them, `gate1.py:44-45` passes them to `screen_trades`, and `run_battery.py:451` calls `run_gate1` — so all four 2026-08-17 verdicts in `.planning/evidence/killtests/*-verdict-20260817.*` were computed against this copy. |
| `backtesting/screen.py:318-329` — the `slippage = {...}` local inside `main()` | **Only** the standalone CLI (`python backtesting/screen.py --trades ...`). `gate1.py` imports `MODELLED_FEE_RATE_PER_PAIR`, `ScreenResult`, `_rows_from_csv` and `screen_trades` from `screen.py` — never its table. Even the H3 killtests define their own local `SLIP`/`FALLBACK` (`tests/killtests/test_screen.py:26-27`, `test_screen_reproduces_h3.py:38`). |

All three currently **agree** (5/5/5/10/10, fallback 10) — but nothing enforces that (`grep -rn "SLIPPAGE_BPS\|paper_slippage" tests/ --include=*.py` returns nothing today), and the canonical table is explicitly slated for recalibration (its own comment says *"SOLUSDT … calibrate first"*). A calibration update would silently leave both research paths — the battery's and the CLI's — computing against stale costs.

This task pins **both research mirrors** to the canonical one. The `screen.py` table is a local inside `main()`, invisible to any importer, so hoisting it to module scope is a prerequisite for testing it. `edge_lab/config.py` is already at module scope and is **not modified by this task** — the guard only reads it.

**Do not make `screen.py` or `edge_lab/config.py` import `paper_slippage`.** `screen.py` must stay runnable standalone (`python backtesting/screen.py`) without a `services/` path hack, and `config.py`'s whole point is to be a declared-before-any-run pin. Agreement is enforced at test time — the same pattern `shared/account.py` uses.

**Files:**
- Modify: `backtesting/screen.py` (hoist to module scope after line ~50; update the two `screen_trades` kwargs)
- Create: `tests/killtests/test_slippage_table_sync.py`
- Read-only: `backtesting/edge_lab/config.py` (asserted against, never edited — see the failure message in Step 2)

**Interfaces:**
- Produces: `screen.SLIPPAGE_BPS_BY_SYMBOL: dict[str, Decimal]` and `screen.SLIPPAGE_FALLBACK_BPS: Decimal` at module scope.
- Consumes unchanged: `edge_lab.config.SLIPPAGE_BPS`, `edge_lab.config.SLIPPAGE_FALLBACK_BPS`. Both import fine from `tests/killtests` — its `conftest.py:9` puts `backtesting/` on `sys.path`, and `config.py`'s own `from shared.account import ACCOUNT_EQUITY_USD` resolves from the repo-root CWD.

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
Both research cost models must equal the paper engine's.

There are three copies of the slippage table. paper_slippage.py is canonical.
edge_lab/config.py is the copy EVERY battery Gate 1 verdict is computed
against (gate1.py:22 imports it, gate1.py:44-45 passes it to screen_trades,
run_battery.py:451 calls run_gate1). screen.py's module-scope table feeds only
the standalone CLI (`python backtesting/screen.py --trades ...`).

Neither research copy imports paper_slippage: screen.py must stay runnable
standalone, and config.py is a declared-before-any-run pin. Nothing enforced
agreement, and paper_slippage.py is explicitly slated for recalibration
("SOLUSDT ... calibrate first") - a recalibration would silently leave both
research paths on stale costs.

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
from edge_lab.config import SLIPPAGE_BPS, SLIPPAGE_FALLBACK_BPS

REPO_ROOT = Path(__file__).resolve().parents[2]
PAPER_SLIPPAGE_PATH = (
    REPO_ROOT / "services" / "trading-engine" / "app" / "paper_slippage.py"
)

# The obvious way to make a config failure green is forbidden. config.py:1-2:
# "Declared before any run; changing a value after verdicts exist invalidates
# them (spec section 4 anti-overfitting rule)."
CONFIG_REMEDIATION = (
    "paper_slippage has been recalibrated, so the pinned battery cost model is "
    "stale - this INVALIDATES the existing battery verdicts under "
    ".planning/evidence/killtests/. Re-pin and re-run the battery. Do NOT edit "
    "backtesting/edge_lab/config.py just to make this test green."
)


def _load_paper_slippage():
    name = "_slippage_sync_paper_slippage"
    spec = importlib.util.spec_from_file_location(name, PAPER_SLIPPAGE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_battery_slippage_table_matches_paper_engine():
    paper = _load_paper_slippage()
    assert SLIPPAGE_BPS == paper.DEFAULT_SLIPPAGE_BPS, (
        "edge_lab.config and the paper engine disagree on slippage; every "
        "battery Gate 1 verdict is computed against edge_lab.config. "
        + CONFIG_REMEDIATION
    )


def test_battery_slippage_fallback_matches_paper_engine():
    paper = _load_paper_slippage()
    assert SLIPPAGE_FALLBACK_BPS == paper.FALLBACK_SLIPPAGE_BPS, CONFIG_REMEDIATION


def test_screen_slippage_table_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_BPS_BY_SYMBOL == paper.DEFAULT_SLIPPAGE_BPS, (
        "the standalone screen CLI and the paper engine disagree on slippage; "
        "`python backtesting/screen.py --trades ...` is computed against the "
        "screen's table"
    )


def test_screen_slippage_fallback_matches_paper_engine():
    paper = _load_paper_slippage()
    assert screen.SLIPPAGE_FALLBACK_BPS == paper.FALLBACK_SLIPPAGE_BPS
```

- [ ] **Step 3: Verify — and prove the guard has teeth**

```bash
python3 -m pytest tests/killtests/test_slippage_table_sync.py tests/killtests/test_screen.py --no-cov -q
```

Expected: all four pass. This guard lands **green**, which is correct and matches the `test_account_config_sync.py` convention — a sync test must be green on the commit that introduces it.

Green proves nothing until you have seen it go red, and there are **two** copies to prove, one at a time:

1. In `backtesting/screen.py`, temporarily set `SLIPPAGE_BPS_BY_SYMBOL["SOLUSDT"] = Decimal("7")`, re-run, confirm `test_screen_slippage_table_matches_paper_engine` fails and names the mismatch, then revert.
2. In `backtesting/edge_lab/config.py`, temporarily set `SLIPPAGE_BPS["SOLUSDT"] = Decimal("7")`, re-run, confirm `test_battery_slippage_table_matches_paper_engine` fails and that the message tells the reader to re-run the battery rather than edit `config.py`, then **revert — `git diff backtesting/edge_lab/config.py` must be empty before you commit.** `config.py` is a pin; this task must not change a byte of it.

- [ ] **Step 4: Commit**

```bash
git commit -- backtesting/screen.py tests/killtests/test_slippage_table_sync.py -m "test(research): pin both research slippage tables to the paper engine's

Three copies of the slippage table, none of them guarded. paper_slippage.py
is canonical. edge_lab/config.py is the copy every battery Gate 1 verdict is
computed against (gate1.py:44-45 via run_battery.py:451) - including all four
2026-08-17 verdicts. screen.py restated a third copy inside main(), invisible
to any importer, reachable only from the standalone CLI. The values agree
today, but paper_slippage is explicitly slated for recalibration - a change
there would silently leave both research paths computing against stale costs.

screen.py's table is hoisted to module scope so it can be asserted on; both
research copies are now pinned by the drift guard. Neither imports across the
service boundary: screen.py must stay runnable standalone and config.py is a
declared-before-any-run pin, so agreement is enforced at test time, the same
pattern shared/account.py uses. paper_slippage is spec-loaded under a unique
module name because a second \`app\` package on sys.path would collide with the
one tests/security/conftest.py installs.

edge_lab/config.py is deliberately NOT in this pathspec - the guard reads it
and never edits it. Its failure message says so, because editing the pin to
make the test green would invalidate the verdicts the pin exists to protect."
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
 "params": [["threshold_mult", "2"]], "date": "2026-08-17",
 "gate1_verdict": "PASS", "gate2_passed": false}
```

That is the real key and the real value: `funding_carry.py:80-84` declares `params=(("threshold_mult", "2"),)` and `funding_carry.py:138` reads `Decimal(dict(variant.params)["threshold_mult"])`. **Ledger param values are strings**, matching `run_battery._score_variant` (`run_battery.py:439`), which already stringifies as `{str(k): str(v) for k, v in variant.params}` on the way into the verdict JSONs — so a ledger row and its verdict row are comparable without a coercion step. Take every key and value from the committed verdict JSONs; do not retype them from memory.

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

**The `path=None` default must resolve through `ledger_path()` at call time, in all three of `load_entries`, `append_entries` and `effective_trials_floor`** — never through a module-level `LEDGER_PATH = ledger_path()` constant, and never by inlining `json.loads(...)` at a hard-coded path:

```python
def load_entries(path: Path | None = None) -> list[dict]:
    path = Path(path) if path is not None else ledger_path()
    ...
```

That single indirection is the only test seam the whole plan has. Task 4 makes `run_battery` both **read** the ledger (to compute the effective floor) and **write** to it (one row per variant), and `tests/edge_lab/test_edge_lab_battery.py` drives `run_battery` with stub registries at four sites. Bind the path at import time and running `pytest tests/edge_lab` appends rows for fictional candidates named `boom`, `quiet` and `stub` straight into the committed `trial_ledger.json` — corrupting the evidence file the completion checklist asserts the contents of, and making the floor a function of how often the suite was run. With the indirection, one `monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")` redirects reads and writes together.

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

**Files:** `backtesting/edge_lab/gate2.py`, `backtesting/edge_lab/run_battery.py`, `backtesting/edge_lab/verdicts.py`; tests `tests/edge_lab/test_edge_lab_trials_threading.py` (new) and `tests/edge_lab/test_edge_lab_battery.py` (existing — its four `run_battery` call sites gain the ledger redirect, see the ledger-seam note below; it must ship in **this** task's commit, not sit uncommitted across Tasks 5–8)

**Interfaces:**
- `Gate2Result` gains `num_trials_used: int`.
- `score_gate2(...)` gains a `num_trials_floor: int` parameter.
- `render_verdict`, `render_summary`, `write_verdict_json` gain `num_trials_floor: int = NUM_TRIALS_FLOOR`.
- `_caveats` (`verdicts.py:179`) gains `num_trials_floor: int` — it is the shared helper all three renderers call.
- `TRIALS_CAVEAT` becomes a function `trials_caveat(n: int) -> str`.
- **Add fields, never rename or remove.** The 2026-08-17 verdict JSONs are committed evidence and downstream readers key on their shape.

- [ ] **Step 1: Write the failing tests**

Cover:

- (a) `run_gate2` with an explicit `num_trials_floor` above the path count records that value in `num_trials_used` — pass a floor `> 45` so it actually binds.
- (b) DSR is monotonically non-increasing as the floor rises.
- (c) a rendered verdict `.md` contains the effective floor, not the constant `16`, when they differ.
- (d) the JSON `thresholds.num_trials_floor` matches the effective floor.
- (e) every key present in a committed `*-verdict-20260817.json` is still present in a freshly rendered one.
- (f) **the floor survives the round trip through `run_battery`.** Tests (c) and (d) must drive `run_battery(...)` with a stub registry and then read the written `.md` / `.json` off disk — **not** call `render_verdict` / `write_verdict_json` directly. Those renderers default `num_trials_floor` to `NUM_TRIALS_FLOOR`, so a direct call passes while the real pipeline silently renders `16`. The stub-registry harness already exists: `tests/edge_lab/test_edge_lab_battery.py:78` (`_stub_registry`, `run_battery(tmp_path, pin, tmp_path / "out", ...)`). Its helpers are module-level and importable the same way `conftest`'s are — `from test_edge_lab_battery import _pin, _stub_registry, _write_daily_csvs` — because `tests/edge_lab/` has no `__init__.py` and pytest prepends the test directory to `sys.path`. Reuse them; do not fork a second copy of the harness.
- (g) **a re-run adds nothing.** Given a ledger that already contains every `(candidate, variant)` pair the registry will score, `effective_trials_floor` must return exactly what it returned before the run — re-scoring a ledgered variant contributes zero, per Task 3's counting rule.

**Every test that drives `run_battery` must redirect the ledger first**, including the ones you are extending in `test_edge_lab_battery.py`:

```python
monkeypatch.setattr(trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json")
```

Task 3's `load_entries` / `append_entries` / `effective_trials_floor` all resolve a `None` path through `ledger_path()` at call time, so that one line controls reads and writes together. Without it the suite reads *and appends to* the committed `backtesting/edge_lab/trial_ledger.json`: test (g) has no way to construct the ledger state it needs, tests (c)/(d) inherit whatever the production file happens to hold, and `pytest tests/edge_lab` silently writes `boom`/`quiet`/`stub` rows into committed evidence.

- [ ] **Step 2: Implement the threading**

1. `gate2.py`: add `num_trials_used: int` to `Gate2Result` (**no default** — a default of `0` would let the arity error below pass silently while recording a false trials count), and populate it at **both** `Gate2Result(...)` construction sites:
   - `gate2.py:296` — the normal return: `max(num_trials_floor, int(dist["n_paths"]))`, the same expression the DSR call at `:263` uses. When `n_paths < 2` and DSR is `nan`, still record the floor that would have applied.
   - `gate2.py:237` — the `except ValueError` early return (`"insufficient samples / invalid split params"`). `dist` is not assigned until `:250`, so the expression above is *uncomputable* here: record `num_trials_floor` directly. No paths were built, so the floor is the only trials count that applies. Miss this site and `Gate2Result.__init__` raises `TypeError: missing 1 required positional argument`, which `tests/edge_lab/test_edge_lab_gate2.py:71-74` will hit in Step 3.
2. `run_battery.py`: after `registry` is assigned (`run_battery.py:515`) and before the candidate loop (`:518`), compute the floor once:
   ```python
   known = {(e["candidate"], e["variant"]) for e in trial_ledger.load_entries()}
   scored = {(c, v.name) for c, e in registry.items() for v in e["variants"]}
   total_new_variants = len(scored - known)
   effective_floor = trial_ledger.effective_trials_floor(total_new_variants)
   ```
   `total_new_variants` is the count of `(candidate, variant)` pairs this battery will score that are **not already in the ledger** — re-runs of battery-1 variants contribute zero, per Task 3's counting rule. This matters because the battery has no candidate or variant selector (`main()` exposes only `--data-dir/--pin/--out/--date`), so it re-scores all eight battery-1 variants on every run; counting them as new would add them to a distinct count that already contains them and double the floor's growth rate on fabricated grounds. A candidate whose module failed to import carries `"variants": []`, so it drops out for free.

   Thread `effective_floor` down to the DSR call. `score_gate2` is defined at `run_battery.py:339` and invoked from inside `_score_variant` (`:468`), so the floor has to travel through it: add a `num_trials_floor: int` parameter to `_score_variant` (`:425-432`) and to `score_gate2`, pass `effective_floor` at the `_score_variant` call site in the candidate loop (`:552-557`), and land it as `run_gate2(returns, horizon, num_trials_floor=num_trials_floor)`. Then put `gate2.num_trials_used` into the record dict as `num_trials_used`.
3. `verdicts.py`: convert `TRIALS_CAVEAT` (`verdicts.py:54-55`) to `trials_caveat(n)`, and take the floor as a parameter at **three** sites:
   - the criterion line in `render_verdict` (`verdicts.py:249`);
   - the JSON `thresholds` block in `write_verdict_json` (`verdicts.py:407`);
   - `_caveats` (`verdicts.py:179`) — it gains a `num_trials_floor` parameter and calls `trials_caveat(num_trials_floor)`. This is the one that is easy to miss: `_caveats` is the shared helper called by `render_verdict` (`:284`), `render_summary` (`:348`) and `write_verdict_json` (`:411`), so writing `trials_caveat(NUM_TRIALS_FLOOR)` inside it satisfies the letter of this item while still printing "num_trials floor = 16" in the caveat block of every output. All three renderers thread their own floor into it.
4. `run_battery.py`: **pass `num_trials_floor=effective_floor` at all three existing render call sites** — `render_verdict` (`run_battery.py:570`), `write_verdict_json` (`:577`), `render_summary` (`:587`). The parameter defaults to `NUM_TRIALS_FLOOR`, so omitting it here is silent: the per-variant `num_trials_used` would carry the real floor into the JSON while `thresholds.num_trials_floor` and the `.md` criterion line still said `16` — the exact failure this task exists to prevent, in its most confusing form.
5. `run_battery.py`: append one ledger entry per variant **after** each candidate's record is assembled, alongside the existing `write_verdict` calls — per candidate, not per battery, so a battery that dies on candidate 3 still ledgers candidates 1–2. Cover **all three** variant states: `NO_TRADES`, Gate-1 `KILL`, and `PASS`. Wrap the ledger write the same way verdict writes are wrapped: a failure is logged and recorded, never fatal to the battery.

- [ ] **Step 3: Verify and commit**

```bash
python3 -m pytest tests/edge_lab --no-cov -q
```

Expected: the full `tests/edge_lab` suite green (80 tests as of `cca426c`, plus the new ones).

```bash
git commit -- backtesting/edge_lab/gate2.py backtesting/edge_lab/run_battery.py backtesting/edge_lab/verdicts.py tests/edge_lab/test_edge_lab_trials_threading.py tests/edge_lab/test_edge_lab_battery.py -m "feat(edge-lab): thread the effective trials floor into Gate 2 and verdicts

run_battery never passed num_trials_floor, Gate2Result had no field recording
the trials count actually used, and verdicts.py imported NUM_TRIALS_FLOOR at
three render sites. A ledger-derived floor that was not threaded through would
have made every future verdict doc state 16 while Gate 2 deflated against
something else - in docs that claim every threshold is read live from
edge_lab.config rather than transcribed.

Gate2Result gains num_trials_used, populated at both construction sites
including the insufficient-samples early return, where no paths exist and the
floor is the only trials count that applies. The renderers - including the
shared _caveats helper - take the floor as a parameter, and run_battery
supplies it at all three render call sites. run_battery computes the floor
once from the ledger, counting only (candidate, variant) pairs not already
ledgered (the battery re-scores every prior variant on every run, so counting
those as new would double the floor's growth rate), and appends one entry per
variant per candidate, covering NO_TRADES, Gate-1 KILL and PASS alike.

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
6. **Cost exposure** — round-trips per position (pairs emits two `Trade` legs per position, so it pays double) and the holding horizon that determines funding accrual. This is the per-candidate *consequence* of the cost model, not a restatement of the rate card; the rate card itself is global and recorded once, below.

The three families, with the evidence that motivates each:

| Family | Motivation | Prior |
|---|---|---|
| **Funding-carry refinements** | Best survivor of battery #1: `thresh_2x` cleared Gate 1 at ratio 2.603, died at Gate 2 (DSR 5.8e-10, positive-path fraction 0.444). Mechanism is real and identifiable: perpetual funding is a payment from crowded longs to shorts. The design spec pins three variant directions as seeds — **funding-percentile entry, holding-period sweep, symbol filter**. Finalize each into exact parameter values in the manifest; these are the pre-registered directions, not a menu to substitute from. | Highest |
| **Pairs / stat-arb** | The one classic family no battery has tested. Mechanism: cointegrated pairs mean-revert around a stable hedge ratio. | Medium |
| **Regime-gated trend** | `lf_trend` cleared Gate 1 decisively (ratios 4.85 and 15.511) but failed Gate 2 with pooled PF ≈ 1.0 — its profit was a handful of outliers, not a distribution. The pinned seed direction is: **a regime filter attempts to turn outliers into a distribution.** | **Low — state this plainly.** A filter that merely removes losing periods in-sample is overfitting, and the DSR is designed to catch exactly that. |

Also record: the universe pin (`universe_2026-08-17.json`, unchanged), the data cutoff `--date`, the ledger count going in, and **the cost model in force as one global block**, read live from `backtesting/edge_lab/config.py` and `backtesting/screen.py` — `MODELLED_FEE_RATE_PER_PAIR`, `SLIPPAGE_BPS` + `SLIPPAGE_FALLBACK_BPS`, `HURDLE_MULTIPLE`, the funding CSV source dir, `DSR_THRESHOLD`, `MIN_POSITIVE_PATH_FRAC`, `NOTIONAL_PER_TRADE`. Transcribe it **once, never per candidate**: `gate1.py:24` loads a single global `_costs` and every candidate is charged from the identical pinned block, so restating the figures three times only invites the transcription drift Task 1 exists to prevent.

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

**Files:** modify `backtesting/edge_lab/candidates/funding_carry.py` (extend `VARIANTS`); modify `tests/edge_lab/test_edge_lab_funding_carry.py` (line 28 asserts `[v.name for v in VARIANTS] == ["thresh_1.5x", "thresh_2x"]` by exact equality and **will fail** the moment new variants land — extend the expected list, do not delete the assertion); create `tests/edge_lab/test_edge_lab_funding_carry_variants.py`. `run_battery.py` needs **no** change: `run_battery.py:92` already carries `"funding_carry": 10` in `LABEL_HORIZONS`.

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

```bash
git commit -- backtesting/edge_lab/candidates/funding_carry.py \
  tests/edge_lab/test_edge_lab_funding_carry_variants.py \
  tests/edge_lab/test_edge_lab_funding_carry.py \
  -m "feat(edge-lab): funding-carry refinement variants

The variants pre-registered in battery_2026-08-18_manifest.md, added verbatim
and parameterized through Variant.params - no branching on variant names, so
generate_trades stays one code path. Shift-invariance is asserted on a cut
point that actually closes trades, since the guard fails a vacuous check by
design (cca426c).

test_edge_lab_funding_carry.py's exact-equality VARIANTS assertion is extended
rather than removed: the point of that assertion is that a variant cannot be
added without a deliberate edit here.

run_battery.py is deliberately absent from this pathspec - LABEL_HORIZONS
already carries funding_carry: 10."
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

```bash
git commit -- backtesting/edge_lab/candidates/pairs_statarb.py \
  backtesting/edge_lab/run_battery.py \
  tests/edge_lab/test_edge_lab_pairs_statarb.py \
  -m "feat(edge-lab): pairs/stat-arb candidate

The one classic family no battery has tested, pre-registered in
battery_2026-08-18_manifest.md. numpy only - services/trading-engine's
pairs_trading.py and cointegration.py are prior art for the math shape (OLS
hedge ratio, spread z-score entries and exits), never imports: they drag in
statsmodels and scipy, which the battery stack does not require, and
pairs_trading.py is on the account-size offender list.

A pair position is emitted as two Trade rows - one LONG, one SHORT, sharing
entry and exit timestamps - because Trade is single-symbol and single-leg;
Gate 2's equal-weight divisor then halves each leg's contribution. Hedge ratio
and spread moments are estimated only from bars strictly before the entry bar,
which is what assert_shift_invariant is pinning here. The negative control -
two independent random walks - is part of the test set: a candidate that
trades enthusiastically on noise is detecting nothing.

The _CANDIDATE_SPECS row and the LABEL_HORIZONS entry land in this same commit;
a missing horizon falls back to 7 days behind only a logger.warning."
```

---

## Task 8: Regime-gated trend variants

**State the prior honestly in the code comments:** `lf_trend`'s Gate 1 pass came from a few outliers rather than a distribution (pooled PF ≈ 1.0 at Gate 2). A regime filter that merely removes losing periods in-sample is overfitting, and the DSR exists to catch it. This candidate is expected to fail; running it is how we find out cheaply.

**Files:** modify `backtesting/edge_lab/candidates/lf_trend.py`; modify `tests/edge_lab/test_edge_lab_lf_trend.py` (line 41 asserts `[v.name for v in VARIANTS] == ["dc_20_10", "dc_55_20"]` by exact equality and **will fail** the moment regime variants land — extend the expected list, do not delete the assertion); create `tests/edge_lab/test_edge_lab_lf_trend_regime.py`

- [ ] **Step 1: Add exactly the manifest's variants**, parameterized through `Variant.params`, with the regime filter computed **causally** — using only bars strictly before the entry bar.
- [ ] **Step 2: Test**, including `assert_shift_invariant` and an assertion that the regime filter reduces trade count relative to the ungated variant (if it does not, it is not filtering anything).
- [ ] **Step 3: Verify and commit**

Run the existing `lf_trend` test alongside the new one — it is the file the new variants break, and running only the new file would defer a guaranteed failure to the completion checklist's full-suite run:

```bash
python3 -m pytest tests/edge_lab/test_edge_lab_lf_trend_regime.py \
  tests/edge_lab/test_edge_lab_lf_trend.py --no-cov -q
```

```bash
git commit -- backtesting/edge_lab/candidates/lf_trend.py \
  tests/edge_lab/test_edge_lab_lf_trend_regime.py \
  tests/edge_lab/test_edge_lab_lf_trend.py \
  -m "feat(edge-lab): regime-gated trend variants

The variants pre-registered in battery_2026-08-18_manifest.md, parameterized
through Variant.params, with the regime filter computed causally - only bars
strictly before the entry bar, which is what assert_shift_invariant pins.

Prior is deliberately low and the code comments say so: lf_trend's Gate 1 pass
(ratios 4.85 and 15.511) came from a handful of outliers, not a distribution -
pooled PF was about 1.0 at Gate 2. A filter that merely removes losing periods
in-sample is overfitting, which is exactly what the DSR exists to catch. This
candidate is expected to fail; running it is how we find that out cheaply.

test_edge_lab_lf_trend.py's exact-equality VARIANTS assertion is extended
rather than removed, so a variant still cannot be added without a deliberate
edit there."
```

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

- [ ] **Step 1b: Date-stamp the trades directory — do this BEFORE running anything**

Running the battery as it stands **destroys committed evidence.** `run_battery.py:434` writes `csv_path = Path(out_dir) / "trades" / f"{candidate}_{variant.name}.csv"` — no date component — and `trades.py:64` opens it `"w"`, truncating. `--out` defaults to `.planning/evidence/killtests` (`run_battery.py:601`), and all eight battery-1 CSVs are tracked, not gitignored:

```
.planning/evidence/killtests/trades/funding_carry_thresh_1.5x.csv
.planning/evidence/killtests/trades/funding_carry_thresh_2x.csv
.planning/evidence/killtests/trades/lf_trend_dc_20_10.csv
.planning/evidence/killtests/trades/lf_trend_dc_55_20.csv
.planning/evidence/killtests/trades/vol_breakout_sqz_default.csv
.planning/evidence/killtests/trades/xs_momentum_lookback_7d.csv
.planning/evidence/killtests/trades/xs_momentum_lookback_30d.csv
.planning/evidence/killtests/trades/xs_momentum_lookback_90d.csv
```

The battery has no candidate or variant selector (`main()` exposes only `--data-dir/--pin/--out/--date`; the `candidates` filter at `run_battery.py:515` is a Python kwarg), so battery #2 necessarily re-scores all eight and reopens exactly those filenames. The committed `*-verdict-20260817.json` files reference them by path — e.g. `funding_carry-verdict-20260817.json` records `"trades_csv": ".planning/evidence/killtests/trades/funding_carry_thresh_2x.csv"` — so a re-run leaves 2026-08-17 verdicts pointing at 2026-08-18 data. The verdict docs are date-stamped; their trades CSVs are not. Close that asymmetry.

**Do not use a throwaway `--out` instead.** The record stores `"trades_csv": str(csv_path)` (`run_battery.py:439`), so a temp `--out` bakes a path that does not exist in the repo into the new verdicts — a dangling pointer traded for a stale one, and the eight legacy filenames get regenerated in the temp dir anyway.

Three edits in `backtesting/edge_lab/run_battery.py`. **Line numbers below are as of `cca426c`; Task 4 has already added lines to this file, so locate each site by the quoted code, not by counting.**

1. Add `date_str: str` to `_score_variant`'s parameter list (`run_battery.py:425-432` — Task 4 added `num_trials_floor` here too). It is needed because `date_str` is computed at `:510` inside `run_battery`, and `_score_variant` has no access to it — changing line 434 alone raises `NameError`.
2. Change `run_battery.py:434` to:
   ```python
   csv_path = Path(out_dir) / "trades" / date_str / f"{candidate}_{variant.name}.csv"
   ```
   `write_trades_csv` already does `path.parent.mkdir(parents=True, exist_ok=True)` (`trades.py:63`), so the nested directory is created for free.
3. Pass it at the call site in the candidate loop (`run_battery.py:552-557`), alongside the `num_trials_floor` argument Task 4 added:
   ```python
   result["variants"].append(
       _score_variant(
           entry,
           bundle,
           variant,
           candidate,
           out_dir,
           funding_dir,
           effective_floor,
           date_str,
       )
   )
   ```

The eight 2026-08-17 CSVs stay exactly where they are, at the undated path, byte-for-byte — they simply stop being write targets. That is what makes the completion-checklist guard below a real check rather than a hope.

Pin it with a test. No existing test asserts the shape of `record["trades_csv"]` (`grep -rn "trades_csv" tests/` finds only `write_trades_csv` calls against `tmp_path`), so add one to `tests/edge_lab/test_edge_lab_battery.py`, using the stub-registry harness already in that file:

```python
def test_trades_csv_is_date_stamped(tmp_path, monkeypatch):
    """A re-run must not overwrite an earlier battery's committed trades CSVs.

    Verdict docs are date-stamped; the trades CSVs they reference were not, so
    re-running truncated the eight files the committed *-verdict-20260817.json
    records point at.
    """
    from edge_lab import trial_ledger
    from edge_lab.run_battery import date_str_from_ms

    # Task 4 made run_battery read and write the ledger. Redirect it, or this
    # test appends a "quiet" row to the committed trial_ledger.json.
    monkeypatch.setattr(
        trial_ledger, "ledger_path", lambda: tmp_path / "ledger.json"
    )

    daily = make_daily(["AUSDT"], n_days=400)
    _write_daily_csvs(tmp_path, daily)
    pin = _pin(tmp_path, ["AUSDT"])
    now_ms = T0 + 400 * DAY

    res = run_battery(
        tmp_path,
        pin,
        tmp_path / "out",
        now_ms,
        candidates=_stub_registry({"quiet": lambda b, v: []}),
    )

    csv_path = Path(res["quiet"]["variants"][0]["trades_csv"])
    assert csv_path.parent.name == date_str_from_ms(now_ms)
    assert csv_path.parent.parent.name == "trades"
    assert csv_path.exists()
```

While you are in this file, confirm the other `run_battery` call sites carry the same `monkeypatch` — Task 4 should have added it. There are exactly four in `tests/edge_lab/test_edge_lab_battery.py`, at lines 78, 94, 178 and 253: `test_crashing_candidate_isolated`, `test_zero_trades_recorded_not_screened`, `test_import_failure_is_error_not_reject`, and `test_verdict_docs_written_with_caveats`. The last one matters most — it is the one that actually scores variants, so without the redirect it appends rows to the committed `trial_ledger.json`. (`test_gate0_drops_are_scoped_to_the_failing_interval` calls `load_bundle`, not `run_battery`, and needs nothing.) `git diff backtesting/edge_lab/trial_ledger.json` must be empty after `pytest tests/edge_lab`.

Verify, then commit this on its own — it is a path fix, not part of Task 4's trials-floor threading:

```bash
python3 -m pytest tests/edge_lab/test_edge_lab_battery.py --no-cov -q
```

```bash
git commit -- backtesting/edge_lab/run_battery.py \
  tests/edge_lab/test_edge_lab_battery.py \
  -m "fix(edge-lab): date-stamp the battery trades directory

run_battery wrote trades/{candidate}_{variant}.csv with no date and truncating
mode, under an --out that defaults to .planning/evidence/killtests. The eight
battery-1 CSVs are committed evidence referenced by path from the
*-verdict-20260817.json records, and the battery has no variant selector - so
every re-run necessarily reopened and clobbered them, leaving 2026-08-17
verdicts pointing at newer data.

The verdict docs were already date-stamped; the CSVs they reference now are
too. _score_variant takes date_str because it is computed in run_battery and
was not in scope. The eight legacy files are untouched at the old path - they
simply stop being write targets."
```

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

- `thresholds.num_trials_floor` in the JSON — confirm it equals the effective ledger floor for this battery **and** equals the floor printed at the criterion line of the rendered `.md`. Then confirm each variant's `num_trials_used` equals `max(num_trials_floor, n_paths_valid)` from the same JSON record. If either identity fails, the Task 4 threading is broken. Note that `num_trials_used` will normally read **45** — the CPCV path count at the pinned 10/2 configuration — rather than the floor. **That is correct, not a bug:** the ledger floor only binds once it exceeds 45. The identity also holds in the degenerate branch, where `n_paths_valid` is 0 or 1 and the floor (≥ 16) wins.
- `funding_missing` and `notional_provenance` — a candidate scored against missing funding is not scored.
- `gate2_trades_dropped_no_daily` — a large drop means the trade set and the price data disagree.

- [ ] **Step 4: Hostile review of any PASS**

If **any** candidate reaches `PASS`, do not celebrate and do not proceed to implementation. Dispatch the `quant-skeptic` agent against the verdict — its default position is *no edge*, and a genuine PASS must survive it. Look-ahead, in-sample parameter selection, survivorship, and cost understatement are the standing suspects.

If every candidate REJECTs, that is the expected outcome and a complete deliverable. Write it up plainly.

- [ ] **Step 5: Commit the evidence**

Name the new files explicitly. A wholesale `.planning/evidence/killtests/` pathspec would sweep in anything else under that directory — the whole reason Step 1b exists.

```bash
git commit -- \
  .planning/evidence/killtests/battery-summary-20260818.md \
  .planning/evidence/killtests/funding_carry-verdict-20260818.md \
  .planning/evidence/killtests/funding_carry-verdict-20260818.json \
  .planning/evidence/killtests/lf_trend-verdict-20260818.md \
  .planning/evidence/killtests/lf_trend-verdict-20260818.json \
  .planning/evidence/killtests/pairs_statarb-verdict-20260818.md \
  .planning/evidence/killtests/pairs_statarb-verdict-20260818.json \
  .planning/evidence/killtests/vol_breakout-verdict-20260818.md \
  .planning/evidence/killtests/vol_breakout-verdict-20260818.json \
  .planning/evidence/killtests/xs_momentum-verdict-20260818.md \
  .planning/evidence/killtests/xs_momentum-verdict-20260818.json \
  .planning/evidence/killtests/trades/20260818/ \
  backtesting/edge_lab/trial_ledger.json \
  -m "data(edge-lab): battery #2 verdicts 2026-08-18

<one line per candidate: verdict, best ratio_taker, gate1/gate2 counts>

Trial ledger updated: <N> distinct variants recorded, effective trials floor
<F> applied at Gate 2."
```

The trades subdirectory is `trades/20260818/`, not `trades/2026-08-18/`: `date_str_from_ms` (`run_battery.py:134`) formats `%Y%m%d`, which is why the verdict files read `-20260818`. Run `ls .planning/evidence/killtests/trades/` and confirm the directory name before committing — a pathspec that matches nothing commits nothing, silently.

- [ ] **Step 6: Report to the operator and stop**

Batteries never auto-loop. Report per candidate: the verdict, the number that decided it, and what it rules out. Then state the ledger count and the effective floor now in force, and **ask which direction battery #3 should take, or whether to stop.** Do not begin battery #3 without that answer.

---

## Plan C completion checklist

- [ ] `python3 -m pytest tests/edge_lab tests/killtests --no-cov -q` green from the repo root.
- [ ] `python3 -m pytest tests/test_phase1_runner_capital.py tests/test_account_size_invariant.py --no-cov -q` green.
- [ ] The slippage drift guard has been *seen* to fail on a deliberate mismatch in **both** research copies — `screen.SLIPPAGE_BPS_BY_SYMBOL` and `edge_lab.config.SLIPPAGE_BPS` — and `git diff backtesting/edge_lab/config.py` is empty afterwards.
- [ ] `trial_ledger.json` contains the 8 seeded battery-#1 variants plus the H-series, and grew by battery #2's variants — including its `NO_TRADES` and Gate-1 `KILL` variants.
- [ ] Every verdict JSON's `thresholds.num_trials_floor` equals the effective ledger floor and equals the floor printed in the matching `.md`; every variant's `num_trials_used` equals `max(num_trials_floor, n_paths_valid)`.
- [ ] `git show --stat HEAD -- .planning/evidence/killtests/trades/` lists **only** paths under `trades/20260818/` — none of the eight 2026-08-17 CSVs. (Check it this way, not with `git diff --stat`: after Step 5 has committed, a working-tree diff is empty whether or not the old files were clobbered.)
- [ ] `git diff backtesting/edge_lab/trial_ledger.json` is empty after `python3 -m pytest tests/edge_lab --no-cov -q` — the suite must not write battery rows into committed evidence.
- [ ] Verdict docs and the battery summary are committed under `.planning/evidence/killtests/`.
- [ ] The operator has been given the per-candidate verdicts and asked to direct battery #3.

## Standing rules for every future battery

1. Pre-register before implementing. No variant is added after a run starts.
2. Universe stays pinned. Re-pinning mid-battery is forbidden.
3. Every variant gets a ledger row — including `NO_TRADES` and Gate-1 deaths. They were still trials.
4. `ERROR` is never filed as `REJECT`.
5. A PASS goes through `quant-skeptic` before anything is implemented, and then through the promotion path in the design spec, `docs/superpowers/specs/2026-08-17-correctness-and-edge-loop-design.md` §4.4 (`StrategyBase` contract, ATR stops, cap-honoring sizing, the venue-floor check — a $10 cap against a $5 minimum notional confines candidates to SOL/BNB/ADA-class notionals — backtest re-confirmation through the repaired engine, and one paper trade observed end to end from `signals` row to `orders` row to notification).
6. REJECT is a complete deliverable. Write it up and stop.
